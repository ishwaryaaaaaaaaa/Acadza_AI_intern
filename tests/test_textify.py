import json, sys, unittest
sys.path.insert(0, r"D:\Acadza AI intern")
from engine.textify import parse, math_hashes, EditError, digits

Q = json.load(open(r"D:\Acadza AI intern\data_raw\acadza-report-fix\data\questions.json", encoding="utf-8"))
BY = {q["_id"]: q for q in Q}
def body(qid, f="question"):
    q = BY[next(k for k in BY if k.startswith(qid))]
    return q[q["questionType"]][f]


class Fidelity(unittest.TestCase):
    def test_all_nodes_faithful(self):
        flagged, n = [], 0
        for q in Q:
            for f in ("question", "solution"):
                for k, m in parse(q[q["questionType"]][f]).math.items():
                    n += 1
                    if not m.ok:
                        flagged.append((q["_id"][:8], f, k))
        self.assertEqual(n, 204)
        # the only legit flag is the real raw-LaTeX leak in 612151a6's solution
        self.assertEqual(flagged, [("612151a6", "solution", "M1")])

    def test_digits_preserved_in_every_node(self):
        for q in Q:
            for f in ("question", "solution"):
                for m in parse(q[q["questionType"]][f]).math.values():
                    src = "".join(m.leaves)
                    self.assertEqual(digits(src), digits(m.latex), m.raw[:80])


class Edits(unittest.TestCase):
    def test_spelling_edit_applies_and_math_untouched(self):
        h = body("61ee6c9d")
        d = parse(h)
        self.assertIn("plexux", d.llm_text)
        new = d.apply_edit("plexux", "plexus")
        self.assertNotIn("plexux", new)
        self.assertEqual(math_hashes(h), math_hashes(new))
        self.assertEqual(len(new), len(h))

    def test_markup_leak_edit(self):
        h = body("63765a28")
        d = parse(h)
        new = d.apply_edit(r"\frac{7}{8} th", "7/8th")
        self.assertIn("7/8th", new)

    def test_cannot_touch_math_node(self):
        d = parse(body("60f744b3", "solution"))
        with self.assertRaises(EditError):
            d.apply_edit("[M1: V=", "[M1: W=")
        with self.assertRaises(EditError):
            d.apply_edit("50V", "70V")        # text lives inside <math>

    def test_nonunique_or_missing_find_rejected(self):
        d = parse(body("60f744b3"))
        with self.assertRaises(EditError):
            d.apply_edit("V", "W")            # many occurrences
        with self.assertRaises(EditError):
            d.apply_edit("no such text", "x")
        with self.assertRaises(EditError):
            d.apply_edit("", "x")

    def test_replacement_is_escaped(self):
        h = "<p>teh cat</p>"
        new = parse(h).apply_edit("teh", "<script>x</script>")
        self.assertNotIn("<script>", new)
        self.assertIn("&lt;script&gt;", new)

    def test_entities_map_back(self):
        h = "<p>5&nbsp;m &amp; 3 tisue</p>"
        d = parse(h)
        self.assertIn("5 m & 3 tisue", d.llm_text)
        self.assertEqual(d.apply_edit("tisue", "tissue"), "<p>5&nbsp;m &amp; 3 tissue</p>")
        with self.assertRaises(EditError):    # a find that would cut inside an entity pair is still safe
            d.apply_edit("m & 3 tisue\nx", "z")

    def test_edit_across_tags_rejected(self):
        h = "<p>ab<span>cd</span></p>"
        with self.assertRaises(EditError):
            parse(h).apply_edit("bc", "XX")
        self.assertEqual(parse(h).apply_edit("ab", "ZZ"), "<p>ZZ<span>cd</span></p>")


if __name__ == "__main__":
    unittest.main()
