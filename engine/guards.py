"""Deterministic guards. The LLM PROPOSES; this module DECIDES.

Hard rule: guards can only make a route safer (auto_apply -> faculty_review, or drop an edit).
They never promote anything, and nothing the student wrote can switch a guard off.
"""
from __future__ import annotations

import difflib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from .lint import extract_options, lint_question
from .screen import Screen, fixed_since
from .textify import EditError, digits, math_hashes, parse

TAX = json.loads((Path(__file__).resolve().parent.parent / "data_raw" / "acadza-report-fix" / "data" / "taxonomy.json")
                 .read_text(encoding="utf-8"))
VERDICTS, REPAIRS = TAX["verdicts"], TAX["repairs"]

FLOOR = 0.85          # general confidence floor for auto_apply
FLOOR_KEY = 0.90      # answer keys
GATE = 0.85           # decision-token probability below this => no auto
DIGIT_SAFE = {"spelling", "markup_leak", "answer_form", "notation"}   # these must never change a digit


@dataclass
class Decision:
    reportId: str
    questionId: str
    verdict: str
    repair: str | None = None
    edit: dict | None = None
    extra_edits: list = field(default_factory=list)
    route: str = "no_change"
    confidence: float = 0.0
    evidence: str = ""
    guards: list = field(default_factory=list)       # audit trail: [(guard, "pass"|"fail"|"note", detail)]
    preview: dict = field(default_factory=dict)      # {field: new_html} for the console diff
    duplicate_of: str | None = None

    def log(self, g, status, detail=""):
        self.guards.append((g, status, detail))

    def downgrade(self, why, g):
        self.log(g, "fail", why)
        if self.route == "auto_apply":
            self.route = "faculty_review"


# ----------------------------------------------------------------------------- answers
def norm_ans(typ: str, a):
    if a is None:
        return None
    if typ == "scq":
        return str(a).strip().upper() if re.fullmatch(r"\s*[A-Da-d]\s*", str(a)) else None
    if typ == "mcq":
        if isinstance(a, str):
            a = re.findall(r"[A-Da-d]", a)
        if not isinstance(a, list):
            return None
        L = sorted({t.upper() for x in a for t in re.findall(r"(?<![A-Za-z])[A-Da-d](?![A-Za-z])", str(x))})
        return L or None
    try:
        return format(float(str(a).strip()), "g")
    except ValueError:
        return None


def deterministic_key_fix(q: dict):
    """Zero-token repair for a malformed-but-unambiguous key, e.g. ['A, B, D'] -> ['A','B','D']."""
    typ, body = q["questionType"], q[q["questionType"]]
    a = body.get("answer")
    if typ == "mcq":
        flat = a if isinstance(a, list) else [a]
        letters = [t for x in flat for t in re.findall(r"\b[A-D]\b", str(x))]
        clean = sorted(set(letters))
        if clean and clean != a and all(re.fullmatch(r"[A-D](\s*,\s*[A-D])*|[A-D]|", str(x).strip()) for x in flat):
            return clean
    return None


def _nums(s: str) -> list:
    return re.findall(r"\d+(?:\.\d+)?", s)


def solution_supports(q: dict, cand) -> bool | None:
    """Does the STORED solution's conclusion back `cand`? True / False / None (inconclusive)."""
    typ, body = q["questionType"], q[q["questionType"]]
    sd = parse(body["solution"]).llm_text.strip()
    if not sd:
        return None
    tail = sd[-160:]
    tail_nums = set(_nums(tail))
    if typ == "integerQuestion":
        c = format(float(cand), "g") if cand is not None else None
        tn = {format(float(x), "g") for x in tail_nums}
        return True if c in tn else None
    opts = extract_options(parse(body["question"]).llm_text)
    hit = []
    for L, t in opts.items():
        n = set(_nums(t))
        if n and n <= tail_nums:
            hit.append(L)
    if not hit:
        return None
    cands = set(cand) if isinstance(cand, list) else {cand}
    if set(hit) & cands:
        return True
    return False


def key_audit(q: dict, sa: dict | None, sb: dict | None) -> dict:
    """Combine the two blind solves with the stored key and the stored solution."""
    typ, body = q["questionType"], q[q["questionType"]]
    stored = norm_ans(typ, body.get("answer"))
    out = {"status": "unknown", "answer": None, "stored": stored, "proof": [], "solves": [sa, sb]}
    if not sa or not sb:
        out["status"] = "unaudited"
        return out
    if sa.get("sound") is False and sb.get("sound") is False:
        out["status"] = "unsound"
        return out
    xa, xb = norm_ans(typ, sa.get("answer")), norm_ans(typ, sb.get("answer"))
    if xa is None or xb is None or xa != xb or sa.get("sound") is False or sb.get("sound") is False:
        out["status"] = "disputed"
        out["proof"] = [f"solver A={sa.get('answer')!r}", f"solver B={sb.get('answer')!r}"]
        return out
    out["answer"] = xa
    out["proof"] = [f"solver A={xa}", f"solver B={xb}"]
    if xa == stored:
        out["status"] = "confirmed"
        return out
    sup = solution_supports(q, xa)
    out["solution_supports"] = sup
    out["status"] = "wrong" if sup is not False else "disputed"
    if typ == "mcq" and sup is not True:      # multi-correct solved by LLMs is shakier: need the stored solution too
        out["status"] = "disputed"
        out["proof"].append("multiple-correct key change needs the stored solution to agree; it does not")
    if sup is True:
        out["proof"].append("stored solution also concludes with this answer")
    elif sup is None:
        out["proof"].append("stored solution does not reach a checkable conclusion")
    else:
        out["proof"].append("stored solution points to a DIFFERENT option")
    return out


# ----------------------------------------------------------------------------- edits
def _tags(html: str) -> list:
    return sorted(re.findall(r"</?[a-zA-Z0-9]+", html))


def apply_text_edit(q: dict, repair: str, edit: dict, solution_text: str, d: Decision):
    """Run every text guard; returns new html or None (after logging why)."""
    fld = edit["field"]
    body = q[q["questionType"]]
    html = body[fld]
    doc = parse(html)
    find, rep = edit.get("find", ""), edit.get("replace", "")
    if re.search(r"\[M\d+:", find) or re.search(r"\[M\d+:", rep):
        d.log("G4 anchor", "fail", "edit text contains a math marker [Mk: ...]")
        return None
    if doc.llm_text.count(find) == 0 and "\\\\" in find:        # model double-escaped LaTeX: \\frac -> \frac
        find, rep = find.replace("\\\\", "\\"), rep.replace("\\\\", "\\")
        edit["find"], edit["replace"] = find, rep
        d.log("G4 anchor", "note", "collapsed doubled backslashes in the model's find string")
    try:
        new = doc.apply_edit(find, rep)
    except EditError as e:
        d.log("G4 anchor/G5 math", "fail", str(e))
        return None
    d.log("G4 anchor", "pass", "find occurs exactly once, in plain text")
    if math_hashes(html) != math_hashes(new):
        d.log("G5 math", "fail", "math nodes changed")
        return None
    d.log("G5 math", "pass", f"{len(math_hashes(html))} math node(s) byte-identical")
    if _tags(html) != _tags(new):
        d.log("G7 markup", "fail", "tag structure changed")
        return None
    d.log("G7 markup", "pass", "tag structure unchanged")
    if repair in DIGIT_SAFE:
        if digits(find) != digits(rep):
            d.log("G6 digits", "fail", f"digits {digits(find)!r} -> {digits(rep)!r}")
            return None
        d.log("G6 digits", "pass", "no digit moved")
    if repair == "spelling":
        if len(find) > 80 or difflib.SequenceMatcher(None, find.lower(), rep.lower()).ratio() < 0.6:
            d.log("G6 spelling", "fail", "not a small word-level correction")
            return None
        d.log("G6 spelling", "pass", "small word-level change")
    if repair == "answer_form" and any(op[0] not in ("equal", "insert") for op in
                                        difflib.SequenceMatcher(None, find, rep).get_opcodes()):
        d.log("G6 additive", "fail", "answer_form must only add text")
        return None
    if repair == "markup_leak" and (re.search(r"[\\$]|&lt;|<[a-z]", rep)):
        d.log("G8 markup_leak", "fail", "replacement still contains raw markup")
        return None
    if repair == "stem_data":
        added = [n for n in _nums(rep) if n not in _nums(find)]
        if not added or not all(n in set(_nums(solution_text)) for n in added):
            d.log("G9 stem_data", "fail", "added value is not stated in the stored solution")
            return None
        d.log("G9 stem_data", "pass", f"added value(s) {added} are stated in the solution")
    if repair in ("solution_fix", "solution_missing"):
        if len(find) > 200 or len(rep) > 400:
            d.log("G9 solution", "fail", "rewrites too much text; authored content goes to faculty")
            return None
    if repair == "option_repair":
        sol = solution_text.lower()
        if not rep.strip() or not (any(n in set(_nums(solution_text)) for n in _nums(rep)) or rep.strip().lower() in sol):
            d.log("G9 option", "fail", "replacement option text is not derivable from the stored solution")
            return None
        d.log("G9 option", "pass", "replacement text is derivable from the stored solution")
    return new


# ----------------------------------------------------------------------------- the decision
ANSWER_CUES = {"key_challenge", "claims_value"}
CUE_LINT = {"option": {"OPT_MISSING", "OPT_BLANK", "OPT_DUP"}, "exam_ref": {"EXAM_REF"},
            "markup": {"MARKUP_LEAK", "MATH_LEAK"}}


def answer_related(s: Screen, item: dict) -> bool:
    return bool(ANSWER_CUES & set(s.cues)) or bool(s.numbers) or s.vague or s.gibberish or s.empty \
        or item.get("repair") == "answer_key" or item.get("verdict") in ("no_error", "not_actionable")


def decide(q: dict, report: dict, s: Screen, item: dict | None, audit: dict | None) -> Decision:
    qid, rid = q["_id"], report["reportId"]
    typ, body = q["questionType"], q[q["questionType"]]
    findings = lint_question(q)
    item = dict(item or {})
    d = Decision(rid, qid, "not_actionable")
    d.evidence = (item.get("evidence") or "").strip()

    # --- G12: a comment that tries to instruct us is never a reason to touch anything
    if s.injection:
        d.verdict, d.repair, d.edit, d.route = "no_error", None, None, "no_change"
        d.confidence = 0.9
        d.log("G12 injection", "pass", "comment looks like an instruction to the system: ignored, no edit possible")
        st = (audit or {}).get("status")
        d.evidence = ("Comment is an instruction aimed at the system, not an error report, so it was ignored. "
                      + ("Independent solves confirm the stored key." if st == "confirmed" else "Question left unchanged."))
        return d

    verdict = item.get("verdict") if item.get("verdict") in VERDICTS else None
    repair = item.get("repair") if item.get("repair") in REPAIRS else None
    edit = item.get("edit")
    if verdict is None:
        d.log("G1 schema", "fail", "verdict missing or outside the closed list")
        verdict, repair, edit = "not_actionable", None, None
    if verdict != "defect":
        repair = None
    if verdict == "defect" and repair is None:
        d.log("G1 schema", "fail", "defect without a valid repair type")
    d.log("G1 schema", "pass", f"{verdict}/{repair}")
    if isinstance(edit, dict) and edit.get("field") == "answer":      # normalise to exact JSON of the stored type
        edit = dict(edit)
        for k in ("find", "replace"):
            raw = edit.get(k, "")
            try:
                val = json.loads(raw)
            except (TypeError, ValueError):
                val = raw
            if isinstance(body.get("answer"), str):
                val = str(val)
            edit[k] = json.dumps(val)
    conf = float(item.get("confidence") or 0.0)
    pv, pr = item.get("_p_verdict"), item.get("_p_repair")

    # --- already_fixed is a FACT about the log, not an opinion
    fx = fixed_since(q, report["reportedAt"])
    if verdict == "already_fixed" and not fx:
        d.log("G13 already_fixed", "fail", "no faculty edit after the report; claim rejected")
        verdict = "defect" if findings else "no_error"
    elif fx and verdict in ("defect", "already_fixed") and not findings:
        verdict, repair, edit = "already_fixed", None, None
        d.log("G13 already_fixed", "pass", f"faculty edited this question at {fx[0]['at']} after the report; lint is clean now")

    # --- key audit overrides triage on anything about the answer key
    key_reportable = answer_related(s, item) and audit and audit["status"] in ("wrong", "confirmed", "disputed", "unsound")
    if key_reportable and (not s.injection):
        st = audit["status"]
        if st == "wrong" and (verdict in ("no_error", "not_actionable", "defect") and repair in (None, "answer_key")):
            verdict, repair = "defect", "answer_key"
            conf = 0.96 if audit.get("solution_supports") is True else 0.9
            d.evidence = ("Two independent blind solves give " + str(audit["answer"]) + " but the stored key is "
                          + str(audit["stored"]) + "; " + audit["proof"][-1] + ".")
            nk = audit["answer"]
            d.log("G10 key proof", "pass", "; ".join(audit["proof"]))
            edit = {"field": "answer", "find": json.dumps(body.get("answer")),
                    "replace": json.dumps(nk if typ != "integerQuestion" else str(nk))}
            if typ == "scq":
                edit["replace"] = json.dumps(nk)
        elif st == "confirmed" and repair == "answer_key" and not any(f.code in ("ANS_FORMAT", "ANS_TYPE") for f in findings):
            verdict, repair, edit = "no_error", None, None
            d.evidence = "Two independent blind solves reproduce the stored key, so the key stands."
            d.log("G10 key proof", "pass", "triage proposed a key change but solves confirm the stored key; reverted to no_error")
        elif st == "confirmed" and verdict in ("not_actionable",) and not (s.gibberish or s.empty):
            verdict = "no_error"
            d.evidence = "Checked once: two independent solves reproduce the stored key."
        elif st in ("disputed", "unsound") and (repair == "answer_key" or verdict in ("no_error", "not_actionable")):
            verdict, repair = "defect", ("unsound" if st == "unsound" else "answer_key")
            edit = None
            d.evidence = (f"The two independent solves {'both find no valid answer' if st=='unsound' else 'disagree'}"
                          f" ({'; '.join(audit['proof'])}), so a teacher must settle the key.")
            conf = 0.6

    # --- deterministic zero-token key repair (malformed list / single-letter mcq)
    if typ == "mcq" and any(f.code in ("ANS_FORMAT", "ANS_TYPE") for f in findings):
        fix = deterministic_key_fix(q)
        letters = norm_ans(typ, body.get("answer"))
        if (any(f.code == "ANS_TYPE" for f in findings) and letters and len(letters) == 1
                and audit and audit.get("answer") == letters):
            verdict, repair = "defect", "type_mismatch"
            edit = {"field": "questionType", "find": "mcq", "replace": "scq"}
            d.extra_edits = [{"field": "answer", "find": json.dumps(body.get("answer")), "replace": json.dumps(letters[0])}]
            conf = 0.93
            d.evidence = (f"Typed multiple-correct but exactly one option ({letters[0]}) is correct, confirmed by two independent "
                          f"solves; the key {body.get('answer')!r} is also malformed.")
            d.log("G10 key proof", "pass", "single correct letter confirmed by both solves")
        elif fix and audit and audit.get("answer") == fix:
            verdict, repair = "defect", "answer_key"
            edit = {"field": "answer", "find": json.dumps(body.get("answer")), "replace": json.dumps(fix)}
            conf = 0.95
            d.evidence = f"Malformed key {body.get('answer')!r} parses unambiguously to {fix}, matching two independent solves."
            d.log("G10 key proof", "pass", "format repair matches both solves")

    # --- duplicate options are authored-content territory: a model may not "repair" them as if an option were merely lost
    if verdict == "defect" and repair == "option_repair" and any(f.code == "OPT_DUP" for f in findings):
        repair = "identical_options"
        d.log("G17 lint fact", "pass", "two options are identical in the record, so this is identical_options (human only), not option_repair")

    # --- the student pointed at a place and the linter independently found a fact there: do not call it no_error
    if verdict in ("no_error", "not_actionable"):
        for cue, codes in CUE_LINT.items():
            f = next((f for f in findings if cue in s.cues and f.code in codes), None)
            if f:
                verdict, repair, conf = "defect", f.repair, min(conf, 0.8)
                d.evidence = f"Automatic check confirms what the student described: {f.detail}."
                d.log("G17 lint fact", "pass", f"{f.code}: {f.detail}")
                break

    # --- non-defects: no edit may travel with them
    if verdict != "defect":
        if edit:
            d.log("G14 no_change", "fail", "non-defect verdict cannot carry an edit; dropped")
        d.verdict, d.repair, d.edit, d.route = verdict, None, None, "no_change"
        d.confidence = conf or 0.8
        if not d.evidence:
            d.evidence = "No change needed."
        return d

    d.verdict, d.repair, d.edit = "defect", repair, (edit if edit and edit.get("field") not in (None, "none") else None)
    d.confidence = conf
    d.route = "auto_apply"
    if repair is None:
        d.route = "faculty_review"
    # G3 human-only repairs
    if repair and not REPAIRS[repair]["auto"]:
        d.route = "faculty_review"
        d.log("G3 human-only", "fail", f"'{repair}' is never auto-applied")
        if d.edit:
            d.log("G3 human-only", "note", "model's suggested edit is kept as a suggestion only")
    elif repair:
        d.log("G3 human-only", "pass", f"'{repair}' is auto-eligible")
    # G2 scope
    if d.edit and repair:
        allowed = REPAIRS[repair]["fields"]
        if d.edit["field"] not in allowed:
            d.log("G2 scope", "fail", f"'{repair}' may touch {allowed}, edit targets '{d.edit['field']}'")
            d.edit = None
            d.route = "faculty_review"
        else:
            d.log("G2 scope", "pass", f"field '{d.edit['field']}' is within {allowed}")
    # edit required for auto
    if d.route == "auto_apply" and not d.edit:
        d.downgrade("no concrete edit to apply", "G15 edit")
    # field-specific guards
    solution_text = parse(body["solution"]).llm_text
    if d.edit and d.edit["field"] in ("question", "solution") and d.route in ("auto_apply", "faculty_review"):
        new = apply_text_edit(q, repair or "", d.edit, solution_text, d)
        if new is None:
            d.route = "faculty_review"
        else:
            d.preview[d.edit["field"]] = new
    if d.edit and d.edit["field"] in ("answer", "questionType"):
        if repair in ("answer_key", "type_mismatch"):
            if not any(g[0] == "G10 key proof" and g[1] == "pass" for g in d.guards):
                d.downgrade("answer change lacks a two-solver proof", "G10 key proof")
    # G11 confidence floors, G-gate probabilities
    floor = FLOOR_KEY if repair in ("answer_key", "type_mismatch") else FLOOR
    if d.confidence < floor:
        d.downgrade(f"confidence {d.confidence:.2f} below floor {floor}", "G11 confidence")
    else:
        d.log("G11 confidence", "pass", f"{d.confidence:.2f} >= {floor}")
    if repair not in ("answer_key", "type_mismatch"):
        for name, p in (("verdict", pv), ("repair", pr)):
            if p is not None and p < GATE:
                d.downgrade(f"{name} token probability {p:.2f} below {GATE}", "G16 token gate")
    # duplicates / multi-report handled by the pipeline
    if d.route == "auto_apply":
        d.log("route", "pass", "all guards passed")
    if not d.evidence:
        d.evidence = "Defect confirmed."
    return d
