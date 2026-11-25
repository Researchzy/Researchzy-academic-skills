"""path_tools.py on the simulated PM-1 survey: the same rows in every equation, the full-sample a*b with seeded
percentile and BCa intervals, centring that leaves b3 alone, probes inside the observed range, the index of moderated
mediation, semopy models, the task end to end, and the coverage of the percentile interval."""
from __future__ import annotations

import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

try:
    import numpy as np
    import pandas as pd
    import statsmodels.formula.api as smf
except ImportError:                    # the tests below skip; the system Python has none of these packages
    np = pd = smf = None
try:
    import semopy
except ImportError:
    semopy = None

SCRIPTS = Path(__file__).parents[1] / "scripts"
A, B, CP, A3 = 0.40, 0.30, 0.10, 0.15          # the PM-1 paths: a*b = 0.12, index a3*b = 0.045
MEDIATION = "mng ~ a*aut + age + female\neng ~ b*mng + cp*aut + age + female"
MODERATED = "mng ~ a1*aut + a2*sup + a3*aut:sup + age + female\neng ~ b*mng + cp*aut + age + female"


def load(name: str, alias: str):
    spec = importlib.util.spec_from_file_location(alias, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def pm1(seed: int, n: int = 350):
    """Composite scores of a cross-sectional survey. Support (the moderator) is skewed towards the top of its 1-7
    scale, so its mean plus one SD lies above 7; 8% of meaning and ten engagement scores are missing."""
    rng = np.random.default_rng(seed)
    aut = np.clip(rng.normal(4.5, 1.1, n), 1, 7)
    sup = np.clip(np.round((7 - rng.gamma(0.5, 2.0, n)) * 4) / 4, 1, 7)
    age, female = rng.normal(40, 10, n), rng.integers(0, 2, n).astype(float)
    wc = sup - sup.mean()
    mng = 4 + A * (aut - 4.5) + 0.2 * wc + A3 * (aut - 4.5) * wc + 0.01 * (age - 40) + rng.normal(0, 1.0, n)
    eng = 3 + B * mng + CP * aut + 0.005 * (age - 40) - 0.1 * female + rng.normal(0, 0.8, n)
    data = pd.DataFrame({"aut": aut, "mng": mng, "sup": sup, "eng": eng, "age": age, "female": female})
    data.loc[rng.choice(n, round(0.08 * n), replace=False), "mng"] = np.nan
    data.loc[rng.choice(n, 10, replace=False), "eng"] = np.nan
    return data


@unittest.skipIf(np is None, "numpy, pandas and statsmodels are not installed")
class PathToolsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pt = load("path_tools", "path_tools_under_test")
        cls.data = pm1(20261118)

    def test_every_equation_uses_the_same_rows(self):
        alone_a = smf.ols("mng ~ aut + age + female", self.data).fit()
        alone_b = smf.ols("eng ~ mng + aut + age + female", self.data).fit()
        self.assertNotEqual(alone_a.nobs, alone_b.nobs)                       # fitted alone, the rows differ
        fit = self.pt.fit_equations(self.data, MEDIATION)
        self.assertEqual({e["n"] for e in fit["equations"].values()}, {fit["n"]})
        self.assertEqual(fit["equations"]["mng"]["n_alone"], alone_a.nobs)
        self.assertEqual(fit["n"] + fit["rows_dropped"], 350)
        same = smf.ols("mng ~ aut + age + female", self.data.dropna()).fit()
        self.assertAlmostEqual(fit["coefficients"]["a"]["value"], same.params["aut"], places=12)
        self.assertAlmostEqual(fit["coefficients"]["a"]["se"], same.bse["aut"], places=12)

    def test_the_indirect_effect_is_the_full_sample_product(self):
        med = self.pt.bootstrap_indirect(self.data, MEDIATION + "\nind := a*b", n_boot=2000, seed=7)
        c, ind = med["coefficients"], med["defined"]["ind"]
        self.assertEqual(ind["estimate"], c["a"]["value"] * c["b"]["value"])
        self.assertLess(ind["low"], 0.12)
        self.assertGreater(ind["high"], 0.12)
        self.assertEqual(med["interval"], {"method": "percentile", "level": 0.95, "draws": 2000, "seed": 7, "failed": 0,
                                           "resampled": "cases (rows) with replacement"})
        total = self.pt.bootstrap_indirect(self.data, MEDIATION, {"total": "cp + a*b"}, n_boot=50, seed=7)["defined"]
        c_path = smf.ols("eng ~ aut + age + female", self.data.dropna()).fit().params["aut"]
        self.assertAlmostEqual(total["total"]["estimate"], c_path, places=10)  # c = c' + a*b on the same rows
        again = self.pt.bootstrap_indirect(self.data, MEDIATION, {"ind": "a*b"}, n_boot=2000, seed=7)
        other = self.pt.bootstrap_indirect(self.data, MEDIATION, {"ind": "a*b"}, n_boot=2000, seed=8)
        self.assertEqual(again["defined"]["ind"], ind)
        self.assertNotEqual(other["defined"]["ind"]["low"], ind["low"])
        bca = self.pt.bootstrap_indirect(self.data, MEDIATION, {"ind": "a*b"}, n_boot=2000, seed=7, method="bca")
        self.assertEqual((bca["interval"]["method"], bca["defined"]["ind"]["estimate"]), ("bca", ind["estimate"]))
        self.assertEqual(set(bca["defined"]["ind"]["bca"]), {"z0", "acceleration"})
        self.assertNotEqual(bca["defined"]["ind"]["low"], ind["low"])

    def test_refusals(self):
        bad = self.data.assign(age=self.data["age"].astype(str))
        for call in (lambda: self.pt.bootstrap_indirect(self.data, MEDIATION, {"ind": "a*b"}),          # no seed
                     lambda: self.pt.bootstrap_indirect(self.data, MEDIATION, {"ind": "a*b"}, seed=1, method="bc"),
                     lambda: self.pt.bootstrap_indirect(self.data, MEDIATION, {"ind": "a*z"}, seed=1),
                     lambda: self.pt.fit_equations(bad, MEDIATION),
                     lambda: self.pt.fit_equations(self.data, MEDIATION + "\nM =~ mng + eng"),
                     lambda: self.pt.fit_equations(self.data, MEDIATION.replace("cp*aut", "a*aut")),
                     lambda: self.pt.fit_equations(self.data, MEDIATION, center=["tenure"])):
            with self.assertRaises(ValueError):
                call()

    def test_centring_leaves_b3_alone_and_lowers_the_vif(self):
        raw = self.pt.fit_equations(self.data, MODERATED)
        centred = self.pt.fit_equations(self.data, MODERATED, center=["aut", "sup"])
        for key in ("value", "se", "t", "p"):
            self.assertAlmostEqual(centred["coefficients"]["a3"][key], raw["coefficients"]["a3"][key], places=10)
        self.assertAlmostEqual(centred["uncentred"]["a3"], centred["coefficients"]["a3"]["value"], places=10)
        self.assertGreater(raw["vif"]["mng"]["aut:sup"], 10)                    # high by construction
        self.assertLess(centred["vif"]["mng"]["aut:sup"], 2)
        self.assertNotAlmostEqual(centred["coefficients"]["a1"]["value"], raw["coefficients"]["a1"]["value"], places=3)
        self.assertEqual(centred["centring"]["around"], f"mean of the {centred['n']} analysed rows")
        self.assertAlmostEqual(centred["centring"]["columns"]["sup"], centred["columns"]["sup"]["mean"], places=12)

    def test_probes_stay_inside_the_observed_range(self):
        fit = self.pt.fit_equations(self.data, MODERATED, center=["aut", "sup"])
        sup = fit["columns"]["sup"]
        self.assertGreater(sup["mean"] + sup["sd"], sup["max"])                 # +1 SD lies above the scale
        plus = self.pt.probe(fit, focal="a1", interaction="a3", moderator="sup", probes=["mean-1sd", "mean", "mean+1sd"])
        self.assertEqual(plus["probe"]["out_of_range"], ["mean+1sd"])
        inside = self.pt.probe(fit, focal="a1", interaction="a3", moderator="sup", probes=["p16", "p50", "p84"])
        self.assertEqual(inside["probe"]["out_of_range"], [])
        self.assertEqual([s["w"] for s in inside["probe"]["slopes"]], [sup["p16"], sup["p50"], sup["p84"]])
        self.assertEqual((inside["kind"], inside["b3_uncentred"]), ("moderation", fit["uncentred"]["a3"]))
        self.assertIn("jn", inside["probe"])
        with self.assertRaises(ValueError):
            self.pt.probe(fit, focal="a1", interaction="b", moderator="sup", probes=["p50"])

    def test_the_index_of_moderated_mediation(self):
        imm = self.pt.moderated_mediation_index(self.data, MODERATED, index="a3*b", conditional="(a1 + a3*{w})*b",
                                                moderator="sup", probes=["p16", "p84"], n_boot=2000, seed=11,
                                                center=["aut", "sup"])
        c, defined, sup = imm["coefficients"], imm["defined"], imm["moderator"]
        self.assertEqual(defined["index"]["estimate"], c["a3"]["value"] * c["b"]["value"])
        self.assertLess(defined["index"]["low"], defined["index"]["estimate"])
        self.assertGreater(defined["index"]["high"], defined["index"]["estimate"])
        at = defined[f"at {sup['p84']:g}"]
        self.assertAlmostEqual(at["estimate"], (c["a1"]["value"] + c["a3"]["value"] * (sup["p84"] - sup["mean"])) * c["b"]["value"])
        self.assertEqual((imm["kind"], imm["index"], at["at"]), ("moderated_mediation", "index", sup["p84"]))
        with self.assertRaises(ValueError):
            self.pt.moderated_mediation_index(self.data, MODERATED, "a3*b", "(a1 + a3)*b", "sup", ["p50"], seed=1)

    def test_without_semopy_latent_models_are_not_checked(self):
        saved = sys.modules.get("semopy")
        sys.modules["semopy"] = None                                            # import semopy now raises ImportError
        try:
            fit = self.pt.fit_sem(self.data, "M =~ mng + eng")
            med = self.pt.bootstrap_indirect(self.data, "M =~ mng + eng\neng ~ b*M", {"x": "b"}, seed=1)
        finally:
            sys.modules.pop("semopy")
            if saved is not None:
                sys.modules["semopy"] = saved
        self.assertEqual((fit["status"], med["status"]), ("not_checked", "not_checked"))
        self.assertIn("ask the user before installing", fit["reason"])

    @unittest.skipIf(semopy is None, "semopy is not installed")
    def test_structural_models_with_semopy(self):
        rng = np.random.default_rng(5)
        x = rng.normal(size=300)
        m = 0.4 * x + rng.normal(scale=0.9, size=300)
        y = 0.3 * m + 0.1 * x + rng.normal(scale=0.9, size=300)
        items = pd.DataFrame({f"{name}{k}": 0.8 * f + rng.normal(scale=0.6, size=300)
                              for name, f in (("x", x), ("m", m), ("y", y)) for k in (1, 2, 3)}).assign(age=rng.normal(size=300))
        latent = "X =~ x1 + x2 + x3\nM =~ m1 + m2 + m3\nY =~ y1 + y2 + y3\nM ~ a*X + age\nY ~ b*M + cp*X\nind := a*b"
        sem = self.pt.fit_sem(items, latent)
        self.assertTrue(sem["converged"])
        self.assertEqual((sem["df"], sem["declared"], sem["n"]), (32, ["age ~~ age"], 300))   # 55 moments, 23 parameters
        self.assertEqual(set(sem["fit"]), {"chi2", "chi2_p", "cfi", "tli", "rmsea", "srmr"})
        self.assertGreater(sem["coefficients"]["a"]["value"], 0)
        saturated = self.pt.fit_sem(pd.DataFrame({"x": x, "m": m, "y": y}), "m ~ x\ny ~ m + x")
        self.assertEqual((saturated["df"], saturated["fit"]["rmsea"]), (0, None))
        boot = self.pt.bootstrap_indirect(items, latent, n_boot=20, seed=3)
        self.assertEqual((boot["kind"], boot["interval"]["draws"]), ("mediation", 20))
        self.assertAlmostEqual(boot["defined"]["ind"]["estimate"],
                               sem["coefficients"]["a"]["value"] * sem["coefficients"]["b"]["value"])

    def test_the_pm1_task_end_to_end(self):
        cp, old = load("check_paths", "check_paths_for_tools"), os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                Path("paths").mkdir()
                self.data.to_csv("survey.csv", index=False)
                Path("analysis.py").write_text("print('paths')\n", encoding="utf-8")
                Path("paths/model.md").write_text(
                    "# Model\n\nDesign: cross-sectional\n\n| Role | Column | Names in the text |\n|---|---|---|\n"
                    "| X | aut | autonomy; 自主性 |\n| M | mng | meaning; 意义感 |\n| W | sup | support; 支持 |\n"
                    f"| Y | eng | engagement; 投入 |\n\n```model mediation\n{MEDIATION}\n```\n\n```model moderated\n"
                    f"{MODERATED}\n```\n", encoding="utf-8")
                with redirect_stdout(io.StringIO()):
                    self.assertEqual(cp.main(["register"]), 0)
                rz = load("rz_results", "rz_results_for_tools")
                rz.OUT = "paths"
                med = self.pt.bootstrap_indirect(self.data, MEDIATION, {"ind": "a*b"}, n_boot=1000, seed=1)
                med["sensitivity"] = {"status": "not_done", "reason": "R is not installed"}
                fit = self.pt.fit_equations(self.data, MODERATED, center=["aut", "sup"])
                mod = self.pt.probe(fit, focal="a1", interaction="a3", moderator="sup", probes=["p16", "p50", "p84"])
                for rid, rec, value in (("indirect", med, med["defined"]["ind"]["estimate"]),
                                        ("a3", mod, mod["coefficients"]["a3"]["value"])):
                    rz.record(id=rid, question="PM-1", family=rid, role="primary", test="path model", unit="respondent",
                              n=rec["n"], estimate={"name": rid, "value": value, "units": "points"}, extra={"paths": rec})
                with redirect_stdout(io.StringIO()):
                    rz.finish(script="analysis.py", data=["survey.csv"], seed=1)
                ind = med["defined"]["ind"]
                Path("good.md").write_text(f"Autonomy was associated with engagement through meaning: the indirect effect "
                                           f"was {ind['estimate']:.2f} (95% CI {ind['low']:.2f} to {ind['high']:.2f}).\n",
                                           encoding="utf-8")
                Path("draft.md").write_text("Autonomy leads to engagement through meaning (Sobel z = 3.1), indicating full "
                                            "mediation; the effect is stronger at high support (+1 SD). The indirect effect "
                                            f"was {ind['estimate'] + 0.04:.2f}.\n\n自主性通过意义感导致投入，表明完全中介。\n",
                                            encoding="utf-8")
                out = io.StringIO()
                with redirect_stdout(out), redirect_stderr(io.StringIO()):
                    self.assertEqual(cp.main(["--text", "good.md"]), 0, out.getvalue())
                out = io.StringIO()
                with redirect_stdout(out), redirect_stderr(io.StringIO()):
                    self.assertEqual(cp.main(["--text", "draft.md"]), 1)
                problems = "\n".join(json.loads(out.getvalue())["problems"])
            finally:
                os.chdir(old)
        for flagged in ("'leads to' joins two model variables", "'导致' joins two model variables", "'Sobel' given as",
                        "'full mediation' given as", "'完全中介' given as", "+1 SD of sup", "prints 3.1: mismatch",
                        f"prints {ind['estimate'] + 0.04:.2f}: mismatch"):
            self.assertIn(flagged, problems)

    def test_the_percentile_interval_covers_a_times_b_at_about_95_percent(self):
        covered = sum(r["low"] <= A * B <= r["high"] for r in (
            self.pt.bootstrap_indirect(pm1(1000 + rep), MEDIATION, {"ind": "a*b"}, n_boot=500, seed=rep)["defined"]["ind"]
            for rep in range(200)))
        self.assertGreaterEqual(covered, 180)                                   # 95% of 200 is 190; the binomial SD 3.1
        self.assertLessEqual(covered, 198)


if __name__ == "__main__":
    unittest.main()
