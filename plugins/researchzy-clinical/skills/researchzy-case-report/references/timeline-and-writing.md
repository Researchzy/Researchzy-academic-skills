# Timeline and writing

## timeline.csv

One row per event, in the order in which the events happened. The example is invented.

```csv
time,event,where,quote,exact_date,approved_by
Day -28,drug X started,notes.md line 3,"four weeks after starting drug X",,
Day 0,itchy eruption on both forearms and the trunk,notes.md line 3,"widespread itchy eruption on both forearms",,
Day 2,punch biopsy of the left forearm,notes.md line 5,"punch biopsy from the left forearm",,
第3天,停用药物X,notes-zh.md 第8行,停用药物X，开始外用糖皮质激素,,
Week 6,eruption resolved,notes.md line 9,"eruption fully resolved without scarring",,
```

| Column | Rule |
|---|---|
| `time` | A relative time and nothing else: `Day 0`, `Day -28`, `Week 6`, `Month 3`, `Year 1`, `Hour 4`, a range such as `Day 3-5`; in Chinese `第0天`, `第6周`, `第3个月`, `3天前`. Choose day 0 with the clinician: the first visit, admission or onset |
| `event` | What happened, in a few words, without dates, names or places |
| `where` | The place in the notes: file and line, or section |
| `quote` | Words copied from the notes that support the row, three or more (a Han character counts as one) |
| `exact_date`, `approved_by` | Optional. A calendar date only when the user wants it in the report and the patient's consent covers it; `approved_by` names who approved it, by role, not by name |

The delimiter may be a comma, a semicolon or a tab. `check` converts each time to days (a month is 30.44 days) and fails: a time it cannot read, a row earlier than the row before it, a quote it cannot find in the notes given with `--notes`, a row without its place in the notes, and an exact date without `approved_by`. Rows with the same time keep their order. Where events are close together, use one unit, so that "Month 1" and "Week 5" are not ordered by rounding.

## Sections

The journal's instructions and the checklist file the user supplied decide the sections, their names, their order and their length. Record the checklist's name and version as printed on the file, and the date you read it. If the user has neither, write introduction, case presentation and discussion, and say that the structure follows no checklist. Never rebuild a checklist from memory: checklists get new versions, and journals ask for particular ones.

## Writing the case

- Facts come from the notes. A finding, value, dose, date or reason the notes do not give becomes `[Author input needed: …]`.
- Report what was done and found in time order, with the relative times of the timeline. Keep the negative findings the clinician recorded: they show what was ruled out.
- The diagnostic reasoning is the clinician's. Write the differential and the reasons for the final diagnosis only as the notes give them.
- Doses are the patient's, as recorded. Never turn one into a recommendation.
- Cause: write the clinician's assessment as theirs ("the treating dermatologist judged the reaction probably related to drug X"), with the facts behind it in the notes: timing, what happened after withdrawal, any re-exposure. If the clinician used a causality tool, report its name, version and the result they recorded; never score it yourself.
- Discussion: this one case against the reports of Table S1. Say what the case adds, what it cannot show and how it differs from them. No review of the literature beyond Table S1 and the sources the user gave.
- The patient's perspective, if included, is the patient's own words, given for this report.

## Leads from the check

The check lists these phrases by position; none of them fails. Reread each one and decide.

| Lead | Wording | What to do |
|---|---|---|
| `rarity` | first, only, never reported, unique; 首例, 唯一…例, 未见报道, 仅N例 | Write what the dated search found: "the searches in Table S1 found no earlier report of …". A rarity claim in the same sentence as the date of a logged search is not listed |
| `proof` | proves, this case shows; 证明 | One case cannot prove: "suggests", "is consistent with" |
| `cause` | caused, led to, induced; 导致, 引起 | Keep it only as the clinician's assessment, named as theirs |
| `advice` | should, must, we recommend, contraindicated; 应当, 不应, 必须, 建议 | Remove advice on practice. A case report may say what a reader could consider, never what patients should take |
| `dose` | 20 mg daily; 剂量, 每日 | Confirm that each dose is the patient's, from the notes, and not advice |
| `unique_description` | the only … on the island; 唯一的… | A quasi-identifier: ask the clinician, then generalise it or leave it out |

## Common failures

| Failure | Instead |
|---|---|
| "First" or "only" with no search behind it | The dated, logged search and its count |
| Events without times, or with calendar dates | A relative time for each event |
| Rarity offered as the reason to publish | What the case teaches a reader who meets the next one |
| One case generalised ("elderly patients should not use drug X") | A claim about this patient only |
| Cause asserted as fact | The clinician's assessment, with the withdrawal and re-exposure facts |
| A literature review in the discussion | The reports of Table S1 and the user's sources |
| Promotional or emotive words | Plain description |

Two or more patients make a case series, which this skill does not write.
