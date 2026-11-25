# Reading the report

`report.md`, `abstracts.md`, `blind.md` and `anonymity.md` are working files for the user. Each script also prints a JSON summary: `ok`, the count per status, and every row.

## The four states

| Status | Means | Tell the user |
|---|---|---|
| `fail` | Certain: the two places disagree, or a declared item is missing | Each finding with file, line or paragraph, and the snippet |
| `pass` | Checked and agreeing | The count, in one line per check |
| `not_checked` | The check could not run: no `.bib`, no `.aux`, no list of abbreviations, no convention, nothing at a place | What was missing and what supplying it would add. Never call it a pass |
| `manual` | Needs a person: numbers removed from the blind copy, the pages listed in [blind review](blind-review.md) | What to look at and where |

A lead is not a status. Leads sit under their check, grouped, at most twelve per group with a count of the rest. Present them as questions ("Table 3-5 reports N = 298 where the others report 312: is an exclusion stated?"), never as errors.

## Presenting failures

- Order: key numbers and table N first (a reviewer quotes them), then hypotheses, citations, floats, abbreviations, the abstracts and the blind copy.
- Say which places disagree and quote both. Never say which one is right: the user knows which number the analysis produced. "The abstract has 312 and chapter 3, line 14 has 321" is the form.
- Group repeats: one abbreviation with two long forms is one item listing both places.
- After the user fixes the thesis, run the same commands again and report what changed. Never mark a failure as resolved without a new run.

## What each failure asks of the user

| Row | Ask |
|---|---|
| A key number not found | Which value is right, and every place to correct. If the declaration was wrong, correct `audit.json` with the user, then run again |
| N of a table | Whether the table uses another sample; if so, the exclusion must be stated in the text, and the declaration may list both values |
| Two long forms | Which long form the thesis uses; the list of abbreviations follows the choice |
| List against the text | Remove the unused entry, or add the missing one |
| A callout to a missing float | Whether the float was renumbered, merged or removed |
| A float never called | Where the text should refer to it, or whether the float can go |
| A cited key or author-year citation with no entry | The missing entry; whether the work exists goes to `researchzy-reference-check` (plugin `researchzy-manuscript`, when installed) |
| An entry never cited | Cite it where it was used, or drop it from the list |
| A hypothesis missing from the results or the conclusion | Report its test, supported or not, in both places |
| An undeclared hypothesis in the results | Whether it was proposed under another label, or must be added to the hypotheses |
| A number in one abstract only | Which value is right, in both abstracts |
| Identity hit or changed number in the blind copy | Remove the identifier from the blind copy; make the blind copy's numbers match the full copy |

## What the report does not say

That the thesis is ready, that it meets the school's format rules, that the statistics are right, or that the references exist. Say so when you hand over, together with each `not_checked` row and each `manual` item.
