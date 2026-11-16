# Researchzy Manuscript plugin

Version 2.2.0. Thirteen skills for the manuscript and what surrounds it: analysis, causal inference, writing, figures, checks, submission, talks, grants and revision. They run on your machine and work on the files you give them; no account is needed.

| User goal | Skill | Result |
|---|---|---|
| Plan, draft or revise an empirical paper from your own results | `researchzy-writing` | A claim ledger, a gap report, an outline, the draft, and a check of numbers, placeholders and citation keys |
| Figures from data, or a check of a figure file | `researchzy-figures` | One script per figure, PDF and PNG at the venue's width, and a check of size, fonts and colours |
| A critical review before submission, or a referee report | `researchzy-paper-review` | Findings with quotes from the manuscript and minimal fixes, and two readiness verdicts |
| Are the references real and correct, and do the cited papers support the text | `researchzy-reference-check` | A verdict and evidence per reference, a corrected `.bib`, and verified quotes for checked claims |
| Statistical reporting of a manuscript | `researchzy-stats-review` | Issues by severity, ready-to-paste Statistical analysis text, and author questions |
| Data and Code Availability statements | `researchzy-data-availability` | A ready-to-paste statement, repository and citation actions, and missing-information flags |
| Responses to reviewers and revision packages | `researchzy-rebuttal` | A master tracker, one response per reviewer, a cover letter, and optional LaTeX files |
| Analysis of your own data, and sample size or power before a study | `researchzy-statistics` | An analysis plan, a script you keep, `results.json` with effect sizes and intervals, Results and Statistical analysis text checked against it |
| A causal effect from observational data: difference-in-differences, instrumental variables, regression discontinuity, panel, synthetic control or weighting | `researchzy-causal-inference` | A probe of the data's shape and a route, the estimand and assumption written first, a robust headline estimator with the traditional one beside it, the diagnostics each design needs, every specification recorded, a robustness table, and text checked against `results.json` |
| A submission package checked against the venue's instructions | `researchzy-submission` | Cover letter, title page, highlights and declarations from your facts, and a check of limits, required statements, agreement across documents and anonymity |
| A LaTeX paper that builds cleanly and a source archive | `researchzy-latex` | A short list of real build problems, mechanical fixes with a check that the content did not change, a move into the venue's template, and a tested source archive |
| Slides for a talk or a journal club on a paper | `researchzy-slides` | A slide plan sized to the time, the paper's own figures, Beamer and PDF (PowerPoint too when python-pptx is installed), speaker notes, and a check that every number comes from the paper |
| A grant proposal against a funder's call | `researchzy-grants` | A requirements record quoted from the call, the aims page first, the proposal, and a check of sections, limits, criteria, aims, timeline and budget |

Example prompts:

- `Draft the Results and Discussion from these tables, and mark what is missing.`
- `Make a two-panel figure from trial.csv for a single Nature column and check it.`
- `Review this manuscript the way its reviewers will before I submit it.`
- `Check the references in main.tex: are they real, do the DOIs belong to them, and is anything retracted?`
- `Audit the statistical reporting of my manuscript and draft the Statistical analysis section.`
- `Draft a Data and Code Availability statement for our RNA-seq data and analysis code.`
- `Here are the editor's letter and the reviewers' comments; draft the point-by-point responses.`
- `Analyse collagen.csv: does each dose lower collagen compared with control? Then how many animals per group do I need next time?`
- `Counties adopted the policy in different years; did it raise employment? Estimate the effect and check the assumptions.`
- `Prepare my submission to this journal and check it against the instructions I pasted.`
- `My paper stopped compiling; get it building without changing the text, then pack it for arXiv.`
- `Make 10 minutes of slides on this paper for our journal club.`
- `Draft my application to this call from my notes and check it against the call.`

## With Researchzy connected

The reference check compares references with public registries (Crossref, doi.org, DataCite, arXiv, PubMed) on its own. Install the [`researchzy`](../researchzy) plugin and sign in, and it also finds references that have no DOI in Researchzy's index, and can check that a cited paper supports the sentence that cites it, with a quote and a page. The paper review then tests claims of novelty against real papers, the writing skill can find and read the papers it cites, a power calculation can take its effect size from a prior study's full text, a causal estimate can be compared with published estimates from the same design, the slides can start from a DOI, the grant's background can rest on real papers, and the submission skill can suggest reviewers from the authors of related papers.

## Requirements

Python 3.10+ for the bundled scripts. The optional packages are listed in `requirements.txt`; every script runs without them and says what it could not do. Reading a PDF needs PyMuPDF. Drawing figures needs matplotlib, and the figure checker compares colours when Pillow is installed. Statistical analysis needs scipy, and statsmodels for models. Causal inference needs numpy, pandas and statsmodels; regression discontinuity also needs rdrobust and rddensity (GPL-licensed, installed only with your consent). Slides and LaTeX builds need a TeX distribution with `latexmk`; slides write PowerPoint when python-pptx is installed, and PDF checks use Poppler's `pdfinfo` and `pdffonts` when present. The rebuttal tests need pytest. Pinned upstream sources, licenses, and Researchzy's modifications are recorded in the [third-party notices](THIRD_PARTY_NOTICES.md).
