# Third-party components

## Skills adapted from Nature Skills (Apache-2.0)

Five skills are derived from [Yuan1z0825/nature-skills](https://github.com/Yuan1z0825/nature-skills)
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
| `researchzy-paper-card` | `nature-paper-card` | `c4e4c99fbeaf0168cda090f8739e1508017a610e` (2026-09-10) | `core/terminology-ledger.md` |
| `researchzy-deep-read` | `nature-paper-xray` | `c1a8e7bbcf86d82a268dc4a9980d36082b31fb2f` (2026-10-31) | `core/paper-type-taxonomy.md` |
| `researchzy-stats-review` | `nature-statistics` | `c1a8e7bbcf86d82a268dc4a9980d36082b31fb2f` (2026-10-31) | `core/consistency-sweep.md`, `core/research-compliance.md`, `core/ethics.md`, `journal-formats/nature-machine-intelligence.md`, `scripts/check_consistency.py`, `tests/test_check_consistency.py` |
| `researchzy-data-availability` | `nature-data` | `c1a8e7bbcf86d82a268dc4a9980d36082b31fb2f` (2026-10-31) | `core/research-compliance.md`, `core/ethics.md`, `journal-formats/nature-machine-intelligence.md` |
| `researchzy-rebuttal` | `nature-response` | `c1a8e7bbcf86d82a268dc4a9980d36082b31fb2f` (2026-10-31) | `core/main-text-discipline.md`, `core/consistency-sweep.md`, `scripts/check_consistency.py`, `tests/test_check_consistency.py` |

### Researchzy modifications

`researchzy-paper-card`:

- 2026-09-13: `SKILL.md` gained optional Researchzy retrieval, a limited-source
  classification fallback, and optional references to workflows outside this
  bundle. Researchzy's own source-acquisition reference resides in
  `skills/researchzy/references/researchzy-source.md`.
- 2026-09-18: README tutorial links point to the pinned upstream repository
  because those tutorials are not bundled.
- 2026-11-01 (version 1.5.0): renamed from `nature-paper-card` (`SKILL.md`,
  `manifest.yaml`, `agents/openai.yaml`, `evals/evals.json`, the READMEs, the
  docstring of `scripts/prepare_paper.py` and a module name in
  `tests/test_prepare_paper.py`); `manifest.yaml` and `static/core/principles.md`
  point to the bundled Terminology Ledger, `SKILL.md` has a shorter description,
  and `README.md` no longer points to upstream skills that are not bundled. `nature-reader` is no longer bundled:
  `SKILL.md` lists it among the workflows that are not bundled and points to
  `researchzy-download` for full text.

The four skills added on 2026-11-01 (version 1.5.0):

- Renamed: the skill name in `SKILL.md`, `manifest.yaml` and `agents/openai.yaml`,
  the titles, the READMEs, and the skill's own name in its references and tests.
- English only: the Chinese trigger words in the descriptions are removed, and
  references to upstream skills this plugin does not bundle are removed or point to
  the bundled Researchzy skills. In the bundled `shared/` copies, references to
  other skills and to the `nature-shared` directory point to the Researchzy skills
  and to the skill's `shared/` directory.
- `researchzy-deep-read`: `SKILL.md` gained a Researchzy source-acquisition
  section and a shorter description; its Boundaries and Output discipline no longer name other skills or a
  language; one sentence of `references/evidence-boundary.md` likewise.
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
- 2026-11-01 (version 1.6.0): `researchzy-paper-card` and `researchzy-deep-read`
  (`SKILL.md`, `README.md`) name `researchzy`, the renamed entry skill, where they
  named `researchzy-literature`, and link to its `references/researchzy-source.md`.
- 2026-11-01 (version 1.6.1): the modification notice at the top of each skill's
  `SKILL.md` and `README.md` is a Markdown comment that points to this file, in
  place of a visible note. `researchzy-paper-card`:
  `README.md` no longer links to the upstream tutorial, and `SKILL.md` no longer
  lists upstream workflows that are not bundled (`nature-reader`,
  `nature-reviewer`, `nature-literature-pipeline`, `nature-paper2ppt`).
  `researchzy-data-availability`: a comment in `manifest.yaml` no longer names
  Nature Skills.

The upstream content and the bundled scripts are otherwise unchanged.

## researchzy-download

`skills/researchzy-download` is derived from `nature-downloader` in
[Yuan1z0825/nature-skills](https://github.com/Yuan1z0825/nature-skills),
commit `c1a8e7bbcf86d82a268dc4a9980d36082b31fb2f` (2026-10-31; the skill last
changed in `3981da9877237d36a21705f314b2b66e41ca59e5`, 2026-10-20). That skill is
distributed under its own [MIT License](licenses/nature-downloader-MIT.txt),
Copyright (c) 2026 baihe26, which the skill directory keeps as `LICENSE`.

Researchzy modifications (2026-11-01):

- Renamed to `researchzy-download`, and every file is English only.
- Kept only the open-access and publisher-API routes. Removed the CNKI route and
  every Chinese-language source, the Web of Science, institutional-browser,
  Chrome DevTools and supporting-information routes, the automatic verification
  module (`anti-bot.mjs`), the school configuration (`configure_school.py`,
  `src/`, `data/school*`), the browser helper scripts, the examples, the upstream
  READMEs, banner and development notes.
- `scripts/batch_download.mjs`: rewritten for those routes (DOI list, exact title,
  known URL); a title shared by several Crossref works is reported as
  `metadata_ambiguous` with its candidates instead of taking the first match.
- `scripts/lib/open-access.mjs`: PMC copies come from NCBI's PMC Article Datasets
  on AWS, because the PMC OA web service (`oa.fcgi`) no longer answers.
- `scripts/lib/routing.mjs`, `status-codes.mjs`, `provider-utils.mjs`,
  `publisher-providers.mjs`, `metadata.mjs`: reduced to the remaining routes and
  statuses; English-only content checks.
- `SKILL.md`, `manifest.yaml`, `agents/openai.yaml` and the tests rewritten
  accordingly; Researchzy's own PDFs are tried first.
- 2026-11-01 (version 1.6.0): `SKILL.md` names `researchzy`, the renamed entry
  skill, where it named `researchzy-literature`.
