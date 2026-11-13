---
name: researchzy-download
description: Download the lawful full text of identified papers by DOI, exact title or a known PDF URL. Tries the PDF Researchzy holds, then open-access copies (PMC, Unpaywall, openly licensed publisher PDFs, arXiv) and Elsevier, Springer Nature or IEEE full text through the user's own API keys, and records every attempt in a per-paper manifest. Use when the user wants papers' PDFs or full text, or another skill needs a paper Researchzy has no PDF for.
metadata:
  compatibility: Requires Node.js 22+ for the downloader and Python 3 with pdfplumber or pypdf for verification. Uses only open-access sources and publisher APIs the user holds keys for.
---

# Researchzy Download

This skill retrieves full text through lawful open-access sources and the publisher APIs the user is entitled to. `scripts/batch_download.mjs` is the entry point; metadata, open-access resolution, publisher APIs, content validation and the manifest are separate modules under `scripts/lib/`. Resolve `SKILL_DIR` to the directory containing this `SKILL.md` and run the bundled scripts by that path, never relative to the working directory.

It covers no institutional or browser access: it does not sign in to libraries, reuse browser sessions or pass verification pages. When a paper has no open-access copy and no API the user holds a key for, report it and let the user supply the file.

## Before downloading

1. Establish a definite list of papers: DOIs, exact titles, or legitimate PDF URLs. Do not turn a keyword search into bulk downloading, and do not download whole journal issues, volumes or result sets. Process only the papers the user identified or confirmed.
2. Researchzy first. When the Researchzy tools are available, look each paper up with `search_papers` (pass its DOI as `doi`, an arXiv ID as `arxiv`, a title as `query`) and call `get_pdf_download` for it. When that returns a URL, download and verify the file as `researchzy` describes and skip the downloader for that paper. Run the downloader for the papers Researchzy has no PDF for, or for all of them when the tools are not available.
3. Prefer DOIs. Resolve a title to its DOI with Researchzy search when possible; titles are not unique.
4. Save into the task workspace unless the user names another folder.

## Run the downloader

```bash
node "$SKILL_DIR/scripts/batch_download.mjs" --dois "10.1371/journal.pone.0000308,10.1016/j.cell.2020.02.052" --out downloads
node "$SKILL_DIR/scripts/batch_download.mjs" --title "<exact title>" --out downloads
node "$SKILL_DIR/scripts/batch_download.mjs" --title "Attention Is All You Need" --open-access --out downloads
node "$SKILL_DIR/scripts/batch_download.mjs" --pdf-url "https://arxiv.org/pdf/1706.03762" --title "Attention Is All You Need" --out downloads
```

For each DOI the script reads Crossref metadata and classifies the publisher:

- Elsevier, Springer Nature or IEEE with a usable key: the publisher API first. A successful API download records `oa_status: not_checked_api_first`, meaning open access was not checked, not that the paper is closed. If the API fails, open access follows.
- Every other paper: open access first, in this order: PMC (NCBI's PMC Article Datasets), Unpaywall's open locations, and the publisher PDF that Crossref lists when the licence is Creative Commons. For Elsevier, Springer Nature or IEEE without a key, the API step that follows reports `credentials_missing` with the page where the user can register for one.
- `--open-access` (or `--route open_access`) stops after open access. `--route elsevier|springer_nature|ieee` tries only that API.

An exact title is resolved through Crossref. When several Crossref works share the title (a preprint and the article, say), the result is `metadata_ambiguous` with `candidates`: ask the user which one they mean, or pick by the DOI from Researchzy, and rerun with `--dois`. When Crossref has no exact match, an exact arXiv title match is downloaded. `--pdf-url` fetches one legitimate URL directly; use it only for a URL the user gave or a source you have confirmed is open.

The script prints `{ summary, manifest, results }` and writes `<out>/manifest.json` with the route, every attempt, open-access evidence, access mode, format, size and SHA-256 of each paper; secret-looking fields are removed. PDFs go under `PDFs/`, HTML and JATS XML full text under `FullText/`. Run one batch at a time; the script requests each source in turn.

Never read file bytes, whole pages or API responses into the conversation. Read the script's JSON and report compact per-paper status.

## Unpaywall contact email

Unpaywall requires a contact email on every request. Without one the script skips Unpaywall, says so on stderr, and still tries PMC and openly licensed publisher PDFs. When papers come back `oa_not_found` without Unpaywall, ask the user once which email address to use; never guess one or take it from elsewhere. Save it with:

```bash
python3 "$SKILL_DIR/scripts/configure_credentials.py" contact-email researcher@example.org
```

`--unpaywall-email` or the `UNPAYWALL_EMAIL` environment variable work for a single run. The address is stored as a non-secret setting in `~/.config/lit-dl/settings.json`.

## Publisher API keys

Configure a key only when a paper from that publisher needs it (`credentials_missing`). Give the user the official registration page: Elsevier `https://dev.elsevier.com/`, Springer Nature `https://dev.springernature.com/docs/quick-start/api-access/`, IEEE `https://developer.ieee.org/member/register`.

```bash
python3 "$SKILL_DIR/scripts/configure_credentials.py" set elsevier
python3 "$SKILL_DIR/scripts/configure_credentials.py" set elsevier --stdin
python3 "$SKILL_DIR/scripts/configure_credentials.py" set springer_nature --service openaccess
python3 "$SKILL_DIR/scripts/configure_credentials.py" set springer_nature --service fulltext
python3 "$SKILL_DIR/scripts/configure_credentials.py" set springer_nature --service metadata
python3 "$SKILL_DIR/scripts/configure_credentials.py" set ieee --fulltext-endpoint 'https://issued-endpoint.example/articles/{doi}'
python3 "$SKILL_DIR/scripts/configure_credentials.py" show
python3 "$SKILL_DIR/scripts/configure_credentials.py" validate <provider>
python3 "$SKILL_DIR/scripts/configure_credentials.py" validate springer_nature --service openaccess
python3 "$SKILL_DIR/scripts/configure_credentials.py" delete <provider>
```

- Elsevier accepts an optional `--insttoken` or `--authtoken` when the user's institution issued one.
- Springer keys are scoped by service: `metadata_api_key` cannot download anything, `openaccess_api_key` uses `/openaccess/jats`, and `fulltext_api_key` uses `/xmldata/jats` under a Full Text agreement. Configure only the services the user has activated; setting one keeps the others. A key without `--service` is a Full Text key. Downloads try Full Text first, then Open Access.
- IEEE: a Metadata API key is not full-text access. Require the Full-Text Access endpoint the user was issued before treating IEEE as downloadable.
- `validate` checks one HTTP response only. It cannot prove that a given article is covered.

Do not ask the user to paste an API key into the chat. The hidden prompt of `set` is the preferred path. If the user sends a publisher API key anyway, treat that as permission to save that key: pass it to `set <provider> --stdin`, keep it out of command-line arguments, logs, replies and manifests, and report only the masked confirmation and validation status. Keys are stored in `~/.config/lit-dl/credentials.json` with mode `0600` on the machine where the skill runs; in a hosted research agent that is the agent's own workspace.

## Status categories

Every paper ends with one of these statuses in the manifest:

```text
downloaded                  publisher API PDF, or a PDF from --pdf-url
open_access_downloaded      PDF from PMC, Unpaywall, an openly licensed publisher PDF or arXiv
full_text_html_available    readable HTML full text, but no PDF
native_fulltext_downloaded  JATS XML full text (for example Springer Nature), but no PDF
credentials_missing         supported publisher without a key; configureUrl says where to get one
credentials_invalid         the publisher rejected the key (HTTP 401)
api_not_entitled            the key works but does not cover this article (HTTP 403)
api_fulltext_unavailable    the API has no usable full text for this article
rate_limited                the publisher API asked to slow down (HTTP 429)
oa_not_found                no lawful open-access copy found; oa_assessment tells confirmed_oa, confirmed_closed or unknown
metadata_ambiguous          the title matches several works, or none
pdf_fetch_failed            the given URL did not return full text
failed_after_retry          a network or service error
do_not_auto_retry           an argument or logic error; fix the request before running again
```

When a paper went through more than one source, `attempts` lists each source and its status. `full_text_html_available` and `native_fulltext_downloaded` are successes, but tell the user plainly that no PDF was available. When `oa_assessment` is `confirmed_oa` but nothing was saved, no source offered a reachable file at the time; Unpaywall is often the missing one. Configure the contact email, or retry once later.

## Verify and deliver

Verify every file before reporting it as downloaded:

```bash
python3 "$SKILL_DIR/scripts/extract_pdf_text.py" --pdf "downloads/PDFs/<file>.pdf" --pages 2 --json
```

- The file exists, its size is plausible, and a PDF starts with `%PDF` (the downloader already rejects anything else).
- The page count is not zero, and the extracted text contains the article's title, DOI or abstract.
- For HTML or JATS XML full text, the saved file contains the title or DOI.

If extraction fails although the file is a PDF, it may be scanned: use PyMuPDF or OCR rather than reporting it as broken. Give the user the saved paths, the status of each paper and the manifest path. When the user asked to rename files, use `FirstAuthor_Year_Journal_short-title.pdf`.

## When no lawful copy is found

Tell the user which sources were tried (from `attempts`) and what is missing:

- `credentials_missing` for a supported publisher: an API key may give access if the user or their institution has an agreement.
- Otherwise the user can download the PDF through their own library or subscription and give you the file. For a paper in their Researchzy library, `researchzy` can add it to the paper with `create_pdf_upload` when they ask.

## Boundaries

- Use only open-access sources and publisher APIs the user holds keys for. Never bypass paywalls or DRM, and never use shadow libraries or mirror sites.
- Do not solve CAPTCHAs, pass bot checks, sign in on the user's behalf, or read cookies, browser profiles or session data.
- Never ask for or accept institutional passwords, OTP codes, recovery codes or session tokens. Publisher API keys follow the separate rule above.
- An open copy is not a licence to redistribute. Follow the licence recorded in the manifest's open-access evidence.

## Continue with other skills

- For a Paper Card, evidence chain or research ideas, pass the verified local PDF and its metadata to `researchzy-paper-card`.
- For search, library work or adding the file to a Researchzy library paper, use `researchzy`.
