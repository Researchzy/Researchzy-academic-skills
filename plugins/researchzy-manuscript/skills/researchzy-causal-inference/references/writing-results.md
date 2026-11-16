# Writing up a causal estimate

Write `causal/results.md` and `causal/methods.md` from `causal/results.json` only: copy each number from its field, never from the console or from memory. Then run `check_causal.py --text`.

## The estimand, with the units it is about

| Design | Write |
|---|---|
| DiD, staggered or 2×2 | "the average effect of adoption on adopting counties over the years after adoption (ATT)", with the aggregation from `plan.md` |
| Event study | "the effect k years after adoption, for the cohorts observed k years after" |
| IV | "the effect for compliers: units whose treatment follows the instrument" |
| RD | "the effect at the cutoff for units at the cutoff" (fuzzy: for compliers at the cutoff) |
| Panel FE | "the effect of a within-unit change in the treatment, under strict exogeneity" |
| Synthetic control | "the effect on [unit] in each year after adoption" |
| Weighting | "the effect on the treated (ATT)", or "in the units with scores in [0.1, 0.9]" after trimming |

## The identifying assumption, in one sentence

- DiD: "Without the policy, employment in adopting counties would have followed the same path as in [never-treated / not-yet-treated] counties, and no county changed course before adopting."
- IV: "The lottery changed attendance, affected scores only through attendance, and made no pupil less likely to attend."
- RD: "Pupils just below and just above the cutoff would have had the same outcomes without admission, and could not choose their side."
- Panel FE: "Within a firm, changes in exposure are unrelated to other changes that affect sales."
- Synthetic control: "A weighted average of the donors reproduces the path [unit] would have had, and no donor was affected by the policy."
- Weighting: "Given [covariates], treatment was as good as random, and every unit could have received either."

Why it is plausible comes from the institutional facts. When those are not in the files, write `[Author input needed: how the adoption dates were set]`.

## What every estimate carries

The estimate with its units and its interval and level; the estimator that ran and the control group; N (units and unit-periods); G and treated G, with the cluster level and its basis; the mean outcome of the untreated, for scale (record it in `descriptives`). Add for IV the first-stage F and the Anderson–Rubin set; for RD the bandwidth and effective n on each side; for synthetic control J and the placebo p; for weighting the units dropped by trimming and the largest weight's share. The methods give the bootstrap draws or permutations and the seed.

## Verbs and evidence

| Evidence in `results.json` | Allowed | Not allowed |
|---|---|---|
| Route `matched`, every required diagnostic `pass` | "Adoption raised employment by 4.6 jobs per 1,000 (95% CI 4.1 to 5.1)", with the assumption named | "proved", "confirmed", "definitively" |
| Breakdown M below 1 | "The estimate suggests a rise of …; a violation of parallel trends as large as the largest pre-period one would overturn it, so the result is fragile" | A plain causal claim |
| A required diagnostic `fail` or `not_checked` | "The estimate was …", "employment was higher by … in adopting counties", followed by what failed | "caused", "led to", "raised", "reduced", "increased" |
| Route not `matched` | Descriptive comparisons only, labelled as such | An effect, in any wording |

`check_causal.py` flags two word lists. It flags these anywhere when the route or a headline's required diagnostics do not support them: cause(d), led to, leads to, result(ed) in, drove, driven by, induce(d). It flags these in a sentence that prints a result's estimate or interval bound: increase(d), decrease(d), raise(d), reduce(d), lower(ed), improve(d), boost(ed). Other phrasings escape the script, but the table still binds them.

Pre-trends: "Pre-period estimates were small (largest |t| = 1.9 against a critical value of 2.6); the test has little power, so it is weak evidence for parallel trends." Never "parallel trends hold" or "were confirmed". For an interval that includes zero: "the data are compatible with effects from −0.4 to 2.6", never "no effect".

## The robustness table

Start from `causal/robustness.md`: the headline first, one row per specification run, a changed n flagged and explained in the note, and dropped specifications listed with their reason (in the appendix when long). Read it plainly: a stable sign and size support the headline, and a result that lives in one specification has to be described as such. When only the headline excludes zero, the text says so with the count ("one of 5 specifications"); the check fails until it does. No significance stars.

## The methods paragraph

In this order, one or two sentences each, from `plan.md` and `results.json`:

1. Design and estimand, with the units it is about.
2. The identifying assumption, and why it is plausible here.
3. The estimator, control group, base period and aggregation; the benchmark reported beside it.
4. Inference: cluster level and basis (Abadie, Athey, Imbens and Wooldridge 2023), G and treated G; bootstrap draws or permutations and the seed.
5. Diagnostics and what they showed, failures included; the sensitivity analysis with its label ("simplified version, not the Rambachan–Roth confidence set").
6. How many specifications were run, and where they are reported.
7. Software: Python and package versions from `record`; which steps an AI model carried out (probing the data, writing the analysis code, estimating, drafting the text).

## Results sentences

Fill every bracket from `results.json`. Where the verbs table forbids a causal verb, use the descriptive form.

- DiD: "Across the [n] treated county-years, the average effect on the treated was [estimate] [units] (95% CI [low] to [high]; Callaway–Sant'Anna with never-treated controls; G = [G] counties, [G1] treated). Static TWFE gives [b] ([low] to [high])."
- IV: "Among compliers, [outcome] was [estimate] [units] higher with [treatment] (Anderson–Rubin 95% set [low] to [high]; first-stage F = [F])."
- RD: "At the cutoff, [outcome] jumps by [estimate] (robust bias-corrected 95% CI [low] to [high]; bandwidth [h], [nL] and [nR] observations)."
- Synthetic control: "After adoption, [unit]'s [outcome] was on average [gap] [units] below its synthetic control (placebo p = [p] with [J] donors)."
- Weighting: "Among the [n] units with scores in [0.1, 0.9] ([k] dropped), the average effect on the treated was [estimate] (95% CI [low] to [high])."
