# Heterogeneity, subgroups, sensitivity and small-study effects

## Sensitivity analyses

`meta_pool.py` runs these for every pool and records each as a secondary result without a p-value (a family of p-values would need a correction, and these are checks of robustness, not claims):

| Label | Runs when | Asks |
|---|---|---|
| `leave out <study>` | k ≥ 3 | Does one study carry the result? |
| `without estimated rows` | Some rows came from medians | Do the median conversions matter? |
| `fixed-effect` / `random-effects` | Inverse-variance pools | Does the model matter? |
| `tau2 by PM`, `tau2 by DL`, `tau2 by REML` | Random effects | Does the τ² estimator matter? |
| `Wald interval` / `Hartung-Knapp interval` | Random effects | Does the interval method matter? |
| `Mantel-Haenszel`, `Peto`, `without the studies given 0.5`, `inverse variance, 0.5 added ...` | Sparse binary pools | Does the zero-event method matter? |

Others need a deliberate step:

- **Risk of bias.** Put each study's overall judgement from `researchzy-risk-of-bias` (plugin `researchzy-evidence`, when installed) in a column such as `rob` and pool with `--subgroup rob`; the low-risk group is the restricted analysis.
- **An assumed ICC or correlation.** Copy the table to a new file with the alternative value (for example the ICC halved and doubled), run `effect_sizes.py` on it with `--out meta-analysis/icc-high`, and pool there with `--out meta-analysis/icc-high`. Report both; never overwrite the primary table.
- **Change against final values in an MD pool.** Pool the two kinds separately as two outcomes.

Report a sensitivity analysis by what changed: the estimate and interval, whether the conclusion holds. One that moves the estimate a lot is a finding about fragility, stated as such.

## Subgroups

- Only study characteristics named in the plan before pooling, each with the reason it could change the effect. A subgroup chosen after looking is exploratory and labelled so.
- Each group is pooled with the main model and its own τ². The test between groups is Q_between = Σ w_g (μ_g − μ̄)², with w_g from each group's Wald SE, on G − 1 df.
- The test runs only when every group has at least 4 studies (a convention): with fewer, the groups are described with their estimates and intervals and not compared. `check_meta.py` fails a recorded test that broke this rule.
- Compare groups through the test between them, never by noting that one group's interval excludes the null and the other's does not.
- A difference between subgroups is an observational comparison across studies: say "the effect was larger in trials of the higher dose", not "the higher dose caused a larger effect".

## Small-study effects

- Tests for funnel-plot asymmetry run only when k ≥ 10 (a convention; with fewer studies they have too little power to mean anything). Below that the record says `not run` with the reason, and the text must not cite a test (`check_meta.py` fails it).
- The test follows the measure, because for some measures the SE is tied to the effect itself:

| Measure | Test | What is regressed |
|---|---|---|
| MD, Z, HR, GENERIC | Egger (1997) | y on its SE, weights 1/SE²; the slope on the SE equals Egger's intercept |
| OR, RR | Peters (2006) | y on 1/N, weights S F / N (events and non-events); needs counts for every study |
| SMD | Egger with the modified SE √(1/n₁ + 1/n₂) (Pustejovsky and Rodgers 2019) | g on that SE |
| RD | None | No test is matched to the risk difference here |

- Each test is a weighted regression with its residual variance estimated, and a t test on k − 2 df.
- Asymmetry has several causes besides publication bias: smaller studies done in different populations, chance, poor methods in small trials, and the choice of measure. Report "evidence of small-study effects", never "publication bias was found". The absence of asymmetry does not show the absence of publication bias.
- The funnel plot is drawn for every pool, with its pseudo 95 % limits around the pooled estimate. With k < 10 its title says the studies are too few to judge asymmetry; describe it, do not interpret it.
- Trim-and-fill, fail-safe N and p-curves are not run.

## Reading heterogeneity

| Statistic | Tells | Does not tell |
|---|---|---|
| Q and its p | Whether the observed spread exceeds sampling error | How much the true effects vary; a large p does not show homogeneity, especially with few studies |
| I² | The share of observed variance not due to sampling error | The amount of heterogeneity in outcome units; it rises with study size for the same τ² |
| τ², τ | The variance and SD of the true effects, in the effect's units | Whether the variation matters clinically, which the prediction interval shows |
| Prediction interval | The range of true effects in a new comparable study | The precision of the mean, which the CI gives |

I² labels such as "low" or "high" are conventions, not findings; when used, give the number beside them. With k < 10, I² and τ² are very uncertain: say so.
