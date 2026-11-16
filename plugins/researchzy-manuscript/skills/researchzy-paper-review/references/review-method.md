# Review method: claims, evidence and numbers

Two passes over the manuscript, in this order, before any finding is written. They make each finding follow from one claim and one piece of evidence instead of from an impression of the whole.

## 1. The claim–evidence table

**Pick the load-bearing claims.** These are the statements the title, the abstract, the end of the introduction and the conclusion rest on: usually three to seven. A statement the paper could lose without changing its message is not one of them. Write each claim in its strongest wording in the manuscript (often the abstract's), because that is the version a reviewer will hold the authors to. Record them under `claims` in `findings.json`.

**Give each claim a type.** The type decides what evidence the claim needs. A proof, a simulation and a field study answer to different standards; judge the claim by its type, not by the habits of another field.

| `type` | The claim says | It needs | How it usually fails |
|---|---|---|---|
| `causal` | X produces, improves, reduces or explains Y | A comparison that isolates X: random assignment, an ablation, a control that differs only in X; or a design whose identifying assumptions are stated and defended | Groups that differ in more than X; a before-and-after difference; "associated with" in the results and "leads to" in the abstract |
| `generalisation` | It holds for a class: all datasets, patients, languages, settings | Evidence under varied conditions, some of them not used to develop the method or choose the model | One dataset, one site, one population; test cases that resemble the development ones |
| `improvement` | Better, faster, cheaper or more accurate than something | A named baseline that is current, was given the same data, tuning effort and metric, and a difference larger than the run-to-run variation | A weak or untuned baseline; another metric or split; a gain inside the noise |
| `priority` | First, only, novel, state of the art, "has not been studied" | A search of the literature: see [Novelty and citations](novelty-and-citations.md) | Asserted from the authors' belief |
| `formal` | A theorem, a bound, a derivation or a guarantee holds | A complete proof or derivation with its assumptions stated, and experiments that respect those assumptions | An assumption used and not stated; a result proved for a simpler case than the one claimed |
| `descriptive` | A measurement, a rate, an association, an observation | The number in a table or figure, with its denominator and its uncertainty | The number is not where the text says, or comes from a subset |

**Find the evidence.** Under `evidence`, name the table, figure or section that supports the claim. Open it and read it; a sentence describing a table is not the table.

**Rate the support.**

| `support` | Meaning |
|---|---|
| `supported` | The evidence shows what the claim says, for the population, outcome and conditions the claim names. |
| `limited` | The evidence supports a narrower or weaker claim than the one written. |
| `unsupported` | The manuscript, as read, has no evidence for it. |
| `contradicted` | Evidence in the manuscript points the other way. |
| `not_assessable` | The evidence is in something not provided or not read, or the claim is too vague to test. |

**Name the mismatch** for every claim that is not `supported`. More than one may apply.

| `mismatch` | The claim and the evidence differ in |
|---|---|
| `direction` | the sign of the effect, or which group is higher |
| `magnitude` | the size: "large" or "substantial" for a small difference, or a number the tables do not give |
| `population` | who or what was studied, against who or what the claim is about |
| `outcome` | what was measured, against what is claimed (a proxy standing in for the real outcome) |
| `timepoint` | when or for how long it was measured, against the period claimed |
| `causal_language` | causal wording on correlational or uncontrolled evidence |
| `scope` | the conditions, settings or cases covered, against the generality claimed |

**From table to findings.** Every claim that is not `supported` leads to a finding, or its `note` says why not.

| `support` | Usual finding |
|---|---|
| `limited` | "Narrow the claim": major when it is the headline claim, otherwise minor. Status `confirmed`. |
| `unsupported`, `contradicted` | Major or critical, status `confirmed`. The scientific verdict cannot be `ready`. |
| `not_assessable` | Status `reporting_gap` or `unresolved`, never `confirmed`: what was not read was not found wanting. |

## 2. The numbers-and-displays audit

A separate pass with the tables and figures open. Take the layers in order. In the review, say which layers were run on which displays: a layer that was not run has not passed.

| Layer | What to do | Example of a finding |
|---|---|---|
| Arithmetic | Recompute what can be recomputed: percentages from counts, totals from rows, differences and ratios from the values given, group sizes that should add up to N, a mean that should lie inside the range | 41 of 212 reported as 21% |
| Bounds | Look for values that cannot be: a proportion above 1, a negative count or variance, a correlation outside −1 to 1, an interval that does not contain its estimate, a score above the scale's maximum | A 95% interval of 2.1 to 4.0 around an estimate of 4.6 |
| Text against displays | Check every number in the abstract, the results text and the conclusion against the table or figure it comes from: value, unit, rounding, row and column | The abstract gives 6.4 points, the table 5.9 |
| Unit of aggregation | Find what `n` counts (patients or visits, images or lesions, runs or seeds) and whether text, table and test use the same unit; a mean of ratios against a ratio of means; per-class against overall figures | 212 students in the methods, 240 exam scripts in the table |
| Provenance | Trace each headline number to a described procedure: which dataset, split, run and exclusions. Check that the test data took no part in tuning and that the sample is the same across tables | The best result is reported, and the text does not say how the run was chosen |
| Anomalies | Note what is too regular: identical values where variation is expected, the same spread in every row, digits repeated across unrelated cells, results with no uncertainty at all | Every standard deviation in a column is 0.10 |

Rules for this pass:

- Recompute before calling a number wrong, and put the calculation in `basis`. A difference that rounding explains is not a finding.
- An oddity without an explanation is `unresolved`, and its fix is a question to the authors. Describe what is in the display; do not suggest how it got there.
- Figures: axes labelled with units, the scale (logarithmic, truncated), what the error bars are, `n` for each panel, and whether the caption says what the text claims. If the figure images were not opened, record that in `coverage` and audit captions only.
- One number given with different precision in two places is minor, unless the conclusion turns on the digit.
- This pass checks consistency, not the choice of test or model. Those go to `researchzy-stats-review`.
