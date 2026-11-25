# Thresholds and decision curves

## Where a cut-off comes from

| `source` | Meaning | Also needs |
|---|---|---|
| `plan` | Fixed in the protocol or analysis plan before the data were seen | The plan's section in `citation`, when there is one |
| `development` | Chosen on the development data, for example by `ra.dev_cutoff` (Youden's J) | Development rows only |
| `published` | Taken from a publication | `citation`: the paper with its table or page |

A cut-off chosen on the test data is refused by `record` and failed by the check: choosing and evaluating on the same data overstates sensitivity and specificity. "Optimal" means nothing without the data and the rule that chose it; write "the cut-off with the largest Youden's J in the development data (2.31)". When the plan names no cut-off, report the ROC curve and AUC on the test data and the accuracy at a cut-off chosen on the development data.

`ra.dev_cutoff(y, score)` counts a score at or above the cut-off as positive and returns the lowest cut-off with the largest J. Record the cut-off on every 2x2 of a score, `threshold={"value": 2.5, "source": "plan"}`: the check fails a 2x2 of a model that has an AUC and no cut-off.

## Prevalence

Predictive values and net benefit use the sample's prevalence in a consecutive or cross-sectional design, and otherwise the target population's prevalence with its source. Record the source as the user gives it, with the date it was read. With the `researchzy` plugin connected, `search_papers` can find a prevalence study of the intended population; read the value in the PDF through `get_paper_files` and quote its table or page.

## Decision curves

The net benefit of treating every unit whose predicted risk is at least the threshold probability pt:

NB(pt) = sensitivity · prev − (1 − specificity) · (1 − prev) · pt / (1 − pt)

In a consecutive sample this is TP/n − FP/n · pt / (1 − pt). Treat-all is prev − (1 − prev) · pt / (1 − pt); treat-none is 0. The odds pt / (1 − pt) is the weight of a false positive against a true positive that a decision maker accepts at that threshold.

- The thresholds come from the plan: the range of risks at which someone would act, fixed before the curves are seen, never chosen where the model looks best. They run strictly between 0 and 1, increasing; the skill has no default range.
- A case-control or enriched sample needs `prevalence=` and `prevalence_source=`; `net_benefit` refuses otherwise.
- `record(nb, at=[0.10, 0.20], ...)` keeps the net benefit at the planned thresholds the text will print; `ra.decision_figure` draws the whole curve.
- A decision curve compares strategies in the study population. It is not a recommendation for any patient.

## Writing it up

| Result | Print |
|---|---|
| Sensitivity, specificity, PPV, NPV | The value, n/N, the interval and its method, the cut-off and its source |
| LR+ and LR− | The value and interval; "not estimable" with the reason when undefined |
| AUC | The value, the interval and its method (DeLong, or bootstrap by patient), units and patients |
| Two tests | The paired difference with its interval, and p for DeLong or McNemar |
| A model | Apparent and corrected AUC; calibration intercept and slope with intervals; B and seed |
| A decision curve | Net benefit of the model, treat-all and treat-none at the planned thresholds |

The methods name the design and how units were sampled, the reference standard and the verification counts, the cut-off and its source, the interval methods, how several units per patient were handled, the steps the bootstrap repeated, and the software versions in `results.json`.

`check_accuracy.py` reads Chinese text the same way, for example `灵敏度为92.5%（37/40；95% CI 79.6%～98.4%）` or `AUC为0.86（95% CI 0.81～0.91）`; its labels include 灵敏度, 特异度, 阳性预测值, 阴性预测值, 似然比, 斜率, 截距, 净获益 and 截断值. A sentence that picks the "best" cut-off by Youden's index on the test set (测试集, 约登指数) fails `cutoff_text`.
