# Similar published cases

Table S1 lists published reports of cases like this one. Every row comes from a search run and saved in this session, every filled cell carries words quoted from the saved abstract or full text, and the draft states the number of reports the search found, with its date. Nothing comes from memory: a well-known case that the searches did not return stays out, however sure you are of it.

## Searching (Researchzy connected)

`search_papers` matches keywords in titles and abstracts only. It has no publication-type filter, no stemming, no author search and no cited-by lists, and its `total` is approximate. So:

- Put "case report" in the query, and search the singular and the plural separately: "drug X eruption case report", "drug X eruptions case reports".
- Search each synonym of the finding separately: eruption, exanthem, rash; 皮疹 and 药疹 when reports may be in Chinese.
- Use `yearFrom`, `fieldOfStudy` or `sort` only when they help, and log them. A page holds up to 50 results; read further pages while there are more.
- Log every search, also those that found nothing useful.

Save each result exactly as the tool returned it, in `case-report/searches/<id>.json`, and log the search in `case-report/searches.json` (invented example):

```json
{"searches": [
  {"id": "s1", "tool": "search_papers", "query": "drug X eruption case report", "filters": {"yearFrom": 2000},
   "sort": "relevance", "total": 4, "date": "2026-11-18", "file": "searches/s1.json"}]}
```

`id`, `query`, `date` (YYYY-MM-DD, the day it ran), `total` (the number the tool returned) and `file` (relative to `case-report/`) are required. `check` fails a search whose saved result cannot be read, or whose `total` differs from the one in the saved result.

## Reading and choosing

- Agree with the user what counts as similar (the same drug and reaction, the same finding in the same organ) and write that rule in the table's note.
- Read each abstract in the saved result. For a full text, use `get_paper` or `researchzy-download` (plugin `researchzy-reading`, when installed), save the text as `case-report/sources/<id>.txt`, and name it in the row's `source`.
- Leave out a report you cannot read, and say so in the note.

## similar-cases.json

```json
{"columns": ["age", "onset", "outcome"],
 "rows": [
  {"id": "r1", "search": "s1", "doi": "10.1000/case.1",
   "cells": {"age": {"value": "67", "quote": "We describe a 67-year-old man"},
             "onset": {"value": "6 weeks", "quote": "six weeks after starting drug X"},
             "outcome": "not reported"}},
  {"id": "r2", "search": "s1", "title": "Report 2 of an eruption with drug X", "source": "sources/r2.txt",
   "cells": {"age": "not reported", "onset": "未报告",
             "outcome": {"value": "resolved", "quote": "the rash resolved after the drug was stopped"}}}]}
```

This example is invented, and so are its papers.

| Field | Rule |
|---|---|
| `columns` | The facts compared, chosen for this case: for example age, sex, exposure, onset, findings, treatment, outcome |
| `search`, then `doi` or `title` | The logged search and the paper in its saved result. `check` fails a row that is not there |
| `source` | Optional: a saved full text, relative to `case-report/`. Without it, the saved title and abstract are the source |
| A cell | `{"value": …, "quote": …}`, or `not reported` (`未报告`). The quote is copied from the source, three words or more; every number of the value must appear in the quote, in figures or in words |

An abstract that does not give the patient's age gives `not reported`, never an age guessed from the title or remembered from elsewhere.

## In the draft

- The count is the number of rows, stated with the search: "The searches in Table S1 (Researchzy index, 18 November 2026) found 3 reports of …". Keep it in one sentence that names the search or Table S1; `check` compares every number of reports or cases in such a sentence with the rows. Avoid abbreviations with full stops in that sentence ("Nov."): they end it early.
- Never write "only N cases have been reported", "this is the first case" or "no case has been described". The index is one source, read on one day: write what the search found.
- A rarity claim belongs only in a sentence that carries the date of a logged search.

## Without Researchzy

The table and the count sentence are `[Evidence needed: similar published cases, from a dated search]`. Tell the user that with Researchzy connected the skill can run, save and quote these searches.
