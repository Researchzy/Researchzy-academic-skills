# Multiplicity, missing data and diagnostics

## Families and corrections

A family is the set of tests behind one claim. Decide the families in `plan.md` before running anything, and give each test its `family` in `rz.record`. The correction follows from what the claim says, not from the number of tests.

| The claim | Family | Correction (`rz.correct(family, method)`) |
|---|---|---|
| One primary comparison | That test alone | None |
| Several co-primary outcomes, each a claim of its own | All of them | `holm` (controls the chance of any false claim; never less powerful than `bonferroni`) |
| Which pairs of groups differ, after a comparison of three or more | Every pair | Tukey or Dunnett through the procedure (`adjusted={...}`), or pairwise Welch tests with `holm` |
| Each treatment against one control | The comparisons with the control | Dunnett, or `holm` |
| Screening many outcomes or features for candidates to follow up | All screened | `bh`; the claim is then "a candidate", and the text says the result is hypothesis-generating |
| Screening with strongly dependent tests | All screened | `by` |
| Secondary outcomes reported for completeness | Each outcome on its own, labelled secondary | None, with `role="secondary"` and no claim beyond the estimate |

Rules:

- Correct over every test run for the claim, including those dropped from the paper: `rz.correct` counts dropped records, and `check_results.py` compares the count with the ledger.
- Name the family, the number of tests and the method in the Statistical analysis paragraph.
- A test chosen after seeing the data (a subgroup that looked interesting, a cut-off moved) is exploratory: `role="exploratory"`, in a family of its own, and the text says so.
- An uncorrected p-value of a corrected family is shown only next to its adjusted value, labelled.
- Power each test of a family at the corrected alpha when planning (`power.py --alpha`).

## Diagnostics are descriptions

Diagnostics describe the data; they do not choose the test. The test is fixed in `plan.md` from the design and the question. Report what the diagnostics show in `notes` or `descriptives`, and plan a sensitivity analysis when a problem is serious.

| Look at | How | When it is a problem |
|---|---|---|
| Distribution of each group, or of the paired differences (not the raw occasions) | Points or a histogram from `researchzy-figures`; skewness, median and quartiles | Strong skew with small n: the mean is a poor summary. Prefer the planned rank analysis or a log scale, decided before the test, or report both with the planned one as primary |
| Spread per group | SD per group and their ratio | Never a reason to leave Welch; a reason not to use Student, Tukey or the F test |
| Outliers | Values outside 1.5 IQR, listed with their unit | Check them against the source. Remove only a value proven wrong, with the reason in the ledger; otherwise keep it and, if planned, add a sensitivity analysis without it (`kept=False` or a secondary role) |
| Regression residuals | Residuals against fitted values; influence (Cook's distance) | A pattern: the model is wrong; change the model in the plan, record the first fit as dropped with the reason |
| Model fitting | Convergence warnings, singular fits, separation | Do not report the estimate; record it as dropped with the warning |

Shapiro-Wilk or Levene p-values may be shown as descriptions; never write "the data were normal" from a large p, and never switch tests on them.

## Missing data

Decide by why data are missing, not by the percentage. Count missing values per group and per variable from the probe, ask the user why they are missing if the files do not say, and write the decision in `plan.md` before any test.

| Why values are missing | Analysis |
|---|---|
| Unrelated to the outcome and to anything measured (a sample dropped, a machine failed) | Complete-case analysis is unbiased; report the n analysed per group |
| A covariate is missing, and missingness does not depend on the outcome | Complete-case analysis of a regression is still unbiased; or multiple imputation (`statsmodels.imputation.mice`) |
| Depends on measured variables (older participants missed more visits) | Mixed model on all observed outcomes over time, or multiple imputation including those variables; complete-case analysis as a sensitivity analysis |
| May depend on the missing value itself (the sickest dropped out) | No analysis removes this. Run the primary analysis, then a sensitivity analysis that shifts the imputed values (delta adjustment) and report how far the conclusion moves; if this is the main problem, say a statistician is needed |

Rules:

- Never replace missing values with zero, the mean or the last observation.
- With multiple imputation, use at least as many imputations as the percentage of incomplete units, combine with Rubin's rules, and report the complete-case estimate next to it.
- Report how many units were analysed in each group and why the others were not, in the Results text (`n` in `results.json` is the analysed n).
