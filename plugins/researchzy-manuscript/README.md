# Researchzy Manuscript plugin

Version 2.0.0. Seven skills for writing, checking and revising a manuscript. They run on your machine and work on the files you give them; no account is needed.

| User goal | Skill | Result |
|---|---|---|
| Plan, draft or revise an empirical paper from your own results | `researchzy-writing` | A claim ledger, a gap report, an outline, the draft, and a check of numbers, placeholders and citation keys |
| Figures from data, or a check of a figure file | `researchzy-figures` | One script per figure, PDF and PNG at the venue's width, and a check of size, fonts and colours |
| A critical review before submission, or a referee report | `researchzy-paper-review` | Findings with quotes from the manuscript and minimal fixes, and two readiness verdicts |
| Are the references real and correct, and do the cited papers support the text | `researchzy-reference-check` | A verdict and evidence per reference, a corrected `.bib`, and verified quotes for checked claims |
| Statistical reporting of a manuscript | `researchzy-stats-review` | Issues by severity, ready-to-paste Statistical analysis text, and author questions |
| Data and Code Availability statements | `researchzy-data-availability` | A ready-to-paste statement, repository and citation actions, and missing-information flags |
| Responses to reviewers and revision packages | `researchzy-rebuttal` | A master tracker, one response per reviewer, a cover letter, and optional LaTeX files |

Example prompts:

- `Draft the Results and Discussion from these tables, and mark what is missing.`
- `Make a two-panel figure from trial.csv for a single Nature column and check it.`
- `Review this manuscript the way its reviewers will before I submit it.`
- `Check the references in main.tex: are they real, do the DOIs belong to them, and is anything retracted?`
- `Audit the statistical reporting of my manuscript and draft the Statistical analysis section.`
- `Draft a Data and Code Availability statement for our RNA-seq data and analysis code.`
- `Here are the editor's letter and the reviewers' comments; draft the point-by-point responses.`

## With Researchzy connected

The reference check compares references with public registries (Crossref, doi.org, DataCite, arXiv, PubMed) on its own. Install the [`researchzy`](../researchzy) plugin and sign in, and it also finds references that have no DOI in Researchzy's index, and can check that a cited paper supports the sentence that cites it, with a quote and a page. The paper review then tests claims of novelty against real papers, and the writing skill can find and read the papers it cites.

## Requirements

Python 3.10+ for the bundled scripts; reading a PDF needs PyMuPDF from `requirements.txt`. Drawing figures needs matplotlib, and the figure checker compares colours when Pillow is installed. The rebuttal tests need pytest. Pinned upstream sources, licenses, and Researchzy's modifications are recorded in the [third-party notices](THIRD_PARTY_NOTICES.md).
