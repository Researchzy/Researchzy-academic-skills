# Model development and validation

## Before fitting

Write the candidate predictors into the plan before looking at how each relates to the outcome, with their coding: continuous predictors stay continuous, categories are named. Every step that learns from the data (univariate screening, stepwise selection, a transformation chosen by fit, tuning, imputation) is part of the model and is repeated in validation. Give the user the probe's events per candidate parameter, with no pass mark, and settle separation before fitting. Say in the plan whether rows with a missing predictor are excluded or imputed; an imputation happens inside the pipeline.

## The pipeline function

Write the whole modelling process as one function of the data it may learn from:

```python
def pipeline(X, y):
    """Scaling, the univariate filter and the logistic fit, all learnt from (X, y) only."""
    model = make_pipeline(StandardScaler(), SelectKBest(f_classif, k=4), LogisticRegression(max_iter=1000))
    model.fit(X, y)
    return lambda new: model.predict_proba(new)[:, 1]
```

It returns a function that gives a predicted risk for each new row. Nothing it uses may be fitted outside it: a scaler, imputer or selector fitted on all rows before the split has seen the test rows, and selection on all rows makes every later estimate optimistic. When the user brings a script like that, keep it unchanged, write the corrected pipeline in `analysis.py`, and run `check_accuracy.py --lint <their script>`: each lead names a line to look at.

## Internal validation: bootstrap optimism

`ra.optimism(pipeline, X, y, groups=patient_ids, B=200, seed=SEED)`:

1. fits the pipeline on all development rows and scores it on them: the apparent AUC, calibration slope, calibration intercept and Brier score;
2. B times, draws patients with replacement (a drawn patient brings all their units), fits the pipeline again on the resample, every step included, and scores the new fit on the resample and on the original rows;
3. averages the difference between the two scores: the optimism. The corrected value is the apparent value minus the optimism.

Record it with `dataset="internal_validation"` and the same `model` name as the apparent AUC. Report the apparent and the corrected AUC side by side, with B and the seed; B = 200 is a convention the user may change. Resamples that fail are counted in `failures` with examples: when many fail, tell the user before reporting.

## Null-label check

`ra.null_label_check(pipeline, X, y, groups=patient_ids, seed=SEED)` permutes the outcome R times (10 by default), runs the pipeline in a cross-validation grouped by patient, and scores the out-of-fold risks:

| Scored against | Expected | Clearly higher means |
|---|---|---|
| The permuted outcome | About 0.5 | A step sees the held-out rows |
| The true outcome | About 0.5 | The pipeline learns from something other than its arguments: a model or selection fitted outside it, or an outcome read from a global variable |

The margin is z null standard deviations of an AUC divided by √R, with z = 3 by default, a convention the user may change. The check sees only what runs inside the function; a selection made beforehand on all rows is what the lint looks for. A `problem` blocks every test-set result in `check_accuracy.py` until it is solved.

## Test data and external validation

Score the fixed model on the test split once, after the plan is final and the probe's `leakage` is `ok`: AUC, calibration and, when planned, a decision curve. Fit nothing on the test rows.

For a published model, apply its intercept and coefficients exactly as published, read from the paper with table and page, to the user's data, and record `dataset="external"`. A predictor the paper defines differently from the user's data is a finding to report, not something to adjust silently.

## Calibration

`ra.calibration(y, risk, groups=...)` gives:

- the calibration intercept (calibration-in-the-large): a logistic model of the outcome with logit(risk) as offset and only an intercept; 0 means the average risk is right;
- the calibration slope: the outcome regressed on logit(risk); 1 means the spread of risks is right, below 1 that the risks are too extreme;
- Wald intervals, cluster-robust by patient when patients have several units; the Brier score;
- a lowess curve without robustness iterations and observed proportions against mean predicted risk in tenths of risk, for `ra.calibration_figure`.

Each AUC of a model on a dataset needs a calibration result on the same dataset. A test value that is not a risk (a biomarker level, a points score) records `no_calibration` with that reason instead. The skill does not use the Hosmer–Lemeshow test, whose result depends on the grouping and its power on the sample size. A straight line drawn from the intercept and slope is not a calibration curve.

## Updating a model

Recalibration (a new intercept, or a new intercept and slope) and refitting are updates, not validation. Label them so, estimate them on development data, and validate the updated model again. Performance on the data used for the update is never reported as validation.
