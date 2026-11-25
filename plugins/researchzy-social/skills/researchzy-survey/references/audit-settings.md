# Declaring the export: `survey/audit-settings.json`

The audit computes only what this file declares. Draft it from the `columns` listing and `design.md`, show the user the roles, and run nothing until they confirm.

## Reading the export first

```sh
python3 "$SKILL_DIR/scripts/survey_audit.py" columns data/export.csv --header-row 1 --skip-rows 2 3
```

It prints every column with its number, the text in the skipped rows under it (often the question wording), how many cells are filled, three example values and a hint (`id`, `duration`, `ip`, `time`, `open_text`). The hints are guesses from names and values. Some platforms write the question text, or internal ids, in rows under the column names: those rows go in `skip_rows`. A CSV with Chinese text in a legacy encoding (GB18030) is read too, and a quoted cell may span lines.

## The keys

| Key | Content |
|---|---|
| `header_row`, `skip_rows` | The row number of the column names (default 1), and the rows to skip, by row number as a spreadsheet shows them |
| `delimiter`, `sheet` | Only when the detected delimiter or the first sheet is wrong |
| `id` | The respondent ID column |
| `blocks` | One per page or matrix: `name`, `items` in the order shown, `scale` `[lowest, highest]`, `reversed` (the reverse-keyed items), `randomised` (true when the order varied), `order_column` (a column listing the items in the order shown to each respondent, separated by `|`, `,` or `;`) |
| `recoded` | `true` when the file already holds reverse-scored values for the `reversed` items; the audit undoes it for its checks |
| `attention` | A list of `{"item": column, "expected": [accepted answers]}`, as numbers or as the labels the file holds |
| `duration` | `{"column": ..., "unit": "seconds"}` (`seconds`, `minutes`, `milliseconds`; "300秒" is read as 300), or `{"start": ..., "end": ...}` with two timestamp columns |
| `start_time`, `time_format` | A start timestamp column, used for the start of fielding; `time_format` (as in `%d.%m.%Y %H:%M`) when timestamps are not ISO-like |
| `fielding_start` | The first day of fielding, `YYYY-MM-DD`: declare it whenever it is known |
| `page_times` | `{"columns": [...], "kind": "timestamps"}` for page submit times, or `"kind": "seconds"` for time spent per page |
| `ip`, `panel_id` | The IP address and panel ID columns, when the export has them |
| `open_text` | The open-answer columns |
| `pairs` | `{"items": [a, b], "max_difference": 1, "reversed": true}`: two items that should agree; `reversed` when b is worded the other way; an optional `scale` |
| `missing` | Further codes meaning "no answer" (`-99`, `跳过`). Blank cells, `NA` and similar are always missing |
| `value_labels` | Answer labels and their numbers, when the file holds labels (`{"非常不同意": 1, "非常同意": 5}`) |
| `settings` | Thresholds ([exclusion rules](exclusion-rules.md)); leave out those the rules file fixes |

An unknown key stops the script with exit code 2, so a misspelt key is never silently ignored.

## An example

Invented for this file:

```json
{"header_row": 1, "skip_rows": [2],
 "id": "编号", "fielding_start": "2026-03-02",
 "duration": {"column": "作答时长（秒）", "unit": "seconds"},
 "blocks": [{"name": "workload", "items": ["W1", "W2", "W3", "W4", "W5", "W6"], "scale": [1, 5], "reversed": ["W4"]},
            {"name": "burnout", "items": ["U1", "U2", "U3", "U4", "U5"], "scale": [1, 7], "randomised": true}],
 "attention": [{"item": "AC1", "expected": [2]}],
 "open_text": ["Q30"], "missing": ["-99"]}
```

## What to confirm with the user

Show one table: column, role, and for blocks the scale and the reverse-keyed items. Ask in particular:

- Are the item values the answers as given, or already recoded? Straight-lining must be judged on the answers as given.
- Was the item order randomised, and does the export hold the order shown? Without it the longest run is `not_checked`.
- Which value passes each attention item?
- Is there an IP or panel ID column? If not, those checks are `not_checked`, and the report says so.

## After the run

| In the summary | Do |
|---|---|
| `columns_not_found` | A typo: correct the name. A column the export lacks: tell the user; its indicator stays `not_checked` |
| `not_read` | The `.xlsx` or `.sav` reader is not installed: ask for a CSV export, or ask before installing |
| Out-of-range or non-number answers in the report | Check the scale and the missing codes; declare a code in `missing` only when the user confirms it means no answer |
| Exit code 2 | Fix the file the message names, and run again |

Keep every version of `audit-settings.json` the report was made from; its SHA-256 is in the report.
