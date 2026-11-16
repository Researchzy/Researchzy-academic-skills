# Changelog

## 2.2.0 (2026-11-16)

Six new skills and two new plugins: `researchzy-evidence` for evidence synthesis and `researchzy-language` for translation and polishing. Like the rest, they carry no facts that expire: risk-of-bias tools, registry fields and journal conventions come from the files you supply or pages read in the session, with their source and date.

- New `researchzy-systematic-review` (plugin `researchzy-evidence`): a systematic review of one question, from a protocol with coded criteria to a PRISMA 2020 flow. Searches of Researchzy's index, PubMed, ClinicalTrials.gov and your own database exports are logged with their dates and counts, and a search that exported fewer records than the source reported is flagged. Duplicates are merged on identifiers and offered as pairs on similar titles; every exclusion carries a protocol code and a quote found in the record; screening is calibrated against a sample you screen yourself (Cohen's kappa and include recall). Every number of the flow is computed from the per-record ledger.
- New `researchzy-risk-of-bias` (plugin `researchzy-evidence`): risk of bias per study, result and domain with a tool registered from its official file or page; no tool text is bundled. Every judgement has a quote that a script finds in the saved full text, or says that the paper gives no information and where you looked; the overall judgement follows the tool's rule. Traffic-light and summary plots, and a GRADE summary of findings with a reason and the studies behind every downgrade.
- New `researchzy-meta-analysis` (plugin `researchzy-evidence`): effect sizes from an extraction table with every conversion declared, refusals for a study counted twice, mixed change and final values, cluster trials without an ICC and silently corrected zero cells; random effects with REML, Hartung–Knapp and a prediction interval; heterogeneity; forest and funnel plots; small-study tests only with ten or more studies; and Results text checked against `results.json`.
- New `researchzy-causal-inference` (plugin `researchzy-manuscript`): difference-in-differences (2×2, staggered adoption with Callaway–Sant'Anna as the headline and TWFE beside it, event studies with a sensitivity analysis), instrumental variables with the Anderson–Rubin set, regression discontinuity, panel fixed effects, basic synthetic control and propensity weighting. A probe reads the data's shape and gives one of four outcomes; every specification is recorded; a script checks the diagnostics, the clustering, the headline estimator and the causal verbs in the text.
- New `researchzy-translate` (plugin `researchzy-language`): academic translation between Chinese and English, or another pair, with the agent's own model. The glossary is agreed first; formulas, LaTeX and citations are masked so they cannot change; a script compares numbers, dates, citations, placeholders and terms unit by unit and writes a side-by-side table.
- New `researchzy-polish` (plugin `researchzy-language`): language-only polishing at an agreed level, with a reason for every edit and a redline. A script checks that numbers, citations, cross-references, protected terms and each sentence's claim strength did not change, and that the change log matches the real edits. Optional profiles of your own style or of a target journal's recent papers describe; they do not prescribe.
- `researchzy-statistics`: a printed minus sign must now match the sign of the recorded value; the ledger keeps the numbers of dropped analyses; the record and check scripts can be extended by other skills, which carry identical copies.
- `researchzy` routes to the new skills; `researchzy-literature-review` and `researchzy-statistics` hand systematic reviews, meta-analyses and causal identification to them.

## 2.1.0 (2026-11-13)

Seven new skills. None of them carries facts that expire, such as journal fees, impact factors, funder or conference page limits, deadlines or templates: those come from the files and pages you supply, or from registry lookups made in the session, with their source and date, and what could not be checked is reported as not checked.

- New `researchzy-citation-finder` (plugin `researchzy`): finds real papers for the sentences of a draft that need a citation, including the `[Citation needed: …]` placeholders `researchzy-writing` leaves. Every search is logged per sentence; a paper is offered only after its abstract or full text was read, with a quote that a script finds in the saved text; a sentence with a number, a comparison or a causal claim needs the full text. Writes a citation map and `new-references.bib` without touching your `.bib`, and says so when nothing in the index supports a sentence.
- New `researchzy-find-journal` (plugin `researchzy`): a shortlist of journals or conferences built from where papers like yours and your own references were published, each venue checked in Crossref and DOAJ (no key needed), with every fact sourced and dated and a list of what to confirm on the venue's site. Bands with reasons, no acceptance probability, and a plan for the next venue after a rejection.
- New `researchzy-statistics` (plugin `researchzy-manuscript`): analyses your data from a plan written before any test. The method follows the design (paired, repeated, clustered or technical replicates), every test is recorded with its effect size and interval, families of tests are corrected, and a script checks each number in your Results text against the record. Sample size and power need a sourced effect size and come as a range.
- New `researchzy-slides` (plugin `researchzy-manuscript`): a talk or a journal-club presentation from a paper, sized to the time, with the paper's own figures cropped from its PDF and recorded, speaker notes, and a check that flags any number on a slide or in the notes that is not in the paper. Writes Beamer and PDF, and PowerPoint when python-pptx is installed.
- New `researchzy-grants` (plugin `researchzy-manuscript`): a grant proposal written against the call you supply. Requirements are recorded with quotes that a script finds in the call; the aims page comes first; a script checks sections, limits, criteria coverage, aims with their risks and fallbacks, the timeline and the budget arithmetic. Preliminary data, publications, partners and amounts are never invented.
- New `researchzy-submission` (plugin `researchzy-manuscript`): cover letter, title page, highlights and declarations from the facts you give, then a check against the limits you paste from the venue's instructions, of agreement across documents (title, author order, grant numbers, ethics and registration IDs), of a letter that repeats the abstract, and, for blind review, of names, affiliations, self-citations, comments and file properties.
- New `researchzy-latex` (plugin `researchzy-manuscript`): builds a LaTeX paper with the engine and bibliography tool it uses, turns the log into a short list of real problems, fixes only mechanical ones with a snapshot that proves no label, citation, figure or text changed, moves a paper into a venue's kit you supply, and packs a source archive that is rebuilt to prove it compiles.
- `researchzy` routes to the new skills.

## 2.0.0 (2026-11-10)

- **Three plugins instead of one.** `researchzy` (search, library, PDFs and literature reviews) is the only one that connects to Researchzy and asks you to sign in. `researchzy-reading` (`researchzy-download`, `researchzy-deep-read`, `researchzy-paper-card`) and `researchzy-manuscript` (`researchzy-reference-check`, `researchzy-stats-review`, `researchzy-data-availability`, `researchzy-rebuttal`) need no account and use Researchzy when `researchzy` is installed and connected. If you had `researchzy` 1.x, install the other two to keep those skills.
- New `researchzy-literature-review`: a literature review from papers in Researchzy's index. It confirms the questions with you, searches in five passes (relevance, foundational, recent, earlier reviews, contrary results) and logs every query with its counts, screens with reasons, reads the core papers in full, and writes a synthesis by theme with a comparison table, gaps, `references.bib` and a search log. A ledger script checks that every citation is an included paper that was read. Needs a Researchzy account.
- New `researchzy-reference-check`: checks every reference of a manuscript or `.bib` file against Crossref, the doi.org registry, DataCite, arXiv and PubMed, and against Researchzy for references the registries do not settle. It reports references whose identifier does not exist, a DOI that belongs to another paper, wrong authors or year, retractions and corrections, duplicates and placeholders, and writes a corrected `.bib`. An optional claim check verifies that each cited paper supports the sentence citing it, with a quote the script finds in the source. The registry check works without a Researchzy account.
- New `researchzy-ideas` (plugin `researchzy`): generate research ideas, sharpen a hypothesis or judge an idea you already have. Each idea is a card with the result that would refute it; novelty is checked with logged searches of Researchzy's index and the closest works are named; a ledger marks an idea recommended only when the checks are in the record. No total score.
- New `researchzy-writing` (plugin `researchzy-manuscript`): plan, draft or revise an empirical paper from your own results, with a claim ledger, a gap report with typed placeholders, an outline with a word budget and evidence-first drafting. A script checks numbers, placeholders and citation keys, and what a revision changed.
- New `researchzy-figures` (plugin `researchzy-manuscript`): profile the data, choose a chart it can support, draw one script per figure at the venue's width, and check the exported PDF or PNG: size, smallest font at print scale, colour separation for colour-blind readers and in grayscale. The checker also reads figures made elsewhere.
- New `researchzy-paper-review` (plugin `researchzy-manuscript`): review a manuscript before submission, or draft a referee report. Findings quote the manuscript, a script confirms the quotes and that the verdicts do not contradict the findings, and there is no score.
- `researchzy` hands each task to the skill that fits and names the plugin it comes with.

## 1.6.1 (2026-11-01)

- Skill pages are shorter: source and license details for third-party components are kept in `THIRD_PARTY_NOTICES.md`.
- `researchzy-paper-card` no longer lists workflows that are not part of this plugin.

## 1.6.0 (2026-11-01)

First public release as **Researchzy Academic Skills**.

- The plugin id and its marketplace are both `researchzy`: install `researchzy@researchzy` in Claude Code or Codex.
- `researchzy-literature` is renamed `researchzy` and becomes the entry point: it searches and manages papers itself and hands every other task to the skill that fits. Prompts and hosts that name `researchzy-literature` must use the new name.
- Claude Code support: a repository marketplace (`.claude-plugin/marketplace.json`) and a plugin manifest. Claude Code signs in with its own client metadata document.
- Licensed under Apache-2.0. `researchzy-download` is under the MIT License.
- The other skills only point to `researchzy` instead of `researchzy-literature`.

## 1.5.0

- New `researchzy-download`: full text of identified papers from the PDFs Researchzy holds, open-access copies (PMC, Unpaywall, openly licensed publisher PDFs, arXiv) or the user's own Elsevier, Springer Nature or IEEE API keys, with every attempt in `manifest.json`. Needs Node.js 22+.
- New `researchzy-deep-read`, `researchzy-stats-review`, `researchzy-data-availability` and `researchzy-rebuttal`.
- `nature-paper-card` is renamed `researchzy-paper-card`; `nature-reader` and `nature-shared` are no longer bundled.

## 1.4.0

- New `create_pdf_upload` tool: adds a local PDF file to a library paper that has none.

## 1.3.0

- Papers whose PDF Researchzy can show link to the Researchzy reader (`readerUrl`); `add_paper_to_library` reports `hasReadablePdf`.

## 1.2.0

- The literature skill is renamed `researchzy-literature`.

## 1.1.0

- New `create_collection` tool for personal collections.

## 1.0.1

- The MCP server is named `researchzy`, so hosts list the tools under Researchzy.
