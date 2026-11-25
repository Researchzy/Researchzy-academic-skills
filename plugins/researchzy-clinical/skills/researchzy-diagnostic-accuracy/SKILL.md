---
name: researchzy-diagnostic-accuracy
description: "Analyse diagnostic tests and logistic risk models: probe the data for leakage and partial verification, exact 2x2 intervals, AUCs by DeLong or patient bootstrap, paired comparisons, calibration, decision curves, bootstrap optimism, and a text check. Use for test accuracy or risk-model studies."
---

# Researchzy Diagnostic Accuracy

This skill analyses the accuracy of a diagnostic test or a logistic prediction model on the user's data. It probes the table before any estimate (patients in two splits, rows without the reference standard, several lesions per patient, separation), then computes 2x2 measures with exact intervals, AUCs with a named interval method, paired comparisons of two tests on the same patients, calibration, decision curves, internal validation that reruns the whole modelling pipeline on bootstrap resamples, and a null-label leakage check. Every result goes through `rz_results.py` into `diagnostic-accuracy/results.json`, and `check_accuracy.py` checks the results and the text written from them.

It refuses three common practices: a cut-off chosen on the test data, discrimination without calibration, and predictive values from a case-control or enriched sample without the target population's prevalence. It gives no clinical advice: it does not diagnose, interpret a result for a patient or recommend a test. It does not run multi-reader multi-case studies, bivariate meta-analysis of accuracy studies, imperfect-reference or latent-class models, deep-learning or imaging model training, multiclass outcomes, Riley sample sizes (R packages) or time-to-event prediction models: name the method and the tool it needs, and stop. QUADAS-2 and PROBAST go to `researchzy-risk-of-bias` (plugin `researchzy-evidence`); STARD and TRIPOD checklists to `researchzy-reporting-checklist` and the protocol to `researchzy-protocol` (plugin `researchzy-clinical`); comparisons that are not accuracy questions to `researchzy-statistics` and a review of someone else's paper to `researchzy-stats-review` (plugin `researchzy-manuscript`), when installed.

## Requirements

Resolve `SKILL_DIR` to the directory containing this `SKILL.md`. Python 3.10 or newer. `probe_accuracy.py`, `check_accuracy.py`, `rz_results.py` and `check_results.py` need nothing else; the probe's separation check uses scipy when it is installed. `rz_accuracy.py`, imported by the analysis script, needs numpy, scipy and statsmodels; model pipelines usually need scikit-learn, and the figures matplotlib. If a package is missing, say which and ask before installing. No account is needed; step 1 says what the Researchzy tools add.

## Inputs

- The data: CSV or TSV, one row per unit (a patient, or a lesion or visit with its patient id): the reference standard, and the index result, score or predicted risk; for model work the candidate predictors and the user's split column, optionally site and date. Or the four cells of a 2x2 when there are no individual rows.
- The sampling design: `consecutive`, `cross_sectional`, `case_control` or `enriched`.
- The positive reference value, the cut-off and its source, and any model script the user already has.

Ask once, in one message, for what the files do not settle: the column names, the design, the positive value, the cut-off and its source, the split column and its values, the planned threshold range of a decision curve, and, for a case-control or enriched sample, the target prevalence with its source. Never guess a column.

## Workflow

Everything goes in `diagnostic-accuracy/` in the user's working directory. Run every command from that directory.

1. **Plan.** Before any estimate, write `diagnostic-accuracy/plan.md` ([input and probe](references/input-and-probe.md)): the question (one test, two tests, a new model, a published model), the reference standard and positive value, the design, the datasets, the cut-off and its source, the candidate predictors, the threshold range, the interval methods, the seed. With the `researchzy` plugin connected (it needs a Researchzy account), `search_papers` and `get_paper_files` can find the prevalence in the intended population and a published model's coefficients, intercept and cut-off; record each with its table and page. Without it, ask the user for the source. Never fill a prevalence, coefficient or cut-off from memory.

2. **Probe.**

   ```sh
   python3 "$SKILL_DIR/scripts/probe_accuracy.py" data/nodules.csv --id patient_id --unit nodule_id \
     --reference biopsy --positive 1 --index biomarker --threshold 2.5 --split split --development development \
     --test test --predictors age,size_mm,spiculated --design consecutive
   ```

   It writes `diagnostic-accuracy/<data>.probe.json`; patient ids never appear in it. Exit code 1: a patient in two splits, no positive value, or a reference with other than two values.

   | Check | `problem` | Do |
   |---|---|---|
   | `overlap` | A patient in two splits; a row without id or split | Ask the user to reassign by patient, then probe again. No test-set result until `leakage` is `ok` |
   | `reference` | Positive value absent, or not two values | Ask; multiclass outcomes are out of scope |
   | `verification`, `index_missing` | Rows without the reference standard, or without the index result | Report the counts by index result and how they are handled; never drop rows silently |
   | `repeated_ids` | Patients with several rows | Pass `groups=` to every function: intervals by bootstrap over patients |
   | `identical_rows`, `date_order` | Same predictors in two splits; a temporal split out of order | Ask the user |
   | `separation` | Complete or quasi-complete separation | Ask; a penalised or exact method is a plan change |

   `events` reports events per candidate parameter with no pass mark; give the number to the user.

3. **Analysis script.** Write `diagnostic-accuracy/analysis.py`, which the user keeps; read [accuracy measures](references/accuracy-measures.md), and for a model [model development and validation](references/model-development-and-validation.md). Every result goes through `ra.record`:

   ```python
   """Accuracy of the biomarker. Plan: diagnostic-accuracy/plan.md. Run: python3 diagnostic-accuracy/analysis.py"""
   import sys
   import pandas as pd
   sys.path.insert(0, "<SKILL_DIR>/scripts")      # written out in full
   import rz_results as rz
   import rz_accuracy as ra

   rz.OUT, SEED, DATA = "diagnostic-accuracy", 20261118, "data/nodules.csv"
   df = pd.read_csv(DATA)
   test = df[(df.split == "test") & df.biopsy.notna()]       # unverified rows: counted by the probe, reported
   y, g = test.biopsy.to_numpy(), test.patient_id.to_numpy()
   common = dict(question="How accurate is the biomarker?", dataset="test", design="consecutive",
                 probe="diagnostic-accuracy/nodules.probe.json")
   ra.record(ra.two_by_two(**ra.cells(y, test.biomarker >= 2.5), design="consecutive", patients=len(set(g))),
             id="biomarker", model="biomarker", threshold={"value": 2.5, "source": "plan"}, **common)
   ra.record(ra.auc(y, test.biomarker, groups=g, seed=SEED), id="biomarker_auc", model="biomarker",
             no_calibration="a biomarker value, not a predicted risk", **common)
   ra.record(ra.compare_auc(y, test.biomarker, test.clinical_score, groups=g, seed=SEED), id="biomarker_vs_score",
             models=("biomarker", "clinical score"), **common)
   rz.finish(script=__file__, data=[DATA], seed=SEED, settings={"bootstrap_resamples": 2000})
   ```

   `record` refuses a test-set result without a probe whose `leakage` is `ok`, a cut-off whose source is not `plan`, `development` or `published` (with a citation), and a predictive value the design does not allow. Run the script; never edit `results.json`.

4. **Cut-offs, predictive values, decision curves.** Read [thresholds and decision curves](references/thresholds-and-decision-curves.md). A cut-off comes from the plan, from `ra.dev_cutoff` on development data, or from a cited publication. PPV and NPV come from the table only in a consecutive or cross-sectional sample; otherwise give `prevalence=` and `prevalence_source=`, or leave them out and say why.

5. **Figures.** `ra.roc_figure`, `ra.calibration_figure` and `ra.decision_figure` save PDF and PNG with a record in `diagnostic-accuracy/figures/`; pass the returned path as `figure=` to `record`. Open each PNG and look at it. `researchzy-figures` (plugin `researchzy-manuscript`, when installed) checks size, fonts and colours.

6. **Write and check.** Write `diagnostic-accuracy/results.md` and `methods.md` from `results.json` only: every AUC and measure with its interval and method, n/N for each proportion, the cut-off with its source, the apparent AUC beside the corrected one, two tests compared by their paired difference, the rows without the reference standard. Then:

   ```sh
   python3 "$SKILL_DIR/scripts/check_accuracy.py" --probe diagnostic-accuracy/nodules.probe.json \
     --script diagnostic-accuracy/analysis.py --lint model.py \
     --text diagnostic-accuracy/results.md diagnostic-accuracy/methods.md
   ```

   | Row | On `fail` |
   |---|---|
   | `intervals`, `calibration`, `internal` | Record the missing interval, calibration (or `no_calibration` with its reason) or `ra.optimism` result, and run the script again |
   | `predictive`, `thresholds`, `leakage` | Remove the result, or supply what it lacks: the sourced prevalence, a cut-off from the plan or development data, a clean probe |
   | `paragraphs`, `apparent`, `comparison` | Print the bounds, the corrected AUC, or the paired difference with its interval |
   | `cutoff_text`, `verification`, `methods` | Say where the cut-off came from; state the rows without the reference standard; name each interval method |
   | `text` mismatch | Copy the recorded value; an interval past 1 was a Wald interval |
   | `complete`, `ledger`, `hashes`, `script` | Fix the script and run it again |

   `lint` lists leads (a scaler or selector fitted before the split, a split that ignores patients): look at each line it names; leads never fail. A `not_checked` row is reported as not checked, never as passed.

7. **Hand over** `results.md`, `methods.md`, the figures and `check.md`, with the probe's problems and how each was settled, every `not_checked` row, and the leads you looked at.

## Outputs

| File in `diagnostic-accuracy/` | Content |
|---|---|
| `plan.md` | Question, design, datasets, cut-off and source, predictors, thresholds, methods, seed |
| `<data>.probe.json` | Leakage, verification, clustering, splits, events per parameter, separation |
| `analysis.py` | The kept analysis script, with the pipeline function for a model |
| `results.json`, `ledger.jsonl` | Every result with `extra["accuracy"]`, hashes and versions |
| `figures/` | ROC, calibration and decision curves: PDF, PNG and a record |
| `results.md`, `methods.md`, `check.md` | The text and its last check |

## Rules

- Never invent data, cut-offs, prevalences, coefficients or citations. Every number in the text comes from `results.json` or the probe; a fact in no file is `[Author input needed: …]`.
- Never change the user's data files or scripts; corrected copies go in `diagnostic-accuracy/`.
- A cut-off is never chosen on the data it is evaluated on. An apparent AUC is never reported alone.
- Thresholds of any kind (an AUC "good" above some value, events per parameter, a decision-curve range) are conventions the user chooses and names with a source; report values without verdicts.
- When asked what a result means for a patient, say that the skill gives no clinical advice, and describe what the study estimates for its population.
- Say in the methods which steps an AI model carried out (probing, code, analysis, drafting).

## Related files

| File | Open when |
|---|---|
| [references/input-and-probe.md](references/input-and-probe.md) | Steps 1 and 2: data shape, designs, partial verification, clustering, splits, the probe |
| [references/accuracy-measures.md](references/accuracy-measures.md) | Step 3: 2x2 measures, intervals, likelihood ratios, AUCs, comparing two tests, predictive values |
| [references/model-development-and-validation.md](references/model-development-and-validation.md) | A model: predictors, the pipeline function, optimism, null-label check, calibration, external validation |
| [references/thresholds-and-decision-curves.md](references/thresholds-and-decision-curves.md) | Step 4: cut-off sources, prevalence, decision curves, writing them up |
| `scripts/probe_accuracy.py`, `scripts/rz_accuracy.py`, `scripts/check_accuracy.py` | The steps above; `--help`, or the module docstring of `rz_accuracy.py` |
| `scripts/rz_results.py`, `scripts/check_results.py`, `scripts/rz_figure.py` | Copies from `researchzy-statistics` and `researchzy-figures`: the result file, the number check, the figure style |
