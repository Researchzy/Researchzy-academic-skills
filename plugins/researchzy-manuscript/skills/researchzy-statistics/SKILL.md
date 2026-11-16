---
name: researchzy-statistics
description: "Analyse the user's data: plan, probe the design (pairs, repeats, clusters, replicates), choose the method from it, run a kept script that records estimates, intervals and effect sizes, correct by family, and check the text against the results. Also sample size and power."
---

# Researchzy Statistics

This skill analyses data the user supplies. It turns the question into a plan, reads the design from the data table, chooses the method from the design, writes an analysis script that the user keeps, records every estimate with its interval and effect size in `statistics/results.json`, corrects for multiple comparisons by family, and writes the Results sentences and the Statistical analysis paragraph from that file. A script then checks that every number in the text is in the results. It also computes sample size, power or the detectable effect before a study.

It does not audit the statistics of a finished manuscript (`researchzy-stats-review`), draw figures (`researchzy-figures`) or write the whole Results section (`researchzy-writing`); these are in plugin `researchzy-manuscript`, when installed. It does not attempt Bayesian models, survival analysis, survey weights, or prediction-model development or validation. Meta-analysis goes to `researchzy-meta-analysis` (plugin `researchzy-evidence`), and causal identification and propensity scores go to `researchzy-causal-inference` (plugin `researchzy-manuscript`), when installed. When the question needs something no installed skill covers, say so, name the part that needs a statistician or a dedicated tool, and stop; never improvise an approximation.

## Requirements

Resolve `SKILL_DIR` to the directory containing this `SKILL.md`. Python 3.10 or newer. `probe_design.py`, `rz_results.py` and `check_results.py` need nothing else. `power.py` and the analysis scripts need scipy; models (mixed models, GEE, regression, Welch ANOVA) need statsmodels; pandas is optional. If a package is missing, say which and ask before installing anything. No account is needed; step 9 says what the Researchzy tools add.

## Inputs

- A data file (CSV or TSV, one row per observation) and the question it should answer; or a profile from `researchzy-figures` (`figures/<name>.profile.json`).
- What one unit of analysis is (a subject, an animal, a culture, a run) if no column says so.
- For sample size: the outcome, the planned test, the effect in raw units and where it comes from.

Ask at most once, in one message, for what changes the analysis: the unit of analysis, the primary question, why values are missing, and the source of a power calculation's effect.

## Workflow

Everything goes in `statistics/` in the user's working directory. Run every command from that directory.

1. **Plan before any test.** Write `statistics/plan.md`: one row per question with the outcome and its type, the comparison, the unit, the role (`primary`, `secondary`, `exploratory`) and the family of tests behind each claim, the missing-data decision, alpha and the interval level. A question decided after seeing the data is exploratory.

2. **Probe the design.**

   ```sh
   python3 "$SKILL_DIR/scripts/probe_design.py" data/trial.csv --unit subject --group condition --outcome latency_min
   python3 "$SKILL_DIR/scripts/probe_design.py" data/trial.csv --unit patient --cluster clinic --group arm --outcome score
   python3 "$SKILL_DIR/scripts/probe_design.py" --profile figures/trial.profile.json --outcome latency_min
   ```

   It writes `statistics/<data>.design.json`: rows per unit, complete and incomplete pairs, n per group in units and in rows, missing values, the outcome type with its evidence, sparse cells, the design, the methods it rules out and the `route` into the method table. Add `--time` for occasions, `--pair` when a column other than the unit links matched units, `--rows-are-units` only when the user said each row is a separate unit.

   | `design` | Do |
   |---|---|
   | `independent` | Use the "independent units" column |
   | `paired`, `repeated` | Use the "same unit measured again" column; report incomplete units |
   | `clustered` | Model the clusters, or analyse one summary per cluster ([method table](references/method-table.md)) |
   | `replicates` | Aggregate to one value per unit and condition, or model the nesting. Rows are not n |
   | `unit_not_declared` | Ask the user what one row is. Do not run a test until they answer |

   A note that ids look reused across groups means the design may be wrong: ask before going on.

3. **Choose the method.** Read [the method table](references/method-table.md) at `route.row` and `route.column`, after `route.first`. Write the method per question into `plan.md`. Never choose or switch a test on a normality or variance pre-test; two means use Welch by default.

4. **Write the analysis script and run it.** One script, `statistics/analysis.py`, that reads the data files and never writes to them. Every analysis run goes through `rz.record`, the kept ones and the ones left out (`kept=False, reason=...`):

   ```python
   """<study>. Plan: statistics/plan.md. Run from the project folder: python3 statistics/analysis.py"""
   import csv, sys
   import numpy as np
   from scipy import stats
   sys.path.insert(0, "<SKILL_DIR>/scripts")     # written out in full; to share, copy rz_results.py next to the script
   import rz_results as rz

   SEED, DATA = 20261113, "data/trial.csv"
   rng = np.random.default_rng(SEED)             # every resampler gets rng=rng
   ...                                           # read DATA, build one value per unit, run the planned test
   rz.record(id="latency_drug_vs_placebo", question="Does the drug shorten sleep latency?", family="latency",
             role="primary", test="paired t test", unit="subject", n={"pairs": len(diff)},
             estimate={"name": "mean difference, drug minus placebo", "value": diff.mean(), "units": "min"},
             interval={"low": low, "high": high, "level": 0.95}, statistic={"name": "t", "value": t.statistic},
             df=t.df, p=t.pvalue, effect_size={"name": "d_z", "value": dz, "low": dz_low, "high": dz_high, "level": 0.95},
             descriptives={"drug": {"mean": drug.mean(), "sd": drug.std(ddof=1)}}, notes="S09 left out: no drug value")
   rz.correct("diet_pairs", "holm")              # after the last record() of a family of two or more tests
   rz.finish(script=__file__, data=[DATA], seed=SEED, settings={"alpha": 0.05, "resamples": 9999})
   ```

   `record` refuses a p-value without an estimate, its interval and an effect size (or `no_effect_size="the reason"`), and a missing unit. Put every number the text will print (group means, SDs, counts left out) in `descriptives`. Run it with `python3 statistics/analysis.py`. Each run rewrites `results.json` and appends to `ledger.jsonl`.

5. **Effect sizes and diagnostics.** Every test has an effect size with its interval from the method table. Diagnostics are descriptions in `notes` or `descriptives`, not gates ([multiplicity, missing data and diagnostics](references/multiplicity-missing-diagnostics.md)).

6. **Multiple comparisons.** A family of two or more tests is corrected with `rz.correct` by the rule in that reference: the family follows the claim, and the correction counts every test run for it, including those left out.

7. **Check.**

   ```sh
   python3 "$SKILL_DIR/scripts/check_results.py" --script statistics/analysis.py
   ```

   | Finding | Do |
   |---|---|
   | `complete` fails | Add the missing field in the script and run it again. Never edit `results.json` |
   | `families` fails | Name the correction, or put the tests in the right family; rerun |
   | `ledger` fails | Record the analysis that is missing, or give a dropped one its reason |
   | `hashes` is `drift` | The script or data changed after the run: run the script again |
   | `script` fails | Fix what it names (seed, typed-in data, writing to an input, `equal_var`) |
   | `not_checked` | Say it was not checked and why; it is not a pass |

8. **Write the text.** Read [writing results](references/writing-results.md). Write `statistics/results.md` and `statistics/methods.md` from `results.json` only, then:

   ```sh
   python3 "$SKILL_DIR/scripts/check_results.py" --script statistics/analysis.py --text statistics/results.md statistics/methods.md
   ```

   A `mismatch` is fixed in the text by copying the recorded value. A printed minus sign must match the recorded sign; a number without a sign may carry its direction in words ("shorter by 9.1 min"). A `not_found` number is either a number from outside the results (say where it comes from) or one the script should record. The exit code is 1 until no mismatch remains.

9. **Sample size and power** (before a study, or when asked). Read [power and sample size](references/power-and-sample-size.md). Ask where the effect and the SD come from, then run, for example:

   ```sh
   python3 "$SKILL_DIR/scripts/power.py" two-means --diff 5 --sd 10 --units mmHg --unit patients \
     --outcome "systolic pressure at 12 weeks" --effect-source prior-study \
     --source-note "doi:10.xxxx/yyyy, Table 2, control arm SD" --attrition 0.1
   ```

   Give the user the table from `statistics/power.md` and the justification paragraph. `--solve effect` is a sensitivity analysis and is labelled so; observed power is refused. With the `researchzy` plugin connected (it needs a Researchzy account), find the prior study with `search_papers`, read the SD or effect in its full text from `get_pdf_download`, and record the DOI and the table or page in `--source-note`. Without it, ask the user for the paper or the value with its source.

## Outputs

| File in `statistics/` | Content |
|---|---|
| `plan.md` | Questions, outcomes, units, roles, families, methods, missing-data decision |
| `<data>.design.json` | The probe: n in units and rows, pairs, missing, outcome type, design, ruled-out methods, route |
| `analysis.py` | The kept analysis script |
| `results.json`, `ledger.jsonl` | Kept results with hashes and versions; every analysis run, kept or dropped |
| `results.md`, `methods.md` | Results sentences and the Statistical analysis paragraph |
| `check.md` | The last check, with every number in the text and its status |
| `power.json`, `power.md` | Sample size or sensitivity table and justification |

## Rules

- Never invent data, numbers, SDs, effects or sources. Every number in the text comes from `results.json` or `power.json`; a fact that is not in the files is `[Author input needed: …]`.
- n counts units, never rows. No test runs while the unit is not declared.
- Record every analysis run, including those that will not be reported. Never edit `results.json` or `ledger.jsonl` by hand.
- Never overwrite or change the user's data files; derived tables go in `statistics/`.
- No significance stars, no "trend towards significance", no "no difference" from a large p.
- Hand the figures to `researchzy-figures`, a full Results section to `researchzy-writing`, the code and data statement to `researchzy-data-availability`, and an audit of a finished manuscript to `researchzy-stats-review` (all in plugin `researchzy-manuscript`, when installed).

## Related files

| File | Open when |
|---|---|
| [references/method-table.md](references/method-table.md) | Step 3; also for replicates, clusters and what the skill does not attempt |
| [references/multiplicity-missing-diagnostics.md](references/multiplicity-missing-diagnostics.md) | Writing the plan (families, missing data); steps 5 and 6 |
| [references/writing-results.md](references/writing-results.md) | Step 8 |
| [references/power-and-sample-size.md](references/power-and-sample-size.md) | Step 9, and any question about sample size or power |
| `scripts/probe_design.py`, `scripts/rz_results.py`, `scripts/check_results.py`, `scripts/power.py` | The steps above; `--help` lists the options |
