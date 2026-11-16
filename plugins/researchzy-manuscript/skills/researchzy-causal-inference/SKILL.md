---
name: researchzy-causal-inference
description: "Estimate causal effects from panel or cross-section data: probe the design, fix the estimand first, run DiD (staggered, event study), IV, RD, panel FE, synthetic control or weighting with diagnostics, log every specification, check the text. Use for policy evaluations and natural experiments."
---

# Researchzy Causal Inference

This skill estimates causal effects with quasi-experimental and econometric designs: difference-in-differences (2×2, staggered adoption, event studies), instrumental variables, regression discontinuity, panel fixed effects, basic synthetic control, and propensity-score weighting. For each design it names the estimand and the identifying assumption first, reads the shape of the data before any result, runs a modern estimator as the headline with the traditional one beside it, runs the diagnostics the design needs, clusters at the level where treatment was assigned, records every specification and diagnostic in `causal/results.json`, and checks the text against that file.

Every request ends in one outcome: `matched` (a design fits), `ambiguous` (ask the user), `not_identifiable_yet` (say what is missing) or `not_attempted` (outside this skill; say why). A failed diagnostic is a result too: report it, do not work around it.

It does not: call an effect causal without its identifying assumption written down; run double machine learning, causal forests, mediation, shift-share or judge-leniency designs, nonlinear or continuous-treatment DiD, treatments that switch on and off, synthetic DiD or augmented synthetic control, RD kinks or several cutoffs, Bayesian or structural models; use MCP computation engines; run Stata or R (it can list the equivalent commands); design or register a trial. Sample size and power go to `researchzy-statistics`, figure styling to `researchzy-figures`, a review of a finished manuscript to `researchzy-stats-review` (all in plugin `researchzy-manuscript`, when installed).

## Requirements

Resolve `SKILL_DIR` to the directory containing this `SKILL.md`. Python 3.10 or newer. `probe_causal.py`, `check_causal.py`, `rz_results.py` and `check_results.py` need nothing else; `causal_tools.py` needs numpy, pandas and statsmodels (statsmodels brings scipy). Regression discontinuity needs `rdrobust` and `rddensity`, which are GPL-licensed: install them only with the user's consent (`python3 -m pip install --user rdrobust rddensity`), call them, never copy their code. Without them, RD ends as `not_attempted` with that reason. Other optional packages (such as `honestdid`) also need consent. If a package is missing, say which and ask before installing. No account is needed; step 6 says what the Researchzy tools add.

## Inputs

- A data file (CSV or TSV): a panel with one row per unit and period, or one row per unit.
- The question: the treatment, the outcome, and how the treatment was assigned (who decided, when, for which units).

Ask at most once, in one message, for what changes the analysis: the estimand (ATT, ATE, LATE, the effect at the cutoff), how and at what level treatment was assigned, the unit and the period, the outcome, the cluster level, and consent for any optional package the design needs.

## Workflow

Everything goes in `causal/` in the user's working directory. Run every command from the working directory, the folder that holds `causal/`.

1. **Question and design.** Write `causal/plan.md`: the design, the estimand with the units it averages over, the identifying assumption in one sentence ([writing results](references/writing-results.md) has one per design), the unit, the period and the cluster level with its basis (assignment or sampling).

2. **Probe the data.** The probe reads treatment, timing, instrument, running variable and cluster columns; of the outcome it reads only whether values are missing.

   ```sh
   python3 "$SKILL_DIR/scripts/probe_causal.py" data/counties.csv --design did --unit county --time year --treat policy --outcome jobs --cluster county
   python3 "$SKILL_DIR/scripts/probe_causal.py" data/pupils.csv --design iv --instrument lottery --treat attended --outcome score --cluster school
   python3 "$SKILL_DIR/scripts/probe_causal.py" data/exam.csv --design rd --running score --cutoff 60 --treat admitted
   ```

   It writes `causal/<data>.design.json`: duplicates, cohorts and their sizes, never- and always-treated units, reversals, periods without an untreated unit, feasible leads and lags, G and treated G with concern flags, whether treatment is constant within clusters and which cluster levels are not finer than the assignment level (`--assign` names it; default the unit), RD counts, binomial tests and heaping, IV compliance shares, SC donors, and the `route`. Other designs: `--design panel`, `sc`, `weighting` (with `--covariates a,b,c`).

   | `route.outcome` | Do |
   |---|---|
   | `matched` | Go on with `route.design`; the headline estimator is in `route.headline`, the one to report beside it in `route.benchmark`. Read `route.next` |
   | `ambiguous` | Ask the question in `route.why`, then probe again |
   | `not_identifiable_yet` | Tell the user what is missing (`route.why`) and stop |
   | `not_attempted` | Tell the user why (`route.why`) and stop |

3. **Design stage, before any estimate.** Add to `plan.md`: the target parameter and its aggregation, the cohorts and the control group (never-treated or not-yet-treated), covariates (pre-treatment only), the headline specification and every robustness specification you will run. A choice made after seeing an estimate is labelled so in the text.

4. **Analysis script.** Write `causal/analysis.py`, which the user keeps. Read the design's reference first ([DiD](references/did.md), [IV and RD](references/iv-rd.md), [panel, SC, weighting](references/panel-sc-weighting.md)). Every specification, kept or dropped (`kept=False, reason=...`), goes through `ct.spec`, which checks the causal fields and records it with `rz_results`, so that `ledger.jsonl` holds every specification run:

   ```python
   """<study>. Plan: causal/plan.md. Run from the project folder: python3 causal/analysis.py"""
   import sys
   import pandas as pd
   sys.path.insert(0, "<SKILL_DIR>/scripts")      # written out in full
   import rz_results as rz
   import causal_tools as ct

   rz.OUT, SEED, DATA = "causal", 20261113, "data/counties.csv"
   panel = pd.read_csv(DATA)
   panel["cohort"] = ct.first_treated(panel, unit="county", time="year", treat="policy")
   cs = ct.callaway_santanna(panel, unit="county", time="year", cohort="cohort", outcome="jobs",
                             control="never_treated", B=999, seed=SEED)
   ct.spec(design="staggered_did", estimator="callaway_santanna", headline=True, estimand="ATT",
           control_group="never_treated", cluster={"level": "county", "basis": "assignment", "G": 60, "G_treated": 45},
           diagnostics={...},                     # every required key below, from cs and the probe
           id="att", question="Did the policy change county jobs?", family="jobs", test="Callaway-Sant'Anna ATT",
           unit="county", n={"counties": 60, "treated": 45},
           estimate={"name": "ATT over treated county-years", "value": cs["overall"]["estimate"], "units": "jobs"},
           interval={"low": cs["overall"]["low"], "high": cs["overall"]["high"], "level": 0.95})
   ...                                            # TWFE beside it (headline=False), robustness rows, dropped rows
   rz.finish(script=__file__, data=[DATA], seed=SEED, settings={"bootstrap_draws": 999})
   ```

   One headline per question (`family`). Give a p-value only to the headline: robustness rows carry their interval, or `check_results.py` asks for a multiplicity correction across them. Each diagnostic is `{"status": "pass" | "fail" | "not_checked", "reason": ..., "value": ...}`; `not_checked` needs its reason.

   | `design` | Headline `estimator` | Required `diagnostics` | When one fails |
   |---|---|---|---|
   | `did_2x2` | `twfe`, `interaction_ols` or `callaway_santanna` | `pretrend_plot`, `pretrend_test` | Breakdown M below 1: the conclusion is directional |
   | `staggered_did` | `callaway_santanna`; `twfe` beside it | `cohorts`, `untreated_each_period`, `event_study`, `sensitivity` | Keep the robust headline; report a cohort with a pre-trend separately or drop it, and name it |
   | `event_study` | `callaway_santanna` (common timing: also `twfe_event_study`) | `pretrend_test`, `sensitivity` | Breakdown M below 1: write that the result is fragile |
   | `iv` | `2sls` | `first_stage`, `reduced_form`, `first_stage_f`, `ar_set`, `ols` | F below 10: the Anderson–Rubin set leads; below 3.84: no IV estimate |
   | `rd` | `rdrobust` | `density`, `covariate_balance`, `bandwidths`, `placebo_cutoffs` | Density test rejects, or covariates jump: no estimate |
   | `panel_fe` | `within` | `within_variation` | 6 or fewer treated clusters: add `randomization_inference` |
   | `sc` | `synthetic_control` | `pre_fit`, `placebos` | Poor pre-period fit: no estimate |
   | `weighting` | `ipw` or `aipw` | `overlap`, `balance`, `max_weight`, `trimming` | Most units trimmed: no ATE, only the overlap population |

   Every headline except `sc` carries `cluster={"level", "basis", "G", "G_treated"}`. The thresholds are conventions with their sources in the references; the user may change them (`--f-low`, `--few-treated`).

5. **Check.** Run `python3 causal/analysis.py`, then:

   ```sh
   python3 "$SKILL_DIR/scripts/check_causal.py" --probe causal/counties.design.json --script causal/analysis.py
   ```

   | Check | On `fail` |
   |---|---|
   | `route` | Use the route's headline estimator; keep the other as `headline=False`, or report no estimate |
   | `diagnostics` | Record the missing diagnostic, or `not_checked` with the reason |
   | `clustering` | Cluster at or above the assignment level the probe names; fix G |
   | `iv_strength`, `rules` | Do what the failed diagnostic requires: another headline, or no estimate |
   | `permutation` | Count the observed assignment: (1 + hits) / (B + 1) |
   | `specifications` | Record through `ct.spec`; when only the headline excludes zero, say so with the count |
   | `complete`, `ledger`, `hashes`, `script` | Fix the script and run it again; never edit `results.json` |
   | `not_checked` | Say that it was not checked and why; it is not a pass |

6. **Write the text.** Read [writing results](references/writing-results.md). Write `causal/results.md` and `causal/methods.md` from `results.json` only, then add `--text causal/results.md causal/methods.md` to the check. `verbs` fails on causal verbs (caused, led to, raised, reduced) about a result whose route or required diagnostics do not support them; describe the estimate instead. Copy `causal/robustness.md` into the robustness table. With the `researchzy` plugin connected (it needs a Researchzy account), `search_papers` finds published estimates from the same design for a magnitude check and earlier uses of an instrument; read their numbers in the full text (`get_pdf_download`), and hand citations to `researchzy-citation-finder`. Without it, ask the user for the papers.

## Outputs

| File in `causal/` | Content |
|---|---|
| `plan.md` | Design, estimand, assumption, cohorts, control group, cluster level, planned specifications |
| `<data>.design.json` | The probe: data shape, clustering and the route |
| `analysis.py` | The kept analysis script |
| `results.json`, `ledger.jsonl` | Kept results with diagnostics and hashes; every specification run, kept or dropped, with its interval and n |
| `results.md`, `methods.md` | Results sentences and the methods paragraph |
| `check.md`, `robustness.md` | The last check; every specification, the headline first, changes in n flagged |

## Rules

- Never invent data, numbers or sources. Every number in the text comes from `results.json`; a fact not in the files is `[Author input needed: …]`.
- The identifying assumption is written down before any causal wording, and the verb matches the evidence ([writing results](references/writing-results.md)).
- A pre-trend test that passes is weak evidence, not proof of parallel trends.
- Cluster at the level of assignment or sampling and say which; a correlation of outcomes within a group is not a reason to cluster there. Report G and treated G.
- Record every specification run, with the reason a dropped one was dropped. Never edit `results.json` or `ledger.jsonl` by hand, and never change the user's data files.
- Say in the methods which steps an AI model carried out (probing, code, estimation, drafting).

## Related files

| File | Open when |
|---|---|
| [references/did.md](references/did.md) | Any DiD or event study: control groups, aggregations, TWFE, pre-trends, sensitivity, few clusters |
| [references/iv-rd.md](references/iv-rd.md) | Instrumental variables or regression discontinuity |
| [references/panel-sc-weighting.md](references/panel-sc-weighting.md) | Panel fixed effects, synthetic control, propensity weighting |
| [references/writing-results.md](references/writing-results.md) | Steps 1 and 6: estimand and assumption sentences, verbs, robustness table, methods paragraph |
| `scripts/probe_causal.py`, `scripts/causal_tools.py`, `scripts/check_causal.py` | The steps above; `--help`, or the module docstring of `causal_tools.py` |
| `scripts/rz_results.py`, `scripts/check_results.py` | The result file and the number check, shared with `researchzy-statistics` |
