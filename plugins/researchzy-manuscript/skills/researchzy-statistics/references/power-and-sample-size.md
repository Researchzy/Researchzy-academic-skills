# Sample size and power

`power.py` answers three questions for five designs: how many units (default), what power a given n has (`--n`), and what effect a given n can detect (`--n --solve effect`, a sensitivity analysis). It always prints a table across a range of effects, and writes a justification paragraph with five elements: the outcome and effect with its source; alpha and power; the test; the n with inflation; the software and version.

## Where the effect size comes from, in order of preference

| `--effect-source` | What it is | Notes |
|---|---|---|
| `smallest-effect-of-interest` | The smallest difference that would change a decision or matter to patients, users or the field, set by the team before seeing data | The best basis. `--source-note` says who set it and why ("smallest change in pain score patients notice, per the steering group") |
| `prior-study` | An SD, a baseline proportion or an effect read from a published study of a similar population and outcome | `--source-note` must hold the DOI and the place in the paper ("doi:10.xxxx/yyyy, Table 2, control arm at 12 weeks"). Published effects tend to be inflated; prefer to take the SD or baseline from the paper and the effect from the smallest effect of interest |
| `pilot` | An estimate from the user's own pilot data | Use the pilot's SD more than its effect: a pilot effect is very imprecise. Look at the rows of the table below 1.0 |
| `convention` | A conventional standardised value (for example d = 0.5) | Last resort. Printed everywhere as a convention, not an estimate; pass `--sd 1` and say that the effect is in SD units |
| `observed` | The effect a finished study found | Refused. Power computed from it is a function of the p-value. For a finished study report the effect's interval, or run `--solve effect` at the achieved n and call it a sensitivity analysis |

Never choose the effect to make the achievable n come out: that is a sensitivity analysis (`--solve effect`), and its paragraph says so. Ask the user for the source of the effect and of the SD before computing; if they have none, say that the calculation would rest on a convention and ask whether that is acceptable.

## Commands

```sh
python3 "$SKILL_DIR/scripts/power.py" two-means --diff 5 --sd 10 --units mmHg --unit patients \
  --outcome "systolic pressure at 12 weeks" --effect-source smallest-effect-of-interest \
  --source-note "5 mmHg agreed by the trial team" --attrition 0.1
python3 "$SKILL_DIR/scripts/power.py" paired --diff 3 --sd-diff 6 ...          # or --sd 6 --corr 0.5
python3 "$SKILL_DIR/scripts/power.py" two-proportions --p1 0.30 --p2 0.15 ...
python3 "$SKILL_DIR/scripts/power.py" correlation --r 0.3 ...
python3 "$SKILL_DIR/scripts/power.py" anova --means 10,12,15 --sd 6 ...
python3 "$SKILL_DIR/scripts/power.py" two-means --sd 10 --n 40 --solve effect ...
```

| Option | Use |
|---|---|
| `--sd1 --sd2`, `--ratio` | Unequal SDs (Welch) and unequal allocation; n is for group 1, group 2 gets ratio × n |
| `--alpha` | The alpha of each test after any correction: for a family of three with Bonferroni, 0.05 / 3 |
| `--alternative one-sided` | Only when the plan states one direction in advance |
| `--attrition 0.15` | Inflates n to n / (1 − 0.15) |
| `--icc 0.05 --cluster-size 20` | Inflates n by the design effect 1 + (m − 1) × ICC; the ICC needs a source too. Equal clusters only: with unequal or few clusters, simulate |
| `--range 0.5,0.8,1,1.2` | The multiples of the effect in the table |
| `--name` | Another output name, so that several calculations sit side by side |

Outputs: `statistics/<name>.json` and `<name>.md` with the table, the justification and the warnings. Give the user the table, not just the n: it shows how fast the n grows if the true effect is smaller.

## What the calculation covers

| Design | Test the power is for | Checked against |
|---|---|---|
| `two-means` | Welch t test (noncentral t, Welch-Satterthwaite df at the planned SDs and sizes) | statsmodels with equal SDs; a simulation of `ttest_ind(equal_var=False)` otherwise |
| `paired` | Paired t test on the differences | statsmodels |
| `two-proportions` | z test (chi-square without continuity correction), normal approximation | statsmodels |
| `correlation` | Test of Pearson's r through Fisher's z | A simulation of `pearsonr` |
| `anova` | One-way F test, equal groups and SDs | statsmodels |

For anything else (mixed models, repeated measures with several occasions, logistic or count models, clusters of unequal size, survival), write a seeded simulation script that generates data under the planned effect, runs the planned analysis, and counts rejections; check that it rejects at about alpha when the effect is zero; report the power with its Monte Carlo standard error. If that is beyond the user's needs, say a statistician should do it.

## What connecting Researchzy adds

With the `researchzy` plugin connected (it needs a Researchzy account), the agent can look for the prior study the effect or SD comes from:

1. Search with `search_papers`: 2 to 4 short keyword queries for the outcome, population and design; the index matches words in titles and abstracts only.
2. Pick studies with the same outcome measure and a similar population; get the full text with `get_pdf_download` (or `researchzy-download`, plugin `researchzy-reading`, when installed).
3. Read the SD, baseline proportion, ICC or effect from the full text: a table, a figure legend or the results text. Never from the abstract shown in the search result, and never from memory.
4. Pass the DOI and the place to `--source-note`, and tell the user which paper and value were used so they can confirm it.

Without Researchzy, ask the user for the paper or the value with its source. A value with no source goes in as `[Author input needed: …]`, not as a guess.
