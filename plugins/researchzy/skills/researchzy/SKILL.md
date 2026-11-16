---
name: researchzy
description: Researchzy, the entry point for research with real papers. Searches about 250 million papers by DOI, arXiv ID, title or keywords, manages the user's library, gets and adds PDFs, and routes every other research task (literature reviews, systematic reviews and meta-analyses, ideas, citations, journal choice, reading, writing, translation and polishing, figures, statistics and causal inference, slides, grants, submission and revision) to the Researchzy skill that does it. Use when the user mentions Researchzy, wants to find, save or get papers, or asks for research help without naming a skill.
---

# Researchzy

This is the entry point to Researchzy. It searches and manages papers itself with Researchzy's MCP tools, and hands the other research tasks to the other Researchzy skills. `researchzy-literature-review`, `researchzy-ideas`, `researchzy-citation-finder` and `researchzy-find-journal` come with this plugin; the reading skills come with the `researchzy-reading` plugin, the manuscript skills with `researchzy-manuscript`, the evidence-synthesis skills with `researchzy-evidence`, and translation and polishing with `researchzy-language`.

## Which skill

| The user wants | Use | Plugin |
|---|---|---|
| Find papers, look up a DOI or arXiv ID, browse or organize the library, get or add a PDF | This skill, below | `researchzy` |
| A literature review, related work, or a survey of what is known about a topic | `researchzy-literature-review` | `researchzy` |
| A systematic review: protocol, logged searches, screening with reasons, a PRISMA 2020 flow | `researchzy-systematic-review` | `researchzy-evidence` |
| Risk-of-bias judgements for included studies, or a summary-of-findings table with certainty of evidence | `researchzy-risk-of-bias` | `researchzy-evidence` |
| A meta-analysis: effect sizes, pooled estimates, heterogeneity, forest and funnel plots | `researchzy-meta-analysis` | `researchzy-evidence` |
| Research ideas: generate them, sharpen a hypothesis, or judge an idea and its novelty | `researchzy-ideas` | `researchzy` |
| Real papers for sentences of a draft that need a citation, or for `[Citation needed: …]` placeholders | `researchzy-citation-finder` | `researchzy` |
| Where to submit a paper: a shortlist of journals or conferences with the evidence for each | `researchzy-find-journal` | `researchzy` |
| The full text of papers Researchzy has no PDF for | `researchzy-download` | `researchzy-reading` |
| A close reading of one paper: how the authors got there, the formulas worked through, how far the evidence reaches | `researchzy-deep-read` | `researchzy-reading` |
| A Paper Card, claim-to-evidence analysis, limitations or research ideas for one paper | `researchzy-paper-card` | `researchzy-reading` |
| Plan, draft or revise a manuscript from the author's own results | `researchzy-writing` | `researchzy-manuscript` |
| Figures from data, or a check of a figure file | `researchzy-figures` | `researchzy-manuscript` |
| A critical review of a manuscript before submission, or a referee report | `researchzy-paper-review` | `researchzy-manuscript` |
| A check that a manuscript's or `.bib` file's references are real and correct, or that the cited papers support the text | `researchzy-reference-check` | `researchzy-manuscript` |
| Analysis of the user's own data, or a sample-size or power calculation | `researchzy-statistics` | `researchzy-manuscript` |
| A causal effect from observational data: difference-in-differences, instrumental variables, regression discontinuity, panel, synthetic control or weighting | `researchzy-causal-inference` | `researchzy-manuscript` |
| A review or draft of a manuscript's statistical reporting | `researchzy-stats-review` | `researchzy-manuscript` |
| A Data and Code Availability statement, repository plan or dataset citations | `researchzy-data-availability` | `researchzy-manuscript` |
| Responses to reviewers, a revision cover letter or a revision package | `researchzy-rebuttal` | `researchzy-manuscript` |
| A submission package: cover letter, title page, declarations, and a check against the venue's instructions | `researchzy-submission` | `researchzy-manuscript` |
| A LaTeX paper that does not build, a move into a venue's template, or a source archive for arXiv or a journal | `researchzy-latex` | `researchzy-manuscript` |
| Slides and speaker notes for a talk or a journal club on a paper | `researchzy-slides` | `researchzy-manuscript` |
| A grant proposal written against a funder's call | `researchzy-grants` | `researchzy-manuscript` |
| A translation of a manuscript section or a paper that keeps numbers, citations and LaTeX | `researchzy-translate` | `researchzy-language` |
| Polished academic English that says the same thing | `researchzy-polish` | `researchzy-language` |

When a request spans several steps (find, get the full text, read, write), take them in that order and stop where the request stops. If the skill a task needs is not installed, say so, name the plugin that provides it, and do what this skill can.

## Researchzy tools

Use Researchzy's MCP tools for literature search, metadata, library access, PDF retrieval, and adding PDFs to library papers. Follow their live schemas. If the tools are unavailable in this session, say so; when the host offers a way to connect Researchzy, point the user to it. Report only fields returned by the tools.

### Tool routing

| User goal | Tool |
|---|---|
| Search by title, keywords, DOI, or arXiv ID | `search_papers` |
| Retrieve one paper by known `corpusId` or `paperId` | `get_paper` |
| List personal collections | `list_collections` |
| Create a personal collection | `create_collection` |
| Browse personal, collection, or shared papers | `list_library_papers` |
| Add a paper to the library or a writable collection | `add_paper_to_library` |
| Get current PDF metadata and a download URL | `get_pdf_download` |
| Add a local PDF file to a library paper without one | `create_pdf_upload` |

### Search and metadata

- Reuse returned titles, authors, abstracts, identifiers, years, `corpusId`, and `hasReadablePdf`. Do not infer missing values.
- When you point the user to a paper, give its returned `readerUrl` as a link to open it in Researchzy, where they can read, highlight and ask about it. Only papers whose PDF Researchzy can show have one; never build it yourself. It is a page for the signed-in user, not a PDF: do not fetch it, and use `get_pdf_download` for the file.
- Pass a DOI or DOI resolver URL as `doi`, an arXiv ID/prefix/abs URL/pdf URL as `arxiv`, and a title or keyword query as `query`. Pass exactly one. The service normalizes supported forms.
- Identifier searches accept pagination only. Do not attach keyword filters, sorting, venue, year, or PDF filters. An empty exact search means only that Researchzy found no indexed match.
- Keyword searches may narrow or order results when the user's request calls for it: `sort: citationCount` for influential work, `sort: year` for the newest, `yearFrom`/`yearTo` for a period, `venue`, `fieldOfStudy` (the index's field name, such as `Computer Science`), and `hasPdfInS3: true` for papers whose PDF Researchzy holds.
- arXiv searches resolve a paper identity. A `vN` suffix identifies the same paper, but the returned metadata or PDF is not guaranteed to be that version or the latest version.
- Use `get_paper` only when a known `corpusId` or `paperId` needs more detail; pass exactly one. Reuse existing search metadata when it is sufficient.
- A `paperId` lookup requires library authorization. Do not bypass a failed library lookup by switching to a corpus lookup. Retrieving details does not download or save the paper.
- Researchzy organizes papers in Collections. A paper may belong to multiple Collections; adding it to one does not move it out of another. Collections may be nested.
- Call `list_collections` with no arguments (`{}`). It returns personal Collections only; shared Collections are excluded. Collection IDs are exposed as `collectionId` and `parentCollectionId`. For `list_library_papers`, use `scope: personal | shared | collection`; `collection` selects a Collection and requires `collectionId`. Collection scope includes direct memberships only. Pagination starts at `page: 1`, never 0; follow `hasMore` when additional pages are needed.
- Call `create_collection` only when the user asks for a new collection, or asks to save papers into a collection that `list_collections` does not return. It creates personal collections only: there is no way to create a shared collection, and `parentCollectionId` must be a personal collection. Pass `name` and, to nest it, `parentCollectionId`. A same-named personal collection in the same place (ignoring case) is returned with `status: already_present` instead of a duplicate; report `created` or `already_present` and use the returned `collectionId`.
- Call `add_paper_to_library` only when the user explicitly asks to save a paper. Use `canAddPapers` to select writable Collections. Use `collectionId` to link the paper to a Collection, preserving its existing Collection memberships. Omit `collectionId` for the personal library. Never silently save somewhere else after a failure. Report the returned `created`, `linked`, or `already_present` result, with `readerUrl` when it is returned.
- Report tool failures with the returned `code` and `userMessage`. For an authorization failure, point the user to the host's Researchzy connection flow when the host offers one; never request passwords, tokens, or cookies.

### PDF metadata and downloads

1. Treat `hasReadablePdf` as a hint. When the user explicitly requests PDF metadata or the file, call `get_pdf_download` once for the current state.
2. Use `{corpusId: ...}` for a corpus result or `{paperId: ...}` for a personal/shared library paper; never pass both. Downloading does not add a paper to the library.
3. For metadata-only requests, return `url`, `expiresAt`, and any available `fileHashSha256` and `sizeBytes`. If no URL is returned, report the actual tool result.
4. When the file is requested, download it into the task workspace before `expiresAt`. Do not send Researchzy authorization headers or cookies to the signed URL.
5. If the URL has expired or returns HTTP 403, call `get_pdf_download` once more and retry once. Report the actual error after a second failure.
6. Verify HTTP success and that the downloaded content is a PDF. Compare `sizeBytes` and `fileHashSha256` when supplied. Receiving a URL alone is not a completed download.
7. Return a link or attachment for the saved file. Keep bibliographic metadata distinct from PDF-file metadata, and do not invent absent fields.

### Adding a PDF to a library paper

1. Add a PDF only when the user asks to attach or upload one to a paper in their library. You need the file in the task workspace: one the user supplied, or one you downloaded for them. A paper the library does not hold yet is saved first with `add_paper_to_library`, which returns its `paperId`.
2. Select the paper by its library `paperId` from `list_library_papers`, `get_paper` or `add_paper_to_library`. Only a paper with `hasReadablePdf: false` can get a PDF; Researchzy never replaces a paper's PDF, so do not try.
3. Check that the file is a PDF. Call `create_pdf_upload` with `{paperId: ...}` and compare the file size with the returned `maxSizeBytes`.
4. Send the file to `uploadUrl` before `expiresAt` with the returned `method` and `contentType`, without Researchzy authorization headers or cookies, for example `curl --fail-with-body -X PUT -H 'Content-Type: application/pdf' --data-binary @paper.pdf '<uploadUrl>'`. Send the bare file: a form or multipart upload such as `curl -F` is refused. Do not record `uploadUrl` in files or artifacts: it works without credentials until it expires.
5. A successful PUT returns `hasReadablePdf: true` and `readerUrl`; give the user the link. If the link has expired (`RESOURCE_NOT_FOUND`), call `create_pdf_upload` once more and retry once. `OPERATION_NOT_ALLOWED` means the paper has a PDF by now: report it and do not retry. Report other failures with their `code` and `userMessage`.
6. If the host cannot read local files or make HTTP requests, say so: the user can add the PDF in the paper's details in Researchzy.

## Full-text downloads, close reading and research cards

- Stop after search or metadata when that is all the user requested. A request to find papers on a topic stays here; a request for a review, related work or a survey of a topic goes to `researchzy-literature-review`, which logs its searches and cites only papers this index returned; a systematic review with a protocol and a PRISMA flow goes to `researchzy-systematic-review`.
- To check a reference list or the citations of a draft, continue with `researchzy-reference-check`. To find papers for sentences that have no citation yet, continue with `researchzy-citation-finder`.
- When Researchzy has no PDF for a paper the user wants the file of, continue with the `researchzy-download` skill: it finds a lawful open-access copy or uses the user's own publisher API keys.
- For close reading of one paper (how the authors got there, which design carries the result, the formulas worked through, how far the evidence reaches), continue with `researchzy-deep-read`.
- For a structured Paper Card, claim-to-evidence analysis, limitations, or research ideas, continue with `researchzy-paper-card`.
- These analysis requests allow retrieving the selected paper's available full text. Read [Researchzy source acquisition](references/researchzy-source.md), obtain and verify the PDF, then pass its local path and real metadata to the selected skill. Do not add the paper to the library unless requested.
- If a local PDF is already available, use it directly.
