# Screening

Two stages: title and abstract (`ta`), then full text (`ft`). The model screens, after the user has calibrated it on a sample. Every exclusion carries a protocol code and a quote that `check` finds in the record.

## Decision lines

One JSON object per line in `systematic-review/decisions/<stage>-<nn>.jsonl`, recorded with `sr_ledger.py decide <file>`.

| Field | Content |
|---|---|
| `record` | The ledger id, such as `R0042`; a duplicate's id counts for its whole group |
| `stage`, `decision` | `pre`: `remove`; `ta`: `include`, `exclude`, `unsure`; `ft`: `include`, `exclude`, `not_retrieved` |
| `reviewer` | `model` for your own decisions, `user`, or the person's name |
| `code` | For an exclusion: an E code of the protocol |
| `quote` | For an exclusion: at least three words copied from the title or abstract (`ta`) or from the full text (`ft`) |
| `locator` | For a full-text exclusion: page or section, such as `p. 4, Methods` |
| `study` | For a full-text inclusion: one label for all reports of the same study, such as its NCT number |
| `reason`, `note` | `reason` for a removal before screening; `note` of what was tried for `not_retrieved` |

```json
{"record": "R0042", "stage": "ta", "decision": "exclude", "code": "E2", "quote": "revision of a failed knee replacement", "reviewer": "model"}
{"record": "R0043", "stage": "ta", "decision": "unsure", "reviewer": "model"}
{"record": "R0051", "stage": "ft", "decision": "exclude", "code": "E1", "quote": "allocated by alternation", "locator": "p. 3", "reviewer": "model"}
{"record": "R0057", "stage": "ft", "decision": "include", "study": "NCT01234567", "reviewer": "model"}
```

`decide` rejects a line that breaks a rule and says why; correct those lines and record them again. The last decision for a record and stage is the final one, and earlier ones stay in the ledger. `pre` with `remove` is for a record that is no study report at all, such as a retraction notice, and needs a `reason`.

## Title and abstract

- Read each record. A script may sort or batch the records for reading but never decides: keyword rules miss what a reader sees and exclude what a reader would keep, and the calibration says nothing about them.
- Include a record that may meet every I criterion. Exclude only when the title or abstract shows that a criterion fails, and quote the words that show it: the design for E2, the population for E3, the intervention for E4, the comparator for E5. A whole title is a quote only when the title itself shows the reason.
- When unsure, decide `unsure`: the record goes to full text. Information that is missing is no reason to exclude.
- Without an abstract, exclude only when the title clearly fails a criterion (`check` lists these for a second look); otherwise `unsure`.
- When several criteria fail, use the first of their codes in `exclusion_order`.
- Never decide from the journal, the authors or the citation count.
- Record decisions in batches of about 50 records (convention), so that rejected lines are corrected early.

## Calibration

Before the model screens the bulk of the records:

1. `sr_agreement.py sample --seed <integer>` draws 50 undecided records, or 10% of them if that is more, at most 100. It writes `calibration/round1-user.csv` and `round1-model.csv` with titles, abstracts and an empty `decision` column.
2. Fill `round1-model.csv` first: `include`, `exclude` or `unsure`, and the `code` of each exclusion.
3. Then give the user `round1-user.csv`: they fill `decision` in a spreadsheet, or answer in the chat while you write their answers into the file. Show none of your decisions before they have finished.
4. `sr_agreement.py score --round 1` writes `calibration/round1-score.md`: kappa (unsure counts as include), agreement, include recall and the disagreements. A scored round is final.

| Status | Do |
|---|---|
| `passed` | Screen the remaining records |
| `below_threshold` | Stop. Go through the disagreements with the user, sharpen the criteria, record the amendment with `--results-seen yes`, and draw a new round with a new seed |
| `not_assessable` | Kappa or recall cannot be computed (the user included none of the sample, or every record fell in one category): draw a new round |

When the user included fewer than five records of a sample, say that the recall rests on few records and offer a further round (convention).

Then record the final title-abstract decisions of the sampled records: the user's decision with `reviewer: user`, and for each of the user's exclusions a code and a quote from the record. After an amendment, screen the records of the earlier rounds again under the new criteria.

If the user declines to screen, record an amendment with `user_screens: false` and the `declined_reason`. `check` then warns MODEL_ONLY_SCREENING, and the methods and the limitations say that the model screened alone.

## Audit of the model's exclusions

Offer it after title-abstract screening; it is optional. `sr_agreement.py sample --audit --size <n> --seed <integer>` draws n of the model's exclusions; the user decides them in `calibration/audit1-user.csv` without seeing the model's reasons; `score --audit` lists the wrong exclusions or, when there are none, the most that could still be wrong at 95% confidence. With many exclusions and no error found, about 60 records bound the share near 5% and about 30 records near 10%. Each wrong exclusion goes to full text; find the code behind it and screen the model's exclusions under that code again. A spot check can find problems; it cannot prove there are none.

## Full text

1. For each record included or unsure at `ta`, get the full text: `get_pdf_download` with its `corpusId` (follow the PDF rules of the `researchzy` skill: download before the URL expires and check that the file is a PDF), then `researchzy-download` (plugin `researchzy-reading`, when installed), then ask the user. Do not write your own downloader or call services that ask for an email address. A registry record's full text is its registry entry.
2. Save the text as `systematic-review/fulltext/<record>.txt` with a line `[[page N]]` at the start of each page, for example by extracting it with PyMuPDF. Keep the PDF beside it. Never write a signed download URL into any file.
3. Decide `include` with a `study` label, `exclude` with code, quote and locator, or `not_retrieved` with a `note` of what was tried. `not_retrieved` is not an exclusion: the flow counts it as a report not retrieved.
4. A trial's registration, conference abstract and journal article are three reports of one study and take the same `study` label. `check` warns when included reports share a PMID or an NCT number under different labels.

## Quotes

- Copy the words from the record: at least three words, from one passage, without an ellipsis or a paraphrase.
- The check ignores case, spacing, punctuation other than signs and comparison marks, ligatures, and a word split by a hyphen at a line end. A changed word, number or sign makes the quote fail.

## What check reports

| Finding | Do |
|---|---|
| NO_DECISION, STAGE_TRANSFER_LOSS | Screen the record at the stage named |
| NOT_AT_STAGE | A full-text decision exists for a record excluded at title-abstract: correct one of the two |
| QUOTE_NOT_FOUND, FULLTEXT_MISSING | Copy the quote again from the record, or save the full text; never change a record |
| CODE_NOT_IN_PROTOCOL, CODE_CHANGED_SINCE_DECISION | Screen the record again under the current protocol |
| SEARCH_INCOMPLETE, EXPORT_COUNT_MISMATCH, SEARCH_TOTAL_UNKNOWN | Fetch the rest, or correct the log with `search --id`; an explained gap stays a warning |
| DUPLICATE_CANDIDATES_PENDING | Settle each pair with `dedup --merge` or `--distinct` |
| CALIBRATION_MISSING, CALIBRATION_BELOW_THRESHOLD, MODEL_ONLY_SCREENING | See Calibration |
| SEED_NOT_FOUND | See searching.md, "Known papers" |
| PROTOCOL_CHANGED_UNRECORDED | Record the change with `protocol --amend` |
| EXCLUDED_ON_TITLE_ONLY, POSSIBLE_SAME_STUDY | Look again; keep the decision or correct it |
| TITLE_AS_QUOTE | Replace the quote with the words of the title or abstract that show the reason for the code |
| EXTRACTION_FORMAT, EXTRACTION_NO_SOURCE, EXTRACTION_QUOTE_NOT_FOUND, EXTRACTION_STUDY_NOT_INCLUDED | Correct the row from the full text (prisma.md, extraction table) |
| EXTRACTION_VALUE_NOT_IN_QUOTE, EXTRACTION_STUDY_MISSING | Quote the words that carry the number; add the missing study's rows or say why it has none |
