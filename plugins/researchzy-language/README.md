# Researchzy Language plugin

Version 2.2.0. Two skills for the language of a paper: academic translation and language polishing. They run on your machine, use your agent's own model, and work on the files you give them; no account is needed.

| User goal | Skill | Result |
|---|---|---|
| A translation of a manuscript section or a paper, Chinese to English and back or another pair | `researchzy-translate` | A glossary agreed first, the translation with LaTeX, maths and citations masked so they cannot change, a check of numbers, dates, citations, placeholders and terms unit by unit, and a side-by-side table |
| Polished academic English that says the same thing | `researchzy-polish` | The polished text at the level you choose, a change log with a reason for every edit, a redline, questions for you where a claim itself looks wrong, and a check that numbers, citations, protected terms and the strength of every claim did not change |

Example prompts:

- `Translate the Methods section of my Chinese manuscript into academic English and keep every number and citation.`
- `Polish the English of this Discussion paragraph; I'm not a native speaker. Don't change what it says.`

## With Researchzy connected

Install the [`researchzy`](../researchzy) plugin and sign in, and the translation can check which of two English candidates for a term the literature uses, and the polishing can describe how recent papers in your target journal are written, from abstracts the index returns, with the query and date recorded.

## Requirements

Python 3.10+ for the bundled scripts, which need only the standard library. A LaTeX redline of the polishing needs `latexdiff` when you want one. The third-party notices are in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
