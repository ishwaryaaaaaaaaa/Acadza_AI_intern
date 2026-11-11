"""Thin, dependency-free LLM clients (Cohere v2 chat, Gemini generateContent) with
a disk cache, per-call token logging and token-probability gating.

Keys are read from the environment or a git-ignored .env file. They are sent only
in request headers, never in URLs, logs or the cache.

Honest note on "entropy": Cohere returns only the log-probability of the token it
CHOSE at each position (no top-k alternatives), so true Shannon entropy cannot be
computed. We gate on the probability of the decision tokens instead (a surprisal
signal). Gemini returns no logprobs on the usable models, so it is used as an
independent second opinion, not as a gate.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "cache"
LOGS = ROOT / "logs"


def load_env() -> None:
    f = ROOT / ".env"
    if f.exists():
        for line in f.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


load_env()


LATEX_CMDS = ("frac|times|theta|tau|text|rightarrow|Rightarrow|rho|nu|nabla|neq|beta|bar|vec|begin|end|right|"
              "left|bf|rm|approx|ne|le|ge|cdot|sqrt|pi|mu|lambda|omega|Delta|sigma|alpha|epsilon|phi|angle|"
              "circ|infty|therefore|because|mathrm|overline|hat|tilde|dot")


class LLMError(Exception):
    pass


@dataclass
class Reply:
    text: str
    provider: str
    model: str
    in_tokens: int = 0
    out_tokens: int = 0
    logprobs: list = field(default_factory=list)   # [(token_text, logprob)]
    cached: bool = False

    def json(self):
        t = self.text.strip()
        t = re.sub(r"^```(?:json)?|```$", "", t, flags=re.M).strip()
        a, b = t.find("{"), t.rfind("}")
        if a < 0 or b <= a:
            raise LLMError(f"model did not return JSON: {t[:120]!r}")
        body = t[a:b + 1]
        # Models often write LaTeX with a single backslash (\frac, \times, \theta ...). JSON would read
        # \f \t \b as control characters and silently corrupt the text, so escape known commands first.
        body = re.sub(r"(?<!\\)\\(?=(?:%s)(?![A-Za-z]))" % LATEX_CMDS, r"\\\\", body)
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            # any remaining lone backslash that is not a valid JSON escape
            return json.loads(re.sub(r'(?<!\\)\\(?!["\\/bfnrtu])', r"\\\\", body))


def _post(url: str, headers: dict, body: dict, retries: int = 4) -> dict:
    data = json.dumps(body).encode("utf-8")
    for i in range(retries):
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json", **headers})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            msg = e.read().decode("utf-8", "replace")[:300]
            if e.code == 429 and "exceeded your current quota" in msg:
                raise LLMError(f"HTTP 429 quota: {msg[:120]}")      # a daily cap will not clear in seconds
            if e.code in (429, 500, 502, 503) and i < retries - 1:
                time.sleep(3 * (2 ** i))
                continue
            raise LLMError(f"HTTP {e.code}: {msg}")
        except urllib.error.URLError as e:
            if i < retries - 1:
                time.sleep(2 * (i + 1))
                continue
            raise LLMError(f"network: {e.reason}")
    raise LLMError("unreachable")


def _key(provider: str, model: str, system: str, user: str, extra: dict) -> str:
    h = hashlib.sha256(json.dumps([provider, model, system, user, extra], sort_keys=True).encode()).hexdigest()
    return h[:24]


def _log(rec: dict) -> None:
    LOGS.mkdir(exist_ok=True)
    with open(LOGS / "llm_calls.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")


def parse_cohere_logprobs(raw) -> list:
    """Defensive: accept either [{token, logprob}] or [{text, logprobs:[...]}]."""
    out = []
    for e in raw or []:
        if "token" in e and "logprob" in e:
            out.append((e["token"], e["logprob"]))
        elif "text" in e and "logprobs" in e:
            lps = e["logprobs"] or [0.0]
            out.append((e["text"], min(lps)))
    return out


_lock = threading.Lock()
_last_call = [0.0]
MIN_GAP = 3.2        # Cohere trial keys allow 20 calls / minute


def _throttle() -> None:
    with _lock:
        wait = _last_call[0] + MIN_GAP - time.time()
        if wait > 0:
            time.sleep(wait)
        _last_call[0] = time.time()


def cohere_chat(model: str, system: str, user: str, *, logprobs: bool = True, max_tokens: int = 1500,
                temperature: float = 0.0, thinking: bool = False, schema: dict | None = None, tag: str = "") -> Reply:
    extra = {"lp": logprobs, "mt": max_tokens, "t": temperature, "th": thinking, "sc": schema}
    ck = _key("cohere", model, system, user, extra)
    cf = CACHE / f"{ck}.json"
    if cf.exists():
        d = json.loads(cf.read_text(encoding="utf-8"))
        return Reply(**{**d, "logprobs": [tuple(x) for x in d["logprobs"]], "cached": True})
    key = os.environ.get("COHERE_API_KEY")
    if not key:
        raise LLMError("COHERE_API_KEY not set (put it in .env or the environment)")
    _throttle()
    body = {"model": model, "temperature": temperature, "max_tokens": max_tokens,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "response_format": {"type": "json_object"}}
    if schema:
        body["response_format"] = {"type": "json_object", "json_schema": schema}
    if not thinking:   # command-a-plus reasons by default and spends the budget before answering
        body["thinking"] = {"type": "disabled"}
    if logprobs:
        body["logprobs"] = True
    j = _post("https://api.cohere.com/v2/chat", {"Authorization": f"Bearer {key}"}, body)
    text = "".join(c.get("text", "") for c in j.get("message", {}).get("content", []))
    bu = (j.get("usage") or {}).get("billed_units") or {}
    r = Reply(text, "cohere", model, int(bu.get("input_tokens", 0)), int(bu.get("output_tokens", 0)),
              parse_cohere_logprobs(j.get("logprobs")))
    _save(cf, r, tag)
    return r


def gemini_chat(model: str, system: str, user: str, *, max_tokens: int = 1500, temperature: float = 0.0,
                tag: str = "") -> Reply:
    ck = _key("gemini", model, system, user, {"mt": max_tokens, "t": temperature})
    cf = CACHE / f"{ck}.json"
    if cf.exists():
        d = json.loads(cf.read_text(encoding="utf-8"))
        return Reply(**{**d, "logprobs": [], "cached": True})
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise LLMError("GEMINI_API_KEY not set (put it in .env or the environment)")
    body = {"systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens,
                                 "responseMimeType": "application/json"}}
    j = _post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
              {"x-goog-api-key": key}, body)
    try:
        text = "".join(p.get("text", "") for p in j["candidates"][0]["content"]["parts"])
    except (KeyError, IndexError):
        raise LLMError(f"gemini returned no candidate: {str(j)[:200]}")
    um = j.get("usageMetadata") or {}
    r = Reply(text, "gemini", model, int(um.get("promptTokenCount", 0)), int(um.get("candidatesTokenCount", 0)))
    _save(cf, r, tag)
    return r


def _save(cf: Path, r: Reply, tag: str) -> None:
    CACHE.mkdir(exist_ok=True)
    d = {"text": r.text, "provider": r.provider, "model": r.model, "in_tokens": r.in_tokens,
         "out_tokens": r.out_tokens, "logprobs": [list(x) for x in r.logprobs]}
    cf.write_text(json.dumps(d), encoding="utf-8")
    _log({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "tag": tag, "provider": r.provider, "model": r.model,
          "in": r.in_tokens, "out": r.out_tokens})


# ------------------------------------------------------------------ token-probability gating
def value_prob(logprobs: list, text: str, key: str) -> float | None:
    """Probability (0-1) of the weakest token inside the JSON string value of `key`.

    Returns None when logprobs are unavailable or the key is not found (caller must then
    treat the field as UNGATED and escalate, never as confident)."""
    if not logprobs:
        return None
    m = re.search(r'"%s"\s*:\s*"?([^",}\]\n]*)' % re.escape(key), text)
    if not m or not m.group(1):
        return None
    lo, hi = m.start(1), m.end(1)
    pos, worst = 0, 0.0
    seen = False
    for tok, lp in logprobs:
        a, b = pos, pos + len(tok)
        pos = b
        if b > lo and a < hi:
            seen = True
            worst = min(worst, lp)
    return math.exp(worst) if seen else None


def mean_surprisal(logprobs: list) -> float | None:
    if not logprobs:
        return None
    return -sum(lp for _, lp in logprobs) / len(logprobs)
