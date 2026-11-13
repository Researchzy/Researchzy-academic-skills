"""rz_figure.py: style, size, axis audit and export, and the checker on what it exports.

Everything here draws with matplotlib; without it the whole file is skipped.
"""
from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import struct
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

SCRIPTS = Path(__file__).parents[1] / "scripts"

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    HAVE_MATPLOTLIB = True
except ImportError:
    HAVE_MATPLOTLIB = False


def load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cf = load("check_figure")
rz = load("rz_figure") if HAVE_MATPLOTLIB else None


@unittest.skipUnless(HAVE_MATPLOTLIB, "matplotlib is not installed")
class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.out = self.dir / "figures"
        self.data = self.dir / "data.csv"
        self.data.write_text("group,value\ncontrol,52\ntreated,58\n", encoding="utf-8")
        matplotlib.rcdefaults()
        rz.apply_style()

    def tearDown(self):
        plt.close("all")
        matplotlib.rcdefaults()
        self.tmp.cleanup()

    def panel(self, width_mm: float = 89, height_mm: float = 60):
        return plt.subplots(figsize=rz.figsize_mm(width_mm, height_mm))

    def rules(self, fig) -> list:
        return [finding["rule"] for finding in rz.audit_axes(fig)]

    def save(self, fig, name: str = "fig", **options) -> dict:
        return rz.save(fig, name, data=[self.data], out=str(self.out), quiet=True, **options)

    def check(self, *argv) -> tuple:
        out = io.StringIO()
        with redirect_stdout(out):
            code = cf.main([str(a) for a in argv])
        result = json.loads(out.getvalue())
        return code, [{c["check"]: c for c in f["checks"]} for f in result["files"]]


class StyleTests(Base):
    def test_size_in_millimetres(self):
        width, height = rz.figsize_mm(89, 60)
        self.assertAlmostEqual(width, 89 / 25.4)
        self.assertAlmostEqual(height, 60 / 25.4)
        with self.assertRaises(ValueError):
            rz.figsize_mm(0, 60)

    def test_style_is_set_for_print(self):
        report = rz.apply_style()
        rc = matplotlib.rcParams
        self.assertEqual((rc["pdf.fonttype"], rc["font.family"], rc["font.sans-serif"][0]), (42, ["sans-serif"], "Arial"))
        self.assertEqual((rc["font.size"], rc["xtick.labelsize"], rc["legend.fontsize"]), (8.0, 7.5, 7.5))
        self.assertEqual((rc["axes.spines.top"], rc["axes.spines.right"]), (False, False))
        self.assertIsNone(rc["savefig.bbox"])               # "standard": the canvas is saved whole
        self.assertEqual(rc["axes.prop_cycle"].by_key()["color"], list(rz.PALETTE.values()))
        # The font that will really be drawn is reported, so a fallback is not a surprise.
        self.assertEqual(report["first_choice"], "Arial")
        self.assertEqual(report["fallback"], report["used"] != "Arial")
        self.assertEqual(rz.apply_style(font_pt=7)["first_choice"], "Arial")
        self.assertEqual(rc["ytick.labelsize"], 6.5)

    def test_palette_and_second_cue(self):
        self.assertEqual(sorted(rz.PALETTE.values()), sorted(
            ["#000000", "#E69F00", "#56B4E9", "#009E73", "#F0E442", "#0072B2", "#D55E00", "#CC79A7"]))
        colours = [tuple(int(code[i:i + 2], 16) for i in (1, 3, 5)) for code in rz.PALETTE.values()]
        self.assertEqual(cf.compare_colours(colours)[0], [])                 # all eight survive the simulations
        self.assertEqual(cf.compare_colours(colours[:4]), ([], []))          # the first four also survive grayscale
        styles = [rz.series_style(i) for i in range(8)]
        self.assertEqual(len({s["marker"] for s in styles}), 8)
        self.assertEqual(len({str(s["linestyle"]) for s in styles}), 8)


class AuditTests(Base):
    def test_bars_must_start_at_zero(self):
        fig, ax = self.panel()
        ax.bar(["control", "treated"], [52, 58])
        self.assertEqual(self.rules(fig), [])
        ax.set_ylim(50, 60)
        finding = rz.audit_axes(fig)[0]
        self.assertEqual((finding["rule"], finding["axes"]), ("bar_not_from_zero", 0))
        self.assertIn("the y axis runs from 50 to 60", finding["detail"])

        fig, ax = self.panel()
        ax.bar(["a", "b"], [2, 8], bottom=50)
        self.assertIn("bars start at 50", rz.audit_axes(fig)[0]["detail"])
        fig, ax = self.panel()
        ax.barh(["a", "b"], [52, 58])
        ax.set_xlim(40, 60)
        self.assertIn("the x axis runs from 40 to 60", rz.audit_axes(fig)[0]["detail"])
        fig, ax = self.panel()
        ax.bar(["a", "b"], [20, 800])
        ax.set_yscale("log")
        self.assertEqual(self.rules(fig), ["bar_not_from_zero"])

    def test_bars_that_do_start_at_zero(self):
        fig, ax = self.panel()
        ax.bar(["a", "b"], [2, 8])
        ax.bar(["a", "b"], [3, 4], bottom=[2, 8])          # stacked
        self.assertEqual(self.rules(fig), [])
        fig, ax = self.panel()
        ax.bar(["a", "b"], [-2, -8])
        self.assertEqual(self.rules(fig), [])
        fig, ax = self.panel()
        ax.hist(np.random.default_rng(0).normal(size=200))
        self.assertEqual(self.rules(fig), [])

    def test_filled_areas_and_bands(self):
        x = np.linspace(0, 10, 30)
        fig, ax = self.panel()
        ax.fill_between(x, np.sin(x) + 5)
        self.assertEqual(self.rules(fig), [])
        ax.set_ylim(3, 7)
        self.assertEqual(self.rules(fig), ["area_not_from_zero"])
        fig, ax = self.panel()
        ax.fill_between(x, np.sin(x) + 5, 3)
        self.assertIn("filled areas start at 3", rz.audit_axes(fig)[0]["detail"])
        fig, ax = self.panel()
        ax.fill_betweenx(x, np.sin(x) + 5, 2)
        self.assertEqual(self.rules(fig), ["area_not_from_zero"])
        # An interval around a line, a violin and a shaded period are not areas from a baseline.
        fig, ax = self.panel()
        ax.plot(x, np.sin(x) + 5)
        ax.fill_between(x, np.sin(x) + 4, np.sin(x) + 6, alpha=0.3)
        ax.fill_between(x, 0, 1, where=x > 5, transform=ax.get_xaxis_transform(), alpha=0.2)
        ax.axhspan(4, 5, alpha=0.1)
        ax.violinplot([np.random.default_rng(1).normal(5, 1, 50)])
        self.assertEqual(self.rules(fig), [])

    def test_twin_axes(self):
        x = np.arange(10)
        fig, ax = self.panel()
        ax.plot(x, x)
        ax.secondary_yaxis("right", functions=(lambda v: v * 2, lambda v: v / 2))      # a unit conversion is fine
        self.assertEqual(self.rules(fig), [])
        ax.twinx().plot(x, x ** 2)
        finding = rz.audit_axes(fig)[0]
        self.assertEqual(finding["rule"], "twin_axes")
        self.assertIn("axes 0 and 1", finding["detail"])
        fig, axes = plt.subplots(1, 2, figsize=rz.figsize_mm(183, 60))
        axes[0].plot(x, x)
        axes[1].plot(x, x ** 2)
        self.assertEqual(self.rules(fig), [])

    def test_log_axis_with_zero_or_negative_values(self):
        fig, ax = self.panel()
        ax.plot([1, 2, 3], [0, 10, 100])
        ax.axhline(1)
        ax.axvline(0)                                      # in axes coordinates along y: not data
        ax.set_yscale("log")
        finding = rz.audit_axes(fig)[0]
        self.assertEqual(finding["rule"], "log_axis_nonpositive")
        self.assertIn("the y axis is logarithmic and 1 plotted coordinate(s)", finding["detail"])
        fig, ax = self.panel()
        ax.scatter([0, 1, 2], [1, 2, 3])
        ax.set_xscale("log")
        self.assertEqual(self.rules(fig), ["log_axis_nonpositive"])
        fig, ax = self.panel()
        ax.errorbar([1, 2], [1, 5], yerr=[2, 2])           # the lower bar of the first point ends at -1
        ax.set_yscale("log")
        self.assertEqual(self.rules(fig), ["log_axis_nonpositive"])
        fig, ax = self.panel()
        ax.plot([1, 2, 3], [1, 10, 100])
        ax.set_yscale("log")
        self.assertEqual(self.rules(fig), [])


class SaveTests(Base):
    def test_save_writes_pdf_png_and_record_at_the_exact_size(self):
        fig, ax = self.panel(89, 60)
        ax.plot([0, 1, 2], [1, 3, 2], **rz.series_style(0))
        ax.set_xlabel("Time (weeks)")
        matplotlib.rcParams["savefig.bbox"] = "tight"      # a style that crops must not change the size
        record = self.save(fig)
        pdf, png, sidecar = (self.out / f"fig{suffix}" for suffix in (".pdf", ".png", ".figure.json"))
        self.assertEqual(struct.unpack(">II", png.read_bytes()[16:24]), (int(89 / 25.4 * 300), int(60 / 25.4 * 300)))
        self.assertIn(b"/MediaBox [ 0 0 252.283", pdf.read_bytes())            # 89 mm in points
        self.assertEqual(record, json.loads(sidecar.read_text(encoding="utf-8")))
        self.assertEqual((record["tool"], record["name"], record["size_mm"], record["dpi"]),
                         ("researchzy-figures", "fig", {"width": 89.0, "height": 60.0}, 300))
        self.assertEqual(Path(record["script"]["path"]).name, Path(__file__).name)
        self.assertEqual(record["data"][0]["sha256"], hashlib.sha256(self.data.read_bytes()).hexdigest())
        self.assertEqual([entry["sha256"] for entry in record["outputs"]],
                         [hashlib.sha256(path.read_bytes()).hexdigest() for path in (pdf, png)])
        self.assertEqual(record["packages"]["matplotlib"], matplotlib.__version__)
        self.assertEqual((record["fonts"]["first_choice"], len(record["fonts"]["used"])), ("Arial", 1))
        self.assertEqual(record["fonts"]["fallback"], record["fonts"]["used"] != ["Arial"])
        self.assertEqual(record["axis_findings"], [])
        # The same figure and data give the same PDF bytes: no creation date inside.
        again = self.save(fig)
        self.assertEqual(again["outputs"][0]["sha256"], record["outputs"][0]["sha256"])

    def test_save_refuses_what_it_should_not_do(self):
        fig, ax = self.panel()
        ax.plot([0, 1], [0, 1])
        self.out.mkdir()
        (self.out / "theirs.pdf").write_bytes(b"%PDF-1.4 someone else's figure")
        with self.assertRaises(FileExistsError):
            self.save(fig, "theirs")
        self.assertEqual((self.out / "theirs.pdf").read_bytes(), b"%PDF-1.4 someone else's figure")
        self.save(fig, "theirs", overwrite=True)
        self.save(fig, "theirs")                             # its own files may be replaced
        with self.assertRaises(FileNotFoundError):
            rz.save(fig, "fig", data=[self.dir / "missing.csv"], out=str(self.out), quiet=True)
        with self.assertRaises(ValueError):
            self.save(fig, "../escape")
        printed = io.StringIO()
        with redirect_stdout(printed):
            rz.save(fig, "said", data=str(self.data), out=str(self.out))
        self.assertEqual(json.loads(printed.getvalue())["data_files"], 1)


class ExportedFileTests(Base):
    def test_a_sound_figure_passes_the_checker(self):
        fig, axes = plt.subplots(1, 2, figsize=rz.figsize_mm(183, 70))
        for i in range(3):
            axes[0].plot(np.arange(8), np.arange(8) * (i + 1), label=f"dose {i}", **rz.series_style(i))
        axes[0].set_xlabel("Time (weeks)")
        axes[0].set_ylabel("Concentration (ng mL$^{-1}$)")
        axes[0].legend()
        axes[1].bar(["control", "treated"], [52, 58], color=rz.PALETTE["blue"])
        axes[1].set_yscale("linear")
        self.save(fig)
        code, (pdf, png) = self.check(self.out / "fig.pdf", self.out / "fig.png", "--width-mm", "183")
        self.assertEqual({name: c["status"] for name, c in pdf.items()},
                         {"width": "PASS", "min_font_size": "PASS", "fonts": "PASS", "images": "PASS", "axes": "PASS"})
        self.assertEqual(pdf["min_font_size"]["smallest_pt"], 5.6)        # the superscript of an 8 pt label
        self.assertEqual((png["width"]["status"], png["resolution"]["status"], png["axes"]["status"]), ("PASS", "PASS", "PASS"))
        if png["colour_vision"]["status"] != "NOT_CHECKED":                 # Pillow is installed
            self.assertEqual(sorted(png["colour_vision"]["colours"]), ["#000000", "#0072B2", "#009E73", "#E69F00"])
            self.assertEqual((png["colour_vision"]["status"], png["grayscale"]["status"], code), ("PASS", "PASS", 0))

    def test_a_tiny_font_and_a_cut_bar_axis_fail_the_checker(self):
        fig, ax = self.panel(89, 60)
        ax.bar(["control", "treated"], [52, 58])
        ax.set_ylim(50, 60)
        ax.set_ylabel("Response", fontsize=4)
        record = self.save(fig, "bad")
        self.assertEqual([f["rule"] for f in record["axis_findings"]], ["bar_not_from_zero"])
        code, (pdf, png) = self.check(self.out / "bad.pdf", self.out / "bad.png", "--width-mm", "89")
        self.assertEqual(code, 1)
        self.assertEqual((pdf["min_font_size"]["status"], pdf["min_font_size"]["smallest_pt"]), ("FAIL", 4.0))
        self.assertEqual(pdf["min_font_size"]["below"][0]["text"], ["Response"])
        self.assertEqual((pdf["axes"]["status"], png["axes"]["status"]), ("FAIL", "FAIL"))
        self.assertEqual(pdf["width"]["status"], "PASS")

    def test_superscripts_shrink_below_the_floor(self):
        fig, ax = self.panel()
        ax.plot([1, 2], [1, 2])
        ax.set_xlabel("Area (mm$^2$)", fontsize=7)
        self.save(fig, "script")
        _, (pdf,) = self.check(self.out / "script.pdf", "--width-mm", "89")
        self.assertEqual((pdf["min_font_size"]["status"], pdf["min_font_size"]["smallest_pt"]), ("FAIL", 4.9))

    def test_default_matplotlib_output_fails_on_fonts_and_size(self):
        matplotlib.rcdefaults()
        fig, ax = plt.subplots()
        ax.plot([0, 1], [0, 1])
        ax.set_title("Default")
        self.out.mkdir()
        fig.savefig(self.out / "default.pdf", bbox_inches="tight")
        code, (pdf,) = self.check(self.out / "default.pdf", "--width-mm", "89")
        self.assertEqual((code, pdf["width"]["status"], pdf["fonts"]["status"]), (1, "FAIL", "FAIL"))
        self.assertIn("Type 3", pdf["fonts"]["detail"])
        self.assertEqual(pdf["axes"]["status"], "NOT_CHECKED")              # no record: never a pass

    def test_a_record_of_an_older_export_is_not_used(self):
        fig, ax = self.panel()
        ax.plot([0, 1], [0, 1])
        self.save(fig)
        with open(self.out / "fig.png", "ab") as handle:
            handle.write(b"edited afterwards")
        _, (png,) = self.check(self.out / "fig.png", "--width-mm", "89")
        self.assertEqual(png["axes"]["status"], "NOT_CHECKED")
        self.assertIn("an older export", png["axes"]["detail"])


if __name__ == "__main__":
    unittest.main()
