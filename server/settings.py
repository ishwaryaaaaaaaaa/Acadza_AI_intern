"""Faculty preferences. Kept in their own file so "reset demo data" never wipes them.
Every key here changes real behaviour somewhere in the console; nothing is decorative."""
from __future__ import annotations

import json
import os
import re
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILE = Path(os.environ.get("CONSOLE_SETTINGS", ROOT / "server" / "settings.json"))

DEFAULTS = {
    "displayName": "Faculty",          # avatar, greeting, and the name on every audit entry
    "theme": "light",                  # light | auto | dark
    "notifyBellDot": True,             # red dot on the bell when cases wait for a decision
    "notifyToasts": True,              # confirmation toast after each decision
    "defaultSort": "priority",         # queue order: priority | reports | confidence | oldest
    "showAutoFixed": True,             # list engine auto-fixes in the queue for a one-click confirm
    "requireRejectNote": False,        # ask for a reason before a Reject can be saved
    "keyboardShortcuts": True,         # A / E / R / Enter / S on the review page
    # profile (My Profile page). Contact details only: sign-in is by password, not by email.
    "email": "",
    "department": "",
    "designation": "",
    "photo": "",                       # small data:image/... URL, resized in the browser before upload
}
ALLOWED = {
    "theme": {"light", "auto", "dark"},
    "defaultSort": {"priority", "reports", "confidence", "oldest"},
}
_lock = threading.Lock()


class SettingsError(Exception):
    pass


def load() -> dict:
    data = {}
    if FILE.exists():
        try:
            data = json.loads(FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {}
    return {**DEFAULTS, **{k: v for k, v in data.items() if k in DEFAULTS}}


def save(patch: dict) -> dict:
    cur = load()
    for k, v in patch.items():
        if k not in DEFAULTS:
            raise SettingsError(f"Unknown setting {k!r}.")
        if isinstance(DEFAULTS[k], bool) and not isinstance(v, bool):
            raise SettingsError(f"{k} must be true or false.")
        if k in ALLOWED and v not in ALLOWED[k]:
            raise SettingsError(f"{k} must be one of {sorted(ALLOWED[k])}.")
        if k == "email":
            v = str(v).strip()
            if v and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", v):
                raise SettingsError("That email address doesn't look right.")
        if k in ("department", "designation"):
            v = str(v).strip()
            if len(v) > 60:
                raise SettingsError(f"{k.title()} must be 60 characters or fewer.")
        if k == "photo":
            v = str(v)
            if v and (not re.match(r"^data:image/(png|jpeg|webp);base64,", v) or len(v) > 400_000):
                raise SettingsError("Photo must be a PNG, JPEG or WebP image under 300 KB.")
        if k == "displayName":
            v = str(v).strip()
            if not 1 <= len(v) <= 40:
                raise SettingsError("Display name must be 1–40 characters.")
        cur[k] = v
    with _lock:
        FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(cur, indent=1), encoding="utf-8")
        tmp.replace(FILE)
    return cur


def actor() -> str:
    return load()["displayName"]
