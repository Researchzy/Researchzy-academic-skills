# The item map and scoring

`psychometrics/items.json` declares what the data must agree with: which items form which construct, which are worded the other way, the response scale and the missing codes. Scoring, the CFA syntax and every construct table come from it, so a mistake here travels everywhere. Write it from the user's codebook, show it to the user, and record the day they confirmed it.

## The format

```json
{
  "data": "data/survey.csv",
  "id": "resp_id",
  "missing": ["-99", "-98"],
  "reversed_in_data": false,
  "group": "sector",
  "marker": ["mk1"],
  "constructs": {
    "AUT": {"label": "Autonomy", "items": ["aut1", "aut2", "aut3", "aut4", "aut5"], "reverse": ["aut4"],
            "min": 1, "max": 7, "categories": 7, "source": "user's codebook, sheet 1", "licence": "open"},
    "MEA": {"label": "Meaning", "items": ["mea1", "mea2", "mea3", "mea4"], "reverse": [],
            "min": 1, "max": 7, "categories": 7, "source": "invented example scale, p. 4", "licence": "unknown"}
  },
  "dropped": {},
  "confirmed": "2026-11-18"
}
```

The example is invented; so are its scales.

| Key | Rule |
|---|---|
| `data` | The data file, relative to the working directory. `--data` overrides it |
| `missing` | Codes that mean "no answer" in any column, as text. A `.sav` file's own user-missing values are applied too, and listed in `scoring.json` |
| `reversed_in_data` | `true` when the file already holds the reverse items reversed, `false` when it holds the answers as given. Ask the user; the script refuses a map without it |
| `constructs` | Name: letters, digits and `_` (the CFA syntax uses it). `items` are column names, two or more, each in one construct only |
| `reverse` | Items worded against the construct. An empty list when there are none |
| `min`, `max` | The lowest and highest response the scale allows, not the lowest and highest observed |
| `categories` | Response options; for the ordinal decision. Optional |
| `source`, `licence` | Where the scale comes from (paper and page, or "the user's own"), and `licensed`, `open` or `unknown` |
| `group`, `marker`, `id` | Optional: the column that defines groups for invariance, the marker items, the respondent id |
| `dropped` | Items the user removed, each with the reason and the date: `{"aut5": "…, 2026-11-20"}` |
| `confirmed` | The day the user confirmed the map. Without it `score_items.py` reports a lead |

## Reverse scoring

A reverse item is scored as (min + max) − x, which works for scales that start at 0 as well as at 1. It is applied only when `reversed_in_data` is `false`. Reversing an item the file already holds reversed turns it back the wrong way: the item then correlates negatively with the rest of its scale, and `score_items.py` reports it.

A negative item-rest correlation is evidence, not proof, of a keying problem: a badly written item can do the same. That is why it is a lead for the user to settle, never an automatic reversal.

## What `score_items.py` writes

- `<data>.scored.csv`: every column of the data, with missing codes emptied and the declared reverse items scored. The analysis reads this copy, never the original.
- `scoring.json`: the SHA-256 of the data file, of `items.json` and of the copy; per construct the complete n, alpha and every item-rest r before and after scoring, and the response categories each item uses; problems and leads.
- `scoring.md`: the same as tables, for the user.

| State | Meaning | Exit code |
|---|---|---|
| problem | A value outside min to max that is not a missing code, text in a numeric item, an item with one value | 1 |
| lead | A negative item-rest r after scoring, a negative alpha, an item using fewer categories than `--few-categories` (a convention, default 5), value labels running the other way, no confirmed date | 0 |

Values outside the scale are emptied in the copy and counted, never recoded. The usual cause is an undeclared missing code: ask, then add it to `missing`. Show each lead to the user, and record what they decided in `items.json` or the notes of the analysis.

## `.sav` files

With pyreadstat installed, the script reads the user-missing values and the value labels. The labels let it see an item whose response scale was entered the other way round (1 = "agree" where the other items have 1 = "disagree"). Without pyreadstat, ask the user to export CSV, or to agree to installing it.

## Licences and items

- Never copy a scale's items into any output, from the user's files or from memory. Refer to items by their column names and, when needed, by a short paraphrase the user approves.
- `unknown` licence: name the scale and its source, and tell the user to check the terms before publishing the items in a paper or an appendix.
- With the `researchzy` plugin connected, the original validation paper can be found with `search_papers` (by the scale's name; the index matches title and abstract words only) and read through `get_paper_files`. Record its DOI, the number of items, the keyed items and the published structure with page numbers, so that the user's results can be set beside them. Not found means `not_checked`, not "no such paper".
