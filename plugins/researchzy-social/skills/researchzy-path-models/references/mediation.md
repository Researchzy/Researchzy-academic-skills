# Mediation

## The estimate

With linear equations for M and Y, and no X×M term, the indirect effect is the product a·b: a from the M equation, b from the Y equation with X held constant. The direct effect is c′. When both equations use the same rows and the same covariates, the total effect c from regressing Y on X and those covariates equals c′ + a·b exactly: a quick check of both.

- **The estimate is the full-sample product.** `pt.bootstrap_indirect` evaluates each defined parameter on the coefficients fitted to all analysed rows. The mean of the bootstrap draws is not an estimate of anything the paper reports; `check_paths.py` recomputes every defined parameter from the recorded coefficients and fails one that differs.
- **The standard error** recorded as `se` is the standard deviation of the draws. Print it only beside the interval.
- **Same rows.** Every equation is fitted on the rows complete in all model variables. Fitted one at a time, the a and b equations can use different respondents, and the product then mixes two samples.

## Defined parameters

| Model | Defined parameters |
|---|---|
| One mediator | `ind := a*b`; `total := cp + a*b` |
| Parallel mediators M1, M2 | `ind1 := a1*b1`, `ind2 := a2*b2`, `total_ind := a1*b1 + a2*b2`, `contrast := a1*b1 - a2*b2` |
| Serial X → M1 → M2 → Y | `ind_serial := a1*d21*b2` (d21 labels M1 in the M2 equation), plus `a1*b1` and `a2*b2` for the other routes |

Pass them as `defined={...}`, or write them in the model block and leave `defined` out. Two separate one-mediator analyses are not a serial model. A difference between two indirect effects is claimed only from the interval of their contrast.

## Intervals

`extra["paths"]["interval"]["method"]` names the interval that was computed, with `draws`, `seed` and `failed` (draws that could not be fitted, which the text reports when there are any).

| `method` | What it is | Use |
|---|---|---|
| `percentile` | Quantiles of the case-resampling bootstrap draws | The default |
| `bca` | Percentile bounds shifted for bias and skew (jackknife acceleration); `bca` in the record holds z0 and the acceleration | When `model.md` chooses it |
| `monte_carlo` | Draws of a and b from their estimated sampling distribution | When the user supplies it from another tool |
| `quasi_bayesian` | Simulation from the coefficients' sampling distribution: what statsmodels' `Mediation(...).fit()` does by default | Only as what ran |
| `bc` | Bias-corrected without acceleration: what pingouin's `mediation_analysis` reports | Never kept: record it with `kept=False` beside a percentile or BCa result |

What the packages do, as read from their code when this skill was written; check the installed version:

- **statsmodels `Mediation`**: `fit()` simulates from the sampling distribution unless `method="bootstrap"`, and its summary prints the **mean of the simulated effects** as the estimate. Record the full-sample a·b from the fitted equations as the estimate and the package's bounds with method `quasi_bayesian` (or `percentile` for its bootstrap); pass `rng=SEED`.
- **pingouin `mediation_analysis`**: a bias-corrected bootstrap with 500 draws by default, unseeded unless `seed=` is given. Its point estimate is the full-sample product.

The number of draws is a convention (5000 is common); it is set in `model.md`. To see whether it is enough, run once with a second seed: if a bound changes at the printed precision, raise the draws. A p-value is not recorded for an indirect effect: the interval is the result.

## What is not evidence

| Not evidence | Why | Instead |
|---|---|---|
| Sobel test | It assumes a normal sampling distribution of a·b, which is skewed | The bootstrap interval |
| Baron-Kenny steps | A significant total effect is not required for an indirect effect; the steps never estimate a·b | a, b, c′ and a·b with intervals |
| "Full" or "partial" mediation | Whether c′ is significant depends on sample size and power, not on the process | The direct and indirect effects with their intervals |

## Proportion mediated

a·b / c is reported only with its own bootstrap interval, and only when the interval of the total effect c lies well away from zero. With a small or uncertain total, the ratio can exceed 1 or turn negative. Otherwise leave it out and say why.

## Outside this skill

A binary mediator or outcome (logistic or probit equations) needs a counterfactual decomposition, not a product of coefficients on the logit scale; so does an X×M interaction. Say that a dedicated tool is needed, and stop.

## Sensitivity

The M-Y path has no design protection, so a mediation result carries a sensitivity analysis. With R and the package mediation, `mediate()` followed by `medsens()` gives ρ, the correlation of the M and Y residuals at which the indirect effect would be zero; record `{"status": "done", "rho_at_zero": ..., "tool": "R mediation <version>"}`. Without them record `{"status": "not_done", "reason": "..."}` and write in the limitations that no sensitivity analysis was done. No threshold makes a ρ "robust": report the value and let the reader judge.

## Recording

`pt.bootstrap_indirect` returns `extra["paths"]` with `kind` `mediation`, `model`, `n`, `equations` (n, n alone, residual df), `coefficients` (value, SE, t, p, interval, standardized), `defined`, `interval`, and the column descriptives. Add `sensitivity` before `rz.record`, and `deviation` when the model differs from the registered one. Record the estimate with `effect_size="estimate"` and no p-value.

## Writing

> In the 314 respondents with complete data, autonomy was associated with meaning (a = 0.36, 95% CI 0.26 to 0.46), and meaning with engagement with autonomy held constant (b = 0.31, 95% CI 0.22 to 0.39). The indirect effect was 0.11 (95% CI 0.07 to 0.16; percentile bootstrap of cases, 5000 draws) and the direct effect c′ = 0.07 (95% CI −0.01 to 0.16). Because all variables were measured in one survey wave, the results are consistent with the hypothesised paths but cannot order them in time.

> 在314名数据完整的受访者中，自主性与意义感正相关（a = 0.36，95% CI [0.26, 0.46]）；控制自主性后，意义感与投入正相关（b = 0.31，95% CI [0.22, 0.39]）。间接效应为0.11（95% CI [0.07, 0.16]；个案百分位bootstrap，5000次），直接效应c′ = 0.07（95% CI [−0.01, 0.16]）。所有变量来自同一次调查，结果与假设的路径一致，但不能确定先后顺序。

The numbers are an illustration; every number in a real text comes from `results.json`.
