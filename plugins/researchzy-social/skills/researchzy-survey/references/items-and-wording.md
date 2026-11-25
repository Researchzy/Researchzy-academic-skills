# Items and wording

## `survey/items.csv`

One row per item, in the order respondents see them. Column names may be English or Chinese; `item_screen.py` reads both, and the values in brackets.

| Column | 中文 | Content |
|---|---|---|
| `construct` | 构念 | What the item measures; for other rows a short label (`attention`, `demographics`) |
| `item_id` | 题项编号 | The column name the export will use, when known (`A1`, `Q5_1`) |
| `text` | 题项文字 | The wording. Empty for a scale whose permission is `unknown` |
| `keying` | 方向 | `forward` or `reverse` (正向, 反向) |
| `source` | 出处 | The paper with the page or table the item comes from, or `user's own` |
| `permission` | 授权 | `licensed`, `open` or `unknown` (已授权, 开放, 未知) |
| `changes` | 改动 | Every change from the source: wording, anchors, number of points, items dropped or added |
| `block` | 区块 | The page or matrix the item appears in |
| `role` | 角色 | `predictor`, `outcome`, `mediator`, `moderator`, `covariate`; or `attention`, `marker`, `open`, `demographic`, `other` (自变量, 因变量, 中介, 调节, 控制, 注意力, 标记, 开放题, 人口学, 其他) |
| `wave` | 波次 | The wave, when the survey has several |
| `expected` | 期望答案 | For an attention item, the answer that passes |

```csv
construct,item_id,text,keying,source,permission,changes,block,role,wave,expected
workload,W1,I have more work than I can finish in a normal day.,forward,user's own,open,,page 2,predictor,1,
workload,W2,,forward,"[Author input needed: development paper], Table 1",unknown,,page 2,predictor,1,
attention,AC1,For this row please choose "disagree".,,,,,page 2,attention,1,2
```

The rows are invented for this file. W2 belongs to a scale whose permission is not known, so it has no text.

## The licence card

`survey/scales.md` holds one card per published scale, written before any item text:

```markdown
## Team support (planned: 6 items)

- Named by the user as: "the support scale from a 2004 paper"
- Development paper: not identified [Author input needed: the paper, or its DOI]
- Held by the user: nothing yet
- Permission: unknown. Evidence: none. Checked: 2026-11-18
- Structure: [Author input needed: items per dimension, points and anchors, reverse-keyed items, each with page or table]
- Planned changes: none
```

| Field | Rule |
|---|---|
| Development paper | The paper that introduced the scale, from the user's file or a tool result in this session, not a paper that only used it |
| Permission | `licensed`: written permission or a licence the user holds. `open`: the paper or its publisher states a licence that covers this use; quote it with page or URL and the date read. `unknown`: anything else, including "everyone uses it" |
| Structure | Item count, points, anchors, reverse-keyed items, each with page or table, never from memory |
| Planned changes | Each one also goes into `changes` in `items.csv`, and into the methods |

A scale described only by year or topic is not identified. While permission is `unknown`, plan with its structure, write no item text, and tell the user who could grant it, if the paper names someone. Translating a scale is outside this skill.

## Finding the paper with Researchzy

With the `researchzy` plugin connected:

1. `search_papers` with the scale's name or its construct and "scale", sorted by `citationCount`. Show the user the candidates (title, year, venue, DOI); the user says which one their scale comes from.
2. Read the full text through `get_paper_files`, or the user's copy. Record the item count, response format and reverse-keyed items, each with page or table and a quote of a few words.
3. Record the result in the card with the date. No result, or no full text, is `not_checked`, not "not found anywhere".

The index matches words in titles and abstracts only: a scale introduced inside a paper about something else may be missed, and nothing in it states licence terms.

## Wording problems

The examples are invented for this file.

| Problem | What shows it | Example | Rewrite |
|---|---|---|---|
| `double_barrelled` | Two objects or two claims; one answer cannot fit both | "My manager is fair and approachable." 我的上级公正而且平易近人。 | Two items: "My manager is fair." / "My manager is approachable." |
| `leading` | The wording suggests the expected answer, or claims others agree | "Don't you agree that flexible hours help families?" 难道你不认为弹性工作制有利于家庭吗？ | "How do flexible hours affect your family time?" with a scale running both ways |
| `double_negative` | Two negations, so agreeing means affirming a denial | "I do not disagree that meetings are useful." 我并非不认可例会的作用。 | "Meetings are useful." 例会是有用的。 |
| `absolute` | always, never, all: one exception forces the extreme | "I always read every email." 我总是阅读每一封邮件。 | "How often do you read your email?" with a frequency scale |
| `too_long` | Several clauses, a condition, a time frame and an object at once | 在过去一年中，当工作任务较多且时间紧迫的时候，我通常会主动和同事讨论分工。 | Keep one idea; move the time frame into the block instruction |
| `jargon` | A term the respondents may not share | "My team has high psychological safety." | Describe what happens: "I can admit a mistake in my team without fear." |
| `unknowable` | Asks what the respondent cannot know | "My colleagues feel valued." | "I feel valued by my colleagues." |

A conjunction is not always a problem: "work-life balance" (工作和生活的平衡) is one concept. A negated item is not a problem by itself; a reverse-keyed item is often a negation on purpose. Judge each candidate in context.

## `survey/wording-review.csv`

One row per problem found, by the agent or the user. Items without a problem need no row.

```csv
item_id,problem,words,rewrite,decision,decided_by
S3,double_barrelled,"fair and approachable","S3a: My manager is fair. S3b: My manager is approachable.",accepted,user
S7,leading,"Don't you agree","How do flexible hours affect your family time?",rejected: the item is from a licensed scale,user
```

- `problem` takes the names of the table above, or `other` with the reason in `words`.
- `decision` is filled by the user: `accepted`, `rejected` with the reason, or `changed` with the new wording.
- An item of a published scale is reworded only when its permission allows it, and the change is recorded in `changes`.
- Plan a second review by a person who does not know the hypotheses; record who and when in `design.md`.
