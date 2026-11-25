"""psy_tools.py: alpha and its intervals, item statistics, parallel analysis, EFA, omega/CR/AVE, HTMT, SRMR, CFA."""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).parents[1] / "scripts" / "psy_tools.py"


def available(*names) -> bool:
    return all(importlib.util.find_spec(name) is not None for name in names)


BASE = available("numpy", "pandas", "scipy")
if BASE:
    import numpy as np
    import pandas as pd
    spec = importlib.util.spec_from_file_location("psy_tools", SCRIPT)
    pt = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pt)


def three_factors_and_a_pair(seed=4, n=400):
    """Three factors of four items (loading .7) and two items that correlate about .2 with each other only."""
    rng = np.random.default_rng(seed)
    f = rng.standard_normal((n, 3))
    cols = {f"f{k}i{j}": 0.7 * f[:, k] + np.sqrt(0.51) * rng.standard_normal(n) for k in range(3) for j in range(4)}
    z = rng.standard_normal(n)
    cols.update({f"pair{j}": np.sqrt(0.2) * z + np.sqrt(0.8) * rng.standard_normal(n) for j in range(2)})
    return pd.DataFrame(cols)


@unittest.skipUnless(BASE, "numpy, pandas or scipy is not installed")
class ReliabilityTests(unittest.TestCase):
    def setUp(self):
        self.items = pd.DataFrame({"a": [1, 2, 3, 4, 5, 2, 3, 4], "b": [2, 2, 3, 5, 4, 1, 3, 5],
                                   "c": [1, 3, 2, 4, 5, 2, 2, 4]}, dtype=float)

    def test_alpha_and_feldt_interval(self):
        x = self.items.to_numpy()
        expected = 3 / 2 * (1 - x.var(axis=0, ddof=1).sum() / x.sum(axis=1).var(ddof=1))
        a = pt.alpha(self.items)
        self.assertAlmostEqual(a["alpha"], expected, places=12)
        self.assertEqual((a["ci"], a["n"], a["k"], a["level"]), ("feldt", 8, 3, 0.95))
        from scipy import stats
        self.assertAlmostEqual(a["low"], 1 - (1 - expected) * stats.f.ppf(0.975, 7, 14), places=12)
        self.assertLess(a["low"], a["alpha"])
        self.assertLess(a["alpha"], a["high"])
        if available("pingouin"):
            import pingouin
            value, (low, high) = pingouin.cronbach_alpha(self.items)
            self.assertAlmostEqual(a["alpha"], value, places=6)
            self.assertAlmostEqual(a["low"], low, places=3)
            self.assertAlmostEqual(a["high"], high, places=3)

    def test_a_bootstrap_interval_is_seeded_and_recorded(self):
        first, second = (pt.alpha(self.items, ci="bootstrap", seed=11, n_boot=300) for _ in range(2))
        self.assertEqual(first, second)
        self.assertEqual((first["seed"], first["n_boot"], first["interval"]), (11, 300, "percentile"))
        with self.assertRaises(ValueError):
            pt.alpha(self.items, ci="bootstrap")

    def test_item_statistics(self):
        frame = self.items.copy()
        frame.loc[8] = [np.nan, 1, 1]                                  # dropped listwise
        out = pt.item_stats(frame, scale_min=1, scale_max=5)
        self.assertEqual(out["n"], 8)
        x = self.items.to_numpy()
        a = out["items"]["a"]
        self.assertAlmostEqual(a["item_rest_r"], np.corrcoef(x[:, 0], x[:, 1] + x[:, 2])[0, 1], places=12)
        self.assertAlmostEqual(a["alpha_if_deleted"], pt.alpha(self.items[["b", "c"]])["alpha"], places=12)
        self.assertEqual((a["floor"], a["ceiling"], a["categories_used"]), (0.125, 0.125, 5))

    def test_omega_cr_and_ave(self):
        out = pt.omega_cr_ave({"x": 0.7, "y": 0.8, "z": 0.6}, {"x": 0.51, "y": 0.36, "z": 0.64})
        self.assertAlmostEqual(out["cr"], 2.1 ** 2 / (2.1 ** 2 + 1.51), places=12)
        self.assertAlmostEqual(out["omega"], out["cr"], places=12)            # theta = 1 - loading^2
        self.assertAlmostEqual(out["ave"], (0.49 + 0.64 + 0.36) / 3, places=12)
        for loadings, errors, problem in (([0.7, 1.02, 0.6], [0.51, -0.04, 0.64], "Heywood"),
                                          ([0.7, -0.5, 0.6], [0.51, 0.75, 0.64], "negative loading"), ([0.7], [0.51], "two")):
            out = pt.omega_cr_ave(loadings, errors)
            self.assertEqual((out["omega"], out["cr"], out["ave"]), (None, None, None))
            self.assertIn(problem, " ".join(out["problems"]))

    def test_htmt_by_hand(self):
        names = ["a1", "a2", "b1", "b2"]
        corr = pd.DataFrame([[1, .6, .3, .2], [.6, 1, .4, .3], [.3, .4, 1, .5], [.2, .3, .5, 1]], index=names, columns=names)
        with tempfile.TemporaryDirectory() as folder:
            out = pt.htmt(corr, {"A": ["a1", "a2"], "B": ["b1", "b2"]}, matrices=Path(folder) / "htmt.json")
            saved = json.loads(Path(out["matrices"]["path"]).read_text())
        self.assertAlmostEqual(out["matrix"]["A"]["B"], 0.3 / np.sqrt(0.6 * 0.5), places=12)
        self.assertEqual(saved["items"], names)

    def test_harman_and_marker_adjustment(self):
        h = pt.harman(self.items)
        self.assertAlmostEqual(h["share"], np.linalg.eigvalsh(self.items.corr().to_numpy())[-1] / 3, places=12)
        corr = pd.DataFrame([[1, .5, .1], [.5, 1, .15], [.1, .15, 1]], index=["X", "Y", "M"], columns=["X", "Y", "M"])
        m = pt.marker_adjust(corr, "M")
        self.assertEqual(m["r_m"], 0.1)
        self.assertAlmostEqual(m["adjusted"]["X"]["Y"], (0.5 - 0.1) / 0.9, places=12)

    def test_cfa_syntax_from_the_item_map(self):
        spec = {"constructs": {"AUT": {"items": ["aut1", "aut2", "aut3"]}, "MEA": {"items": ["mea1", "mea2", "mea3"]}}}
        self.assertEqual(pt.cfa_syntax(spec), "AUT =~ aut1 + aut2 + aut3\nMEA =~ mea1 + mea2 + mea3")
        with self.assertRaises(ValueError):
            pt.cfa_syntax({"constructs": {"自主 性": {"items": ["a", "b", "c"]}}})


@unittest.skipUnless(BASE, "numpy, pandas or scipy is not installed")
class FactorTests(unittest.TestCase):
    def test_parallel_analysis_3_against_kaiser_4_with_its_settings(self):
        data = three_factors_and_a_pair()
        pa = pt.parallel_analysis(data, n_sets=200, percentile=95, seed=7)
        self.assertEqual((pa["suggested"], pa["kaiser"]["count"]), (3, 4))
        self.assertEqual({k: pa[k] for k in ("n_sets", "percentile", "seed", "eigen", "criterion", "data", "n", "p")},
                         {"n_sets": 200, "percentile": 95, "seed": 7, "eigen": "pca", "criterion": "percentile",
                          "data": "normal", "n": 400, "p": 14})
        self.assertEqual(pa, pt.parallel_analysis(data, n_sets=200, percentile=95, seed=7))      # repeatable
        self.assertEqual(pt.parallel_analysis(data, n_sets=50, seed=7, kind="fa")["eigen"], "fa")
        with self.assertRaises(ValueError):
            pt.parallel_analysis(data)

    @unittest.skipUnless(available("statsmodels"), "statsmodels is not installed")
    def test_efa_loadings_signs_and_factor_correlations(self):
        data = three_factors_and_a_pair().iloc[:, :12]
        out = pt.efa(data, n_factors=3, method="pa", rotation="oblimin")
        loadings = pd.DataFrame(out["loadings"]).T
        self.assertEqual(loadings.shape, (12, 3))
        self.assertTrue((loadings.max(axis=1) > 0.55).all())               # every item loads on its factor
        self.assertTrue((loadings.sum() > 0).all())                         # signs made positive
        phi = pd.DataFrame(out["factor_corr"]).to_numpy()
        self.assertTrue(np.allclose(np.diag(phi), 1) and np.allclose(phi, phi.T))
        self.assertEqual((out["correlation"], out["rotation"], out["n"]), ("pearson", "oblimin", 400))


@unittest.skipUnless(BASE and available("semopy"), "numpy, pandas, scipy or semopy is not installed")
class CfaTests(unittest.TestCase):
    """The three-factor Holzinger-Swineford model, whose fit lavaan reports as chi2 85.306 on 24 df,
    CFI .931, TLI .896, RMSEA .092 and SRMR .065."""

    def test_holzinger_swineford(self):
        import semopy
        data = semopy.examples.holzinger39.get_data()
        syntax = "visual =~ x1 + x2 + x3\ntextual =~ x4 + x5 + x6\nspeed =~ x7 + x8 + x9"
        with tempfile.TemporaryDirectory() as folder:
            out = pt.cfa_semopy(data, syntax, matrices=Path(folder) / "cfa.json")
            saved = json.loads(Path(out["matrices"]["path"]).read_text())
        fit = out["fit"]
        self.assertEqual((out["converged"], out["df"], out["n"], out["n_free"], out["heywood"]), (True, 24, 301, 21, []))
        for key, value, places in (("chi2", 85.306, 3), ("cfi", 0.931, 3), ("tli", 0.896, 3), ("rmsea", 0.092, 3),
                                   ("srmr", 0.0652, 4)):
            self.assertAlmostEqual(fit[key], value, places=places, msg=key)
        self.assertAlmostEqual(pt.srmr(saved["sample_cov"], saved["implied_cov"])["srmr"], fit["srmr"], places=12)
        self.assertAlmostEqual(out["loadings"]["textual"]["x5"], 0.855, places=3)
        self.assertNotIn("visual", out["factor_corr"].get("visual", {}))
        v = pt.validity(out)
        self.assertAlmostEqual(v["ave"]["visual"], np.mean([x ** 2 for x in out["loadings"]["visual"].values()]), places=12)


@unittest.skipUnless(BASE, "numpy, pandas or scipy is not installed")
class MissingPackageTests(unittest.TestCase):
    def test_without_semopy_the_cfa_is_not_checked(self):
        with mock.patch.dict(sys.modules, {"semopy": None}):
            out = pt.cfa_semopy(None, "F =~ a + b + c")
        self.assertEqual(out["status"], "not_checked")
        self.assertIn("semopy is not installed", out["reason"])


if __name__ == "__main__":
    unittest.main()
