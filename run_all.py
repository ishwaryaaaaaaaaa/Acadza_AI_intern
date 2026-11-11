"""python run_all.py  ->  results.json (+ results_full.json for the console)"""
import json
import sys
from pathlib import Path

from engine import pipeline

ROOT = Path(__file__).resolve().parent
ids = set(sys.argv[1:]) or None
results, full, usage = pipeline.run(ids)
(ROOT / ("results.json" if not ids else "results_partial.json")).write_text(
    json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
(ROOT / ("results_full.json" if not ids else "results_full_partial.json")).write_text(
    json.dumps(full, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
print("tokens:", usage)
