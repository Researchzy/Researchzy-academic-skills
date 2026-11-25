# Answer outlines

An outline is what the student looks at the evening before, not what they recite. A memorised paragraph breaks at the first follow-up; an opening sentence and two or three anchors survive it, because the student can find the page and talk from it.

## Shape

| Part | Content |
|---|---|
| `opening` | One sentence that answers the question directly. No preamble, no thanks for the question |
| `points` | Two to four short fragments that carry the answer, each one a fact from the thesis or a reason |
| `anchors` | Where the support is: a printed page with a table or figure on it, or a quote from it |
| `level` | How the answer defends: `defend`, `bound` or `adopt` (below) |
| `not_done` | Only for an analysis the thesis does not contain: `{"analysis": …, "because": …}` |
| `allow` | Only for numbers that are not in the thesis: `"number | where it comes from"` |

Write points as fragments: "312 of 364 returned, 85.7%", not "We were very pleased that a large share of the questionnaires…". Write the outline in the language of the defence. Size it for an answer of one to two minutes when spoken: a convention the user may change; only the department's notice sets real limits.

## Anchors

- `page` is the printed page number (`"76"`, `"vii"`, `"76-77"` for both ends of a range), never the PDF page number, unless `thesis-pages.txt` says no page shows a number.
- `display` is a table or figure as the thesis numbers it: `"Table 4.3"`, `"Figure 3.2"`, `"表4-3"`, `"图 3.2"`. The check finds its caption and fails when the caption is on another page.
- `quote` is copied word for word from `thesis-pages.txt`: at least five words, or twelve Chinese characters. Do not repair or translate it.
- A page alone is no anchor: give the table, figure or quote on it, or use a number that is printed on it.
- Several anchors are fine; the numbers in the outline are searched on all of them first.

## Defence levels

| Level | When | The answer |
|---|---|---|
| `defend` | The thesis contains the evidence that answers the question | State the answer and point to it |
| `bound` | The question touches a real limit | Admit the limit plainly, then say how far it reaches and which results it leaves standing |
| `adopt` | The question suggests something the thesis did not do and could reasonably have done | Agree it is worth doing, say what it would take, and place it in future work |

Choose the level from the evidence, not from what sounds strongest. A `defend` answer without an anchor is not a defence. An examiner who sees a limit bounded honestly usually moves on; one who hears it denied keeps asking.

## Analyses that were not done

When the question asks for something the thesis does not contain (a robustness check, a second dataset, an interview round, an ablation), the outline says so:

```json
"not_done": {"analysis": "robustness check with another measure of commitment",
             "because": "the survey contained a single measure; a second one would have lengthened it by a third"}
```

Never write what the analysis would probably have shown, and never cite a page as if it held such a result: the check fails a number that is not in the thesis and a page that holds no supporting table, figure, quote or number. If the reason is not in the thesis or the student's notes, write `[Author input needed: why this was not done]` and ask the student.

## When the student does not know

Prepare the outline so that the honest route is easy:

1. Ask the examiner to restate or narrow the question.
2. Answer the part that the thesis covers, with its anchor.
3. Say what would be needed to answer the rest and how it could be checked.
4. Never improvise a number, a reference or a result.

## Numbers

- Use numbers as the thesis prints them. A rounding of a printed number is found (86% for 85.7%); a different number is `NOT_FOUND` (87.5% for 85.7%).
- Page, table, figure, chapter, section, equation and hypothesis references are not treated as numbers; numbers that touch Chinese characters are (样本量为312人).
- `allow` is for numbers from outside the thesis: a figure from a paper the user supplied, the year of a paper from a saved search, a date of the defence. Each entry names whose number it is: `"0.71 | Smith et al. (2024), Table 2, supplied by the user"`. Using `allow` to silence a number that belongs to the thesis is fabrication: correct the number instead.

## Example (an invented thesis)

```json
{"opening": "The register was the only complete list of active volunteers, so it set the sampling frame.",
 "points": ["The register covered 14 clubs.", "Unregistered helpers are named as a limit."],
 "anchors": [{"page": "33", "quote": "The sampling frame was the 2023 membership register of 14 clubs"},
             {"page": "83", "quote": "No robustness analysis with alternative measures of commitment was carried out"}],
 "level": "bound"}
```

```json
{"opening": "假设3没有得到支持，说明组织承诺对留任意愿的作用小于预期。",
 "points": ["β=0.04，见表4-3。", "样本量为312人，检验力的局限写在第五章。"],
 "anchors": [{"page": "76", "display": "表4-3"}], "level": "bound"}
```
