# Exclusion rules

Rules are written and dated before fielding, so that who is excluded cannot follow from what the data turn out to show. The audit flags; only a rule excludes. Without `survey/exclusion-rules.json` nobody is excluded.

## The indicators

`survey_audit.py` computes these per respondent and writes them to `flags.csv`. A flag is `1`, `0`, or empty when the answers it needs are missing ("not judged", never 0). An indicator whose column is absent is `not_checked` and has no column at all.

| Flag | True when | Setting and default (a convention) |
|---|---|---|
| `attention` | Wrong answers to attention items reach the setting. A blank is counted apart, in `attention_blank` | `attention_fail_min` 1 |
| `straightline` | One value throughout a block, on the answers as given before reverse scoring, with enough answers | `straightline_min_items` 5 |
| `long_run` | The longest run of identical answers in presentation order reaches the setting | `long_run_min` null: reported, never flagged |
| `fast` | Total duration under a share of the sample median, or under seconds per answered item | `fast_share_of_median` 0.33; `fast_seconds_per_item` null |
| `slow` | Total duration over a multiple of the median | `slow_multiple_of_median` 3 |
| `pause` | A gap between two page times reaches the setting | `pause_seconds` 1800 |
| `duplicate_id` | The ID occurred in an earlier row | none |
| `duplicate_answers` | The same answers to every item as an earlier row under another ID; one value throughout is left to `straightline` | `duplicate_min_answered` 0.5 (share answered) |
| `duplicate_ip`, `duplicate_panel` | The IP address or panel ID occurred in an earlier row | none |
| `break_off` | The last item column is blank (the answers stop early) | none |
| `open_text_empty`, `open_text_short`, `open_text_identical` | An open answer is blank; shorter than the setting in words or Han characters; the same as another respondent's | `open_text_short_units` 3 |
| `inconsistent` | A declared pair differs by more than its `max_difference` | per pair, declared |

Values that rules can compare: `attention_wrong`, `attention_blank`, `duration_s`, `longest_run`, `longest_pause_s`, `missing_share`, `pairs_inconsistent`. Three settings only shape the report: `attention_pass_low` 0.80, `attention_pass_high` 0.98, `item_missing_share` 0.10.

No default here comes from a study that justified it; they are values met in practice. The user may set each one, best from a paper they have read, and the report prints where every value came from. No standard deviation cut-off is used for straight-lining, because the same cut-off means different things in blocks of different lengths; the number of distinct values and the share of the most common answer are in `flags.csv` instead.

## Settings

A setting is a number, `null` (switched off), or an object:

```json
{"fast_share_of_median": {"value": 0.4, "source": "pretest-log.md, round 2: the fastest careful readers", "date": "2026-02-20"}}
```

The audit takes each setting from `audit-settings.json`, then from `exclusion-rules.json`, then the default. Put the thresholds the rules rest on in `exclusion-rules.json`, so that they are fixed with the rules.

## `survey/exclusion-rules.json`

```json
{"written": "2026-02-20",
 "settings": {"fast_share_of_median": 0.33, "straightline_min_items": 5},
 "rules": [
   {"id": "R1", "description": "Two wrong answers to the attention items", "when": ["attention_wrong >= 2"]},
   {"id": "R2", "description": "Two independent signals together",
    "when": ["fast", "straightline", "duplicate_answers", "open_text_identical"], "at_least": 2},
   {"id": "R3", "description": "A later submission under an ID already seen", "when": ["duplicate_id"]}]}
```

| Field | Content |
|---|---|
| `written` | The date the rules were agreed, `YYYY-MM-DD`; a rule may carry its own `written` |
| `settings` | The thresholds as they were when the rules were written |
| `id`, `description` | A short id, and the rule in words for the methods section |
| `when` | Conditions: a flag name alone means the flag is true; a value takes `>=`, `>`, `<=`, `<` or `=` and a number |
| `at_least` | How many conditions must hold; the default is all of them |

A respondent is excluded when any rule holds. When too few conditions hold but enough are not judged, the rule is not decided: the respondent stays in and is counted apart. The respondent who left the only attention item blank is the usual case.

## Combining signals

- One weak signal alone only flags: speed, a straight-lined block without reverse-keyed items, a short or repeated open answer, a slow total, a pause. Combine them with `at_least`.
- Signals that come from one behaviour are not independent: a respondent who straight-lines a long block is often fast too. When a rule asks for independent signals, say which ones count as one.
- A repeated ID is the same person twice: the rule says which copy stays. The audit flags the later rows.
- A rule with one condition (R1, R3 above) is a strong claim. Tell the user, and keep it only for a signal they would defend alone.
- Whether partial responses (`break_off`) are analysed is decided with the analysis plan in `researchzy-statistics`.

## Before and after fielding

| Status | When |
|---|---|
| `a_priori` | Dated on or before the day fielding started, and every threshold it rests on is the value it was written with |
| `post_hoc` | Undated; dated after fielding started; or a threshold it uses differs now from the rules file, or from the default when the rules file did not fix it |

The start of fielding is `fielding_start` in `audit-settings.json`; otherwise the earliest start time in the data. With neither, the rules' timing cannot be compared: each rule is `timing_not_known` and its exclusions are counted apart until `fielding_start` is declared. A post hoc rule still counts, and the report shows its exclusions apart. Never change a date. To change rules after the data are in, copy the file first (`exclusion-rules-2026-02-20.json`), then edit it with today's date; the report labels the changed rules.

## With and without

Excluded respondents are never deleted: `flags.csv` marks them, and the analysis applies the rules. The analysis with and without the excluded respondents, and any comparison of responders with non-responders, belong to `researchzy-statistics` (plugin `researchzy-manuscript`, when installed). A low exclusion rate says nothing about non-response.
