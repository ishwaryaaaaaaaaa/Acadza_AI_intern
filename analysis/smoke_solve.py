import json, sys, time
sys.path.insert(0, r"D:\Acadza AI intern")
from engine import judge
D = r"D:\Acadza AI intern\data_raw\acadza-report-fix\data"
Q = {q["_id"]: q for q in json.load(open(D + r"\questions.json", encoding="utf-8"))}
for pref in sys.argv[1:]:
    q = Q[next(k for k in Q if k.startswith(pref))]
    key = q[q["questionType"]]["answer"]
    for w in ("a", "b"):
        t = time.time()
        try:
            d = judge.solve_blind(q, w)
            print(pref, "stored key", key, "| solver", w, "->", d.get("answer"), "sound", d.get("sound"),
                  "| tok", d["_usage"], f"{time.time()-t:.0f}s", "|", str(d.get("working"))[:110])
        except Exception as e:
            print(pref, w, "ERR", str(e)[:160])
