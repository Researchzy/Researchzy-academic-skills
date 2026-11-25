---
name: researchzy-psychometrics
description: "Test multi-item scales on response data: score from a declared item map, alpha with an interval, EFA with seeded parallel analysis, CFA with convergence and Heywood checks, CR, AVE, HTMT, invariance in lavaan, common-method tests, and a check of the text. Use for scale reliability and validity."
---

# Researchzy Psychometrics

This skill tests multi-item scales on the user's response data. It scores the items from an item map the user confirms and finds keying problems; runs the item analysis and reliability (alpha with an interval, omega); an exploratory factor analysis whose number of factors comes from a seeded parallel analysis; a confirmatory factor analysis whose convergence, identification and improper estimates are recorded before any fit index; convergent and discriminant validity (CR, AVE, Fornell-Larcker, HTMT); measurement invariance across groups when R's lavaan is available; and the statistical tests of common-method bias with their limits. Every result goes through `rz_results.py` into `psychometrics/results.json`, and `check_psychometrics.py` checks the text against it.

It holds no cut-offs: CFI .95, AVE .50 or HTMT .85 are conventions the user chooses and names with a source. It does not write, adapt or translate items or screen response quality (`researchzy-survey`), or estimate structural paths (`researchzy-path-models`), both in plugin `researchzy-social`; nor does it compare composite scores between groups or compute power (`researchzy-statistics`, plugin `researchzy-manuscript`), when installed. It does not run IRT, DIF, PLS-SEM, bifactor models or omega hierarchical: name the tool they need and stop. It runs no content-validity panel and never reproduces a scale's items.

## Requirements

Resolve `SKILL_DIR` to the directory containing this `SKILL.md`. Python 3.10 or newer. `score_items.py`, `check_psychometrics.py`, `rz_results.py` and `check_results.py` need nothing else. `psy_tools.py`, imported by the analysis script, needs numpy, pandas and scipy, and statsmodels for the EFA. A `.sav` file needs pyreadstat; the CFA needs semopy or R with lavaan; metric and scalar invariance need lavaan. Check first what is installed (`import semopy`, `import pyreadstat`, `Rscript -e 'library(lavaan)'`) and install a missing package only after the user agrees: `python3 -m pip install --user semopy pyreadstat`; lavaan as in [CFA and validity](references/cfa-and-validity.md). A step whose package is missing is reported as `not_checked`, with the package named. No account is needed; step 2 says what the Researchzy tools add.

## Inputs

- The data: CSV, TSV or `.sav`, one row per respondent.
- The item map: which items measure which construct, the reverse-worded items, the lowest and highest response, the missing-value codes.
- Each scale's source (paper and page, or the user's own) and licence status.
- The group variable when groups are to be compared, and the marker item if the questionnaire has one.
- The conventions the user will judge results by, each with its source.

Ask once, in one message, for whatever the files do not settle, and ask whether the reverse-worded items are already reversed in the data file. Never guess that answer: it decides the scoring.

## Workflow

Everything goes in `psychometrics/` in the user's working directory. Run every command from the working directory.

1. **Declare the item map.** Write `psychometrics/items.json` ([item map and scoring](references/item-map-and-scoring.md)). Show it to the user as a table; when they confirm it, add `"confirmed": "<date>"`. It is the only source for scoring, the CFA syntax and the construct tables.

2. **Sources.** Record each scale's source and licence in the map. With the `researchzy` plugin (it needs a Researchzy account), find the original validation paper with `search_papers` by the scale's name and read it through `get_paper_files`: record the number of items, the keyed items and the reported structure with page numbers. A scale that is not found is `not_checked`. Without it, use the user's codebook and say so. Never copy item wording from memory.

3. **Score.**

   ```sh
   python3 "$SKILL_DIR/scripts/score_items.py" psychometrics/items.json
   ```

   It writes `<data>.scored.csv` (reverse items as min + max - x), `scoring.json` and `scoring.md`, and never touches the data file. Exit code 1 means a problem; leads never fail, but each is shown to the user before step 4.

   | Finding | Do |
   |---|---|
   | Value outside the scale or not a number | An undeclared missing code goes into `missing`; anything else goes to the user. Never recode it yourself |
   | Item with one value | Ask the user; it cannot enter a scale |
   | Negative item-rest r, not declared reverse | Ask whether the item is reverse-worded; if so, add it to `reverse` and run again |
   | Negative item-rest r, declared reverse | Ask whether the file already holds it reversed (`reversed_in_data`), or whether the key is wrong |
   | Few categories used | Carry it to the ordinal decision of steps 5 and 6 |

4. **Item analysis and reliability.** Write `psychometrics/analysis.py` from the template in [reliability and EFA](references/reliability-and-efa.md): it reads the scored copy, imports `psy_tools` and `rz_results`, sets `rz.OUT = "psychometrics"`, and records every result with `extra={"psy": {"kind": ...}}`. Per construct, `pt.item_stats` and `pt.alpha` (Feldt interval by default, or a seeded bootstrap). Deleting an item is the user's decision, with the reason recorded; no cut-off deletes one.

5. **EFA, when needed** (a new or adapted scale, or a CFA that fails). Split the sample with a seeded generator: EFA on one half, CFA on the other. `pt.parallel_analysis` (seeded; random sets, percentile and eigenvalue type recorded) gives the number of factors, with Kaiser's count beside it; retaining another number needs a recorded reason. Correlations are Pearson: say so, because polychoric correlations need lavaan. Use an oblique rotation for constructs that correlate.

6. **CFA.** Engine: semopy or lavaan, with the user's consent ([CFA and validity](references/cfa-and-validity.md)). Syntax from `pt.cfa_syntax("psychometrics/items.json")`; with semopy, `pt.cfa_semopy(..., matrices=...)` returns the record. Before any fit index is reported: converged, df, identification, indicators per factor, Heywood cases, estimator, and the ordinal decision (`ordinal`). SRMR comes from `pt.srmr`, from the sample and model-implied matrices. Every respecification is a new recorded result with its reason.

7. **Validity.** `pt.validity(cfa)` gives omega, CR and AVE per factor; `pt.htmt` the HTMT matrix. Record them under the CFA's `validity`, with the user's conventions under `conventions`.

8. **Invariance, when groups are compared** ([invariance and CMV](references/invariance-and-cmv.md)). Only lavaan constrains parameters across groups: configural, metric, scalar, in order, each with its fit, the deltas and the user's rule with its source; stop at the first failure or free named parameters. With semopy alone, separate fits per group are configural evidence at most, and metric and scalar are recorded `not_checked` with that reason. Group means are compared only after scalar invariance, or with the freed parameters named; the comparison itself goes to `researchzy-statistics` (plugin `researchzy-manuscript`, when installed).

9. **Common-method bias.** Harman's test with its limits; the marker adjustment when the design has a marker (`pt.marker_adjust`); a latent method factor if the user wants one. Never write that common-method bias is absent.

10. **Write and check.** Run the analysis (`python3 psychometrics/analysis.py`), write `psychometrics/results.md` and `psychometrics/methods.md` from `results.json` only, then:

    ```sh
    python3 "$SKILL_DIR/scripts/check_psychometrics.py" --script psychometrics/analysis.py --text psychometrics/results.md psychometrics/methods.md
    ```

    | Fails | Do |
    |---|---|
    | `cfa`, `factors`, `reliability`, `invariance`, `cmv`, `conventions`, `complete` | Record the missing field in the script and run it again; never edit `results.json` |
    | `validity` | Recompute in the script with `pt.validity` and `pt.htmt`; never type a value |
    | `text` mismatch | Copy the recorded value into the text |
    | `wording` | Name the user's convention in the sentence, or report the value without the judgement |
    | `group_means`, `invariance_claims` | Remove the claim, or name the freed parameters and say "partial" |
    | `cmv_claims`, `loadings_claims` | Say what the test shows and cannot show; give the loadings' real range |
    | `hashes` drift, `not_checked` | Run the analysis again; report a `not_checked` row as not checked, never as passed |

    Hand over `results.md`, `methods.md`, `check.md`, the leads of step 3 and every `not_checked` row.

## Outputs

| File in `psychometrics/` | Content |
|---|---|
| `items.json` | The item map the user confirmed |
| `<data>.scored.csv`, `scoring.json`, `scoring.md` | Scored copy, hashes, item-rest r and alpha before and after scoring, problems, leads |
| `analysis.py` | The kept analysis script |
| `results.json`, `ledger.jsonl` | Every result with its `psy` record, hashes and versions |
| `*.matrices.json` | Saved covariance and correlation matrices, for recomputing SRMR and HTMT |
| `results.md`, `methods.md`, `check.md` | The text and its last check |

## Rules

- Never invent data, loadings, fit values, conventions or sources. Every number in the text comes from `results.json`; a fact in no file is `[Author input needed: …]`.
- Never change the user's data file; derived files go in `psychometrics/`.
- Never reproduce a scale's items. A scale whose licence is `unknown` is named, not quoted.
- Cut-offs are conventions: the user's choice, recorded with its source and date. Without one, report values without calling them good or acceptable.
- No item is deleted, factor retained or path added because of a cut-off alone. The user decides; the reason is recorded.
- Cross-sectional measurement results say nothing about causes; write "is consistent with", never "causes".
- Hand structural models to `researchzy-path-models` (plugin `researchzy-social`) with `items.json` and the CFA syntax that passed; group comparisons and power to `researchzy-statistics`, scree and loading plots to `researchzy-figures` and the full Results section to `researchzy-writing` (plugin `researchzy-manuscript`), when installed.

## Related files

| File | Open when |
|---|---|
| [references/item-map-and-scoring.md](references/item-map-and-scoring.md) | Steps 1 to 3: `items.json`, reverse keys, missing codes, `.sav` files, licences, leads |
| [references/reliability-and-efa.md](references/reliability-and-efa.md) | Steps 4 and 5: the analysis template, alpha, omega, item deletion, parallel analysis, the ordinal decision |
| [references/cfa-and-validity.md](references/cfa-and-validity.md) | Steps 6 and 7: engines, the CFA record, lavaan output, SRMR, CR, AVE, HTMT, conventions, wording |
| [references/invariance-and-cmv.md](references/invariance-and-cmv.md) | Steps 8 and 9: invariance levels and record, group means, common-method tests and their limits |
| `scripts/score_items.py`, `scripts/psy_tools.py`, `scripts/check_psychometrics.py` | The steps above; `--help` or the module docstring lists the options |
| `scripts/rz_results.py`, `scripts/check_results.py` | Copies from `researchzy-statistics`: the result file and the number check that the checker extends |
