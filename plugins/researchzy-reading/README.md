# Researchzy Reading plugin

Version 2.2.0. Three skills for reading papers. They run on your machine and work on the PDFs and text you give them; no account is needed.

| User goal | Skill | Result |
|---|---|---|
| The full text of papers, by DOI, exact title or a known PDF URL | `researchzy-download` | Verified PDFs or full text from open access or your own publisher API keys, and `manifest.json` |
| A close reading: how the authors got there, which design carries the result, worked formulas, how far the evidence reaches | `researchzy-deep-read` | A Markdown long-read |
| A Paper Card: evidence chain, methods, limitations, research ideas | `researchzy-paper-card` | A source-anchored `paper-card.md` and an audit report |

Example prompts:

- `Download the full text of 10.1371/journal.pone.0000308 and 10.1016/j.cell.2020.02.052.`
- `Read this PDF closely: why did the authors design it this way, and how far does the evidence reach?`
- `Create a Paper Card for this local PDF and separate author claims from your analysis.`

## With Researchzy connected

Install the [`researchzy`](../researchzy) plugin and sign in, and these skills also take a DOI, arXiv ID or title: they find the paper in Researchzy's index, use the PDF Researchzy holds, and follow each skill's `references/researchzy-source.md` to retrieve and verify it. Metadata alone is never enough to invent full-text claims or page references.

## Requirements

Python 3.10+ for the bundled scripts. PDF preparation uses PyMuPDF from `requirements.txt`; scanned PDFs also need OCR support. The downloader needs Node.js 22+ and verifies PDFs with pdfplumber or pypdf. Pinned upstream sources, licenses, and Researchzy's modifications are recorded in the [third-party notices](THIRD_PARTY_NOTICES.md).
