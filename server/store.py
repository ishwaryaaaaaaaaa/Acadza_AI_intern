"""Console state: cases (one per reported question) and an append-only audit log.

Everything the console shows is derived from three real sources and nothing else:
  data_raw/.../questions.json + reports.json   (Acadza's data)
  results_full.json                            (what the engine decided)
  server/state.json                            (what faculty did since; created on first run)
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data_raw" / "acadza-report-fix" / "data"
RESULTS = ROOT / "results_full.json"
STATE = Path(os.environ.get("CONSOLE_STATE", ROOT / "server" / "state.json"))

# Urgency = harm to students. A wrong key silently costs marks to everyone who attempts the question,
# so it outranks anything that is merely confusing, which outranks anything cosmetic.
TIER = {
    "answer_key": "critical", "type_mismatch": "critical", "unsound": "critical", "wrong_question": "critical",
    "option_repair": "high", "identical_options": "high", "diagram": "high", "stem_data": "high",
    "solution_fix": "high", "solution_missing": "high", "notation": "high",
    "wrong_chapter": "medium", "syllabus": "medium", "spelling": "medium", "markup_leak": "medium",
    "exam_reference": "medium", "noise": "medium", "answer_form": "medium",
}
TIER_RANK = {"critical": 0, "high": 1, "medium": 2}

ISSUE_LABEL = {
    "answer_key": "Answer key wrong", "type_mismatch": "Wrong question type", "unsound": "No valid option",
    "wrong_question": "Solution doesn't match", "option_repair": "Missing / blank option",
    "identical_options": "Identical options", "diagram": "Figure missing", "stem_data": "Missing data in question",
    "solution_fix": "Incorrect solution", "solution_missing": "Solution missing", "notation": "Symbol lost",
    "wrong_chapter": "Wrong chapter", "syllabus": "Out of syllabus", "spelling": "Spelling mistake",
    "markup_leak": "Raw code in question", "exam_reference": "Exam tag in text", "noise": "Stray text",
    "answer_form": "Unit not stated",
}

OPEN = {"needs_decision", "auto_applied"}          # a teacher still has to look
RESOLVED = {"verified_no_change", "approved", "edited", "rejected", "confirmed", "reverted"}

_lock = threading.Lock()


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _load(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


class Store:
    def __init__(self):
        self.questions = {q["_id"]: q for q in _load(DATA / "questions.json")}
        self.reports = {r["reportId"]: r for r in _load(DATA / "reports.json")}
        self.results = {x["reportId"]: x for x in _load(RESULTS)}
        self.engine_run_at = datetime.fromtimestamp(RESULTS.stat().st_mtime, timezone.utc).isoformat(timespec="seconds")
        self.state = _load(STATE) if STATE.exists() else self._seed()

    # ---------------------------------------------------------------- seeding from the engine's output
    def _seed(self) -> dict:
        by_q: dict[str, list] = {}
        for rid in sorted(self.results):
            by_q.setdefault(self.results[rid]["questionId"], []).append(rid)
        cases, events = {}, []
        for qid, rids in by_q.items():
            rs = [self.results[r] for r in rids]
            routes = {x["route"] for x in rs}
            status = "needs_decision" if "faculty_review" in routes else ("auto_applied" if "auto_apply" in routes
                                                                           else "verified_no_change")
            cases[qid] = {"status": status, "updatedAt": self.engine_run_at}
            events.append(self._engine_event(qid, status))
        state = {"cases": cases, "events": events, "seededAt": now()}
        self._save(state)
        return state

    def _engine_event(self, qid: str, status: str) -> dict:
        c = self.case_summary(qid, status_override=status)
        if status == "auto_applied":
            title, detail, kind = f"{c['displayId']} fixed", self._change_text(qid), "fixed"
        elif status == "needs_decision":
            title, detail, kind = f"{c['displayId']} under review", "AI analysis completed", "review"
        else:
            title, detail, kind = f"{c['displayId']} verified", "No issue found", "verified"
        return {"at": self.engine_run_at, "actor": "AI engine", "questionId": qid, "kind": kind,
                "title": title, "detail": detail}

    def _save(self, state=None) -> None:
        STATE.parent.mkdir(parents=True, exist_ok=True)
        tmp = STATE.with_suffix(".tmp")
        tmp.write_text(json.dumps(state or self.state, indent=1), encoding="utf-8")
        tmp.replace(STATE)

    def reset(self) -> None:
        with _lock:
            if STATE.exists():
                STATE.unlink()
            self.state = self._seed()

    # ---------------------------------------------------------------- derived views
    def case_results(self, qid: str) -> list[dict]:
        return [x for x in self.results.values() if x["questionId"] == qid]

    def primary(self, qid: str) -> dict:
        """The decision that defines the case: the most harmful defect, then the most confident."""
        rs = self.case_results(qid)
        return sorted(rs, key=lambda x: (x["verdict"] != "defect", TIER_RANK.get(TIER.get(x["repair"] or "", ""), 9),
                                         -x["confidence"]))[0]

    def _change_text(self, qid: str) -> str:
        p = self.primary(qid)
        e = p.get("edit")
        if p.get("repair") in ("answer_key", "type_mismatch") and e:
            if e["field"] == "questionType":
                a = next((x for x in p.get("extra_edits") or [] if x["field"] == "answer"), None)
                return f"Type {e['find']} → {e['replace']}" + (f", key → {json.loads(a['replace'])}" if a else "")
            f, r = json.loads(e["find"]), json.loads(e["replace"])
            fmt = lambda v: ", ".join(x for x in v if x) if isinstance(v, list) else str(v)
            return f"Answer key updated ({fmt(f)} → {fmt(r)})"
        return f"{ISSUE_LABEL.get(p.get('repair'), 'Fix')} corrected"

    def case_summary(self, qid: str, status_override: str | None = None) -> dict:
        q = self.questions[qid]
        rs = self.case_results(qid)
        p = self.primary(qid)
        repair = p.get("repair")
        tier = TIER.get(repair or "")
        status = status_override or self.state["cases"][qid]["status"]
        return {
            "questionId": qid,
            "displayId": qid[:8].upper(),
            "subject": q.get("subject"),
            "chapter": q.get("chapter"),
            "issue": ISSUE_LABEL.get(repair, {"no_error": "No error", "display_issue": "Display issue",
                                             "app_issue": "App issue", "language_mode": "Language request",
                                             "already_fixed": "Already fixed", "not_actionable": "Unclear report"
                                             }.get(p["verdict"], p["verdict"])),
            "repair": repair,
            "verdict": p["verdict"],
            "tier": tier,
            "reports": len(rs),
            "reportIds": sorted(x["reportId"] for x in rs),
            "confidence": round(max(x["confidence"] for x in rs if x["verdict"] == p["verdict"]), 2),
            "status": status,
            "needsDecision": status == "needs_decision",
            "firstReportedAt": min(self.reports[x["reportId"]]["reportedAt"] for x in rs),
        }

    def queue(self, tier: str | None = None, sort: str | None = None) -> list[dict]:
        from .settings import load as load_settings
        prefs = load_settings()
        sort = sort or prefs["defaultSort"]
        statuses = OPEN if prefs["showAutoFixed"] else {"needs_decision"}
        rows = [self.case_summary(q) for q, c in self.state["cases"].items() if c["status"] in statuses]
        rows = [r for r in rows if r["tier"]]          # open cases are always defects, so always tiered
        if tier in TIER_RANK:
            rows = [r for r in rows if r["tier"] == tier]
        keys = {
            "priority": lambda r: (TIER_RANK[r["tier"]], not r["needsDecision"], -r["reports"], -r["confidence"]),
            "reports": lambda r: (-r["reports"], TIER_RANK[r["tier"]], -r["confidence"]),
            "confidence": lambda r: (-r["confidence"], TIER_RANK[r["tier"]]),
            "oldest": lambda r: (r["firstReportedAt"], TIER_RANK[r["tier"]]),
        }
        return sorted(rows, key=keys.get(sort, keys["priority"]))

    def dashboard(self) -> dict:
        open_rows = self.queue()
        by_tier = {t: sum(1 for r in open_rows if r["tier"] == t) for t in TIER_RANK}
        total = len(self.state["cases"])
        resolved_cases = [c for c in self.state["cases"].values() if c["status"] in RESOLVED]
        week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat(timespec="seconds")
        return {
            "counts": by_tier,
            "resolved": len(resolved_cases),
            "resolvedThisWeek": sum(1 for c in resolved_cases if c["updatedAt"] >= week_ago),
            "underReview": len(open_rows),
            "needsDecision": sum(1 for r in open_rows if r["needsDecision"]),
            "totalReported": total,
            "totalReports": len(self.reports),
            "progress": round(100 * len(resolved_cases) / total) if total else 0,
            "engineRunAt": self.engine_run_at,
            "recent": self.activity(limit=3),
        }

    def activity(self, limit: int | None = None) -> list[dict]:
        rank = {"fixed": 0, "review": 1, "verified": 2}
        ev = sorted(self.state["events"], key=lambda e: (e["at"], -rank.get(e["kind"], 3)), reverse=True)
        # engine events share one timestamp; within it show fixes first, then reviews, then verifications
        ev = sorted(ev, key=lambda e: (e["at"], -rank.get(e["kind"], 3) if e["actor"] == "AI engine" else 9),
                    reverse=True)
        return ev[:limit] if limit else ev


STORE = Store()
