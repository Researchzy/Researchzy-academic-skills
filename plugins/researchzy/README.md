# Researchzy plugin

Version 2.0.0. Find and review the literature with real papers. This is the one Researchzy plugin that needs a Researchzy account: it connects your agent to Researchzy through nine MCP tools (`search_papers`, `get_paper`, `list_collections`, `create_collection`, `list_library_papers`, `add_paper_to_library`, `get_pdf_download`, `create_pdf_upload` and `get_profile`) and bundles two skills that use them.

| User goal | Skill | Result |
|---|---|---|
| Start here: search, metadata, library, or PDF retrieval, and the way to every other Researchzy skill | `researchzy` | Real metadata or a verified local PDF |
| A literature review on a topic | `researchzy-literature-review` | `review.md` with a comparison table and gaps, `papers.csv`, `references.bib` and a search log |

The reading skills (`researchzy-download`, `researchzy-deep-read`, `researchzy-paper-card`) are in the [`researchzy-reading`](../researchzy-reading) plugin and the manuscript skills in [`researchzy-manuscript`](../researchzy-manuscript). They need no account, and use the tools of this plugin when it is installed and connected.

The plugin does not wrap Researchzy's AI Search or AI Survey: the literature review skill runs in your agent and uses the search tool.

## Tools

Search takes titles, keywords, DOI and arXiv identifiers. Paper metadata has `hasReadablePdf`, and a paper whose PDF Researchzy can show has `readerUrl`, its page in the Researchzy reader. The PDF tool returns a short-lived URL, its expiry, and the file's hash and size when known; the host downloads and verifies the file as the [`researchzy` skill](skills/researchzy/SKILL.md) describes. The upload tool returns a short-lived URL that the host PUTs a local PDF file to, for a library paper that has no PDF yet. See the [tool reference](docs/tools.md) for boundaries.

Example prompts:

- `Use Researchzy to look up DOI 10.1051/0004-6361/202556799 and return metadata only.`
- `Find the most-cited papers on CRISPR off-target effects since 2020 and save the top five to my "Gene editing" collection.`
- `Review the literature on sleep deprivation and memory encoding since 2010.`

The literature review's ledger script needs Python 3.10+.

## Connection

The plugin's MCP server is `https://app.researchzy.com/mcp`. Codex signs in with the public OAuth client `paperone-codex` and the callback `http://127.0.0.1:8766/callback` (`.mcp.json`); Claude Code identifies itself with its own client metadata document (`.claude-plugin/plugin.json`). See [connection setup](../../docs/connection.md) for other hosts.

Every tool needs a connected Researchzy account. Search, paper details, library access and `get_profile` need `library.read`; saving papers, creating collections and adding PDFs to library papers need `library.write`; PDF download metadata needs `pdf.read`. The host requests these scopes and the user approves them. An access token lasts an hour, and the host renews it with a refresh token that is replaced on every use and lasts 90 days, so a connection stays signed in while it is used at least once in 90 days. The user can disconnect an app on the Researchzy Account page, which ends its tokens at once. Never store passwords, cookies, access tokens or signing keys in this package.

## Basic flow

1. Call `search_papers` with exactly one of `doi`, `arxiv`, or `query`.
2. Reuse returned metadata; call `get_paper` only when additional details are needed.
3. When the user requests a PDF, call `get_pdf_download`, download the signed URL, and verify the file.
4. Save a paper only when requested. Use `list_collections` and `canAddPapers` before selecting a collection.
5. When the user asks to add a local PDF to a library paper without one, call `create_pdf_upload` and PUT the file to `uploadUrl`.

Example identifiers illustrate input formats and do not guarantee a match.
