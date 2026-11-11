# PRODUCT.md

**Who loses most when a question is broken?** The student who trusts it. A wrong answer key silently teaches the wrong thing to every student who attempts it, and they cannot tell. A typo costs a second; a wrong key costs marks and confidence at scale. So the queue is ordered by *harm*, not by recency: wrong key / wrong type / no valid option first, then content students can't solve (missing option, figure or value), then cosmetic fixes. Within a tier, cases that need a teacher outrank ones the AI already fixed, then more reports, then higher confidence. Many reports raise urgency but never replace evidence: five students saying "wrong" is not proof.

**What I would never let the AI auto-apply**
* **Anything that authors content:** new distractors for identical options, a missing figure, a rewritten solution (R018/R019 go to faculty even though the repair type allows auto), moving a question's chapter, deciding syllabus.
* **An answer-key change on one model's say-so.** It needs two independent solves that never saw the key or the comment, and a multiple-correct change also needs the stored solution to agree.
* **Any edit touching MathML.** The model cannot even address a math node.
* **Anything a student's comment tells it to do.** Comments are leads. A prompt-injection report (R027) is ignored and gets a neutral reply.
* **A reply that claims a fix that didn't happen.** Replies are checked by code and fall back to templates.

**One metric for week 1: wrong-key escape rate**, the share of answer keys that faculty later *reverse* after the AI auto-applied or confirmed them (target: 0). It is the single number that says whether auto-apply is safe. Watch it alongside faculty agreement with the AI check, shown in Analytics.

**One idea beyond this brief: fix before the student ever reports.** The linter and blind solvers already run on every question for almost no tokens. Run them nightly across all ~8 lakh questions and queue the disputed ones (solvers disagree with the key) for faculty. My run found defects nobody reported, such as a solution containing raw `\AA` and a blank option. Reports then become confirmation, not discovery.
