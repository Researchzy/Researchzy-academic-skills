# Researchzy plugin

Version 1.7.0 connects your agent to Researchzy through nine MCP tools: `search_papers`, `get_paper`, `list_collections`, `create_collection`, `list_library_papers`, `add_paper_to_library`, `get_pdf_download`, `create_pdf_upload` and `get_profile`. It also bundles nine skills that run on your machine. `researchzy` is the entry point: it searches and manages papers itself and hands the other tasks to the skill that fits, to review the literature, download full text, read papers closely, build research cards, check references and prepare manuscript revisions. The plugin does not wrap Researchzy's AI Search or AI Survey: the literature review skill runs in your agent and uses the search tool.

Search takes titles, keywords, DOI and arXiv identifiers. Paper metadata has `hasReadablePdf`, and a paper whose PDF Researchzy can show has `readerUrl`, its page in the Researchzy reader. The PDF tool returns a short-lived URL, its expiry, and the file's hash and size when known; the host downloads and verifies the file as the [`researchzy` skill](skills/researchzy/SKILL.md) describes. The upload tool returns a short-lived URL that the host PUTs a local PDF file to, for a library paper that has no PDF yet.

## Workflows

| User goal | Skill | Result |
|---|---|---|
| Start here: search, metadata, library, or PDF retrieval, and the way to every other skill | `researchzy` | Real metadata or a verified local PDF |
| A literature review on a topic | `researchzy-literature-review` | `review.md` with a comparison table and gaps, `papers.csv`, `references.bib` and a search log |
| Full text Researchzy has no PDF for | `researchzy-download` | Verified PDFs or full text from open access or the user's publisher API keys, and `manifest.json` |
| Close reading: how the authors got there, load-bearing design, worked formulas, evidence boundary | `researchzy-deep-read` | A Markdown long-read |
| Paper Card, evidence chain, methods, or limitations | `researchzy-paper-card` | Source-anchored `paper-card.md` and an audit report |
| Statistical reporting of a manuscript | `researchzy-stats-review` | Issues by severity, ready-to-paste Statistical analysis text, and author questions |
| Data and Code Availability statements | `researchzy-data-availability` | A ready-to-paste statement, repository and citation actions, and missing-information flags |
| Are the references real and correct, and do the cited papers support the text | `researchzy-reference-check` | A verdict and evidence per reference, a corrected `.bib`, and verified quotes for checked claims |
| Responses to reviewers and revision packages | `researchzy-rebuttal` | A master tracker, one response per reviewer, a cover letter, and optional LaTeX files |

For a close reading or a Paper Card, the agent follows the [source acquisition rules](skills/researchzy/references/researchzy-source.md), retrieves and verifies the PDF, then runs the requested skill locally. Researchzy's servers do not run these skills. Local PDFs work directly. Metadata alone is never enough to invent full-text claims or page references.

Example prompts:

- `Use Researchzy to look up DOI 10.1051/0004-6361/202556799 and return metadata only.`
- `Download the full text of 10.1371/journal.pone.0000308 and 10.1016/j.cell.2020.02.052.`
- `Create a Paper Card for this local PDF and separate author claims from your analysis.`
- `Read arXiv 1706.03762 closely: why did the authors design it this way, and how far does the evidence reach?`
- `Review the literature on sleep deprivation and memory encoding since 2010.`
- `Check the references in main.tex: are they real, and do the DOIs belong to them?`
- `Here are the editor's letter and the reviewers' comments; draft the point-by-point responses.`

Python 3.10+ is recommended for the bundled scripts. PDF preparation uses PyMuPDF from `requirements.txt`; scanned PDFs also need OCR support. The downloader needs Node.js 22+ and verifies PDFs with pdfplumber or pypdf. Pinned upstream sources, licenses, and Researchzy's modifications are recorded in the [third-party notices](THIRD_PARTY_NOTICES.md).

## Connection

The plugin's MCP server is `https://app.researchzy.com/mcp`. Codex signs in with the public OAuth client `paperone-codex` and the callback `http://127.0.0.1:8766/callback` (`.mcp.json`); Claude Code identifies itself with its own client metadata document (`.claude-plugin/plugin.json`). See [connection setup](../../docs/connection.md) for other hosts.

Every tool needs a connected Researchzy account. Search, paper details, library access and `get_profile` need `library.read`; saving papers, creating collections and adding PDFs to library papers need `library.write`; PDF download metadata needs `pdf.read`. The host requests these scopes and the user approves them. An access token lasts an hour, and the host renews it with a refresh token that is replaced on every use and lasts 90 days, so a connection stays signed in while it is used at least once in 90 days. The user can disconnect an app on the Researchzy Account page, which ends its tokens at once. Never store passwords, cookies, access tokens or signing keys in this package.

## Basic flow

1. Call `search_papers` with exactly one of `doi`, `arxiv`, or `query`.
2. Reuse returned metadata; call `get_paper` only when additional details are needed.
3. When the user requests a PDF, call `get_pdf_download`, download the signed URL, and verify the file.
4. Save a paper only when requested. Use `list_collections` and `canAddPapers` before selecting a collection.
5. When the user asks to add a local PDF to a library paper without one, call `create_pdf_upload` and PUT the file to `uploadUrl`.

Example identifiers illustrate input formats and do not guarantee a match. See the [tool reference](docs/tools.md) for boundaries.
