# Researchzy Thesis plugin

Version 2.3.0. Four skills for a degree thesis, from the proposal to the defence. They run on your machine and work on the files you give them; the school's template and rules are read from the school's own documents and never built in. The proposal's literature search needs the [`researchzy`](../researchzy) plugin and a Researchzy account.

| User goal | Skill | Result |
|---|---|---|
| A thesis proposal, or a research proposal for a PhD application | `researchzy-thesis-proposal` | The school's template recorded with quotes, research questions you choose, a literature basis of real papers from a logged search, a question-by-method matrix, a feasibility plan and a timeline, written under the template's own sections and checked by a script |
| A thesis assembled from published papers, in the school's format | `researchzy-thesis-build` | The school's format rules recorded with quotes, a chapter plan, the papers placed in a copy of the school's Word template or its LaTeX class without rewording them, a reuse table, and the PDF and the `.docx` measured against the rules |
| The whole thesis checked before review or the defence | `researchzy-thesis-audit` | Abbreviations, key numbers, sample sizes across tables, figure and table callouts, citations against the reference list, hypotheses against results, the two abstracts, and the blind-review copy, each reported as pass, fail or not checked |
| Preparing the defence | `researchzy-defense` | Questions tied to pages of the thesis, starting from the reviewers' reports; answer outlines whose pages, numbers and quotes a script finds in the thesis; a mock defence one question at a time; a revision list |

Example prompts:

- `Write my thesis proposal to this template from my department. My direction is remote work and team trust; here are my supervisor's twelve references.`
- `Build my thesis from these two published papers in the university's Word template, then check it against the formatting rules in this PDF.`
- `Check my thesis for inconsistencies before it goes to blind review. Here are the chapters, the two abstracts and the blind copy.`
- `My defence is next week. Here are the thesis and the two review reports: give me the likely questions and run a mock defence.`

The skills read Chinese and English theses. They do not lower a similarity score or an "AI rate", and they do not rewrite published text.

## Install

Claude Code:

```text
/plugin install researchzy-thesis --marketplace Researchzy/Researchzy-academic-skills
```

Codex:

```sh
codex plugin marketplace add Researchzy/Researchzy-academic-skills
codex plugin add researchzy-thesis@researchzy
```

## With Researchzy connected

Install the [`researchzy`](../researchzy) plugin and sign in, and the proposal's literature basis comes from Researchzy's index of about 250 million papers, with every search logged and every cited paper one the search returned; without it the proposal uses only the references you supply and says so. Thesis assembly can then fill the reuse table from each published paper's record, and defence preparation can find recent papers close to the thesis that its reference list does not have.

## Requirements

Python 3.10+ for the bundled scripts, which use the standard library. Measuring a PDF needs PyMuPDF; rendering a sample reference list needs pandoc. A check whose tool is missing is reported as not checked. The third-party notices are in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
