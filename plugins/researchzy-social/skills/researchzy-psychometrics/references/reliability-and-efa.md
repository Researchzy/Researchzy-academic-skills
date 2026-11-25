# Reliability and exploratory factor analysis

## The analysis script

One script, `psychometrics/analysis.py`, reads the scored copy and records every result. It never writes to the data.

```python
"""<study>: measurement analysis. Item map: psychometrics/items.json. Run: python3 psychometrics/analysis.py"""
import sys
import numpy as np
import pandas as pd
sys.path.insert(0, "<SKILL_DIR>/scripts")        # written out in full
import psy_tools as pt
import rz_results as rz

rz.OUT = "psychometrics"
SEED, DATA, MAP = 20261118, "psychometrics/survey.scored.csv", "psychometrics/items.json"
data = pd.read_csv(DATA)
items = pt.item_map(MAP)
common = dict(family="measurement", role="primary", unit="respondent")

for name, members in items.items():
    a = pt.alpha(data[members], ci="feldt")
    rz.record(id=f"alpha_{name}", question=f"Internal consistency of {name}", test="Cronbach's alpha", **common,
              n={"respondents": a["n"]}, estimate={"name": "Cronbach's alpha", "value": a["alpha"], "units": "unitless"},
              interval={"low": a["low"], "high": a["high"], "level": a["level"]},
              extra={"psy": {"kind": "reliability", "construct": name, "items": members, **a,
                             "item_stats": pt.item_stats(data[members], scale_min=1, scale_max=7)}})
...                                              # EFA, CFA, invariance, common-method tests: see the other references
rz.finish(script=__file__, data=[DATA, MAP], seed=SEED, packages=("semopy",), settings={"alpha": 0.05})
```

Every function drops incomplete rows of the columns it uses and returns the n it used; say so in the methods. Record what the text will print, and nothing typed by hand.

## Item statistics

`pt.item_stats` gives per item the mean, SD, item-rest r (the item against the sum of the others), alpha if the item is deleted, the shares at the floor and the ceiling of the scale, the categories used and the skewness. They describe; they decide nothing.

Deleting an item changes the scale others have validated. Only the user decides it, for a reason that is not "alpha rises": a wording problem, a translation error, a published revision. Record the reason in `dropped` of `items.json`, run the analysis again, and report both versions.

## Alpha and its interval

Alpha = k / (k − 1) × (1 − Σ item variances / variance of the sum). Its interval:

| `ci` | Method | Records |
|---|---|---|
| `feldt` (default) | (1 − alpha) / (1 − estimate) follows an F distribution with n − 1 and (n − 1)(k − 1) df | `low`, `high`, `level` |
| `bootstrap` | Percentile interval of alpha over rows resampled with a seeded generator | also `seed`, `n_boot` |

Alpha assumes one factor and equal loadings. It rises with the number of items, and a high value does not show that a scale measures one thing. Report it with omega from the CFA, which allows unequal loadings.

## When to run an EFA

For a new or adapted scale, a translation, or a CFA that fits poorly. Never present an EFA and a CFA on the same rows as confirmation: split the sample first.

```python
rng = np.random.default_rng(SEED)
order = rng.permutation(len(data))
half_a, half_b = data.iloc[order[: len(data) // 2]], data.iloc[order[len(data) // 2:]]   # EFA on a, CFA on b
pa = pt.parallel_analysis(half_a[every_item], n_sets=500, percentile=95, seed=SEED)
efa = pt.efa(half_a[every_item], n_factors=pa["suggested"], method="pa", rotation="oblimin")
rz.record(id="efa", question="How many factors do the items measure?", test="exploratory factor analysis", **common,
          n={"respondents": efa["n"]}, estimate={"name": "factors retained", "value": efa["n_factors"], "units": "factors"},
          extra={"psy": {"kind": "efa", "sample": f"random half A (seed {SEED})", **efa, "parallel": pa,
                         "kaiser": pa["kaiser"], "reason": ""}})
```

| Setting | Choice | Record |
|---|---|---|
| Correlations | Pearson here; polychoric correlations need lavaan (or R's psych) | `correlation` |
| Extraction | `pa` (principal axis) or `ml` | `method` |
| Rotation | Oblique (`oblimin`) when the constructs may correlate; `none` for one factor | `rotation`, `factor_corr` |
| Number of factors | Parallel analysis; Kaiser's count beside it, not chosen by | `parallel`, `kaiser`, `n_factors`, `reason` |

statsmodels' `oblimin` is its quartimin rotation. Its `promax` returned uncorrelated factors in a check on 2026-11-18, unlike R's: prefer `oblimin`.

## Parallel analysis

Observed eigenvalues are compared with those of random normal data of the same size. The skill's defaults are conventions the user may change: 500 random sets, the 95th percentile, eigenvalues of the correlation matrix (`kind="pca"`; `"fa"` uses the reduced matrix). Record them all, with the seed. The suggested number is the count of leading eigenvalues above the random ones.

Kaiser's rule (eigenvalues above 1) usually suggests more factors than parallel analysis. When the two disagree, report both counts; retain the parallel-analysis number, or record in `reason` why another number was retained (a theory the user names, an uninterpretable factor). The checker recomputes both counts from the recorded eigenvalues.

## The ordinal decision

Likert items are ordered categories. Treating them as continuous is a decision, not a default, and it is recorded in the CFA's `ordinal` field.

| Data | Options |
|---|---|
| Five or more categories used, roughly symmetric | Continuous ML is often defended; say that it was chosen and why |
| Few categories used, or strong floor or ceiling (`score_items.py` lead) | Ordinal estimation in lavaan (`ordered =`, a WLSMV-type estimator on polychoric correlations), or continuous ML with the limitation stated |

semopy declares ordinal items with `DEFINE(ordinal) item …` in the model text. In a check on 2026-11-18 that path failed with a recent numpy (`corrcoef()` no longer takes `bias`): try it in the session, and if it fails, use lavaan, or record continuous estimation with its limitation. The number five is a convention; the user may set another.
