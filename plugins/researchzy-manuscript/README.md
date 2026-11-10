# Researchzy Manuscript plugin

Version 2.0.0. Four skills for preparing, checking and revising a manuscript. They run on your machine and work on the files you give them; no account is needed.

| User goal | Skill | Result |
|---|---|---|
| Are the references real and correct, and do the cited papers support the text | `researchzy-reference-check` | A verdict and evidence per reference, a corrected `.bib`, and verified quotes for checked claims |
| Statistical reporting of a manuscript | `researchzy-stats-review` | Issues by severity, ready-to-paste Statistical analysis text, and author questions |
| Data and Code Availability statements | `researchzy-data-availability` | A ready-to-paste statement, repository and citation actions, and missing-information flags |
| Responses to reviewers and revision packages | `researchzy-rebuttal` | A master tracker, one response per reviewer, a cover letter, and optional LaTeX files |

Example prompts:

- `Check the references in main.tex: are they real, do the DOIs belong to them, and is anything retracted?`
- `Audit the statistical reporting of my manuscript and draft the Statistical analysis section.`
- `Draft a Data and Code Availability statement for our RNA-seq data and analysis code.`
- `Here are the editor's letter and the reviewers' comments; draft the point-by-point responses.`

## With Researchzy connected

The reference check compares references with public registries (Crossref, doi.org, DataCite, arXiv, PubMed) on its own. Install the [`researchzy`](../researchzy) plugin and sign in, and it also finds references that have no DOI in Researchzy's index, and can check that a cited paper supports the sentence that cites it, with a quote and a page.

## Requirements

Python 3.10+ for the bundled scripts; reading a PDF needs PyMuPDF from `requirements.txt`. The rebuttal tests need pytest. Pinned upstream sources, licenses, and Researchzy's modifications are recorded in the [third-party notices](THIRD_PARTY_NOTICES.md).
