# Instrumental variables and regression discontinuity

## Instrumental variables

**Estimand.** With a binary instrument and treatment, 2SLS identifies the average effect for compliers, the units whose treatment follows the instrument (Imbens and Angrist 1994). Name it so: "the effect of attending for pupils who attend because they won the lottery". The probe's `facts.compliance` gives their share.

**Assumptions**, each argued in `plan.md` from how the instrument arose: relevance (it moves the treatment), independence (as good as randomly assigned), exclusion (it reaches the outcome only through the treatment) and monotonicity (nobody is pushed the other way). No test validates exclusion; a passing over-identification test is not validity.

```python
fit = ct.iv_2sls(df, outcome="score", treatment="attended", instruments=["lottery"], covariates=["age"], cluster="school")
ar = ct.anderson_rubin(df, outcome="score", treatment="attended", instruments=["lottery"], covariates=["age"], cluster="school")
```

`iv_2sls` runs 2SLS in one step: never two stages by hand, whose second-stage errors are wrong. It also returns the first stage with its cluster-robust F, the reduced form, and OLS. `anderson_rubin` inverts the cluster-robust Anderson–Rubin test (Anderson and Rubin 1949) over a grid. The set is valid however weak the instrument, and can be unbounded or in pieces: report it as it comes.

| First-stage F (cluster-robust) | Reading | Do |
|---|---|---|
| Below 3.84 (χ²₁ at 5%) | The first stage is not distinguishable from zero; with one instrument the AR set is unbounded | No IV estimate: report the first stage and the AR set |
| Below 10 | Weak by the rule of thumb of Staiger and Stock (1997); Stock and Yogo (2005) tabulate critical values | The AR set is the headline interval (`check_causal.py` compares them) |
| 10 or more | | The 2SLS interval may lead; the AR set stays beside it |

The bar is disputed. Lee, McCrary, Moreira and Porter (2022) show that the usual 5% t-test needs F above 104.7 with one instrument; much applied work keeps 10. Our choice: always record the AR set, which Andrews, Stock and Sun (2019) recommend at any strength, and let it lead below 10. Raise `--f-low` to 104.7 when the paper's claim rests on the t-ratio. With one instrument the robust F equals the effective F of Montiel Olea and Pflueger (2013). With several it does not, and `causal_tools` computes only the robust F: say so in the diagnostic's detail.

Also: put OLS beside 2SLS, because the gap shows the direction of selection; a 2SLS estimate close to OLS with a weak first stage is suspect. Cluster at the level where the instrument varies (a lottery run per school: by school). A placebo outcome the instrument cannot affect, such as a pre-treatment outcome, should show no reduced-form effect; run it as a robustness row.

| Key | Record |
|---|---|
| `first_stage`, `reduced_form`, `ols` | `value`: `fit["first_stage"]`, `fit["reduced_form"]`, `fit["ols"]`; `pass` when reported in full |
| `first_stage_f` | `value`: the F; `statistic`: `{"name": "F", "value": F, "df": fit["first_stage"]["df"]}`; `pass` at 10 or more |
| `ar_set` | `value`: the `anderson_rubin` result; `pass` when bounded, `fail` when unbounded or empty |

## Regression discontinuity

**Estimand.** The effect at the cutoff for units at the cutoff (sharp), or for compliers at the cutoff (fuzzy, when take-up jumps by less than one: the probe's `facts.sharp`). It is local; a claim away from the cutoff needs assumptions this skill does not supply.

**Packages.** `rdrobust` (local linear fit, triangular kernel, MSE-optimal bandwidth and a robust bias-corrected interval; Calonico, Cattaneo and Titiunik 2014) and `rddensity` (Cattaneo, Jansson and Ma 2020; McCrary 2008 is the older density test). Both are GPL: install them only with the user's consent, call them, never copy their code. Read the installed help for argument names. Record the robust bias-corrected estimate and interval, the bandwidth and the effective n on each side. Without the packages the route is `not_attempted`: stop and say why.

Order, before any estimate is read:

1. **Manipulation.** The probe's binomial tests count units just below and just above the cutoff in the nearest 20, 50 and 100 observations; `most_common_values` shows heaping. Then run the `rddensity` test. If it rejects, record `density` as `fail` and report no point estimate: manipulation-robust bounds are outside this skill.
2. **Covariate balance.** Run each predetermined covariate as an outcome through `rdrobust`, each with its own bandwidth. A jump in a covariate that predicts the outcome means no estimate; never adjust it away.
3. **Estimate.** Use a local linear fit; polynomials of order 3 or more overfit at the boundary (Gelman and Imbens 2019).
4. **Bandwidths.** Run h/2, h and 2h (a convention) as robustness rows. Instability at or below h is the warning sign; drift far above h is expected.
5. **Placebo cutoffs.** Test away from the true cutoff, on one side at a time, so the real effect does not leak in.
6. **Donut.** Drop the observations nearest the cutoff and keep the bandwidth, as a robustness row.

**Discrete running variable.** Lee and Card (2008) proposed clustering on its values. Kolesár and Rothe (2018) show that those intervals can cover far less than nominal. Our choice: never cluster on the running variable. With few distinct values (the probe flags 30 or fewer, our working line), say that the estimate extrapolates between mass points. Local-randomization methods are outside this skill.

| Key | `pass` when | Record |
|---|---|---|
| `density` | The density test does not reject | p-value and bandwidths; the probe's binomial tests |
| `covariate_balance` | No predetermined covariate jumps | Estimate and interval per covariate |
| `bandwidths` | Sign and size stable over h/2, h, 2h | The rows |
| `placebo_cutoffs` | No jump at the placebo cutoffs | Cutoffs and estimates |
