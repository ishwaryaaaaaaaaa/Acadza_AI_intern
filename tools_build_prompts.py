"""Regenerates PROMPTS.md so the in-product prompts are always verbatim from engine/prompts.py."""
import sys

sys.path.insert(0, ".")
from engine import prompts as P  # noqa: E402


def block(t):
    return "```\n" + t.strip() + "\n```\n"


HEAD = """# PROMPTS.md

Honest note first: this was built with Claude Code across one long session. Prompts below are verbatim; where I paraphrase, I say so.

## 1. Prompts inside the product (verbatim, generated from `engine/prompts.py`)

Versions in use: __VERSIONS__

### Triage (cheap pass, `command-r-plus`, JSON schema, one call per question)
"""

TAIL = """
### What changed between versions, and why
* **Triage v1 to v2:** free-text answers from `command-a-plus` leaked its reasoning and got cut off before the JSON. I moved triage to `command-r-plus` with a JSON schema and put `evidence` *before* `verdict`, so the model reasons first and its verdict token probability is meaningful.
* **Triage v2 to v3:** the first live run was 34/44 verdicts. I added rules from reading the misses: edit anchors must be short and never contain `[Mk:]`; raw LaTeX visible in text is editable plain text; how to tell `solution_fix` from `wrong_question` and `unsound`; lint findings are facts, never answer `no_error` against one; keyword hints are unverified.
* **Reply v1 to v2:** `command-r7b` echoed student comments, said "Fixed" when nothing was fixed, and told wrong students they were right. v2 hides the comment from the writer, gives it a STATUS that limits what it may claim, and only verified FACTS. Code then rejects any draft that fails a check (echo, false fix claim, agreement with a wrong student, numbers or units not in the facts) and uses a template instead.

## 2. Prompts I gave my AI coding assistant (the first is verbatim; the rest are close paraphrases of my messages)

1. "i have got to create system for Acadza AI ... turns those reports into safe fixes, and a review console faculty would actually want to open ... focus on design as much as strategy ... tired faculty tell in seconds what changed and why, act in one click, and trust what they see?"
2. "no no u dont have to build anything, just tell me how i can proceed" (I wanted a plan before code.)
3. My flow: dedupe, check the report is genuine, check gibberish once instead of discarding it, rule out student mistakes, then solve and fix real defects with many guardrails, design last; and "use tokens judiciously" using the entropy-aware token generation idea.
4. "as a jee student myself ... math ... converts into text or html format that is not understandable, so there should be a huge guardrail" (this produced the linearizer and the byte-identical-MathML rule).
5. "wai wait we are building a system, so we need to use the live api key, undo whatever we have done ... give me the breakdown of all the tasks in different phases" (I had it throw away a prototype that never called a real model.)
6. Console: I supplied a design image per page and said "make the exact same ... all the functionalities", one page at a time. Rules I set: "all the stats ... should not be made up, it should change only when [the faculty acts]", "make the images better clarity", "the analysis should show up only when the faculty does something", and "remove this login ... this is not a real product, it should be able to work".

## 3. Three moments the AI was wrong, and how I caught them

1. **A confidently wrong triage call (R005).** The cheap model said `no_error` with 0.999 token probability on a question whose key is really wrong. Token probability alone cannot protect answer keys. I made any answer-related report run two blind solves that never see the key, and let that evidence overrule the triage verdict. Caught by comparing the first live run to my hand labels.
2. **A guard that silently never ran.** A "solver contradicts its own working" check used a word-boundary regex in a shell-written file, which became a backspace character, so it matched nothing and the panel looked fine. I only noticed because a case that plainly contradicted itself wasn't flagged. A similar shell-escaping bug broke a LaTeX regex and blanked a page. After that I wrote regexes with the editor tool, not shell heredocs.
3. **"Escalation" that never escalated.** My patch adding the strong-model pass failed to apply, so the escalation step just re-read the cheap answer from the cache and the score barely moved. I caught it because the logged probabilities in the "escalated" results were still the cheap model's. Related: when the strong model *did* run, it relabelled R015 (identical options) as an auto-fixable `option_repair` and it was auto-applied. A regression test now pins that.

Others worth knowing: JSON turned LaTeX `\\frac` into a form-feed character; `gemini-3.5-flash-lite` produced garbled and rambling solves; and an early draft of this document claimed prompt versions that had never run.

## 4. Design decisions log

* **Architecture:** model proposes, deterministic guards decide, and guards can only downgrade a route. Zero-token screening and linting come first; tokens are spent only where an answer is at stake or the cheap pass is unsure.
* **Token gating, honestly:** Cohere returns only the log-probability of the *chosen* token, so true entropy is not computable. I gate on the weakest token probability in the verdict and repair values instead. It flagged most cheap-model mistakes (0.38 to 0.82 on R014, R020, R036, R039, R013) and drove escalation (21 of 39 questions). It never relaxes the key proof. Gemini gives no logprobs, so it is a second opinion, not a gate.
* **Auto-apply vs human:** auto only for small, text-only, verifiable edits; key changes need two agreeing solvers; solution rewrites and anything authored go to faculty. I chose to miss some of my own "auto" labels (R011, R018, R019) rather than let an LLM write math into a record unreviewed.
* **Math:** the model reads `[M1: latex]` and may never edit inside it; the console shows rendered MathML in locked chips. Edits are exact-once substrings, math node hashes must match before and after, and a fuzz test over random edits never changed one.
* **UI:** queue ordered by harm; one-click Approve/Edit/Reject with an audit entry; before/after diff; AI evidence in plain language; "Mixed Signals" instead of a false "High Confidence" when solvers disagree; every number comes from real data and changes only when someone acts (Analytics counts only faculty decisions as resolved).
* **Tried and dropped:** an earlier prototype that never called a real model; a login (it locked its own author out and wasn't needed for a demo); keyword-only gibberish detection (it flagged a real sentence, now limited to 3 words or fewer).
* **Known limits:** scored against my own labels, not Acadza's; free-tier quotas (Gemini 20/day, Cohere trial 20/min) shaped model choices; remaining misses are R011 (non-unique anchor), R018/R019 (rewrites go to faculty by design), R024 (strong model said no_error), R026 (syllabus claim).
"""

doc = HEAD.replace("__VERSIONS__", str(P.VERSIONS))
doc += block(P.TRIAGE_SYSTEM) + "\nUser message template:\n" + block(P.TRIAGE_USER)
doc += "\nEscalation note, appended only when the cheap pass was unsure (strong model `command-a-plus`, thinking on):\n" + block(P.ESCALATION_NOTE)
doc += "\n### Blind solve (two independent solvers: Cohere `command-a-plus` and Gemini `3.5-flash`, `flash-lite` fallback)\n"
doc += block(P.SOLVE_SYSTEM) + block(P.SOLVE_USER)
doc += "\n### Student reply (`command-r-plus`; the draft is then checked by code)\n"
doc += block(P.REPLY_SYSTEM) + block(P.REPLY_USER)
doc += TAIL
open("PROMPTS.md", "w", encoding="utf-8").write(doc)
print(len(doc), "chars")
