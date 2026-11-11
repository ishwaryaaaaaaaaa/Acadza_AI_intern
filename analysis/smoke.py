import json, sys
sys.path.insert(0, r"D:\Acadza AI intern")
from engine import judge
D = r"D:\Acadza AI intern\data_raw\acadza-report-fix\data"
Q = {q["_id"]: q for q in json.load(open(D + r"\questions.json", encoding="utf-8"))}
R = json.load(open(D + r"\reports.json", encoding="utf-8"))
for pref in sys.argv[1:]:
    qid = next(k for k in Q if k.startswith(pref))
    reps = [r for r in R if r["questionId"] == qid]
    out = judge.triage_group(Q[qid], reps)
    print("==", pref, "tokens in/out", out["usage"], "cached", out["cached"])
    for rid, it in out["items"].items():
        print(" ", rid, it.get("verdict"), it.get("repair"), "conf", it.get("confidence"),
              "p_v", None if it["_p_verdict"] is None else round(it["_p_verdict"], 3),
              "p_r", None if it["_p_repair"] is None else round(it["_p_repair"], 3))
        print("     edit:", json.dumps(it.get("edit"), ensure_ascii=False)[:160])
        print("     why :", it.get("evidence"))
