# Researchzy Social plugin

Version 2.3.0. Five skills for social-science methods: questionnaires, scale reliability and validity, mediation and moderation, qualitative coding, and text turned into variables. They run on your machine and work on the files you give them. Every cut-off is a convention you choose and record, and every number in your text is checked against the results.

| User goal | Skill | Result |
|---|---|---|
| A questionnaire study, before and after fielding | `researchzy-survey` | An item table with each scale's source and licence, a recorded wording review, attention items, procedural remedies against common-method bias, exclusion rules dated before fielding, and an audit of the returned data: straight-lining on the raw values, speed, attention items, duplicates and missing data, counted under your rules |
| Reliability and validity of multi-item scales | `researchzy-psychometrics` | Scoring from a declared item map that finds unrecoded reverse items, item analysis, alpha and omega, EFA with seeded parallel analysis, CFA with convergence and SRMR, CR, AVE and HTMT, invariance in lavaan, common-method tests with their limits, and checked Results text |
| Mediation, moderation and structural paths | `researchzy-path-models` | A model registered before estimation, indirect effects with seeded bootstrap intervals, simple slopes inside the observed range and the Johnson-Neyman region, the index of moderated mediation, every model in a ledger, and wording checked against the design |
| Qualitative coding of interviews or open answers | `researchzy-qualitative` | The approach recorded first, a versioned codebook, quotes checked at their place in the transcript and in the right speaker's turn, blind calibration of agreement, participants per theme, negative cases and a saturation table, in Chinese or English |
| Text turned into a research variable | `researchzy-text-as-data` | A codebook, sealed blind rounds scoring the model's labels against yours, frozen instructions with provenance on every labelled row, dictionary and topic comparisons, and class shares corrected for the measured errors |

Example prompts:

- `Here is my questionnaire draft and the exported responses. Check the items, then audit the data before I analyse it.`
- `Check the reliability and validity of my three scales from this .sav file and compare the two departments.`
- `Test whether meaning mediates the effect of autonomy on engagement, moderated by support, and check my Results paragraph.`
- `Code these six interview transcripts with codebook thematic analysis and check every quote in my findings draft.`
- `Label these 2,000 product reviews as price, quality, service or none, and show me how well the labels agree with mine.`

## Install

Claude Code:

```text
/plugin install researchzy-social --marketplace Researchzy/Researchzy-academic-skills
```

Codex:

```sh
codex plugin marketplace add Researchzy/Researchzy-academic-skills
codex plugin add researchzy-social@researchzy
```

## With Researchzy connected

Install the [`researchzy`](../researchzy) plugin and sign in, and the survey and psychometrics skills can find a scale's development and validation papers in Researchzy's index and read the number of items, the keyed items and the reported loadings from the paper itself; the path-model skill can find prior work for each hypothesised path. Everything else works without an account.

## Requirements

Python 3.10+ for the bundled scripts. The audit, item screen, qualitative ledger and text ledger need only the standard library. The psychometrics, path-model and topic-model steps use numpy, pandas, scipy, statsmodels and scikit-learn; a confirmatory factor analysis needs semopy or R with lavaan, installed only with your consent, and measurement invariance needs lavaan. On Linux, installing lavaan from CRAN compiles Fortran in its dependencies (gfortran); on Debian or Ubuntu, `apt-get install r-cran-lavaan` installs it ready-built. A step whose package is missing is reported as not run. The third-party notices are in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
