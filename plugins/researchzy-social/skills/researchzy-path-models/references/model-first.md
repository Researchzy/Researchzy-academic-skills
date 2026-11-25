# The model first

A path model chosen after looking at estimates fits the sample, not the question. So the model is written in `paths/model.md`, the user confirms it, and `check_paths.py register` records its SHA-256 in `paths/ledger.jsonl` before the first estimate. Every later change is a deviation with a reason, and the text reports it.

## paths/model.md

Three parts are required; `register` refuses the file without them.

| Part | Form |
|---|---|
| Design line | `Design: cross-sectional`, `longitudinal` or `experimental` (`设计：横截面` also works), as the user states it; add in brackets what was measured when |
| Roles table | Header `\| Role \| Column \| Names in the text \|`; one row per variable; roles `X`, `M` (`M1`, `M2`), `W`, `Y`, `covariate`; names separated by `;` |
| Model blocks | A fenced block opened by `` ```model <name> `` per model, in lavaan style; the analysis script reads it as `model["models"]["<name>"]` |

Also write, one line each: the hypotheses with the path each one concerns; covariates and why each was chosen before estimation; the missing-data decision (from `researchzy-statistics`); which columns are centred; the probe values and their source; the interval method, draws, seed and level; the sensitivity plan; for latent variables, the file the measurement model comes from and its SHA-256.

**Names in the text** are the words the paper uses for each variable, in every language of the text (`autonomy; 自主性`). The wording check counts a sentence as naming a variable when one of these names appears in it, so give the specific phrase (`supervisor support`) rather than an everyday word on its own (`support`).

An invented example (the variables and settings are not from any study):

````markdown
# Model: autonomy, meaning and engagement

- Design: cross-sectional (one survey wave; every variable measured at the same time)
- H1 autonomy is positively associated with meaning (a); H2 meaning with engagement, autonomy held constant (b);
  H3 the indirect effect a·b is positive; H4 supervisor support moderates the a path (index a3·b)
- Covariates: age, female, chosen before estimation. Missing data: rows complete in every model variable.
- Centring: aut and sup around the mean of the analysed rows. Probes of sup: p16, p50, p84 (sup is skewed).
- Interval: percentile bootstrap of cases, 5000 draws, seed 20261118, level 0.95. Sensitivity: R mediation, or not done.

| Role | Column | Names in the text |
|---|---|---|
| X | aut | autonomy; 自主性 |
| M | mng | meaning; sense of meaning; 意义感 |
| W | sup | supervisor support; 领导支持 |
| Y | eng | engagement; work engagement; 投入 |
| covariate | age | age; 年龄 |

```model mediation
mng ~ a*aut + age + female
eng ~ b*mng + cp*aut + age + female
ind := a*b
```

```model moderated
mng ~ a1*aut + a2*sup + a3*aut:sup + age + female
eng ~ b*mng + cp*aut + age + female
```
````

## The model syntax

| Statement | Meaning |
|---|---|
| `y ~ a*x + z` | A regression of y on x and z; `a` labels the x coefficient |
| `y ~ a3*x:w` | The product of x and w, labelled `a3` (columns, not latent variables) |
| `F =~ i1 + i2 + i3` | A latent variable measured by items: copy these lines from the CFA syntax of `researchzy-psychometrics` |
| `i1 ~~ i2` | A residual covariance (latent models only) |
| `ind := a*b` | A defined parameter: labels, numbers, `+ - * /` and brackets |

Labels are letters, digits and `_`, each used once. Categories enter as 0/1 columns made in the script. A comparison of an analysed model with the registered one ignores labels, the order of terms and the order of a product; it does not ignore an added or dropped term, path or covariance.

## Registration and changes

```sh
python3 "$SKILL_DIR/scripts/check_paths.py" register paths/model.md
python3 "$SKILL_DIR/scripts/check_paths.py" register paths/model.md --reason "tenure added: the reviewer asked for it"
```

The first command runs once, after the user confirms the file and before `analysis.py` is run. Once estimates exist, a changed `model.md` is refused without `--reason`. The check fails when `model.md` no longer has the SHA-256 of its last registration. Registering is not a test of the model: it fixes what counts as planned.

## Identification

A bootstrap interval measures sampling error, not whether a path is causal. Write in `model.md` which of these the design supplies and which are assumed:

| Assumption | Supplied by |
|---|---|
| No unmeasured confounding of X and M, or of X and Y | Random assignment of X |
| No unmeasured confounding of M and Y | Nothing in the design: assumed, then probed by the sensitivity analysis |
| No confounder of M and Y that X itself changes | Theory about the process; it is not testable here |
| X before M before Y | Measurement at three occasions; a cross-sectional survey cannot order them |

An experiment supplies the first row only: the b path stays observational.

## Wording by design

| Design | Write | Do not write |
|---|---|---|
| Cross-sectional | "was associated with", "is consistent with the hypothesised path", "与……相关", "与……一致" | "leads to", "causes", "increases", "drives", "导致", "引起", "提高", "促进", and these words in the title, abstract and discussion |
| Longitudinal | "earlier autonomy was associated with later meaning" | Causal verbs, unless the user's identification argument is written in `model.md` |
| Experimental | "assignment to the autonomy condition increased meaning" (the a path) | Causal verbs about M and Y |
| Any | The indirect and direct effects with their intervals | "full" or "partial mediation", "完全中介", "部分中介"; a Sobel or Baron-Kenny test as evidence; "proves", "证明" |

`check_paths.py --text` enforces the cross-sectional row in sentences that name two model variables, and the last row everywhere. A sentence that rules a claim out ("cannot show that autonomy causes engagement", "不能证明") is not a finding.

## Every fit is a row

- Fit the registered model first and record it, even when its fit is poor.
- Each change (a path, a covariate, a residual covariance, a dropped item) is a new fit and a new record: `kept=False, reason="freed mng1 ~~ eng1: same wording"` for the steps, and for a kept final model `extra["paths"]["deviation"]` with the reason. One change per fit.
- `check_paths.py` fails a kept model that differs from every registered block when it has no deviation reason, or when the run's ledger lacks the registered model's fit or one earlier fit per change.
- It writes `paths/models.md`: every model of the run, kept or dropped, with its changes. Report the registered model's result first, then each change and why, and label the final model exploratory when it was chosen after seeing the fit.
