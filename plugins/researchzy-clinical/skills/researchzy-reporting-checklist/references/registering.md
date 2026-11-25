# Registering the checklist

The skill carries no checklist. Each manuscript registers one in `reporting-checklist/checklist.json`, from the checklist's own file, so that the ids, the number of items and the wording are those the journal's editors will hold the manuscript against. `register` then compares the registration with the file.

## Which file

1. The file the journal attaches or links: its own form, or the guideline's file it names.
2. Otherwise the guideline's official file, or its official page read in this session and saved as .html in `source/`.
3. Never items from memory, from a summary on another site, or from a copy whose version you have not seen printed.

The journal decides the version. A journal that asks for an older version than the newest one you know gets the older one, from its own file. If the version the journal names and the version the file prints differ, tell the user both, replace neither, and write their answer, in their words and with the date, in `journal.user_decision`.

| The user has | Do |
|---|---|
| .docx, .csv, a saved .html page, or a journal article as JATS .xml | Register it as it is |
| A PDF | `pdftotext -layout form.pdf reporting-checklist/source/form.txt`. A text has no table rows: `register` finds each item's wording in it, but the ids and the count are `not_checked`. Count the items yourself, and ask whether the guideline offers a .docx |
| A web page whose HTML you cannot save | Save its text as .txt, with the address and the date at the top; it is registered like a PDF's text |
| An old Word .doc | Convert a copy: `soffice --headless --convert-to docx --outdir reporting-checklist/source form.doc` |
| Nothing but a name | Stop (step 1 of the workflow) |

## Design variants and extensions

- **Several designs in one file.** Some files give, inside one item, the wording for each design: "Cohort study: …", "Case-control study: …". Set `variant` to the study's design, with its label exactly as printed, and list every label the file prints in `variant_labels`. An item's `text` is its common wording plus the wording for that design only. `register` fails an item whose text carries another design's wording, or every design's.
- **A file for one design.** `variant` is that design as the file names it, and `variant_labels` is `[]`. If it is not the study's design, stop and ask for the right file. A checklist that names no design at all has `"variant": "none"`.
- **Extensions.** An extension adds items to a base guideline of a stated version. Record the base's name and version, as the extension's file prints them, in `extension_of`. When the extension's form lists only its own items, the base is a second registration from its own file: run the skill again with `--dir reporting-checklist/<base>` on every command.

## checklist.json

The checklist below is invented, and so is everything in it:

```json
{"name": "Example Observational Reporting Checklist (EORC)", "version": "1.0",
 "variant": "Cohort study", "variant_labels": ["Cohort study", "Case-control study"],
 "extension_of": "none",
 "journal": {"name": "Journal of Invented Results", "version": "1.0", "read": "2026-11-18",
             "quote": "a completed EORC checklist (version 1.0) with page numbers",
             "source": "journal-instructions.txt", "user_decision": ""},
 "source": {"path": "source/eorc-1.0.docx", "sha256": "…", "read": "2026-11-18", "type": "file", "url": ""},
 "licence": {"text": "For non-commercial reproduction only", "where": "footer"},
 "items": [{"id": "1a", "topic": "Design named", "text": "Say in the title or the abstract what kind of study this is"},
           {"id": "5a", "topic": "Who took part", "text": "Say who could join the cohort and how members were followed over time"}]}
```

| Field | Content |
|---|---|
| `name`, `version` | As the file prints them. `register` fails a version the file does not print |
| `variant`, `variant_labels` | The study's design and every design label of the file, as printed; `[]` when there are none |
| `extension_of` | `"none"`, or `{"name": …, "version": …}` of the base guideline |
| `journal` | `name`; `quote`, the journal's words that ask for the checklist; `version`, the version those words name, or `"not_stated"`; `source`, the saved instructions file (or a web address, or `user` when the user said it); `read`, the date; `user_decision`. The whole field is `"not_stated"` when no journal is involved |
| `source` | `path` of the copy (relative to `reporting-checklist/`), `sha256` from `hash`, `read`, `type` (`file`, or `web_page` with its `url`) |
| `licence` | `{"text": the statement exactly as printed, "where": footer, title page, web page}`, or `"not_stated"` |
| `items` | Every item, in the file's order: `id`, `topic`, `text` |

## Ids, topics and wording

- Ids are the checklist's own: 1a, 1b, 5a, 12, S3. A sub-point "(b)" in the rows of item 1 is `1b`. Never renumber, merge or split items.
- `text` is the item's wording as printed, for the registered design. Case, quotation marks, dashes, spacing and punctuation make no difference to the comparison; words do.
- `topic` is your own name for the item, at most 60 characters, never five words in a row of its wording. It is all of the item that leaves this folder.

## What register reports

| Row | On `fail` |
|---|---|
| `fields` | Complete `checklist.json` as above |
| `source_file` | Record the hash it names; if the file changed after registration, register it again from the file as it is |
| `version` | Write the version exactly as the file prints it |
| `journal` | Copy the journal's words again from the saved instructions; `version` must be in them |
| `journal_version` | The journal and the file disagree: ask the user (above) |
| `licence` | Copy the statement exactly as printed, or write `"not_stated"` |
| `count`, `ids` | An item is missing from the registration, or registered but not in the file: correct `items` |
| `wording` | Copy the item's wording again from the file, for the registered design only |

`not_checked` rows are not passes: a journal requirement that is not a saved file, a licence statement not recorded, ids and count of a text file. Report them to the user.

## The licence

Record the statement exactly as printed and say where it is. If the file prints none, write `"not_stated"`: silence is not permission. Either way the item wording stays in `checklist.json` and `source/`, and every file meant to be shared carries ids and topics only. Report the statement to the user as printed; do not interpret it.
