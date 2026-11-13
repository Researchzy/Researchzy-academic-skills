"""paper_figure.py: crops a one-page PDF made here, records it, and refuses to overwrite. The
rendering tests need PyMuPDF and skip without it; the message for a missing renderer does not."""
from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).parents[1] / "scripts" / "paper_figure.py"
spec = importlib.util.spec_from_file_location("paper_figure", SCRIPT)
pf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pf)

try:
    import pymupdf as fitz
except ImportError:
    try:
        import fitz
    except ImportError:
        fitz = None


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.slides = self.root / "slides"

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *argv):
        old, out, err = sys.argv, io.StringIO(), io.StringIO()
        sys.argv = ["paper_figure.py", "--dir", str(self.slides), *argv]
        try:
            with redirect_stdout(out), redirect_stderr(err):
                code = pf.main()
        finally:
            sys.argv = old
        return code, json.loads(out.getvalue()) if out.getvalue() else err.getvalue()


class WithoutRenderer(Base):
    def test_says_what_is_missing(self):
        blocked = {"pymupdf": None, "fitz": None, "PIL": None}
        with mock.patch.dict(sys.modules, blocked), mock.patch.object(pf.shutil, "which", return_value=None):
            code, out = self.run_cli("crop", "paper.pdf", "--page", "1", "--box", "0,0,1,1", "--id", "f")
        self.assertEqual(code, 1)
        self.assertIn("PyMuPDF", out["refused"])
        self.assertIn("pdftoppm", out["refused"])

    def test_bad_box(self):
        for box in ("0.1,0.1,0.5", "0.5,0.1,0.4,0.6", "0,0,1.2,1", "a,b,c,d"):
            with self.assertRaises(pf.Refused):
                pf.parse_box(box)
        self.assertEqual(pf.parse_box("0.1,0.2,0.9,0.8"), (0.1, 0.2, 0.9, 0.8))


@unittest.skipUnless(fitz, "PyMuPDF is not installed")
class Crop(Base):
    def setUp(self):
        super().setUp()
        doc = fitz.open()
        page = doc.new_page(width=600, height=800)
        page.draw_rect(fitz.Rect(60, 80, 300, 320), color=(0, 0, 0), fill=(0.0, 0.45, 0.70))
        page.draw_line(fitz.Point(60, 320), fitz.Point(540, 320), color=(0, 0, 0), width=2)
        page.insert_text((60, 360), "Figure 1: A blue block on a black axis.", fontsize=11)
        self.pdf = self.root / "paper.pdf"
        doc.save(self.pdf)

    def crop(self, *extra, fid="fig1", box="0.1,0.1,0.5,0.4"):
        return self.run_cli("crop", str(self.pdf), "--page", "1", "--box", box, "--id", fid, "--dpi", "100", *extra)

    def test_crop_writes_the_png_and_its_manifest_row(self):
        code, out = self.crop("--label", "Fig. 1 of the test paper")
        self.assertEqual(code, 0, out)
        png = self.slides / "figures" / "fig1.png"
        manifest = json.loads((self.slides / "figures" / "manifest.json").read_text())
        row = manifest["figures"][0]
        self.assertEqual(row["id"], "fig1")
        self.assertEqual(row["file"], "fig1.png")
        self.assertEqual(row["page"], 1)
        self.assertEqual(row["box"], [0.1, 0.1, 0.5, 0.4])
        self.assertEqual(row["dpi"], 100)
        for got in row["pixels"]:                              # 0.4 x 600 pt and 0.3 x 800 pt at 100 dpi
            self.assertAlmostEqual(got, 333, delta=1)
        self.assertEqual(row["sha256"], hashlib.sha256(png.read_bytes()).hexdigest())
        self.assertEqual(row["source_sha256"], hashlib.sha256(self.pdf.read_bytes()).hexdigest())
        self.assertEqual(row["label"], "Fig. 1 of the test paper")
        self.assertTrue(any("raise --dpi" in note for note in out["notes"]))

    def test_refuses_to_overwrite(self):
        self.crop()
        first = (self.slides / "figures" / "fig1.png").read_bytes()
        code, out = self.crop(box="0.1,0.1,0.9,0.5")
        self.assertEqual(code, 1)
        self.assertIn("--replace", out["refused"])
        self.assertEqual((self.slides / "figures" / "fig1.png").read_bytes(), first)
        code, out = self.crop("--replace", box="0.1,0.1,0.9,0.5")
        self.assertEqual(code, 0)
        self.assertTrue(out["replaced"])
        rows = json.loads((self.slides / "figures" / "manifest.json").read_text())["figures"]
        self.assertEqual([r["box"] for r in rows], [[0.1, 0.1, 0.9, 0.5]])
        (self.slides / "figures" / "fig1.png").write_bytes(b"edited by hand")
        code, out = self.crop("--replace")
        self.assertEqual(code, 1)
        self.assertIn("not overwritten", out["refused"])
        (self.slides / "figures" / "mine.png").write_bytes(b"the user's own file")
        code, out = self.crop(fid="mine")
        self.assertIn("not overwritten", out["refused"])

    def test_refusals(self):
        code, out = self.run_cli("crop", str(self.pdf), "--page", "2", "--box", "0,0,1,1", "--id", "x")
        self.assertIn("outside the PDF's 1 page", out["refused"])
        code, out = self.crop(box="0.6,0.7,0.9,0.95")              # white space only
        self.assertIn("single colour", out["refused"])
        self.assertFalse((self.slides / "figures" / "fig1.png").exists())
        code, out = self.crop(fid="../escape")
        self.assertIn("--id takes", out["refused"])
        (self.root / "broken.pdf").write_text("not a pdf")
        code, err = self.run_cli("crop", str(self.root / "broken.pdf"), "--page", "1", "--box", "0,0,1,1", "--id", "x")
        self.assertEqual(code, 2)
        self.assertIn("Cannot read the PDF", err)

    def test_page_preview_lists_the_caption_and_the_drawing(self):
        code, out = self.run_cli("page", str(self.pdf), "--page", "1")
        self.assertEqual(code, 0)
        self.assertTrue(Path(out["preview"]).is_file())
        items = out["on_this_page"]
        self.assertTrue(any(i.get("caption", "").startswith("Figure 1:") for i in items))
        drawings = [i["box"] for i in items if "drawing" in i]
        if hasattr(fitz.Page, "cluster_drawings"):
            self.assertTrue(drawings)
            self.assertAlmostEqual(drawings[0][0], 0.1, delta=0.01)


if __name__ == "__main__":
    unittest.main()
