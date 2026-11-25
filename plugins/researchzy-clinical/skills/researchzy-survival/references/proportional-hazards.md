# Proportional hazards

## What the test looks at

A Cox model assumes that each hazard ratio stays the same over follow-up. For each parameter, the scaled Schoenfeld residuals at the event times estimate β(t), the log hazard ratio as it moves with time; under proportional hazards β(t) is flat. The Grambsch-Therneau test regresses the scaled residuals on a transformed time g(t): one chi-square on 1 df per parameter, and a global one on as many df as the model has parameters.

## How `ph_test` computes it

With r the Schoenfeld residuals of the d event rows (from statsmodels; censored rows are NaN), V the model's covariance, g the transformed event times centred on their mean, and u = Σ g r:

| Test | Statistic | df |
|---|---|---|
| Parameter j | d (uV)_j² / (V_jj Σ g²) | 1 |
| Global | d u′Vu / Σ g² | number of parameters |

This is the original approximation, which replaces each event's information by the average one. Some programs now compute the exact score test, so their values differ slightly. With tied event times, statsmodels' residuals use the mean of the whole risk set rather than Efron's adjusted mean; the record then carries a note, and the statistic can differ slightly from programs that adjust.

| `transform` | g(t) |
|---|---|
| `km` (default) | 1 minus the Kaplan-Meier estimate of all rows of the model, just after t |
| `rank` | The rank of t among the event times, ties given their average rank |
| `identity` | t |
| `log` | log t (event times above 0) |

The result depends on the transform: choose it in the plan and name it in the methods. One model, one transform; trying several and reporting the smallest p-value is not allowed.

## The plot

`ph_test` draws `survival/ph-<model>.png`: for each chosen parameter, β̂ plus its scaled residuals against g(t), a local mean (lowess without robustness weights, so that no event is discounted as an outlier), and a dashed line at β̂. Read the local mean:

- flat near the dashed line: consistent with a constant hazard ratio;
- rising or falling: the hazard ratio changes with time; read the direction from the axis;
- crossing zero for a group indicator: the curves cross, and one hazard ratio averages effects of opposite sign.

With few events in a group the points form bands, one per group; the local mean is what to read. Choose the parameters to draw with `plot=[...]` when the model has many.

## A description, not a gate

A large p-value does not show that hazards are proportional: with few events the test has little power, and with many it finds departures too small to matter. Report the test, the plot and what they show; never write that the assumption "holds" or was "met". Do not switch to another model because p falls below 0.05 unless the plan said so; if it did, quote the plan.

## The planned alternative

The plan names one before any result. Report it beside the hazard ratio when the test or the plot shows hazards that are not proportional, and say that it was planned.

| Alternative | How | Report |
|---|---|---|
| Stratified Cox | `rs.cox(data, ["arm", "age"], reference={"arm": ...}, strata="stage")` when the variable that breaks proportionality is a covariate, not the comparison | Hazard ratios of the other parameters; none for the stratifying variable |
| A hazard ratio per period | Split follow-up at cut points fixed in the plan (start-stop rows, see below) and use one indicator per period as covariates | One hazard ratio per period with its interval, and the cut points |
| RMST difference | `rs.rmst(data, "arm", tau=..., reference=...)`, τ within every group's follow-up | The difference in mean time free of the event up to τ, with its interval |

Splitting at one cut point, with `raw`, `DATA` and `DROP` as in the analysis script of [Kaplan-Meier, log-rank and Cox](km-logrank-cox.md):

```python
CUT = 365                                                    # days, from the plan
days = pd.to_numeric(raw["days"], errors="coerce")
first = raw.assign(start=0.0, stop=days.clip(upper=CUT), status=raw.status.where(days <= CUT, "1"))
second = raw[days > CUT].assign(start=float(CUT), stop=days[days > CUT])
split = pd.concat([first, second]).sort_index()              # a patient's two rows keep its index: one row number
split["chemo_early"] = ((split.arm == "chemoradiation") & (split.start == 0)).astype(int)
split["chemo_late"] = ((split.arm == "chemoradiation") & (split.start == CUT)).astype(int)
periods = rs.prepare(split, time="stop", event="status", entry="start", id="patient_id", mapping={"1": 0, "2": 1},
                     time_unit="days", time_zero="date of diagnosis (plan, section 2)", drop=DROP, source=DATA)
by_period = rs.cox(periods, ["chemo_early", "chemo_late"])
```

Here `"1"` is the censored code, so the first period of a patient who lives past the cut point ends censored. A row with a time of 0 cannot form an interval: `prepare` names it, and it goes into `DROP` with that reason. τ for RMST, cut points and landmarks are conventions the plan fixes in advance; none of them is chosen after seeing the curves.
