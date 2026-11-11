import json, sys
sys.path.insert(0, r"D:\Acadza AI intern")
from engine.textify import parse
Q = json.load(open(r"D:\Acadza AI intern\data_raw\acadza-report-fix\data\questions.json", encoding="utf-8"))
bad = n = 0
for q in Q:
    typ = q["questionType"]
    for f in ("question", "solution"):
        d = parse(q[typ][f])
        for k, m in d.math.items():
            n += 1
            if not m.ok:
                bad += 1
                print("FLAG", q["_id"][-6:], f, k, m.warnings, m.checks, "\n   ", m.latex[:200])
print("nodes", n, "flagged", bad)
