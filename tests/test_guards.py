import json, random, sys, unittest
sys.path.insert(0, r"D:\Acadza AI intern")
from engine.guards import decide, key_audit, apply_text_edit, Decision
from engine.screen import screen_comment
from engine.textify import parse, math_hashes

D = r"D:\Acadza AI intern\data_raw\acadza-report-fix\data"
Q = {q["_id"]: q for q in json.load(open(D + r"\questions.json", encoding="utf-8"))}
R = {r["reportId"]: r for r in json.load(open(D + r"\reports.json", encoding="utf-8"))}


def q(p):
    return Q[next(k for k in Q if k.startswith(p))]


def run(rid, item, solves=None):
    rep = R[rid]
    qq = Q[rep["questionId"]]
    a = key_audit(qq, *solves) if solves else None
    return decide(qq, rep, screen_comment(rep), item, a)


def both(ans, sound=True):
    return ({"answer": ans, "sound": sound}, {"answer": ans, "sound": sound})


def item(verdict="defect", repair=None, edit=None, conf=0.95, pv=0.99, pr=0.99, ev="e"):
    return {"verdict": verdict, "repair": repair, "edit": edit, "confidence": conf, "evidence": ev,
            "_p_verdict": pv, "_p_repair": pr}


def E(f, a, b):
    return {"field": f, "find": a, "replace": b}


class KeySafety(unittest.TestCase):
    def test_R005_confident_wrong_triage_is_overruled_by_solves(self):
        d = run("R005", item("no_error", conf=1.0, pv=0.999), both("1"))      # stored key is 2
        self.assertEqual((d.verdict, d.repair, d.route), ("defect", "answer_key", "auto_apply"))
        self.assertEqual(d.edit, E("answer", '"2"', '"1"'))

    def test_vague_wrong_ans_R002_uses_audit(self):
        d = run("R002", item("not_actionable"), both("A"))                    # stored key is C
        self.assertEqual((d.repair, d.route), ("answer_key", "auto_apply"))
        self.assertEqual(d.edit["replace"], '"A"')

    def test_student_claim_cannot_change_key_when_solves_confirm(self):
        d = run("R033", item("defect", "answer_key", E("answer", '"3113"', '"3112.99"')), both("3113"))
        self.assertEqual((d.verdict, d.route, d.edit), ("no_error", "no_change", None))

    def test_solver_disagreement_goes_to_faculty_without_edit(self):
        d = run("R005", item("defect", "answer_key", E("answer", '"2"', '"1"')),
                ({"answer": "1", "sound": True}, {"answer": "2", "sound": True}))
        self.assertEqual(d.route, "faculty_review")
        self.assertIsNone(d.edit)

    def test_triage_key_edit_without_audit_never_auto(self):
        d = run("R005", item("defect", "answer_key", E("answer", '"2"', '"1"')), None)
        self.assertEqual(d.route, "faculty_review")

    def test_solution_pointing_elsewhere_blocks_auto(self):
        qq = q("60f744b3")      # its solution concludes 50 V, which is option A
        a = key_audit(qq, {"answer": "D", "sound": True}, {"answer": "D", "sound": True})
        self.assertEqual(a["status"], "disputed")

    def test_malformed_mcq_key_repairs_when_solves_match(self):
        d = run("R020", item("defect", "answer_key"), both(["A", "B", "D"]))
        self.assertEqual((d.repair, d.route, d.edit["replace"]), ("answer_key", "auto_apply", '["A", "B", "D"]'))

    def test_malformed_mcq_key_not_applied_if_solves_differ(self):
        d = run("R020", item("defect", "answer_key"), both(["A", "B"]))
        self.assertNotEqual(d.route, "auto_apply")

    def test_type_mismatch_R021(self):
        d = run("R021", item("defect", "type_mismatch"), both(["B"]))
        self.assertEqual((d.repair, d.route), ("type_mismatch", "auto_apply"))
        self.assertEqual(d.edit, E("questionType", "mcq", "scq"))
        self.assertEqual(d.extra_edits[0]["replace"], '"B"')

    def test_unsound_both_solvers(self):
        d = run("R034", item("defect", "unsound"), ({"answer": None, "sound": False},) * 2)
        self.assertEqual((d.repair, d.route), ("unsound", "faculty_review"))


class Injection(unittest.TestCase):
    def test_R027_cannot_edit_even_if_model_obeys(self):
        d = run("R027", item("defect", "answer_key", E("answer", '"A"', '"C"'), conf=1.0), both("A"))
        self.assertEqual((d.verdict, d.route, d.edit), ("no_error", "no_change", None))
        self.assertNotIn("admin", d.evidence.lower())


class Scope(unittest.TestCase):
    def test_human_only_repairs_never_auto(self):
        for rid, rep in (("R015", "identical_options"), ("R025", "diagram"), ("R042", "wrong_chapter"),
                         ("R026", "syllabus")):
            d = run(rid, item("defect", rep, E("question", "x", "y")))
            self.assertEqual(d.route, "faculty_review", rep)

    def test_duplicate_options_cannot_be_relabelled_option_repair(self):
        # live run: the strong model called R015 "option_repair" and invented a new option; it was auto-applied
        d = run("R015", item("defect", "option_repair", E("question", "0 W", "2 W")))
        self.assertEqual((d.repair, d.route), ("identical_options", "faculty_review"))

    def test_edit_outside_repair_fields(self):
        d = run("R022", item("defect", "spelling", E("answer", '"A"', '"B"')))
        self.assertEqual(d.route, "faculty_review")
        self.assertIsNone(d.edit)

    def test_non_defect_cannot_carry_edit(self):
        d = run("R036", item("display_issue", None, E("question", "a", "b")))
        self.assertEqual((d.route, d.edit), ("no_change", None))

    def test_invalid_verdict_falls_to_safe(self):
        d = run("R036", item("totally_fake"))
        self.assertEqual(d.route, "no_change")


class TextEdits(unittest.TestCase):
    def test_good_spelling_auto(self):
        d = run("R022", item("defect", "spelling", E("question", "plexux", "plexus")))
        self.assertEqual(d.route, "auto_apply")
        self.assertIn("question", d.preview)

    def test_spelling_cannot_move_a_digit(self):
        d = run("R012", item("defect", "spelling", E("question", "tisue", "tissue 2")))
        self.assertEqual(d.route, "faculty_review")

    def test_hallucinated_find(self):
        d = run("R022", item("defect", "spelling", E("question", "this text is not there", "x")))
        self.assertEqual(d.route, "faculty_review")

    def test_edit_inside_math_rejected(self):
        d = run("R016", item("defect", "solution_fix", E("solution", "[M1: V=", "[M1: W=")))
        self.assertEqual(d.route, "faculty_review")

    def test_markup_leak_replacement_must_be_clean(self):
        d = run("R014", item("defect", "markup_leak", E("question", r"\frac{7}{8}", r"\dfrac{7}{8}")))
        self.assertEqual(d.route, "faculty_review")
        d = run("R014", item("defect", "markup_leak", E("question", r"\frac{7}{8}", "7/8")))
        self.assertEqual(d.route, "auto_apply")

    def test_exam_reference(self):
        d = run("R013", item("defect", "exam_reference", E("question", "(NEET 2019) ", "")))
        self.assertEqual(d.route, "auto_apply")

    def test_stem_data_value_must_be_in_solution(self):
        d = run("R007", item("defect", "stem_data", E("question", "inductance", "inductance L = 12345 mH")))
        self.assertEqual(d.route, "faculty_review")

    def test_low_confidence_and_low_token_prob_downgrade(self):
        d = run("R022", item("defect", "spelling", E("question", "plexux", "plexus"), conf=0.6))
        self.assertEqual(d.route, "faculty_review")
        d = run("R022", item("defect", "spelling", E("question", "plexux", "plexus"), pr=0.5))
        self.assertEqual(d.route, "faculty_review")

    def test_big_solution_rewrite_goes_to_faculty(self):
        d = run("R018", item("defect", "solution_fix", E("solution", "x" * 300, "y")))
        self.assertEqual(d.route, "faculty_review")


class AlreadyFixed(unittest.TestCase):
    def test_R017_accepted_only_with_log(self):
        d = run("R017", item("already_fixed"))
        self.assertEqual((d.verdict, d.route), ("already_fixed", "no_change"))

    def test_claim_without_log_is_rejected(self):
        d = run("R022", item("already_fixed"))
        self.assertNotEqual(d.verdict, "already_fixed")


class Fuzz(unittest.TestCase):
    def test_no_edit_can_ever_change_math(self):
        rnd = random.Random(7)
        accepted = 0
        for qq in Q.values():
            body = qq[qq["questionType"]]
            for fld in ("question", "solution"):
                t = parse(body[fld]).llm_text
                if len(t) < 5:
                    continue
                for _ in range(25):
                    i = rnd.randrange(len(t) - 2)
                    j = min(len(t), i + rnd.randint(1, 30))
                    dd = Decision("x", qq["_id"], "defect")
                    rep = rnd.choice(["spelling", "noise", "markup_leak", "solution_fix", "stem_data",
                                      "option_repair", "answer_form"])
                    new = apply_text_edit(qq, rep, {"field": fld, "find": t[i:j],
                                                    "replace": rnd.choice(["", "ZZ", "<b>x</b>", "[M1: 5]", "9"])}, "", dd)
                    if new is not None:
                        accepted += 1
                        self.assertEqual(math_hashes(body[fld]), math_hashes(new))
        self.assertGreater(accepted, 20)   # the fuzz really exercised accepted edits


if __name__ == "__main__":
    unittest.main()
