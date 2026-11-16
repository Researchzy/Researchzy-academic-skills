# Pooling

`meta_pool.py` pools each pool of `effects.csv` as `plan.md` says, records every result in `meta-analysis/results.json`, and writes `pooled.md` and the plots. The plan is fixed before any pooled number is seen; a choice made afterwards is a deviation, recorded in `plan.md` with its date and reason, and the original analysis stays reported.

## The plan

| Item | Default (a convention; the user may change it) | Flag |
|---|---|---|
| Measure per outcome | The scale the studies share: MD when all use one unit, SMD when scales differ, OR or RR for events | `effect_sizes.py --measure` |
| Model | Random effects | `--model random` or `fixed` |
| τ² estimator | REML | `--tau2 REML`, `PM`, `DL` |
| Interval | Hartung–Knapp with its floor; Wald as a sensitivity analysis | `--ci HK` or `Wald` |
| Level | 95 % | `--level 0.95` |
| Primary outcome | The one the review question names | `--primary` |
| Subgroups | Only study characteristics named before pooling, each with a reason | `--subgroup` |
| Several arms | Combine against the control | `effect_sizes.py --combine`, `--split`, `--drop` |
| Zero cells, rare events | Decided per binary outcome | `effect_sizes.py --sparse` |

## Fixed or random effects

The model follows from how the studies differ, never from I² or the Q test. Fixed effect assumes one true effect shared by every study; random effects assumes the true effects vary around a mean. When populations, doses, follow-up or settings differ, random effects is the honest description.

| Acceptable reason | Not a reason |
|---|---|
| "The trials differed in dose, population and follow-up, so one common effect could not be assumed." | "Random effects because I² was 65 %." |
| "All trials used the same protocol in one population (a multicentre programme), so a common effect was assumed." | "Fixed effect because the Q test was not significant." |
| | "The model depended on the heterogeneity found." |

`check_meta.py` fails a sentence that ties the model to I², Q or a heterogeneity test.

## τ² estimators

- **REML** (default): Fisher scoring from the DerSimonian–Laird value, truncated at 0, at most 100 iterations. If it does not converge, the pool uses Paule–Mandel and the record says so (`tau2_method`, `tau2_method_planned`, `tau2_converged`).
- **Paule–Mandel**: the τ² at which the generalised Q equals k − 1; 0 when Q at τ² = 0 is already below k − 1.
- **DerSimonian–Laird**: only when the user asks for it. (Q − df)/C is negative whenever Q < df; τ² is then 0 and the untruncated value is kept as `tau2_raw`. Some software reports the negative value and lets the weights go negative; never print it.

The two estimators not used run as sensitivity analyses.

## Interval methods

- **Hartung–Knapp** (default): the variance of the pooled estimate is scaled by q = Σw*(y − μ)²/(k − 1) and the interval uses t on k − 1 df. When q < 1 the plain method can be narrower than the Wald interval; the floor (Knapp and Hartung's ad hoc correction) uses max(1, q), so the interval is never narrower. `hk_floor_applied` says when it acted.
- **Wald**: μ ± z × SE. It is too narrow when k is small, which is why it is the sensitivity analysis.

The test statistic follows the interval: t with k − 1 df for Hartung–Knapp, z for Wald.

## Prediction interval

μ ± t(k − 2) × √(τ² + SE²), with the SE of the chosen interval method (Higgins, Thompson and Spiegelhalter 2009). It estimates where the true effect of a new comparable study is likely to lie, so it is reported for every random-effects pool with k ≥ 3. With k < 3 or a fixed-effect model there is none, and the record says why; the text then says so too.

## Heterogeneity

Q around the fixed-effect mean (around the Mantel–Haenszel estimate for `mh`), with k − 1 df and its p; I² = (Q − df)/Q truncated at 0 (Higgins and Thompson 2002, the same whatever the τ² estimator) with `I2_raw` kept; τ² and τ from the chosen estimator. I² is a proportion of observed variance, not an amount of heterogeneity: report τ² or τ and the prediction interval beside it.

## Zero cells and rare events

Inverse-variance pooling relies on large-sample approximations that fail when events are few, and adding 0.5 to every cell pulls estimates towards no effect. `effect_sizes.py` therefore stops a binary pool with a zero cell, or with a pooled event rate below 1 % (a convention), until the plan chooses:

| `--sparse` | What it does | Use when | Sensitivity run |
|---|---|---|---|
| `mh` | Mantel–Haenszel fixed effect from the counts, no correction (OR, RR, RD) | Every study has 2×2 counts; zero cells in one arm are handled | Peto (OR), inverse variance with 0.5 in zero-cell studies |
| `peto` | Peto one-step OR, fixed effect | Very rare events, arms of similar size, effects not large; Peto is biased otherwise | Mantel–Haenszel, inverse variance with 0.5 |
| `cc` | 0.5 added to every cell of the studies with a zero cell only; then the planned model | When random effects are needed and the counts allow it | Without those studies; Mantel–Haenszel |
| `iv` | The planned inverse-variance model | Rare events but no zero cell, accepted knowingly | Mantel–Haenszel; Peto (OR) |

Mantel–Haenszel and Peto are fixed-effect methods: they replace the planned random effects, the record notes it, and there is no prediction interval. Q is computed from each study's own estimate. A random-effects model for rare events needs a binomial-normal mixed model, which this skill does not fit: say so and stop if the plan requires one.

## What the skill does not do

Network meta-analysis, individual participant data, Bayesian models, the bivariate or HSROC models of diagnostic accuracy, multivariate and robust-variance models (each study enters a pool once instead), pooled single-arm proportions (they need a binomial mixed model), data reconstructed from survival curves, fail-safe N and p-curves. When the question needs one of these, name the method and the kind of tool it needs, and stop.
