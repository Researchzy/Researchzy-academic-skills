# The structural part of an SEM

## Measurement first, and from elsewhere

The measurement model is tested by `researchzy-psychometrics` (plugin `researchzy-social`, when installed): its `psychometrics/items.json` maps items to constructs, and its CFA syntax passed convergence, identification and validity checks there. Copy the `=~` lines of that syntax into a `` ```model `` block of `paths/model.md`, add the structural paths (`MNG ~ a*AUT`), and record in `model.md` the file and SHA-256 they came from. Do not re-test or change the measurement model here; a measurement problem goes back to that skill. Without its output, ask the user for the measurement model and its evidence, or use composite scores and say so.

## Engines

| Engine | How | Notes |
|---|---|---|
| semopy | `python3 -m pip install --user semopy`, with the user's consent; `pt.fit_sem(data, model)` | No `:=` (path_tools evaluates them); no constraints across groups; check whether the installed version reports modification indices |
| lavaan (R) | Check with `Rscript -e 'library(lavaan)'`. To install, with the user's consent: `apt-get install r-cran-lavaan` on Debian or Ubuntu with root; otherwise `install.packages("lavaan")` into a writable library (create `Sys.getenv("R_LIBS_USER")` first), which on Linux compiles Fortran in mnormt, pbivnorm and quadprog and needs gfortran. Run from an R script the user keeps | `sem()`, `modindices()`, multigroup constraints, bootstrap intervals with `se = "bootstrap"`. The R script writes its estimates, df, fit and convergence to a CSV or JSON file in `paths/`; `analysis.py` reads and records them, with `engine` naming lavaan and its version. Never retype console output |

Without either, the structural model is `not_checked`: record `fit_sem`'s answer with `kept=False` and say why. Never estimate latent paths from composite scores and call them latent.

## What fit_sem records

The rows complete in every observed variable (`n`, `rows_dropped`), `converged` and semopy's message, `df`, χ² and its p, CFI, TLI, RMSEA, SRMR, and each structural path with its estimate, SE, z, p and standardized value. Two details:

- **df.** semopy counts the variances of observed exogenous variables (a covariate such as age) as data without estimating them, which adds to df. `fit_sem` declares them (`age ~~ age`, listed in `declared`), so df counts as lavaan's does. Check df by hand when it matters: the number of distinct variances and covariances of the observed variables minus the free parameters.
- **SRMR** is computed from the sample covariance (divisor n) and the model-implied covariance; the formula is in `srmr_formula`. With df = 0 the model reproduces the data and CFI, TLI and RMSEA are left empty.

Before any fit index, report whether the model converged, its df, the estimator, and improper estimates (negative variances, standardized loadings at or above 1). A model that did not converge has no estimates to report.

## Fit is judged by conventions

No cut-off for CFI, TLI, RMSEA or SRMR is a law. If the user wants one, record it in `model.md` as a convention with its source (a paper the user names, read in this session), and write "CFI of 0.961, above the 0.95 convention of [source]". Without a stated convention, report the values and the df and do not label the fit good or poor.

## Re-specification

Every change to the registered model is a new fit and a new ledger row:

1. Fit and record the registered model first, whatever its fit.
2. One change per fit: a residual covariance, a path, a cross-loading. Its reason is substantive (the two items share wording, the same rater, a path in the theory), not only a modification index. Record the fit with `kept=False, reason="..."`, unless it is the final model.
3. The final model, if it differs from the registered one, is kept with `extra["paths"]["deviation"]` and labelled exploratory (`role="exploratory"`).
4. `check_paths.py` writes `paths/models.md` with every model and its changes; the text reports the registered model's fit and each change.

A request such as "free residual covariances until CFI exceeds .95" asks the data to choose the model. Before doing it, tell the user that each freed parameter improves fit in this sample whether or not it reflects anything; that the final fit no longer tests the hypothesised model; that the result has to be labelled exploratory and confirmed in new data; and that every step will be reported. If the user still wants it, do it one change at a time, with a reason for each, and record every step. A rival model that theory motivates, registered and fitted beside the hypothesised one, tells a reader more than one model adjusted until it passes a cut-off.

## Indirect effects with latent variables

`pt.bootstrap_indirect(items, model["models"]["latent"], {"ind": "a*b"}, n_boot=2000, seed=SEED)` refits the semopy model in every draw (tens of milliseconds each, so 2000 draws take a minute or more); draws that fail to converge are counted in `failed` and reported. Set the number of draws in `model.md`. With lavaan, use its bootstrap and record the interval type it printed.

## Comparing paths across groups

A path compared between groups (departments, countries) means the same thing in each group only when the loadings are equal across groups: metric invariance, tested by `researchzy-psychometrics` with lavaan.

| Invariance record from psychometrics | Do |
|---|---|
| Metric (or scalar) invariance holds | Compare the structural paths; with lavaan, constrain the path and compare the fits |
| Not tested, or tested with semopy only (not_checked) | Do not compare latent paths; say why. With composite scores, test the difference as a group × predictor interaction in OLS, and say the composites assume equal measurement |
| Metric invariance fails | Do not compare; report the paths per group descriptively, if at all |

## Recording

`pt.fit_sem` returns `kind` `sem`. Record the path the hypothesis is about as the estimate (its `value` from `coefficients`), with `extra={"paths": sem}`. `check_paths.py` fails a kept structural model that did not converge, has no df or no fit, or was recorded although semopy was missing.
