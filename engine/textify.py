"""Math-safe linearizer for Acadza question HTML.

Two promises:
1. The LLM sees readable LaTeX-ish text with every <math> node labelled [Mk: ...].
2. Any edit the LLM proposes is applied to the ORIGINAL html, on plain text only.
   It can never touch, re-serialise or "round-trip" a MathML node.

Public API:
    doc = parse(html)
    doc.llm_text            text the model reads
    doc.math                {"M1": MathNode, ...}
    doc.apply_edit(find, replace)  -> new html   (raises EditError)
    math_hashes(html)       ordered fingerprints of every <math> node
"""
from __future__ import annotations

import hashlib
import html as _html
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser


class EditError(Exception):
    pass


# ----------------------------------------------------------------- symbols
GREEK = {
    "α": r"\alpha", "β": r"\beta", "γ": r"\gamma", "δ": r"\delta", "ε": r"\epsilon",
    "ϵ": r"\epsilon", "ζ": r"\zeta", "η": r"\eta", "θ": r"\theta", "ϑ": r"\vartheta",
    "ι": r"\iota", "κ": r"\kappa", "λ": r"\lambda", "μ": r"\mu", "ν": r"\nu",
    "ξ": r"\xi", "π": r"\pi", "ρ": r"\rho", "σ": r"\sigma", "τ": r"\tau", "υ": r"\upsilon",
    "φ": r"\varphi", "ϕ": r"\phi", "χ": r"\chi", "ψ": r"\psi", "ω": r"\omega",
    "Γ": r"\Gamma", "Δ": r"\Delta", "Θ": r"\Theta", "Λ": r"\Lambda", "Ξ": r"\Xi",
    "Π": r"\Pi", "Σ": r"\Sigma", "Φ": r"\Phi", "Ψ": r"\Psi", "Ω": r"\Omega",
}
OPS = {
    "−": "-", "–": "-", "×": r"\times", "·": r"\cdot", "⋅": r"\cdot", "÷": r"\div",
    "±": r"\pm", "∓": r"\mp", "≈": r"\approx", "≠": r"\neq", "≤": r"\le", "≥": r"\ge",
    "∞": r"\infty", "→": r"\rightarrow", "←": r"\leftarrow", "⇒": r"\Rightarrow",
    "⇔": r"\Leftrightarrow", "∴": r"\therefore", "∵": r"\because", "∘": r"\circ",
    "°": r"^\circ", "∝": r"\propto", "∂": r"\partial", "∇": r"\nabla", "∫": r"\int",
    "∑": r"\sum", "√": r"\sqrt", "′": "'", "…": r"\ldots", "⁡": "", "⁢": "",
    "⁣": "", " ": " ", "∈": r"\in", "∥": r"\parallel", "⊥": r"\perp",
    "∠": r"\angle", "≡": r"\equiv", "∼": r"\sim", "∆": r"\Delta",
}
BOLD_ITALIC = {  # mathematical alphanumerics -> plain letter + style
    **{chr(0x1D400 + i): ("bold", chr(65 + i)) for i in range(26)},
    **{chr(0x1D41A + i): ("bold", chr(97 + i)) for i in range(26)},
}

# ----------------------------------------------------------------- tiny MathML tree
@dataclass
class El:
    tag: str
    attrs: dict
    kids: list = field(default_factory=list)  # El | str

VOID = {"mspace", "mprescripts", "none", "malignmark", "maligngroup"}


class _TreeBuilder(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = El("root", {})
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        e = El(tag, dict(attrs))
        self.stack[-1].kids.append(e)
        if tag not in VOID:
            self.stack.append(e)

    def handle_startendtag(self, tag, attrs):
        self.stack[-1].kids.append(El(tag, dict(attrs)))

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                return

    def handle_data(self, data):
        k = self.stack[-1].kids
        if k and isinstance(k[-1], str):
            k[-1] += data
        else:
            k.append(data)


def parse_mathml(src: str) -> El:
    tb = _TreeBuilder()
    tb.feed(src)
    tb.close()
    m = next((k for k in tb.root.kids if isinstance(k, El) and k.tag == "math"), tb.root)
    _prune(m)
    return m


LEAF = {"mi", "mn", "mo", "mtext", "ms"}


def _prune(e: El) -> None:
    """Drop whitespace-only text between structural children (it breaks child counts)."""
    if e.tag in LEAF:
        return
    e.kids = [k for k in e.kids if isinstance(k, El) or k.strip()]
    for k in e.kids:
        if isinstance(k, El):
            _prune(k)


# ----------------------------------------------------------------- MathML -> LaTeX
class Ctx:
    def __init__(self):
        self.leaves: list[str] = []      # every visible leaf text, in order
        self.warnings: list[str] = []


def _text(e: El) -> str:
    return "".join(k if isinstance(k, str) else _text(k) for k in e.kids)


def _join(parts: list[str]) -> str:
    out = ""
    for p in parts:
        if not p:
            continue
        if out and re.search(r"\\[A-Za-z]+$", out) and re.match(r"[A-Za-z]", p):
            out += " "
        out += p
    return out


def _atom(s: str, base: bool = False) -> str:
    """Brace a sub/superscript unless it is one symbol; bases only when compound."""
    s = s.strip()
    if base:
        simple = re.fullmatch(r"[A-Za-z0-9.]+|\\[A-Za-z]+|\\mathrm\{[A-Za-z]+\}|\(.*\)", s)
        return s if simple else "{" + s + "}"
    return s if (len(s) == 1 or re.fullmatch(r"\\[A-Za-z]+", s)) else "{" + s + "}"


def _sym(ch: str) -> str:
    if ch in GREEK:
        return GREEK[ch]
    if ch in OPS:
        return OPS[ch]
    return ch


def _leaf_text(raw: str, c: "Ctx | None" = None) -> str:
    raw = raw.replace(" ", " ")
    if "\\" in raw and c is not None:
        c.warnings.append(f"raw LaTeX leaked inside MathML leaf: {raw!r}")
        return raw.replace("\\", "")
    out = []
    for ch in raw:
        if ch in BOLD_ITALIC:
            out.append(BOLD_ITALIC[ch][1])
        else:
            out.append(_sym(ch))
    return _join(out)


def _conv(e, c: Ctx) -> str:
    if isinstance(e, str):
        s = e.strip()
        if s:
            c.warnings.append(f"stray text in mathml: {s[:20]!r}")
            c.leaves.append(s)
        return s
    t = e.tag
    k = e.kids
    if t in ("math", "mrow", "mstyle", "mpadded", "mphantom", "semantics"):
        return _join([_conv(x, c) for x in k])
    if t == "mn":
        s = _text(e).strip()
        c.leaves.append(s)
        return s
    if t == "mi":
        raw = _text(e).strip()
        c.leaves.append(raw)
        s = _leaf_text(raw, c)
        mv = e.attrs.get("mathvariant", "")
        if any(ch in BOLD_ITALIC for ch in raw) or mv == "bold":
            return r"\mathbf{" + s + "}"
        if len(raw) > 1 and raw.isascii() and raw.isalpha():
            return r"\mathrm{" + s + "}"
        return s
    if t == "mo":
        raw = _text(e).strip()
        c.leaves.append(raw)
        return _leaf_text(raw, c)
    if t in ("mtext", "ms"):
        raw = _text(e)
        c.leaves.append(raw.strip())
        raw = raw.replace(" ", " ").strip()
        return r"\text{" + raw + "}" if raw else ""
    if t == "mspace":
        return " "
    if t == "msub" and len(k) == 2:
        return _atom(_conv(k[0], c), True) + "_" + _atom(_conv(k[1], c))
    if t == "msup" and len(k) == 2:
        return _atom(_conv(k[0], c), True) + "^" + _atom(_conv(k[1], c))
    if t == "msubsup" and len(k) == 3:
        return _atom(_conv(k[0], c), True) + "_" + _atom(_conv(k[1], c)) + "^" + _atom(_conv(k[2], c))
    if t == "mfrac" and len(k) == 2:
        return r"\frac{" + _conv(k[0], c) + "}{" + _conv(k[1], c) + "}"
    if t == "msqrt":
        return r"\sqrt{" + _join([_conv(x, c) for x in k]) + "}"
    if t == "mroot" and len(k) == 2:
        return r"\sqrt[" + _conv(k[1], c) + "]{" + _conv(k[0], c) + "}"
    if t == "mover" and len(k) == 2:
        base, over = _conv(k[0], c), _conv(k[1], c)
        acc = {r"\rightarrow": r"\vec", "-": r"\overline", "¯": r"\overline", "^": r"\hat",
               "~": r"\tilde", ".": r"\dot", "→": r"\vec"}.get(over.strip())
        return f"{acc}{{{base}}}" if acc else r"\overset{" + over + "}{" + base + "}"
    if t == "munder" and len(k) == 2:
        return r"\underset{" + _conv(k[1], c) + "}{" + _conv(k[0], c) + "}"
    if t == "munderover" and len(k) == 3:
        return _conv(k[0], c) + "_{" + _conv(k[1], c) + "}^{" + _conv(k[2], c) + "}"
    if t == "mfenced":
        o, cl = e.attrs.get("open", "("), e.attrs.get("close", ")")
        return o + ",".join(_conv(x, c) for x in k) + cl
    if t == "mtable":
        rows = [x for x in k if isinstance(x, El)]
        return r"\begin{array}" + r" \\ ".join(_conv(r, c) for r in rows) + r"\end{array}"
    if t == "mtr":
        return " & ".join(_conv(x, c) for x in k if isinstance(x, El))
    if t == "mtd":
        return _join([_conv(x, c) for x in k])
    # unknown: never drop silently
    c.warnings.append(f"unknown element <{t}>")
    return _join([_conv(x, c) for x in k])


@dataclass
class MathNode:
    id: str
    raw: str
    latex: str
    sha: str
    leaves: list
    warnings: list
    checks: list = field(default_factory=list)   # failed fidelity checks

    @property
    def ok(self) -> bool:
        return not self.warnings and not self.checks


def _norm(raw: str) -> str:
    return re.sub(r"\s+", " ", raw).strip()


def sha(raw: str) -> str:
    return hashlib.sha1(_norm(raw).encode("utf-8")).hexdigest()[:12]


def to_latex(raw: str, mid: str = "M?") -> MathNode:
    tree = parse_mathml(raw)
    c = Ctx()
    latex = re.sub(r"\s+", " ", _conv(tree, c)).strip()
    checks = []
    # fidelity: every digit that is in the MathML text must be in the latex, same order
    src_digits = "".join(re.findall(r"\d", "".join(c.leaves)))
    out_digits = "".join(re.findall(r"\d", latex))
    if src_digits != out_digits:
        checks.append(f"digit mismatch {src_digits!r} vs {out_digits!r}")
    # every ascii letter leaf of an <mi>/<mtext> must survive in order
    src_letters = "".join(re.findall(r"[A-Za-z]", "".join(
        BOLD_ITALIC.get(ch, ("", ch))[1] for ch in "".join(c.leaves) if ch not in GREEK)))
    latex_chk = latex.replace(r"\begin{array}", "").replace(r"\end{array}", "")
    stripped = re.sub(r"\\(?:frac|sqrt|times|cdot|div|pm|mp|approx|neq|le|ge|infty|rightarrow|leftarrow|"
                      r"Rightarrow|Leftrightarrow|therefore|because|circ|propto|partial|nabla|int|sum|ldots|in|"
                      r"parallel|perp|angle|equiv|sim|mathrm|mathbf|text|vec|overline|hat|tilde|dot|overset|"
                      r"underset|left|right|[A-Za-z]+)(?![A-Za-z])", "", latex_chk)
    # the replacement above strips text{...} command names only; text bodies stay
    out_letters = "".join(re.findall(r"[A-Za-z]", stripped))
    if src_letters != out_letters:
        checks.append(f"letter mismatch {src_letters!r} vs {out_letters!r}")
    return MathNode(mid, raw, latex, sha(raw), c.leaves, c.warnings, checks)


# ----------------------------------------------------------------- HTML document
TOKEN = re.compile(r"(<math\b.*?</math>)|(<[^>]+>)|([^<]+)", re.S)
ENT = re.compile(r"&(?:#x[0-9A-Fa-f]+|#[0-9]+|[A-Za-z][A-Za-z0-9]*);")


@dataclass
class Seg:
    lin_start: int
    lin_end: int
    orig_start: int
    orig_end: int
    chars: list      # per linear char: (orig_start, orig_end) in html


@dataclass
class Doc:
    html: str
    llm_text: str
    math: dict
    segs: list

    # -- finding where a linear-text span lives in the original html
    def locate(self, find: str) -> tuple[int, int]:
        n = self.llm_text.count(find)
        if not find:
            raise EditError("empty find")
        if n != 1:
            raise EditError(f"find string occurs {n} times in the text the model saw (need exactly 1)")
        a = self.llm_text.index(find)
        b = a + len(find)
        for s in self.segs:
            if s.lin_start <= a and b <= s.lin_end:
                i, j = a - s.lin_start, b - s.lin_start
                return s.chars[i][0], s.chars[j - 1][1]
        raise EditError("find string touches math, a line break, or spans several tags; faculty must edit")

    def apply_edit(self, find: str, replace: str) -> str:
        a, b = self.locate(find)
        new = self.html[:a] + _html.escape(replace, quote=False) + self.html[b:]
        before, after = math_hashes(self.html), math_hashes(new)
        if before != after:
            raise EditError("edit would alter a <math> node")
        return new


def math_hashes(html: str) -> list:
    return [sha(m.group(0)) for m in re.finditer(r"<math\b.*?</math>", html, re.S)]


def parse(html: str) -> Doc:
    lin: list[str] = []
    pos = 0
    segs: list[Seg] = []
    math: dict = {}
    oi = 0

    def put_virtual(s: str):
        nonlocal pos
        lin.append(s)
        pos += len(s)

    def newline():
        if lin and not "".join(lin[-1:]).endswith("\n") and pos:
            put_virtual("\n")

    for m in TOKEN.finditer(html):
        raw = m.group(0)
        if m.group(1):
            mid = f"M{len(math) + 1}"
            node = to_latex(raw, mid)
            math[mid] = node
            put_virtual(f"[{mid}: {node.latex}]")
        elif m.group(2):
            tag = raw.lower()
            if re.match(r"<br\b", tag):
                put_virtual("\n")
            elif re.match(r"</(p|h\d|li|ol|ul|div)>", tag):
                newline()
            elif re.match(r"<li\b", tag):
                put_virtual("- ")
            elif tag.startswith("<sup"):
                put_virtual("^(")
            elif tag.startswith("<sub"):
                put_virtual("_(")
            elif tag in ("</sup>", "</sub>"):
                put_virtual(")")
        else:
            # plain text node: map every decoded char back to its raw span
            start = m.start(3)
            chars = []
            out = []
            i = 0
            while i < len(raw):
                em = ENT.match(raw, i)
                if em:
                    dec = _html.unescape(em.group(0)).replace(" ", " ")
                    for ch in dec:
                        out.append(ch)
                        chars.append((start + i, start + em.end()))
                    i = em.end()
                else:
                    out.append(raw[i])
                    chars.append((start + i, start + i + 1))
                    i += 1
            txt = "".join(out).replace(" ", " ")
            segs.append(Seg(pos, pos + len(txt), start, start + len(raw), chars))
            lin.append(txt)
            pos += len(txt)
    llm = "".join(lin)
    return Doc(html, llm, math, segs)


def digits(s: str) -> str:
    return "".join(re.findall(r"\d", s))
