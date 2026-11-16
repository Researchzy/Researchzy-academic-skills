# Core tools

| Tool | Input | Purpose |
|---|---|---|
| `search_papers` | Exactly one of `query`, `doi`, or `arxiv`; optional `page` and `pageSize`. Keyword (`query`) searches also take `sort` (`relevance`, `citationCount`, `year` newest first, `influency`), `yearFrom`, `yearTo`, `fieldOfStudy`, `venue` and `hasPdfInS3` | Search bibliographic metadata |
| `get_paper` | Exactly one of `corpusId` or `paperId` | Retrieve one paper |
| `list_collections` | No arguments (`{}`) | List visible personal collections only and `canAddPapers` hints; a paper may belong to multiple collections |
| `list_library_papers` | `scope: personal/shared/collection`; collection scope requires `collectionId`; optional `query`, `page`, `pageSize` | Browse visible papers; `collection` scope selects a collection; `query` narrows the list |
| `create_collection` | `name` (1–100 characters); optional `parentCollectionId` of a personal collection | Create a personal collection when explicitly requested; shared collections cannot be created or used as the parent. An existing personal collection with the same name in the same place is returned with `status: already_present` |
| `add_paper_to_library` | `corpusId`; optional `collectionId` | Save a paper when explicitly requested |
| `get_pdf_download` | Exactly one of `corpusId` or `paperId` | Get current PDF metadata and a short-lived URL |
| `create_pdf_upload` | `paperId` of a library paper without a PDF | Get a short-lived URL that adds a local PDF file to that paper, when explicitly requested |
| `get_profile` | No arguments (`{}`) | Read the connected account's opaque ID, name and email; hosts such as ChatGPT use it to tell linked accounts apart |

Follow the connected MCP server's live schemas. Every tool requires a connected Researchzy account. Input schemas carry no `oneOf`; the exactly-one rules above are enforced by the server, which answers a wrong combination with `INVALID_REQUEST`. Identifier searches accept only the identifier and pagination; do not add keyword sorting or filters. For keyword searches, `sort: citationCount` finds influential work, `sort: year` recent work, and `fieldOfStudy` must match the index's field name, such as `Computer Science` or `Medicine`. DOI input may be a bare value, a `doi:` prefix, or a resolver URL. arXiv input may be a bare value, a prefix, or an abs/pdf URL. A version suffix resolves the paper identity but does not guarantee that PDF version.

Metadata may include title, authors, abstract, year, `corpusId`, `doi`, `arxiv`, and `hasReadablePdf`. A successful empty search means only that the current index found no match. Do not interpret a backend error as evidence that the paper does not exist.

A paper whose PDF Researchzy can show (`hasReadablePdf: true`) also has `readerUrl`, its page in the Researchzy reader. Search results and `get_paper` by `corpusId` open read-only; library papers from `list_library_papers`, `get_paper` by `paperId` and `add_paper_to_library` open with the user's highlights and notes. `add_paper_to_library` returns `hasReadablePdf` for the saved paper. Give `readerUrl` to the user as a link. It is a web page for the signed-in user, not a PDF: use `get_pdf_download` for the file.

`hasReadablePdf` is a hint. Use `get_pdf_download` for current `url`, `expiresAt`, and any available `sizeBytes` or `fileHashSha256`. Do not attach Researchzy authorization or cookies to the signed URL. Receiving a URL alone does not complete the download. See the [Researchzy Literature skill](../skills/researchzy/SKILL.md) for the full workflow.

`create_pdf_upload` returns `uploadUrl`, `method` (`PUT`), `contentType` (`application/pdf`), `maxSizeBytes` and `expiresAt` (15 minutes). The host sends the bare file itself, without Researchzy authorization or cookies, for example `curl --fail-with-body -X PUT -H 'Content-Type: application/pdf' --data-binary @paper.pdf '<uploadUrl>'`; form and multipart uploads (`curl -F`) are refused with `INVALID_REQUEST`. The PUT answers with `paperId`, `hasReadablePdf: true`, `readerUrl`, `sizeBytes` and `fileHashSha256`, or with an error `code` and `userMessage`. Only papers without a PDF accept one: a paper's PDF, from the index or an earlier upload, is never replaced, and such a paper is refused with `OPERATION_NOT_ALLOWED`. The paper's metadata is not changed. An expired or unknown link answers `RESOURCE_NOT_FOUND`. A host that cannot read local files or make HTTP requests cannot use it; the user can add the PDF in the paper's details in Researchzy.
