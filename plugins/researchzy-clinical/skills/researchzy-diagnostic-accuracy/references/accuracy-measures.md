# Accuracy measures

## The 2x2 table

`ra.cells(y, positive)` counts tp, fp, fn and tn from 0/1 arrays. `ra.two_by_two(tp, fp, fn, tn, design=...)` returns each measure with its numerator, denominator, interval and method.

| Measure | Formula | Interval |
|---|---|---|
| Sensitivity | tp / (tp + fn) | Clopper–Pearson (exact); Wilson with `method="wilson"` |
| Specificity | tn / (tn + fp) | As above |
| LR+ | sensitivity / (1 − specificity) | exp(log LR+ ± z·se), se² = 1/tp − 1/(tp + fn) + 1/fp − 1/(fp + tn) |
| LR− | (1 − sensitivity) / specificity | exp(log LR− ± z·se), se² = 1/fn − 1/(tp + fn) + 1/tn − 1/(fp + tn) |
| PPV | tp / (tp + fp) | Exact; only in a consecutive or cross-sectional sample |
| NPV | tn / (tn + fn) | As above |

The exact interval is the default because the Wald interval, p ± z·√(p(1 − p)/n), can pass 0 or 1 near them: for 37/40 it runs from 0.843 to 1.007. A measure that cannot be estimated has the value `None` and a reason: a zero denominator; LR+ when specificity is 1 (it is infinite). A likelihood ratio with a zero cell has a value and no log interval. Never replace an undefined value by 0 or 1, and add 0.5 to a cell only when the plan says so.

Print each proportion with its counts: "sensitivity 92.5% (37/40; 95% CI 79.6% to 98.4%, exact)". Overall accuracy, the share of correct results, depends on the prevalence; the skill does not report it.

## Predictive values and prevalence

PPV and NPV depend on the prevalence. In a case-control or enriched sample the sampling set the share of positives, so the table's PPV and NPV describe no real population: `two_by_two` returns `None` for them, with the reason. Given the target population's prevalence p and its source:

- PPV = sens·p / (sens·p + (1 − spec)(1 − p)), so logit(PPV) = log LR+ + logit(p);
- NPV = spec(1 − p) / (spec(1 − p) + (1 − sens)p), so logit(NPV) = −(log LR− + logit(p)).

The intervals carry those of the likelihood ratios through the logit with p held fixed; say so in the methods. `prevalence_source` names where p was read: a paper and its table, a registry and its year. A prevalence from memory or a default value is never used.

## AUC

`ra.auc(y, score)` is the Mann–Whitney estimate with ties counted half: the chance that a random positive unit scores above a random negative one. Higher scores must mean more likely positive; a score that ranks the other way gives an AUC below 0.5, which is reported as it is, never flipped after seeing the data.

| Units | Interval | Notes |
|---|---|---|
| One per patient | DeLong's standard error on the logit scale: logit(AUC) ± z·se / (AUC(1 − AUC)), transformed back | Stays inside 0 to 1, asymmetric near 1 |
| Several per patient | Percentile bootstrap over patients, `groups=` and `seed=` required | All units of a drawn patient come along; B = 2000 by default, a convention |

An AUC of 0 or 1 has no logit interval: report the counts instead. Verbal grades such as "excellent above 0.9" have no basis in the data; use one only when the user names it with its source.

## Two tests on the same patients

Whether two intervals overlap is no test of a difference: both estimates come from the same patients and are correlated.

| Question | Function | Result |
|---|---|---|
| Do the AUCs differ? | `ra.compare_auc(y, a, b)` | AUC(a) − AUC(b) with DeLong's paired variance, z and p; with several units per patient, a paired bootstrap over patients and no p |
| Do the sensitivities differ? | `ra.mcnemar_pair(y, a, b, among=1)`; `among=0` for specificities | The difference with Newcombe's paired interval (his method 10) and the exact McNemar p from the discordant pairs |

Record a comparison with `models=(first, second)`, in the order of the difference. The paired DeLong comparison is for two separate tests or models. Whether one added predictor improves a model is a likelihood-ratio test of that term, which belongs to `researchzy-statistics`.

## What a record holds

`ra.record` writes `extra["accuracy"]` beside the estimate and interval: `kind`, `model` (or `models`), `dataset` (`development`, `internal_validation`, `test`, `external`, or `study` for an accuracy study in which nothing was fitted), `design`, `units`, `patients` and `positives`; per measure its numerator, denominator and method, the 2x2 cells and the sample prevalence; for an AUC its method, and for a bootstrap the resamples and seed; the cut-off with its source; the probe's leakage status with the hash of the file it read. A 2x2 table gives one record per measure (`<id>.sensitivity` and so on); measures without a value are listed in `not_recorded` with their reasons, and asking for one with `measures=` raises its reason.
