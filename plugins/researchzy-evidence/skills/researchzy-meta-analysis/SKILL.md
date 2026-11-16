---
name: researchzy-meta-analysis
description: "Pool study results from an extraction table: effect sizes with declared conversions, fixed or random effects (REML, Hartung-Knapp, prediction interval), heterogeneity, forest and funnel plots, sensitivity and subgroup analyses, and a check of the results text. Use for a meta-analysis."
---

# Researchzy Meta-analysis

This skill pools the results of studies the user has already chosen. It turns an extraction table into one effect size per study and comparison, with every conversion declared on its row; pools them with the model a written plan names; reports heterogeneity and a prediction interval; draws forest and funnel plots; runs sensitivity and subgroup analyses; and records every number in `meta-analysis/results.json`. A script then checks that each number in the results text is in that file and that each pooled estimate is reported with its interval, its prediction interval and its heterogeneity.

It does not search or screen (`researchzy-systematic-review`) or judge risk of bias and certainty of evidence (`researchzy-risk-of-bias`), both in plugin `researchzy-evidence`, and it does not audit someone else's meta-analysis (`researchzy-stats-review`, plugin `researchzy-manuscript`), when installed. It does not fit network, individual-participant, Bayesian, diagnostic-accuracy (bivariate) or multivariate models, pool single-arm proportions, rebuild data from survival curves, or compute fail-safe N or p-curves. When the question needs one of these, name the method and the kind of tool it needs, and stop.

## Requirements

Resolve `SKILL_DIR` to the directory containing this `SKILL.md`. Python 3.10 or newer. `effect_sizes.py` and `check_meta.py` need nothing else (scipy, when installed, gives the t quantiles). `meta_pool.py` needs numpy and scipy; the plots need matplotlib, and without it the run reports that they were not drawn. If a package is missing, say which and ask before installing (`python3 -m pip install --user …`). No account is needed; step 2 says what the Researchzy tools add.

## Inputs

- The studies' results: an extraction table (from `researchzy-systematic-review`, from the user, or built here from the papers), or the papers themselves.
- The review question, with the outcomes and timepoints to pool.
- How the studies differ (populations, doses, settings, follow-up): this decides the model.

Ask once, in one message, before pooling: the measure per outcome, the model and its reason, the primary outcome, the subgroups with their reasons, how multi-arm studies enter, and, for binary outcomes with zero cells or rare events, the zero-event method. Offer the defaults in step 1; do not ask what the files already settle.

## Workflow

Everything goes in `meta-analysis/` in the user's working directory. Run every command from the working directory.

1. **Plan.** Write `meta-analysis/plan.md` before any pooled number exists ([pooling](references/pooling.md)): the measure per outcome; the model with its reason from how the studies differ, never from I²; the τ² estimator (default REML, which falls back to Paule–Mandel when it does not converge; DerSimonian–Laird only when the user asks); the interval (default Hartung–Knapp with its floor, Wald as a sensitivity analysis); the primary outcome; subgroups; multi-arm studies; the zero-event method. A later change is a dated deviation in the plan, and the planned analysis stays reported.

2. **Extraction table.** Build `meta-analysis/extraction.csv` in the format of [effect sizes](references/effect-sizes.md): one row per arm, `reported_as` saying what the row holds, a `locator` and a `quote` for every value, every inference in `notes` (for example "Table 2 footnote: values are mean (SE)" with `reported_as` = `mean_se`). Convert a table the user gives into this format without changing their file. With the `researchzy` plugin connected (it needs a Researchzy account), read each value in the full text from `get_pdf_download`, which settles SD against SE and median against mean, and look each study up with `search_papers` by DOI to find two reports of one trial. Without it, ask for the PDFs or use the values the user gives, and say which values were not seen in a source.

3. **Effect sizes.**

   ```sh
   python3 "$SKILL_DIR/scripts/effect_sizes.py" meta-analysis/extraction.csv --measure "weight change=MD"
   python3 "$SKILL_DIR/scripts/effect_sizes.py" meta-analysis/extraction.csv --measure death=OR --sparse death=mh \
     --combine "Lee 2021"
   ```

   It writes `effects.csv` and `effects.md`. Exit code 1 means something was refused:

   | Refusal | Do |
   |---|---|
   | A study twice in one pool; several arms against one control | One row per arm, or `--combine`, `--split` or `--drop` as the plan says |
   | An MD pool without one shared unit | Fill `units`; scales that differ need an SMD, which is a plan change |
   | An SMD pool mixing change and final values | Pool them as separate outcomes |
   | A cluster row without its ICC and source; a crossover row without its correlation | Find them in the paper or a cited source; otherwise leave the study out and say why |
   | An impossible ratio CI | Read the source again |
   | A zero cell, or a pooled event rate below 1 % | `--sparse` with the method from the plan |

   Settle every warning in the source (an SD that looks like an SE, an asymmetric ratio CI, a missing locator) and note what was checked. Never edit `effects.csv`.

4. **Pool.**

   ```sh
   python3 "$SKILL_DIR/scripts/meta_pool.py" meta-analysis/effects.csv --model random --tau2 REML --ci HK \
     --primary "weight change" --subgroup dose
   ```

   It records each main pool with its p-value, and the sensitivity and subgroup results without one, through `rz_results.py`; writes `pooled.md` and the plots; and runs the small-study test only at k ≥ 10 and the test between subgroups only with at least 4 studies per group (conventions; [heterogeneity and bias](references/heterogeneity-and-bias.md)). Exit code 1: `effects.csv` has refused rows or a pool could not be pooled, and nothing was recorded. Exit code 2: numpy or scipy is missing.

5. **Look.** Read `pooled.md` and open the plots. Each study's estimate must match its paper in direction and size, and a study that dominates the weights needs a reason. A study that looks wrong goes back to step 2; it is not explained away by the leave-one-out table.

6. **Write.** Read [writing results](references/writing-results.md). Write `meta-analysis/results.md` and `meta-analysis/methods.md` from `results.json` only.

7. **Check.**

   ```sh
   python3 "$SKILL_DIR/scripts/check_meta.py" --text meta-analysis/results.md meta-analysis/methods.md
   ```

   Fix the text until the exit code is 0 (the last table of writing-results.md says how). A `not_checked` status is not a pass. Give the user `results.md`, `methods.md`, the plots, `check.md` and the warnings settled in step 3.

## Outputs

| File in `meta-analysis/` | Content |
|---|---|
| `plan.md` | Measures, model and its reason, estimators, subgroups, zero-event method, deviations |
| `extraction.csv` | One row per arm, with locators and quotes |
| `effects.csv`, `effects.md` | One effect per study and comparison, with conversions, warnings and refusals |
| `results.json`, `ledger.jsonl` | Every pooled, sensitivity and subgroup result, with hashes and versions |
| `pooled.md` | Pooled results, heterogeneity, sensitivity table and subgroups, for reading |
| `forest-<pool>.*`, `funnel-<pool>.*` | The plots as PDF, PNG and SVG, when matplotlib is installed |
| `results.md`, `methods.md`, `check.md` | The text and its last check |

## Rules

- Never invent a value, an SD, an ICC, a correlation or a source. Every number in the text comes from `results.json`; a fact that is in no file is `[Author input needed: …]`.
- Every conversion is declared on its row; estimated values are marked and dropped in a sensitivity analysis.
- One effect per study in each pool. Zero cells are never corrected without the plan's choice.
- Never edit `effects.csv`, `results.json` or `ledger.jsonl` by hand; run the scripts again.
- The model's reason comes from the studies, never from I² or a test. Funnel asymmetry is not proof of publication bias.
- The thresholds (10 studies for a small-study test, 4 per subgroup, a 1 % event rate) are conventions the user may change in the plan; say which were used.
- The methods say what the agent did (extraction, conversions, analysis) and what the user checked.
- Hand risk of bias and certainty of evidence to `researchzy-risk-of-bias` (it reads `results.json`), figure styling to `researchzy-figures` and the manuscript to `researchzy-writing`, when installed.

## Related files

| File | Open when |
|---|---|
| [references/effect-sizes.md](references/effect-sizes.md) | Steps 2 and 3: columns, what each row holds, formulas, cluster and crossover designs, warnings |
| [references/pooling.md](references/pooling.md) | Steps 1 and 4: model, τ² estimators, intervals, prediction interval, zero events, what is out of scope |
| [references/heterogeneity-and-bias.md](references/heterogeneity-and-bias.md) | Subgroups, sensitivity analyses, small-study tests, reading I² and τ² |
| [references/writing-results.md](references/writing-results.md) | Steps 6 and 7 |
| `scripts/effect_sizes.py`, `scripts/meta_pool.py`, `scripts/check_meta.py` | The steps above; `--help` lists the options |
| `scripts/rz_results.py`, `scripts/check_results.py` | Copies from `researchzy-statistics`: the result file and the number check the scripts above build on |
