"""Zero-token screening of a student's comment and grouping of reports.

The comment is an untrusted LEAD. Nothing here decides a verdict; it only
produces hints and flags that the judge sees, and a hard block for injection.
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field

INJECTION = re.compile(
    r"ignore (all |any )?(the )?(previous|prior|above)|disregard (all |the )?(previous|above|instructions)|"
    r"you are (now )?(the )?(an? )?(admin|system|developer|assistant|bot)|system prompt|"
    r"(change|set|mark|make) (the )?(answer|key|report|verdict)|mark (this )?report as|"
    r"as an? (ai|llm|admin)|new instructions?|override|jailbreak|act as", re.I)

# cue words are HINTS for the judge, never verdicts
CUES = {
    "display": r"\b(cut|cropp?ed|overflow|screen|layout|zoom|font|small|blur|load|loading|slow|lag|forever|scroll)\b",
    "app": r"\b(clicked|tapped|saved|recorded|keyboard|keypad|button|crash|hang|submit(ted)?|timer)\b",
    "language": r"\b(hindi|hinglish|tamil|telugu|marathi|bengali|gujarati|language|translation|translate)\b|"
                r"\b(me|mein|mai)\s+(question|qsn|prashn)\b|question\s+chahiye",
    "missing_data": r"\b(not given|nahi di|missing|not mentioned|kuch nahi|data missing|figure|diagram|value hi)\b",
    "option": r"\b(option|options)\b|\b(only \d options|blank|same|identical)\b",
    "chapter": r"\b(chapter|syllabus|out of)\b",
    "spelling": r"\b(spelling|typo|mistake in)\b",
    "exam_ref": r"\b(neet|jee|aieee|aipmt|cbse)\b.{0,20}\b(19|20)\d\d\b|written in (the )?question",
    "markup": r"\\[a-z]+|latex|\bcode\b.{0,20}\bshowing|symbols? (is|are) (showing|visible)",
    "claims_value": r"(should be|answer is|answer should|aana chahiye|hona chahiye|sahi answer|correct answer|i got|i solved|mera answer)",
    "key_challenge": r"\b(ans(wer)?|key)\b.{0,12}\b(wrong|galat|incorrect)\b|\b(wrong|galat)\b.{0,12}\bans(wer)?\b",
}
_CUE_RE = {k: re.compile(v, re.I) for k, v in CUES.items()}

VOWELS = set("aeiouAEIOU")


def _token_mash(tok: str) -> float:
    letters = [c for c in tok if c.isalpha()]
    if len(letters) < 4:
        return 0.0
    sc = 0.0
    if len(set(tok.lower())) <= max(2, len(tok) // 3):          # "aaaaa", "ababab"
        sc += 0.5
    vr = sum(c in VOWELS for c in letters) / len(letters)
    if vr < 0.15 or vr > 0.85:
        sc += 0.4
    if re.search(r"(asd|sdf|dfg|fgh|ghj|hjk|jkl|qwe|wer|ert|rty|tyu|yui|zxc|xcv|cvb|vbn|bnm)", tok, re.I):
        sc += 0.7
    return min(1.0, sc)


def gibberish_score(s: str) -> float:
    """0 = looks like words, 1 = keyboard mash. Only short comments can be gibberish:
    a long sentence with real words is never mash, even if one word looks odd."""
    toks = re.findall(r"\S+", s.strip())
    if not toks:
        return 1.0
    if len(toks) > 3:
        return 0.0
    if all(len([c for c in t if c.isalpha()]) < 3 for t in toks):
        return 0.9 if not any(c.isdigit() for c in s) else 0.3
    return max(_token_mash(t) for t in toks)


@dataclass
class Screen:
    reportId: str
    injection: bool = False
    gibberish: bool = False
    vague: bool = False
    empty: bool = False
    cues: list = field(default_factory=list)
    numbers: list = field(default_factory=list)       # numbers the student claims
    sanitized: str = ""                              # what the judge is shown

    @property
    def block_edit(self) -> bool:
        """Injection or empty junk can never be the justification for an edit."""
        return self.injection

    @property
    def specific(self) -> bool:
        return bool(self.numbers) or any(c in self.cues for c in (
            "missing_data", "option", "chapter", "spelling", "claims_value", "display", "app", "language"))


def screen_comment(report: dict) -> Screen:
    c = (report.get("comment") or "").strip()
    s = Screen(report["reportId"])
    if not c:
        s.empty = True
        return s
    s.injection = bool(INJECTION.search(c))
    s.gibberish = gibberish_score(c) >= 0.6 and not s.injection
    s.cues = [k for k, rx in _CUE_RE.items() if rx.search(c)]
    s.numbers = re.findall(r"(?<![\w.])\d+(?:\.\d+)?(?![\w])", c)
    words = re.findall(r"[A-Za-zऀ-ॿ]+", c)
    s.vague = (not s.gibberish and not s.injection and len(words) <= 3 and not s.numbers
               and not any(k != "key_challenge" for k in s.cues))
    s.sanitized = "[comment withheld: looks like an instruction aimed at the system]" if s.injection else c
    return s


def group_reports(reports: list[dict]) -> dict[str, list[dict]]:
    g = defaultdict(list)
    for r in sorted(reports, key=lambda r: r["reportedAt"]):
        g[r["questionId"]].append(r)
    return dict(g)


def fixed_since(question: dict, reported_at: str) -> list[dict]:
    """Faculty edits recorded AFTER the report was filed (ISO strings compare lexically)."""
    return [h for h in (question.get("errorHistory") or []) if h.get("at", "") > reported_at]
