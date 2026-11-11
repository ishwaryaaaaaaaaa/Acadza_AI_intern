"""Faculty console API.   uvicorn server.app:app --port 8000"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from pydantic import BaseModel

from . import analytics as analytics_mod
from . import assistant
from . import settings as settings_mod
from . import review
from .store import STORE

app = FastAPI(title="Acadza Check API")

@app.get("/api/dashboard")
def dashboard():
    return STORE.dashboard()


@app.get("/api/queue")
def queue(tier: str | None = None, sort: str | None = None):
    return {"rows": STORE.queue(tier, sort), "counts": STORE.dashboard()["counts"]}


@app.get("/api/activity")
def activity(limit: int | None = None):
    return {"events": STORE.activity(limit)}


@app.get("/api/cases/{qid}")
def case(qid: str):
    if qid not in STORE.state["cases"]:
        raise HTTPException(404, "unknown question")
    return review.detail(qid)


class Action(BaseModel):
    action: str                      # approve | reject | edit | reopen
    changes: list[dict] | None = None
    note: str = ""


@app.post("/api/cases/{qid}/action")
def case_action(qid: str, body: Action):
    try:
        ev = review.act(qid, body.action, body.changes, body.note)
    except review.ActionError as e:
        raise HTTPException(400, str(e))
    return {"event": ev, "case": review.detail(qid)}


class Preview(BaseModel):
    changes: list[dict]


@app.post("/api/cases/{qid}/preview")
def case_preview(qid: str, body: Preview):
    """Validate a manual edit and return the result WITHOUT saving it."""
    if qid not in STORE.state["cases"]:
        raise HTTPException(404, "unknown question")
    try:
        patch = review.apply_changes(qid, body.changes)
    except review.ActionError as e:
        raise HTTPException(400, str(e))
    return {"patch": patch}


class Chat(BaseModel):
    messages: list[dict]


@app.post("/api/cases/{qid}/chat")
def case_chat(qid: str, body: Chat):
    try:
        return assistant.chat(qid, body.messages)
    except assistant.AssistantError as e:
        raise HTTPException(503, str(e))


@app.get("/api/reviews")
def my_reviews():
    return review.reviews()


@app.get("/api/analytics")
def analytics(range: str = "7d"):
    return analytics_mod.analytics(range)


@app.get("/api/settings")
def get_settings():
    return {"settings": settings_mod.load(), "engine": review.engine_policy()}


@app.put("/api/settings")
def put_settings(body: dict):
    try:
        return {"settings": settings_mod.save(body), "engine": review.engine_policy()}
    except settings_mod.SettingsError as e:
        raise HTTPException(400, str(e))


@app.get("/api/audit-log")
def audit_log():
    """Every event, engine and faculty, oldest first, for export."""
    return {"exportedAt": review.now(), "events": STORE.state["events"]}


@app.post("/api/admin/reset")
def reset():
    """Demo helper: forget every faculty action and start again from the engine's output."""
    STORE.reset()
    return {"ok": True}


# Serve the built console (console/dist) from the same origin in production.
DIST = Path(__file__).resolve().parent.parent / "console" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        f = DIST / path
        return FileResponse(f if path and f.is_file() else DIST / "index.html")
