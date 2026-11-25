# Researchzy Clinical plugin

Version 2.3.0. Six skills for clinical research: protocols, trial-registry checks, reporting checklists, survival analysis, diagnostic accuracy and prediction models, and case reports. They run on your machine and work on the files you give them. No checklist, registry field list, form or regulation is built in: each comes from the file or page you supply, recorded with its version, source and date. None of the skills gives clinical advice.

| User goal | Skill | Result |
|---|---|---|
| A trial or observational study protocol | `researchzy-protocol` | One set of core items behind the protocol, the registry entry and the analysis plan, a check that the three agree item by item, a table of variable definitions each with a source, a target-trial table for observational comparisons, and the institution's Word form filled without breaking its styles |
| A trial report compared with its registry record, or a search for earlier trials | `researchzy-registry-check` | The ClinicalTrials.gov record saved as returned, the paper matched to the right trial first, outcomes, time points, enrolment and dates compared item by item with both texts side by side, registration timing from the first-submitted date, and the record version read |
| The reporting checklist a journal asks for | `researchzy-reporting-checklist` | The checklist registered from the file you downloaded, every item with a page (and lines) and a quote a script finds there, reasons for every item that does not apply, suggestions that hold no invented fact, an upload list and a separate list of gaps |
| A survival analysis | `researchzy-survival` | A probe of event codes, times and ids before any fit, Kaplan-Meier with numbers at risk, medians or "not reached", log-rank, Cox with Efron ties, a proportional-hazards test and plot, RMST, cumulative incidence, and Results text checked against the record |
| Diagnostic accuracy or a clinical prediction model | `researchzy-diagnostic-accuracy` | A leakage and verification probe, exact intervals and likelihood ratios, DeLong AUC and paired comparisons, calibration, optimism correction that reruns the whole pipeline, decision curves, thresholds that never come from the test set, and predictive values only with a sourced prevalence |
| A case report | `researchzy-case-report` | A scan for identifiers before the notes are read, a timeline in relative time with a source for every row, a similar-cases table with checked quotes from logged searches, a consent statement built from the record, and a check that no identifier remains, which reports categories and lines but never the values |

Example prompts:

- `Draft the protocol, registry entry and analysis plan for this trial idea, and check that they agree.`
- `Compare my trial paper with its ClinicalTrials.gov record before I submit.`
- `Fill the STROBE checklist the journal asks for, with page and line numbers from my submission PDF.`
- `Analyse overall survival by arm in this cohort and check my Results paragraph.`
- `Validate this prediction model on the test split and check that nothing leaked from the development data.`
- `Write a case report from these de-identified notes and check that no identifier is left.`

## Install

Claude Code:

```text
/plugin install researchzy-clinical --marketplace Researchzy/Researchzy-academic-skills
```

Codex:

```sh
codex plugin marketplace add Researchzy/Researchzy-academic-skills
codex plugin add researchzy-clinical@researchzy
```

## With Researchzy connected

Install the [`researchzy`](../researchzy) plugin and sign in, and the protocol skill can find sources for variable definitions in Researchzy's index, the registry check can read the full text of the paper and find published reports of earlier trials, the diagnostic-accuracy skill can find the target population's prevalence and a published model's coefficients, and the case report can find similar cases with every search logged. Everything else works without an account; reading ClinicalTrials.gov needs web access but no key.

## Requirements

Python 3.10+ for the bundled scripts. The protocol, registry, checklist and case-report scripts need only the standard library; filling a Word form needs python-docx. The survival and diagnostic-accuracy analyses use numpy, scipy, statsmodels, scikit-learn and matplotlib. A step whose package or tool is missing is reported as not run. The third-party notices are in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
