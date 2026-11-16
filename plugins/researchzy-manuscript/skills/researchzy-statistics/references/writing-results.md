# Writing the results

Write `statistics/results.md` (Results sentences) and `statistics/methods.md` (the Statistical analysis paragraph) from `statistics/results.json` only. Open the file and copy each number from its field. Do not recompute, and do not take a number from the console or from memory. Then run `check_results.py --text`.

## Numbers

| Quantity | Print |
|---|---|
| Estimate, interval, effect size | The same decimals for an estimate and its interval; two or three significant digits are usually enough |
| Interval | "95% CI 1.2 to 3.4", with the level from `interval.level`; write "to", not a dash, when a bound can be negative |
| p | Exact, two significant digits (p = 0.031, p = 0.0042); below 0.001 write p < 0.001. Never p = 0.000, never "p = n.s." |
| Adjusted p | "Holm-adjusted p = 0.036", from `p_adjusted` |
| Test statistic | With its degrees of freedom: t(10) = −11.6; F(2, 19.9) = 1.22; χ²(1) = 4.1 |
| n | The units from `n`, with what a unit is: "11 pairs", "4 mice per genotype" |
| Software | Python, package and `rz_results` versions from `record.python` and `record.packages` |

## Results sentences

One sentence per result, in this order: what was compared, the direction, the estimate with its units and interval, then the test, then the effect size. Templates (fill every `{}` from `results.json`):

- Two groups: "{Outcome} was {higher/lower} in {group A} than in {group B} (difference in means {estimate} {units}, 95% CI {low} to {high}; Welch t({df}) = {t}, p = {p}; Hedges' g = {g}, 95% CI {low} to {high}; n = {nA} and {nB} {units of analysis})."
- Paired: "{Outcome} was {lower} under {condition A} than under {condition B} (mean within-{unit} difference {estimate} {units}, 95% CI {low} to {high}; paired t({df}) = {t}, p = {p}; d_z = {dz}; {n} {units} with both measurements, {k} left out because {reason})."
- Several groups: first the omnibus test, then each pair with its difference, interval and adjusted p.
- Proportions: "{k1}/{n1} ({%}) versus {k2}/{n2} ({%}); risk difference {rd} (95% CI {low} to {high})."
- Model: the coefficient in outcome units (or the ratio) with its interval and what it is adjusted for.

Group descriptives (mean and SD, or median and quartiles) come from `descriptives`.

## Wording

| Result | Allowed | Not allowed |
|---|---|---|
| p above alpha | "The difference was 1.1 points (95% CI −0.4 to 2.6); the data are compatible with no difference and with a difference of up to 2.6 points." | "There was no difference", "the groups were equivalent", "no effect", "a trend towards significance", "marginally significant" |
| p below alpha | "{Group} had higher {outcome} (difference …)" with the interval; the size judged against what matters in the field | "Proved", "confirmed", "highly significant", stars, a judgement from p alone |
| Exploratory result | "In an exploratory analysis, …; this was not planned and needs confirmation." | Any wording that presents it as planned or confirmatory |
| Secondary outcome | Estimate and interval with the label "secondary" | A conclusion drawn from it alone |
| Observational design | "was associated with", "was higher in" | "caused", "led to", "increased" (as a causal verb) |
| Small n | State n and the interval width; say that the estimate is imprecise | "Underpowered" as an excuse, observed power |

A conclusion of equivalence needs an equivalence test with a margin fixed in advance, which this skill does not run.

## The Statistical analysis paragraph

Write it in this order, one or two sentences each, all from `plan.md` and `results.json`:

1. Software: Python and the package versions in `record`, and that the analysis script is available (hand the statement to `researchzy-data-availability` when installed).
2. Summary convention: mean (SD) or median (quartiles), and what intervals are (95% confidence intervals).
3. Unit and n: what one unit is, how replicates were combined, how clusters were handled.
4. Tests and models per question, with Welch, the paired or mixed structure, and the effect sizes and how their intervals were computed (BCa bootstrap with the number of resamples and the seed from `record.settings` and `record.seed`).
5. Multiplicity: each family, the number of tests and the correction.
6. Missing data and exclusions: the decision from the plan and the numbers excluded.
7. Alpha and sidedness, and which analyses were exploratory.

Where a fact is not in the files (randomisation, blinding, a pre-registration), write `[Author input needed: …]`; never fill it in.
