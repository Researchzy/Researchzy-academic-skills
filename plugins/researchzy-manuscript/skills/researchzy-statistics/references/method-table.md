# Choosing the method from the design

Find the row the probe names in `route.row` (`statistics/<data>.design.json`) and read the column it names in `route.column`. The method follows from the question and the design. Never from a normality or variance pre-test: choosing the test after looking at a pre-test changes the error rate of the test you finally report. Read `route.first` before anything in this table: replicates and clusters are dealt with first.

`s` is `scipy.stats`, `sm` is `statsmodels.api`, `smf` is `statsmodels.formula.api`. Every test is recorded through `rz.record` with an estimate in raw units, its interval, and an effect size with its interval or the reason it has none. The summary column says what one row of `n` is: always the unit, never a row of the file.

## The table

| Row | Independent units | Same unit measured again | Effect size and its interval |
|---|---|---|---|
| `continuous / one group` | One-sample t: `s.ttest_1samp(x, mu)`; `.confidence_interval()` | n/a | Mean difference from `mu` with the t interval; d with a bootstrap interval |
| `continuous / 2 groups` | Welch t by default: `s.ttest_ind(a, b, equal_var=False)`. Mann-Whitney `s.mannwhitneyu(a, b)` only when the question is about ranks or order | Paired t on the differences: `s.ttest_rel(x, y)`. Signed-rank `s.wilcoxon(x, y)` when the question is about the median difference | Difference in means and the test's `.confidence_interval()`; Hedges' g (independent) or d_z (paired) with a BCa bootstrap interval. For ranks: rank-biserial r = 2U/(n1·n2) − 1, bootstrap interval |
| `continuous / 3+ groups` | Welch ANOVA: `statsmodels.stats.oneway.anova_oneway(groups, use_var="unequal")`; then pairwise Welch t tests with Holm. All pairs with equal SDs: `s.tukey_hsd(*groups)`; each against a control: `s.dunnett(*groups, control=c)`. Ranks: `s.kruskal` | Mixed model (default; keeps units with a missing occasion): `smf.mixedlm("y ~ C(condition)", d, groups=d["unit"]).fit()`. Complete units only and a rank question: `s.friedmanchisquare` | The pairwise differences with their intervals (Tukey and Dunnett give them with `.confidence_interval()`); one number only if asked: eta squared with a bootstrap interval |
| `continuous / numeric predictor` | Slope from `smf.ols("y ~ x", d).fit(cov_type="HC3")`, or Pearson `s.pearsonr(x, y)` for a linear association, Spearman `s.spearmanr` for a monotone one: chosen by the question | Mixed model with a random intercept per unit | Slope in outcome units per unit of x with `.conf_int()`; r with `.confidence_interval()` (Pearson) or a bootstrap interval (Spearman) |
| `binary / one group` | `s.binomtest(k, n, p0)` | n/a | Proportion with `.proportion_ci(method="wilson")` |
| `binary / 2 groups` | `s.chi2_contingency(table, correction=False)`; `s.fisher_exact(table)` when the probe rules out chi-square | McNemar on the discordant pairs: `statsmodels.stats.contingency_tables.mcnemar(table, exact=True)` | Risk difference with `confint_proportions_2indep(..., method="newcomb")`; risk ratio (`s.contingency.relative_risk`) or odds ratio (`s.contingency.odds_ratio(table).confidence_interval()`). Paired: the discordant-pair odds ratio b/c, interval from `s.binomtest(b, b + c).proportion_ci()` turned into p/(1 − p) |
| `binary / 3+ groups` | `s.chi2_contingency`; ordered groups: `Table(table).test_ordinal_association()` | Cochran's Q: `statsmodels.stats.contingency_tables.cochrans_q(x)` | Each group's proportion with its Wilson interval; risk differences against a reference group |
| `categorical / 2+ groups` | `s.chi2_contingency`; sparse: `method=s.PermutationMethod(rng=rng)` | Symmetry (McNemar-Bowker): `SquareTable(table).symmetry()` | Proportions per category with intervals; Cramér's V (`s.contingency.association`) with a bootstrap interval |
| `ordinal / 2 groups` | `s.mannwhitneyu` | `s.wilcoxon` | Rank-biserial r with a bootstrap interval; medians per group as description |
| `ordinal / 3+ groups` | `s.kruskal`, or a proportional-odds model `statsmodels.miscmodels.ordinal_model.OrderedModel` | `s.friedmanchisquare` on complete units | Pairwise rank-biserial r; odds ratios from the model with `.conf_int()` |
| `count / 2+ groups` | Poisson GLM `smf.glm("y ~ g", d, family=sm.families.Poisson(), offset=np.log(d.time))`; when the variance exceeds the mean, `smf.negativebinomial` | Mixed model or GEE: `smf.gee(..., groups=d["unit"], family=sm.families.Poisson())` | Rate ratio = exp(coefficient) with exp(`.conf_int()`), and the rates per group |
| `model` | Covariates, or two factors such as group and time: the regression of the outcome type (OLS with HC3, logistic `smf.logit`, Poisson or negative binomial, `OrderedModel`) | Group and time on the same units: `smf.mixedlm("y ~ group * time", d, groups=d["unit"]).fit()`; binary or count outcome: `smf.gee` with an exchangeable working correlation | Coefficients in outcome units (or exp for ratios) with `.conf_int()`; report the interaction first when it is the question |
| `describe only` | No test fits: give counts, proportions and intervals | | |
| agreement (not from the probe) | Bland-Altman: mean difference and limits of agreement from the paired differences; categories: `statsmodels.stats.inter_rater.cohens_kappa` | | Limits with their own intervals (bootstrap); kappa with its reported interval |

Notes on the cells:

- Welch is the default for two means and for several means. Student's t (`equal_var=True`) or Tukey assume equal SDs; use them only when the plan gives a reason, and say so in `notes`.
- Repeated-measures ANOVA (`statsmodels.stats.anova.AnovaRM`) needs every unit at every occasion and gives no sphericity correction; the mixed model is the default.
- A bootstrap resamples units, never rows: `s.bootstrap((a, b), statistic, method="BCa", n_resamples=9999, rng=rng)` resamples each group separately; for paired data resample the differences. Clustered data: resample clusters. Older scipy calls `rng` `random_state`.
- `s.ttest_ind` without `equal_var` runs Student's test; `check_results.py --script` reports it.
- A mixed model that fails to converge or warns of a singular fit is recorded with `kept=False` and the warning as the reason; then try a random intercept only, and say so.
- Logistic models: before fitting, look for a predictor level where every outcome is the same (complete separation). The odds ratio is then infinite: describe the table instead, or ask a statistician.

## Replicates and clusters

| The probe says | Do |
|---|---|
| `replicates` | Aggregate to one value per unit and condition (the mean, or the median for skewed replicates; state which in `notes`), then use the row above with n = units. Or fit a mixed model with a random intercept per unit on the rows. Never a test on the rows |
| `clustered`, group constant within cluster | The cluster is the unit that was assigned: n is the number of clusters. Use one summary per cluster, or a mixed model or GEE with the cluster as the group. With fewer than about 10 clusters per arm, say that the interval is unreliable |
| `clustered`, group varies within cluster | Mixed model with a random intercept per cluster, or OLS or GLM with `cov_type="cluster", cov_kwds={"groups": d["cluster"]}` |
| `paired` or `repeated` with incomplete units | Mixed model on every observation, or the complete-unit test with the left-out units counted and reported |

## What this skill does not attempt

Bayesian models, survival or time-to-event analysis, survey weights, prediction-model development or validation, equivalence and non-inferiority margins, diagnostic-accuracy studies, and simulation studies. Meta-analysis belongs to `researchzy-meta-analysis`, and causal identification (instruments, difference-in-differences, regression discontinuity) and propensity scores to `researchzy-causal-inference`, when installed. When the question needs one of the others, say so to the user and stop: name the part that needs a statistician or a dedicated tool, and do not improvise an approximation. Descriptive statistics for the same data are still fine.
