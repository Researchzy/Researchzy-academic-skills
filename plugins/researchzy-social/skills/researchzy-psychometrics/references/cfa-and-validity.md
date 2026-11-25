# Confirmatory factor analysis and validity

## Engines

| | semopy (Python) | lavaan (R) |
|---|---|---|
| Install | Check with `import semopy`; if missing, `python3 -m pip install --user semopy` after the user agrees | Check with `Rscript -e 'library(lavaan)'`; if missing, see below |
| One-group CFA | Yes: `pt.cfa_semopy` returns the record | Yes: the R script writes the fields below to JSON |
| SRMR | Not among its statistics: `pt.srmr` computes it | `fitMeasures()` |
| RMSEA interval | Not given: report RMSEA without one | `fitMeasures()` |
| Ordinal items | See [reliability and EFA](reliability-and-efa.md) | `ordered =` |
| Constraints across groups | No: groups are fitted one by one | Yes: the only route to metric and scalar invariance |

Record the engine and its version (`engine`, `engine_version`; `rz.finish(packages=("semopy",))`). When neither engine is installed and the user does not agree to installing one, or the install fails, the CFA is `not_checked`, with the reason.

To install lavaan, after the user agrees: on Debian or Ubuntu with root, `apt-get install r-cran-lavaan` installs ready-built packages. Otherwise install from CRAN into a library the user can write. Create the personal library first (`Rscript -e 'dir.create(Sys.getenv("R_LIBS_USER"), recursive = TRUE)'`): a non-interactive R whose library is not writable stops with "unable to install packages". Then run `Rscript -e 'install.packages("lavaan", repos = "https://cloud.r-project.org")'`. On Linux this builds from source, and lavaan's dependencies mnormt, pbivnorm and quadprog compile Fortran: without `gfortran` the install fails. If it fails, metric and scalar invariance are `not_checked`, with the error as the reason.

## With semopy

```python
cfa = pt.cfa_semopy(half_b, pt.cfa_syntax(MAP), matrices="psychometrics/cfa.matrices.json")
cfa["ordinal"] = "seven-point items treated as continuous, Wishart ML; ENG uses four categories: a limitation"
cfa["validity"] = {**pt.validity(cfa), "htmt": pt.htmt(half_b[every_item].corr(), items,
                                                       matrices="psychometrics/htmt.matrices.json")}
cfa["conventions"] = [{"name": "<short name>", "rule": "<the user's cut-offs>", "source": "<paper, page>",
                       "date": "2026-11-18", "default": False}]
rz.record(id="cfa", question="Does the measurement model fit?", test="confirmatory factor analysis", **common,
          n={"respondents": cfa["n"]}, estimate={"name": "chi-square", "value": cfa["fit"]["chi2"], "units": "unitless"},
          statistic={"name": "chi2", "value": cfa["fit"]["chi2"]}, df=cfa["df"], extra={"psy": {"kind": "cfa", **cfa}})
```

If `cfa_semopy` returns `"converged": false`, record it as it is and report no fit index. semopy fixes each factor's first loading to 1 (marker identification).

## With lavaan

Fit with `cfa()`, then have the R script write one JSON file that the Python script reads and records: `lavInspect(fit, "converged")`, the df and the fit measures (chisq, df, pvalue, cfi, tli, rmsea with its interval, srmr), the standardized loadings and residual variances from `standardizedSolution()`, the factor correlations, and the sample and implied covariance matrices for `pt.save_matrices`. Name the estimator and how ordinal items were treated.

## The CFA record

| Field | Content | Checker |
|---|---|---|
| `converged` | `true` only when the engine says so | fails unless `true` |
| `df`, `n_free` | Degrees of freedom and free parameters | `df` > 0 |
| `identification` | Marker loading or fixed factor variance | required |
| `estimator`, `ordinal` | The estimator, and the decision about ordinal items | required |
| `loadings`, `errors` | Standardized loadings per factor; standardized residual variances | no \|loading\| ≥ 1, no negative variance |
| `factor_corr` | Standardized factor correlations | none at ±1 or beyond |
| `constraints` | What identifies a factor with fewer than three indicators | required for such a factor |
| `fit` | `chi2`, `df`, `p`, `cfi`, `tli`, `rmsea`, `srmr` and `srmr_formula`, or `srmr_reason` | recomputes SRMR from `matrices` |
| `validity`, `conventions` | See below | recomputed |

A Heywood case (a standardized loading of 1 or more, a negative variance) means the solution is improper: report it, do not interpret the fit, and discuss with the user (too few indicators, an item that duplicates another, too small a sample). Never fix a variance at a small positive value to hide it.

## SRMR

`pt.srmr` takes the square root of the mean, over the lower triangle with the diagonal, of ((s_ij − σ_ij) / √(s_ii s_jj))², with the sample covariance computed with divisor n. On the three-factor Holzinger-Swineford model this gives .065, as lavaan reports. `fit.srmr_formula` records the formula, and the saved matrices let the checker recompute it.

## Validity

From the standardized loadings λ and residual variances θ of each factor's items:

| Quantity | Formula | Note |
|---|---|---|
| omega | (Σλ)² / ((Σλ)² + Σθ) | Reliability of the unit-weighted composite under the model |
| CR | (Σλ)² / ((Σλ)² + Σ(1 − λ²)) | Equals omega when each item loads on one factor |
| AVE | mean of λ² | Variance the items share with their factor |
| Fornell-Larcker | AVE of each factor against its squared correlation with every other | the checker lists the pairs where AVE is lower |
| HTMT | mean correlation between the items of two constructs / √(product of the mean correlations within each) | from the item correlations, recomputed from `htmt.matrices.json` |

`pt.validity` returns `None` with the reason for a factor with a Heywood case or a negative loading. A high HTMT or an AVE below a squared correlation does not show that two constructs are one; it shows that these data do not separate them. Report it, and let the user decide between keeping both, merging, or revising, with the reason recorded.

## Conventions and wording

A cut-off is a convention: the user names it, with its source, and it is recorded in `conventions` (`name`, `rule`, `source`, `date`, `default`). The text names the convention by that `name` in the sentence that applies it. Without a recorded convention, report the value and its interval and make no judgement.

| Write | Not |
|---|---|
| "CFI = .93 and SRMR = .052; by <convention name>, the convention the authors chose, CFI falls short" | "The model fit well" |
| "Loadings ranged from .30 (aut5) to .86" | "All loadings exceeded .70" when one did not |
| "AVE of ENG (.48) was below its squared correlation with MEA (.94)" | "Discriminant validity was established" |
| "The model did not converge; no fit index is reported" | Fit indices of a model that did not converge |

The names and values in this table are examples, not cut-offs to apply.
