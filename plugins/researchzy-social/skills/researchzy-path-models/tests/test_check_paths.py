"""check_paths.py: registration before the first estimate, the recorded paths, the registered model and its
re-specifications, and the wording, probes and numbers of the text in English and Chinese, on the PM-1 task."""
from __future__ import annotations

import copy
import importlib.util
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

SCRIPTS = Path(__file__).parents[1] / "scripts"


def load(name: str, alias: str):
    spec = importlib.util.spec_from_file_location(alias, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cp = load("check_paths", "check_paths_under_test")

MEDIATION = "mng ~ a*aut + age + female\neng ~ b*mng + cp*aut + age + female\nind := a*b"
MODERATED = "mng ~ a1*aut + a2*sup + a3*aut:sup + age + female\neng ~ b*mng + cp*aut + age + female"
LATENT = "AUT =~ aut1 + aut2 + aut3\nMNG =~ mng1 + mng2 + mng3\nENG =~ eng1 + eng2 + eng3\nMNG ~ a*AUT\nENG ~ b*MNG + cp*AUT"
MODEL = f"""# Model: autonomy, meaning and engagement

- Design: cross-sectional (one survey wave)
- Probe values of sup: 16th, 50th and 84th percentiles of the analysed rows

| Role | Column | Names in the text |
|---|---|---|
| X | aut | autonomy; 自主性 |
| M | mng | meaning; 意义感 |
| W | sup | supervisor support; high support; 领导支持; 高支持 |
| Y | eng | engagement; 投入 |
| covariate | age | age; 年龄 |

```model mediation
{MEDIATION}
```

```model moderated
{MODERATED}
```

```model latent
{LATENT}
```
"""


def coefficient(lhs, term, value, low, high, std=None, p=1e-6, t=7.0):
    return {"lhs": lhs, "term": term, "value": value, "se": 0.05, "t": t, "p": p, "low": low, "high": high, "std": std}


A, B, CP, A1, A3 = 0.3582, 0.3058, 0.0747, 0.3700, 0.0888
COEFFICIENTS = {"a": coefficient("mng", "aut", A, 0.2578, 0.4585, 0.3678, t=7.02),
                "b": coefficient("eng", "mng", B, 0.2191, 0.3925, 0.3853, t=6.94),
                "cp": coefficient("eng", "aut", CP, -0.0091, 0.1585, 0.0967, p=0.0804, t=1.75)}
EQUATIONS = {"mng": {"n": 314, "n_alone": 322, "df_resid": 310}, "eng": {"n": 314, "n_alone": 314, "df_resid": 309}}
INTERVAL = {"method": "percentile", "level": 0.95, "draws": 5000, "seed": 20261118, "failed": 0, "resampled": "cases"}
NO_RHO = {"status": "not_done", "reason": "R and its mediation package are not installed"}
MED = {"kind": "mediation", "model": MEDIATION, "n": 314, "equations": EQUATIONS, "coefficients": COEFFICIENTS,
       "defined": {"ind": {"expression": "a*b", "estimate": A * B, "se": 0.022, "low": 0.0701, "high": 0.1561}},
       "interval": INTERVAL, "sensitivity": NO_RHO}
SUPPORT = {"column": "sup", "min": 1.0, "max": 7.0, "mean": 6.104, "sd": 1.251, "p16": 5.25, "p50": 6.5, "p84": 7.0}
MOD_COEFFICIENTS = {"a1": coefficient("mng", "aut", A1, 0.27, 0.47), "a3": coefficient("mng", "aut:sup", A3, 0.014, 0.1636,
                                                                                      p=0.0201, t=2.34),
                    "b": COEFFICIENTS["b"], "cp": COEFFICIENTS["cp"]}
SLOPES = [{"label": f"{w:g}", "w": w, "in_range": True, "slope": A1 + A3 * (w - 6.104), "se": 0.06, "t": 5.0, "p": 1e-6,
           "low": 0.1, "high": 0.6} for w in (5.25, 6.5, 7.0)]
MOD = {"kind": "moderation", "model": MODERATED, "n": 314, "equations": {**EQUATIONS, "mng": {"n": 314, "df_resid": 308}},
       "coefficients": MOD_COEFFICIENTS, "centring": {"columns": {"aut": 4.47, "sup": 6.104}, "around": "mean of the 314 rows"},
       "b3_uncentred": A3, "moderator": SUPPORT, "focal": "a1", "interaction": "a3",
       "probe": {"b1": A1, "b3": A3, "df": 308, "slopes": SLOPES,
                 "jn": {"roots": [-19.98, 4.01], "roots_in_range": [False, True], "summary": "from 4.01 to 7"}}}
CONDITIONAL = {f"at {w:g}": {"expression": f"(a1 + a3*({w} - 6.104))*b", "estimate": (A1 + A3 * (w - 6.104)) * B,
                             "low": 0.05, "high": 0.19, "at": w} for w in (5.25, 6.5, 7.0)}
IMM = {"kind": "moderated_mediation", "model": MODERATED, "n": 314, "equations": EQUATIONS, "coefficients": MOD_COEFFICIENTS,
       "centring": MOD["centring"], "moderator": SUPPORT, "index": "index", "interval": INTERVAL, "sensitivity": NO_RHO,
       "defined": {"index": {"expression": "a3*b", "estimate": A3 * B, "low": 0.0085, "high": 0.0464}, **CONDITIONAL}}
SEM = {"kind": "sem", "model": LATENT, "n": 350, "converged": True, "df": 32,
       "fit": {"chi2": 86.36, "chi2_p": 1e-7, "cfi": 0.961, "tli": 0.944, "rmsea": 0.072, "srmr": 0.035},
       "coefficients": {"a": {"lhs": "MNG", "term": "AUT", "value": 0.5316, "se": 0.06, "z": 8.8, "p": 1e-9, "std": 0.48}}}

GOOD = """# Results

In the 314 respondents with complete data, autonomy was associated with meaning (a = 0.36, 95% CI 0.26 to 0.46;
t(310) = 7.02, p < 0.001), and meaning with engagement when autonomy was held constant (b = 0.31, β = 0.39). The
indirect effect was 0.11 (95% CI 0.07 to 0.16; percentile bootstrap of cases, 5000 draws, seed 20261118) and the direct
effect c′ = 0.07. These estimates are consistent with the hypothesised paths; one survey wave cannot order them in time.

At the 16th, 50th and 84th percentiles of supervisor support (5.25, 6.5 and 7), the conditional indirect effect was
0.09, 0.12 and 0.14; the index of moderated mediation was 0.027 (95% CI 0.009 to 0.046).

The registered latent model gave χ²(32) = 86.36, CFI = 0.961, RMSEA = 0.072 and SRMR = 0.035.
"""
GOOD_ZH = """# 结果

在314名数据完整的受访者中，自主性与意义感正相关（a路径系数为0.36，95% CI [0.26, 0.46]）。间接效应为0.11（95% CI [0.07, 0.16]），
与假设的路径一致。有调节的中介指数为0.027（95% CI [0.009, 0.046]）。我们不使用Sobel检验，横截面数据也不能证明自主性导致投入。
"""
DRAFT = """# Results

Autonomy leads to engagement through meaning (Sobel z = 3.1), indicating full mediation; the effect is stronger at
high support (+1 SD).

The indirect effect was 0.15 (95% CI 0.07 to 0.16).
"""
DRAFT_ZH = """# 结果

自主性通过意义感导致投入（Sobel z＝3.1），表明完全中介；在高支持（+1 SD）时效应更强。

间接效应为0.15（95% CI [0.07, 0.16]）。
"""


class CheckPathsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = os.getcwd()
        os.chdir(self.tmp.name)
        Path("paths").mkdir()
        Path("data.csv").write_text("id,aut,mng,sup,eng\n1,4,4,6,5\n", encoding="utf-8")
        Path("analysis.py").write_text("print('paths')\n", encoding="utf-8")
        Path("paths/model.md").write_text(MODEL, encoding="utf-8")

    def tearDown(self):
        os.chdir(self.old)
        self.tmp.cleanup()

    def run_main(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cp.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def register(self, *argv):
        return self.run_main("register", "paths/model.md", *argv)

    def build(self, results=None, register=True, dropped=()):
        """Register model.md, then record the results (id, extra) and the dropped fits (id, extra, reason)."""
        if register:
            self.assertEqual(self.register()[0], 0)
        rz = load("rz_results", "rz_results_for_check")
        rz.OUT = "paths"
        results = results if results is not None else [("indirect", MED), ("a3", MOD), ("index", IMM),
                                                       ("sem_registered", SEM)]
        for rid, extra, *reason in list(results) + [(rid, extra, reason) for rid, extra, reason in dropped]:
            values = [v for v in (extra.get("defined") or {}).values() if v.get("low") is not None]
            head = values[0] if values else next(iter(extra.get("coefficients", {}).values()), {"value": 1.0})
            rz.record(id=rid, question="Is autonomy associated with engagement through meaning?", family=rid,
                      role="primary", test="path model", unit="respondent", n=extra.get("n", 314),
                      estimate={"name": rid, "value": head.get("estimate", head.get("value")), "units": "points"},
                      extra={"paths": extra}, kept=not reason, reason=reason[0] if reason else None)
        with redirect_stdout(io.StringIO()):
            rz.finish(script="analysis.py", data=["data.csv"], seed=20261118, settings={"draws": 5000})

    def check(self, *texts, argv=()):
        names = []
        for i, text in enumerate(texts):
            names.append(f"text{i}.md")
            Path(names[-1]).write_text(text, encoding="utf-8")
        code, out, _ = self.run_main(*argv, *(["--text", *names] if names else []))
        summary = json.loads(out) if out else None
        return code, summary

    def problems(self, summary, name):
        return "\n".join(p for p in summary["problems"] if p.startswith(name + ":"))

    def test_a_clean_analysis_and_text_pass(self):
        self.build()
        code, summary = self.check(GOOD, GOOD_ZH)
        self.assertEqual(code, 0, summary["problems"])
        for name in ("registration", "paths", "model", "wording", "probes", "text"):
            self.assertEqual(summary["checks"][name], "ok", name)
        self.assertEqual(summary["text"], {"matched": 45})
        report = Path("paths/check.md").read_text(encoding="utf-8")
        self.assertTrue(report.startswith("# Path model check\n"))
        for row in ("| text0.md:3 | 0.36 | matched | indirect.extra.paths.coefficients.a.value = 0.3582 |",
                    "| text0.md:4 | 0.39 | matched | indirect.extra.paths.coefficients.b.std = 0.3853 |",
                    "| text0.md:5 | 0.11 | matched | indirect.extra.paths.defined.ind.estimate = 0.109538 |",
                    "| text0.md:6 | 0.07 | matched | indirect.extra.paths.coefficients.cp.value = 0.0747 |",
                    "| text0.md:9 | 0.027 | matched | index.extra.paths.defined.index.estimate = 0.0271550 |"
                    .replace("0.0271550", f"{A3 * B:.6g}"),
                    "| text1.md:3 | 0.36 | matched | indirect.extra.paths.coefficients.a.value = 0.3582 |"):
            self.assertIn(row, report)
        models = Path("paths/models.md").read_text(encoding="utf-8")
        self.assertEqual(models.count("| kept |"), 4)
        self.assertIn("| sem_registered | sem | kept | 350 | 0.5316 | CFI 0.961, RMSEA 0.072, SRMR 0.035, df 32 | none |", models)

    def test_the_pm1_draft_fails_on_wording_probes_and_numbers(self):
        self.build()
        code, summary = self.check(DRAFT)
        self.assertEqual(code, 1)
        wording = self.problems(summary, "wording")
        for flagged in ("'leads to' joins two model variables", "'full mediation' given as evidence", "'Sobel' given as evidence"):
            self.assertIn(flagged, wording)
        self.assertIn("+1 SD of sup is 7.355, outside its observed range 1 to 7", self.problems(summary, "probes"))
        text = self.problems(summary, "text")
        self.assertIn("text0.md:6 prints 0.15: mismatch", text)                  # the indirect effect is 0.11
        self.assertIn("prints 3.1: mismatch", text)                              # the Sobel z is in no output

    def test_the_chinese_draft_fails_the_same_way(self):
        self.build()
        code, summary = self.check(DRAFT_ZH)
        self.assertEqual(code, 1)
        wording = self.problems(summary, "wording")
        for flagged in ("'导致' joins two model variables", "'完全中介' given as evidence", "'Sobel' given as evidence"):
            self.assertIn(flagged, wording)
        self.assertIn("text0.md:3: +1 SD of sup is 7.355", self.problems(summary, "probes"))
        text = self.problems(summary, "text")
        self.assertIn("text0.md:5 prints 0.15: mismatch", text)                 # 间接效应为0.15: a number touching Han
        self.assertIn("text0.md:3 prints 3.1: mismatch", text)                  # z＝3.1 in full width

    def test_causal_verbs_follow_the_registered_design(self):
        Path("paths/model.md").write_text(MODEL.replace("cross-sectional (one survey wave)", "experimental (autonomy "
                                                                                                "was assigned)"), encoding="utf-8")
        self.build()
        code, summary = self.check(DRAFT)
        wording = self.problems(summary, "wording")
        self.assertNotIn("leads to", wording)
        self.assertIn("'full mediation' given as evidence", wording)            # full mediation and Sobel: any design
        text = "Autonomy increased engagement. Higher autonomy was associated with more meaning, which drove engagement."
        Path("paths/model.md").write_text(MODEL, encoding="utf-8")
        self.assertEqual(self.register("--reason", "the design is cross-sectional after all")[0], 0)
        code, summary = self.check(text)
        self.assertEqual(self.problems(summary, "wording").count("joins two model variables"), 2)

    def test_disclaimers_and_negations_are_not_findings(self):
        self.build()
        text = ("We report the bootstrap interval instead of the Sobel test and do not label the result as full or partial "
                "mediation. One survey wave cannot show that autonomy causes engagement, and the estimates do not prove "
                "the model.\n\n我们不使用Sobel检验，也不能证明自主性导致投入。\n")
        code, summary = self.check(text)
        self.assertEqual((code, summary["checks"]["wording"]), (0, "ok"), summary["problems"])
        code, summary = self.check("The results prove that meaning matters.\n\n结果证实了意义感的作用。\n")
        self.assertEqual(self.problems(summary, "wording").count("never prove it"), 2)

    def test_moderated_mediation_is_claimed_only_with_an_index(self):
        self.build([("indirect", MED), ("a3", MOD)])
        code, summary = self.check("Support moderated the indirect effect: moderated mediation.\n\n中介效应受到领导支持的调节。\n"
                                   "\nThere was no evidence of moderated mediation.\n")
        wording = self.problems(summary, "wording")
        self.assertEqual(wording.count("without a recorded index"), 2, wording)
        self.assertIn("'moderated mediation' without a recorded index", wording)
        self.assertIn("中介效应受到领导支持的调节", wording)

    def test_probes_written_in_standard_deviations(self):
        self.build()
        code, summary = self.check("Slopes were probed at 1 SD above the mean of support.\n\n在高于均值1个标准差处探测。\n\n"
                                   "以及均值以上一个标准差。\n\nAt -1 SD the slope was smaller. Support (M = 6.10, SD = 1.25) "
                                   "was skewed; we used the 84th percentile.\n")
        probes = self.problems(summary, "probes")
        self.assertEqual(probes.count("outside its observed range"), 3, probes)
        self.assertNotIn("-1 SD", probes)
        self.build([("indirect", MED)], register=False)                          # a new run without a moderator
        code, summary = self.check("At +1 SD the effect was larger.\n")
        self.assertEqual(summary["checks"]["probes"], "not_checked")

    def test_registration(self):
        self.build(register=False)
        code, summary = self.check()
        self.assertIn("was never registered", self.problems(summary, "registration"))
        code, _, err = self.register()
        self.assertEqual(code, 1)
        self.assertIn("give --reason", err)
        code, out, _ = self.register("--reason", "registered late: estimates were run first")
        self.assertEqual((code, json.loads(out)["after_estimates"]), (0, True))
        code, summary = self.check()
        self.assertEqual(summary["checks"]["registration"], "ok")

    def test_a_model_changed_after_registration(self):
        self.build()
        code, out, _ = self.register()
        self.assertEqual((code, json.loads(out)["registered"]), (0, False))      # unchanged: nothing appended
        Path("paths/model.md").write_text(MODEL.replace("+ age + female\neng", "+ age\neng"), encoding="utf-8")
        code, summary = self.check()
        self.assertIn("changed after its registration", self.problems(summary, "registration"))
        self.assertEqual(self.register("--reason", "age only, as in the preregistered model")[0], 0)
        code, summary = self.check()
        self.assertEqual(summary["checks"]["registration"], "ok")
        Path("paths/model.md").write_text("# Model\n\nNo design here.\n", encoding="utf-8")
        code, _, err = self.register("--reason", "x")
        self.assertEqual(code, 2)
        for missing in ("a design line", "a roles table", "a ```model block"):
            self.assertIn(missing, err)

    def test_the_estimate_is_the_full_sample_value(self):
        boot_mean = copy.deepcopy(MED)
        boot_mean["defined"]["ind"]["estimate"] = 0.1122                         # the mean of the draws
        self.build([("indirect", boot_mean)])
        code, summary = self.check()
        self.assertIn("ind = 0.1122, but a*b on the recorded coefficients is 0.109538: report the full-sample value",
                      self.problems(summary, "paths"))

    def test_every_equation_on_the_same_rows(self):
        apart = copy.deepcopy(MED)
        apart["equations"]["mng"]["n"] = 322                                    # the a equation fitted alone
        self.build([("indirect", apart)])
        code, summary = self.check()
        self.assertIn("equations on different rows (n mng 322, eng 314)", self.problems(summary, "paths"))

    def test_interval_method_draws_and_seed(self):
        for method, ok in (("bc", False), ("bootstrap", False), ("bca", True), ("quasi_bayesian", True)):
            record = copy.deepcopy(MED)
            record["interval"]["method"] = method
            self.build([("indirect", record)], register=method == "bc")
            code, summary = self.check()
            self.assertEqual(summary["checks"]["paths"], "ok" if ok else "fail", method)
        record = copy.deepcopy(MED)
        del record["interval"]["seed"]
        self.build([("indirect", record)], register=False)
        self.assertIn("lacks its number of draws, seed", self.problems(self.check()[1], "paths"))

    def test_moderation_fields(self):
        outside, no_jn, changed, uncentred = (copy.deepcopy(MOD) for _ in range(4))
        outside["probe"]["slopes"].append({**SLOPES[0], "label": "mean+1sd", "w": 7.355})
        del no_jn["probe"]["jn"]
        changed["b3_uncentred"] = 0.0                                           # centred with a per-case mean
        del uncentred["centring"]
        self.build([("outside", outside), ("no_jn", no_jn), ("changed", changed), ("uncentred", uncentred)])
        paths = self.problems(self.check()[1], "paths")
        self.assertIn("outside: probe mean+1sd = 7.355 lies outside the observed range 1.0 to 7.0 of sup", paths)
        self.assertIn("no_jn: no Johnson-Neyman bounds", paths)
        self.assertIn("changed: b3 is 0.0888 centred and 0.0 uncentred", paths)
        self.assertIn("uncentred: centring is not recorded", paths)
        no_jn["jn_reason"] = "the moderator takes two values"
        self.build([("no_jn", no_jn)], register=False)
        self.assertEqual(self.check()[1]["checks"]["paths"], "ok")

    def test_conditional_effects_need_the_index_and_mediation_its_sensitivity(self):
        no_index, no_rho = copy.deepcopy(IMM), copy.deepcopy(MED)
        del no_index["index"]
        del no_rho["sensitivity"]
        outside = copy.deepcopy(IMM)
        outside["defined"]["at 7"]["at"] = 7.355
        self.build([("no_index", no_index), ("no_rho", no_rho), ("outside", outside)])
        paths = self.problems(self.check()[1], "paths")
        self.assertIn("no_index: conditional indirect effects without the index", paths)
        self.assertIn("no_rho: no sensitivity record", paths)
        self.assertIn("outside: probe at 7 = 7.355 lies outside", paths)

    def test_structural_models(self):
        failed, empty = copy.deepcopy(SEM), {"kind": "sem", "status": "not_checked", "reason": "semopy is not installed",
                                             "model": LATENT}
        failed["converged"] = False
        del failed["df"]
        self.build([("failed", failed), ("empty", empty)])
        paths = self.problems(self.check()[1], "paths")
        self.assertIn("failed: the structural model did not converge", paths)
        self.assertIn("failed: df or fit is missing", paths)
        self.assertIn("empty: kept although not run (semopy is not installed)", paths)

    def test_every_re_specification_is_a_ledger_row(self):
        step1, step2 = copy.deepcopy(SEM), copy.deepcopy(SEM)
        step1["model"] = LATENT + "\nmng1 ~~ eng1"
        step2["model"] = LATENT + "\nmng1 ~~ eng1\naut3 ~~ mng3"
        self.build([("final", step2)])                                          # no deviation, no earlier fits
        model = self.problems(self.check()[1], "model")
        self.assertIn("final: differs from the registered model (+ aut3 ~~ mng3; + eng1 ~~ mng1)", model)
        self.assertIn("final: 2 change(s) from the registered model, but this run's ledger holds 0 earlier fit(s)", model)
        step2["deviation"] = "freed at the user's request to reach CFI 0.95; exploratory"
        self.build([("final", step2)], register=False, dropped=[("registered", SEM, "re-specified: CFI 0.93")])
        self.assertIn("holds 1 earlier fit(s)", self.problems(self.check()[1], "model"))
        self.build([("final", step2)], register=False, dropped=[("registered", SEM, "re-specified: CFI 0.93"),
                                                                 ("step1", step1, "re-specified: CFI 0.94")])
        code, summary = self.check()
        self.assertEqual(summary["checks"]["model"], "ok", summary["problems"])
        models = Path("paths/models.md").read_text(encoding="utf-8")
        self.assertIn("| step1 | sem | dropped: re-specified: CFI 0.94 | 350 |", models)
        self.assertIn("+ aut3 ~~ mng3; + eng1 ~~ mng1 (reason: freed at the user's request", models)

    def test_a_sub_model_and_a_changed_equation(self):
        moderation_only = copy.deepcopy(MOD)
        moderation_only["model"] = "mng ~ a1*aut + a2*sup + a3*sup:aut + age + female"   # the a equation only
        extra_covariate = copy.deepcopy(MED)
        extra_covariate["model"] = MEDIATION.replace("cp*aut + age", "cp*aut + tenure + age")
        self.build([("a3", moderation_only), ("indirect", extra_covariate)])
        model = self.problems(self.check()[1], "model")
        self.assertNotIn("a3:", model)
        self.assertIn("indirect: differs from the registered model (+ eng ~ tenure)", model)

    def test_labelled_numbers(self):
        self.build()
        code, summary = self.check("Paths: a = 0.31, b = 0.36, β = 0.36, CFI = 0.96, RMSEA = 0.08, c′ = 0.07, ab = 0.11, "
                                   "index = 0.03.\n\n指数为0.027，间接效应为0.11，a路径系数为0.36。\n")
        text = self.problems(summary, "text")
        self.assertIn("prints 0.31: mismatch", text)                            # b's value, labelled as a
        self.assertIn("prints 0.08: mismatch", text)                            # RMSEA is 0.072
        self.assertEqual(text.count("mismatch"), 3, text)                       # and β: no standardized 0.36
        self.assertEqual(summary["text"]["matched"], 8)

    def test_parse_evaluate_and_changes(self):
        statements = cp.parse("eng ~ b*mng + cp*aut  # the outcome\nind := a*b; F =~ 1*x1 + x2\nx1 ~~ x2")
        self.assertEqual(statements, [("eng", "~", [("b", "mng"), ("cp", "aut")]), ("ind", ":=", "a*b"),
                                      ("F", "=~", [("1", "x1"), ("", "x2")]), ("x1", "~~", [("", "x2")])])
        for bad in ("eng mng", "eng ~ ", "eng ~ b* + aut"):
            with self.assertRaises(ValueError):
                cp.parse(bad)
        self.assertAlmostEqual(cp.evaluate("(a1 + a3*(7 - 6.104))*b - 0", {"a1": 0.37, "a3": 0.0888, "b": 0.3058}),
                               (0.37 + 0.0888 * 0.896) * 0.3058)
        for bad in ("a*c", "__import__('os')", "a**2", "a +"):
            with self.assertRaises(ValueError):
                cp.evaluate(bad, {"a": 1.0})
        self.assertEqual(cp.atoms("y ~ a*x:w\nm2 ~~ m1"), {"y ~ w:x", "m1 ~~ m2"})
        blocks = {"one": "y ~ x + w", "two": "y ~ x"}
        self.assertEqual(cp.changes("y ~ b*x", blocks, whole=False), [])
        self.assertEqual(cp.changes("y ~ x + z", {"one": "y ~ x + w"}, whole=False), ["+ y ~ z", "- y ~ w"])
        self.assertEqual(cp.changes("y ~ x", {"one": "y ~ x\nm ~ x"}, whole=True), ["- m ~ x"])

    def test_help_and_unreadable_input(self):
        code, out, _ = self.run_main("--help")
        self.assertEqual(code, 0)
        self.assertIn("registration", out)
        self.assertEqual(self.run_main("--dir", "nowhere")[0], 2)
        self.build()
        Path("paths/model.md").unlink()
        code, summary = self.check()
        self.assertEqual(summary["checks"]["model"], "not_checked")
        self.assertIn("is missing or changed", self.problems(summary, "registration"))


if __name__ == "__main__":
    unittest.main()
