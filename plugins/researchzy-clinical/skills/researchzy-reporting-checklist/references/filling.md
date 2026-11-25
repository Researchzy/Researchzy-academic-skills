# Filling the checklist

## The texts

Pages and lines are those of the file the journal will see, so the places are taken from its PDF.

- `pdftotext -layout manuscript.pdf reporting-checklist/manuscript.txt`. The form feeds it writes mark the pages, and the first page of the file is page 1. If the journal's page numbers differ (an unnumbered cover page), start each page with a line `[[page N]]` carrying the printed number instead.
- Without pdftotext, extract each page with another tool (PyMuPDF has it in Python) and write `[[page N]]` on a line of its own before each page.
- A line-numbered PDF keeps its numbers at the left margin with `-layout`, and `check` reads them. Without line numbers, lines are `not_checked`.
- A .docx manuscript has no pages: quotes are checked against its whole text and pages are `not_checked`. Use the PDF when there is one.
- The supplement gets its own text file and its own page numbers.
- Record each text's hash in `filled.json`. Never edit a text to make a quote fit.

## Read first, then judge

Read the whole manuscript, the supplement, every figure and table caption and the reference list before you mark anything as missing. An item reported only in the supplement is reported, and its place names the supplement. Judge whether the item is reported, not whether the study was done well.

## The four statuses

| Status | When | Needs |
|---|---|---|
| `reported` | The manuscript or the supplement gives everything the item asks for | One place or more |
| `partly_reported` | Some of what the item asks for is there, some is not | Places for what is there; `missing`; `suggestion` |
| `not_reported` | None of it is there, after reading everything | `missing`, saying where you looked; `suggestion` |
| `not_applicable` | The item cannot apply to this study | `reason`: the feature of the study that rules it out |

- Not applicable is not "not done": an item about something the study did and did not describe is not reported.
- A reason names the study's feature ("The cohort was not matched on any characteristic"). "N/A" is not a reason, and neither is a placeholder.
- Read the item in the registered design's wording; the wording for another design does not apply.
- If you cannot judge an item, because a figure or a table could not be read, ask the user for the file. Do not guess a status.

## Places

| Field | Content |
|---|---|
| `document` | `manuscript`, or the id of a supplement in `documents` |
| `page` | The page of that document; `"8-9"` when the passage runs over a page break |
| `lines` | When the text has line numbers: the first and last line of the passage, `"112-118"` |
| `where` | The section, table or figure, for the reader: "Methods, Participants", "Table 2", "Table S2" |
| `quote` | The passage, word for word |

- A quote is copied from the text: at least five words, or twelve Chinese, Japanese or Korean characters; one passage; no ellipsis; nothing repaired or translated.
- Quote the sentence that reports the item, not one that only mentions its keyword. From a table, quote the row or the caption.
- Give several places when the item is reported in several (the methods and a table).
- `check` reports the page and the lines where it found the quote. Reread the passage there before you correct the place.
- Known limit: the match tolerates extraction noise between words, so a quote that lacks a "not" or a digit can still be found. Reread every quote that turns on a negation or a number.

## filled.json

Invented, like the checklist of [registering](registering.md):

```json
{"documents": [{"id": "manuscript", "path": "manuscript.txt", "sha256": "…"},
               {"id": "supplement", "path": "supplement.txt", "sha256": "…", "label": "Supplement"}],
 "items": [
  {"id": "1a", "status": "reported", "assessor": "model", "checked_by": "",
   "locations": [{"document": "manuscript", "page": 1, "lines": "1-2", "where": "Title",
                  "quote": "Evening light at work and sleep duration in shift workers: a prospective cohort study"}]},
  {"id": "6", "status": "reported", "assessor": "model", "checked_by": "",
   "locations": [{"document": "supplement", "page": 2, "where": "Table S2",
                  "quote": "Evening light lux measured by the wrist sensor between 18:00 and 23:00"}]},
  {"id": "5b", "status": "not_applicable", "assessor": "model", "checked_by": "",
   "reason": "The cohort was not matched on any characteristic"},
  {"id": "7", "status": "not_reported", "assessor": "model", "checked_by": "",
   "missing": "How the number of participants was decided; searched Methods, Results and the supplement",
   "suggestion": "Say how the number was decided: [Author input needed: how the number of participants was decided]"}]}
```

| Field | Content |
|---|---|
| `documents` | Each text: `id` (`manuscript` once), `path` (relative to `reporting-checklist/`), `sha256` from `hash`, and `label` for a supplement as the upload list should name it |
| `id` | The registered id, once per item |
| `status` | `reported`, `partly_reported`, `not_reported` or `not_applicable` |
| `locations` | The places, as above |
| `missing`, `suggestion` | For `partly_reported` and `not_reported` ([suggestions](suggestions.md)) |
| `reason` | For `not_applicable` |
| `assessor`, `checked_by` | `model` for your entries; the reviewer's name once a person has checked the entry |

In a methods section or a cover letter, say that the model filled the checklist and which entries a person reviewed (`checked_by`).
