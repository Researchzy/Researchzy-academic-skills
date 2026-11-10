---
name: researchzy-reference-check
description: "Check the references of a manuscript or .bib file: each one exists, its DOI belongs to it, authors and year are right, and it is not retracted. Optionally check that each cited paper supports the sentence that cites it, with a quote and page. Use before submission or on AI-drafted text."
---

# Researchzy Reference Check

This skill checks a reference list in two levels:

1. **Reference check.** Is every reference a real work, does its DOI, PMID or arXiv number belong to it, are its authors and year right, and has it been retracted or corrected?
2. **Claim check** (optional). Does the cited paper say what the sentence citing it says? Every "supported" verdict carries a quote and a page, and a script confirms that the quote is in the source.

The verdicts come from the bundled scripts, which compare the references with public registries (Crossref, doi.org, DataCite, arXiv, PubMed) and with Researchzy's index. Do not decide from memory whether a paper exists, and never mark a reference confirmed yourself.

Resolve `SKILL_DIR` to the directory containing this `SKILL.md` and run the scripts by that path. They need Python 3.10 or newer and nothing else; reading a PDF needs PyMuPDF.

## Inputs

- A bibliography: `.bib`, or a `.tsv` with `title`, `author`, `year`, `doi` columns.
- A manuscript: `.tex` (with its `.bib` or a `thebibliography`), `.md`, `.docx` or `.pdf` with a reference list.
- A pasted reference list: save it as `references.txt`, one reference per line.

Prefer the source files to a PDF. A PDF's reference list is read reliably only when it is numbered; if it is not, copy the list into `references.txt` first.

Ask the user one question before starting, unless they already said: reference check only, or the claim check as well. The claim check reads the cited papers, so it takes much longer.

## Reference check

1. **Run the registry check.**

   ```sh
   python3 "$SKILL_DIR/scripts/check_references.py" main.tex --out reference-check
   python3 "$SKILL_DIR/scripts/check_references.py" refs.bib --manuscript paper.md --out reference-check
   ```

   Give the manuscript with `--manuscript` when the input is a `.bib` or a list, so that citations are located and unused or missing keys are reported. Add `--contact you@example.org` only if the user gives an address for the registries' courtesy header. The run is resumable: answers are cached in `reference-check/cache.json`.

2. **Look up in Researchzy what the registries left open.** Open `reference-check/lookups.json`. For each reference under `needed`, run its `calls` in order with the Researchzy `search_papers` tool and stop at the first call that returns papers. Save the results in `reference-check/researchzy-results.json`:

   ```json
   {"results": {"kingma2015": [{"corpusId": 6628106, "title": "…", "authors": ["…"], "authorCount": 2,
                                "year": 2014, "venue": "…", "doi": "…", "arxiv": "…",
                                "hasReadablePdf": true, "readerUrl": "…"}],
                "invented2023": []}}
   ```

   Copy the fields exactly as the tool returned them. Write an empty list when nothing came back: that records that the search was made. Do not judge which paper matches; the script does. If the Researchzy tools are not connected, skip this step and say so in the summary.

3. **Run the script again** with the saved results:

   ```sh
   python3 "$SKILL_DIR/scripts/check_references.py" main.tex --out reference-check \
     --researchzy reference-check/researchzy-results.json
   ```

4. **Report.** Read `reference-check/report.md` and `references.json`. Tell the user, in this order: references whose identifier does not exist, mismatches, retracted or corrected works and cited notices, unconfirmed references, duplicates and citation-key problems. Give the counts first. [Verdicts](references/verdicts.md) says what each verdict means and what to recommend for it.

| Verdict | Meaning |
|---|---|
| `confirmed` | A registry or index record matches the reference. |
| `mismatch` | The work exists, but its authors, title, year or identifier disagree with the record. |
| `unconfirmed` | Nothing confirmed or refuted it. Not evidence of invention: books, reports, theses and web pages are often in no registry. |
| `identifier_not_registered` | The DOI, PMID or arXiv number exists in no registry and no lookup found the work. |

Flags are separate from the verdict: `retracted`, `partly_retracted`, `expression_of_concern`, `corrected`, `update_notice` (the cited item is itself a retraction or correction notice), `preprint_published`, `duplicate`, `placeholder`.

## Fixing references

- For a `.bib` input the script writes `reference-check/fixes.bib`: the mismatching entries with only the disagreeing fields corrected from the registry record, each with a comment naming its source. Show it to the user. Apply it to their file only when they ask.
- For other inputs, list the corrected values from the report.
- Never delete a reference, never replace it with another paper, and never edit the manuscript text unless the user asks. A "nearest real paper" in the report is a lead for the author, not a replacement.
- After the user edits the references, run the check again. `references.json` records the hash of the files it checked, so an old report is recognisably old.

## Claim check

Run it only when the user asked for it. Read [Claim check](references/claim-check.md) first; in short:

1. Take the citations to check from `citations` in `references.json`. By default check those with `"check": true`: sentences with a number, a comparison, a claim of priority or quoted words. Check all of them when the user asks. Find author-year citations the script did not locate by reading the manuscript.
2. Get each cited paper's text: the user's own file, then Researchzy (`get_pdf_download` for the record in `lookups.json` under `for_full_text`), then `researchzy-download`, then the abstract. Never judge a claim from the title.
3. Read the source and give each citing sentence a verdict with a quote and page, in `reference-check/claims.json`.
4. Run `python3 "$SKILL_DIR/scripts/check_claims.py" check reference-check/claims.json`. A verdict whose quote the script does not find is not accepted: reread the source and correct the quote or the verdict.
5. Report from `reference-check/claims.md`.

## Rules

- The scripts decide existence and metadata; you report. If a result looks wrong, say why and let the user decide, but do not overrule it silently.
- A failed lookup is `unconfirmed`, never "does not exist". Do not call a reference fabricated: report what was looked up and what was found.
- Report only what the tools and scripts returned. Do not fill in a missing DOI, author or year from memory.
- Retrieving a paper for the claim check does not add it to the user's library. Save papers only when asked.
- Do not put signed download URLs, tokens or cookies into any file under `reference-check/`.

## Related files

| File | Open when |
|---|---|
| [references/verdicts.md](references/verdicts.md) | Reporting results, or the user asks why a reference got its verdict |
| [references/claim-check.md](references/claim-check.md) | Before any claim check |
| `scripts/check_references.py` | Steps 1 and 3; `--help` lists the options (`--offline`, `--refresh`, `--strict`) |
| `scripts/check_claims.py` | Claim check; `text` turns a PDF into text with page markers, `check` verifies quotes |
