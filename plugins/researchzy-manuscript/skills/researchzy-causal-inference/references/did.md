# Difference-in-differences and event studies

Read `causal/<data>.design.json` first: `facts.timing`, `facts.cohorts`, `facts.never_treated`, `facts.periods_without_untreated` and `route` decide the rows below.

## Which design

| Probe | `design` | Headline | Beside it |
|---|---|---|---|
| One adoption date, never-treated units | `did_2x2` | `twfe` with the adoption dummy (equal to interaction OLS without covariates) or `callaway_santanna` | — |
| Two or more adoption dates | `staggered_did` | `callaway_santanna` | `twfe` as a benchmark, `headline=False` |
| Effects by time since adoption | `event_study` | The event-time aggregation of `callaway_santanna`; with one adoption date also `twfe_event_study` | — |

`causal_tools` estimates without covariates (unconditional parallel trends). When parallel trends is plausible only given covariates, say that the conditional design needs another estimator (for example a doubly robust Callaway–Sant'Anna in R `did` or Stata `csdid`; check the installed version's options) and do not add the covariates to TWFE: that recovers the ATT only under further restrictions, such as effects that do not vary with the covariates (Roth, Sant'Anna, Bilinski and Poe 2023).

## The estimand

`ct.callaway_santanna` (Callaway and Sant'Anna 2021) returns ATT(g, t) for each cohort g and period t: the change from g − 1 to t in cohort g minus the change in the controls. The base g − 1 is the same for every t, so pre-period cells are long differences against the year before adoption and event time −1 is zero by construction. Choose the summary in `plan.md` before any estimate:

| Key | Averages over | Says |
|---|---|---|
| `overall` | Treated unit-periods, each the same | "The average effect over treated county-years" (cohorts with more post years weigh more) |
| `group["overall"]` | Cohorts weighted by size: each treated unit the same | "The average effect on a treated county" |
| `event`, `event_average` | Event times; the average over e ≥ 0 | How the effect evolves with exposure |

Each unit weighs the same. A population-weighted effect is another estimand, not a robustness check.

Control group, fixed before results: `never_treated` assumes the never-treated would have trended like the adopters. `not_yet_treated` adds later adopters before they adopt; it assumes they did not react in advance and that their timing did not follow their own outcomes. Run the other as a robustness row. Without never-treated units only `not_yet_treated` works, and cells after the last adoption are not identified (`cells_without_controls`).

## TWFE beside it

With staggered adoption and effects that change over time, TWFE also compares late adopters with units treated earlier, so some group-time effects enter with negative weights (de Chaisemartin and D'Haultfœuille 2020; Goodman-Bacon 2021); dynamic TWFE leads are contaminated the same way (Sun and Abraham 2021). Report `ct.twfe(..., regressors=["post"])` beside the headline. Agreement is reassuring; disagreement means effects differ across cohorts or time, and the robust estimate stands. `ct.simulate_staggered` builds a panel with a known ATT: before the real data, run the analysis script on it once and see the headline recover the truth while TWFE does not.

## Event study

- Record it as one result: `estimate` from `cs["event_average"]`, `extra={"path": cs["event"]}`, with the diagnostics `pretrend_test` and `sensitivity`. Every event-time number printed in the text is then found in `extra`.
- With one adoption date a TWFE event study is fine: `out, names = ct.event_dummies(panel, time="year", cohort="cohort", window=(-5, 4))` bins the ends, omits −1 and asserts that no treated row is left without a dummy; then `ct.twfe(out, ..., regressors=names)` and `ct.event_path(...)` for the plot.
- Under staggered adoption use the event-time aggregation of Callaway–Sant'Anna, never dynamic TWFE. Without never-treated units a dynamic TWFE needs a second omitted period (Borusyak, Jaravel and Spiess 2024); avoid it.
- The ends of the window rest on fewer cohorts (`cohorts` in each row of `cs["event"]`), so an apparent trend there can be a change of composition. `balance_e=E` keeps only cohorts observed up to e = E.
- Plot separate points with whiskers, the omitted period at zero, the adoption marked (to `researchzy-figures`).

## Pre-trends

- A test that passes is weak evidence: it has little power against the trends that bias the estimate, and reporting only designs that pass distorts the estimates further (Roth 2022). Never write that parallel trends holds.
- The test: `cs["pretrend"]` asks whether any pre-period event-time estimate leaves the sup-t band (the level quantile of the largest |t| over the bootstrap draws; Montiel Olea and Plagborg-Møller 2019); `cs["pretrend_by_cohort"]` does the same per cohort. A joint F over many leads with clustered errors can reject too often when clusters are few.
- Never move the base period or drop leads until the test passes.
- A cohort that fails is reported separately or dropped, labelled as decided after the event study, and named in the text (`check_causal.py` looks for its name). Record it in the diagnostic: `{"status": "fail", "cohorts": [2018], ...}`.

## Sensitivity

`ct.relative_magnitude(estimate, se, pre)` bounds the post-treatment bias by M times the largest pre-period deviation D (the pre-period event-time estimates against the base). It returns the interval for M = 0.5, 1 and 2 and the breakdown M, the smallest M at which the interval reaches zero, under the label "simplified version, not the Rambachan–Roth confidence set". Print that label wherever the result appears. Record `sensitivity` as pass when the breakdown M is 1 or more, fail when below 1 (then write that the result is fragile; for a 2×2, that the conclusion is directional), not_checked with the reason when there is no pre-period. The confidence sets of Rambachan and Roth (2023) need an optional package (`honestdid`), installed only with the user's consent; record its result as a separate diagnostic.

## Clusters

Cluster where treatment was assigned: a county policy by county, a state law by state, whatever level the panel rows are (Abadie, Athey, Imbens and Wooldridge 2023); serial correlation within units makes unclustered errors far too small (Bertrand, Duflo and Mullainathan 2004). `B` bootstrap draws resample whole clusters; pass `cluster=` when it is coarser than the unit. Report G and treated G. Guides give rules of thumb of 30 to 50 clusters; MacKinnon, Nielsen and Webb (2023) show that no count is safe when clusters are unbalanced or few are treated, and flag G ≤ 12 and 6 or fewer treated or untreated clusters. Our choice: no count passes by itself; with 6 or fewer treated clusters add `ct.ri_pvalue`, permuting adoption across clusters within strata, beside the bootstrap interval. The wild cluster bootstrap (Cameron, Gelbach and Miller 2008) is not in `causal_tools`.

## Recording the diagnostics

| Key | `pass` when | Record |
|---|---|---|
| `cohorts` | Cohort sizes and never-treated count are known | `value`: `cs["cohorts"]` |
| `untreated_each_period` | The probe's `periods_without_untreated` is empty | Otherwise `fail` and the periods |
| `event_study`, `pretrend_test` | The uniform pre-trend test does not reject | `value`: `cs["pretrend"]`; on `fail`, `cohorts` from `pretrend_by_cohort` |
| `sensitivity` | Breakdown M ≥ 1 | `value`: the `relative_magnitude` result |
| `pretrend_plot` (2×2) | The pre-period means of both groups are drawn and look as the test says | `not_checked` with the reason if not drawn |

## Commands elsewhere (listed, not run)

R: `did::att_gt()` with `control_group` and `base_period = "universal"`, then `aggte()`; Stata: `csdid`. Names only: options and defaults change between versions, so read the installed help before relying on one.
