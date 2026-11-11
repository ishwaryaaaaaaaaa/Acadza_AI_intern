"""Case review: what one question looks like now, what the AI proposes, and faculty actions.

The "live record" here is Acadza's question plus the patches this console has applied (engine auto-fixes and
faculty approvals). Original data files are never modified, so every change is reversible and auditable.
Manual edits go through the same math-safe editor as the AI: exact-once anchors, MathML untouched.
"""
from __future__ import annotations

import copy
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from engine.screen import screen_comment  # noqa: E402
from engine.textify import EditError, math_hashes, parse  # noqa: E402

from .settings import actor as settings_actor  # noqa: E402
from .settings import load as load_settings  # noqa: E402
from .store import ISSUE_LABEL, OPEN, RESOLVED, STORE, _lock, now  # noqa: E402

REPAIR_PLAIN = {
    "answer_key": "the answer key is wrong", "type_mismatch": "the question type is set wrong",
    "unsound": "no option is correct as written", "wrong_question": "the solution doesn't belong to this question",
    "option_repair": "an option is missing or blank", "identical_options": "two options are identical",
    "diagram": "the figure is missing", "stem_data": "a value needed to solve it is missing",
    "solution_fix": "the solution has an error", "solution_missing": "the solution is missing",
    "notation": "a symbol was lost", "wrong_chapter": "it is filed under the wrong chapter",
    "syllabus": "it may be outside the syllabus", "spelling": "there is a spelling mistake",
    "markup_leak": "raw code shows instead of math", "exam_reference": "an exam tag is left in the text",
    "noise": "there is stray text", "answer_form": "the unit / answer form is not stated",
}


# ------------------------------------------------------------------ live record = original + patches
def _patches() -> dict:
    st = STORE.state
    if "patches" not in st:                       # older state files: build engine patches once
        st["patches"] = {}
        for qid, c in st["cases"].items():
            if c["status"] in ("auto_applied", "confirmed"):
                st["patches"][qid] = engine_patch(qid)
        STORE._save()
    return st["patches"]


def engine_patch(qid: str) -> dict:
    p = STORE.primary(qid)
    full = next(x for x in json.loads((ROOT / "results_full.json").read_text(encoding="utf-8"))
                if x["reportId"] == p["reportId"])
    patch = {}
    for e in [full.get("edit")] + list(full.get("extra_edits") or []):
        if not e:
            continue
        if e["field"] == "answer":
            patch["answer"] = json.loads(e["replace"])
        elif e["field"] == "questionType":
            patch["questionType"] = e["replace"]
        elif e["field"] in ("question", "solution") and full.get("preview", {}).get(e["field"]):
            patch[e["field"]] = full["preview"][e["field"]]
    return patch


def live(qid: str) -> dict:
    """{type, question, solution, answer, chapter} as students see it now."""
    q = STORE.questions[qid]
    t = q["questionType"]
    rec = {"type": t, "question": q[t]["question"], "solution": q[t]["solution"], "answer": q[t].get("answer"),
           "chapter": q.get("chapter")}
    p = _patches().get(qid) or {}
    if "questionType" in p:
        rec["type"] = p["questionType"]
    for k in ("question", "solution", "answer", "chapter"):
        if k in p:
            rec[k] = p[k]
    return rec


def original(qid: str) -> dict:
    q = STORE.questions[qid]
    t = q["questionType"]
    return {"type": t, "question": q[t]["question"], "solution": q[t]["solution"], "answer": q[t].get("answer"),
            "chapter": q.get("chapter")}


# ------------------------------------------------------------------ display helpers
MARK = re.compile(r"\(\s*([A-D])\s*\)")


def split_options(html: str):
    """Stem + per-option HTML, cut at the last (A)(B)(C)(D) run. Browsers repair the cut tags when rendering."""
    marks = [(m.group(1), m.start(), m.end()) for m in MARK.finditer(html)]
    starts = [i for i, m in enumerate(marks) if m[0] == "A"]
    if not starts:
        return html, None
    run, want = [], "A"
    for m in marks[starts[-1]:]:
        if m[0] == want:
            run.append(m)
            want = chr(ord(want) + 1)
    if len(run) < 2:
        return html, None
    opts = {}
    for i, (letter, s, e) in enumerate(run):
        end = run[i + 1][1] if i + 1 < len(run) else len(html)
        opts[letter] = html[e:end]
    return html[:run[0][1]], opts


def fmt_key(v) -> str:
    if isinstance(v, list):
        return ", ".join(x for x in v if x) or "—"
    return "—" if v in (None, "") else str(v)


def key_letters(v) -> list:
    if isinstance(v, list):
        return sorted({t for x in v for t in re.findall(r"[A-D]", str(x))})
    return re.findall(r"^[A-D]$", str(v or "").strip())


MODEL_NAME = {"command-a-plus-05-2026": "Cohere Command A+", "gemini-3.5-flash": "Gemini Flash",
              "gemini-3.5-flash-lite": "Gemini Flash-Lite"}


def solver_name(sv: dict | None, i: int) -> str:
    m = (sv or {}).get("_model")
    return f"Solver {i}" + (f" ({MODEL_NAME.get(m, m)})" if m else "")


def self_contradicts(sv: dict) -> bool:
    """Picked an answer while its own working ends by calling the question unsound."""
    w = (sv.get("working") or "")[-300:].lower()
    return sv.get("sound") is not False and sv.get("answer") not in (None, "", []) and bool(
        re.search(r"\bunsound\b|none of the options|no option (is|matches)|no correct option", w))


def conf_label(c: float) -> str:
    return "High Confidence" if c >= 0.9 else ("Medium Confidence" if c >= 0.75 else "Low Confidence")


def _context(text: str, find: str, pad: int = 60, math: dict | None = None):
    """Words around the edit. Never cuts a math block in half, so it can be shown rendered."""
    i = text.find(find)
    if i < 0:
        return None
    a, b = max(0, i - pad), min(len(text), i + len(find) + pad)
    for k, node in (math or {}).items():
        marker = f"[{k}: {node.latex}]"
        j = text.find(marker)
        while j >= 0:
            if j < a < j + len(marker):
                a = j
            if j < b < j + len(marker):
                b = j + len(marker)
            j = text.find(marker, j + 1)
    return {"before": ("…" if a else "") + text[a:i], "after": text[i + len(find):b] + ("…" if b < len(text) else "")}


def math_map(html: str) -> dict:
    """{M1: {latex, mathml}} so the console can show each [Mk: …] block as real, rendered math."""
    return {k: {"latex": n.latex, "mathml": n.raw} for k, n in parse(html).math.items()}


def proposal(qid: str, full: dict) -> dict:
    """What the AI wants to change, in a form the diff view can show."""
    e = full.get("edit")
    if not e:
        return {"kind": "none"}
    if e["field"] in ("answer", "questionType"):
        orig = original(qid)
        new_ans = orig["answer"]
        new_type = orig["type"]
        for x in [e] + list(full.get("extra_edits") or []):
            if x["field"] == "answer":
                new_ans = json.loads(x["replace"])
            if x["field"] == "questionType":
                new_type = x["replace"]
        return {"kind": "key", "currentKey": fmt_key(orig["answer"]), "suggestedKey": fmt_key(new_ans),
                "currentType": orig["type"], "suggestedType": new_type, "suggestedLetters": key_letters(new_ans)}
    orig_html = original(qid)[e["field"]]
    doc = parse(orig_html)
    text = doc.llm_text
    ctx = _context(text, e["find"], math=doc.math)
    return {"kind": "text", "field": e["field"], "find": e["find"], "replace": e["replace"],
            "context": ctx, "afterHtml": (full.get("preview") or {}).get(e["field"])}


def checks(qid: str, full: dict) -> list:
    """Short, verifiable statements for the AI Check card. ok=True green tick, ok=False red cross."""
    out = []
    audit = full.get("audit") or {}
    solves = full.get("solves") or []
    rep, verdict = full.get("repair"), full["verdict"]
    if audit.get("status") in ("wrong", "confirmed", "disputed", "unsound"):
        a = [(s or {}).get("answer") for s in solves]
        if audit["status"] == "unsound":
            out.append({"ok": False, "text": "Two independent solvers both found no valid answer as written."})
        elif audit["status"] == "disputed":
            said = lambda i: ("found no valid option" if solves[i] and (solves[i].get("sound") is False or a[i] in (None, "", []))
                              else f"picked {fmt_key(a[i])}")
            out.append({"ok": False, "text": f"The two independent solvers disagree: "
                                             f"{solver_name(solves[0], 1)} {said(0)}, {solver_name(solves[1], 2)} {said(1)}."})
            for i, sv in enumerate(solves):
                if sv and self_contradicts(sv):
                    out.append({"ok": None, "text": f"{solver_name(sv, i + 1)} gave an answer but its own working "
                                                    f"concludes the question is unsound, so its answer is unreliable."})
        else:
            out.append({"ok": True, "text": f"Two independent solvers, without seeing the key, both get {fmt_key(audit.get('answer'))}."})
        if audit.get("solution_supports") is True:
            out.append({"ok": True, "text": "The stored solution also concludes with that answer."})
        if audit["status"] == "wrong":
            out.append({"ok": False, "text": f"The current answer key ({fmt_key(audit.get('stored'))}) is incorrect."})
        elif audit["status"] == "confirmed" and verdict == "no_error":
            out.append({"ok": True, "text": f"So the current answer key ({fmt_key(audit.get('stored'))}) is correct."})
    if verdict == "defect" and rep not in ("answer_key",):
        out.append({"ok": False, "text": f"Problem found: {REPAIR_PLAIN.get(rep, rep)}."})
    for g in full.get("guards") or []:
        name, status, detail = g
        if status != "pass":
            continue
        if name.startswith("G5"):
            n = int(re.match(r"\d+", detail).group(0)) if re.match(r"\d+", detail) else 0
            if n:
                out.append({"ok": True, "text": f"All {n} math expression{'s' if n > 1 else ''} stay exactly as they were."})
        elif name == "G6 digits":
            out.append({"ok": True, "text": "No number or digit changes."})
        elif name == "G6 spelling":
            out.append({"ok": True, "text": "Only a small word-level correction."})
        elif name.startswith("G9"):
            out.append({"ok": True, "text": detail[0].upper() + detail[1:] + "."})
        elif name.startswith("G17") and "identical" in detail:
            out.append({"ok": True, "text": "The record really does contain two identical options."})
        elif name.startswith("G17"):
            out.append({"ok": True, "text": "An automatic check confirms what the student described."})
    if full["route"] == "faculty_review" and rep:
        if rep and not STORE_TAX_AUTO.get(rep, True):
            out.append({"ok": None, "text": f"'{ISSUE_LABEL.get(rep, rep)}' needs authored content, so a teacher decides."})
        elif not full.get("edit"):
            out.append({"ok": None, "text": "No safe automatic edit exists; a teacher must write the fix."})
        else:
            out.append({"ok": None, "text": "A safety check held this edit for a teacher instead of applying it."})
    if not out:
        out.append({"ok": True, "text": full.get("evidence") or "Checked."})
    # de-duplicate, keep order
    seen, res = set(), []
    for c in out:
        if c["text"] not in seen:
            seen.add(c["text"])
            res.append(c)
    return res[:6]


TAX = json.loads((ROOT / "data_raw" / "acadza-report-fix" / "data" / "taxonomy.json").read_text(encoding="utf-8"))
STORE_TAX_AUTO = {k: v["auto"] for k, v in TAX["repairs"].items()}


def _full(qid: str) -> list:
    if not hasattr(STORE, "_full_cache"):
        STORE._full_cache = {x["reportId"]: x for x in json.loads((ROOT / "results_full.json").read_text(encoding="utf-8"))}
    return [x for x in STORE._full_cache.values() if x["questionId"] == qid]


def detail(qid: str) -> dict:
    summary = STORE.case_summary(qid)
    p = STORE.primary(qid)
    full = next(x for x in _full(qid) if x["reportId"] == p["reportId"])
    rec = live(qid)
    stem, opts = split_options(rec["question"]) if rec["type"] in ("scq", "mcq") else (rec["question"], None)
    reports = []
    for x in sorted(_full(qid), key=lambda x: STORE.reports[x["reportId"]]["reportedAt"]):
        r = STORE.reports[x["reportId"]]
        sc = screen_comment(r)
        reports.append({"reportId": r["reportId"], "comment": r["comment"], "source": r["source"],
                        "reportedAt": r["reportedAt"],
                        "flag": "instruction" if sc.injection else ("gibberish" if sc.gibberish else ("vague" if sc.vague else None)),
                        "verdict": x["verdict"], "reply": x["student_reply"], "replySource": x.get("reply_source")})
    case = STORE.state["cases"][qid]
    return {
        **summary,
        # Never show "High Confidence" next to evidence that contradicts itself.
        "confidenceLabel": ("Mixed Signals" if (full.get("audit") or {}).get("status") == "disputed"
                            else conf_label(summary["confidence"])),
        "evidence": p.get("evidence"),
        "route": p.get("route"),
        "question": {"type": rec["type"], "stemHtml": stem, "options": opts, "fullHtml": rec["question"],
                     "solutionHtml": rec["solution"], "answer": fmt_key(rec["answer"]),
                     "answerLetters": key_letters(rec["answer"]), "chapter": rec["chapter"],
                     "patched": bool(_patches().get(qid))},
        "original": {"answer": fmt_key(original(qid)["answer"]), "type": original(qid)["type"]},
        "proposal": proposal(qid, full),
        "checks": checks(qid, full),
        "reports": reports,
        "solverWork": [{"name": solver_name(s, i + 1), "answer": fmt_key((s or {}).get("answer")),
                        "noAnswer": (s or {}).get("sound") is False or (s or {}).get("answer") in (None, "", []),
                        "selfContradicts": self_contradicts(s), "working": (s or {}).get("working")}
                       for i, s in enumerate(full.get("solves") or []) if s],
        "guards": full.get("guards") or [],
        "decidedBy": case.get("decidedBy"),
        "decidedAt": case.get("updatedAt") if case["status"] not in OPEN else None,
        "history": [e for e in STORE.activity() if e["questionId"] == qid],
        "editable": {"question": parse(rec["question"]).llm_text, "solution": parse(rec["solution"]).llm_text},
        "math": {"question": math_map(rec["question"]), "solution": math_map(rec["solution"]),
                 "original": math_map(original(qid)[p["edit"]["field"]]) if (p.get("edit") or {}).get("field")
                 in ("question", "solution") else {}},
    }


# ------------------------------------------------------------------ faculty actions
class ActionError(Exception):
    pass


def _validate_answer(qtype: str, value):
    if qtype == "scq":
        if not (isinstance(value, str) and re.fullmatch(r"[A-D]", value)):
            raise ActionError("Single-correct answer must be one letter A–D.")
        return value
    if qtype == "mcq":
        if not (isinstance(value, list) and value and all(re.fullmatch(r"[A-D]", str(v)) for v in value)):
            raise ActionError("Multiple-correct answer must be a list of letters A–D.")
        return sorted(set(value))
    if not re.fullmatch(r"-?\d+(\.\d+)?", str(value).strip()):
        raise ActionError("Integer answer must be a number.")
    return str(value).strip()


def apply_changes(qid: str, changes: list) -> dict:
    """Apply faculty edits on top of the live record. Returns the new patch (not yet saved)."""
    rec = live(qid)
    patch = copy.deepcopy(_patches().get(qid) or {})
    for ch in changes:
        f = ch.get("field")
        if f in ("question", "solution"):
            find, rep = ch.get("find", ""), ch.get("replace", "")
            try:
                new = parse(rec[f]).apply_edit(find, rep)
            except EditError as e:
                msg = str(e)
                if "occurs 0 times" in msg:
                    msg = "the Find text isn't in the current version. Copy it exactly from the text above"
                elif "occurs" in msg:
                    msg = "the Find text appears more than once. Include a few more words so it is unique"
                elif "touches math" in msg:
                    msg = ("the Find text touches a math block [M…], a line break or formatting. "
                           "Choose a phrase of plain words next to it")
                raise ActionError(f"{f.title()} edit refused: {msg}.")
            if math_hashes(rec[f]) != math_hashes(new):
                raise ActionError("That edit would change a math expression; edit outside the [M…] blocks.")
            rec[f] = new
            patch[f] = new
        elif f == "questionType":
            if ch.get("value") not in ("scq", "mcq", "integerQuestion"):
                raise ActionError("Question type must be scq, mcq or integerQuestion.")
            rec["type"] = patch["questionType"] = ch["value"]
        elif f == "answer":
            patch["answer"] = rec["answer"] = _validate_answer(rec["type"], ch.get("value"))
        elif f == "chapter":
            v = str(ch.get("value", "")).strip()
            if not v:
                raise ActionError("Chapter cannot be empty.")
            patch["chapter"] = rec["chapter"] = v
        else:
            raise ActionError(f"Unknown field {f!r}.")
    return patch


def act(qid: str, action: str, changes: list | None = None, note: str = "") -> dict:
    if qid not in STORE.state["cases"]:
        raise ActionError("Unknown question.")
    with _lock:
        case = STORE.state["cases"][qid]
        status = case["status"]
        disp = qid[:8].upper()
        patches = _patches()
        before = copy.deepcopy(patches.get(qid))
        if action in ("approve", "reject", "edit") and status not in OPEN:
            raise ActionError("This case is already resolved. Reopen it first.")
        if action == "approve":
            if status == "auto_applied":
                new_status, kind, title, det = "confirmed", "confirmed", f"{disp} confirmed", "Auto-fix confirmed by faculty"
            else:
                p = STORE.primary(qid)
                full = next(x for x in _full(qid) if x["reportId"] == p["reportId"])
                if not full.get("edit"):
                    raise ActionError("There is no suggested fix to approve. Use Edit Manually.")
                patches[qid] = engine_patch(qid) or {}
                if not patches[qid]:
                    raise ActionError("The suggested fix could not be applied safely. Use Edit Manually.")
                new_status, kind, title = "approved", "fixed", f"{disp} fixed"
                det = STORE._change_text(qid)
        elif action == "reject":
            if load_settings()["requireRejectNote"] and not note.strip():
                raise ActionError("Please add a short reason before rejecting (Settings: require a note).")
            if status == "auto_applied":
                patches.pop(qid, None)
                new_status, kind, title, det = "reverted", "reverted", f"{disp} reverted", "Auto-fix undone; original restored"
            else:
                new_status, kind, title, det = "rejected", "rejected", f"{disp} kept as is", "Faculty rejected the suggested fix"
        elif action == "edit":
            if not changes:
                raise ActionError("No changes given.")
            patches[qid] = apply_changes(qid, changes)
            new_status, kind, title = "edited", "fixed", f"{disp} fixed"
            det = "Edited manually: " + ", ".join(sorted({c["field"] for c in changes}))
        elif action == "reopen":
            if status in OPEN:
                raise ActionError("This case is already open.")
            new_status, kind, title, det = "needs_decision", "review", f"{disp} reopened", "Sent back for review"
        else:
            raise ActionError(f"Unknown action {action!r}.")
        who = settings_actor()
        case.update({"status": new_status, "updatedAt": now(), "decidedBy": who})
        ev = {"at": now(), "actor": "Faculty", "by": who, "questionId": qid, "kind": kind, "title": title, "detail": det,
              "action": action, "note": note, "before": before, "after": copy.deepcopy(patches.get(qid))}
        STORE.state["events"].append(ev)
        STORE._save()
        return ev


assert RESOLVED  # imported for callers


# ------------------------------------------------------------------ My Reviews: built ONLY from faculty actions
DECISION = {"approve": "approved", "edit": "edited", "reject": "rejected"}


def ai_verdict(qid: str) -> dict:
    p = STORE.primary(qid)
    c = round(p["confidence"] * 100)
    if p["verdict"] != "defect":
        return {"label": "No Defect", "tone": "ok", "confidence": c}
    if p["route"] == "faculty_review" and p["confidence"] < 0.8:
        return {"label": "Review", "tone": "warn", "confidence": c}
    return {"label": "Defect", "tone": "bad", "confidence": c}


def reviews() -> dict:
    evs = [e for e in STORE.state["events"] if e.get("actor") == "Faculty"]
    rows = []
    for i, e in enumerate(evs):
        if e.get("action") not in DECISION:
            continue
        qid = e["questionId"]
        later = [x for x in evs[i + 1:] if x["questionId"] == qid]
        s = STORE.case_summary(qid)
        first = sorted(STORE.case_results(qid), key=lambda x: STORE.reports[x["reportId"]]["reportedAt"])[0]
        rows.append({
            "questionId": qid, "displayId": s["displayId"], "subject": s["subject"], "chapter": s["chapter"],
            "issue": s["issue"], "studentSaid": STORE.reports[first["reportId"]]["comment"],
            "reports": s["reports"], "aiVerdict": ai_verdict(qid),
            "decision": DECISION[e["action"]], "detail": e["detail"], "kind": e["kind"], "at": e["at"],
            "superseded": bool(later),
        })
    rows.reverse()                                    # newest first
    current = [r for r in rows if not r["superseded"]]
    count = lambda d: sum(1 for r in current if r["decision"] == d)
    # approving keeps or applies a fix; editing writes one. Either way the question is now fixed.
    fixed_q = {r["questionId"] for r in current if r["decision"] in ("approved", "edited")}
    resolved_reports = sum(r["reports"] for r in current)
    double_checked = sum(1 for r in current if r["detail"].startswith(("Auto-fix confirmed", "Auto-fix undone")))
    return {
        "stats": {"total": len(current), "approved": count("approved"), "rejected": count("rejected"),
                  "edited": count("edited")},
        "impact": {"questionsFixed": len(fixed_q), "reportsResolved": resolved_reports,
                   "autoFixesChecked": double_checked},
        "subjects": sorted({r["subject"] for r in rows if r["subject"]}),
        "rows": rows,
    }


def engine_policy() -> dict:
    """The engine's safety rules, read from the code that enforces them (shown read-only in Settings)."""
    sys.path.insert(0, str(ROOT))
    from engine import guards
    return {"floor": guards.FLOOR, "floorKey": guards.FLOOR_KEY, "gate": guards.GATE,
            "humanOnly": sorted(k for k, v in TAX["repairs"].items() if not v["auto"]),
            "autoAllowed": sorted(k for k, v in TAX["repairs"].items() if v["auto"])}
