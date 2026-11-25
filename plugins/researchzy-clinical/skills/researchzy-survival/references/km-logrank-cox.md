# Kaplan-Meier, log-rank and Cox

## The analysis script

One script, `survival/analysis.py`, reads the data and never writes to it. Every analysis goes through `rz.record`.

```python
"""<study>: overall survival by arm. Plan: survival/plan.md. Run from the project folder: python3 survival/analysis.py"""
import sys
import pandas as pd
sys.path.insert(0, "<SKILL_DIR>/scripts")      # written out in full; to share, copy rz_results.py, rz_survival.py, rz_figure.py
import rz_results as rz
import rz_survival as rs

rz.OUT, DATA = "survival", "data/cohort.csv"
raw = pd.read_csv(DATA, dtype=str, keep_default_na=False)          # codes as written; keep the index (row numbers)
DROP = {11: "negative time: entry error (user, 2026-11-18)", 181: "duplicate of row 8 (user, 2026-11-18)"}
data = rs.prepare(raw, time="days", event="status", mapping={"1": 0, "2": 1}, time_unit="days",
                  time_zero="date of diagnosis (plan, section 2)", id="patient_id", drop=DROP, source=DATA)
q = "Does overall survival differ between surgery and chemoradiation?"

km = rs.km_table(data, "arm", times=list(range(0, 2401, 600)), labels={"surgery": ["surgery", "surgical", "手术"]})
for g in km["groups"]:
    rz.record(id=f"km_{g}", question=q, family="km", role="secondary", **rs.fields(km, group=g))
rs.km_figure(km, "km-arm")
rz.record(id="logrank_arm", question=q, family="logrank", role="secondary", **rs.fields(rs.logrank(data, "arm")))
cox = rs.cox(data, ["arm", "age", "stage"], reference={"arm": "surgery", "stage": "I"})
rz.record(id="cox_arm", question=q, family="os", role="primary", **rs.fields(cox, parameter="arm[chemoradiation]"))
ph = rs.ph_test(cox, model="cox_arm", transform="km", plot=["arm[chemoradiation]"])
rz.record(id="cox_arm_ph", question=q, family="ph", role="secondary", **rs.fields(ph))
rmst = rs.rmst(data, "arm", tau=1800, reference="surgery")         # tau from the plan
rz.record(id="rmst_arm", question=q, family="rmst", role="secondary", **rs.fields(rmst, group="chemoradiation"))
rz.finish(script=__file__, data=[DATA], settings={"tau_days": 1800})
```

- Build print times with `range`: `check_results.py` reads a literal list of eight or more numbers as typed-in data.
- Families follow `researchzy-statistics`: one per claim. Analyses that test the same claim share a family and are corrected with `rz.correct`. The log-rank and proportional-hazards records have no record-level p: their p-values stay in `extra` because they describe.
- Each record holds its `extra["survival"]`: the time unit, time zero, the mapping, every row left out with its reason, and the numbers of its kind. A median that is not reached has no number, so the Kaplan-Meier record's estimate is the lowest Kaplan-Meier value, and `extra` says `not_reached`.

## statsmodels' defaults, and what `rz_survival` does instead

| statsmodels | Consequence | `rz_survival` |
|---|---|---|
| The status is a weight (`SurvfuncRight`, `survdiff`, `PHReg`) | With codes 1/2 a censored patient counts as an event and a death as two, without a warning | `prepare` maps the codes the user confirmed and refuses any other |
| `PHReg(ties="breslow")` | Hazard ratios pulled toward 1 when many events share a time | `ties="efron"` always, recorded |
| `PHReg(missing="drop")` | Rows vanish silently; n is unknown | Rows with a missing model value are listed with the reason, then `missing="raise"` |
| `quantile` gives NaN, `quantile_ci` an infinite bound | A median that does not exist | `not_reached` for the estimate and each bound |
| No proportional-hazards test | | `ph_test` |
| `PHReg` counts a row at risk at its own entry time | Rows enter one event time early | Entry times moved forward by 1e-9 of the longest time: entry < t <= exit, as in the Kaplan-Meier estimate |
| `survdiff` with strata does not split entry times | An error | Refused, with the reason |
| The median is the first time S(t) < 0.5 | Other programs take the first time S(t) <= 0.5, or the middle of a flat stretch at 0.5 | A note in the record when the curve equals 0.5 over an interval |

## Kaplan-Meier

- The band is pointwise (log(-log) transform of Greenwood's standard error), not a band for the whole curve.
- The number at risk at t counts rows with time >= t, or entry < t <= exit with entry times. Choose print times within follow-up.
- The median is the first time the curve falls below 0.5. Its interval (Brookmeyer and Crowley) is the set of event times at which a z test of S(t) = 0.5 on the log(-log) scale is not rejected. A curve that stays above 0.5 has no median: estimate and upper bound are `not_reached`; the lower bound may still be a time.
- Follow-up: the reverse Kaplan-Meier median (censoring counted as the event) per group, with the longest time.
- `labels` gives the names the text uses for a group ("surgical arm", "手术组"), so that `check_survival.py` finds them.

## Log-rank

`survdiff` returns the chi-square statistic and p; df is groups minus 1. Every event time weighs the same. Gehan-Breslow, Tarone-Ware or Fleming-Harrington weights (`weight_type`) only when the plan names them, because they change which differences the test looks for. A stratified test sums observed minus expected events and their variance within strata. When curves cross, the log-rank test loses power and its p-value is a description; report the planned alternative.

## Cox

- Every categorical covariate needs its reference level in `reference=`; a numeric covariate's hazard ratio is per one unit, and the text states the unit.
- A level without events is refused: it has no hazard ratio. The user merges it or leaves it out.
- `strata=` fits a stratified model: a separate baseline hazard per stratum, and no hazard ratio for the stratifying variable.
- The record holds each parameter's hazard ratio, interval, p and reference level, n, events, rows left out, events per parameter and whether the fit converged. Report a fit that did not converge to the user; do not interpret it.

## Writing the text

Results, from `results.json` only:

- Patients and events per group; rows left out and why.
- Median follow-up (reverse Kaplan-Meier) per group.
- The median per group with its interval, or "not reached".
- The number at risk at the times the figure prints, when the text uses them.
- Each hazard ratio with its interval, its p-value and the comparison it makes ("chemoradiation vs surgery").
- The proportional-hazards test with its time transform and what the plot shows; when hazards are not proportional, the planned alternative.
- RMST per group or the difference, with τ.

Methods: time zero; the event and how censoring was defined; the Kaplan-Meier estimate and its band; the log-rank test and its weights; the Cox model with Efron's method for ties; the proportional-hazards test (Grambsch-Therneau on scaled Schoenfeld residuals, with its time transform) and plot; missing values and n per model; statsmodels and its version, from `results.json`.

Never write "no difference" from a large p-value, or that proportional hazards hold. A full Results section goes to `researchzy-writing` (plugin `researchzy-manuscript`, when installed).
