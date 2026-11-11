"""Orchestrates the whole report -> decision flow.

group by question -> screen comments -> LLM triage (1 call / question) -> blind key audit only
when a report is about the answer -> deterministic guards decide the route -> student replies.
"""
from __future__ import annotations

import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path

from . import judge, replies
from .guards import CUE_LINT, GATE, answer_related, decide, key_audit
from .lint import lint_question
from .screen import group_reports, screen_comment
from .textify import parse

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data_raw" / "acadza-report-fix" / "data"


def load():
    Q = {q["_id"]: q for q in json.loads((DATA / "questions.json").read_text(encoding="utf-8"))}
    R = json.loads((DATA / "reports.json").read_text(encoding="utf-8"))
    return Q, R


def _safe(fn, *a, default=None, label=""):
    try:
        return fn(*a)
    except Exception as e:      # a failed model call must degrade to "human decides", never crash or guess
        print(f"   ! {label} failed: {str(e)[:120]}", file=sys.stderr)
        return default


def out_edit(e: dict | None) -> dict | None:
    """Internal edits carry JSON-encoded answers (exact apply); results.json shows plain values."""
    if not e:
        return None
    if e["field"] == "answer":
        return {"field": "answer", "find": json.loads(e["find"]), "replace": json.loads(e["replace"])}
    return {k: e[k] for k in ("field", "find", "replace")}


def run(report_ids=None, workers=3, verbose=True):
    t0 = time.time()
    Q, R = load()
    if report_ids:
        R = [r for r in R if r["reportId"] in report_ids]
    groups = group_reports(R)
    usage = {"triage": [0, 0], "strong": [0, 0], "solve": [0, 0], "escalated_questions": 0}

    def work(item):
        qid, reps = item
        q = Q[qid]
        screens = {r["reportId"]: screen_comment(r) for r in reps}
        tri = _safe(judge.triage_group, q, reps, default={"items": {}, "usage": (0, 0), "cached": False}, label=f"triage {qid[:8]}")
        items = tri["items"]
        findings = lint_question(q)
        need = any(answer_related(screens[r["reportId"]], items.get(r["reportId"], {})) and not screens[r["reportId"]].injection
                   for r in reps) or any(f.code.startswith("ANS_") for f in findings)
        # an injection-only group still gets one audit so the "no_error" is backed by evidence
        need = need or any(screens[r["reportId"]].injection for r in reps)
        sa = sb = None
        if need:
            sa = _safe(judge.solve_blind, q, "a", label=f"solveA {qid[:8]}")
            sb = _safe(judge.solve_blind, q, "b", label=f"solveB {qid[:8]}")
        audit = key_audit(q, sa, sb) if need else None
        # --- the token gate decides where the expensive model is worth its tokens
        why = []
        for r in reps:
            it, sc = items.get(r["reportId"], {}), screens[r["reportId"]]
            if sc.injection:
                continue
            if not it:
                why.append("no triage output")
            for k in ("_p_verdict", "_p_repair"):
                if it.get(k) is not None and it[k] < GATE:
                    why.append(f"{r['reportId']} {k[3:]} prob {it[k]:.2f}")
            if it.get("verdict") != "defect" and any(c in sc.cues and any(f.code in codes for f in findings)
                                                      for c, codes in CUE_LINT.items()):
                why.append(f"{r['reportId']} triage says {it.get('verdict')} but the linter found a matching defect")
            if audit and audit["status"] == "confirmed" and it.get("repair") == "answer_key" \
                    and not any(f.code.startswith("ANS_") for f in findings):
                why.append(f"{r['reportId']} triage wanted a key change but solves confirm the key")
            if "chapter" in sc.cues:
                why.append(f"{r['reportId']} chapter/syllabus claim needs the strong model")
        if why:
            note = "none run" if not audit else (f"{audit['status']}; solver answers "
                                                 f"{[(x or {}).get('answer') for x in audit['solves']]}; stored key {audit['stored']}")
            st = _safe(judge.triage_group, q, reps, True, note, label=f"strong {qid[:8]}")
            if st:
                items = {**items, **{k: v for k, v in st["items"].items() if v.get("verdict")}}
                tri = {**tri, "strong_usage": st["usage"], "escalated": why}
        decs = []
        for r in reps:
            decs.append(decide(q, r, screens[r["reportId"]], items.get(r["reportId"]), audit))
        # same question, same edit -> one proposal, the others point at it
        first = {}
        for d in decs:
            sig = json.dumps([d.edit, d.extra_edits], sort_keys=True) if d.edit else None
            if sig and sig in first:
                d.duplicate_of = first[sig]
            elif sig:
                first[sig] = d.reportId
        comments = {r["reportId"]: r["comment"] for r in reps}
        qtext, stext = parse(q[q["questionType"]]["question"]).llm_text, parse(q[q["questionType"]]["solution"]).llm_text
        info = {}
        for d in decs:
            inj = screens[d.reportId].injection
            f = replies.facts(d, q, audit, qtext, stext)
            st = replies.status(d, inj)
            info[d.reportId] = (inj, st, f, replies.grounding(f, qtext, stext, d, st), replies.final_key(q, d))
        ask = [d for d in decs if info[d.reportId][1] in replies.MODEL_STATUSES]
        reps_out = (_safe(judge.write_replies, q, [
            {"reportId": d.reportId, "status": info[d.reportId][1], "language": replies.language(comments[d.reportId]),
             "facts": info[d.reportId][2]} for d in ask], default={}, label=f"reply {qid[:8]}") or {}) if ask else {}
        final = {}
        for d in decs:
            inj, st, _f, ground, key = info[d.reportId]
            if st not in replies.MODEL_STATUSES:
                final[d.reportId] = (replies.template(d, comments[d.reportId], inj), "template", "",
                                     ["status uses a fixed template"])
                continue
            draft = reps_out.get(d.reportId, "")
            problems = replies.check_reply(d, comments[d.reportId], draft, inj, ground, key)
            if problems:
                final[d.reportId] = (replies.template(d, comments[d.reportId], inj), "template", draft, problems)
            else:
                final[d.reportId] = (draft.strip(), "model", draft, [])
        reps_out = final
        for d in decs:
            d.guards.insert(0, ("escalation", "note", "; ".join(why) if why else "cheap pass was confident; no second opinion needed"))
        return qid, tri, audit, decs, reps_out, sa, sb

    with ThreadPoolExecutor(workers) as ex:
        done = list(ex.map(work, list(groups.items())))

    results, full = [], []
    for qid, tri, audit, decs, reps_out, sa, sb in done:
        usage["triage"][0] += tri["usage"][0]
        usage["triage"][1] += tri["usage"][1]
        if tri.get("strong_usage"):
            usage["strong"][0] += tri["strong_usage"][0]
            usage["strong"][1] += tri["strong_usage"][1]
            usage["escalated_questions"] += 1
        for s in (sa, sb):
            if s:
                usage["solve"][0] += s["_usage"][0]
                usage["solve"][1] += s["_usage"][1]
        for d in decs:
            reply, src, draft, problems = reps_out[d.reportId]
            results.append({"reportId": d.reportId, "questionId": d.questionId, "verdict": d.verdict, "repair": d.repair,
                            "edit": out_edit(d.edit), "route": d.route, "confidence": round(d.confidence, 2),
                            "evidence": d.evidence, "student_reply": reply})
            full.append({**asdict(d), "student_reply": reply, "reply_source": src, "reply_draft": draft,
                         "reply_problems": problems, "audit": audit and {k: v for k, v in audit.items() if k != "solves"},
                         "solves": audit["solves"] if audit else None, "triage_raw": tri["items"].get(d.reportId),
                         "escalated": tri.get("escalated")})
    results.sort(key=lambda r: r["reportId"])
    full.sort(key=lambda r: r["reportId"])
    if verbose:
        print(f"done in {time.time()-t0:.0f}s, {len(results)} reports, {len(groups)} questions")
    return results, full, usage
