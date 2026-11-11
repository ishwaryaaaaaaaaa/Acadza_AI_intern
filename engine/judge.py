"""LLM stages: triage (Cohere, with token-probability gating), blind solve (Cohere + Gemini),
student replies (cheap model). Guards live in guards.py and may only downgrade routes."""
from __future__ import annotations

import json
import re
from pathlib import Path

from . import llm
from .lint import lint_question
from .prompts import (ESCALATION_NOTE, REPLY_SYSTEM, REPLY_USER, SOLVE_SYSTEM, SOLVE_USER, TRIAGE_SYSTEM, TRIAGE_USER)
from .screen import fixed_since, screen_comment
from .textify import parse

TAXONOMY = json.loads((Path(__file__).resolve().parent.parent / "data_raw" / "acadza-report-fix" / "data" / "taxonomy.json")
                      .read_text(encoding="utf-8"))

MODELS = {
    "triage": ("cohere", "command-r-plus-08-2024"),            # cheap pass, has logprobs => gate
    "triage_strong": ("cohere", "command-a-plus-05-2026"),     # reasoning pass, only when the gate says "unsure"
    "solve_a": ("cohere", "command-a-plus-05-2026"),
    "solve_b": ("gemini", "gemini-3.5-flash"),
    "solve_b2": ("gemini", "gemini-3.5-flash-lite"),     # fallback when the free daily quota of the stronger model is gone
    "reply": ("cohere", "command-r-plus-08-2024"),    # r7b echoed comments and claimed fixes; see PROMPTS.md
}


def taxonomy_text() -> str:
    v = "\n".join(f'  {k}: {d}' for k, d in TAXONOMY["verdicts"].items())
    r = "\n".join(f'  {k} [{"/".join(d["fields"])}] {"AUTO-OK" if d["auto"] else "HUMAN-ONLY"}: {d["label"]}'
                  for k, d in TAXONOMY["repairs"].items())
    return f"VERDICTS:\n{v}\n\nREPAIRS [fields it may touch]:\n{r}"


def _body(q: dict) -> dict:
    return q[q["questionType"]]


def _triage_schema() -> dict:
    return {"type": "object", "required": ["reports"], "properties": {"reports": {"type": "array", "items": {
        "type": "object",
        "required": ["reportId", "evidence", "verdict", "repair", "edit", "confidence"],
        "properties": {
            "reportId": {"type": "string"},
            "evidence": {"type": "string"},
            "verdict": {"type": "string", "enum": list(TAXONOMY["verdicts"])},
            "repair": {"type": "string", "enum": ["none"] + list(TAXONOMY["repairs"])},
            "edit": {"type": "object", "required": ["field", "find", "replace"], "properties": {
                "field": {"type": "string", "enum": ["none", "question", "solution", "answer", "questionType"]},
                "find": {"type": "string"}, "replace": {"type": "string"}}},
            "confidence": {"type": "number"}}}}}}


def _call(role: str, system: str, user: str, *, logprobs=False, max_tokens=1500, schema=None, tag=""):
    prov, model = MODELS[role]
    if prov == "cohere":
        return llm.cohere_chat(model, system, user, logprobs=logprobs, max_tokens=max_tokens,
                               thinking=(role in ("solve_a", "triage_strong")), schema=schema, tag=tag)
    return llm.gemini_chat(model, system, user, max_tokens=max_tokens, tag=tag)


def triage_group(q: dict, reports: list[dict], strong: bool = False, audit_note: str = "") -> dict:
    """One call for ALL reports on a question (the question text is paid for once)."""
    b = _body(q)
    qd, sd = parse(b["question"]), parse(b["solution"])
    screens = {r["reportId"]: screen_comment(r) for r in reports}
    findings = lint_question(q)
    hist = q.get("errorHistory") or []
    lines = []
    for r in reports:
        s = screens[r["reportId"]]
        fx = fixed_since(q, r["reportedAt"])
        lines.append(f'- reportId {r["reportId"]} (source {r["source"]}, filed {r["reportedAt"]}): '
                     f'"{s.sanitized}"' + (f"   [screen: {', '.join(n for n in ('gibberish','vague') if getattr(s, n))}]"
                                           if (s.gibberish or s.vague) else "")
                     + (f"   [hints: {', '.join(s.cues)}]" if s.cues else "")
                     + (f"   [faculty edited this question AFTER this report: {fx[0]['note']}]" if fx else ""))
    system = TRIAGE_SYSTEM.replace("{TAXONOMY}", taxonomy_text())
    user = TRIAGE_USER.format(
        qid=q["_id"], qtype=q["questionType"], subject=q.get("subject"), chapter=q.get("chapter"),
        question=qd.llm_text.strip(), answer=json.dumps(b.get("answer")), solution=sd.llm_text.strip() or "(empty)",
        lint="\n".join(f"- {f.code} in {f.field}: {f.detail}" for f in findings) or "- none",
        history=json.dumps(hist) if hist else "none", reports="\n".join(lines))
    if strong:
        user += "\n\n" + ESCALATION_NOTE.format(audit=audit_note or "not run")
        rep = _call("triage_strong", system, user, logprobs=False, max_tokens=7000, tag=f"triageS:{q['_id'][:8]}")
    else:
        rep = _call("triage", system, user, logprobs=True, max_tokens=900 + 350 * len(reports),
                    schema=_triage_schema(), tag=f"triage:{q['_id'][:8]}")
    data = rep.json()
    out = {}
    for item in data.get("reports", []):
        rid = item.get("reportId")
        if not rid:
            continue
        # per-report decision probabilities (None => ungated, the pipeline must escalate)
        seg = _segment(rep.text, rid)
        item["_p_verdict"] = llm.value_prob(rep.logprobs, rep.text, "verdict") if len(reports) == 1 else _seg_prob(rep, seg, "verdict")
        item["_p_repair"] = llm.value_prob(rep.logprobs, rep.text, "repair") if len(reports) == 1 else _seg_prob(rep, seg, "repair")
        if item.get("repair") in (None, "none"):
            item["repair"] = None
        e = item.get("edit") or {}
        item["edit"] = None if e.get("field") in (None, "none", "") else {k: e.get(k, "") for k in ("field", "find", "replace")}
        out[rid] = item
    return {"items": out, "usage": (rep.in_tokens, rep.out_tokens), "cached": rep.cached, "raw": rep.text, "strong": strong}


def _segment(text: str, rid: str):
    i = text.find(f'"reportId": "{rid}"')
    if i < 0:
        i = text.find(rid)
    if i < 0:
        return None
    j = text.find('"reportId"', i + 10)
    return (i, j if j > 0 else len(text))


def _seg_prob(rep, seg, key):
    if not seg or not rep.logprobs:
        return None
    a, b = seg
    pos, toks, first = 0, [], None
    for t, lp in rep.logprobs:
        s0, e0 = pos, pos + len(t)
        pos = e0
        if e0 > a and s0 < b:
            if first is None:
                first = s0
            toks.append((t, lp))
    return llm.value_prob(toks, rep.text[first:b], key) if toks else None


def solve_blind(q: dict, which: str = "a") -> dict:
    """Independent solve WITHOUT key, solution or student comment. Cached per question."""
    b = _body(q)
    qd = parse(b["question"])
    user = SOLVE_USER.format(qtype=q["questionType"], question=qd.llm_text.strip())
    role = "solve_" + which
    try:
        rep = _call(role, SOLVE_SYSTEM, user, max_tokens=6000 if which == "a" else 1500, tag=f"solve{which}:{q['_id'][:8]}")
    except llm.LLMError as e:
        if which != "b" or "429" not in str(e):
            raise
        role = "solve_b2"
        rep = _call(role, SOLVE_SYSTEM, user, max_tokens=1500, tag=f"solveb2:{q['_id'][:8]}")
    d = rep.json()
    d["_usage"] = (rep.in_tokens, rep.out_tokens)
    d["_model"] = rep.model
    return d


def write_replies(q: dict, items: list[dict]) -> dict:
    """items: [{reportId, status, language, facts}] -> {reportId: reply}. The comment itself is NOT sent:
    the model cannot echo what it never sees, and an injected comment cannot reach the reply writer."""
    b = _body(q)
    short = re.sub(r"\s+", " ", parse(b["question"]).llm_text)[:400]
    txt = "\n".join(f'- reportId {i["reportId"]}\n  STATUS: {i["status"]}\n  LANGUAGE: {i["language"]}\n'
                    f'  FACTS: {i["facts"]}' for i in items)
    schema = {"type": "object", "required": ["replies"], "properties": {"replies": {"type": "array", "items": {
        "type": "object", "required": ["reportId", "student_reply"],
        "properties": {"reportId": {"type": "string"}, "student_reply": {"type": "string"}}}}}}
    rep = _call("reply", REPLY_SYSTEM, REPLY_USER.format(question=short, items=txt), max_tokens=300 * len(items) + 300,
                schema=schema, tag=f"reply:{q['_id'][:8]}")
    return {x["reportId"]: x["student_reply"] for x in rep.json().get("replies", []) if "reportId" in x}
