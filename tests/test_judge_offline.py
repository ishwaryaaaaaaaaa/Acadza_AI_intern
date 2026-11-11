import json, sys, unittest
sys.path.insert(0, r"D:\Acadza AI intern")
from engine import judge, llm

D = r"D:\Acadza AI intern\data_raw\acadza-report-fix\data"
Q = {q["_id"]: q for q in json.load(open(D + r"\questions.json", encoding="utf-8"))}
R = json.load(open(D + r"\reports.json", encoding="utf-8"))

def fake_reply(text, bad=None):
    # one logprob per char; mark the `bad` substring as improbable
    lps = [(c, -0.0) for c in text]
    if bad:
        i = text.index(bad)
        for k in range(i, i + len(bad)):
            lps[k] = (text[k], -1.2)
    return llm.Reply(text, "cohere", "fake", 10, 5, lps)

class T(unittest.TestCase):
    def test_triage_gating_per_report(self):
        qid = next(k for k in Q if k.startswith("60f744b3"))
        reps = [r for r in R if r["questionId"] == qid]
        ids = [r["reportId"] for r in reps]
        body = {"reports": [{"reportId": i, "verdict": "defect", "repair": "answer_key", "edit": None,
                             "confidence": 0.9, "evidence": "x"} for i in ids]}
        text = json.dumps(body)
        # make ONLY the second report's repair value improbable
        second = text.index(ids[1])
        bad_at = text.index('"answer_key"', second)
        lps = [(c, -0.0) for c in text]
        for k in range(bad_at + 1, bad_at + 11):
            lps[k] = (text[k], -1.2)
        calls = []
        judge._call = lambda *a, **k: (calls.append(1), llm.Reply(text, "cohere", "fake", 100, 50, lps))[1]
        out = judge.triage_group(Q[qid], reps)
        self.assertEqual(len(calls), 1)                       # one call for all reports on a question
        p = [out["items"][i]["_p_repair"] for i in ids]
        self.assertGreater(p[0], 0.95)
        self.assertLess(p[1], 0.4)                            # the uncertain one is identified
        self.assertGreater(p[2], 0.95)
    def test_no_logprobs_means_ungated(self):
        self.assertIsNone(llm.value_prob([], '{"verdict": "defect"}', "verdict"))
    def test_prompt_never_contains_injected_comment(self):
        qid = next(k for k in Q if k.startswith("6062ec84"))
        reps = [r for r in R if r["questionId"] == qid]
        seen = {}
        def spy(role, system, user, **k):
            seen["u"] = user
            return llm.Reply(json.dumps({"reports": []}), "cohere", "fake")
        judge._call = spy
        judge.triage_group(Q[qid], reps)
        self.assertNotIn("IGNORE ALL PREVIOUS", seen["u"])
        self.assertIn("comment withheld", seen["u"])
    def test_taxonomy_prompt(self):
        t = judge.taxonomy_text()
        self.assertIn("HUMAN-ONLY", t); self.assertIn("answer_key", t)

if __name__ == "__main__":
    unittest.main()
