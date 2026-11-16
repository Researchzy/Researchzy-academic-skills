# The ledger, its files and the BibTeX rules

## The folder

Everything goes in `citations/` in the user's working directory. Run every command from that directory: the ledger stores paths as given.

| Path | Written by | Holds |
|---|---|---|
| `citations/ledger.json` | the script | Targets, searches, candidates, verdicts, papers. Change it only through commands |
| `citations/targets.md` | `targets`, `confirm` | Every target and candidate sentence, the other marker forms, placeholders in skipped blocks |
| `citations/results/<target>-<n>.json` | you | Each tool result, saved as returned and never edited |
| `citations/pdf/`, `citations/texts/` | you, `text` | PDFs from `get_pdf_download`; their text with `[[page N]]` marks |
| `citations/new-references.bib` | `bib` | Entries for accepted papers that are not in the author's `.bib` |
| `citations/citation-map.md` | `check` | Per target: sentence, verdict, key, grade, quote with its place, wording, searches |
| `citations/<name>.cited.md` or `.tex` | `apply` | A copy of the manuscript with supported placeholders replaced |

Do not put signed download URLs, tokens or cookies into any file under `citations/`.

## Targets and ids

- `t1`, `t2`, … are `[Citation needed: …]` placeholders, in any letter case. They are targets from the start.
- `c1`, `c2`, … are candidate sentences: a sentence with another marker (`[CITATION NEEDED]`, `[citation needed]`, `[?]`, `\cite{?}`, `[@NEW:…]`), a sentence without a citation that carries a statistic (a percentage, a p-value, `n =`, a fold change, a ratio) or a literature phrase ("studies have shown", "it is well known", "previous work", "has been reported"), or a sentence named with `targets --line N`. A candidate becomes a target only with `confirm`.
- A sentence counts as cited when it holds `\cite…{key}`, `[@key]` or `@key`, a numeric `[12]`, or an author-year citation, "(Okoro et al., 2019)" or "Okoro et al. (2019)".
- Skipped: Markdown front matter, fenced and inline code, headings, tables, HTML comments, math and the reference list; LaTeX comments, the preamble, headings, `verbatim`, `lstlisting`, `minted`, tables, `thebibliography` and math. A placeholder inside them is listed apart, not made a target.
- An id is kept across runs while the sentence text (and, for a placeholder, its note) is unchanged. A confirmed target whose sentence disappeared stays in the ledger, marked as no longer in the manuscript, with what was found for it. An unconfirmed candidate that disappeared is dropped.

## Commands and what they refuse

| Command | Refuses (exit 1, nothing recorded) |
|---|---|
| `need t1 <type>` | A candidate that was not confirmed; `not_needed` without `--reason` |
| `search t1 …` | A completed search without `--total` and `--saved`, or with a saved file that does not exist |
| `candidate t1 <file> --doi …` | A file that is not a saved tool result, or holds no record with that identifier and a title |
| `verdict t1 supported` / `partial` / `contradicts` | A missing `--paper`, `--grade`, `--quote` or `--source`; `partial` without `--wording`; a quote under five words; a source file that does not exist; `full-text` from a `.json` or `.pdf`; a paper that is not a candidate of this target |
| `verdict t1 not_found` | Fewer than three distinct completed keyword searches of the index, without `--reason` |
| `verdict t1 not_needed` / `not_checked` | No `--reason` |
| `text <file>` | A file that is not a PDF. With no extractor installed it records nothing and says so |

A saved result may be a list of records, or an object with `results`, `papers`, `items` or `paper`. The script reads `title`, `authors` (strings or objects with `name`), `authorCount`, `year`, `venue`, `doi`, `arxiv`, `corpusId`, `abstract`, `hasReadablePdf` and `readerUrl`. DOIs are compared in lower case without a resolver prefix; arXiv ids without a version.

## What `check` enforces

Exit code 1 when any of these is broken; each problem is listed with its target in the JSON and in `citation-map.md`.

1. Every confirmed target has a verdict from the vocabulary.
2. `supported`, `partial` and `contradicts` name a recorded paper with a DOI, arXiv id or corpusId, a grade of `abstract` or `full-text`, and a quote of five words or more that is found in the named text: the text file, or the abstract of that paper in the saved record.
3. Grade `metadata` is never support. A `full-text` grade rests on a text file of at least 400 words, not on a saved record.
4. `supported` and `partial` whose sentence (for `partial`, the wording) carries a number, a comparison word or a causal verb have grade `full-text`, or every number of that sentence appears in the quote.
5. `partial` has a narrower wording. `not_needed` and `not_checked` have a reason. `not_found` has three distinct completed keyword searches, or a reason.
6. Every verdict other than `not_needed` and `not_found` has at least one logged search or a reason.
7. Every accepted paper has its final key from `bib`, and `new-references.bib` exists when it should.

`check` also lists the candidate sentences never confirmed and the targets no longer in the manuscript, so nothing goes missing without a line in the output.

## BibTeX rules (`bib`)

- Only papers of `supported` and `partial` verdicts get an entry, built from the fields the tool returned and nothing else.
- With the author's `.bib` (`--bib`, or the one given to `targets`): a paper whose DOI, or whose title after removing case, accents, braces, markup and punctuation, matches an entry keeps that entry's key and gets no new entry. The author's file is read, never written.
- A new key is the first author's family name, the year and the first word of the title that is not a short function word: ASCII, lower case, with `a`, `b`, … added when the key is taken in the ledger or in the author's file.
- Entry type: `@inproceedings` (venue in `booktitle`) when the venue names proceedings, a conference, workshop, symposium, congress or meeting; `@article` (venue in `journal`) for any other venue; `@misc` with `eprint` and `archivePrefix = {arXiv}` for an arXiv-only record or one with no venue.
- Titles lose markup tags and character entities and are double-braced to keep their capitals. `\ & % $ # _ { } ~ ^` are escaped in titles, authors and venue. Names stay in UTF-8 as returned. When the record reports more authors than it lists, the list ends with `and others`.
- Never written: `volume`, `number`, `pages` (the index does not return them), `abstract`, `url`, `month`, `publisher`, or any field the record lacks. `researchzy-reference-check` (plugin `researchzy-manuscript`), when installed, completes and verifies the entries and checks retractions.

## `apply`

`apply paper.md` writes `citations/paper.cited.md` (`.tex` likewise). Each `[Citation needed: …]` of a `supported` target with no broken rule becomes `[@key]` in Markdown, or in LaTeX the cite command the manuscript uses most (`\cite`, `\citep`, `\parencite`, `\autocite`). Every other placeholder stays, and the JSON lists why. Candidate sentences confirmed from other markers are not changed: give their keys to the user from the map. The original file is never written.
