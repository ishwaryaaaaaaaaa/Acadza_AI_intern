import json, sys, re, collections
D = sys.argv[1]
Q = json.load(open(D + "/questions.json", encoding="utf-8"))
R = json.load(open(D + "/reports.json", encoding="utf-8"))
T = json.load(open(D + "/taxonomy.json", encoding="utf-8"))

print("QUESTIONS", len(Q), "type", type(Q).__name__)
q0 = Q[0] if isinstance(Q, list) else next(iter(Q.values()))
print("fields:", list(q0.keys()))
qs = Q if isinstance(Q, list) else list(Q.values())
idk = "_id" if "_id" in q0 else ("questionId" if "questionId" in q0 else list(q0.keys())[0])
print("id key:", idk)
print(collections.Counter(q.get("type") or q.get("questionType") for q in qs))
print(collections.Counter(q.get("subject") for q in qs))
tot_math = sum(len(re.findall(r"<math", json.dumps(q))) for q in qs)
print("total <math> nodes:", tot_math, " total chars:", sum(len(json.dumps(q)) for q in qs))
print("--- sample question (trimmed) ---")
print(json.dumps(q0, ensure_ascii=False)[:1500])

print("\nREPORTS", len(R))
print(collections.Counter(r["source"] for r in R))
byq = collections.defaultdict(list)
for r in R:
    byq[r["questionId"]].append(r["reportId"])
print("distinct questions reported:", len(byq))
print("multi-report questions:", {k: v for k, v in byq.items() if len(v) > 1})
qids = {q[idk] for q in qs}
print("reports pointing at unknown question:", [r["reportId"] for r in R if r["questionId"] not in qids])
print("questions never reported:", sorted(qids - set(byq)))
print("comment length min/max:", min(len(r["comment"]) for r in R), max(len(r["comment"]) for r in R))
print("\nTAXONOMY keys:", list(T.keys()))
print(json.dumps(T, ensure_ascii=False)[:1800])
