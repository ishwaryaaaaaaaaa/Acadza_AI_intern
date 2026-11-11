"""Analytics. Live from real data; only FACULTY decisions count as "resolved".

- Reported / issue types / subjects come from the reports themselves (they exist before anyone acts).
- Resolved, resolution rate, the resolved line and the agreement insight move only when a teacher
  approves, edits or rejects. The AI's own "no change needed" closures are reported separately.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone

from .review import DECISION, ai_verdict
from .store import OPEN, STORE

NON_DEFECT = {"no_error": "Not a question error", "display_issue": "Not a question error",
              "app_issue": "Not a question error", "language_mode": "Not a question error",
              "not_actionable": "Unclear report", "already_fixed": "Already fixed"}


# Issue families a teacher thinks in. Fixed order = fixed colour per family (colour follows the entity).
FAMILY = [
    ("Wrong answer key / type", {"answer_key", "type_mismatch", "unsound"}),
    ("Missing or broken content", {"option_repair", "identical_options", "diagram", "stem_data", "solution_missing"}),
    ("Wrong solution", {"solution_fix", "wrong_question", "notation"}),
    ("Text & formatting", {"spelling", "markup_leak", "exam_reference", "noise", "answer_form"}),
    ("Chapter / syllabus", {"wrong_chapter", "syllabus"}),
]


def family(repair: str | None) -> str:
    return next((name for name, reps in FAMILY if repair in reps), "Other")


def _dt(iso: str) -> datetime:
    return datetime.fromisoformat(iso.replace("Z", "+00:00"))


def faculty_decisions() -> dict:
    """Latest standing decision per question: {qid: {decision, at}} (a later reopen cancels it)."""
    out = {}
    for e in STORE.state["events"]:
        if e.get("actor") != "Faculty":
            continue
        if e.get("action") in DECISION:
            out[e["questionId"]] = {"decision": DECISION[e["action"]], "at": e["at"], "action": e["action"]}
        elif e.get("action") == "reopen":
            out.pop(e["questionId"], None)
    return out


def analytics(range_key: str = "7d") -> dict:
    now = datetime.now(timezone.utc)
    days = {"7d": 7, "30d": 30}.get(range_key)
    first_report = min(_dt(r["reportedAt"]) for r in STORE.reports.values())
    start = (now - timedelta(days=days - 1)) if days else first_report
    start_day = start.date()

    # questions whose FIRST report falls inside the window
    first_at = {}
    for r in STORE.reports.values():
        t = _dt(r["reportedAt"])
        if r["questionId"] not in first_at or t < first_at[r["questionId"]]:
            first_at[r["questionId"]] = t
    in_range = {q for q, t in first_at.items() if t.date() >= start_day}

    decisions = faculty_decisions()
    resolved = {q: d for q, d in decisions.items() if q in in_range}
    open_q = {q for q in in_range if STORE.state["cases"][q]["status"] in OPEN}
    ai_closed = {q for q in in_range if STORE.state["cases"][q]["status"] == "verified_no_change"}
    total = len(in_range)

    # ---- progress: cumulative per day
    n_days = (now.date() - start_day).days + 1
    series = []
    for i in range(n_days):
        day = start_day + timedelta(days=i)
        series.append({
            "date": day.isoformat(),
            "reported": sum(1 for q in in_range if first_at[q].date() <= day),
            "resolved": sum(1 for d in resolved.values() if _dt(d["at"]).date() <= day),
        })

    # ---- issue types: real defects only (the AI's classification; a faculty rejection removes it)
    types, not_defect, rejected = Counter(), 0, 0
    for q in in_range:
        p = STORE.primary(q)
        if p["verdict"] != "defect":
            not_defect += 1
        elif resolved.get(q, {}).get("decision") == "rejected":
            rejected += 1
        else:
            types[family(p.get("repair"))] += 1
    issue_types = [{"label": name, "count": types[name], "slot": i} for i, (name, _) in enumerate(FAMILY)]
    if types.get("Other"):
        issue_types.append({"label": "Other", "count": types["Other"], "slot": len(FAMILY)})

    # ---- subjects
    subj = Counter(STORE.questions[q].get("subject") or "Other" for q in in_range)
    reports_by_subject = Counter(STORE.questions[r["questionId"]].get("subject") or "Other"
                                 for r in STORE.reports.values() if r["questionId"] in in_range)
    subjects = [{"label": s, "questions": n, "reports": reports_by_subject[s]} for s, n in subj.most_common()]

    # ---- insights (only from what is true right now)
    insights = []
    rate = round(100 * len(resolved) / total) if total else 0
    if resolved:
        insights.append(f"{rate}% of reported questions have been resolved by faculty.")
        agree = sum(1 for q, d in resolved.items()
                    if (ai_verdict(q)["label"] != "No Defect") == (d["decision"] in ("approved", "edited")))
        insights.append(f"Faculty agreed with the AI check on {agree} of {len(resolved)} decisions.")
    else:
        insights.append("No faculty decisions yet. Resolution numbers start moving with the first review.")
    defects = sorted([(t["label"], t["count"]) for t in issue_types if t["label"] != "Other" and t["count"]],
                     key=lambda x: -x[1])
    if defects:
        insights.append(f"{defects[0][0]} is the most common real issue ({defects[0][1]} question"
                        f"{'s' if defects[0][1] != 1 else ''}).")
    if subjects:
        s0 = max(subjects, key=lambda s: s["reports"])
        insights.append(f"{s0['label']} has the highest number of reports ({s0['reports']}).")
    if ai_closed:
        insights.append(f"{len(ai_closed)} reported questions were checked by the AI and needed no change.")

    return {
        "range": range_key, "from": start_day.isoformat(), "to": now.date().isoformat(),
        "cards": {"totalReported": total, "underReview": len(open_q), "resolved": len(resolved),
                  "resolutionRate": rate, "aiClosed": len(ai_closed)},
        "progress": series, "issueTypes": issue_types, "issueTotal": sum(types.values()),
        "notDefect": not_defect, "rejectedByFaculty": rejected,
        "subjects": subjects, "insights": insights[:4],
    }
