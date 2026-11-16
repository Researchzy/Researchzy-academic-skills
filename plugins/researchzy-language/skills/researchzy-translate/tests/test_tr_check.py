"""tr_check.py: each check in both directions (zh-en, en-zh), and the false alarms it tolerates."""
from __future__ import annotations

import importlib.util
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

SCRIPTS = Path(__file__).parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location("tr_check", SCRIPTS / "tr_check.py")
tc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tc)


def numbers(text: str, lang: str = "zh") -> list:
    return [n["raw"] for n in tc.facts(text, False, lang)["numbers"]]


class CheckTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, source: str, translation: str, pair: str = "zh-en", *extra, ext: str = ".md", command="check"):
        (self.dir / f"s{ext}").write_text(source, encoding="utf-8")
        (self.dir / f"t{ext}").write_text(translation, encoding="utf-8")
        out = io.StringIO()
        with redirect_stdout(out):
            code = tc.main([command, str(self.dir / f"s{ext}"), str(self.dir / f"t{ext}"), "--pair", pair,
                            "--out", str(self.dir / "translation"), *extra])
        return code, json.loads(out.getvalue())

    def found(self, source: str, translation: str, pair: str = "zh-en", *extra, ext: str = ".md") -> list:
        """[(check, severity, message)] for a source and a translation."""
        self.run_cli(source, translation, pair, *extra, ext=ext)
        report = json.loads((self.dir / "translation" / "translation-check.json").read_text(encoding="utf-8"))
        return [(f["check"], f["severity"], f["message"]) for f in report["findings"]]

    def assertClean(self, source: str, translation: str, pair: str = "zh-en", *checks: str, extra=()):
        hits = [f for f in self.found(source, translation, pair, *extra) if not checks or f[0] in checks]
        self.assertEqual(hits, [], f"{source!r} → {translation!r}")

    def assertFinds(self, source: str, translation: str, pair: str, check: str, severity: str, words: str, extra=()):
        hits = [f for f in self.found(source, translation, pair, *extra) if f[0] == check]
        self.assertTrue(any(f[1] == severity and words in f[2] for f in hits), f"{check} {severity} {words!r}: {hits}")

    # ---- numbers ----------------------------------------------------------------------------

    def test_numbers_are_found_next_to_han_characters(self):
        self.assertEqual(numbers("共纳入37名患者，其中12名（32.4%）为女性"), ["37", "12", "32.4%"])
        self.assertEqual(numbers("共纳入３７名患者，第3组，1,234例，0.5，.05"), ["37", "3", "1,234", "0.5", ".05"])
        self.assertEqual(numbers("COVID-19、IL-6、H2O、3D打印、type-2 diabetes", "en"), ["2"])   # names are not numbers
        self.assertEqual(numbers("A total of 1,204 patients (3.5 %) aged 18–65 years", "en"), ["1,204", "3.5 %", "18", "65"])
        self.assertEqual(numbers("Werte von 3,5 und 1.204", "de"), ["3,5", "1.204"])
        self.assertEqual(numbers("组间差异为-1.3分（95%CI：-2.0～-0.6）"), ["-1.3", "95%", "-2.0", "-0.6"])
        self.assertEqual([n["sign"] for n in tc.facts("was -1.3 (-2.0 to -0.6), range 0.91 -0.97", False, "en")["numbers"]],
                         ["-", "-", "-", "", ""])                    # a minus after a word; a range after a number
        self.assertEqual([n["canon"] for n in tc.facts("1.2万步与3亿元", False, "zh")["numbers"]], ["12000", "300000000"])

    def test_a_changed_or_lost_number_is_an_error_in_both_directions(self):
        self.assertFinds("共纳入37名患者。", "A total of 38 patients were enrolled.", "zh-en", "numbers", "error",
                         "37 is not in the translation")
        self.assertFinds("A total of 37 patients were enrolled.", "共纳入38名患者。", "en-zh", "numbers", "error",
                         "38 is in the translation but not in the source")
        self.assertClean("共纳入３７名患者，1.2万步，年龄18～65岁。", "We enrolled 37 patients, 12,000 steps, aged 18–65 years.")
        self.assertClean("Steps rose to 1.2 million, 37–40% of patients.", "步数增至120万，37%～40%的患者。", "en-zh")

    def test_percent_unit_and_bound_errors(self):
        self.assertFinds("其中12名（32.4%）为女性。", "Of them, 12 (32.4) were women.", "zh-en", "numbers", "error",
                         "percent sign is lost")
        self.assertFinds("The dose was 5 mg.", "剂量为5 g。", "en-zh", "numbers", "error", "the unit mg became g")
        self.assertFinds("差异有统计学意义（P<0.05）。", "The difference was significant (P > 0.05).", "zh-en",
                         "numbers", "error", "the bound < became >")
        self.assertClean("剂量为5mg，体温37℃，P<0.05。", "The dose was 5 mg, temperature 37 °C, P < 0.05.", "zh-en", "numbers")

    def test_number_warnings_that_tolerate_rewording(self):
        self.assertFinds("3组之间无差异。", "The three groups did not differ.", "zh-en", "numbers", "warning",
                         "3 is written as a word in the translation")
        self.assertFinds("Twelve patients withdrew.", "12名患者退出。", "en-zh", "numbers", "warning",
                         "12 is written as a word in the source")
        self.assertFinds("变化为−0.5 kg。", "Weight decreased by 0.5 kg.", "zh-en", "numbers", "warning", "minus sign")
        self.assertFinds("The ratio was 0.50.", "比值为0.5。", "en-zh", "numbers", "warning", "another precision")
        self.assertFinds("P<0.05。", "P was less than 0.05.", "zh-en", "numbers", "warning", "bound is a symbol on one side")
        # Tolerated: a unit symbol rendered as a unit word gives a warning, never an error.
        self.assertFinds("The dose was 5 mg.", "剂量为5毫克。", "en-zh", "numbers", "warning", "not written as a symbol")
        self.assertClean("剂量为5毫克。", "The dose was 5 mg.", "zh-en", "numbers")     # the translation made the unit explicit
        self.assertClean("新冠肺炎（COVID-19）患者", "patients with COVID-19", "zh-en", "numbers")

    # ---- dates -------------------------------------------------------------------------------

    def test_dates_are_compared_as_dates(self):
        self.assertClean("2024年3月至2024年6月，3月15日起。", "From March 2024 to June 2024, from 15 March on.", "zh-en", "dates", "numbers")
        self.assertClean("On March 15, 2024 and on 2024-06-01.", "于2024年3月15日和2024年6月1日。", "en-zh", "dates", "numbers")
        self.assertFinds("2024年3月开始。", "It started in April 2024.", "zh-en", "dates", "error", "2024-03")
        self.assertFinds("It started in March 2024.", "2024年4月开始。", "en-zh", "dates", "error", "not in the source: 2024-04")
        self.assertEqual(tc.facts("We may see this in May 2024.", False, "en")["dates"], ["2024-05"])   # "may" is a verb

    # ---- citations, LaTeX, formulas, placeholders, links -------------------------------------

    def test_citations(self):
        self.assertClean("研究[@liu2022]显示，见@smith2020与[1–3]。", "Studies [@liu2022] show, see @smith2020 and [1, 2, 3].",
                         "zh-en", "citations")
        self.assertFinds("如\\cite{a,b}所示。", "As shown \\cite{a}.", "zh-en", "citations", "error", "not in the translation: b")
        self.assertFinds("As shown in [3].", "如[4]所示。", "en-zh", "citations", "error", "not in the source: 4")
        self.assertClean("既往研究［1，2］表明。", "Earlier studies [1, 2] showed this.", "zh-en", "citations", "numbers")

    def test_latex_commands_keys_and_braces(self):
        src = "见图~\\ref{fig:a}与\\textbf{结果}\\label{sec:r}。"
        self.assertClean(src, "See Figure~\\ref{fig:a} and \\textbf{results}\\label{sec:r}.", "zh-en", "latex")
        self.assertFinds(src, "See Figure~\\ref{fig:b} and \\textbf{results}\\label{sec:r}.", "zh-en", "latex", "error", "fig:b")
        self.assertFinds("See \\textbf{results}.", "见结果。", "en-zh", "latex", "error", "textbf")
        hits = self.found("见\\textbf{结果}。", "See \\textbf{results.", "zh-en", ext=".tex")
        self.assertIn(("latex", "error", "unbalanced braces: { minus } is 0 in the source, 1 here"), hits)

    def test_formulas_and_code_are_byte_equal(self):
        self.assertFinds("显著性水平为$\\alpha = 0.05$。", "Significance was $\\alpha=0.05$.", "zh-en", "maths", "error", "alpha")
        self.assertFinds("Run `fit(x)`.", "运行`fit(y)`。", "en-zh", "maths", "error", "`fit(y)`")
        self.assertClean("其中$y$为总分。", "where $y$ is the total score.", "zh-en", "maths")

    def test_placeholders_keep_type_and_count(self):
        self.assertClean("[Author input needed: 伦理批准号]", "[Author input needed: ethics approval number]", "zh-en", "placeholders")
        self.assertFinds("[Citation needed: 一项试验]", "[Author input needed: a trial]", "zh-en", "placeholders", "error", "citation")
        self.assertFinds("A claim [Evidence needed: a cohort].", "一个论断。", "en-zh", "placeholders", "error", "evidence")

    def test_links(self):
        self.assertClean("见 https://example.org/a 与 doi:10.1000/XYZ。", "See https://example.org/a and doi:10.1000/xyz.",
                         "zh-en", "links")
        self.assertFinds("See https://example.org/a.", "见 https://example.org/b。", "en-zh", "links", "error", "example.org/b")

    def test_figure_table_and_equation_numbers(self):
        self.assertClean("如图2和图3所示，见附表1与式(3)，表S2。",
                         "As shown in Figures 2 and 3; see Supplementary Table 1 and Eq. (3), Table S2.", "zh-en", "figures", "numbers")
        self.assertClean("As shown in Fig. 2a and Table S1.", "如图2a和表S1所示。", "en-zh", "figures", "numbers")
        self.assertFinds("如图2所示。", "As shown in Figure 3.", "zh-en", "figures", "error", "figure 2")
        self.assertFinds("See Table 1.", "见表2。", "en-zh", "figures", "error", "table 2")
        self.assertEqual(tc.facts("这代表2种结果。", False, "zh")["figures"], [])        # 代表 is not 表

    # ---- glossary ----------------------------------------------------------------------------

    def glossary(self, rows: str) -> str:
        path = self.dir / "terms.tsv"
        path.write_text("term\ttranslation\tfield\tnote\n" + rows, encoding="utf-8")
        return str(path)

    def test_glossary_terms_in_both_directions(self):
        terms = self.glossary("睡眠潜伏期\tsleep onset latency\tsleep\t\n限时进食\ttime-restricted eating|TRE\tnutrition\t\n"
                              "睡眠效率\tsleep efficiency\tsleep\t\nPSQI\t\tsleep\t=\n")
        hits = self.found("限时进食缩短睡眠潜伏期，PSQI改善。", "Time restricted eating shortened sleep efficiency; the "
                          "Pittsburgh index improved.", "zh-en", "--glossary", terms)
        messages = [m for check, _, m in hits if check == "glossary"]
        self.assertEqual(len(messages), 2, hits)                       # 限时进食 matched despite case and hyphen
        self.assertIn("睡眠潜伏期: sleep onset latency is not in the translation; it has sleep efficiency, the glossary's "
                      "translation of 睡眠效率", messages)
        self.assertIn("PSQI is marked keep-as-is (=) but is not in the translation", messages)
        terms = self.glossary("sleep latency\t睡眠潜伏期\tsleep\t\n")
        self.assertClean("Sleep latencies were shorter.", "睡眠潜伏期缩短。", "en-zh", "glossary",
                         extra=("--glossary", terms))                                       # plural, capital
        self.assertFinds("Sleep latency was shorter.", "入睡时间缩短。", "en-zh", "glossary", "warning", "睡眠潜伏期",
                         extra=("--glossary", terms))

    def test_glossary_problems_and_missing_glossary(self):
        terms = self.glossary("睡眠质量\tsleep quality\t\t\n睡眠品质\tsleep quality\t\t\n效应\t\t\t\n")
        messages = [m for check, _, m in self.found("一句话。", "One sentence.", "zh-en", "--glossary", terms)]
        self.assertIn("one translation for two terms: 睡眠质量 and 睡眠品质 are both sleep quality", messages)
        self.assertTrue(any("效应 has no translation" in m for m in messages))
        _, summary = self.run_cli("一句话。", "One sentence.")
        self.assertEqual(summary["not_checked"]["glossary"], "no --glossary given")
        (self.dir / "bad.tsv").write_text("a\tb\n", encoding="utf-8")
        with self.assertRaises(SystemExit) as raised, redirect_stderr(io.StringIO()):
            self.run_cli("一句话。", "One sentence.", "zh-en", "--glossary", str(self.dir / "bad.tsv"))
        self.assertEqual(raised.exception.code, 2)

    # ---- length, negation, hedges, script, commentary -----------------------------------------

    def test_length_against_the_median(self):
        source = "\n\n".join(["本研究在三家医院招募了成年参与者，并在基线和十二周时评估了睡眠质量与体重变化。"] * 4)
        translation = "\n\n".join(["Adult participants were recruited at three hospitals, and sleep quality and weight "
                                   "change were assessed at baseline and at twelve weeks."] * 3 + ["Adults were recruited."])
        self.assertFinds(source, translation, "zh-en", "length", "warning", "content may be missing")
        _, summary = self.run_cli("短句。", "Short.")
        self.assertEqual(summary["not_checked"]["length"], "fewer than 3 units of 30 or more characters")

    def test_negation_in_both_directions(self):
        self.assertClean("未见不良事件，差异无统计学意义。", "No adverse events were seen, and the difference was not significant.",
                         "zh-en", "negation")
        self.assertFinds("但并非所有患者均获益。", "All patients benefited.", "zh-en", "negation", "warning", "并非")
        self.assertFinds("The difference was not significant.", "差异有统计学意义。", "en-zh", "negation", "warning", "not")
        self.assertClean("不同组别非常相似，是否获益无论如何。", "The different groups were very similar.", "zh-en", "negation")
        # Tolerated: lexical negation in English (uncertain, non-) is not counted, so it warns.
        self.assertFinds("结果不确定。", "The result is uncertain.", "zh-en", "negation", "warning", "不")

    def test_hedges_in_both_directions(self):
        self.assertClean("结果提示可能改善，约9.1分钟。", "The results suggest it may improve, by about 9.1 minutes.", "zh-en", "hedges")
        self.assertFinds("限时进食可能改善睡眠。", "Time-restricted eating improves sleep.", "zh-en", "hedges", "warning", "可能")
        self.assertFinds("It may reduce weight by approximately 2 kg.", "它使体重减轻2 kg。", "en-zh", "hedges", "warning", "may")
        self.assertClean("始于2024年5月。", "It began in May 2024.", "zh-en", "hedges")            # the month is not a hedge
        # Tolerated: 提示 rendered as "indicate" is counted on one side only.
        self.assertFinds("结果提示有效。", "The results indicate an effect.", "zh-en", "hedges", "warning", "提示")

    def test_script_left_in_the_wrong_language(self):
        self.assertFinds("采用匹兹堡睡眠质量指数。", "We used the 匹兹堡 index，as planned.", "zh-en", "script", "warning", "匹 兹 堡 ，")
        self.assertFinds("Participants did not report any adverse events during the study.",
                         "参与者 did not report any adverse events during the study。", "en-zh", "script", "warning",
                         "lowercase Latin words")
        self.assertClean("We used the Pittsburgh Sleep Quality Index.", "采用Pittsburgh Sleep Quality Index（PSQI）。",
                         "en-zh", "script")                                                   # names are carried over
        # Tolerated: an English title kept in the Chinese text is reported.
        self.assertFinds("See the trial.", "见 the effect of eating on sleep in adults 一文。", "en-zh", "script", "warning", "Latin")
        _, summary = self.run_cli("一句话。", "Одно предложение.", "zh-ru")
        self.assertEqual(summary["not_checked"]["script"], "no rule for ru")

    def test_commentary(self):
        self.assertFinds("方法。", "Here is the translation: Methods.", "zh-en", "commentary", "warning", "Here is the translation")
        self.assertFinds("Methods.", "以下是译文：方法。", "en-zh", "commentary", "warning", "以下是译文")
        self.assertClean("此处我们发现。", "Here, we show this.", "zh-en", "commentary")

    # ---- pairing, other pairs, output, exit codes -------------------------------------------

    def test_units_without_a_counterpart_are_not_compared(self):
        code, summary = self.run_cli("# 方法\n\n共纳入37名患者。\n\n随访12周。\n",
                                     "# Methods\n\nNote from the translator.\n\nWe enrolled 37 patients.\n\nFollow-up was 12 weeks.\n")
        self.assertEqual(summary["units"]["compared"], 3)
        self.assertEqual(summary["not_compared"], {"source": [], "translation": ["u0002"]})
        self.assertEqual(summary["errors"], 0)

    def test_other_language_pairs_get_the_invariant_checks_only(self):
        hits = self.found("37人の患者を登録した（2024年3月）。", "We enrolled 38 patients (March 2024).", "ja-en")
        self.assertIn(("numbers", "error", "37 is not in the translation"), hits)
        _, summary = self.run_cli("37人。", "37 people.", "ja-en")
        self.assertEqual(summary["not_checked"]["negation"], "only for zh-en and en-zh")

    def test_strict_exit_code_table_and_bad_input(self):
        self.assertEqual(self.run_cli("共纳入37名患者。", "We enrolled 38 patients.", "zh-en", "--strict")[0], 1)
        self.assertEqual(self.run_cli("共纳入37名患者。", "We enrolled 38 patients.")[0], 0)
        self.assertEqual(self.run_cli("共纳入37名患者。", "We enrolled 37 patients.", "zh-en", "--strict")[0], 0)
        code, summary = self.run_cli("# 方法\n\n共纳入37名患者。\n", "# Methods\n\nWe enrolled 38 patients.\n", command="table")
        table = (self.dir / "translation" / "bilingual.md").read_text(encoding="utf-8")
        self.assertIn("| u0002 | 共纳入37名患者。 | We enrolled 38 patients. | error: 37 is not in the translation; "
                      "error: 38 is in the translation but not in the source |", table)
        # A translation unit without a source keeps its own issues, apart from the source unit with the same id.
        self.run_cli("# 方法\n\n共纳入37名患者。\n", "Here is the translation:\n\n# Methods\n\nWe enrolled 37 patients.\n",
                     command="table")
        table = (self.dir / "translation" / "bilingual.md").read_text(encoding="utf-8")
        self.assertIn("| u0001 | 方法 | Methods |  |", table)
        self.assertIn("| — | (no source unit) | Here is the translation: | warning: words to the reader: Here is the "
                      "translation |", table)
        for argv in (["check", "missing.md", "t.md", "--pair", "zh-en"], ["check", "s.md", "t.md", "--pair", "chinese"]):
            with self.assertRaises(SystemExit) as raised, redirect_stderr(io.StringIO()):
                tc.main([argv[0], str(self.dir / argv[1]), str(self.dir / argv[2]), *argv[3:]])
            self.assertEqual(raised.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
