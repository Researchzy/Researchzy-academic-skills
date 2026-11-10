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
