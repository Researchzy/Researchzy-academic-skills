# Panel fixed effects, synthetic control and weighting

## Panel fixed effects

**When.** A treatment that varies within units over time (an exposure, a dose) without a clean adoption date. A binary treatment that switches on for good is a DiD: the probe sends it to the DiD route.

**Assumption.** Strict exogeneity given the unit effects: within a unit, changes in treatment are unrelated to the shocks to the outcome, so past outcomes do not steer later treatment and no time-varying confounder moves both. The within estimator is not a design by itself: `plan.md` says why the within-unit changes are as good as random.

```python
fe = ct.twfe(panel, unit="firm", time="year", outcome="sales", regressors=["exposure"], cluster="firm")
```

Units whose treatment never changes contribute nothing (`facts.units_without_within_variation`). Record their number in `within_variation`, which is `pass` when reported. Cluster at the level of assignment and report G and treated G (here, clusters with a unit whose treatment changes).

**Few treated clusters.** With 6 or fewer treated clusters (after MacKinnon, Nielsen and Webb 2023; a convention), cluster-robust intervals are unreliable. Add `randomization_inference`:

```python
ri = ct.ri_pvalue(df["treated_group"].to_numpy(), statistic, B=999, seed=SEED, clusters=df["state"], strata=None)
```

`assignment` is the 0/1 label that was assigned per cluster; `statistic(a)` re-estimates with a permuted label (for a common adoption date, the 2×2 DiD with `a` as the treated group). Treatment must be constant within the permuted clusters. The p-value counts the observed assignment, (1 + hits) / (B + 1), so it is never below 1/(B + 1). Record `{"status": ..., "B": 999, "p": ri["p"]}`.

## Synthetic control (basic)

**When.** One treated aggregate unit (a state, a country), untreated donors that are comparable, and a long pre-period. With several treated units the probe returns `ambiguous`: analyse each one on its own, or use the DiD route.

**Estimand and assumption.** The effect on the treated unit in each post period. Assumption: a weighted average of donors, with non-negative weights summing to one, reproduces the path the treated unit would have had, and no donor was touched by the treatment or by a large shock of its own (Abadie, Diamond and Hainmueller 2010; Abadie 2021).

```python
wide = panel.pivot(index="year", columns="state", values="smoking")      # rows in time order
sc = ct.sc_placebos(wide, treated="CA", T0=19)                            # T0: number of pre-treatment years
```

This basic version matches the pre-period outcome path only. It uses no covariates and no predictor weights, so with a short pre-period the fit can follow noise. Fix the donor pool before looking at the effect: drop donors with a similar policy or a large shock of their own, and record the pool in `plan.md`.

- `pre_fit`: compare the pre-period RMSPE with the scale of the outcome and with the placebos' (`pre_fit_rank`; 1 is the best fit). A poor fit is `fail`, and then there is no estimate. Augmented synthetic control and synthetic DiD are outside this skill.
- `placebos`: each donor is fitted as if treated. The p-value is the treated unit's rank among the J + 1 post/pre RMSPE ratios divided by J + 1. It is never below 1/(J + 1) (the probe prints that floor) and never a t-ratio. Record `{"status": ..., "value": {"J": sc["J"], "p": sc["p"]}}`.
- Record the headline as the average post-period gap, without an interval: the inference is the placebo p.
- Robustness rows: leave out each donor with positive weight in turn; move the adoption date earlier (an in-time placebo).

## Propensity-score weighting

**Estimand.** ATT (the effect on the treated) or ATE (on everyone), chosen in `plan.md`. Trimming moves either to the units kept.

**Assumption.** No unmeasured confounding given the covariates, which cannot be tested: argue it from how treatment was chosen. Also overlap: every unit could have ended up treated or untreated. Covariates are measured before treatment, never something the treatment could change.

```python
w = ct.ipw(df, treatment="program", outcome="earnings", covariates=["age", "educ", "earn_before"],
           estimand="ATT", trim=(0.1, 0.9), B=999, seed=SEED)          # doubly_robust=True for AIPW
```

- `overlap`: score ranges by group, and the share of controls inside the treated range and of treated units inside the control range (`w["overlap"]`).
- `trimming`: units scored outside [0.1, 0.9] are dropped, the rule of thumb that Crump, Hotz, Imbens and Mitnik (2009) give. Clipping scores is not trimming: it keeps off-support units with capped weights and estimates something else. Record `{"method": "drop", "trimmed_share": ...}` from `w["trimming"]`. When more than half the units are dropped (`w["ate_allowed"]` is false), report no ATE, only the effect for the units kept (`w["population"]`).
- `balance`: standardised differences after weighting. The convention is |d| < 0.1 (Austin 2009); others accept 0.25 (Stuart 2010, after Rubin 2001). Our choice is 0.1. A covariate above it is `fail`. Never use a significance test of balance, which mixes imbalance with sample size.
- `max_weight`: the largest weight's share of its group (`w["max_weight_share"]`). One unit carrying a large share means the estimate rests on it; say so.
- Sensitivity to unmeasured confounding is not computed here. Say so in the limitations.
