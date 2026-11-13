"""latex_guard.py: safe comment stripping, snapshots, the content comparison and the override scan."""
from __future__ import annotations

import importlib.util
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts" / "latex_guard.py"
spec = importlib.util.spec_from_file_location("latex_guard", SCRIPT)
lg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lg)

MAIN = r"""\documentclass[11pt]{article}
\usepackage{graphicx}
\usepackage{natbib}
\title{Dose and response}
\begin{document}
\maketitle
\section{Introduction}\label{sec:intro}
Dose-finding studies are common \citep{smith2020,lee2018}. % a note to self
We give $n = 40$ doses and 50\% respond.
\input{sections/method}
\begin{figure}[t]
  \includegraphics[width=\linewidth]{figures/plot}
  \caption{Response against dose.}\label{fig:plot}
\end{figure}
\bibliographystyle{plainnat}
\bibliography{refs}
\end{document}
"""
METHOD = r"""\section{Method}\label{sec:method}
Participants were assigned at random \citet{lee2018}.
\begin{equation} y = a + b x \label{eq:model} \end{equation}
"""


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = lg.main(list(argv))
    return code, out.getvalue(), err.getvalue()


class StripCommentsTests(unittest.TestCase):
    def strip(self, text, keep_lines=False):
        return lg.strip_comments(text, keep_lines)

    def test_escaped_percent_is_text(self):
        self.assertEqual(self.strip(r"50\% of them % note"), r"50\% of them")
        self.assertEqual(self.strip("a\\\\% note"), "a\\\\%")      # \\ is a line break; the % after it is a comment

    def test_percent_ending_a_line_after_text_is_kept(self):
        self.assertEqual(self.strip("dose.% no space here\nNext"), "dose.%\nNext")
        self.assertEqual(self.strip("\\newcommand{\\x}{%\n  y}"), "\\newcommand{\\x}{%\n  y}")

    def test_comment_lines_are_dropped_or_blanked(self):
        text = "one\n% a whole comment line\n  % indented\ntwo\n"
        self.assertEqual(self.strip(text), "one\ntwo\n")
        self.assertEqual(self.strip(text, keep_lines=True), "one\n\n\ntwo\n")

    def test_verbatim_like_environments_are_untouched(self):
        for env in ("verbatim", "lstlisting", "minted", "filecontents*", "comment"):
            with self.subTest(env=env):
                text = f"\\begin{{{env}}}\nx = 1 % kept\n\\end{{{env}}} % gone\n"
                self.assertEqual(self.strip(text), f"\\begin{{{env}}}\nx = 1 % kept\n\\end{{{env}}}\n")

    def test_inline_verbatim_and_urls(self):
        self.assertEqual(self.strip(r"\verb|50%| and \verb*+a%b+ % c"), r"\verb|50%| and \verb*+a%b+")
        self.assertEqual(self.strip(r"\lstinline{a%b} % c"), r"\lstinline{a%b}")
        self.assertEqual(self.strip(r"\url{http://x.org/a%20b} % c"), r"\url{http://x.org/a%20b}")
        self.assertEqual(self.strip(r"\href{http://x.org/a%20b}{text} % c"), r"\href{http://x.org/a%20b}{text}")

    def test_crlf_line_endings_survive(self):
        self.assertEqual(self.strip("a % c\r\nb\r\n"), "a\r\nb\r\n")


class GuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.paper = self.dir / "paper"
        self.write(MAIN, METHOD)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, main, method):
        (self.paper / "sections").mkdir(parents=True, exist_ok=True)
        (self.paper / "main.tex").write_text(main, encoding="utf-8")
        (self.paper / "sections" / "method.tex").write_text(method, encoding="utf-8")

    def snap(self, name):
        code, out, err = run("snapshot", str(self.paper / "main.tex"), "-o", str(self.dir / name))
        self.assertEqual(code, 0, err)
        return json.loads((self.dir / name).read_text(encoding="utf-8"))

    def compare(self, *extra):
        code, out, _ = run("compare", str(self.dir / "before.json"), str(self.dir / "after.json"),
                           "--out", str(self.dir / "out"), *extra)
        return code, json.loads(out)

    def test_snapshot_records_the_content(self):
        snap = self.snap("before.json")
        self.assertEqual([f["path"] for f in snap["files"]], ["main.tex", "sections/method.tex"])
        self.assertEqual([l["key"] for l in snap["labels"]], ["sec:intro", "fig:plot", "sec:method", "eq:model"])
        self.assertEqual([c["key"] for c in snap["citations"]], ["smith2020", "lee2018", "lee2018"])
        self.assertEqual(snap["citations"][2]["at"], "sections/method.tex:2")
        self.assertEqual([g["target"] for g in snap["graphics"]], ["figures/plot"])
        self.assertEqual([s["title"] for s in snap["sections"]], ["Introduction", "Method"])
        self.assertEqual(snap["floats"], {"figure": 1})
        self.assertEqual({b["value"] for b in snap["bibliography"]}, {"plainnat", "refs"})
        self.assertEqual([p["name"] for p in snap["packages"]], ["graphicx", "natbib"])
        # Title 3, Introduction 1, sentence 4, "We give MATH doses and 50 respond" 7, caption 3, Method 1, 5, MATH 1
        self.assertEqual(snap["words"], 25)

    def test_snapshot_refuses_to_overwrite(self):
        self.snap("before.json")
        code, _, err = run("snapshot", str(self.paper / "main.tex"), "-o", str(self.dir / "before.json"))
        self.assertEqual(code, 2)
        self.assertIn("exists", err)

    def test_unchanged_paper_passes(self):
        self.snap("before.json")
        self.write(MAIN.replace("% a note to self", "% another note"), METHOD)
        self.snap("after.json")
        code, result = self.compare()
        self.assertEqual((code, result["content_changed"]), (0, False))
        self.assertEqual(result["files"]["changed"], ["main.tex"])

    def test_a_mechanical_fix_passes(self):
        self.snap("before.json")
        self.write(MAIN.replace("\\usepackage{natbib}", "\\usepackage{natbib}\n\\usepackage{booktabs}"), METHOD)
        self.snap("after.json")
        code, result = self.compare()
        self.assertEqual(code, 0)
        self.assertEqual(result["added"]["packages"], ["booktabs"])

    def test_removed_citation_is_a_content_change(self):
        self.snap("before.json")
        self.write(MAIN.replace("\\citep{smith2020,lee2018}", "\\citep{smith2020}"), METHOD)
        self.snap("after.json")
        code, result = self.compare()
        self.assertEqual(code, 1)
        self.assertEqual(result["removed"]["citations"], ["lee2018"])

    def test_commented_out_figure_is_a_content_change(self):
        self.snap("before.json")
        self.write(MAIN.replace("  \\includegraphics", "  %\\includegraphics"), METHOD)
        self.snap("after.json")
        code, result = self.compare()
        self.assertEqual(code, 1)
        self.assertEqual(result["removed"]["graphics"], ["figures/plot"])

    def test_renamed_section_and_dropped_float(self):
        self.snap("before.json")
        main = MAIN.replace("\\section{Introduction}", "\\section{Background}")
        main = main[:main.index("\\begin{figure}")] + main[main.index("\\end{figure}") + len("\\end{figure}"):]
        self.write(main, METHOD)
        self.snap("after.json")
        code, result = self.compare()
        self.assertEqual(code, 1)
        self.assertEqual(result["removed"]["sections"], ["section: Introduction"])
        self.assertEqual(result["removed"]["floats"], {"figure": 1})
        self.assertIn("fig:plot", result["removed"]["labels"])

    def test_word_count_tolerance(self):
        self.snap("before.json")
        self.write(MAIN, METHOD.replace("at random", "at random here"))
        self.snap("after.json")
        self.assertEqual(self.compare()[0], 0)                      # one word, within the 2-word floor
        self.write(MAIN, METHOD.replace("Participants were assigned at random", "Assigned"))
        (self.dir / "after.json").unlink()
        self.snap("after.json")
        code, result = self.compare()
        self.assertEqual((code, result["words"]["delta"]), (1, -4))
        self.assertEqual(self.compare("--tolerance", "20")[0], 0)

    def test_a_corrected_figure_path_is_not_a_content_change(self):
        (self.paper / "figures").mkdir()
        (self.paper / "figures" / "plot.pdf").write_bytes(b"%PDF-1.4\n")
        self.write(MAIN.replace("{figures/plot}", "{figures/plt}"), METHOD)
        self.snap("before.json")
        self.write(MAIN, METHOD)
        self.snap("after.json")
        code, result = self.compare()
        self.assertEqual((code, result["graphics_path_fixes"]), (0, [["figures/plt", "figures/plot"]]))

    def test_replacing_an_existing_figure_is_a_content_change(self):
        (self.paper / "figures").mkdir()
        for name in ("plot.pdf", "other.pdf"):
            (self.paper / "figures" / name).write_bytes(b"%PDF-1.4\n")
        self.snap("before.json")
        self.write(MAIN.replace("{figures/plot}", "{figures/other}"), METHOD)
        self.snap("after.json")
        code, result = self.compare()
        self.assertEqual((code, result["removed"]["graphics"]), (1, ["figures/plot"]))

    def test_an_added_layout_override_is_reported_as_a_change(self):
        self.snap("before.json")
        self.write(MAIN.replace("\\maketitle", "\\maketitle\n\\vspace{-2mm}"), METHOD)
        self.snap("after.json")
        code, result = self.compare()
        self.assertEqual(code, 1)
        self.assertTrue(any("layout override added: negative_space" in r for r in result["reasons"]))

    def test_compare_needs_snapshots(self):
        (self.dir / "x.json").write_text("{}")
        self.assertEqual(run("compare", str(self.dir / "x.json"), str(self.dir / "x.json"))[0], 2)


class OverrideTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def scan(self, text):
        (self.dir / "main.tex").write_text(text, encoding="utf-8")
        code, out, _ = run("overrides", str(self.dir / "main.tex"), "--out", str(self.dir / "out"))
        self.assertEqual(code, 0)
        return [(item["kind"], item["at"]) for item in json.loads(out)["overrides"]]

    def test_each_kind_with_its_line(self):
        found = self.scan("\n".join([
            r"\documentclass{article}",                               # 1
            r"\usepackage[margin=1cm]{geometry}",                     # 2
            r"\renewcommand{\baselinestretch}{0.95}",                 # 3
            r"\setlength{\textfloatsep}{4pt}",                        # 4
            r"\begin{document}",                                      # 5
            r"Text \vspace{-3mm} more.",                              # 6
            r"\looseness=-1 A paragraph.",                            # 7
            r"\enlargethispage{2\baselineskip}",                      # 8
            r"\resizebox{\linewidth}{!}{x}",                          # 9
            r"\linespread{0.9}\selectfont",                           # 10
            r"% \vspace{-5mm} only a comment",                        # 11
            r"\end{document}"]))
        self.assertEqual(found, [("margins", "main.tex:2"), ("line_spacing", "main.tex:3"),
                                 ("float_or_display_spacing", "main.tex:4"), ("negative_space", "main.tex:6"),
                                 ("looseness", "main.tex:7"), ("enlargethispage", "main.tex:8"),
                                 ("scaled_text", "main.tex:9"), ("line_spacing", "main.tex:10")])

    def test_size_switches_for_a_whole_float_or_the_rest_of_the_text(self):
        found = self.scan("\n".join([
            r"\documentclass{article}",                               # 1
            r"\begin{document}",                                      # 2
            r"\begin{table}",                                         # 3
            r"\centering\small",                                      # 4: whole float
            r"\caption{{\footnotesize A note}}",                      # 5: inside a group, fine
            r"\begin{tabular}{l}\scriptsize a\end{tabular}",          # 6: one cell, fine
            r"\end{table}",                                           # 7
            r"Some text {\small in a group} here.",                   # 8: fine
            r"\begin{figure}\begin{footnotesize}x\end{footnotesize}\end{figure}",  # 9: environment form
            r"\small",                                                # 10: rest of the document
            r"\end{document}"]))
        self.assertEqual(found, [("font_size", "main.tex:4"), ("font_size", "main.tex:9"), ("font_size", "main.tex:10")])

    def test_writes_overrides_md(self):
        self.scan("\\documentclass{article}\n\\begin{document}\nx\n\\end{document}\n")
        self.assertIn("None found.", (self.dir / "out" / "overrides.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
