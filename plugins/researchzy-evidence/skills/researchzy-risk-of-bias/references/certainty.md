# Certainty of the evidence and the summary of findings

GRADE rates the body of evidence for one outcome, not single studies. This file describes the approach in general terms; where the review's protocol or the GRADE guidance the user follows (read in this session) says more, that decides.

## Per outcome

1. **Studies and participants.** The studies in the pooled analysis of the outcome and their total number of participants, from `meta-analysis/results.json` or from the user.
2. **Starting level.** Randomised trials start high, observational studies low. Randomised evidence always starts high. Observational evidence may start high only with a `start_reason` the user confirms, taken from the guidance the review follows.
3. **Five domains**, each with a decision:

| Decision | Levels | Needs |
|---|---|---|
| `none` | 0 | A reason is welcome, not required |
| `not_assessable` | 0 | A reason, for example too few studies to judge publication bias. Kept apart from "no concern" |
| `serious` | −1 | A reason and the studies behind it (`"all"` for every study of the outcome) |
| `very_serious` | −2 | A reason and the studies behind it |

4. **Rating up.** Only observational evidence, for `large_effect`, `dose_response` or `plausible_confounding`, by 1 or 2 levels, each with a reason and `decided_by` naming the person who decided. You may propose it; the user decides.
5. **Certainty.** The start minus the downgrades plus the upgrades, never below very low or above high. The label in `sof.json` must equal it.
6. **No studies.** The certainty is `no_evidence`. That is not "very low": there is nothing to rate.

## What each domain looks at

| Domain | Look at | Rate down when |
|---|---|---|
| `risk_of_bias` | This skill's judgements for the outcome, and the weight each study carries | The studies that carry most of the weight have limitations that could change the estimate. Say why a high-risk study with little weight does or does not matter |
| `inconsistency` | Point estimates, overlap of the intervals, heterogeneity statistics, the prediction interval | Results differ in ways the subgroup and sensitivity analyses do not explain, and the difference matters for a decision |
| `indirectness` | Population, intervention, comparator and outcome against the review question; surrogate outcomes | The evidence answers a different question from the one asked |
| `imprecision` | The confidence interval against the threshold the review set for an important effect; the numbers of participants and events | The interval includes effects that would lead to different decisions |
| `publication_bias` | Completeness of the search, trial registries, funding, tests for small-study effects | Bias is strongly suspected. With too few studies to judge, `not_assessable` with the reason |

No numeric cut-off decides a domain by itself, such as a band of a heterogeneity statistic or a fixed sample size. Use a threshold only when the protocol or the user sets one, and quote it in the reason. Testing for small-study effects is, by convention, done only with ten or more studies, and an asymmetric funnel plot is not proof of publication bias.

## Absolute effects

For a risk ratio (RR) or odds ratio (OR) and a comparator risk CR, written as a proportion:

- Risk with the comparator: CR × 1,000.
- Risk with the intervention: RR × CR, or OR × CR / (1 − CR + OR × CR), times 1,000, never above 1,000. Its interval comes from the ratio's interval.
- Difference: the risk with the intervention minus the risk with the comparator, per 1,000, written as "fewer" or "more".

The comparator risk needs a source: the median or pooled risk in the control groups of the included studies (from the extraction table), or an external figure the user supplies and cites, such as a cohort or a registry. Give several when the risk differs across the population; `comparator_risks` takes a list, and each gets its own row. For a mean difference the effect is already in the outcome's unit, and no rate per 1,000 is computed.

## sof.json

```json
{"question": "Intervention compared with comparator for population",
 "outcomes": [{
   "id": "weight", "name": "Body weight at 12 weeks", "studies": ["alder2021", "birch2022", "cedar2023"],
   "participants": 240, "design": "randomised", "start": "high",
   "effect": {"measure": "RR", "value": 0.80, "low": 0.60, "high": 1.05, "units": "",
              "source": "meta-analysis/results.json, record weight_rr"},
   "results_id": "weight_rr",
   "comparator_risks": [{"label": "control groups", "value": 0.15,
                         "source": "median risk in the control groups, extraction.csv"}],
   "downgrades": {"risk_of_bias": {"decision": "serious", "reason": "…", "studies": ["cedar2023"]},
                  "inconsistency": {"decision": "none"}, "indirectness": {"decision": "none"},
                  "imprecision": {"decision": "serious", "reason": "…", "studies": "all"},
                  "publication_bias": {"decision": "not_assessable", "reason": "three studies"}},
   "upgrades": {},
   "certainty": "low", "decided_by": "model", "checked_by": ""}]}
```

- `id` is the outcome's id in `assessments.json`: `sof_check.py` checks that every study listed has a risk-of-bias assessment of that outcome.
- `measure` is `RR`, `OR`, `HR`, `MD`, `SMD`, `RD` or the name the results file uses. Absolute effects are computed for RR and OR.
- `results_id` names the record in `meta-analysis/results.json`, written by `researchzy-meta-analysis`. `sof_check.py --results` compares the estimate, its interval, the number of studies and the participants with that record, at the precision written in `sof.json`: copy the numbers from the record and keep their decimals.
- `decided_by` is `model` for your ratings; `checked_by` names the person who reviewed them.

`sof.md` holds the summary-of-findings table, the comparator risks with their sources, the evidence profile with a numbered reason for each decision, and the checks that did not pass.

## Writing about certainty (convention)

A common convention, which the user may change, words each finding by its certainty: high "results in", moderate "probably results in", low "may result in", very low "the evidence is very uncertain about". Keep the effect and its certainty in the same sentence.
