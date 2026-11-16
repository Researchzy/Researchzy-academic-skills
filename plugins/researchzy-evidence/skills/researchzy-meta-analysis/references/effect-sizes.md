# The extraction table and the effect sizes

`effect_sizes.py` reads `meta-analysis/extraction.csv` and writes `effects.csv` (one row per study and comparison in each pool) and `effects.md`. A pool is one outcome at one timepoint. `researchzy-systematic-review` (plugin `researchzy-evidence`, when installed) writes its extraction table in this format.

## Columns

One row per arm of a study; one row per study for `ratio_ci`, `r` and `yi_se`.

| Column | Holds |
|---|---|
| `study` | One label per study. Two reports of one trial get the same label, and only one row per arm |
| `outcome`, `timepoint` | Together they name the pool. Spell them identically in every row |
| `arm` | `control` for the comparator; any other name for an intervention arm. Left empty on study-level rows |
| `n` | Participants analysed in this arm (study-level rows: in the study) |
| `design` | `parallel` (default), `cluster` or `crossover` |
| `reported_as` | What the row holds (next table) |
| `value`, `spread`, `low`, `high` | The numbers as printed in the source |
| `ci_level` | 95 or 0.95; empty means 95 % |
| `events` | Number of participants with the event |
| `cluster_size`, `icc`, `icc_source` | Cluster trials: mean cluster size, intracluster correlation, where the ICC comes from |
| `corr`, `corr_source` | Crossover trials: within-person correlation between the two conditions, and its source |
| `units` | The outcome's unit (kg, mmHg). Required for an MD pool, the same in every row |
| `reverse` | `yes` when the scale runs the other way (higher is better here, lower elsewhere): the mean or effect changes sign |
| `locator`, `quote` | Page, table or figure, and the words copied from the source |
| `notes` | Anything inferred, for example "Table 2 footnote: values are mean (SE)" |

Any other column is a study characteristic (dose, region, risk of bias). It is copied into `effects.csv`, where `meta_pool.py --subgroup` can use it.

## What a row holds

| `reported_as` | Needs | Becomes |
|---|---|---|
| `mean_sd` | value, spread = SD | mean, SD |
| `mean_se` | value, spread = SE | SD = SE × √n |
| `mean_ci` | value, low, high | SD = √n × (high − low) / (2 t), t on n − 1 df for the CI level |
| `median_iqr` | value = median, low = Q1, high = Q3 | mean = (Q1 + m + Q3)/3; SD = (Q3 − Q1) / (2 Φ⁻¹((0.75n − 0.125)/(n + 0.25))); marked `estimated` |
| `median_range` | value = median, low = minimum, high = maximum | mean = (a + 2m + b)/4; SD = (b − a) / (2 Φ⁻¹((n − 0.375)/(n + 0.25))); marked `estimated` |
| `change_sd`, `change_se`, `change_ci`, `change_median_iqr`, `change_median_range` | as above | the same, for change from baseline |
| `events` | events | the arm's 2×2 counts |
| `ratio_ci` | value = ratio, low, high | log ratio; SE = (ln high − ln low) / (2 z) |
| `r` | value = correlation | Fisher z = atanh r, variance 1/(n − 3) |
| `yi_se` | value, spread = its SE | used as given: the natural log for a ratio, Hedges' g for an SMD, the paired MD for a crossover |

The median formulas are those of Wan and colleagues (2014). They assume a roughly symmetric distribution, which is why every such row is `estimated` and `meta_pool.py` repeats each pool without them.

## Measures

| `--measure` | Effect, treatment against control | Variance |
|---|---|---|
| `MD` | m₁ − m₂ | SD₁²/n₁ + SD₂²/n₂ (each group's own SD, not a pooled SD) |
| `SMD` | Hedges' g = J × (m₁ − m₂) / S_pooled, J exact: Γ(df/2) / (√(df/2) Γ((df − 1)/2)), df = n₁ + n₂ − 2 | N/(n₁n₂) + g²/(2(N − 3.94)) |
| `OR` | ln(a d / (b c)) | 1/a + 1/b + 1/c + 1/d |
| `RR` | ln((a/n₁) / (c/n₂)) | 1/a − 1/n₁ + 1/c − 1/n₂ |
| `RD` | a/n₁ − c/n₂ | p₁(1 − p₁)/n₁ + p₂(1 − p₂)/n₂ |
| `HR` | ln HR from `ratio_ci` or `yi_se` | from the CI, or the SE given |
| `Z` | atanh r | 1/(n − 3) |
| `GENERIC` | `yi_se` rows as given | SE² |

a and c are events, b and d non-events, in the treatment and control arms. Give one measure for every outcome (`--measure MD`) or per outcome (`--measure weight=MD --measure psqi=SMD`).

## Designs and arms

- **Cluster trials.** Rows are deflated by the design effect 1 + (m − 1) × ICC: n and events are divided by it, the variance of a study-level estimate multiplied by it. The ICC needs a source: the trial's own report, another trial of the same outcome and setting, or a published database. Without `cluster_size`, `icc` and `icc_source` the row is refused. A study-level estimate from an analysis that already accounted for clustering takes `icc_source` = `adjusted`, with the place in `locator`.
- **Crossover trials.** Prefer the paired analysis the paper reports, entered as `yi_se`. With only per-condition means and SDs, both rows need the same `n` and a `corr` with its `corr_source`: the MD variance is (SD₁² + SD₂² − 2 r SD₁ SD₂)/n; g uses the average within-condition SD and the variance (1/n + g²/(2n)) × 2(1 − r). Binary crossover outcomes need the paired analysis.
- **Several arms against one control.** A study enters a pool once. Choose per study: `--combine "Lee 2021"` merges the intervention arms (means and SDs by the standard formula for combining groups; events and n add up), `--split "Lee 2021"` divides the control group evenly among the comparisons, `--drop "Lee 2021=low dose"` leaves an arm out. Combining is the usual first choice; state the choice and its reason in `plan.md`.
- **Change and final values.** An MD pool may mix them (the summary notes it; say so in the methods). An SMD pool may not, because the two SDs measure different things: pool them separately.

## Zero cells and rare events

A binary pool stops when a study has a zero cell or the pooled event rate is below 1 % (a convention), until `--sparse` names the method from the plan: `mh`, `peto` (OR only), `cc` or `iv` (only when no cell is zero). [Pooling](pooling.md) says how to choose. Nothing is added to a zero cell unless `cc` is chosen; with `mh` and `peto`, 0.5 is added only to the study's own estimate on the forest plot and in Q. Studies with no events, or only events, in both arms carry no information on a ratio: they leave OR and RR pools and are counted in `effects.md` and in the result.

## Warnings to settle in the source

| Warning | Means | Do |
|---|---|---|
| SD equals the CI half-width / t | The "SD" is probably an SE | Read the table footnote. If it is an SE, change `reported_as` to `mean_se` and say so in `notes` |
| SD far below the other studies' median, SD × √n near it | Same suspicion, from the other studies | As above; if the SD is real, note what was checked |
| Ratio CI asymmetric on the log scale | A bound may be mistyped | Compare with the source; an exact or profile CI can be asymmetric |
| No locator | The value cannot be traced | Add the page or table |

When the user's own table has another layout, convert it into this format first and write every inference (which statistic a column holds, which group is the control) into `notes`.
