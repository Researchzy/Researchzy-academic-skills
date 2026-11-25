"""rz_accuracy.py against hand-computed examples and independent implementations (scipy's beta quantiles,
statsmodels' interval and McNemar functions, scikit-learn's roc_auc_score and logistic regression, a root of the
score equation), the refusals, the optimism loop and the null-label check on the DA-1 data, record(), the figures."""
from __future__ import annotations

import importlib.util
import io
import json
import math
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

SCRIPTS = Path(__file__).parents[1] / "scripts"
sys.path.insert(0, str(Path(__file__).parent))
import da1_fixture  # noqa: E402


def load(name: str, alias: str):
    spec = importlib.util.spec_from_file_location(alias, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ra = load("rz_accuracy", "rz_accuracy_under_test")
try:
    import numpy as np
    from scipy import optimize, stats
    from sklearn.feature_selection import SelectKBest, f_classif
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import roc_auc_score
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    from statsmodels.stats.proportion import confint_proportions_2indep, proportion_confint
    HAVE = True
except ImportError:
    HAVE = False
try:
    import matplotlib  # noqa: F401
    HAVE_MPL = True
except ImportError:
    HAVE_MPL = False
NEEDS = unittest.skipUnless(HAVE, "numpy, scipy, statsmodels and scikit-learn are not installed")
Z = 1.959963984540054


def da1(split="test"):
    """The verified DA-1 rows of one split, the corrected split (crossing patients all in development)."""
    rows = da1_fixture.rows()
    crossing = {r["patient_id"] for r in rows if r["split"] == "test"} & {r["patient_id"] for r in rows
                                                                       if r["split"] == "development"}
    keep = [r for r in rows if r["biopsy"] != "" and ("development" if r["patient_id"] in crossing else r["split"]) == split]
    return {"y": np.array([int(r["biopsy"]) for r in keep]), "groups": [r["patient_id"] for r in keep],
            "X": np.array([[float(r[p]) for p in da1_fixture.PREDICTORS] for r in keep]),
            **{k: np.array([float(r[k]) for r in keep]) for k in ("biomarker", "clinical_score")}}


def pipeline(X, y):
    """Scaling, a univariate filter and the fit, all inside: the corrected version of the user's model.py."""
    pipeline.calls += 1
    model = make_pipeline(StandardScaler(), SelectKBest(f_classif, k=4), LogisticRegression(max_iter=1000)).fit(X, y)
    return lambda new: model.predict_proba(new)[:, 1]


pipeline.calls = 0


@NEEDS
class TwoByTwoTests(unittest.TestCase):
    def test_exact_intervals_likelihood_ratios_and_predictive_values(self):
        t = ra.two_by_two(37, 12, 3, 88, design="consecutive")
        m = t["measures"]
        # Clopper-Pearson for 37/40 is the pair of beta quantiles B(0.025; 37, 4) and B(0.975; 38, 3).
        self.assertAlmostEqual(m["sensitivity"]["low"], stats.beta.ppf(0.025, 37, 4), places=10)
        self.assertAlmostEqual(m["sensitivity"]["high"], stats.beta.ppf(0.975, 38, 3), places=10)
        # The draft's Wald interval, 0.925 +- 1.96 * sqrt(0.925 * 0.075 / 40), passes 1 (planted problem 4).
        self.assertGreater(0.925 + Z * math.sqrt(0.925 * 0.075 / 40), 1)
        self.assertLess(m["sensitivity"]["high"], 1)
        # LR+ = (37/40) / (12/100) and LR- = (3/40) / (88/100): log intervals as statsmodels' log interval of a ratio
        # of two independent proportions.
        for name, counts in (("lr_positive", (37, 40, 12, 100)), ("lr_negative", (3, 40, 88, 100))):
            low, high = confint_proportions_2indep(*counts, compare="ratio", method="log")
            self.assertAlmostEqual(m[name]["value"], (counts[0] / counts[1]) / (counts[2] / counts[3]))
            self.assertAlmostEqual(m[name]["low"], low, places=10)
            self.assertAlmostEqual(m[name]["high"], high, places=10)
        self.assertEqual((m["ppv"]["numerator"], m["ppv"]["denominator"], m["npv"]["denominator"]), (37, 49, 91))
        # Bayes' rule at the sample's own prevalence, 40/140, gives back the table's PPV and NPV.
        bayes = ra.two_by_two(37, 12, 3, 88, design="case_control", prevalence=40 / 140, prevalence_source="test")
        self.assertAlmostEqual(bayes["measures"]["ppv"]["value"], 37 / 49)
        self.assertAlmostEqual(bayes["measures"]["npv"]["value"], 88 / 91)
        self.assertLess(bayes["measures"]["npv"]["low"], 88 / 91)
        wilson = ra.two_by_two(37, 12, 3, 88, design="consecutive", method="wilson")["measures"]["sensitivity"]
        self.assertEqual((wilson["low"], wilson["high"]), proportion_confint(37, 40, method="wilson"))

    def test_a_case_control_sample_gets_no_predictive_values_without_a_sourced_prevalence(self):
        t = ra.two_by_two(110, 24, 10, 96, design="case_control")                 # planted problem 7: 50% cases
        for name in ("ppv", "npv"):
            self.assertIsNone(t["measures"][name]["value"])
            self.assertIn("target population's prevalence", t["measures"][name]["reason"])
        self.assertAlmostEqual(t["measures"]["sensitivity"]["value"], 110 / 120)
        with self.assertRaisesRegex(ValueError, "prevalence_source"):
            ra.two_by_two(110, 24, 10, 96, design="case_control", prevalence=0.08)
        stated = ra.two_by_two(110, 24, 10, 96, design="case_control", prevalence=0.08, prevalence_source="registry, table 2")
        lr = (110 / 120) / (24 / 120)                                              # PPV odds = LR+ x prior odds
        self.assertAlmostEqual(stated["measures"]["ppv"]["value"], lr * 0.08 / 0.92 / (1 + lr * 0.08 / 0.92))
        self.assertEqual(stated["measures"]["ppv"]["prevalence"]["source"], "registry, table 2")

    def test_zero_cells(self):
        m = ra.two_by_two(20, 0, 0, 30, design="consecutive")["measures"]
        self.assertIsNone(m["lr_positive"]["value"])
        self.assertIn("infinite", m["lr_positive"]["reason"])
        self.assertEqual((m["lr_negative"]["value"], m["lr_negative"]["low"]), (0.0, None))
        self.assertEqual(m["specificity"]["high"], 1.0)
        self.assertIsNone(ra.two_by_two(0, 3, 0, 7, design="consecutive")["measures"]["sensitivity"]["value"])
        with self.assertRaises(ValueError):
            ra.two_by_two(1.5, 3, 0, 7, design="consecutive")


@NEEDS
class AucTests(unittest.TestCase):
    def test_delong_by_hand(self):
        # Positives 0.9, 0.8, 0.4; negatives 0.7, 0.4, 0.2. The positives outrank 1, 1 and 0.5 of the negatives (0.4
        # ties one), the negatives are outranked by 2/3, 5/6 and 1 of the positives. AUC = 5/6; S10 = 1/12,
        # S01 = 1/36; var = S10/3 + S01/3 = 1/27. Logit interval: ln 5 -+ 1.96 * sqrt(1/27) / (5/6 * 1/6).
        r = ra.auc([1, 1, 1, 0, 0, 0], [0.9, 0.8, 0.4, 0.7, 0.4, 0.2])
        self.assertAlmostEqual(r["value"], 5 / 6)
        self.assertAlmostEqual(r["se"], math.sqrt(1 / 27))
        half = Z * math.sqrt(1 / 27) / (5 / 36)
        self.assertAlmostEqual(r["low"], 1 / (1 + math.exp(-(math.log(5) - half))))
        self.assertAlmostEqual(r["high"], 1 / (1 + math.exp(-(math.log(5) + half))))
        self.assertEqual(r["method"], "DeLong, logit scale")

    def test_the_auc_is_scikit_learns_with_ties(self):
        rng = np.random.default_rng(7)
        y = rng.integers(0, 2, 300)
        score = np.round(y + rng.normal(0, 1.2, 300), 1)                          # rounded: many ties
        self.assertAlmostEqual(ra.auc(y, score)["value"], roc_auc_score(y, score), places=12)
        with self.assertRaises(ValueError):
            ra.auc([1, 0, 0], [0.3, 0.2, 0.1])                                     # one positive: no DeLong variance

    def test_two_nodules_per_patient_take_the_bootstrap_by_patient(self):
        d = da1()                                                                  # planted problem 10
        with self.assertRaisesRegex(ValueError, "seed="):
            ra.auc(d["y"], d["biomarker"], groups=d["groups"])
        r = ra.auc(d["y"], d["biomarker"], groups=d["groups"], B=300, seed=11)
        self.assertEqual((r["method"], r["B"], r["seed"]), ("bootstrap by patient, percentile", 300, 11))
        self.assertLess(r["patients"], r["units"])
        self.assertTrue(r["low"] < r["value"] < r["high"])
        self.assertEqual(r, ra.auc(d["y"], d["biomarker"], groups=d["groups"], B=300, seed=11))

    def test_paired_delong_by_hand(self):
        # y = 1 1 1 0 0; a = .9 .7 .3 | .5 .2; b = .6 .8 .1 | .4 .3. Placements of a: positives 1, 1, 1/2, negatives 2/3,
        # 1; of b: positives 1, 1, 0, negatives 2/3, 2/3. AUCs 5/6 and 2/3. Over positives var(a) = 1/12, var(b) = 1/3,
        # cov = 1/6; over negatives var(a) = 1/18, var(b) = 0, cov = 0. var = (1/12 + 1/3 - 1/3)/3 + (1/18)/2 = 1/18.
        r = ra.compare_auc([1, 1, 1, 0, 0], [0.9, 0.7, 0.3, 0.5, 0.2], [0.6, 0.8, 0.1, 0.4, 0.3])
        self.assertAlmostEqual(r["value"], 1 / 6)
        self.assertAlmostEqual(r["se"], math.sqrt(1 / 18))
        self.assertAlmostEqual(r["p"], 2 * stats.norm.sf((1 / 6) / math.sqrt(1 / 18)))
        same = ra.compare_auc([1, 1, 0, 0], [0.9, 0.4, 0.5, 0.1], [0.9, 0.4, 0.5, 0.1])
        self.assertEqual((same["value"], same["se"], same.get("p")), (0.0, 0.0, None))

    def test_two_tests_on_the_same_patients_are_compared_by_their_paired_difference(self):
        d = da1()                                                                  # planted problem 9
        one = {}
        for i, g in enumerate(d["groups"]):
            one.setdefault(g, i)                                                   # first nodule of each patient
        idx = sorted(one.values())
        r = ra.compare_auc(d["y"][idx], d["biomarker"][idx], d["clinical_score"][idx])
        self.assertEqual(r["method"], "DeLong, paired")
        self.assertAlmostEqual(r["value"], roc_auc_score(d["y"][idx], d["biomarker"][idx])
                               - roc_auc_score(d["y"][idx], d["clinical_score"][idx]))
        self.assertTrue(r["low"] < r["value"] < r["high"])
        both = ra.compare_auc(d["y"], d["biomarker"], d["clinical_score"], groups=d["groups"], B=300, seed=5)
        self.assertEqual(both["method"], "bootstrap by patient, paired, percentile")
        self.assertNotIn("p", both)

    def test_dev_cutoff(self):
        # Cut-offs 0.35, 0.4 and 0.8 all give J = 0.5 on this development sample; the lowest is kept.
        cut = ra.dev_cutoff([0, 0, 1, 1], [0.1, 0.4, 0.35, 0.8])
        self.assertEqual((cut["value"], cut["source"], cut["youden_j"]), (0.35, "development", 0.5))


@NEEDS
class McNemarTests(unittest.TestCase):
    def test_exact_p_and_newcombe_interval(self):
        # Paired table both 4, only A 2, only B 6, neither 3: exact p = 2 * P(X <= 2), X ~ Bin(8, 1/2) = 74/256. As ad = bc,
        # phi = 0 and the paired interval equals statsmodels' Newcombe interval for 6/15 against 10/15.
        y = np.ones(15, dtype=int)
        a = np.array([1] * 6 + [0] * 9)
        b = np.array([1] * 4 + [0] * 2 + [1] * 6 + [0] * 3)
        r = ra.mcnemar_pair(y, a, b)
        self.assertAlmostEqual(r["p"], 74 / 256)
        self.assertAlmostEqual(r["value"], (2 - 6) / 15)
        low, high = confint_proportions_2indep(6, 15, 10, 15, compare="diff", method="newcomb")
        self.assertAlmostEqual(r["low"], low, places=10)
        self.assertAlmostEqual(r["high"], high, places=10)
        swapped = ra.mcnemar_pair(y, b, a)
        self.assertAlmostEqual(swapped["low"], -r["high"])

    def test_the_phi_term_and_specificity(self):
        # both 20, only A 9, only B 2, neither 10: phi = (200 - 18) / sqrt(29 * 12 * 22 * 19), with Wilson margins from
        # statsmodels for 29/41 and 22/41 (Newcombe's method 10 written out).
        y = np.zeros(41, dtype=int)
        a = np.array([0] * 29 + [1] * 12)                  # among=0: a correct result is a negative one
        b = np.array([0] * 20 + [1] * 9 + [0] * 2 + [1] * 10)
        r = ra.mcnemar_pair(y, a, b, among=0)
        (l1, u1), (l2, u2) = proportion_confint(29, 41, method="wilson"), proportion_confint(22, 41, method="wilson")
        phi, p1, p2 = 182 / math.sqrt(29 * 12 * 22 * 19), 29 / 41, 22 / 41
        self.assertEqual(r["measure"], "specificity")
        self.assertAlmostEqual(r["low"], p1 - p2 - math.sqrt((p1 - l1) ** 2 - 2 * phi * (p1 - l1) * (u2 - p2) + (u2 - p2) ** 2))
        self.assertAlmostEqual(r["high"], p1 - p2 + math.sqrt((u1 - p1) ** 2 - 2 * phi * (u1 - p1) * (p2 - l2) + (p2 - l2) ** 2))
        self.assertAlmostEqual(r["p"], 2 * stats.binom.cdf(2, 11, 0.5))
        with self.assertRaisesRegex(ValueError, "independent pairs"):
            ra.mcnemar_pair([1, 1], [1, 0], [0, 1], groups=["p1", "p1"])


@NEEDS
class CalibrationTests(unittest.TestCase):
    def test_intercept_and_slope_against_independent_fits(self):
        rng = np.random.default_rng(3)
        lp = rng.normal(-1, 1.2, 1500)
        p = 1 / (1 + np.exp(-lp))
        y = rng.binomial(1, 1 / (1 + np.exp(-(0.3 + 0.7 * lp))))
        c = ra.calibration(y, p)
        # The intercept with logit(p) as offset solves sum(y - expit(a + logit p)) = 0.
        root = optimize.brentq(lambda a: np.sum(y - 1 / (1 + np.exp(-(a + lp)))), -5, 5)
        self.assertAlmostEqual(c["intercept"]["value"], root, places=5)
        slope = LogisticRegression(C=np.inf, tol=1e-10, max_iter=10000).fit(lp[:, None], y).coef_[0, 0]
        self.assertAlmostEqual(c["slope"]["value"], slope, places=4)
        self.assertTrue(c["slope"]["low"] < 0.7 < c["slope"]["high"])
        self.assertAlmostEqual(c["brier"], np.mean((y - p) ** 2))
        self.assertEqual(len(c["tenths"]), 10)
        grouped = ra.calibration(y, p, groups=np.repeat(np.arange(750), 2))
        self.assertIn("cluster-robust by patient", grouped["method"])
        self.assertNotEqual(grouped["slope"]["low"], c["slope"]["low"])
        with self.assertRaisesRegex(ValueError, "strictly between 0 and 1"):
            ra.calibration([1, 0], [1.0, 0.2])


@NEEDS
class NetBenefitTests(unittest.TestCase):
    def test_by_hand(self):
        # y 1 1 0 0 0, risks .8 .3 .6 .2 .1. At pt = .25 three are treated, TP 2, FP 1: 2/5 - 1/5 * 1/3; treat all
        # 2/5 - 3/5 * 1/3. At pt = .5: TP 1, FP 1: 1/5 - 1/5 * 1 = 0; treat all 2/5 - 3/5.
        nb = ra.net_benefit([1, 1, 0, 0, 0], [0.8, 0.3, 0.6, 0.2, 0.1], [0.25, 0.5], design="consecutive")
        for got, want in zip(nb["model"] + nb["treat_all"], [0.4 - 0.2 / 3, 0.0, 0.4 - 0.2, -0.2]):
            self.assertAlmostEqual(got, want)
        self.assertEqual(nb["treat_none"], [0.0, 0.0])

    def test_a_case_control_sample_needs_the_target_prevalence(self):
        with self.assertRaisesRegex(ValueError, "target population's prevalence"):
            ra.net_benefit([1, 1, 0, 0], [0.8, 0.3, 0.6, 0.2], [0.25], design="case_control")
        nb = ra.net_benefit([1, 1, 0, 0], [0.8, 0.3, 0.6, 0.2], [0.25], design="case_control", prevalence=0.1,
                            prevalence_source="registry 2024, table 1")
        self.assertAlmostEqual(nb["model"][0], 1.0 * 0.1 - 0.5 * 0.9 / 3)        # sens 2/2, false-positive rate 1/2
        for bad in ([0.0, 0.2], [0.3, 0.2]):
            with self.assertRaises(ValueError):
                ra.net_benefit([1, 0], [0.8, 0.2], bad, design="consecutive")


@NEEDS
class InternalValidationTests(unittest.TestCase):
    def test_optimism_reruns_the_whole_pipeline_on_patients(self):
        d = da1("development")                                                     # planted problems 2 and 6
        pipeline.calls = 0
        r = ra.optimism(pipeline, d["X"], d["y"], groups=d["groups"], B=25, seed=20261118)
        self.assertEqual(pipeline.calls, 26)                                       # once on all data, once per resample
        self.assertEqual((r["B_used"], r["resampled"], r["seed"]), (25, "patients", 20261118))
        auc = r["metrics"]["auc"]
        self.assertGreater(auc["optimism"], 0)
        self.assertAlmostEqual(auc["corrected"], auc["apparent"] - auc["optimism"])
        self.assertEqual(r, ra.optimism(pipeline, d["X"], d["y"], groups=d["groups"], B=25, seed=20261118))

    def test_noise_shows_its_optimism(self):
        rng = np.random.default_rng(4)
        X, y = rng.normal(size=(240, 20)), rng.binomial(1, 0.3, 240)
        r = ra.optimism(pipeline, X, y, B=40, seed=1)["metrics"]["auc"]
        self.assertGreater(r["apparent"] - r["corrected"], 0.05)
        self.assertLess(abs(r["corrected"] - 0.5), 0.08)

    def test_resamples_keep_a_patients_rows_together_and_failures_are_counted(self):
        X = np.repeat(np.arange(60.0), 2)[:, None]                                 # the patient number as the predictor
        y, seen = np.tile([0, 1], 60), []

        def spy(X_, y_):
            seen.append(np.bincount(X_[:, 0].astype(int)))
            if len(seen) % 3 == 0:
                raise RuntimeError("cannot fit")
            return lambda new: np.full(len(new), 0.5)
        r = ra.optimism(spy, X, y, groups=np.repeat(np.arange(60), 2), B=9, seed=2)
        self.assertTrue(all((counts % 2 == 0).all() for counts in seen))
        self.assertEqual((r["failures"], r["B_used"]), (3, 6))
        self.assertIn("RuntimeError: cannot fit", r["failure_examples"])

    def test_null_label_check(self):
        d = da1("development")
        honest = ra.null_label_check(pipeline, d["X"], d["y"], groups=d["groups"], R=5, seed=9)
        self.assertEqual((honest["status"], honest["R_used"], honest["folds"]), ("ok", 5, 5))
        self.assertLess(abs(honest["value"] - 0.5), honest["margin"] + 0.05)
        fitted = make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000)).fit(d["X"], d["y"])
        leaky = ra.null_label_check(lambda X, y: (lambda new: fitted.predict_proba(new)[:, 1]), d["X"], d["y"],
                                    groups=d["groups"], R=5, seed=9)
        self.assertEqual(leaky["status"], "problem")
        self.assertIn("learns from something other than its arguments", leaky["reason"])


@NEEDS
class RecordTests(unittest.TestCase):
    """Real results of the DA-1 test split through record(), then check_accuracy.py on them."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = os.getcwd()
        os.chdir(self.tmp.name)
        rows = da1_fixture.rows()
        crossing = {r["patient_id"] for r in rows if r["split"] == "test"} & {r["patient_id"] for r in rows
                                                                           if r["split"] == "development"}
        for r in rows:
            r["split"] = "development" if r["patient_id"] in crossing else r["split"]
        da1_fixture.write(Path("."), table=rows)
        probe = load("probe_accuracy", "probe_for_record")
        with redirect_stdout(io.StringIO()):
            probe.main(["nodules.csv", "--id", "patient_id", "--reference", "biopsy", "--positive", "1", "--split", "split",
                        "--development", "development", "--test", "test"])
        Path("analysis.py").write_text("print('analysis')\n", encoding="utf-8")

    def tearDown(self):
        os.chdir(self.old)
        self.tmp.cleanup()

    def test_record_and_check(self):
        rz = load("rz_results", "rz_results")
        rz.OUT = "diagnostic-accuracy"
        sys.modules["rz_results"] = rz
        d, probe = da1(), "diagnostic-accuracy/nodules.probe.json"
        common = {"question": "How accurate is the biomarker?", "design": "consecutive", "dataset": "test", "probe": probe}
        cut = {"value": da1_fixture.CUTOFF, "source": "plan"}
        entries = ra.record(ra.two_by_two(**ra.cells(d["y"], d["biomarker"] >= da1_fixture.CUTOFF), design="consecutive",
                                          patients=len(set(d["groups"]))), id="bm", model="biomarker", threshold=cut, **common)
        self.assertEqual([e["id"] for e in entries], ["bm.sensitivity", "bm.specificity", "bm.lr_positive",
                                                      "bm.lr_negative", "bm.ppv", "bm.npv"])
        ra.record(ra.auc(d["y"], d["biomarker"], groups=d["groups"], B=200, seed=1), id="bm_auc", model="biomarker",
                  no_calibration="a biomarker value, not a risk", **common)
        ra.record(ra.auc(d["y"], d["clinical_score"], groups=d["groups"], B=200, seed=1), id="cs_auc",
                  model="clinical score", no_calibration="a points score, not a risk", **common)
        ra.record(ra.compare_auc(d["y"], d["biomarker"], d["clinical_score"], groups=d["groups"], B=200, seed=1),
                  id="diff", models=("biomarker", "clinical score"), **common)
        risk = 1 / (1 + np.exp(-(d["biomarker"] - 3.2)))
        ra.record(ra.calibration(d["y"], risk, groups=d["groups"]), id="cal", model="risk", **common)
        ra.record(ra.net_benefit(d["y"], risk, [0.05, 0.1, 0.2], design="consecutive", groups=d["groups"]), id="nb",
                  model="risk", at=[0.1], **common)
        with self.assertRaisesRegex(ValueError, "not one of the planned thresholds"):
            ra.record(ra.net_benefit(d["y"], risk, [0.1], design="consecutive"), id="nb2", model="risk", at=[0.15], **common)
        with redirect_stdout(io.StringIO()):
            rz.finish(script="analysis.py", data=["nodules.csv"], seed=1)
        ca = load("check_accuracy", "check_for_record")
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            code = ca.main(["--probe", probe])
        summary = json.loads(out.getvalue())
        self.assertEqual(code, 0, summary["problems"])
        for name in ("fields", "intervals", "calibration", "predictive", "thresholds", "leakage", "complete"):
            self.assertEqual(summary["checks"][name], "ok", name)

    @unittest.skipUnless(HAVE_MPL, "matplotlib is not installed")
    def test_figures(self):
        d = da1()
        roc = ra.roc_figure("roc-test", data=["nodules.csv"], curves=[
            ("Biomarker", d["y"], d["biomarker"], ra.auc(d["y"], d["biomarker"], groups=d["groups"], B=100, seed=1))])
        risk = 1 / (1 + np.exp(-(d["biomarker"] - 3.2)))
        cal = ra.calibration_figure("calibration-test", data=["nodules.csv"], cal=ra.calibration(d["y"], risk))
        dca = ra.decision_figure("decision-test", data=["nodules.csv"],
                                 nb=ra.net_benefit(d["y"], risk, np.arange(0.05, 0.31, 0.05), design="consecutive"))
        for path in (roc, cal, dca):
            self.assertTrue(Path(path).is_file(), path)
            self.assertTrue(Path(path).with_suffix(".png").is_file())
            self.assertEqual(json.loads(Path(path[:-4] + ".figure.json").read_text())["axis_findings"], [])


if __name__ == "__main__":
    unittest.main()
