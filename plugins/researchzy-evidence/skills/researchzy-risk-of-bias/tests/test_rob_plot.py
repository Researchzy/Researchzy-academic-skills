"""rob_plot.py: every judgement has a colour and a symbol, no information is its own state, and
nothing is drawn from failing assessments or without matplotlib."""
from __future__ import annotations

import copy
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

HERE = Path(__file__).parent


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


rp = load("rob_plot", HERE.parent / "scripts" / "rob_plot.py")
fx = load("review_fixture", HERE / "review_fixture.py")
try:
    import matplotlib  # noqa: F401
    HAVE_MATPLOTLIB = True
except ImportError:
    HAVE_MATPLOTLIB = False


class PlotTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def plot(self, *argv, assessments=None) -> tuple:
        base = fx.build(self.dir, assessments=assessments)
        out = io.StringIO()
        with redirect_stdout(out):
            code = rp.main(["--dir", str(base), *argv])
        return code, json.loads(out.getvalue()), base

    def test_each_judgement_has_its_own_colour_and_symbol(self):
        style = rp.styles(rp.rc.prepare(fx.TOOL))
        self.assertEqual(style["ni"], rp.NO_INFORMATION)
        self.assertEqual([style[j][1] for j in ("low", "some", "high", "ni")], ["+", "−", "x", "?"])
        self.assertEqual(len({style[j][0] for j in style}), 4)
        self.assertEqual(len({style[j][2] for j in style}), 4)               # the bars' hatching differs too
        four = dict(fx.TOOL, judgements=[{"id": c} for c in "abcd"])
        self.assertEqual(rp.ink(rp.styles(rp.rc.prepare(four))["d"][0]), "white")   # the worst of four is black
        six = dict(fx.TOOL, judgements=[{"id": c} for c in "abcdef"])
        self.assertIsNone(rp.styles(rp.rc.prepare(six)))

    def test_without_matplotlib_nothing_is_drawn_and_the_summary_says_so(self):
        with mock.patch.dict(sys.modules, {"matplotlib": None, "matplotlib.pyplot": None, "matplotlib.patches": None}):
            code, summary, base = self.plot()
        self.assertEqual((code, summary["drawn"], summary["matplotlib"]), (0, [], "not installed"))
        self.assertEqual(summary["message"], "no plot drawn: matplotlib is not installed")
        self.assertFalse(list(base.glob("traffic-light-*")))

    def test_failing_assessments_are_not_drawn(self):
        assessments = copy.deepcopy(fx.ASSESSMENTS)
        assessments["assessments"][0]["results"][0]["domains"]["D1"]["support"] = []
        assessments["assessments"][0]["results"][0]["domains"]["D1"]["judgement"] = "low"
        code, summary, _ = self.plot(assessments=assessments)
        self.assertEqual((code, summary["drawn"], summary["failures"]), (1, [], 1))

    @unittest.skipUnless(HAVE_MATPLOTLIB, "matplotlib is not installed")
    def test_both_plots_are_drawn_in_three_formats(self):
        code, summary, base = self.plot("--weighted")
        self.assertEqual(code, 0)
        self.assertEqual(sorted(Path(p).name for p in summary["drawn"]), sorted(
            f"{kind}-demo-weight.{ext}" for kind in ("traffic-light", "summary") for ext in ("pdf", "png", "svg")))
        self.assertEqual((base / "summary-demo-weight.png").read_bytes()[:8], b"\x89PNG\r\n\x1a\n")
        self.assertTrue((base / "traffic-light-demo-weight.pdf").read_bytes().startswith(b"%PDF"))
        self.assertIn("No information", (base / "traffic-light-demo-weight.svg").read_text(encoding="utf-8"))
        self.assertEqual(summary["notes"], [])

        assessments = copy.deepcopy(fx.ASSESSMENTS)
        del assessments["assessments"][1]["results"][0]["weight"]
        code, summary, _ = self.plot("--weighted", "--formats", "png", assessments=assessments)
        self.assertEqual((code, len(summary["drawn"])), (0, 2))
        self.assertEqual(summary["notes"], ["demo / weight: not every result has a positive weight; summary unweighted"])


if __name__ == "__main__":
    unittest.main()
