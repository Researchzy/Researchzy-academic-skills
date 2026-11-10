# Changelog

## 2.0.0 (2026-11-10)

- **Three plugins instead of one.** `researchzy` (search, library, PDFs and literature reviews) is the only one that connects to Researchzy and asks you to sign in. `researchzy-reading` (`researchzy-download`, `researchzy-deep-read`, `researchzy-paper-card`) and `researchzy-manuscript` (`researchzy-reference-check`, `researchzy-stats-review`, `researchzy-data-availability`, `researchzy-rebuttal`) need no account and use Researchzy when `researchzy` is installed and connected. If you had `researchzy` 1.x, install the other two to keep those skills.
- New `researchzy-literature-review`: a literature review from papers in Researchzy's index. It confirms the questions with you, searches in five passes (relevance, foundational, recent, earlier reviews, contrary results) and logs every query with its counts, screens with reasons, reads the core papers in full, and writes a synthesis by theme with a comparison table, gaps, `references.bib` and a search log. A ledger script checks that every citation is an included paper that was read. Needs a Researchzy account.
- New `researchzy-reference-check`: checks every reference of a manuscript or `.bib` file against Crossref, the doi.org registry, DataCite, arXiv and PubMed, and against Researchzy for references the registries do not settle. It reports references whose identifier does not exist, a DOI that belongs to another paper, wrong authors or year, retractions and corrections, duplicates and placeholders, and writes a corrected `.bib`. An optional claim check verifies that each cited paper supports the sentence citing it, with a quote the script finds in the source. The registry check works without a Researchzy account.
- `researchzy` hands literature reviews and reference checks to the new skills, and names the plugin each skill comes with.

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
