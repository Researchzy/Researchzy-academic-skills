# Input and probe

## The data table

One row per unit. A unit is what the index test is applied to: a patient, or a lesion, nodule, eye or visit that belongs to a patient. The user names every column; the probe guesses none.

| Role | Option | Notes |
|---|---|---|
| Patient id | `--id` | Required. Rows with the same id are one patient |
| Unit within a patient | `--unit` | A lesion or visit id; the same unit twice for one patient is a duplicate |
| Reference standard | `--reference`, `--positive` | Two values; `--positive` names the one that means the condition is present |
| Index result | `--index` with `--index-positive` (a categorical result) or `--threshold` (a score) | The threshold is the planned cut-off: a score at or above it is positive |
| Split | `--split`, `--development`, `--test` | The user's split; other split values (a validation set) are counted too |
| Date | `--date` | Only for a temporal split |
| Candidate predictors | `--predictors a,b,c` | For events per parameter and separation; a text column is categorical |

An empty cell, `NA`, `.` or `缺失` means missing; add other codes with `--na`. Dates may be written 2021-03-05, 2021/3/5 or 2021年3月5日; full-width digits are read as digits. The probe writes row numbers, never patient ids.

With no individual rows (a published 2x2 only), skip the probe, use `ra.two_by_two` with the four counts, and say that clustering, verification and leakage could not be checked.

## Sampling designs

| `design` | Meaning | Predictive values and net benefit |
|---|---|---|
| `consecutive` | Every eligible patient in a period, given both the index test and the reference standard | From the table |
| `cross_sectional` | A sample of the target population, not selected on the outcome | From the table |
| `case_control` | Patients chosen because they have, or do not have, the condition | Only with the target population's prevalence and its source |
| `enriched` | Positives over-sampled, or negatives under-sampled, by design | As for case-control |

Sensitivity, specificity and likelihood ratios are reported under every design. A case-control sample tends to hold clearer cases and healthier controls than practice does, which inflates them; say so among the limitations.

## Partial verification

A unit without a reference result has an unknown true status. The probe's `verification` counts these units by split and by index result. When mostly test-negative units go unverified (often only a positive test leads to biopsy), sensitivity is overestimated and specificity underestimated among the verified units. Report the counts as the probe gives them, for example "23 of 163 test-negative nodules had no biopsy (14.1%)", analyse the verified units, and name the bias among the limitations. Correcting verification bias or imputing reference results is outside this skill.

`index_missing` counts verified units without an index result. Report how many, and whether they are excluded or classed positive or negative, as the plan says.

## Several units per patient

Units of one patient are not independent. When `repeated_ids` is a problem:

- pass `groups=<patient ids>` to `auc`, `compare_auc`, `calibration`, `optimism` and `null_label_check`: AUC intervals then come from a bootstrap over patients, calibration intervals are cluster-robust, and resamples and folds keep a patient's units together;
- McNemar's test needs one unit per patient, and `mcnemar_pair` refuses clustered units;
- report units and patients: "281 nodules from 211 patients".

## Leakage between splits

Development and test data must not share a patient.

| Check | A problem when |
|---|---|
| `overlap` | A patient id appears under two split values; or a row has no id or no split value (such rows cannot be placed and are never skipped) |
| `identical_rows` | A row's predictors equal those of a row in another split: often one patient under two ids |
| `date_order` | With `--date`, a development row is dated on or after the first test date |

`leakage` in the probe sums up `overlap` and `date_order`. `rz_accuracy.record` refuses every `dataset="test"` result unless `probe=` names a probe whose `leakage` is `ok`; `check_accuracy.py` also checks that the probe read a file the analysis read. The fix belongs to the user: reassign the rows by patient, or remove the crossing patients from the test set with the reason; then probe again. Never edit the split yourself.

A test split sits in the same file as the development rows, so that the probe can compare them. Data from another source are `dataset="external"`; an accuracy study in which nothing was fitted is `dataset="study"`.

## Events per parameter and separation

`events` divides the count of the rarer outcome in the development rows by the number of candidate parameters (a categorical predictor with k levels counts k − 1). It has no pass mark: give the number to the user, who judges it against a source they name.

`separation` asks, by linear programming, whether a combination of the predictors splits the outcomes perfectly (`complete`) or with ties on the boundary (`quasi-complete`). Either way a maximum-likelihood logistic fit has no finite estimate. Report it and ask the user: a penalised or exact method is a change of plan, never a silent fix. Without scipy the check is `not_checked`.
