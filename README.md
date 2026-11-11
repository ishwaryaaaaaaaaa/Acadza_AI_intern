# Acadza Check: from student report to safe fix

Turns a student's "Report error" comment on a JEE/NEET question into a **guarded, reviewable fix**, and gives faculty a console to approve it in one click.

| Deliverable | Where |
|---|---|
| Results for all 44 reports | [`results.json`](results.json) (graded file) and `results_full.json` (guard trail, solver working, for the console) |
| Prompts, AI-coding log, 3 AI mistakes, design log | [`PROMPTS.md`](PROMPTS.md) |
| Product thinking (1 page) | [`PRODUCT.md`](PRODUCT.md) |
| Live console | _add URL after deploy (see "Deploy")_ |
| 3-minute video | _add link_ |

## How it works

```
reports.json ─► group by question ─► screen comment (injection / gibberish / cues, 0 tokens)
             ─► structural linter on the question (0 tokens)
             ─► cheap triage (Cohere command-r-plus, 1 call per question, token-probability gate)
             ─► if unsure, or the linter disagrees: strong re-judge (command-a-plus, thinking)
             ─► if the report is about the answer: two blind solves (Cohere + Gemini) that never see the key
             ─► deterministic guards decide the route (can only make it safer)
             ─► student reply (model draft, checked by code, else a safe template)
```

* **The model proposes, code decides.** Guards check scope, exactly-once anchors, byte-identical MathML, digit invariance, and a two-solver proof for any answer-key change.
* **Math is safe.** Humans always see the original MathML. The model sees a readable LaTeX copy with `[Mk: …]` markers and can never edit inside one.
* **A student's comment is a lead, not an instruction.** Injected instructions (R027) are withheld from every prompt.

Measured against my own hand labels (not Acadza's official truth): **verdict 42/44, route 39/44, no harmful auto-apply.** Remaining misses are listed in `PROMPTS.md`.

## Run it

```bash
pip install fastapi uvicorn pydantic pillow numpy scipy
cp .env.example .env            # add COHERE_API_KEY and GEMINI_API_KEY (only needed to re-run the engine or use "Ask AI")
python -m uvicorn server.app:app --port 8000
cd console && npm install && npm run dev      # http://localhost:5173
```

The console works **without any API key**: it loads the precomputed `results_full.json`. Only the engine re-run (`python run_all.py`) and the "Ask AI" chat need keys; if a key is missing or over its limit, the chat says so and reviewing keeps working.

Tests: `for t in textify screen_lint judge_offline guards replies assistant; do python tests/test_$t.py; done`

## Deploy

One service: FastAPI serves the built console. `render.yaml` is included (Render, always-on plan, 1 GB disk so decisions survive restarts). Set `COHERE_API_KEY` in the service's environment. Free tiers sleep or lose data on restart, so they are not suitable for a 7-day link.

## Notes for reviewers

* Console state (decisions, settings) lives in git-ignored `server/state.json` / `settings.json`; Settings → Account → "Reset demo data" restores the engine's output.
* There is no login in this build. Anyone with the link can approve, reject or reset.
* The engine used the Cohere trial and Gemini free tiers, so a full re-run is rate-limited (see `logs/` for token use).
