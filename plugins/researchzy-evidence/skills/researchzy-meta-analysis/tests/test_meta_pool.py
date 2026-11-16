"""meta_pool.py: pooling against independent computations and statsmodels, truncation, the Hartung-Knapp
floor, the prediction interval, small-study tests, subgroups, zero-event methods and the result file.

The 13 BCG vaccine trials (Colditz et al. 1994) are the main fixture. The reference values below were
computed independently of meta_pool.py: REML by direct numerical maximisation of the restricted
likelihood, the others from their closed forms. statsmodels, when installed, is a second oracle for
DerSimonian-Laird, Paule-Mandel and Mantel-Haenszel; it does not truncate DL and has no prediction
interval, so those are checked against our own arithmetic only.
"""
from __future__ import annotations

import csv
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


def load(name: str, alias: str):
    spec = importlib.util.spec_from_file_location(alias, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mp = load("meta_pool", "meta_pool_under_test")
es = load("effect_sizes", "effect_sizes_for_pooling")
HAVE = mp.np is not None
if HAVE:
    import numpy as np
    from scipy import optimize, stats
try:
    from statsmodels.stats.contingency_tables import StratifiedTable
    from statsmodels.stats.meta_analysis import combine_effects
except ImportError:
    combine_effects = StratifiedTable = None
try:
    import matplotlib  # noqa: F401
    HAVE_MPL = True
except ImportError:
    HAVE_MPL = False

# vaccinated TB cases, vaccinated without TB, control cases, controls without TB
BCG = [("Aronson 1948", 4, 119, 11, 128), ("Ferguson 1949", 6, 300, 29, 274), ("Rosenthal 1960", 3, 228, 11, 209),
       ("Hart 1977", 62, 13536, 248, 12619), ("Frimodt-Moller 1973", 33, 5036, 47, 5761),
       ("Stein 1953", 180, 1361, 372, 1079), ("Vandiviere 1973", 8, 2537, 10, 619), ("TPT Madras 1980", 505, 87886, 499, 87892),
       ("Coetzee 1968", 29, 7470, 45, 7232), ("Rosenthal 1961", 17, 1699, 65, 1600), ("Comstock 1974", 186, 50448, 141, 27197),
       ("Comstock 1969", 5, 2493, 3, 2338), ("Comstock 1976", 27, 16886, 29, 17825)]
REML = {"tau2": 0.3132432628912972, "mu": -0.7145323425931489, "se": 0.17978151720378535}
HK_CI = (-1.1084437143376604, -0.3206209708486374)
PI_HK = (-2.0090576597653063, 0.5799929745790084)
FIELDS = ["study", "outcome", "timepoint", "arm", "n", "reported_as", "value", "spread", "events", "units", "locator"]


def events_rows(data, outcome="tb"):
    rows = []
    for study, a, b, c, d in data:
        rows += [{"study": study, "outcome": outcome, "arm": "treatment", "n": a + b, "reported_as": "events", "events": a,
                  "locator": "Table 1"},
                 {"study": study, "outcome": outcome, "arm": "control", "n": c + d, "reported_as": "events", "events": c,
                  "locator": "Table 1"}]
    return rows


def yi_rows(values, extra=None):
    return [dict({"study": f"S{i + 1}", "outcome": "score", "arm": "", "n": 60, "reported_as": "yi_se", "value": y,
                  "spread": math.sqrt(v), "units": "points", "locator": "p. 3"}, **(extra[i] if extra else {}))
            for i, (y, v) in enumerate(values)]


@unittest.skipUnless(HAVE, "numpy and scipy are not installed")
class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = os.getcwd()
        os.chdir(self.tmp.name)
        Path("meta-analysis").mkdir()

    def tearDown(self):
        os.chdir(self.old)
        self.tmp.cleanup()

    def table(self, rows, *options):
        columns = list(dict.fromkeys(FIELDS + [k for r in rows for k in r]))
        with open("meta-analysis/extraction.csv", "w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=columns)
            writer.writeheader()
            writer.writerows(rows)
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            return es.main(["meta-analysis/extraction.csv", *options])

    def pool(self, *options, plots=False):
        sys.modules.pop("rz_results", None)                   # each run is a new process in real use
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            code = mp.main(["meta-analysis/effects.csv", *([] if plots else ["--no-plots"]), *options])
        path = Path("meta-analysis/results.json")
        return code, json.loads(out.getvalue()), json.loads(path.read_text()) if path.exists() else None

    @staticmethod
    def get(content, rid):
        return next(r for r in content["results"] if r["id"] == rid)


class BcgTests(Base):
    def setUp(self):
        super().setUp()
        self.assertEqual(self.table(events_rows(BCG), "--measure", "RR"), 1)      # pooled event rate below 1 %
        self.assertEqual(self.table(events_rows(BCG), "--measure", "RR", "--sparse", "iv"), 0)
        code, self.summary, self.content = self.pool("--model", "random", "--tau2", "REML", "--ci", "HK")
        self.assertEqual(code, 0, self.summary)
        self.main = self.get(self.content, "tb")
        self.meta = self.main["extra"]["meta"]

    def test_reml_hartung_knapp_and_the_prediction_interval(self):
        self.assertAlmostEqual(self.meta["tau2"], REML["tau2"], places=7)
        self.assertAlmostEqual(self.meta["analysis_scale"]["estimate"], REML["mu"], places=7)
        self.assertAlmostEqual(self.meta["Q"], 152.2330080823734, places=8)
        self.assertAlmostEqual(self.meta["I2"], 92.11734685456207, places=8)
        self.assertEqual((self.meta["k"], self.main["df"], self.main["statistic"]["name"]), (13, 12, "t"))
        self.assertFalse(self.meta["hk_floor_applied"])                       # q = 1.0113
        self.assertAlmostEqual(self.main["interval"]["low"], math.exp(HK_CI[0]), places=7)
        self.assertAlmostEqual(self.main["interval"]["high"], math.exp(HK_CI[1]), places=7)
        self.assertAlmostEqual(self.main["estimate"]["value"], math.exp(REML["mu"]), places=7)
        self.assertEqual(self.main["estimate"]["units"], "ratio")
        self.assertAlmostEqual(self.meta["pi"]["low"], math.exp(PI_HK[0]), places=6)
        self.assertAlmostEqual(self.meta["pi"]["high"], math.exp(PI_HK[1]), places=6)
        self.assertEqual(self.main["n"], {"studies": 13, "participants": sum(a + b + c + d for _, a, b, c, d in BCG)})

    def test_reml_agrees_with_direct_maximisation(self):
        y = np.array([math.log((a / (a + b)) / (c / (c + d))) for _, a, b, c, d in BCG])
        v = np.array([1 / a - 1 / (a + b) + 1 / c - 1 / (c + d) for _, a, b, c, d in BCG])
        def minus_loglik(t2):
            w = 1 / (v + t2)
            mu = (w * y).sum() / w.sum()
            return 0.5 * (np.log(v + t2).sum() + np.log(w.sum()) + (w * (y - mu) ** 2).sum())
        direct = optimize.minimize_scalar(minus_loglik, bounds=(0, 10), method="bounded", options={"xatol": 1e-12}).x
        self.assertAlmostEqual(mp.tau2_estimate(y, v, "REML")[0], direct, places=7)

    def test_other_estimators_against_statsmodels(self):
        dl = self.get(self.content, "tb | tau2 by DL")["extra"]["meta"]
        pm = self.get(self.content, "tb | tau2 by PM")["extra"]["meta"]
        fixed = self.get(self.content, "tb | fixed-effect")["extra"]["meta"]
        self.assertAlmostEqual(dl["tau2"], 0.3087602628623764, places=9)
        self.assertAlmostEqual(pm["tau2"], 0.3180684522050242, places=8)
        self.assertAlmostEqual(fixed["analysis_scale"]["estimate"], -0.4302851636540906, places=9)
        if combine_effects is None:
            self.skipTest("statsmodels is not installed")
        y = np.array([math.log((a / (a + b)) / (c / (c + d))) for _, a, b, c, d in BCG])
        v = np.array([1 / a - 1 / (a + b) + 1 / c - 1 / (c + d) for _, a, b, c, d in BCG])
        self.assertAlmostEqual(dl["tau2"], combine_effects(y, v, method_re="dl").tau2, places=9)
        self.assertAlmostEqual(pm["tau2"], combine_effects(y, v, method_re="pm").tau2, places=8)

    def test_peters_test_runs_at_thirteen_studies(self):
        small = self.meta["small_study"]
        self.assertEqual((small["status"], small["test"], small["df"]), ("run", "Peters", 11))
        n = np.array([a + b + c + d for _, a, b, c, d in BCG], float)
        events = np.array([a + c for _, a, b, c, d in BCG], float)
        y = np.array([math.log((a / (a + b)) / (c / (c + d))) for _, a, b, c, d in BCG])
        w = events * (n - events) / n                                          # Peters' weights S F / N
        design = np.column_stack([np.ones(13), 1 / n]) * np.sqrt(w)[:, None]
        beta, residual, *_ = np.linalg.lstsq(design, y * np.sqrt(w), rcond=None)
        se = math.sqrt(residual[0] / 11 * np.linalg.inv(design.T @ design)[1, 1])
        self.assertAlmostEqual(small["slope"], beta[1], places=6)
        self.assertAlmostEqual(small["t"], beta[1] / se, places=6)

    def test_sensitivity_records_carry_no_p_and_the_file_checks(self):
        records = self.content["results"]
        self.assertEqual([r["id"] for r in records if r["p"] is not None], ["tb"])
        self.assertEqual(sum(1 for r in records if "leave out" in r["id"]), 13)
        self.assertTrue(all(r["role"] == "secondary" for r in records[1:]))
        cr = load("check_results", "check_results_on_pool")
        with redirect_stdout(io.StringIO()) as out, redirect_stderr(io.StringIO()):
            code = cr.main(["--dir", "meta-analysis"])
        checks = json.loads(out.getvalue())["checks"]
        self.assertEqual((code, checks["complete"], checks["families"], checks["ledger"], checks["hashes"]),
                         (0, "ok", "ok", "ok", "ok"))
        self.assertIn("Peters", Path("meta-analysis/pooled.md").read_text())


class HeterogeneityTests(Base):
    LOW = [(0.10, 0.04), (0.12, 0.05), (0.11, 0.06), (0.09, 0.05), (0.10, 0.04)]     # Q far below its df

    def test_dl_is_truncated_and_its_raw_value_kept(self):
        self.table(yi_rows(self.LOW), "--measure", "GENERIC")
        code, summary, content = self.pool("--tau2", "DL", "--ci", "HK")
        meta = self.get(content, "score")["extra"]["meta"]
        y, v = np.array([p[0] for p in self.LOW]), np.array([p[1] for p in self.LOW])
        w = 1 / v
        q = float((w * (y - (w * y).sum() / w.sum()) ** 2).sum())
        raw = (q - 4) / (w.sum() - (w ** 2).sum() / w.sum())
        self.assertEqual((meta["tau2"], meta["I2"]), (0.0, 0.0))
        self.assertAlmostEqual(meta["tau2_raw"], raw, places=12)
        self.assertAlmostEqual(meta["I2_raw"], (q - 4) / q * 100, places=10)
        self.assertLess(meta["I2_raw"], 0)
        if combine_effects is not None:                                        # statsmodels returns the raw value
            self.assertAlmostEqual(combine_effects(y, v, method_re="dl").tau2, raw, places=12)

    def test_hartung_knapp_floor(self):
        self.table(yi_rows(self.LOW), "--measure", "GENERIC")
        code, summary, content = self.pool()
        main, wald = self.get(content, "score"), self.get(content, "score | Wald interval")
        self.assertTrue(main["extra"]["meta"]["hk_floor_applied"])
        se_fixed = math.sqrt(1 / sum(1 / v for _, v in self.LOW))
        half = (main["interval"]["high"] - main["interval"]["low"]) / 2
        self.assertAlmostEqual(half, float(stats.t.ppf(0.975, 4)) * se_fixed, places=10)
        self.assertGreater(half, (wald["interval"]["high"] - wald["interval"]["low"]) / 2)

    def test_closed_forms_for_three_studies(self):
        y, v = np.array([0.2, 0.5, 0.9]), np.array([0.04, 0.09, 0.0625])
        w = 1 / v
        mu = (w * y).sum() / w.sum()
        q = (w * (y - mu) ** 2).sum()
        dl = (q - 2) / (w.sum() - (w ** 2).sum() / w.sum())
        self.assertAlmostEqual(mp.tau2_estimate(y, v, "DL")[0], dl, places=12)
        res = mp.inverse_variance(y, v, "random", "DL", "Wald", 0.95)
        ws = 1 / (v + dl)
        mu_re, se_re = (ws * y).sum() / ws.sum(), math.sqrt(1 / ws.sum())
        self.assertAlmostEqual(res["mu"], mu_re, places=12)
        self.assertAlmostEqual(res["low"], mu_re - float(stats.norm.ppf(0.975)) * se_re, places=12)
        half = float(stats.t.ppf(0.975, 1)) * math.sqrt(dl + se_re ** 2)      # t on k - 2 = 1 df
        self.assertAlmostEqual(res["pi"][1], mu_re + half, places=12)
        pm = mp.tau2_estimate(y, v, "PM")[0]
        wp = 1 / (v + pm)
        self.assertAlmostEqual(float((wp * (y - (wp * y).sum() / wp.sum()) ** 2).sum()), 2.0, places=9)

    def test_reml_that_does_not_converge_falls_back_to_paule_mandel(self):
        original = mp.tau2_estimate
        mp.tau2_estimate = lambda y, v, method: (0.5, 0.5, False) if method == "REML" else original(y, v, method)
        try:
            res = mp.inverse_variance(np.array([0.2, 0.5, 0.9]), np.array([0.04, 0.09, 0.0625]), "random", "REML", "HK", 0.95)
        finally:
            mp.tau2_estimate = original
        self.assertEqual((res["tau2_method"], res["tau2_method_planned"], res["tau2_converged"]), ("PM", "REML", False))
        self.assertIn("did not converge", res["notes"][0])


class RuleTests(Base):
    def test_two_studies_have_no_prediction_interval_or_leave_one_out(self):
        self.table(yi_rows([(0.2, 0.04), (0.6, 0.05)]), "--measure", "GENERIC")
        code, summary, content = self.pool()
        meta = self.get(content, "score")["extra"]["meta"]
        self.assertIsNone(meta["pi"])
        self.assertIn("k = 2", meta["pi_reason"])
        self.assertFalse(any("leave out" in r["id"] for r in content["results"]))

    def test_small_study_test_only_from_ten_studies(self):
        values = [(0.10 + 0.05 * i, 0.01 + 0.012 * i) for i in range(10)]
        self.table(yi_rows(values[:6]), "--measure", "GENERIC")
        meta = self.get(self.pool()[2], "score")["extra"]["meta"]
        self.assertEqual(meta["small_study"], {"status": "not run", "reason": "k = 6, fewer than 10 studies (a convention)"})
        self.table(yi_rows(values), "--measure", "GENERIC")
        small = self.get(self.pool()[2], "score")["extra"]["meta"]["small_study"]
        y, se = np.array([p[0] for p in values]), np.sqrt([p[1] for p in values])
        design = np.column_stack([np.ones(10), 1 / se])                       # Egger: y/SE on 1/SE, the intercept
        beta, residual, *_ = np.linalg.lstsq(design, y / se, rcond=None)
        se_b0 = math.sqrt(residual[0] / 8 * np.linalg.inv(design.T @ design)[0, 0])
        self.assertEqual((small["status"], small["test"]), ("run", "Egger"))
        self.assertAlmostEqual(small["slope"], beta[0], places=8)
        self.assertAlmostEqual(small["t"], beta[0] / se_b0, places=8)
        self.assertAlmostEqual(small["p"], 2 * stats.t.sf(abs(beta[0] / se_b0), 8), places=8)

    def test_smd_uses_the_modified_se_and_z_returns_to_r(self):
        rows = []
        for i in range(10):
            n1, n2 = 15 + 9 * i, 16 + 7 * i
            rows += [{"study": f"S{i + 1}", "outcome": "pain", "arm": "treatment", "n": n1, "reported_as": "mean_sd",
                      "value": 4.0 - 0.1 * i, "spread": 2.0 + 0.05 * i, "locator": "Table 2"},
                     {"study": f"S{i + 1}", "outcome": "pain", "arm": "control", "n": n2, "reported_as": "mean_sd",
                      "value": 5.0, "spread": 2.1, "locator": "Table 2"}]
        self.table(rows, "--measure", "SMD")
        small = self.get(self.pool()[2], "pain")["extra"]["meta"]["small_study"]
        effects = list(csv.DictReader(io.StringIO(Path("meta-analysis/effects.csv").read_text(encoding="utf-8"))))
        y = np.array([float(e["yi"]) for e in effects])
        x = np.sqrt(1 / np.array([float(e["n1"]) for e in effects]) + 1 / np.array([float(e["n2"]) for e in effects]))
        design = np.column_stack([np.ones(10), x]) / x[:, None]               # weights 1/x^2
        beta, *_ = np.linalg.lstsq(design, y / x, rcond=None)
        self.assertEqual(small["test"], "Egger with the modified SE sqrt(1/n1 + 1/n2)")
        self.assertAlmostEqual(small["slope"], beta[1], places=8)
        rows = [{"study": f"S{i}", "outcome": "link", "arm": "", "n": n, "reported_as": "r", "value": r, "locator": "p. 2"}
                for i, (r, n) in enumerate(((0.30, 50), (0.45, 80), (0.25, 120)))]
        self.table(rows, "--measure", "Z")
        main = self.get(self.pool("--ci", "Wald")[2], "link")
        self.assertAlmostEqual(main["estimate"]["value"], math.tanh(main["extra"]["meta"]["analysis_scale"]["estimate"]))
        self.assertEqual(main["estimate"]["units"], "unitless")

    def test_subgroups_are_tested_only_with_four_studies_each(self):
        values = [(0.1, 0.02), (0.2, 0.03), (0.15, 0.025), (0.05, 0.02), (0.5, 0.03), (0.6, 0.02), (0.45, 0.04), (0.55, 0.03)]
        groups = [{"dose": "low"}] * 4 + [{"dose": "high"}] * 4
        self.table(yi_rows(values, groups), "--measure", "GENERIC")
        code, summary, content = self.pool("--model", "fixed", "--subgroup", "dose")
        test = self.get(content, "score")["extra"]["meta"]["subgroups"][0]["test"]
        mus, ws = [], []
        for part in (values[:4], values[4:]):
            w = np.array([1 / v for _, v in part])
            mus.append(float((w * np.array([y for y, _ in part])).sum() / w.sum()))
            ws.append(float(w.sum()))
        mus, ws = np.array(mus), np.array(ws)
        q_between = float((ws * (mus - (ws * mus).sum() / ws.sum()) ** 2).sum())
        self.assertEqual((test["status"], test["df"]), ("run", 1))
        self.assertAlmostEqual(test["Q_between"], q_between, places=10)
        self.assertEqual(self.get(content, "score | dose = low")["p"], None)
        groups = [{"dose": "low"}] * 3 + [{"dose": "high"}] * 5
        self.table(yi_rows(values, groups), "--measure", "GENERIC")
        test = self.get(self.pool("--subgroup", "dose")[2], "score")["extra"]["meta"]["subgroups"][0]["test"]
        self.assertEqual(test["status"], "not run")
        self.assertIn("low (3)", test["reason"])

    def test_mantel_haenszel_and_peto(self):
        data = [("A", 0, 50, 4, 46), ("B", 6, 54, 11, 49), ("C", 3, 97, 8, 92), ("D", 10, 140, 17, 133)]
        self.table(events_rows(data), "--measure", "OR", "--sparse", "mh")
        code, summary, content = self.pool("--model", "random")
        main = self.get(content, "tb")
        meta = main["extra"]["meta"]
        self.assertEqual((meta["model"], meta["method"], main["statistic"]["name"]), ("fixed", "Mantel-Haenszel", "z"))
        self.assertIn("fixed-effect method", " ".join(meta["notes"]))
        self.assertIn("fixed-effect model", meta["pi_reason"])
        a, b, c, d = (np.array([row[i] for row in data], float) for i in (1, 2, 3, 4))
        n = a + b + c + d
        self.assertAlmostEqual(main["estimate"]["value"], (a * d / n).sum() / (b * c / n).sum(), places=10)
        o_e, var = a - (a + b) * (a + c) / n, (a + b) * (c + d) * (a + c) * (b + d) / (n ** 2 * (n - 1))
        peto = self.get(content, "tb | Peto")
        self.assertAlmostEqual(peto["estimate"]["value"], math.exp(o_e.sum() / var.sum()), places=10)
        self.assertAlmostEqual(peto["extra"]["meta"]["Q"], (o_e ** 2 / var).sum() - o_e.sum() ** 2 / var.sum(), places=10)
        if StratifiedTable is None:
            self.skipTest("statsmodels is not installed")
        table = StratifiedTable([np.array([[x[1], x[2]], [x[3], x[4]]]) for x in data])
        self.assertAlmostEqual(main["estimate"]["value"], table.oddsratio_pooled, places=10)
        z = float(stats.norm.ppf(0.975))
        self.assertAlmostEqual(main["interval"]["low"], math.exp(table.logodds_pooled - z * table.logodds_pooled_se), places=10)


class InputTests(Base):
    def test_refused_effects_are_not_pooled(self):
        rows = yi_rows([(0.2, 0.04), (0.6, 0.05)]) + yi_rows([(0.3, 0.04)])          # S1 twice in one pool
        self.assertEqual(self.table(rows, "--measure", "GENERIC"), 1)
        code, summary, content = self.pool()
        self.assertEqual((code, summary["status"], content), (1, "refused", None))

    def test_wrong_files_and_columns(self):
        self.table(yi_rows([(0.2, 0.04), (0.6, 0.05), (0.4, 0.03)]), "--measure", "GENERIC")
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(mp.main(["meta-analysis/extraction.csv"]), 2)          # not an effects.csv
            with self.assertRaises(SystemExit) as caught:
                mp.main(["meta-analysis/effects.csv", "--subgroup", "dose"])
        self.assertEqual(caught.exception.code, 2)

    def test_plots(self):
        self.table(yi_rows([(0.2, 0.04), (0.6, 0.05), (0.4, 0.03)]), "--measure", "GENERIC")
        self.assertEqual(self.pool()[1]["plots"], "not drawn: --no-plots")
        if not HAVE_MPL:
            self.skipTest("matplotlib is not installed")
        drawn = self.pool(plots=True)[1]["plots"]
        self.assertEqual(sorted(Path(p).name for p in drawn), sorted(f"{kind}-score.{ext}" for kind in ("forest", "funnel")
                                                                        for ext in ("pdf", "png", "svg")))
        self.assertTrue(all(Path(p).stat().st_size > 0 for p in drawn))


class MissingPackageTests(unittest.TestCase):
    def test_without_numpy_or_scipy_nothing_runs(self):
        saved, mp.np = mp.np, None
        try:
            out = io.StringIO()
            with redirect_stdout(out):
                code = mp.main(["effects.csv"])
        finally:
            mp.np = saved
        self.assertEqual((code, json.loads(out.getvalue())["status"]), (2, "not_run"))


if __name__ == "__main__":
    unittest.main()
