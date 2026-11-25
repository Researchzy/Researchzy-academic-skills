# Measurement invariance and common-method bias

## What each level allows

Groups can be compared only on what the items measure in the same way in each group. Each level adds equality constraints to the one before and allows one more kind of comparison.

| Level | Equal across groups | Then it is meaningful to compare |
|---|---|---|
| configural | The pattern: same items on the same factors | Nothing yet; it is the baseline |
| metric | Loadings | Relations: correlations and regression slopes between factors |
| scalar | Loadings and intercepts (thresholds for ordinal items) | Latent means, and observed means of the scale |
| strict | Also residual variances | Observed scores as equally precise in each group |

Test the levels in this order and stop at the first that fails. A failed level can be made partial: free the parameters that differ, one at a time, each for a reason (the largest score test or modification index, read together with the item's content), and test that level again. Partial invariance needs most of each factor's parameters still equal; how many is a convention for the user to state. Name every freed parameter, in the record and in the text.

## With lavaan

Fit the same CFA per group with `cfa(model, data, group = "<group column>")`, then add `group.equal = "loadings"`, then `c("loadings", "intercepts")`; free a parameter with `group.partial`, for example `"aut4 ~ 1"` for an intercept. Write each level's chisq, df, CFI, RMSEA and SRMR to the JSON file that the Python script records.

The decision at each level follows a rule the user chooses before seeing the results: the largest drop in CFI and the largest rise in RMSEA, with the source of those numbers. Record it, and compute every delta against the last level that held, not against the failed one before it.

```python
levels = [{"level": "configural", "engine": "lavaan", "chi2": ..., "df": ..., "cfi": ..., "rmsea": ..., "srmr": ...,
           "decision": "holds"},
          {"level": "metric", ..., "delta_cfi": ..., "delta_rmsea": ..., "decision": "holds"},
          {"level": "scalar", ..., "delta_cfi": ..., "delta_rmsea": ..., "decision": "fails"},
          {"level": "scalar", "freed": ["aut4", "mea2"], ..., "decision": "holds"}]   # partial: two intercepts freed
rz.record(id="invariance", question="Do the items measure the same constructs in each sector?",
          test="multigroup CFA, lavaan", **common, n={"public": 210, "private": 190},
          estimate={"name": "delta CFI, scalar against metric", "value": ..., "units": "unitless"},
          extra={"psy": {"kind": "invariance", "engine": "lavaan", "group": "sector", "group_terms": ["sector", "部门"],
                         "levels": levels, "rule": {"name": "<short name>", "max_cfi_drop": ..., "max_rmsea_rise": ...,
                                                    "source": "<paper, page>", "date": "2026-11-18"}}})
```

`group_terms` are the words the text uses for the groups; the checker looks for group comparisons through them. `freed` lists the items whose intercepts (scalar) or loadings (metric) were freed, as the text names them: the checker looks for each name in the text.

## With semopy only

semopy fits each group on its own and cannot hold a parameter equal across groups. Fitting the model per group with `pt.cfa_semopy` shows at most whether the same pattern fits in each (configural evidence). Record metric and scalar as `{"level": "metric", "decision": "not_checked", "reason": "semopy cannot constrain parameters across groups; lavaan is not installed"}`, tell the user, and offer lavaan.

## Comparing group means

Only after scalar invariance holds, or holds partially with the freed parameters named. Under partial invariance compare latent means from the lavaan model, not raw composite scores, which still carry the non-invariant items. The test of the difference goes to `researchzy-statistics` (plugin `researchzy-manuscript`, when installed). When scalar invariance is not checked or fails, say that the means were not compared and why.

## Common-method bias

Procedural remedies (separating predictor and outcome, a marker item planned in the questionnaire) belong to the design, in `researchzy-survey`. Here the statistical tests are run and reported with what they cannot show.

| Test | How | What it can show | What it cannot show |
|---|---|---|---|
| Harman's single factor (`pt.harman`) | Share of variance of the first unrotated component of all items | A very large share points to a dominant common factor | That common-method variance is absent: one factor rarely dominates even when method variance inflates correlations |
| Marker adjustment (`pt.marker_adjust`) | Correlations corrected by r_M, the marker's smallest correlation with the scales (floored at 0): (r − r_M) / (1 − r_M) | How much correlations change if r_M reflects method variance | Anything, if the marker is related to the constructs or does not share their method |
| Latent method factor | The CFA plus a factor loading on every item, uncorrelated with the others (in semopy `M =~ …` and `M ~~ 0*AUT`) | Whether loadings and factor correlations change with the method factor | Which method causes it; such models are often poorly identified, so report convergence and Heywood cases as for any CFA |

```python
h = pt.harman(data[every_item])
scores = pd.DataFrame({name: data[m].mean(axis=1) for name, m in items.items()} | {"mk1": data["mk1"]})
rz.record(id="cmv", question="How far could common-method variance inflate the correlations?",
          test="Harman's test and marker adjustment", **common, n={"respondents": h["n"]},
          estimate={"name": "first-component share", "value": h["share"], "units": "proportion"},
          extra={"psy": {"kind": "cmv", "tests": [h, pt.marker_adjust(scores.corr(), "mk1")],
                         "limits": "<what these tests cannot show, in one or two sentences>"}})
```

Write what each test showed and its limits: "The first unrotated component explained 39% of the variance; this test cannot show that common-method variance is absent." Never write that there is no common-method bias, and never rest a claim that it is "not a concern" on Harman's test alone; the checker fails both.
