"""slide_plan.py: the plan format, every rule of `check`, the number matching, and `deck` on a
PPTX built here with zipfile and on a captured Beamer log. Standard library only; the PDF cases
skip without PyMuPDF."""
from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
import zipfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts" / "slide_plan.py"
spec = importlib.util.spec_from_file_location("slide_plan", SCRIPT)
sp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sp)

try:
    import pymupdf  # noqa: F401
    HAVE_PYMUPDF = True
except ImportError:
    try:
        import fitz  # noqa: F401
        HAVE_PYMUPDF = True
    except ImportError:
        HAVE_PYMUPDF = False

FRONT = """---
title: Sparse attention halves the memory of long-document transformers
presenter: A. Example
minutes: {minutes}
talk: {talk}
---

Seconds: 20
Notes: Thank you. One message today.
"""
FILLER = " ".join(["The encoder was trained with the same data and the same schedule as before."] * 30)
PAPER = ("[[page 1]]\nOn inputs of 16,384 tokens, peak memory falls from 31.2 GB to 16.1 GB, a reduction "
         "of 48.4 %. The mean score changes by \u22120.15 points; throughput rises by a factor of 1.9. "
         "We report 3 runs and a window of 256 tokens. Accuracy stays at 88 on classification.\n"
         + FILLER + "\n[[page 2]]\nThe loss changed by 0.3 points. Training took 120,000 steps.\n")


def slide(title, bullets=("A bullet with no numerals in it at all",), seconds=60, notes="Short notes here.", extra=""):
    lines = [f"## {title}"] + [f"- {b}" for b in bullets]
    lines += [f"Seconds: {seconds}"] if seconds is not None else []
    lines += [f"Notes: {notes}"] if notes else []
    return "\n".join(lines + ([extra] if extra else [])) + "\n\n"


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.slides = self.root / "slides"
        (self.slides / "figures").mkdir(parents=True)
        (self.root / "paper.txt").write_text(PAPER, encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def plan(self, body: str, minutes=5, talk="conference") -> Path:
        path = self.slides / "plan.md"
        path.write_text(FRONT.format(minutes=minutes, talk=talk) + "\n" + body, encoding="utf-8")
        return path

    def check(self, body: str, paper="paper.txt", **kw) -> dict:
        plan = sp.parse_plan(self.plan(body, **{k: kw.pop(k) for k in ("minutes", "talk") if k in kw}))
        return sp.check_plan(plan, None if paper is None else self.root / paper, **kw)

    def figure(self, fid: str, data: bytes = b"\x89PNG fake", label="Fig. 1 of the paper", record=None):
        (self.slides / "figures" / f"{fid}.png").write_bytes(data)
        manifest = self.slides / "figures" / "manifest.json"
        rows = json.loads(manifest.read_text())["figures"] if manifest.exists() else []
        rows.append({"id": fid, "file": f"{fid}.png", "page": 1, "box": [0, 0, 1, 1], "pixels": [400, 300],
                     "sha256": record or hashlib.sha256(data).hexdigest(), "label": label})
        manifest.write_text(json.dumps({"figures": rows}))

    def run_cli(self, *argv):
        old, out, err = sys.argv, io.StringIO(), io.StringIO()
        sys.argv = ["slide_plan.py", *argv]
        try:
            with redirect_stdout(out), redirect_stderr(err):
                code = sp.main()
        finally:
            sys.argv = old
        return code, out.getvalue(), err.getvalue()

    @staticmethod
    def checks(result, level):
        return [(item["check"], item["slide"]) for item in result[level]]


class ParserTests(Base):
    def test_the_plan_format(self):
        path = self.plan(
            "## Peak memory falls by half on long inputs\n- First bullet\n* Second bullet\n"
            "Figure: fig2a\nSource: Fig. 2a of the paper\nSeconds: 1:15\nAllow: 2027 | my plan\n"
            "Notes: First paragraph of the notes\ncontinues here.\n\nSecond paragraph.\n\n"
            "## Part two\nKind: section\nSeconds: 5\n\n"
            "## Use the window by default for long documents\n- Last\nSeconds: 30\n\n"
            "# Backup\n\n## Extra results kept for questions\n- Held back\n", talk="Journal Club")
        plan = sp.parse_plan(path)
        self.assertEqual(plan["problems"], [])
        self.assertEqual(plan["front"]["talk"], "journal-club")
        self.assertEqual(plan["front"]["aspect"], "16:9")
        first, s2, section, closing, backup = plan["slides"]
        self.assertEqual((first["kind"], first["seconds"], first["notes"]), ("title", 20, "Thank you. One message today."))
        self.assertEqual(s2["bullets"], ["First bullet", "Second bullet"])
        self.assertEqual((s2["figure"], s2["source"], s2["seconds"]), ("fig2a", "Fig. 2a of the paper", 75))
        self.assertEqual(s2["notes"], "First paragraph of the notes continues here.\n\nSecond paragraph.")
        self.assertEqual(s2["allow"], [{"text": "2027", "reason": "my plan"}])
        self.assertEqual(section["kind"], "section")
        self.assertEqual(closing["kind"], "closing")      # the last slide before # Backup
        self.assertTrue(backup["backup"])
        self.assertEqual([s["n"] for s in plan["slides"]], [1, 2, 3, 4, 5])

    def test_lines_the_scripts_cannot_read_are_problems(self):
        plan = sp.parse_plan(self.plan(
            "Figure: early\n- a bullet before any slide\n## A title that says what the slide shows\nFigure: a\nFigure: b\n"
            "Seconds: soon\nAllow: no number | reason\nAllow: 12\nKind: appendix\nfree text\n### Sub\n"
            "## Another title that is a full claim\nSource: Fig. 1\n# Backup\nstray text\n"))
        text = "\n".join(plan["problems"])
        for expected in ("title frame", "second Figure", "Seconds: takes", "Allow: takes", "Kind: is",
                         "not a bullet", "only headings", "after `# Backup`", "Source: without Figure"):
            self.assertIn(expected, text)
        result = sp.check_plan(plan, None)
        self.assertFalse(result["ok"])
        self.assertIn("format", [e["check"] for e in result["errors"]])

    def test_a_plan_without_its_front_block_is_refused(self):
        bad = self.slides / "bad.md"
        for text in ("## Just a slide\n", "---\ntitle: T\nminutes: 5\n---\n", "---\ntitle: T\ntalk: seminar\n---\n",
                     "---\ntitle: T\nminutes: 5\ntalk: party\n---\n"):
            bad.write_text(text)
            with self.assertRaises(sp.PlanError):
                sp.parse_plan(bad)
        code, _, err = self.run_cli("check", str(bad))
        self.assertEqual(code, 2)
        self.assertIn("talk:", err)


class BudgetTests(Base):
    def test_slides_against_the_budget_with_backup_off_the_clock(self):
        body = "".join(slide(f"Claim number {chr(65 + i)} says something specific", seconds=20) for i in range(5))
        result = self.check(body + "# Backup\n\n" + slide("A backup slide nobody times"), minutes=5)
        self.assertEqual(result["checks"]["slides"]["status"], "PASS")       # 6 on the clock, 6 <= 5 * 1.25
        result = self.check(body * 2, minutes=5)
        self.assertIn(("slides", None), self.checks(result, "errors"))
        self.assertIn("a convention for a conference talk", result["checks"]["slides"]["detail"])
        result = self.check(body * 2, minutes=5, per_minute=2.5)
        self.assertEqual(result["checks"]["slides"]["status"], "PASS")
        self.assertIn("--slides-per-minute", result["checks"]["slides"]["detail"])
        result = self.check(body, minutes=5, talk="lecture")                # 0.7 a minute: budget 4
        self.assertIn(("slides", None), self.checks(result, "errors"))

    def test_planned_seconds_against_the_slot(self):
        over = self.check(slide("Two hundred seconds is more than the slot allows", seconds=300), minutes=4)
        self.assertIn(("time", None), self.checks(over, "errors"))
        missing = self.check(slide("This slide has no planned seconds at all", seconds=None), minutes=1)
        self.assertIn(("time", None), self.checks(missing, "not_checked"))
        self.assertEqual(missing["checks"]["time"]["status"], "NOT_CHECKED")
        short = self.check(slide("This slide fills a small part of the slot", seconds=40), minutes=5)
        self.assertIn(("time", None), self.checks(short, "flags"))

    def test_spoken_time_of_the_notes(self):
        long = " ".join(["word"] * 400)
        result = self.check(slide("Notes that take three minutes to say aloud", seconds=40, notes=long), minutes=1)
        self.assertIn(("speech", None), self.checks(result, "errors"))
        result = self.check(slide("Notes that take three minutes to say aloud", seconds=40, notes=long),
                            minutes=1, wpm=600)
        self.assertNotIn(("speech", None), self.checks(result, "errors"))
        silent = self.check(slide("A slide whose notes are still missing", notes=""))
        self.assertIn(("speech", None), self.checks(silent, "not_checked"))
        thin = self.check(slide("A slide with far too little said about it", seconds=200, notes="Hi."), minutes=4)
        self.assertIn(("speech", None), self.checks(thin, "flags"))

    def test_words_bullets_titles_and_empty_slides(self):
        wordy = [" ".join(["word"] * 25)] * 3
        body = (slide("Results") + slide("Main results") + slide("Two words") + slide("Results on long inputs beat dense attention")
                + slide("This slide carries far too many words for a room", bullets=wordy)
                + slide("This slide has seven bullets which is too many", bullets=[f"point {c}" for c in "abcdefg"])
                + "## A slide with nothing but its title on it\nSeconds: 10\nNotes: Pause.\n\n"
                + "## Results\nKind: section\n\n" + slide("Thank you"))
        result = self.check(body, minutes=12)
        flags = self.checks(result, "flags")
        self.assertIn(("titles", 2), flags)
        self.assertIn(("titles", 3), flags)                 # every word is a label word
        self.assertIn(("titles", 4), flags)                 # two words
        self.assertNotIn(("titles", 5), flags)              # a label word inside a claim is fine
        self.assertIn(("words", 6), flags)
        self.assertIn(("bullets", 7), flags)
        self.assertIn(("empty", 8), flags)
        self.assertNotIn(("titles", 9), flags)              # a section slide is exempt
        self.assertNotIn(("empty", 9), flags)
        self.assertNotIn(("titles", 10), flags)             # the closing slide is exempt
        self.assertTrue(result["ok"])                       # flags do not fail the check
        dense = self.check(slide("Every slide here is dense with words", bullets=wordy[:2]) * 3)
        self.assertIn(("words", None), self.checks(dense, "flags"))      # the median

    def test_figures_against_the_manifest(self):
        self.figure("fig1")
        self.figure("fig2", label="")
        self.figure("fig3", record="0" * 64)
        self.figure("fig4")
        (self.slides / "figures" / "fig4.png").unlink()
        body = "".join(slide(f"Figure slide {i} shows a specific result", extra=f"Figure: {fid}")
                       for i, fid in enumerate(("fig1", "fig2", "fig3", "fig4", "nofig"), 2))
        result = self.check(body, minutes=6)
        errors, flags = self.checks(result, "errors"), self.checks(result, "flags")
        self.assertNotIn(("figures", 2), errors + flags)
        self.assertIn(("figures", 3), flags)                # no source label anywhere
        self.assertIn(("figures", 4), errors)               # not the recorded crop
        self.assertIn(("figures", 5), errors)               # file missing
        self.assertIn(("figures", 6), errors)               # not in the manifest
        code, _, _ = self.run_cli("check", str(self.slides / "plan.md"), "--paper", str(self.root / "paper.txt"))
        self.assertEqual(code, 1)


class NumberTests(Base):
    def numbers(self, *bullets, notes="", extra="") -> dict:
        result = self.check(slide("A claim title without numerals in it", bullets=bullets, notes=notes, extra=extra))
        return {row["number"]: row for row in result["numbers"]}

    def test_normalised_and_rounded_numbers_are_found(self):
        bullets = ("16384 tokens", "16\u202f384 tokens again", "48.4% less", "a 48% cut",
                   "mean \u22120.15 points", "about -0.2 points", "1.9 times", "0.3 points")
        result = self.check(slide("A claim title without numerals in it", bullets=bullets))
        self.assertEqual([(r["number"], r["result"]) for r in result["numbers"]],
                         [("16384", "found"), ("16384", "found"), ("48.4%", "found"), ("48%", "found"),
                          ("-0.15", "found"), ("-0.2", "found"), ("1.9", "found"), ("0.3", "found")])
        rows = {row["number"]: row for row in result["numbers"]}
        self.assertEqual(rows["48%"]["how"], "rounded")
        self.assertEqual(rows["48.4%"]["paper_number"], "48.4 %")        # the space before % is normalised
        self.assertEqual(rows["-0.2"]["how"], "rounded")
        self.assertEqual(rows["48.4%"]["page"], 1)
        self.assertEqual(rows["0.3"]["page"], 2)

    def test_sign_percent_and_names(self):
        rows = self.numbers("-0.3 points", "88% on classification", "the p53 gene", "a 52% gain")
        self.assertEqual(rows["-0.3"]["result"], "NOT_FOUND")           # the paper's 0.3 is not negative
        self.assertEqual(rows["88%"]["result"], "found")
        self.assertFalse(rows["88%"]["percent_sign"])                   # the paper has 88, not 88%
        self.assertNotIn("53", rows)                                    # a digit glued to a letter is a name
        self.assertEqual(rows["52%"]["result"], "NOT_FOUND")

    def test_allow_lines_and_notes(self):
        rows = self.numbers("We start in 2027", notes="The cost was 35% of the budget.",
                            extra="Allow: 2027 | the presenter's own plan\nAllow: 99 | unused")
        self.assertEqual(rows["2027"]["result"], "allowed")
        self.assertEqual(rows["35%"]["result"], "NOT_FOUND")
        self.assertEqual(rows["35%"]["in"], "notes")
        result = self.check(slide("A claim title without numerals in it", extra="Allow: 99 | unused"))
        self.assertTrue(any("99" in f["message"] for f in result["flags"]))

    def test_without_the_paper_numbers_are_not_checked_never_passed(self):
        result = self.check(slide("A cut of 48% at 16,384 tokens"), paper=None)
        self.assertTrue(result["ok"])
        self.assertEqual(result["checks"]["numbers"]["status"], "NOT_CHECKED")
        self.assertEqual({r["result"] for r in result["numbers"]}, {"NOT_CHECKED"})
        self.assertIn(("numbers", None), self.checks(result, "not_checked"))
        (self.root / "scan.txt").write_text("Figure 1. 48%")
        result = self.check(slide("A cut of 48% at 16,384 tokens"), paper="scan.txt")
        self.assertEqual(result["checks"]["numbers"]["status"], "NOT_CHECKED")
        self.assertIn("almost no text", result["not_checked"][0]["message"])

    def test_cli_report_and_paper_from_the_front_block(self):
        path = self.plan(slide("Peak memory falls by 48% at 16,384 tokens", notes="A 35% saving."))
        path.write_text(path.read_text().replace("talk: conference", "talk: conference\npaper: paper.txt"))
        code, out, _ = self.run_cli("check", str(path))
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(out)["checks"]["numbers"]["NOT_FOUND"], 1)
        report = (self.slides / "plan-check.md").read_text()
        self.assertIn("| numbers | FAIL |", report)
        self.assertIn("rounded from 48.4 %", report)
        self.assertTrue((self.slides / "plan-check.json").is_file())

    @unittest.skipUnless(HAVE_PYMUPDF, "PyMuPDF is not installed")
    def test_numbers_from_a_pdf(self):
        try:
            import pymupdf as fitz
        except ImportError:
            import fitz
        doc = fitz.open()
        page = doc.new_page()
        page.insert_textbox(fitz.Rect(50, 50, 550, 780), PAPER.replace("\u2212", "-").split("[[page 2]]")[0][10:],
                            fontsize=9)
        doc.save(self.root / "paper.pdf")
        rows = {r["number"]: r for r in self.check(slide("A cut of 48% at 16,384 tokens"), paper="paper.pdf")["numbers"]}
        self.assertEqual(rows["48%"]["result"], "found")
        self.assertEqual(rows["16,384"]["page"], 1)


A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG = "http://schemas.openxmlformats.org/package/2006/relationships"
EMU = 914400


def text_shape(name, x, y, w, h, text, pt=24):
    return (f'<p:sp><p:nvSpPr><p:cNvPr id="2" name="{name}"/><p:cNvSpPr txBox="1"/><p:nvPr/></p:nvSpPr>'
            f'<p:spPr><a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{w}" cy="{h}"/></a:xfrm></p:spPr>'
            f'<p:txBody><a:bodyPr/><a:p><a:r><a:rPr sz="{int(pt * 100)}"/><a:t>{text}</a:t></a:r></a:p></p:txBody></p:sp>')


def picture(x, y, w, h):
    return (f'<p:pic><p:nvPicPr><p:cNvPr id="3" name="Picture"/><p:cNvPicPr/><p:nvPr/></p:nvPicPr>'
            f'<p:blipFill><a:blip r:embed="rIdImg"/></p:blipFill>'
            f'<p:spPr><a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{w}" cy="{h}"/></a:xfrm></p:spPr></p:pic>')


def pptx(path: Path, slides: list, media: bytes = b"\x89PNG fake") -> None:
    """A minimal package: slides as (shape XML, notes text); part names deliberately reversed so
    that the order must come from presentation.xml."""
    head = f'xmlns:a="{A_NS}" xmlns:p="{P_NS}" xmlns:r="{R_NS}"'
    n = len(slides)
    with zipfile.ZipFile(path, "w") as z:
        ids = "".join(f'<p:sldId id="{256 + i}" r:id="rId{i + 1}"/>' for i in range(n))
        z.writestr("ppt/presentation.xml", f'<p:presentation {head}><p:sldIdLst>{ids}</p:sldIdLst>'
                   f'<p:sldSz cx="{int(13.333 * EMU)}" cy="{int(7.5 * EMU)}"/></p:presentation>')
        z.writestr("ppt/_rels/presentation.xml.rels", f'<Relationships xmlns="{PKG}">' + "".join(
            f'<Relationship Id="rId{i + 1}" Type="{R_NS}/slide" Target="slides/slide{n - i}.xml"/>' for i in range(n))
            + "</Relationships>")
        z.writestr("ppt/media/image1.png", media)
        for i, (shapes, notes) in enumerate(slides):
            part = n - i
            z.writestr(f"ppt/slides/slide{part}.xml", f'<p:sld {head}><p:cSld><p:spTree>{shapes}</p:spTree></p:cSld></p:sld>')
            rels = f'<Relationship Id="rIdImg" Type="{R_NS}/image" Target="../media/image1.png"/>'
            if notes:
                rels += f'<Relationship Id="rIdN" Type="{R_NS}/notesSlide" Target="../notesSlides/notesSlide{part}.xml"/>'
                z.writestr(f"ppt/notesSlides/notesSlide{part}.xml",
                           f'<p:notes {head}><p:cSld><p:spTree><p:sp><p:nvSpPr><p:cNvPr id="2" name="Notes"/>'
                           f'<p:cNvSpPr/><p:nvPr><p:ph type="body"/></p:nvPr></p:nvSpPr><p:txBody><a:p><a:r>'
                           f'<a:t>{notes}</a:t></a:r></a:p></p:txBody></p:sp></p:spTree></p:cSld></p:notes>')
            z.writestr(f"ppt/slides/_rels/slide{part}.xml.rels", f'<Relationships xmlns="{PKG}">{rels}</Relationships>')


# A captured pdflatex log (-file-line-error), shortened: a missing graphic, an undefined
# reference, a frame too tall, a box too wide, a line TeX broke at 79 characters.
CAPTURED_LOG = """This is pdfTeX, Version 3.141592653-2.6-1.40.29 (TeX Live 2026) (preloaded format=pdflatex)
LaTeX Warning: File `figures/nosuchfig.png' not found on input line 6.

./deck.tex:6: Package pdftex.def Error: File `figures/nosuchfig.png' not found:
 using draft setting.

l.6 \\end{frame}

LaTeX Warning: Reference `fig:none' on page 2 undefined on input line 9.

[2

]
Overfull \\vbox (113.23177pt too high) detected at line 12
 []

Overfull \\hbox (3.1pt too wide) in paragraph at lines 15--15
 []

Overfull \\hbox (170.71652pt too wide) in paragraph at lines 15--15
[][]
Package rerunfilecheck Warning: File `deck.out' has changed.
(rerunfilecheck)                Rerun to get outlines right or use package `bookm
ark'.

Output written on deck.pdf (4 pages, 45577 bytes).
"""


class DeckTests(Base):
    def setUp(self):
        super().setUp()
        self.plan_path = self.plan(slide("Peak memory falls by half on long inputs", extra="Figure: fig1")
                                   + slide("Use the window by default") + "# Backup\n\n" + slide("Held back for questions"))
        self.figure("fig1")

    def deck(self, *files):
        code, out, err = self.run_cli("deck", *map(str, files), "--plan", str(self.plan_path))
        return code, (json.loads(out) if out else err)

    def test_pptx_read_as_a_zip(self):
        W = int(13.333 * EMU)
        good = [(text_shape("Title", 0, 0, W, EMU, "A title"), "Opening"),
                (text_shape("Title", 0, 0, W, EMU, "Peak memory falls") + picture(EMU, EMU, 6 * EMU, 4 * EMU), "Main result"),
                (text_shape("Body", 0, EMU, W, EMU, "Use it"), "Close"),
                (text_shape("Body", 0, EMU, W, EMU, "Held back"), "If asked")]
        pptx(self.slides / "deck.pptx", good)
        code, r = self.deck(self.slides / "deck.pptx")
        self.assertEqual(code, 0, r)
        facts = r["files"][str(self.slides / "deck.pptx")]
        self.assertEqual((facts["slides"], facts["pictures"], facts["pictures_not_in_manifest"]), (4, 1, 0))
        self.assertTrue(any("NOT_RENDERED" in n for n in r["not_checked"]))
        self.assertTrue(any("build.json" in n for n in r["not_checked"]))
        self.assertTrue((self.slides / "deck-check.md").is_file())

        bad = [(text_shape("Title", 0, 0, W, EMU, "A title") + text_shape("Hidden", 0, 0, 0, EMU, "lost text"), ""),
               (text_shape("Body", W - EMU, 0, 2 * EMU, EMU, "runs off the edge", pt=14)
                + picture(0, 0, EMU // 2, EMU // 2), "Main result"),
               (text_shape("Body", 0, EMU, W, EMU, "Use it"), "Close")]
        pptx(self.slides / "deck.pptx", bad, media=b"another picture")
        code, r = self.deck(self.slides / "deck.pptx")
        self.assertEqual(code, 1)
        text = "\n".join(r["errors"] + r["flags"])
        for expected in ("3 slides, the plan has 4", "box of zero size", "extends beyond the slide",
                         "14 pt, under the 20 pt floor", "not a figure of figures/manifest.json",
                         "hard to read", "slide 1 has no notes"):
            self.assertIn(expected, text)
        self.assertEqual(r["files"][str(self.slides / "deck.pptx")]["smallest_pt"], 14)

    def test_beamer_frames_and_a_captured_log(self):
        tex = self.slides / "deck.tex"
        frames = "\n".join(r"\begin{frame}{T}" + "\nx\n" + r"\end{frame}" for _ in range(3))
        tex.write_text("\\begin{document}\n" + frames + "\n\\appendix\n\\begin{frame}{B}\n"
                       "\\includegraphics{figures/gone.png}\n\\end{frame}\n\\end{document}\n")
        code, r = self.deck(tex)
        self.assertTrue(any("no deck.log" in n for n in r["not_checked"]))
        self.assertIn("missing file: figures/gone.png", "\n".join(r["errors"]))
        tex.with_suffix(".log").write_text(CAPTURED_LOG)
        code, r = self.deck(tex)
        self.assertEqual(code, 1)
        errors = "\n".join(r["errors"])
        self.assertIn("file not found: figures/nosuchfig.png", errors)
        self.assertIn("undefined reference fig:none", errors)
        self.assertIn("overfull vbox, 113.232 pt (slide 4, line 12)", errors.replace("113.23177", "113.232"))
        self.assertIn("170.717 pt", errors.replace("170.71652", "170.717"))
        self.assertNotIn("3.1 pt", errors)                     # under the 5 pt limit
        self.assertTrue(any("another run" in n for n in r["not_checked"]))
        facts = r["files"][str(tex)]
        self.assertEqual((facts["frames"], facts["backup_frames"], facts["pages_in_log"]), (3, 1, 4))
        tex.write_text(tex.read_text().replace(r"\appendix", ""))       # the backup boundary is gone
        tex.with_suffix(".fdb_latexmk").write_text(f'  "deck.tex" 1 99 {"0" * 32} ""\n')
        code, r = self.deck(tex)
        self.assertIn("4 frames and 0 backup frames; the plan has 3 and 1", "\n".join(r["errors"]))
        self.assertTrue(any("earlier version" in n for n in r["not_checked"]))

    def test_a_plan_changed_after_the_build(self):
        (self.slides / "build.json").write_text(json.dumps({"plan_sha256": "0" * 64}))
        tex = self.slides / "deck.tex"
        tex.write_text("")
        code, r = self.deck(tex)
        self.assertIn("the plan changed after the deck was built", r["errors"][0])
        code, err = self.deck(self.slides / "nothing.pptx")
        self.assertEqual(code, 2)
        self.assertIn("not a .tex, .pdf or .pptx", err)

    @unittest.skipUnless(HAVE_PYMUPDF, "PyMuPDF is not installed")
    def test_pdf_page_count(self):
        try:
            import pymupdf as fitz
        except ImportError:
            import fitz
        doc = fitz.open()
        for _ in range(3):
            doc.new_page()
        doc.save(self.slides / "deck.pdf")
        code, r = self.deck(self.slides / "deck.pdf")
        self.assertIn("3 pages, the plan has 4 slides", r["errors"][0])


if __name__ == "__main__":
    unittest.main()
