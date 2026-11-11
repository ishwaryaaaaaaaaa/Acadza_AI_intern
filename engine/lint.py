"""Zero-token structural linter. Runs on EVERY question, reported or not.

A finding is a fact about the stored record ("option D is absent"), never a fix.
The judge gets these as evidence; the guards use them to decide what may be auto.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .textify import parse

# code -> taxonomy repair it points at
REPAIR_HINT = {
    "OPT_MISSING": "option_repair", "OPT_BLANK": "option_repair", "OPT_DUP": "identical_options",
    "ANS_FORMAT": "answer_key", "ANS_TYPE": "type_mismatch", "ANS_NO_OPTION": "answer_key",
    "MARKUP_LEAK": "markup_leak", "MATH_LEAK": "markup_leak", "EXAM_REF": "exam_reference",
    "NOISE": "noise", "SOL_MISSING": "solution_missing", "SOL_CUTOFF": "solution_fix",
    "MATH_UNPARSED": None,
}


@dataclass
class Finding:
    code: str
    field: str
    detail: str

    @property
    def repair(self):
        return REPAIR_HINT.get(self.code)

    def as_dict(self):
        return {"code": self.code, "field": self.field, "detail": self.detail, "repair": self.repair}


MARK = re.compile(r"(?:\[M\d+: )?\(([A-Da-d])\)\]?")


def plain_text(doc) -> str:
    """Only text that is NOT inside a <math> node."""
    return "\n".join(doc.llm_text[s.lin_start:s.lin_end] for s in doc.segs)


def extract_options(text: str) -> dict:
    """Return {'A': 'text', ...} from the LAST consecutive run of (A)(B)... markers."""
    marks = [(m.start(), m.end(), m.group(1).upper()) for m in MARK.finditer(text)]
    # keep the last run that starts at A
    starts = [i for i, m in enumerate(marks) if m[2] == "A"]
    if not starts:
        return {}
    run = marks[starts[-1]:]
    seq, want = [], ord("A")
    for m in run:
        if ord(m[2]) == want:
            seq.append(m)
            want += 1
    opts = {}
    for i, (_st, en, letter) in enumerate(seq):
        nxt = seq[i + 1][0] if i + 1 < len(seq) else len(text)
        opts[letter] = re.sub(r"\s+", " ", text[en:nxt]).strip()
    return opts


def norm_opt(s: str) -> str:
    return re.sub(r"[\s.;,]+$", "", re.sub(r"\s+", " ", s)).strip().lower()


def lint_question(q: dict) -> list[Finding]:
    typ = q["questionType"]
    body = q[typ]
    out: list[Finding] = []
    qdoc, sdoc = parse(body["question"]), parse(body["solution"])

    # --- options (choice types only)
    if typ in ("scq", "mcq"):
        opts = extract_options(qdoc.llm_text)
        if len(opts) >= 2 and len(opts) < 4:
            missing = [l for l in "ABCD" if l not in opts]
            out.append(Finding("OPT_MISSING", "question", f"only options {','.join(opts)} found; {','.join(missing)} absent"))
        for l, t in opts.items():
            if not t.strip():
                out.append(Finding("OPT_BLANK", "question", f"option {l} is empty"))
        seen = {}
        for l, t in opts.items():
            k = norm_opt(t)
            if k and k in seen:
                out.append(Finding("OPT_DUP", "question", f"options {seen[k]} and {l} are identical: {t[:40]!r}"))
            seen.setdefault(k, l)
        if not opts:
            out.append(Finding("OPT_MISSING", "question", "no (A)(B)(C)(D) options could be parsed"))
    else:
        opts = {}

    # --- answer shape
    ans = body.get("answer")
    if typ == "scq":
        if not (isinstance(ans, str) and re.fullmatch(r"[A-D]", ans)):
            out.append(Finding("ANS_FORMAT", "answer", f"scq answer {ans!r} is not a single letter A-D"))
        elif opts and (ans not in opts or not opts[ans].strip()):
            out.append(Finding("ANS_NO_OPTION", "answer", f"key is {ans} but that option is absent or blank"))
    elif typ == "mcq":
        ok = isinstance(ans, list) and ans and all(isinstance(x, str) and re.fullmatch(r"[A-D]", x) for x in ans)
        if not ok:
            out.append(Finding("ANS_FORMAT", "answer", f"mcq answer {ans!r} is not a list of letters A-D"))
        else:
            if len(set(ans)) != len(ans):
                out.append(Finding("ANS_FORMAT", "answer", f"mcq answer {ans!r} has duplicates"))
        letters = [x for x in (ans if isinstance(ans, list) else []) if re.fullmatch(r"[A-D]", str(x))]
        if len(set(letters)) <= 1:
            out.append(Finding("ANS_TYPE", "answer", f"typed multiple-correct but key holds {len(set(letters))} valid letter(s): {ans!r}"))
    elif typ == "integerQuestion":
        if not (isinstance(ans, str) and re.fullmatch(r"-?\d+(\.\d+)?", ans.strip())):
            out.append(Finding("ANS_FORMAT", "answer", f"integer answer {ans!r} is not a plain number"))

    # --- text hygiene, per field, on plain text only (never inside math)
    for fname, doc in (("question", qdoc), ("solution", sdoc)):
        pt = plain_text(doc)
        for m in re.finditer(r"\\[A-Za-z]{2,}(?:\{[^}]*\})*|\$[^$\n]{1,60}\$|\\\(|\\\)", pt):
            out.append(Finding("MARKUP_LEAK", fname, f"raw LaTeX visible as text: {m.group(0)[:40]!r}"))
            break
        m = re.search(r"\(\s*(?:JEE|NEET|AIEEE|AIPMT|IIT|CBSE|BITSAT|MHT[- ]?CET|KCET|WBJEE|EAMCET)[^)]{0,30}\)", pt, re.I)
        if m:
            out.append(Finding("EXAM_REF", fname, f"exam tag in text: {m.group(0)!r}"))
        m = re.search(r"space for rough work|rough work|^\s*(?:Q\.?\s*)?\d{1,3}[.)]\s|\bsource\s*:", pt, re.I | re.M)
        if m:
            out.append(Finding("NOISE", fname, f"stray text: {m.group(0).strip()!r}"))
        for k, node in doc.math.items():
            for w in node.warnings:
                out.append(Finding("MATH_LEAK" if "leaked" in w else "MATH_UNPARSED", fname, f"{k}: {w}"))
            for c in node.checks:
                out.append(Finding("MATH_UNPARSED", fname, f"{k}: {c}"))

    # --- solution presence / truncation
    st = re.sub(r"\s+", " ", plain_text(sdoc)).strip()
    if not st and not sdoc.math:
        out.append(Finding("SOL_MISSING", "solution", "solution is empty"))
    elif len(st) + sum(len(m.latex) for m in sdoc.math.values()) < 12:
        out.append(Finding("SOL_MISSING", "solution", "solution is a few characters only"))
    else:
        tail = sdoc.llm_text.rstrip()
        mtail = re.search(r"(\[M\d+: (.*?)\])$", tail, re.S)
        last = (mtail.group(2) if mtail else tail).rstrip()
        if re.search(r"(=|\+|-|\\times|,|\()$", last):
            out.append(Finding("SOL_CUTOFF", "solution", f"solution ends mid-expression: ...{last[-30:]!r}"))
    return out
