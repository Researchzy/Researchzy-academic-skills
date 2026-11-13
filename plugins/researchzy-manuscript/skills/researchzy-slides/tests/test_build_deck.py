"""build_deck.py: escaping, the appendix boundary, a missing figure, the overwrite guard, notes,
and the PPTX (skips without python-pptx). One test compiles the deck when latexmk is on PATH."""
from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

SCRIPTS = Path(__file__).parents[1] / "scripts"


def load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


bd, sp = load("build_deck"), load("slide_plan")

try:
    import pptx  # noqa: F401
    HAVE_PPTX = True
except ImportError:
    HAVE_PPTX = False

def png(width: int = 4, height: int = 3) -> bytes:
    """A real red PNG, so that python-pptx and LaTeX can read it."""
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    raw = b"".join(b"\x00" + bytes([200, 30, 30] * width) for _ in range(height))
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


PNG = png()
PLAN = """---
title: Costs fell by 48% & stayed low
subtitle: A. Example (2026)
presenter: A. Example
event: Group meeting
minutes: 5
talk: seminar
{aspect}---

Seconds: 20
Notes: Hello and welcome.

## Peak memory falls by 48% with α ≥ 0.5 and 100$ saved_now
- Costs #1 fell {{by}} ~half^2 at 50% \\ less
- [bracket] first
Figure: fig1
Source: Fig. 1 of A. Example (2026)
Seconds: 90
Notes: The main result, in "quotes".

Second paragraph.

## A slide whose figure is missing still compiles
- Look at the box
Seconds: 60

## Use the window by default for long documents
- Close
Seconds: 30

# Backup

## Extra results kept back for questions
- Held back
Notes: If asked.
"""


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.slides = Path(self.tmp.name) / "slides"
        (self.slides / "figures").mkdir(parents=True)
        (self.slides / "figures" / "fig1.png").write_bytes(PNG)
        (self.slides / "figures" / "manifest.json").write_text(json.dumps({"figures": [
            {"id": "fig1", "file": "fig1.png", "pixels": [4, 3], "sha256": hashlib.sha256(PNG).hexdigest(),
             "label": "Fig. 1"}]}))
        self.plan = self.slides / "plan.md"
        self.plan.write_text(PLAN.format(aspect=""), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, module, *argv):
        old, out, err = sys.argv, io.StringIO(), io.StringIO()
        sys.argv = ["x.py", *argv]
        try:
            with redirect_stdout(out), redirect_stderr(err):
                code = module.main()
        finally:
            sys.argv = old
        return code, json.loads(out.getvalue()) if out.getvalue() else err.getvalue()

    def build(self, *flags, check=True):
        if check:
            self.run_cli(sp, "check", str(self.plan))
        return self.run_cli(bd, "build", str(self.plan), *flags)


class BeamerTests(Base):
    def test_refuses_a_plan_that_was_not_checked(self):
        code, out = self.build(check=False)
        self.assertEqual(code, 1)
        self.assertIn("not been run", out["refused"])
        self.assertFalse((self.slides / "deck.tex").exists())
        code, out = self.build("--unchecked", check=False)
        self.assertEqual(out["plan_check"], "not run")
        self.assertTrue((self.slides / "deck.tex").exists())
        self.run_cli(sp, "check", str(self.plan))
        self.plan.write_text(self.plan.read_text() + "\n")
        code, out = self.run_cli(bd, "build", str(self.plan))
        self.assertIn("another version", out["refused"])

    def test_escaping(self):
        self.assertEqual(bd.tex(r"50% & $5 #1 a_b {x} ~ ^ \ "), r"50\% \& \$5 \#1 a\_b \{x\} \textasciitilde{} "
                         r"\textasciicircum{} \textbackslash{} ")
        self.assertEqual(bd.tex("α ≥ β − 1 µm"), r"$\alpha$ $\geq$ $\beta$ \textminus{} 1 \textmu{}m")
        self.assertEqual(bd.tex('say "this"'), "say ``this''")
        self.assertEqual(bd.unsupported("Latin é and 中文"), ["中", "文"])

    def test_the_deck(self):
        self.plan.write_text(self.plan.read_text().replace("- Look at the box\n", "- Look at the box\nFigure: gone\n"))
        code, out = self.build("--unchecked")                    # the check fails on the missing figure
        self.assertEqual(out["plan_check"], "failed")
        self.assertEqual(code, 1)                                 # the missing figure
        self.assertEqual(out["missing_figures"], [{"slide": 3, "figure": "gone", "why": "not in figures/manifest.json"}])
        text = (self.slides / "deck.tex").read_text()
        self.assertIn("aspectratio=169", text)
        self.assertIn(r"\title{Costs fell by 48\% \& stayed low}", text)
        self.assertIn(r"Peak memory falls by 48\% with $\alpha$ $\geq$ 0.5 and 100\$ saved\_now", text)
        self.assertIn(r"\item Costs \#1 fell \{by\} \textasciitilde{}half\textasciicircum{}2 at 50\% \textbackslash{} less", text)
        self.assertIn(r"\item{} [bracket] first", text)
        self.assertIn(r"\includegraphics[width=\linewidth,height=5.6cm,keepaspectratio]{figures/fig1.png}", text)
        self.assertIn(r"\rzsource{Fig. 1 of A. Example (2026)}", text)
        self.assertNotIn("figures/gone", text)
        self.assertIn(r"\rzmissing{gone}", text)
        self.assertIn(r"\note{The main result, in ``quotes''.\par}", text)
        self.assertIn(r"\note{Second paragraph.\par}", text)
        before, after = text.split(r"\appendix")
        self.assertEqual(before.count(r"\begin{frame}"), 4)
        self.assertEqual(after.count(r"\begin{frame}"), 1)
        self.assertIn("Extra results kept back", after)
        self.assertEqual(text.count(r"\appendix"), 1)
        notes = (self.slides / "notes.md").read_text()
        self.assertIn("## 2. Peak memory falls by 48% with α ≥ 0.5 and 100$ saved_now (1:30, from 0:20)", notes)
        self.assertIn("## 4. Use the window by default for long documents (0:30, from 2:50)", notes)
        self.assertIn("# Backup (off the clock)\n\n## 5. Extra results kept back for questions\n", notes)
        record = json.loads((self.slides / "build.json").read_text())
        self.assertEqual(record["files"]["deck.tex"], hashlib.sha256((self.slides / "deck.tex").read_bytes()).hexdigest())
        self.assertEqual(record["plan_sha256"], hashlib.sha256(self.plan.read_bytes()).hexdigest())

    def test_four_by_three_and_characters_for_xelatex(self):
        self.plan.write_text(PLAN.format(aspect="aspect: 4:3\n").replace("Held back", "Held back 中文"), encoding="utf-8")
        code, out = self.build()
        self.assertIn("aspectratio=43", (self.slides / "deck.tex").read_text())
        self.assertEqual(out["characters_for_xelatex"], "中文")
        self.assertIn("latexmk -xelatex", out["compile"])

    def test_overwrite_guard(self):
        self.build()
        deck = self.slides / "deck.tex"
        deck.write_text(deck.read_text() + "% my edit\n")
        code, out = self.build()
        self.assertEqual(code, 1)
        self.assertIn("--force", out["refused"][0])
        self.assertTrue(deck.read_text().endswith("% my edit\n"))
        code, out = self.build("--force")
        self.assertTrue((self.slides / "deck.edited.tex").read_text().endswith("% my edit\n"))
        self.assertFalse(deck.read_text().endswith("% my edit\n"))
        code, out = self.build()                                  # unedited output: rebuilt freely
        self.assertNotIn("refused", out)

    @unittest.skipUnless(shutil.which("latexmk") and shutil.which("pdflatex"), "latexmk is not on PATH")
    def test_compiles_and_passes_the_deck_check(self):
        code, out = self.build()
        self.assertEqual(code, 0, out)
        done = subprocess.run(["latexmk", "-pdf", "-cd", "-interaction=nonstopmode", "-halt-on-error", "-file-line-error",
                               str(self.slides / "deck.tex")], capture_output=True, text=True, timeout=300)
        self.assertEqual(done.returncode, 0, done.stdout[-2000:])
        code, out = self.run_cli(sp, "deck", str(self.slides / "deck.tex"), "--plan", str(self.plan))
        self.assertEqual(code, 0, out)
        self.assertEqual(out["files"][str(self.slides / "deck.tex")]["pages_in_log"], 5)


class PptxTests(Base):
    @unittest.skipIf(HAVE_PPTX, "python-pptx is installed")
    def test_without_python_pptx_it_says_so(self):
        code, out = self.build("--pptx")
        self.assertIn("not written: python-pptx is not installed", out["pptx"])
        self.assertTrue((self.slides / "deck.tex").exists())

    @unittest.skipUnless(HAVE_PPTX, "python-pptx is not installed")
    def test_pptx_matches_the_plan(self):
        code, out = self.build("--pptx")
        self.assertEqual(code, 0, out)
        self.assertEqual(out["overfull_pptx_slides"], [])
        from pptx import Presentation
        deck = Presentation(str(self.slides / "deck.pptx"))
        self.assertEqual(len(deck.slides), 5)
        self.assertEqual(round(deck.slide_width / 914400, 2), 13.33)
        self.assertIn("The main result", deck.slides[1].notes_slide.notes_text_frame.text)
        sizes = [run.font.size.pt for shape in deck.slides[1].shapes if shape.has_text_frame
                 and shape.name == "Body" for p in shape.text_frame.paragraphs for run in p.runs]
        self.assertTrue(sizes and min(sizes) >= 20)
        code, check = self.run_cli(sp, "deck", str(self.slides / "deck.pptx"), "--plan", str(self.plan))
        self.assertEqual(code, 0, check)
        self.assertEqual(check["flags"], [])
        self.assertTrue(any("NOT_RENDERED" in n for n in check["not_checked"]))

    @unittest.skipUnless(HAVE_PPTX, "python-pptx is not installed")
    def test_an_overfull_slide_is_reported_not_shrunk(self):
        long = "\n".join(f"- {'a long bullet that keeps going ' * 4}{i}" for i in range(7))
        self.plan.write_text(self.plan.read_text().replace("- Close", long), encoding="utf-8")
        code, out = self.build("--pptx", "--unchecked")
        self.assertEqual(code, 1)
        self.assertEqual([(o["slide"], o["where"]) for o in out["overfull_pptx_slides"]], [(4, "bullets")])
        from pptx import Presentation
        sizes = {run.font.size.pt for shape in Presentation(str(self.slides / "deck.pptx")).slides[3].shapes
                 if shape.name == "Body" for p in shape.text_frame.paragraphs for run in p.runs}
        self.assertEqual(sizes, {bd.BODY_PT})


if __name__ == "__main__":
    unittest.main()
