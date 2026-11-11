"""Student replies: what the model is allowed to say, a deterministic guard on what it did say,
and safe templates when the model's reply fails the guard.

A reply is the only output a student ever sees, so it gets the same treatment as an edit:
the model drafts, code checks, and a failed check falls back to a template rather than shipping.
"""
from __future__ import annotations

import difflib
import json
import re

HINGLISH = re.compile(r"\b(hai|hain|kyu|kyun|chahiye|nahi|nahin|galat|toh|kya|aana|hona|mein|kar|karu|raha|rahi|diya|di)\b", re.I)

REPAIR_PLAIN = {
    "spelling": "there was a spelling mistake", "noise": "there was stray text in the question",
    "exam_reference": "an exam tag was left in the question text", "markup_leak": "raw code was showing instead of the math",
    "answer_form": "the unit / answer format was not stated", "notation": "a symbol was lost in an expression",
    "stem_data": "a value needed to solve it was missing", "option_repair": "an option was missing or blank",
    "solution_fix": "the solution had a problem", "solution_missing": "the solution was missing",
    "answer_key": "the answer key was wrong", "type_mismatch": "the question type was set wrong",
    "identical_options": "two options are the same", "diagram": "the figure is missing",
    "wrong_question": "the question and its solution don't match", "unsound": "no option is fully correct as written",
    "wrong_chapter": "it is filed under the wrong chapter", "syllabus": "it may be outside the syllabus",
}


def language(comment: str) -> str:
    return "Hinglish" if HINGLISH.search(comment or "") else "English"


def status(d, injection: bool) -> str:
    if injection:
        return "IGNORED"
    if d.verdict == "defect":
        return "FIXED_NOW" if d.route == "auto_apply" else "TEACHER_REVIEW"
    return {"no_error": "STUDENT_WRONG", "already_fixed": "ALREADY_FIXED", "display_issue": "NOT_THE_QUESTION",
            "app_issue": "NOT_THE_QUESTION", "language_mode": "NOT_THE_QUESTION"}.get(d.verdict, "UNCLEAR")


def new_answer(d):
    for e in [d.edit] + list(d.extra_edits or []):
        if e and e.get("field") == "answer":
            v = json.loads(e["replace"])
            return ", ".join(v) if isinstance(v, list) else str(v)
    return None


# statuses where a model-written reply adds something; the rest are fixed templates (zero tokens, zero risk)
MODEL_STATUSES = {"FIXED_NOW", "TEACHER_REVIEW", "STUDENT_WRONG"}


def final_key(q: dict, d) -> str:
    """The answer students will see after this decision."""
    na = new_answer(d) if d.route == "auto_apply" else None
    if na:
        return na
    a = q[q["questionType"]].get("answer")
    return ", ".join(x for x in a if x) if isinstance(a, list) else str(a)


def facts(d, q: dict, audit: dict | None, question_text: str, solution_text: str) -> str:
    """What the reply may rely on: verified content only. Internal mechanics are stripped."""
    ev = re.sub(r"(two )?independent (blind )?solves?|solver [AB]|stored key|triage|the model|blind", "our re-check",
                d.evidence or "", flags=re.I)
    parts = [ev.strip()]
    if d.repair:
        parts.append(f"Problem type: {REPAIR_PLAIN.get(d.repair, d.repair)}.")
    parts.append(f"Correct answer (after this decision): {final_key(q, d)}.")
    if status(d, False) == "STUDENT_WRONG":
        work = [((x or {}).get("working") or "").strip() for x in ((audit or {}).get("solves") or [])]
        work = [w for w in work if w]
        if work:
            parts.append(f"Key working from an independent re-solve: {work[0][:400]}")
        else:
            parts.append(f"Stored solution: {re.sub(r'[ \t\n]+', ' ', solution_text)[:400]}")
    return " ".join(p for p in parts if p)


def grounding(facts_text: str, question_text: str, solution_text: str, d=None, st: str = "") -> str:
    """Numbers a reply may use. A reply about a FIX may only quote the fix itself and the verified facts;
    a reply explaining why the student is wrong may also quote the question and the stored solution."""
    if st in ("FIXED_NOW", "TEACHER_REVIEW") and d is not None:
        edits = [e for e in [d.edit] + list(d.extra_edits or []) if e]
        return " ".join([facts_text] + [str(e.get("replace", "")) for e in edits])
    return " ".join([facts_text, question_text, solution_text])


# ------------------------------------------------------------------ the guard
FIX_CLAIM = re.compile(r"\b(has been|have been|is now|was|we('ve| have)|now|already|ab)\s+(been\s+)?"
                       r"(fixed|corrected|updated|changed|theek kar)|^\W*(fixed|corrected|updated)\b|theek kar diya", re.I)
JARGON = re.compile(r"\b(verdict|route|triage|solver|guard|llm|ai model|faculty[_ ]review|auto[_ ]apply|no_error|"
                    r"the student|the user|reportId)\b", re.I)
AGREE = re.compile(r"\byou('re| are| were) (right|correct)\b|\byou got (it|the (right|correct) answer)\b(?! wrong)|"
                   r"\byour answer (is|was) (right|correct)\b|\baap(ne)? sahi\b|\baapka answer sahi\b|\btum sahi\b|"
                   r"\bgood catch\b", re.I)
HARSH = re.compile(r"\byou got it wrong\b|\bwrong!|\bobviously\b|\bsimply\b|\bclearly you\b|\bcareless\b", re.I)
NUM = re.compile(r"(?<![A-Za-z])\d+(?:\.\d+)?")
UNIT = re.compile(r"(?<![A-Za-z\d.])(\d+(?:\.\d+)?)\s*(mm|cm|km|m|kg|g|ms|s|sec|min|N|V|mV|A|mA|W|J|eV|Pa|mH|H|K|Hz|"
                  r"days?|hours?|seconds?)(?![A-Za-z])")
LETTER_CLAIM = re.compile(r"\b(?:answer|option|jawaab|uttar)\s+(?:is\s+|hai\s+|=\s*)?(?:now\s+)?\(?([A-D])\)?(?![A-Za-z])",
                          re.I)


def check_reply(d, comment: str, text: str, injection: bool, ground: str | None = None,
                key: str | None = None) -> list[str]:
    """Return the list of problems; empty means the reply may ship."""
    st = status(d, injection)
    t = (text or "").strip()
    bad = []
    if not t:
        return ["empty"]
    if len(t) > 400 or len(re.findall(r"[.!?](\s|$)", t)) > 3:
        bad.append("longer than 3 sentences")
    if JARGON.search(t):
        bad.append(f"internal wording: {JARGON.search(t).group(0)!r}")
    c = (comment or "").strip().lower()
    if c and (difflib.SequenceMatcher(None, c, t.lower()).ratio() > 0.6 or (len(c) >= 12 and c in t.lower())):
        bad.append("echoes the student's comment")
    if st not in ("FIXED_NOW", "ALREADY_FIXED") and FIX_CLAIM.search(t):
        bad.append(f"claims a fix that did not happen ({st})")
    if st in ("STUDENT_WRONG", "IGNORED", "UNCLEAR", "NOT_THE_QUESTION") and AGREE.search(t):
        bad.append(f"tells the student they are right ({st})")
    if HARSH.search(t):
        bad.append(f"harsh tone: {HARSH.search(t).group(0)!r}")
    if ground is not None:      # every number must come from verified content, never from the student or the model
        gnums = {x.lstrip("0") or "0" for x in NUM.findall(ground)}
        stray = [x for x in NUM.findall(t) if (x.lstrip("0") or "0") not in gnums]
        if stray:
            bad.append(f"numbers not backed by verified facts: {stray}")
        # a value with a unit must appear with THAT unit in the facts ("10 cm" fixed, reply says "10 mm")
        gpairs = {(n.lstrip("0") or "0", u.lower()) for n, u in UNIT.findall(ground)}
        gunits = {}
        for n, u in gpairs:
            gunits.setdefault(n, set()).add(u)
        # flag only a CONTRADICTION: the facts give this number with another unit and never with this one
        wrong = [f"{n} {u}" for n, u in UNIT.findall(t)
                 if (k := n.lstrip("0") or "0") in gunits and u.lower() not in gunits[k]]
        if wrong:
            bad.append(f"value/unit not in verified facts: {wrong}")
    if key is not None:
        keyl = set(re.findall(r"[A-D]", key))
        claimed = {m.upper() for m in LETTER_CLAIM.findall(t)}
        if keyl and claimed - keyl:
            bad.append(f"names option(s) {sorted(claimed - keyl)} as the answer; key is {key}")
    if st == "IGNORED" and re.search(r"admin|ignore|instruction|answer to [A-D]", t, re.I):
        bad.append("repeats the injected instruction")
    na = new_answer(d)
    if st == "FIXED_NOW" and d.repair in ("answer_key", "type_mismatch") and na and \
            not all(re.search(rf"(?<![A-Za-z0-9.]){re.escape(x.strip())}(?![A-Za-z0-9]|\.\d)", t) for x in na.split(",")):
        bad.append(f"does not state the corrected answer {na}")
    return bad


# ------------------------------------------------------------------ safe templates
def template(d, comment: str, injection: bool) -> str:
    st, hi = status(d, injection), language(comment) == "Hinglish"
    what = REPAIR_PLAIN.get(d.repair or "", "something was wrong")
    na = new_answer(d)
    if st == "FIXED_NOW":
        if na:
            return (f"Aap sahi the, answer key galat thi. Sahi answer {na} hai aur ab key theek kar di gayi hai. Thanks for reporting!"
                    if hi else f"You were right: the answer key was wrong. The correct answer is {na}, and the key has been fixed. Thanks for reporting!")
        return (f"Aap sahi the: {what}. Ab ise theek kar diya gaya hai, thanks!" if hi
                else f"Good catch: {what}. It has been fixed now. Thanks for reporting!")
    if st == "TEACHER_REVIEW":
        return (f"Thanks, aapne sahi jagah dekha: {what}. Ek teacher ise check karke jaldi theek karenge." if hi
                else f"Thanks, you spotted a real problem: {what}. A teacher will check it and fix it soon.")
    if st == "STUDENT_WRONG":
        return ("Humne ise dobara solve kiya aur diya hua answer sahi hai. Aapka answer kis step par alag aaya, bataoge? Hum saath mein dekh lenge."
                if hi else "We solved this again from scratch and the given answer holds. Tell us the step where your answer differs and we'll go through it with you.")
    if st == "ALREADY_FIXED":
        return "Thanks! A teacher already corrected this after your report, so you should see the fixed version now."
    if st == "NOT_THE_QUESTION":
        if d.verdict == "language_mode":
            return ("Yeh question abhi sirf English mein available hai. Hindi version ke liye request note kar li hai." if hi
                    else "This question is only available in English right now. We've noted the request for another language.")
        if d.verdict == "app_issue":
            return ("Question mein koi galti nahi hai; yeh app ki problem lag rahi hai. App update karke dobara try karo, aur hum app team ko bata rahe hain." if hi
                    else "The question itself is fine; this looks like an app problem. Please update the app and try again; we've passed it to the app team.")
        return ("Question sahi hai; problem screen par dikhne ki hai. Phone ko landscape mein ya app update karke try karo." if hi
                else "The question itself is fine; this is a display problem on your screen. Try rotating to landscape or updating the app.")
    if st == "IGNORED":
        return "This box is only for reporting a mistake in a question. If something in this question looks wrong, tell us what and we'll check it."
    return ("Thanks for reporting! Batao exactly kya galat laga, hum turant check karenge." if hi
            else "Thanks for reporting! Could you tell us in one line what exactly looked wrong? We'll check it right away.")
