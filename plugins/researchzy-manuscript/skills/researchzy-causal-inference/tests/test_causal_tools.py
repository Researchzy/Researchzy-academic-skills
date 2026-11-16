"""causal_tools.py: event dummies, Callaway-Sant'Anna against a known truth, TWFE, IV and the AR set, RI, SC,
weighting, the simplified sensitivity and the specification ledger."""
from __future__ import annotations

import importlib.util
import json
import math
import os
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).parents[1] / "scripts"


def load(name: str, alias: str):
    spec = importlib.util.spec_from_file_location(alias, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ct = load("causal_tools", "causal_tools_under_test")
try:
    import numpy as np
    import pandas as pd
    import statsmodels.api as sm
    import statsmodels.formula.api as smf
    HAVE = True
except ImportError:
    HAVE = False
NEEDS = unittest.skipUnless(HAVE, "numpy, pandas and statsmodels are not installed")


@NEEDS
class EventDummyTests(unittest.TestCase):
    def frame(self, cohort=2012.0):
        return pd.DataFrame({"unit": [1] * 9 + [2] * 9, "year": list(range(2008, 2017)) * 2,
                             "g": [cohort] * 9 + [float("nan")] * 9})

    def test_end_bins_the_omitted_period_and_never_treated_rows(self):
        out, names = ct.event_dummies(self.frame(), time="year", cohort="g", window=(-2, 2))
        self.assertEqual(names, ["lead2", "lag0", "lag1", "lag2"])
        first = out[out.unit == 1].set_index("year")
        self.assertEqual(first.loc[2008, "lead2"], 1)                    # e = -4 falls into the -2 bin
        self.assertEqual(first.loc[2011, names].sum(), 0)                # e = -1 is the reference
        self.assertEqual(first.loc[2016, "lag2"], 1)                     # e = 4 falls into the +2 bin
        self.assertEqual(out[out.unit == 2][names].to_numpy().sum(), 0)
        zero = self.frame().assign(g=lambda d: d.g.fillna(0))            # 0 means never when 0 is not a period
        self.assertEqual(ct.event_dummies(zero, time="year", cohort="g", window=(-2, 2))[0].query("unit == 2")[names]
                         .to_numpy().sum(), 0)

    def test_invariants_are_asserted(self):
        with self.assertRaises(ValueError):
            ct.event_dummies(self.frame(), time="year", cohort="g", window=(-1, 3))     # ref at the edge
        with self.assertRaises(ValueError):
            ct.event_dummies(self.frame(2012.5), time="year", cohort="g", window=(-2, 2))
        path = ct.event_path({"lead2": -0.1, "lag0": 0.5, "lag1": 0.7, "lag2": 0.9},
                             {"lead2": 0.2, "lag0": 0.2, "lag1": 0.3, "lag2": 0.3}, window=(-2, 2))
        self.assertEqual(path[1], (-1, 0.0, 0.0))
        self.assertEqual(len(path), 5)

    def test_first_treated_refuses_reversals(self):
        d = pd.DataFrame({"u": [1, 1, 1, 2, 2, 2], "t": [1, 2, 3] * 2, "d": [0, 1, 1, 0, 0, 0]})
        self.assertEqual(ct.first_treated(d, unit="u", time="t", treat="d").tolist()[:3], [2, 2, 2])
        self.assertTrue(math.isnan(ct.first_treated(d, unit="u", time="t", treat="d").iloc[3]))
        with self.assertRaises(ValueError):
            ct.first_treated(d.assign(d=[0, 1, 0, 0, 0, 0]), unit="u", time="t", treat="d")
        with self.assertRaises(ValueError):
            ct.first_treated(d.assign(d=[0, 2, 2, 0, 0, 0]), unit="u", time="t", treat="d")


@NEEDS
class CallawaySantAnnaTests(unittest.TestCase):
    def cs(self, frame, **options):
        return ct.callaway_santanna(frame, unit="unit", time="period", cohort="cohort", outcome="y", **options)

    def test_a_2x2_is_the_difference_in_mean_changes(self):
        frame = pd.DataFrame({"unit": list("AABBCCDD"), "period": [2000, 2001] * 4,
                              "cohort": [2001] * 4 + [None] * 4, "y": [1.0, 4.0, 2.0, 4.0, 1.5, 2.0, 3.0, 4.5]})
        result = self.cs(frame, B=0)
        self.assertAlmostEqual(result["overall"]["estimate"], (3.0 + 2.0) / 2 - (0.5 + 1.5) / 2)
        self.assertIsNone(result["overall"]["se"])
        self.assertEqual(result["att_gt"][0]["n_control"], 2)

    def test_group_time_cells_by_hand(self):
        y = {"A": [1, 2, 5, 6], "B": [2, 2, 6, 7], "C": [0, 1, 1, 4], "D": [1, 1.5, 2, 2.5]}
        cohort = {"A": 3, "B": 3, "C": 4, "D": None}
        frame = pd.DataFrame([(u, t + 1, cohort[u], v) for u, vs in y.items() for t, v in enumerate(vs)],
                             columns=["unit", "period", "cohort", "y"])
        cells = {(r["g"], r["t"]): r["estimate"] for r in self.cs(frame, control="not_yet_treated", B=0)["att_gt"]}
        # ATT(3, 1): base 2; controls adopt after period 2 (C) or never (D): -0.5 - (-0.75)
        # ATT(4, 1): base 3; C itself and the units treated at the base are not controls, so only D: -1 - (-1)
        expected = {(3, 1): 0.25, (4, 1): 0.0, (4, 2): 0.5, (3, 3): 3.25, (3, 4): 3.5, (4, 4): 2.5}
        for key, value in expected.items():
            self.assertAlmostEqual(cells[key], value, msg=str(key))
        never = {(r["g"], r["t"]): r["estimate"] for r in self.cs(frame, B=0)["att_gt"]}
        self.assertAlmostEqual(never[(3, 1)], 0.0)                         # D alone: -0.5 - (-0.5)
        self.assertAlmostEqual(never[(3, 3)], 3.0)

    def test_recovers_a_known_att_where_twfe_is_biased(self):
        frame, truth = ct.simulate_staggered(slope=0.5, seed=3)
        self.assertAlmostEqual(truth, frame.loc[frame.treated == 1, "effect"].mean())
        for control in ("never_treated", "not_yet_treated"):
            result = self.cs(frame, control=control, B=499, seed=7)
            self.assertLess(abs(result["overall"]["estimate"] - truth), 3 * result["overall"]["se"], control)
        twfe = ct.twfe(frame, unit="unit", time="period", outcome="y", regressors=["treated"])["coef"]["treated"]
        self.assertGreater(truth - twfe["estimate"], 4 * twfe["se"])      # far too low under growing effects
        flat, zero = ct.simulate_staggered(slope=0.0, seed=3)
        self.assertEqual(zero, 0.0)
        self.assertLess(abs(self.cs(flat, B=199, seed=7)["overall"]["estimate"]), 0.25)

    def test_bootstrap_bands_and_pretrends(self):
        frame, _ = ct.simulate_staggered(slope=0.5, pretrend={2018: (2014, 0.3)}, seed=3)
        result = self.cs(frame, B=499, seed=11)
        self.assertEqual(result["overall"], self.cs(frame, B=499, seed=11)["overall"])
        self.assertTrue(result["pretrend"]["reject"])
        self.assertTrue(result["pretrend_by_cohort"]["2018"]["reject"])
        self.assertFalse(result["pretrend_by_cohort"]["2014"]["reject"])
        self.assertGreater(result["sup_t"]["post"]["critical"], 1.96)
        rows = [r for r in result["event"] if not r.get("reference")]
        self.assertTrue(all(r["band_low"] <= r["low"] and r["band_high"] >= r["high"] for r in rows))
        self.assertEqual([r for r in result["event"] if r.get("reference")], [{"e": -1, "estimate": 0.0, "se": 0.0,
                                                                             "reference": True}])
        self.assertEqual(result["cohorts"], {"2014": 15, "2016": 15, "2018": 15})
        self.assertEqual(result["event_average"]["event_times"], list(range(8)))
        balanced = self.cs(frame, B=0, balance_e=2)
        self.assertEqual(max(r["e"] for r in balanced["event"]), 2)

    def test_not_yet_treated_without_never_treated_units(self):
        frame, _ = ct.simulate_staggered(never=0, seed=5)
        with self.assertRaises(ValueError) as caught:
            self.cs(frame, B=0)
        self.assertIn("use control='not_yet_treated'", str(caught.exception))
        result = self.cs(frame, control="not_yet_treated", B=0)
        self.assertIn([2018, 2018], result["cells_without_controls"])
        self.assertEqual(result["group"]["by_cohort"][-1]["cohort"], 2016)

    def test_refusals(self):
        frame, _ = ct.simulate_staggered(seed=5)
        with self.assertRaises(ValueError):
            self.cs(frame, B=99)                                          # no seed
        with self.assertRaises(ValueError):
            self.cs(frame, control="everyone", B=0)
        with self.assertRaises(ValueError):
            self.cs(pd.concat([frame, frame.head(1)]), B=0)


@NEEDS
class RegressionTests(unittest.TestCase):
    def test_cluster_robust_ols_matches_statsmodels(self):
        rng = np.random.default_rng(1)
        X = sm.add_constant(rng.normal(size=(200, 2)))
        y, groups = X @ [1.0, 0.5, -0.2] + rng.normal(size=200), np.repeat(np.arange(20), 10)
        fit = sm.OLS(y, X).fit(cov_type="cluster", cov_kwds={"groups": groups}, use_t=True)
        beta, V, dof = ct._ols(y, X, groups)
        np.testing.assert_allclose(beta, fit.params)
        np.testing.assert_allclose(np.sqrt(np.diag(V)), fit.bse)
        self.assertEqual(dof, 19)

    def test_twfe_equals_the_dummy_regression(self):
        frame, _ = ct.simulate_staggered(seed=2)
        frame = frame.drop(index=[3, 50, 51])                             # unbalanced
        mine = ct.twfe(frame, unit="unit", time="period", outcome="y", regressors=["treated"])
        full = smf.ols("y ~ treated + C(unit) + C(period)", frame).fit(cov_type="cluster",
                                                                        cov_kwds={"groups": frame["unit"]})
        self.assertAlmostEqual(mine["coef"]["treated"]["estimate"], full.params["treated"], places=10)
        N, U, T = len(frame), frame.unit.nunique(), frame.period.nunique()  # unit effects are not counted in K
        self.assertAlmostEqual(mine["coef"]["treated"]["se"], full.bse["treated"] * math.sqrt((N - U - T) / (N - T)),
                               places=10)
        self.assertEqual(mine["G"], U)


@NEEDS
class InstrumentTests(unittest.TestCase):
    def data(self, strength, seed=5):
        rng = np.random.default_rng(seed)
        cluster = np.repeat(np.arange(50), 20)
        u = rng.normal(size=1000) + np.repeat(rng.normal(size=50), 20)
        z = rng.normal(size=1000)
        d = strength * z + 0.8 * u + rng.normal(size=1000)
        return pd.DataFrame({"y": 2.0 * d + u + rng.normal(size=1000), "d": d, "z": z, "x": rng.normal(size=1000),
                             "cl": cluster})

    def test_2sls_first_stage_and_reduced_form(self):
        frame = self.data(1.0)
        fit = ct.iv_2sls(frame, outcome="y", treatment="d", instruments=["z"], cluster="cl")
        self.assertAlmostEqual(fit["estimate"], np.cov(frame.z, frame.y)[0, 1] / np.cov(frame.z, frame.d)[0, 1])
        first = fit["first_stage"]
        self.assertAlmostEqual(first["F"], (first["coef"]["z"] / first["se"]["z"]) ** 2)
        self.assertAlmostEqual(fit["estimate"], fit["reduced_form"]["coef"]["z"] / first["coef"]["z"])
        self.assertEqual((fit["G"], first["df"]), (50, [1, 49]))
        self.assertGreater(fit["ols"]["estimate"], fit["estimate"])      # OLS is pulled by the confounder

    def test_anderson_rubin_set(self):
        strong = self.data(1.0)
        fit = ct.iv_2sls(strong, outcome="y", treatment="d", instruments=["z"], covariates=["x"], cluster="cl")
        ar = ct.anderson_rubin(strong, outcome="y", treatment="d", instruments=["z"], covariates=["x"], cluster="cl")
        width = fit["high"] - fit["low"]
        self.assertTrue(ar["bounded"])
        self.assertEqual(len(ar["set"]), 1)
        self.assertLess(abs(ar["set"][0][0] - fit["low"]), 0.1 * width)
        self.assertLess(abs(ar["set"][0][1] - fit["high"]), 0.1 * width)
        weak = self.data(0.05)
        self.assertLess(ct.iv_2sls(weak, outcome="y", treatment="d", instruments=["z"], cluster="cl")["first_stage"]["F"],
                        3.84)
        self.assertFalse(ct.anderson_rubin(weak, outcome="y", treatment="d", instruments=["z"], cluster="cl")["bounded"])

    def test_against_linearmodels(self):
        try:
            from linearmodels.iv import IV2SLS
        except ImportError:
            self.skipTest("linearmodels is not installed")
        frame = self.data(1.0).assign(const=1.0)
        theirs = IV2SLS(frame.y, frame[["const", "x"]], frame.d, frame.z).fit(cov_type="clustered", clusters=frame.cl,
                                                                              debiased=True)
        mine = ct.iv_2sls(frame, outcome="y", treatment="d", instruments=["z"], covariates=["x"], cluster="cl")
        self.assertAlmostEqual(mine["estimate"], theirs.params["d"], places=8)
        self.assertAlmostEqual(mine["se"], theirs.std_errors["d"], places=6)


@NEEDS
class PermutationAndSynthTests(unittest.TestCase):
    def test_randomization_inference_counts_the_observed_assignment(self):
        rng = np.random.default_rng(3)
        clusters = np.repeat(np.arange(20), 5)
        a = np.repeat([1, 0] * 10, 5)
        y = rng.normal(size=100) + 3 * a
        result = ct.ri_pvalue(a, lambda s: y[s == 1].mean() - y[s == 0].mean(), B=199, seed=4, clusters=clusters)
        self.assertEqual((result["p"], result["min_p"]), (1 / 200, 1 / 200))
        null = ct.ri_pvalue(a, lambda s: 0.0, B=99, seed=4, clusters=clusters)
        self.assertEqual(null["p"], 1.0)
        with self.assertRaises(ValueError):
            ct.ri_pvalue(rng.integers(0, 2, 100), lambda s: 0.0, B=9, seed=4, clusters=clusters)
        strata, seen, free = np.repeat((np.arange(20) // 2) % 2, 5), set(), set()
        ct.ri_pvalue(a, lambda s: seen.add(int(s[strata == 0].sum())) or 0.0, B=50, seed=4, clusters=clusters,
                     strata=strata)
        ct.ri_pvalue(a, lambda s: free.add(int(s[strata == 0].sum())) or 0.0, B=50, seed=4, clusters=clusters)
        self.assertEqual(seen, {25})                                      # 5 of the 10 clusters in stratum 0 stay treated
        self.assertGreater(len(free), 1)

    def test_synthetic_control_weights_and_placebos(self):
        rng = np.random.default_rng(8)
        factor = np.cumsum(rng.normal(size=20))
        donors = np.column_stack([factor * rng.uniform(0.5, 1.5) + rng.normal(0, 0.3, 20) + rng.uniform(0, 3)
                                  for _ in range(8)])
        treated = donors @ np.array([0.5, 0.3, 0.2, 0, 0, 0, 0, 0])
        weights = ct.synth_weights(treated[:14], donors[:14])
        self.assertAlmostEqual(weights.sum(), 1.0, places=12)
        self.assertGreaterEqual(weights.min(), 0.0)
        np.testing.assert_allclose(weights[:3], [0.5, 0.3, 0.2], atol=1e-4)
        treated[14:] += 5.0
        wide = pd.DataFrame(np.column_stack([treated, donors]), columns=["T"] + [f"d{j}" for j in range(8)])
        result = ct.sc_placebos(wide, treated="T", T0=14)
        self.assertEqual((result["J"], result["rank"], result["p"], result["min_p"]), (8, 1, 1 / 9, 1 / 9))
        with self.assertRaises(ValueError):
            ct.sc_placebos(wide[["T", "d0", "d1"]], treated="T", T0=14)


@NEEDS
class WeightingTests(unittest.TestCase):
    def data(self, n=2000, sharpness=1.0, seed=6):
        rng = np.random.default_rng(seed)
        x1, x2 = rng.normal(size=n), rng.normal(size=n)
        d = rng.binomial(1, 1 / (1 + np.exp(-sharpness * (0.8 * x1 - 0.5 * x2))))
        return pd.DataFrame({"d": d, "y": 1.0 * d + x1 + 0.5 * x2 + rng.normal(size=n), "x1": x1, "x2": x2})

    def test_trimming_drops_and_never_clips(self):
        frame = self.data()
        result = ct.ipw(frame, treatment="d", outcome="y", covariates=["x1", "x2"], B=50, seed=1)
        self.assertGreater(result["trimming"]["dropped"], 0)
        self.assertEqual(result["n"]["after"], result["n"]["before"] - result["trimming"]["dropped"])
        self.assertEqual((result["trimming"]["method"], result["population"]), ("drop", "units with scores in [0.1, 0.9]"))
        X = sm.add_constant(frame[["x1", "x2"]])
        e = sm.Logit(frame.d, X).fit(disp=0).predict(X)
        keep = (e >= 0.1) & (e <= 0.9)
        t, c = keep & (frame.d == 1), keep & (frame.d == 0)
        w = e[c] / (1 - e[c])
        self.assertAlmostEqual(result["estimate"], frame.y[t].mean() - (w * frame.y[c]).sum() / w.sum(), places=10)
        self.assertLess(abs(result["estimate"] - 1.0), 4 * result["se"])
        self.assertLess(result["max_abs_smd_after"], max(abs(b["smd_before"]) for b in result["balance"]))
        self.assertEqual(result["se"], ct.ipw(frame, treatment="d", outcome="y", covariates=["x1", "x2"], B=50,
                                              seed=1)["se"])

    def test_doubly_robust_and_the_ate_rule(self):
        frame = self.data()
        dr = ct.ipw(frame, treatment="d", outcome="y", covariates=["x1", "x2"], estimand="ATE", doubly_robust=True)
        self.assertEqual(dr["estimator"], "aipw")
        self.assertLess(abs(dr["estimate"] - 1.0), 0.2)
        sharp = ct.ipw(self.data(sharpness=8.0), treatment="d", outcome="y", covariates=["x1", "x2"], estimand="ATE")
        self.assertGreater(sharp["trimming"]["trimmed_share"], 0.5)
        self.assertFalse(sharp["ate_allowed"])
        with self.assertRaises(ValueError):
            ct.ipw(frame, treatment="d", outcome="y", covariates=["x1"], B=10)
        with self.assertRaises(ValueError):
            ct.ipw(frame.assign(d=frame.d * 2), treatment="d", outcome="y", covariates=["x1"])


class SensitivityTests(unittest.TestCase):
    def test_hand_computed_bounds_and_breakdown(self):
        result = ct.relative_magnitude(2.0, 0.5, [0.4, -0.8])
        half = 1.959963984540054 * 0.5
        self.assertEqual(result["label"], "simplified version, not the Rambachan–Roth confidence set")
        self.assertAlmostEqual(result["largest_pre_deviation"], 0.8)
        self.assertAlmostEqual(result["rows"][1]["low"], 2.0 - half - 0.8)
        self.assertAlmostEqual(result["rows"][2]["high"], 2.0 + half + 1.6)
        self.assertAlmostEqual(result["breakdown_M"], (2.0 - half) / 0.8)
        self.assertFalse(result["fragile"])
        weak = ct.relative_magnitude(0.5, 0.5, [0.2])
        self.assertEqual((weak["breakdown_M"], weak["fragile"]), (0.0, True))
        self.assertIsNone(ct.relative_magnitude(1.0, 0.1, [])["breakdown_M"])


class SpecTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = os.getcwd()
        os.chdir(self.tmp.name)
        self.rz = load("rz_results", "rz_results")
        self.rz.OUT = "causal"
        sys.modules["rz_results"] = self.rz

    def tearDown(self):
        os.chdir(self.old)
        self.tmp.cleanup()

    def record(self, **fields):
        base = dict(design="staggered_did", estimator="callaway_santanna", headline=True,
                    cluster={"level": "county", "basis": "assignment", "G": 60, "G_treated": 45},
                    diagnostics={"cohorts": {"status": "pass"}}, id="att", question="Did it work?", family="jobs",
                    test="CS", unit="county", n={"counties": 60}, estimate={"name": "ATT", "value": 2.4, "units": "jobs"},
                    interval={"low": 1.8, "high": 2.9, "level": 0.95})
        base.update(fields)
        return ct.spec(**base)

    def test_every_specification_reaches_the_ledger(self):
        self.record()
        self.record(id="twfe", estimator="twfe", headline=False, estimate={"name": "b", "value": 0.3, "units": "jobs"},
                    interval={"low": -0.2, "high": 0.8, "level": 0.95})
        self.record(id="old", headline=False, kept=False, reason="chosen before the control group was fixed")
        lines = [json.loads(x) for x in Path("causal/ledger.jsonl").read_text().splitlines()]
        self.assertEqual([(x["id"], x["run"], x["status"], x["extra"]["causal"]["headline"]) for x in lines],
                         [("att", 1, "kept", True), ("twfe", 1, "kept", False), ("old", 1, "dropped", False)])
        self.assertEqual((lines[2]["interval"], lines[2]["n"]), ({"low": 1.8, "high": 2.9, "level": 0.95}, {"counties": 60}))
        self.assertFalse(Path("causal/specifications.jsonl").exists())
        results = json.loads(Path("causal/results.json").read_text())["results"]
        self.assertEqual((results[0]["role"], results[1]["role"], results[0]["effect_size"]),
                         ("primary", "secondary", "estimate"))
        self.assertEqual(results[0]["extra"]["causal"]["cluster"]["G"], 60)

    def test_refusals(self):
        for fields, message in (({"kept": False, "reason": "no"}, "a headline is kept"),
                                ({"diagnostics": {"cohorts": {"status": "ok"}}}, "needs a status"),
                                ({"diagnostics": {"cohorts": {"status": "not_checked"}}}, "without a reason"),
                                ({"cluster": {"level": "county"}}, "cluster must be"),
                                ({"design": ""}, "design and estimator"),
                                ({"permutation": {"B": 99}}, "permutation must be")):
            with self.assertRaises(ValueError) as caught:
                self.record(id=f"x{len(message)}", **fields)
            self.assertIn(message, str(caught.exception))


if __name__ == "__main__":
    unittest.main()
