"""python eval/score.py [results.json] : compare against my hand labels (NOT Acadza's official truth)."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
res = json.loads(Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "results.json").read_text(encoding="utf-8"))
gt = json.loads((ROOT / "eval" / "ground_truth.json").read_text(encoding="utf-8"))["labels"]
n = len(res)
v = r = ro = 0
unsafe = []
for x in sorted(res, key=lambda x: x["reportId"]):
    g = gt[x["reportId"]]
    okv = x["verdict"] == g["verdict"]
    okr = (x["repair"] == g["repair"]) if g["verdict"] == "defect" else True
    okro = x["route"] == g["route"]
    v += okv
    r += okr and okv
    ro += okro
    # a harmful auto-apply: auto route where the truth says not to touch it / needs a human
    if x["route"] == "auto_apply" and g["route"] != "auto_apply":
        unsafe.append(x["reportId"])
    flag = "" if (okv and okr and okro) else "  <== MISS"
    print(f'{x["reportId"]} got {x["verdict"][:13]:13} {str(x["repair"])[:16]:16} {x["route"]:14} | want {g["verdict"][:13]:13} {str(g["repair"])[:16]:16} {g["route"]:14}{flag}')
print(f"\nverdict {v}/{n}   verdict+repair {r}/{n}   route {ro}/{n}   auto-applied where truth says not: {unsafe or 'none'}")
