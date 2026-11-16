"""rz_results.py: what record() refuses, what the files hold, adjust(), correct() and finish()."""
from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts" / "rz_results.py"


def fresh():
    """A new copy of the module, as a new analysis process would have."""
    spec = importlib.util.spec_from_file_location("rz_results_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def full(**fields) -> dict:
    base = {"id": "t1", "question": "Does the drug shorten latency?", "family": "primary", "role": "primary",
            "test": "paired t test", "unit": "subject", "n": {"pairs": 11},
            "estimate": {"name": "mean difference", "value": -9.1, "units": "min"},
            "interval": {"low": -10.8, "high": -7.4, "level": 0.95}, "statistic": {"name": "t", "value": -11.6},
            "df": 10, "p": 0.0000004, "effect_size": {"name": "d_z", "value": -3.5, "low": -5.1, "high": -1.9, "level": 0.95}}
    base.update(fields)
    return base


class AdjustTests(unittest.TestCase):
    P = [0.01, 0.04, 0.03, 0.005]

    def test_hand_computed_values(self):
        rz = fresh()
        close = lambda a, b: [self.assertAlmostEqual(x, y, places=12) for x, y in zip(a, b)]  # noqa: E731
        close(rz.adjust(self.P, "bonferroni"), [0.04, 0.16, 0.12, 0.02])
        close(rz.adjust(self.P, "holm"), [0.03, 0.06, 0.06, 0.02])
        close(rz.adjust(self.P, "bh"), [0.02, 0.04, 0.04, 0.02])
        c = 1 + 1 / 2 + 1 / 3 + 1 / 4
        close(rz.adjust(self.P, "by"), [0.02 * c, 0.04 * c, 0.04 * c, 0.02 * c])
        self.assertEqual(rz.adjust([0.9, 0.8], "bonferroni"), [1.0, 1.0])
        with self.assertRaises(ValueError):
            rz.adjust(self.P, "sidak-ish")
        with self.assertRaises(ValueError):
            rz.adjust([1.2], "holm")

    def test_against_statsmodels(self):
        try:
            from statsmodels.stats.multitest import multipletests
        except ImportError:
            self.skipTest("statsmodels is not installed")
        rz = fresh()
        p = [0.001, 0.008, 0.039, 0.041, 0.042, 0.06, 0.074, 0.205, 0.212, 0.216]
        for ours, theirs in (("bonferroni", "bonferroni"), ("holm", "holm"), ("bh", "fdr_bh"), ("by", "fdr_by")):
            expected = multipletests(p, method=theirs)[1]
            for x, y in zip(rz.adjust(p, ours), expected):
                self.assertAlmostEqual(x, y, places=12, msg=ours)


class RecordTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = os.getcwd()
        os.chdir(self.tmp.name)
        self.rz = fresh()

    def tearDown(self):
        os.chdir(self.old)
        self.tmp.cleanup()

    def refused(self, message: str, **fields):
        with self.assertRaises(ValueError) as caught:
            self.rz.record(**full(**fields))
        self.assertIn(message, str(caught.exception))

    def test_refusals(self):
        self.refused("unit of analysis is missing", unit="")
        self.refused("unit of analysis is missing", unit="rows")
        self.refused("estimate must be", estimate=None)
        self.refused("estimate must be", estimate={"name": "mean difference", "value": -9.1})
        self.refused("not recorded without the interval", interval=None)
        self.refused("needs an effect size", effect_size=None)
        self.refused("low and high, or no_interval", effect_size={"name": "d_z", "value": -3.5})
        self.refused("exact p-value", p="<0.001")
        self.refused("role must be", role="main")
        self.refused("n must be a whole number", n={"pairs": 11.5})
        self.refused("needs reason=", kept=False)
        self.refused("extra must be a dict", extra=[0.04])

    def test_extra_fields_are_kept_only_when_given(self):
        self.rz.record(**full(id="a"))
        self.rz.record(**full(id="b", extra={"tau2": 0.04, "pi": {"low": -0.9, "high": 0.1}}))
        results = json.loads(Path("statistics/results.json").read_text())["results"]
        self.assertNotIn("extra", results[0])
        self.assertEqual(results[1]["extra"], {"tau2": 0.04, "pi": {"low": -0.9, "high": 0.1}})

    def test_reasons_instead_of_an_effect_size_or_its_interval(self):
        self.rz.record(**full(id="a", effect_size=None, no_effect_size="the omnibus test has no single effect"))
        self.rz.record(**full(id="b", effect_size={"name": "rank-biserial r", "value": 0.4, "no_interval": "too few pairs"}))
        self.rz.record(**full(id="c", effect_size="estimate"))
        self.rz.record(**full(id="d", p=None, interval=None, effect_size=None))     # a description, no test
        self.assertEqual(len(json.loads(Path("statistics/results.json").read_text())["results"]), 4)
        self.refused("already recorded", id="a")

    def test_kept_and_dropped_lines_and_corrections(self):
        self.rz.record(**full(id="ab", family="pairwise", role="secondary", p=0.01))
        self.rz.record(**full(id="ac", family="pairwise", role="secondary", p=0.04))
        self.rz.record(**full(id="bc", family="pairwise", role="secondary", p=0.03, kept=False,
                              reason="planned, but the table was cut"))
        family = self.rz.correct("pairwise", "holm")
        self.assertEqual(family["m"], 3)                         # the dropped test still counts
        content = json.loads(Path("statistics/results.json").read_text())
        self.assertEqual([r["id"] for r in content["results"]], ["ab", "ac"])
        self.assertAlmostEqual(content["results"][0]["p_adjusted"], 0.03)
        self.assertAlmostEqual(content["results"][1]["p_adjusted"], 0.06)
        lines = [json.loads(x) for x in Path("statistics/ledger.jsonl").read_text().splitlines()]
        self.assertEqual([x.get("status") for x in lines], ["kept", "kept", "dropped", None])
        self.assertEqual(lines[2]["reason"], "planned, but the table was cut")
        self.assertLessEqual({"estimate", "interval", "n", "p"}, set(lines[2]))     # a dropped test keeps its numbers
        self.assertNotIn("extra", lines[2])
        with self.assertRaises(ValueError):
            self.rz.record(**full(id="late", family="pairwise"))
        self.rz.record(**full(id="t1", family="tukey", p=0.02))
        self.rz.record(**full(id="t2", family="tukey", p=0.2))
        with self.assertRaises(ValueError):
            self.rz.correct("tukey", "tukey", adjusted={"t1": 0.04})
        self.rz.correct("tukey", "Tukey HSD", adjusted={"t1": 0.04, "t2": 0.33})
        self.assertEqual(json.loads(Path("statistics/results.json").read_text())["families"]["tukey"]["adjusted_by"],
                         "the test procedure")

    def test_numpy_values_become_plain_json(self):
        try:
            import numpy as np
        except ImportError:
            self.skipTest("numpy is not installed")
        entry = self.rz.record(**full(n={"pairs": np.int64(11)}, p=np.float64(0.003),
                                      estimate={"name": "mean difference", "value": np.float64(-9.1), "units": "min"}))
        self.assertIs(type(entry["p"]), float)
        self.assertIs(type(entry["n"]["pairs"]), int)

    def test_finish_binds_the_script_and_the_data(self):
        Path("data.csv").write_text("subject,y\nS1,1\n", encoding="utf-8")
        Path("analysis.py").write_text("print('analysis')\n", encoding="utf-8")
        self.rz.record(**full(id="x1", family="f", p=0.01))
        self.rz.record(**full(id="x2", family="f", p=0.02))
        out = io.StringIO()
        with redirect_stdout(out):
            summary = self.rz.finish(script="analysis.py", data=["data.csv"], seed=20261112, settings={"alpha": 0.05})
        self.assertEqual(summary["families_without_correction"], ["f"])
        record = json.loads(Path("statistics/results.json").read_text())["record"]
        self.assertEqual(record["data"][0], {"path": "data.csv", "bytes": 15,
                                             "sha256": hashlib.sha256(b"subject,y\nS1,1\n").hexdigest()})
        self.assertEqual(record["script"]["path"], "analysis.py")
        self.assertEqual((record["seed"], record["settings"]), (20261112, {"alpha": 0.05}))
        self.assertIn("python", record)
        self.assertIn("rz_results", record["packages"])
        with self.assertRaises(ValueError):
            self.rz.record(**full(id="after"))
        rz2 = fresh()                                             # a second run of the script
        with self.assertRaises(ValueError):
            rz2.finish(script="analysis.py", data="data.csv")
        rz2.record(**full(id="x1"))
        self.assertEqual(json.loads(Path("statistics/results.json").read_text())["run"], 2)
        self.assertEqual(len(json.loads(Path("statistics/results.json").read_text())["results"]), 1)
        self.assertEqual(len(Path("statistics/ledger.jsonl").read_text().splitlines()), 4)   # x1, x2, finish; x1


if __name__ == "__main__":
    unittest.main()
