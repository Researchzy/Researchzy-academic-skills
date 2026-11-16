# Third-party components

## Skills adapted from Nature Skills (Apache-2.0)

Three skills of this plugin are derived from [Yuan1z0825/nature-skills](https://github.com/Yuan1z0825/nature-skills)
and distributed under the [Apache License 2.0](licenses/nature-skills-Apache-2.0.txt). Upstream
did not contain a NOTICE file at these revisions. Nature Skills is a third-party project; bundling
it does not imply endorsement by its authors or the journal Nature.

Each skill retains its upstream references, templates, scripts, tests and attribution except as
listed below. The files a skill loads from upstream's `nature-shared` are bundled in that skill's
own `shared/` directory, with the same layout as in `nature-shared`, so the links between them
are unchanged; `nature-shared` itself is not bundled. Upstream's Chinese `README.md` files are not
bundled; each skill's `README.md` is upstream's `README_EN.md`.

| Skill | Upstream skill | Upstream commit | Files bundled from `nature-shared` |
|---|---|---|---|
| `researchzy-stats-review` | `nature-statistics` | `c1a8e7bbcf86d82a268dc4a9980d36082b31fb2f` (2026-10-31) | `core/consistency-sweep.md`, `core/research-compliance.md`, `core/ethics.md`, `journal-formats/nature-machine-intelligence.md`, `scripts/check_consistency.py`, `tests/test_check_consistency.py` |
| `researchzy-data-availability` | `nature-data` | `c1a8e7bbcf86d82a268dc4a9980d36082b31fb2f` (2026-10-31) | `core/research-compliance.md`, `core/ethics.md`, `journal-formats/nature-machine-intelligence.md` |
| `researchzy-rebuttal` | `nature-response` | `c1a8e7bbcf86d82a268dc4a9980d36082b31fb2f` (2026-10-31) | `core/main-text-discipline.md`, `core/consistency-sweep.md`, `scripts/check_consistency.py`, `tests/test_check_consistency.py` |

### Researchzy modifications

The three skills, added on 2026-11-01 (version 1.5.0):

- Renamed: the skill name in `SKILL.md`, `manifest.yaml` and `agents/openai.yaml`,
  the titles, the READMEs, and the skill's own name in its references and tests.
- English only: the Chinese trigger words in the descriptions are removed, and
  references to upstream skills that are not bundled are removed or point to
  the Researchzy skills. In the bundled `shared/` copies, references to
  other skills and to the `nature-shared` directory point to the Researchzy skills
  and to the skill's `shared/` directory.
- `researchzy-stats-review`: `SKILL.md` accepts author notes in any language.
- `researchzy-data-availability`: `static/core/chinese-mode.md` and
  `references/chinese-author-alignment.md` are removed and replaced by a
  language-neutral rule in `SKILL.md`; the Chinese confirmation block is removed
  from `static/core/workflow.md` and the Chinese guidance lines from
  `references/statement-patterns.md`.
- `researchzy-rebuttal`: `references/chinese-author-alignment.md` is rewritten in
  English as `references/author-notes.md`; the Chinese wording of the
  decision-type question and the Chinese confirmation block are replaced by
  language-neutral author confirmation notes (`SKILL.md`, `static/core/workflow.md`,
  `references/intake-and-routing.md`, `references/response-structure.md`,
  `tests/unclear-decision-type.md`, `tests/evaluation-summary.md`).
- `researchzy-data-availability` and `researchzy-rebuttal`: the routers' path to the
  workflow is corrected to `static/core/workflow.md`.
- 2026-11-01 (version 1.6.1): the modification notice at the top of each skill's
  `SKILL.md` and `README.md` is a Markdown comment that points to this file, in
  place of a visible note. `researchzy-data-availability`: a comment in
  `manifest.yaml` no longer names Nature Skills.
- 2026-11-10 (version 2.0.0): the skills moved to the `researchzy-manuscript` plugin.

The upstream content and the bundled scripts are otherwise unchanged.

## researchzy-reference-check scripts

Two scripts of `skills/researchzy-reference-check` are derived from the `verify-refs` skill of
[Aperivue/medsci-skills](https://github.com/Aperivue/medsci-skills), commit
`4e7b3d08e0d17935644a0e281c944764da4b2601` (2026-11-10), distributed under the
[MIT License](licenses/medsci-skills-MIT.txt), Copyright (c) 2026 Aperivue. The skill directory
keeps the license as `scripts/LICENSE-MIT.txt`. medsci-skills is a third-party project; bundling
parts of it does not imply endorsement by its authors.

| File | Upstream file |
|---|---|
| `scripts/check_references.py` | `skills/verify-refs/scripts/verify_refs.py` |
| `scripts/quote_match.py` | `skills/verify-refs/scripts/_quote_match.py` |

Researchzy modifications (2026-11-10, version 2.0.0):

`check_references.py`:

- Kept from upstream: the BibTeX, TSV and reference-line parsers, the DOI, author-name and title
  comparison functions, the author cross-check, the doi.org handle lookup and the detection of
  duplicate identifiers.
- The verdicts are named `confirmed`, `mismatch`, `unconfirmed` and
  `identifier_not_registered`.
- The registry lookups are rewritten around one result type. The Crossref lookup also reads
  retraction, correction and update-notice links and the preprint relation; a DataCite lookup
  follows a DOI registered with another agency; an arXiv lookup handles `eprint` fields, arXiv
  URLs and arXiv DOIs; the PubMed lookup also reads retraction and erratum links. The OpenAlex
  lookup and the PubMed title search are removed, and a Crossref bibliographic search takes the
  place of the title search.
- An identifier that resolves to a work with another title is set aside, and the cited work is
  searched by title; the report then names both.
- A match by title alone also needs a year within one of the cited year; a rejected match is
  listed as a nearest real paper.
- The cited year is compared with the record's.
- Researchzy search results saved by the agent are merged (`--researchzy`), and the searches
  still worth making are written to `lookups.json`.
- Citations are located in LaTeX, Pandoc and numbered manuscripts, with their sentences; cited
  keys missing from the list and unused entries are reported.
- New inputs: LaTeX sources (`thebibliography`, or the `.bib` files they name) and PDF. LaTeX
  accents and brace-protected letters in BibTeX titles are read as plain text.
- Output goes to a folder: `references.json`, `report.md`, `lookups.json` and, for BibTeX,
  `fixes.bib`. Registry answers are cached, requests are paced per host and retried once, and
  no contact address is sent unless the user gives one.
- A placeholder ("in press", "forthcoming") is a flag and no longer changes the verdict, and is
  matched on word boundaries. The `_audit_truncated` field is no longer read; BibTeX's
  `and others` is.
- Entries with the same title and first author are reported as duplicates.
- Comments that referred to upstream's project conventions are reworded.

`quote_match.py`: the module's introductory comment is rewritten; the code is unchanged.

`check_claims.py`, `SKILL.md`, the reference files and the tests are Researchzy's own.

## researchzy-writing, researchzy-paper-review and researchzy-figures scripts

Added on 2026-11-12 (version 2.0.0). Their `SKILL.md` files, reference files and tests are
Researchzy's own; parts of three scripts are derived from the projects named above.

`skills/researchzy-writing/scripts/manuscript_check.py`:

- From [Aperivue/medsci-skills](https://github.com/Aperivue/medsci-skills), commit
  `4e7b3d08e0d17935644a0e281c944764da4b2601`, MIT License ([text](licenses/medsci-skills-MIT.txt),
  kept beside the script as `LICENSE-MIT.txt`):
  - `skills/write-paper/scripts/check_placeholders.py`: the placeholder patterns, the skipping of
    code fences and the reference-section pattern. Researchzy added its three typed placeholders
    and the unresolved LaTeX reference.
  - `skills/humanize/scripts/check_rewrite_fidelity.py`: the number pattern, the rule that tells a
    minus from a range, the binding of inequalities, the citation patterns and the word lists for
    direction. Researchzy replaced the alignment of the two texts with sentence pairing.
  - `skills/polish-language/scripts/lint_consistency.py`: the abbreviation rules and the approach
    to mixed US and UK spelling. The word lists, the separate scopes for abstract and main text
    and the guard for proper names are Researchzy's.
- From Nature Skills `nature-shared/scripts/check_consistency.py` (Apache-2.0, the copy bundled
  in `researchzy-stats-review`): the check for one value written at two precisions and the
  stripping of LaTeX comments.

`skills/researchzy-paper-review/scripts/quote_match.py` is the file of the same name in
`researchzy-reference-check`, unchanged, with its `LICENSE-MIT.txt`.

`skills/researchzy-figures/scripts/check_figure.py`: from
[Yuan1z0825/nature-skills](https://github.com/Yuan1z0825/nature-skills), commit
`a1a8220366e82ecd8584ea3d7f46cb3969f4b018` (2026-11-10),
`skills/nature-figure/scripts/audit_pdf_text.py`, Apache License 2.0
([text](licenses/nature-skills-Apache-2.0.txt), kept beside the script as
`LICENSE-APACHE-2.0.txt`): the tokenizer patterns, the text-showing operators and the matrix
helpers are taken as they are; the scan of text runs is rewritten to count only text inside
text objects and to keep the strings; the decoding of streams and the verdicts are Researchzy's.

## researchzy-statistics and researchzy-submission scripts

Added on 2026-11-13 (version 2.1.0). Their `SKILL.md` files, reference files and tests are
Researchzy's own; parts of four scripts are derived from
[Aperivue/medsci-skills](https://github.com/Aperivue/medsci-skills), commit
`4e7b3d08e0d17935644a0e281c944764da4b2601`, MIT License ([text](licenses/medsci-skills-MIT.txt),
kept beside each script as `LICENSE-MIT.txt`).

`skills/researchzy-statistics/scripts/rz_results.py` and `scripts/check_results.py`:

- `skills/analyze-stats/scripts/run_analysis.py`: the chunked SHA-256 of files and the idea of an
  execution record (inputs, environment, seed) checked afterwards for drift. Researchzy made the
  record a module that any analysis script imports, keeps a state per file, and reports an absent
  file as not checked.
- `skills/analyze-stats/scripts/check_generated_code.py`: the checks for a missing or unseeded
  random generator, numbers typed into the script as data, writing to an input file, and a
  two-sample t test without `equal_var`. Researchzy rewrote them on the syntax tree, added the
  checks for a global seed, resamplers without a generator and results not recorded, and left out
  the R, path, debugging and machine-learning checks.

`probe_design.py` and `power.py` are Researchzy's own.

`skills/researchzy-submission/scripts/check_package.py` and `scripts/check_anonymity.py`:

- `skills/sync-submission/scripts/check_asset_anonymization.py`: the patterns for document
  properties and tracked-change authors in Office files, the scan of every XML part, the pattern
  for home-folder paths, the list of program names that are not authors, and the reading of
  `pdfinfo` output. Researchzy matches program names exactly and leaves out the scan of figure
  scripts for institution words.
- `skills/sync-submission/scripts/check_credit_integrity.py`: the 14 CRediT terms, part of the
  map of near misses, and the rules that initials resolve to exactly one author and that every
  author has a role. Researchzy reads the roles from the authors' record.
- `skills/sync-submission/scripts/cover_letter_drift_check.py`: reading the counts of figures,
  tables, references and words that a cover letter states, skipping a quoted limit, and the title
  comparison. Researchzy added number words and sample sizes and leaves out supplementary items.
- `skills/sync-submission/scripts/check_disclosure_availability.py`: finding statements by
  heading synonyms and counting a placeholder as missing. The synonym lists and the reading of
  LaTeX and Word files are Researchzy's.
- `skills/sync-submission/scripts/check_wordcount_cap.py`: the scope of the main-text word count
  (what is left out and what is kept). The classification of sections is Researchzy's, and no
  journal profile is read.
- `skills/write-paper/scripts/build_title_page_affiliations.py`: numbering affiliations by first
  appearance and the marks on the author line. Researchzy reads JSON instead of YAML.

## researchzy-slides scripts

Added on 2026-11-13 (version 2.1.0). `SKILL.md`, the reference files, the tests and the Beamer
layout are Researchzy's own; parts of three scripts are derived from two projects.

From [Aperivue/medsci-skills](https://github.com/Aperivue/medsci-skills), commit
`4e7b3d08e0d17935644a0e281c944764da4b2601`, MIT License ([text](licenses/medsci-skills-MIT.txt),
kept beside the scripts as `LICENSE-MIT.txt`):

- `skills/present-paper/scripts/check_deck_budget.py`, in `scripts/slide_plan.py`: a slide budget
  per talk type with backup slides off the clock, the slack before an overrun, and the median and
  maximum words per slide. Researchzy checks the plan instead of the finished deck, with its own
  table of conventions and an explicit `# Backup` marker.
- `skills/present-paper/scripts/check_slide_tells.py`, in `scripts/slide_plan.py`: the list of
  titles that are filing labels (shortened, English only, matched word by word) and the reading of
  a PowerPoint file as a zip archive (slide order, notes through each slide's relationships, the
  test for text boxes without a size).
- `skills/present-paper/scripts/extract_pdf_figures.py`, in `scripts/paper_figure.py`: cropping one
  box, given as fractions of the page, from a page rendered with `pdftoppm`. Rendering with
  PyMuPDF, the manifest and the guard against overwriting are Researchzy's.

From [Yuan1z0825/nature-skills](https://github.com/Yuan1z0825/nature-skills), commit
`a1a8220366e82ecd8584ea3d7f46cb3969f4b018`,
`skills/nature-paper2ppt/scripts/audit_pptx_quality.py`, Apache License 2.0
([text](licenses/nature-skills-Apache-2.0.txt), kept beside the scripts as
`LICENSE-APACHE-2.0.txt`), in `scripts/slide_plan.py`: the bounds of shapes inside groups (offset
and scale), the threshold for a picture too small to read, and the facts read about media and
notes. Rotation and the alignment checks were left out.

`scripts/build_deck.py` is Researchzy's own.

## researchzy-grants and researchzy-latex

Added on 2026-11-13 (version 2.1.0). Both are Researchzy's own and contain no third-party code.
The log excerpts under `skills/researchzy-latex/tests/fixtures/` come from builds made for the
tests.

## researchzy-causal-inference scripts

Added on 2026-11-13 (version 2.2.0). `SKILL.md`, the reference files, the tests,
`probe_causal.py` and `check_causal.py` are Researchzy's own. `scripts/rz_results.py` and
`scripts/check_results.py` are copies of the files of the same name in `researchzy-statistics`,
unchanged, with their `LICENSE-MIT.txt` (see that skill's section above).

Parts of `scripts/causal_tools.py` are derived from
[Jill0099/causal-inference-mixtape](https://github.com/Jill0099/causal-inference-mixtape), commit
`5d3d938a18e7cd4992e2023aa309fc02c5008d66` (2026-08-12), MIT License
([text](licenses/causal-inference-mixtape-MIT.txt), Copyright (c) 2026 Jill0099, kept beside the
script as `LICENSE-MIT-causal_tools.txt`). causal-inference-mixtape is a third-party project;
bundling parts of it does not imply endorsement by its authors.

- `scripts/03_event_study.py`: `build_event_dummies` and `coefficient_path`, as `event_dummies`
  and `event_path`. Researchzy handles staggered cohorts and never-treated units, checks that the
  reference period lies strictly inside the window, and raises errors instead of assertions.
- `scripts/09_randomization_inference.py`: `ri_pvalue`, with the +1 rule and permutation by
  cluster. Researchzy accepts any statistic, adds strata and checks that treatment is constant
  within clusters.
- `scripts/08_matching_ipw.py`, the weighting block: the overlap share, trimming that drops units
  instead of clipping weights, and the share of the largest weight. Researchzy normalises weights
  within groups, adds the ATE, an optional doubly robust estimate, a balance table and bootstrap
  standard errors.
- `scripts/simulations/sim_twfe_staggered_bias.py`: `simulate`, as `simulate_staggered`, with fixed
  cohort sizes, an optional pre-trend and vectorised draws.
