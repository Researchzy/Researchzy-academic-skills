# Moderation and moderated mediation

The model is y = b0 + b1·x + b2·w + b3·x·w + covariates. b3 is the change in the slope of x per unit of w. Write the product as `x:w` in the model block; `path_tools` builds it from the columns.

## Centring

`pt.fit_equations(data, model, center=["aut", "sup"])` subtracts from each named column its mean over the analysed rows and records `centring` (the means, and "mean of the n analysed rows"). Without `center`, it records "not centred".

| Centring changes | Centring does not change |
|---|---|
| b1 and b2: each becomes the slope at the other variable's mean | b3, its standard error, t and p |
| The VIF of x, w and x·w, which is high by construction without it | The simple slope at any given value of w |

So centring is a choice about what b1 and b2 mean, not a remedy for collinearity, and a high VIF of a product term is not a reason to doubt b3. With `center`, the record also holds `b3_uncentred` and `vif_uncentred`, and `check_paths.py` fails when b3 differs between the two fits. That catches a centring done wrong, such as a mean taken within each case, which sets every value to 0. A standardized product (z-scores multiplied) has a different b3 and is reported as such.

## Probe values

Probe at values of the moderator that occur in the data. For a skewed or bounded moderator, the mean plus one SD can lie above the scale's maximum: a slope there describes nobody.

| Moderator | Probe at |
|---|---|
| Continuous, roughly symmetric | `mean-1sd`, `mean`, `mean+1sd`, if all three lie inside the range |
| Skewed or bounded | `p16`, `p50`, `p84`: those percentiles of the analysed rows |
| A few meaningful values (scale anchors, a policy threshold) | Those values, with their source in `model.md` |
| Categories | Each category, as 0/1 columns |

Record the choice and its source in `model.md`. `pt.probe` and `probe_interaction.py` flag a probe outside the observed range; `check_paths.py` fails a recorded probe outside it, and a text that probes at k SD (+1 SD, 均值以上1个标准差) where that value lies outside the range. In the text, name the moderator ("at supervisor support = 5.25"), not "W = 5.25": the number check reads "W =" as a test statistic.

## Simple slopes and Johnson-Neyman

At moderator value w (u = w minus the centring mean), the slope of x is b1 + b3·u, with standard error √(var b1 + 2u·cov(b1, b3) + u²·var b3) and t on the equation's residual df. `pt.probe(fit, focal="a1", interaction="a3", moderator="sup", probes=["p16", "p50", "p84"])` reads these from the fit.

The Johnson-Neyman bounds are the moderator values where the slope's t equals the critical value. Report the region inside the observed range where the interval of the slope excludes zero ("from 4.01 to 7, the maximum"), and say when a root lies outside the range. A region that holds nowhere or everywhere in the range is reported as such. Without bounds (two-valued moderator, categories), give `jn_reason`.

From summary numbers, for a model fitted elsewhere:

```sh
python3 "$SKILL_DIR/scripts/probe_interaction.py" --b1 0.40 --b3 0.15 --var-b1 0.0024 --var-b3 0.0021 --cov -0.0002 \
  --df 344 --min 1 --max 7 --mean 6.02 --sd 1.31 --center 6.02 --probe 5.25 6.5 7
```

It writes `paths/probe.md` and exits 1 when a probe lies outside the range.

## Moderated mediation

| Stage moderated | Conditional indirect effect at w | Index |
|---|---|---|
| First: W moderates X → M (`mng ~ a1*aut + a2*sup + a3*aut:sup`) | (a1 + a3·u)·b | a3·b |
| Second: W moderates M → Y (`eng ~ b1*mng + b2*sup + b3*mng:sup + cp*aut`) | a·(b1 + b3·u) | a·b3 |

```python
imm = pt.moderated_mediation_index(data, model["models"]["moderated"], index="a3*b", conditional="(a1 + a3*{w})*b",
                                   moderator="sup", probes=["p16", "p50", "p84"], n_boot=5000, seed=SEED,
                                   center=["aut", "sup"])
```

The index and every conditional effect come from the same draws. The index is the slope of the indirect effect across the moderator; its interval answers whether the indirect effect depends on W. Two conditional effects, one with an interval excluding zero and one without, do not show that the indirect effect is moderated. When both stages are moderated, the indirect effect is not linear in W and no single index exists: report the conditional effects and the contrasts between them that `model.md` names.

## Recording

`pt.probe` returns `kind` `moderation`: the fit, `focal`, `interaction`, `moderator` (column, min, max, mean, SD, percentiles), `centring`, `b3_uncentred` and `probe` (slopes and `jn`). Record the interaction's coefficient as the estimate with its interval, t, df and p:

```python
a3 = mod["coefficients"]["a3"]
rz.record(id="a3", question="Does supervisor support moderate the autonomy-meaning path?", family="H4", role="primary",
          test="OLS, autonomy x support in the meaning equation", unit="respondent", n=mod["n"],
          estimate={"name": "interaction a3", "value": a3["value"], "units": "meaning points per autonomy point per support point"},
          interval={"low": a3["low"], "high": a3["high"], "level": 0.95}, statistic={"name": "t", "value": a3["t"]},
          df=mod["equations"]["mng"]["df_resid"], p=a3["p"], effect_size="estimate", extra={"paths": mod})
```

`pt.moderated_mediation_index` returns `kind` `moderated_mediation` with `index` naming the defined parameter, each conditional effect with its `at` value, and the interval record; add `sensitivity` as for mediation and record the index as the estimate.

## Writing

> The association of autonomy with meaning was larger where supervisor support was higher (a3 = 0.089, 95% CI 0.014 to 0.164). Support was skewed towards the top of its scale, so the slopes were probed at its 16th, 50th and 84th percentiles (5.25, 6.5 and 7): 0.29 (95% CI 0.18 to 0.41), 0.40 (0.30 to 0.51) and 0.45 (0.33 to 0.57). The interval of the slope excluded zero for support from 4.01 to 7. The index of moderated mediation was 0.027 (95% CI 0.009 to 0.046).

The numbers are an illustration; every number in a real text comes from `results.json`.
