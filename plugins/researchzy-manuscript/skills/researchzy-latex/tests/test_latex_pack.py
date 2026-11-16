"""latex_pack.py: which files go in, comment stripping, refusals, warnings and the rebuild.

The last test builds a small paper with latexmk, packs it and rebuilds the archive in an empty
folder; it skips when latexmk, pdflatex or bibtex is not installed.
"""
from __future__ import annotations

import importlib.util
import io
import json
import os
import shutil
import struct
import subprocess
import tarfile
import tempfile
import unittest
import zipfile
import zlib
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts" / "latex_pack.py"
spec = importlib.util.spec_from_file_location("latex_pack", SCRIPT)
lp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lp)

HAVE_TEX = all(shutil.which(tool) for tool in ("latexmk", "pdflatex", "bibtex"))
STYLE = "% mystyle.sty: a local style file, copied byte for byte\n\\RequirePackage{helper}\n"
MAIN = "\n".join([
    "% Draft 3: check the numbers with Ann before sending",
    r"\documentclass{article}",
    r"\usepackage{graphicx,url}",
    r"\usepackage{mystyle}",
    r"\begin{document}",
    r"\section{Introduction}\label{sec:intro} % TODO cite more",
    r"Half of them, 50\% in all, responded.% no space here",
    r"See \url{https://example.org/a%20b} and \verb|x % y|.",
    r"\input{sections/method}",
    r"\includegraphics{figures/plot}",
    r"\includegraphics{figures/size map}",
    r"\begin{verbatim}",
    r"keep % this",
    r"\end{verbatim}",
    r"\cite{lee2018}",
    r"\bibliographystyle{plain}",
    r"\bibliography{refs}",
    r"\end{document}", ""])


def png() -> bytes:
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    raw = b"".join(b"\x00" + b"\xff\x00\x00" * 2 for _ in range(2))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 2, 2, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = lp.main(list(argv))
    return code, (json.loads(out.getvalue()) if out.getvalue() else None), err.getvalue()


class PackTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.paper = self.dir / "paper"
        files = {"main.tex": MAIN, "sections/method.tex": "\\section{Method}% keep\nText. % drop\n",
                 "mystyle.sty": STYLE, "helper.sty": "% helper\n\\def\\helper{}\n",
                 "refs.bib": "@misc{lee2018, title={A}}\n",
                 "main.bbl": "\\begin{thebibliography}{1}\\bibitem{lee2018} A.\\end{thebibliography}\n",
                 "unused.tex": "\\section{Old}\n", "notes.txt": "names and plans\n", "main.aux": "\\relax\n",
                 "main.log": "log\n"}
        for name, text in files.items():
            path = self.paper / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        (self.paper / "figures").mkdir()
        (self.paper / "figures" / "plot.pdf").write_bytes(b"%PDF-1.4\n")
        (self.paper / "figures" / "plot.png").write_bytes(png())
        (self.paper / "figures" / "size map.png").write_bytes(png())
        self.out = self.dir / "build" / "source"

    def tearDown(self):
        self.tmp.cleanup()

    def pack(self, *extra, main="main.tex"):
        return run("pack", str(self.paper / main), "--out", str(self.out), *extra)

    def test_keeps_only_used_files_with_reasons(self):
        code, summary, err = self.pack()
        self.assertEqual(code, 0, err)
        kept = sorted(str(p.relative_to(self.out)) for p in self.out.rglob("*") if p.is_file())
        self.assertEqual(kept, ["figures/plot.pdf", "figures/size map.png", "helper.sty", "main.bbl", "main.tex",
                                "mystyle.sty", "refs.bib", "sections/method.tex"])
        manifest = (self.dir / "build" / "source.MANIFEST.md").read_text(encoding="utf-8")
        self.assertIn("| unused.tex | not used by the build |", manifest)
        self.assertIn("| main.aux | build output |", manifest)
        self.assertIn("| figures/plot.png | not used by the build |", manifest)   # .pdf comes first for pdfLaTeX
        self.assertIn("space in file name: figures/size map.png", summary["warnings"])

    def test_comments_are_stripped_safely(self):
        self.pack()
        text = (self.out / "main.tex").read_text(encoding="utf-8")
        self.assertNotIn("Draft 3", text)
        self.assertNotIn("TODO", text)
        self.assertIn(r"50\% in all, responded.%", text)
        self.assertIn(r"\url{https://example.org/a%20b}", text)
        self.assertIn(r"\verb|x % y|", text)
        self.assertIn("keep % this", text)
        self.assertTrue(text.startswith("\\documentclass"))
        self.assertEqual((self.out / "sections/method.tex").read_text(encoding="utf-8"), "\\section{Method}%\nText.\n")
        self.assertEqual((self.out / "mystyle.sty").read_text(encoding="utf-8"), STYLE)

    def test_keep_comments(self):
        _, summary, _ = self.pack("--keep-comments")
        self.assertEqual((self.out / "main.tex").read_text(encoding="utf-8"), MAIN)
        self.assertTrue(any("comments kept" in w for w in summary["warnings"]))

    def test_archives_hold_the_files_at_their_root(self):
        _, summary, _ = self.pack()
        tar_path, zip_path = map(Path, summary["archives"])
        with tarfile.open(tar_path) as tar:
            self.assertIn("main.tex", tar.getnames())
        with zipfile.ZipFile(zip_path) as archive:
            self.assertIn("sections/method.tex", archive.namelist())
        self.assertIn("latexmk -pdf -file-line-error -halt-on-error -interaction=nonstopmode main.tex",
                      summary["rebuild"][1])

    def test_refuses_to_overwrite(self):
        self.assertEqual(run("pack", str(self.paper / "main.tex"), "--out", str(self.paper))[0], 2)
        self.assertEqual(run("pack", str(self.paper / "main.tex"), "--out", str(self.dir))[0], 2)
        self.out.mkdir(parents=True)
        (self.out / "x").write_text("x")
        code, _, err = self.pack()
        self.assertEqual(code, 2)
        self.assertIn("not empty", err)
        (self.out / "x").unlink()
        (self.dir / "build" / "source.zip").write_text("old")
        self.assertEqual(self.pack()[0], 2)
        self.assertEqual((self.dir / "build" / "source.zip").read_text(), "old")

    def test_a_subfolder_of_the_project_is_allowed_and_skipped(self):
        self.out = self.paper / "latex-build" / "source"
        code, summary, _ = self.pack()
        self.assertEqual(code, 0)
        manifest = Path(summary["manifest"]).read_text(encoding="utf-8")
        self.assertNotIn("| latex-build/", manifest)
        self.assertTrue((self.out / "main.tex").is_file())

    def test_missing_and_unsafe_files_are_problems(self):
        text = MAIN.replace(r"\includegraphics{figures/plot}",
                            "\\includegraphics{figures/gone}\n\\includegraphics{/home/me/fig.png}")
        (self.paper / "main.tex").write_text(text, encoding="utf-8")
        code, summary, _ = self.pack()
        self.assertEqual(code, 1)
        self.assertTrue(any("figures/gone" in p and "not found" in p for p in summary["problems"]))
        self.assertTrue(any("absolute path" in p for p in summary["problems"]))

    def test_no_bbl_and_stale_bbl_warnings(self):
        (self.paper / "main.bbl").unlink()
        _, summary, _ = self.pack()
        self.assertTrue(any("no main.bbl" in w for w in summary["warnings"]))

    def test_bbl_only_rebuild_does_not_run_bibtex(self):
        (self.paper / "refs.bib").unlink()
        _, summary, _ = self.pack()
        self.assertIn("-bibtex-", summary["rebuild"][1])

    def test_fls_decides_and_outside_files_are_named(self):
        fls = self.paper / "main.fls"
        fls.write_text("\n".join([
            f"PWD {self.paper}", "INPUT /usr/local/texlive/2026/texmf-dist/tex/latex/base/article.cls",
            "INPUT main.tex", "INPUT ./main.aux", "INPUT sections/method.tex", "INPUT mystyle.sty",
            "INPUT helper.sty", "INPUT figures/plot.pdf", "INPUT figures/size map.png", "INPUT main.bbl",
            "INPUT /home/someone/texmf/tex/latex/private.sty", "OUTPUT main.log", ""]), encoding="utf-8")
        code, summary, _ = self.pack("--fls", str(fls))
        self.assertEqual(code, 0)
        self.assertTrue(any("personal or local TeX tree" in w and "private.sty" in w for w in summary["warnings"]))
        self.assertFalse(any("article.cls" in w for w in summary["warnings"]))
        self.assertTrue((self.out / "refs.bib").is_file())             # BibTeX's input is not in the .fls

    def test_size_warning(self):
        _, summary, _ = self.pack("--warn-size-mb", "0.000001")
        self.assertTrue(any("MB (over" in w for w in summary["warnings"]))

    @unittest.skipUnless(HAVE_TEX, "latexmk, pdflatex or bibtex is not installed")
    def test_real_build_pack_and_rebuild(self):
        (self.paper / "figures" / "plot.pdf").unlink()           # the fake PDF would not load; use the PNG
        (self.paper / "main.bbl").unlink()
        command = ["latexmk", "-pdf", "-file-line-error", "-halt-on-error", "-interaction=nonstopmode", "main.tex"]
        done = subprocess.run(command, cwd=self.paper, capture_output=True, text=True, timeout=300)
        self.assertEqual(done.returncode, 0, done.stdout[-2000:])
        code, summary, err = self.pack("--fls", str(self.paper / "main.fls"))
        self.assertEqual(code, 0, err)
        self.assertTrue((self.out / "main.bbl").is_file())
        script = " && ".join(summary["rebuild"][:2])
        env = dict(os.environ, TMPDIR=str(self.dir))
        done = subprocess.run(["bash", "-c", script + ' && echo "$tmp"'], capture_output=True, text=True,
                              timeout=300, env=env)
        self.assertEqual(done.returncode, 0, done.stdout[-2000:] + done.stderr[-2000:])
        rebuilt = Path(done.stdout.strip().splitlines()[-1])
        self.assertTrue((rebuilt / "main.pdf").is_file())
        self.assertNotIn("Citation", (rebuilt / "main.log").read_text(encoding="utf-8", errors="replace"))


if __name__ == "__main__":
    unittest.main()
