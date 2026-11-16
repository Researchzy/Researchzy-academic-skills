# Writing the results

Write `meta-analysis/results.md` and `meta-analysis/methods.md` from `meta-analysis/results.json` only. Copy each number from its field (`pooled.md` shows the same numbers rounded, for orientation). Never recompute, and never take a number from the console, a plot or memory. Then run `check_meta.py --text`.

## Each pooled estimate

State each pooled estimate once, in its own paragraph, with everything below. Elsewhere refer to it in words ("the main estimate") without repeating the number: `check_meta.py` treats any paragraph that prints the estimate beside a bound of its interval, or beside a word such as "pooled", as the place where it is reported.

| Part | From `results.json` | Printed as |
|---|---|---|
| Studies and participants | `extra.meta.k`, `n.participants` | "Six trials (k = 6; 436 participants)" |
| Estimate with direction and units | `estimate` | "mean difference −1.55 kg"; a ratio on its ratio scale: "risk ratio 0.49" |
| Interval | `interval` | "(95% CI −2.27 to −0.82)": "to", not a dash, when a bound can be negative |
| Test | `statistic`, `df`, `p` | "t(5) = −5.46, p = 0.0028" for Hartung–Knapp; "z = …" for Wald |
| Prediction interval | `extra.meta.pi`, or `pi_reason` | "95% prediction interval −2.33 to −0.76 kg"; or "No prediction interval was computed: only two trials." |
| Heterogeneity | `I2`, `tau2`, `tau`, `Q`, `Q_df`, `Q_p` | "τ² = 0.04, I² = 31% (Q = 7.2, df = 5, p = 0.21)" |

`check_meta.py` reads the labels `k =`, `I² =` (or `I^2 =`), `τ² =` (`tau^2 =`), `τ =`, `Q =`, `df =` and `p =`; write them in that form so each number is compared with the right field. I² is a whole percentage, truncated at 0: never print `I2_raw` or `tau2_raw`. Use the same decimals for an estimate and its bounds.

Template:

> {k in words} studies (k = {k}; {participants} participants) reported {outcome} at {timepoint}. {Direction in words}: the pooled {measure} was {estimate} {units} (95% CI {low} to {high}; {statistic}({df}) = {value}, p = {p}). The 95% prediction interval for a new study was {pi low} to {pi high} {units}. τ² = {tau2}, I² = {I2}% (Q = {Q}, df = {Q_df}, p = {Q_p}).

## Other results

- **Sensitivity.** "Leaving out each trial in turn gave estimates from −1.80 to −1.41 kg; without the trial whose values were estimated from medians, the estimate was −1.53 kg (95% CI −2.40 to −0.66)." No p-values: none were recorded.
- **Subgroups with a test.** Both group estimates with their intervals, then "Q between = {Q_between}, df = {df}, p = {p}".
- **Subgroups without a test.** "With fewer than 4 trials per group, the groups were described and not compared."
- **Small-study effects, k < 10.** "Small-study effects were not assessed: with {k} trials, fewer than 10, no asymmetry test was run."
- **Small-study effects, k ≥ 10.** "{Test}: t({df}) = {t}, p = {p}." Add that asymmetry can have causes other than publication bias.
- **Excluded studies.** Double-zero studies left out of a ratio pool are named with the reason.

## Wording

| Result | Write | Never write |
|---|---|---|
| Model | The reason from how the studies differ | "Because I² was high, random effects were used" |
| Large Q p-value | "Q = 4.0, df = 5, p = 0.55; I² = 0%; with six studies heterogeneity is estimated imprecisely" | "There was no heterogeneity", "the studies were homogeneous" |
| PI includes no effect | "In a new setting the effect could be absent or reversed" | "The effect is consistent across settings" |
| Asymmetry test | "Evidence of small-study effects" or its absence, with the caveat | "Publication bias was found" or "ruled out" |
| Subgroup difference not tested | The two estimates, described | "The effect was significant only in…" |
| Subgroup difference | "was larger in trials of …" | Causal language about the characteristic |
| Interval includes no effect | "compatible with no difference and with a reduction of up to …" | "no effect", "no difference" |

## The methods paragraph

Write it in this order, from `plan.md` and `results.json`:

1. Software: Python and package versions from `record.python` and `record.packages`, and that the scripts are available.
2. The effect measure per outcome and the conversions used, naming the rows marked `estimated` and how each conversion works (SD from SE, from a CI with t, from medians).
3. The model and the reason for it from how the studies differ.
4. The τ² estimator ("restricted maximum likelihood (REML)", "Paule–Mandel", "DerSimonian–Laird, truncated at 0") and, if REML fell back, that it did.
5. The interval method ("Hartung–Knapp with the ad hoc floor, so the interval is never narrower than the Wald interval"; the Wald interval as a sensitivity analysis) and the prediction interval on k − 2 df.
6. Heterogeneity statistics reported; subgroups with their reasons and the 4-study rule; the sensitivity analyses.
7. Small-study tests: the test per measure and the 10-study rule.
8. Zero cells: the method chosen and how double-zero studies were handled.
9. What the agent did and what the user checked: which values the agent extracted and converted, which the user verified. Where a fact is not in the files (registration, who extracted), write `[Author input needed: …]`.

`check_meta.py` fails when no text names a pool's τ² estimator and interval method, or its Mantel–Haenszel, Peto or inverse-variance fixed-effect method.

## Fixing the check

| Finding | Do |
|---|---|
| `paragraphs` | Add what the message names to that paragraph, or stop repeating the estimate there |
| `small-study` | Remove the test, or say it was not run and why |
| `methods` | Name the estimator and the interval method, as in step 4 and 5 above |
| `wording` | Give the model's reason from the studies; print truncated I² and τ² |
| `meta` | Run `meta_pool.py` again; never edit `results.json` |
| text `mismatch` | Copy the recorded value; a printed minus must match the recorded sign |
| `hashes` is `drift` | `effects.csv` or `extraction.csv` changed after pooling: run both scripts again |
