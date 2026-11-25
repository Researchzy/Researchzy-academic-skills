"""rz_agreement.py against small examples computed by hand, and its degenerate cases: never 1.0, never 0, but None."""
from __future__ import annotations

import importlib.util
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts" / "rz_agreement.py"
spec = importlib.util.spec_from_file_location("rz_agreement", SCRIPT)
ra = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ra)


class CohenKappaTests(unittest.TestCase):
    def test_chance_agreement_uses_each_coders_own_marginals(self):
        # Both yes 30, a yes and b no 10, a no and b yes 5, both no 5 (n = 50). p_o = 35/50 = .70.
        # a says yes 40 times (.8), b 35 times (.7): p_e = .8 * .7 + .2 * .3 = .62, kappa = .08 / .38 = 4/19.
        # An assumed even split (p_e = .5) would give .40 instead.
        a = ["yes"] * 40 + ["no"] * 10
        b = ["yes"] * 30 + ["no"] * 10 + ["yes"] * 5 + ["no"] * 5
        result = ra.cohen_kappa(a, b)
        self.assertAlmostEqual(result["kappa"], 4 / 19)
        self.assertAlmostEqual(result["observed"], 0.70)
        self.assertAlmostEqual(result["expected"], 0.62)
        self.assertEqual((result["categories"], result["table"], result["reason"]), (["no", "yes"], [[5, 5], [10, 30]], None))

    def test_three_categories(self):
        # Table (a in rows, b in columns): x: 5 1 0 / y: 1 3 1 / z: 0 1 3. n = 15, p_o = 11/15.
        # Margins 6, 5, 4 for both coders: p_e = (36 + 25 + 16) / 225 = 77/225. kappa = (165 - 77) / (225 - 77) = 22/37.
        pairs = [("x", "x")] * 5 + [("x", "y"), ("y", "x")] + [("y", "y")] * 3 + [("y", "z"), ("z", "y")] + [("z", "z")] * 3
        result = ra.cohen_kappa([p[0] for p in pairs], [p[1] for p in pairs])
        self.assertAlmostEqual(result["kappa"], 22 / 37)
        self.assertEqual(result["table"], [[5, 1, 0], [1, 3, 1], [0, 1, 3]])

    def test_missing_labels_drop_out(self):
        # The fourth unit has no label from a. Pairs (x,x), (y,y), (x,y): p_o = 2/3; a: x 2, y 1; b: x 1, y 2;
        # p_e = (2 * 1 + 1 * 2) / 9 = 4/9; kappa = (2/9) / (5/9) = .4.
        result = ra.cohen_kappa(["x", "y", "x", None], ["x", "y", "y", "x"])
        self.assertAlmostEqual(result["kappa"], 0.4)
        self.assertEqual((result["n"], result["missing"]), (3, 1))

    def test_degenerate_tables_are_not_estimable_never_one(self):
        same = ra.cohen_kappa(["满意"] * 6, ["满意"] * 6)
        self.assertEqual((same["kappa"], same["reason"], same["observed"], same["expected"]), (None, "not_estimable", 1.0, 1.0))
        self.assertIn("chance agreement is 1", same["detail"])
        empty = ra.cohen_kappa([None, "x"], ["y", None])
        self.assertEqual((empty["kappa"], empty["reason"], empty["n"]), (None, "not_estimable", 0))
        opposite = ra.cohen_kappa(["x"] * 4, ["y"] * 4)       # p_o = 0 and p_e = 0: estimable, and 0
        self.assertEqual((opposite["kappa"], opposite["reason"]), (0.0, None))
        with self.assertRaises(ValueError):
            ra.cohen_kappa(["x"], ["x", "y"])


class KappaByCodeTests(unittest.TestCase):
    A = {"u1": {"x", "y"}, "u2": {"x"}, "u3": {"y"}, "u4": set(), "u5": {"x", "z"}, "u6": {"x"}}
    B = {"u1": {"x"}, "u2": {"x"}, "u3": {"y"}, "u4": {"y"}, "u5": {"x"}, "u6": {"x", "y"}}

    def test_each_code_is_scored_on_present_or_absent(self):
        result = ra.kappa_by_code(list(self.A), self.A, self.B, codes=["w", "x", "y", "z"])
        # x: identical (4 present, 2 absent) -> 1. y: a 1 0 1 0 0 0, b 0 0 1 1 0 1 -> p_o = 3/6, p_e = (4*3 + 2*3)/36 = .5 -> 0.
        # z: a present once, b never -> p_o = 5/6, p_e = (5*6 + 1*0)/36 = 5/6 -> 0. w: used by neither coder.
        self.assertAlmostEqual(result["x"]["kappa"], 1.0)
        self.assertAlmostEqual(result["y"]["kappa"], 0.0)
        self.assertAlmostEqual(result["z"]["kappa"], 0.0)
        self.assertEqual((result["y"]["a_present"], result["y"]["b_present"], result["y"]["both_present"]), (2, 3, 1))
        self.assertEqual((result["w"]["kappa"], result["w"]["reason"], result["w"]["detail"]),
                         (None, "not_estimable", "neither coder applied 'w' to any unit"))
        self.assertEqual(list(ra.kappa_by_code(list(self.A), self.A, self.B)), ["x", "y", "z"])   # default: codes used

    def test_a_code_on_every_unit_from_both_coders_is_not_estimable(self):
        units = ["U1", "U2", "U3"]
        result = ra.kappa_by_code(units, {u: ["工作负担", "x"] for u in units}, {u: ["工作负担"] for u in units})
        self.assertEqual((result["工作负担"]["kappa"], result["工作负担"]["reason"]), (None, "not_estimable"))
        self.assertEqual(result["工作负担"]["detail"], "both coders applied '工作负担' to every unit")

    def test_a_unit_one_coder_did_not_code_drops_out(self):
        partial = {u: codes for u, codes in self.B.items() if u != "u6"}
        result = ra.kappa_by_code(list(self.A), self.A, partial, codes=["x"])
        self.assertEqual((result["x"]["n"], result["x"]["missing"], result["x"]["kappa"]), (5, 1, 1.0))


class AlphaTests(unittest.TestCase):
    def test_two_coders(self):
        # Units (a,a) (a,b) (b,b) (b,b). Coincidences: o_aa 2, o_ab = o_ba 1, o_bb 4; n_a 3, n_b 5, n 8.
        # alpha = 1 - (n - 1) * 2 / (2 * 3 * 5) = 1 - 14/30 = 16/30.
        result = ra.krippendorff_alpha_nominal([["a", "a"], ["a", "b"], ["b", "b"], ["b", "b"]])
        self.assertAlmostEqual(result["alpha"], 16 / 30)
        self.assertEqual(result["coincidence"], [[2.0, 1.0], [1.0, 4.0]])
        self.assertAlmostEqual(result["observed_disagreement"], 2 / 8)
        self.assertAlmostEqual(result["expected_disagreement"], 30 / 56)

    def test_three_coders_with_missing_values(self):
        # (a,a,a) adds 6 ordered pairs of weight 1/2: o_aa 3; (a,b,-) adds o_ab = o_ba 1; (b,b,b): o_bb 3; (-,a,-) cannot
        # be paired. n_a = n_b = 4, n = 8: alpha = 1 - 7 * 2 / (2 * 4 * 4) = 18/32.
        result = ra.krippendorff_alpha_nominal([["a", "a", "a"], ["a", "b", None], ["b", "b", "b"], [None, "a", None]])
        self.assertAlmostEqual(result["alpha"], 18 / 32)
        self.assertEqual((result["units"], result["pairable_units"], result["values"]), (4, 3, 8))
        self.assertEqual(result["coincidence"], [[3.0, 1.0], [1.0, 3.0]])

    def test_degenerate_data_are_not_estimable(self):
        same = ra.krippendorff_alpha_nominal([[True, True]] * 5, n_boot=50, seed=1)
        self.assertEqual((same["alpha"], same["reason"], same["bootstrap"]), (None, "not_estimable", None))
        self.assertIn("so no disagreement is expected by chance", same["detail"])
        lonely = ra.krippendorff_alpha_nominal([["a", None], [None, "b"]])
        self.assertEqual((lonely["alpha"], lonely["detail"]), (None, "no unit has two values to compare"))

    def test_the_bootstrap_is_seeded_and_brackets_the_estimate(self):
        table = [["a", "a"]] * 8 + [["b", "b"]] * 8 + [["a", "b"], ["b", "a"]] + [["c", "c"]] * 2
        first = ra.krippendorff_alpha_nominal(table, n_boot=400, seed=11)
        again = ra.krippendorff_alpha_nominal(table, n_boot=400, seed=11)
        self.assertEqual(first["bootstrap"], again["bootstrap"])
        boot = first["bootstrap"]
        self.assertTrue(boot["low"] <= first["alpha"] <= boot["high"] <= 1.0)
        self.assertEqual((boot["n_boot"], boot["seed"], boot["level"]), (400, 11, 0.95))
        self.assertIsNone(ra.krippendorff_alpha_nominal(table)["bootstrap"])
        rare = ra.krippendorff_alpha_nominal([["a", "a"]] * 9 + [["a", "b"]], n_boot=200, seed=3)["bootstrap"]
        self.assertGreater(rare["not_estimable_draws"], 0)               # resamples without the one "b" unit


class ClassificationTests(unittest.TestCase):
    def test_per_class_figures_macro_f1_and_confusion(self):
        # a: TP 2, FP 1, FN 1 -> P = R = F1 = 2/3. b: TP 2, FP 1, FN 0 -> P 2/3, R 1, F1 4/5.
        # c: never predicted -> P None, R 0, F1 0. d: not in the sample -> nothing estimable.
        result = ra.classification_report(list("aaabbc"), list("aabbba"), classes=["a", "b", "c", "d"])
        a, b, c, d = (result["classes"][k] for k in "abcd")
        self.assertAlmostEqual(a["f1"], 2 / 3)
        self.assertEqual((b["precision"], b["recall"], b["f1"]), (2 / 3, 1.0, 0.8))
        self.assertEqual((c["precision"], c["recall"], c["f1"], c["support"]), (None, 0.0, 0.0, 1))
        self.assertEqual((d["precision"], d["recall"], d["f1"], d["reason"]), (None, None, None, "not_estimable"))
        self.assertAlmostEqual(result["accuracy"], 4 / 6)
        self.assertAlmostEqual(result["macro_f1"], (2 / 3 + 0.8 + 0.0) / 3)
        self.assertEqual(result["macro_f1_classes"], ["a", "b", "c"])
        self.assertEqual(result["confusion"]["matrix"], [[2, 1, 0, 0], [0, 2, 0, 0], [1, 0, 0, 0], [0, 0, 0, 0]])
        json.dumps(result)

    def test_labels_outside_the_classes_are_listed_not_dropped(self):
        result = ra.classification_report(["价格", "服务态度", None], ["价格", "价格", "质量"], classes=["价格", "质量", "服务"])
        self.assertEqual(result["unknown_labels"], {"truth": ["服务态度"], "pred": []})
        self.assertEqual(result["confusion"]["labels"], ["价格", "质量", "服务", "服务态度"])
        self.assertEqual(result["confusion"]["matrix"][3], [1, 0, 0, 0])
        self.assertEqual((result["n"], result["missing"], result["classes"]["服务"]["f1"]), (2, 1, None))
        self.assertIsNone(ra.classification_report([], [])["macro_f1"])


class CommandTests(unittest.TestCase):
    def test_a_table_of_units_by_coders(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "codes.csv"
            path.write_text("unit,model,user\nu1,a,a\nu2,a,b\nu3,b,b\nu4,b,b\n", encoding="utf-8")
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(ra.main([str(path), "--boot", "100", "--seed", "5"]), 0)
            result = json.loads(out.getvalue())
            self.assertAlmostEqual(result["alpha"]["alpha"], 16 / 30)
            self.assertAlmostEqual(result["kappa"]["kappa"], 0.5)
            with redirect_stderr(io.StringIO()) as err:
                self.assertEqual(ra.main([str(Path(tmp) / "missing.csv")]), 2)
            self.assertIn("cannot read", err.getvalue())


if __name__ == "__main__":
    unittest.main()
