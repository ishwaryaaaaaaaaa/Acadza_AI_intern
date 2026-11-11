import json, sys
sys.path.insert(0, r"D:\Acadza AI intern")
from engine.screen import screen_comment, group_reports, fixed_since
from engine.lint import lint_question

D = r"D:\Acadza AI intern\data_raw\acadza-report-fix\data"
Q = {q["_id"]: q for q in json.load(open(D + r"\questions.json", encoding="utf-8"))}
R = json.load(open(D + r"\reports.json", encoding="utf-8"))
GT = json.load(open(r"D:\Acadza AI intern\eval\ground_truth.json", encoding="utf-8"))["labels"]

print("=== COMMENT SCREEN ===")
for r in sorted(R, key=lambda r: r["reportId"]):
    s = screen_comment(r)
    flags = [n for n in ("injection", "gibberish", "vague", "empty") if getattr(s, n)]
    print(r["reportId"], GT[r["reportId"]]["verdict"][:10].ljust(10), flags, s.cues, s.numbers, "|", r["comment"][:50])

print("\n=== GROUPS ===")
for qid, rs in group_reports(R).items():
    if len(rs) > 1:
        print(qid[:8], [r["reportId"] for r in rs])
    fx = fixed_since(Q[qid], rs[0]["reportedAt"]) if qid in Q else []
    if fx:
        print("  FIXED AFTER REPORT:", qid[:8], [r["reportId"] for r in rs], fx[0]["note"][:60])

print("\n=== LINT (every question) ===")
rep = {}
for r in R:
    rep.setdefault(r["questionId"], []).append(r["reportId"])
for qid, q in Q.items():
    fs = lint_question(q)
    print(qid[:8], rep.get(qid, ["UNREPORTED"]))
    for f in fs:
        print("    ", f.code, f.field, "->", f.repair, "|", f.detail)
