# The audit file

`thesis-audit/audit.json` holds what must agree across the thesis. You draft it from the thesis and the user confirms it. The script checks the declared items against the text; floats, citations and abbreviations are also checked without a declaration. The identity list for the blind copy is not here: it goes in `authors.json` ([blind review](blind-review.md)).

## Example

An invented thesis; none of these numbers describe a real study.

```json
{
  "thesis": "移动支付使用意愿的影响因素研究 (invented example)",
  "files": [
    {"path": "main.tex", "role": "thesis"},
    {"path": "chapters/conclusion.tex", "role": "conclusion"}
  ],
  "abbreviations": {"convention": "once", "source": "撰写规定.pdf p. 6", "quote": "缩略语首次出现时应给出中文全称", "date_read": "2026-11-18"},
  "key_numbers": [
    {"id": "N", "value": "312", "meaning": "有效问卷数", "labels": ["有效问卷", "样本量", "valid responses"],
     "appears_in": ["abstract-zh", "abstract-en", "chapter 3 text", "table 3-2"]},
    {"id": "B1", "value": "0.24", "meaning": "感知有用性对使用意愿的标准化路径系数", "labels": ["β"],
     "appears_in": ["abstract-zh", "abstract-en", "table 4-3"]}
  ],
  "table_n": [{"table": "3-2", "n": 312}, {"table": "4-3", "n": 312}],
  "hypotheses": {"labels": ["H1", "H2", "H3"], "results": ["chapter 4"], "conclusion": ["conclusion"]}
}
```

## files

| Field | Value |
|---|---|
| `path` | Relative to the working directory or to `audit.json` |
| `role` | `thesis`, `abstract`, `chapter`, `results`, `conclusion`, `abbreviations`, `references`, `appendix`, `other` |
| `language` | `zh` or `en`, for a file whose role is `abstract` |

- List the files in reading order. For LaTeX, list the main file: every `\input` and `\include` is read where it stands. List an included file again only to give it a role.
- A `thesis` file (and any other) finds its parts by headings: 摘要 / Abstract, 缩略语表 / List of Abbreviations, 第N章 / `\chapter` / Chapter N, 参考文献 / References, 致谢, 附录 / Appendix. 目录 and lists of figures are skipped, so their entries do not count as callouts.
- In `.docx`, a heading is a paragraph with an outline level, a style named Heading N or 标题 N, or a short paragraph that is only a part name or 第N章.

## Places

`appears_in`, `results` and `conclusion` take places from this list. A place that is neither one of these nor an existing file stops the script with exit code 2.

| Place | What is read |
|---|---|
| `abstract`, `abstract-zh`, `abstract-en` | Both abstracts, or one of them |
| `chapter 3` | Chapter 3, with its tables, captions and footnotes |
| `chapter 3 text` | The prose and footnotes of chapter 3 only, without tables and captions |
| `table 3-2` | The rows, caption and notes of that table ("3.2" and "3-2" are the same number) |
| `figure 3-4` | The caption of that figure |
| `results`, `conclusion` | The files with that role |
| a file path | Everything in that file |

Chapter numbers come from 第3章, Chapter 3 or a leading "3 " in the heading; otherwise chapter headings are counted. An unnumbered `\chapter*` does not start a chapter.

## key_numbers

| Field | Value |
|---|---|
| `id` | A short name for the report |
| `value` | As the main place writes it: `"312"`, `"0.24"`, `"85.7%"`, `"3.12万"` |
| `meaning` | What the number is, in the thesis's words |
| `labels` | Words that stand right next to the number and name only it: 样本量, 有效问卷, β, valid responses |
| `appears_in` | Every place where the thesis states it |

- Take the numbers from the abstract and the conclusion first, then add each place the thesis repeats them. Declare the numbers a reader would quote, not every number: about five to fifteen.
- Values are compared at the coarser precision: 0.42 agrees with 0.416 and 0.420, not with 0.24. A percentage only matches a percentage.
- When the value is missing from a place, the row fails and lists the numbers that stand next to a label there (样本量为321人). When the value is present and a label also stands next to another value, that is a lead.
- A sentence that cites a study is skipped for labels, so a cited study's own sample size is not compared.
- Two numbers meant to differ (N before and after exclusions) are two entries with their own meanings.

## table_n

| Field | Value |
|---|---|
| `table` | The table number as printed: `"3-2"` |
| `n` | An integer, or a list when several values are right (two models on different samples) |

Declare every table that reports the main sample. Leave out subgroup tables and tables of earlier studies: the ledger lists them anyway, marked `subgroup` or `cited study`.

## hypotheses

| Field | Value |
|---|---|
| `labels` | H1, H2a, 假设1. 假设1, H1 and Hypothesis 1 are the same label |
| `results` | Places of the results (default: the files with role `results`) |
| `conclusion` | Places of the conclusion (default: the files with role `conclusion`) |

A parent label (H2) counts as present when one of its parts (H2a) appears. H0 is never a hypothesis label.

## abbreviations

`convention` is `once` (defined at first use in the main text; each abstract defines its own) or `per_chapter` (defined again in every chapter). When it comes from a school rule, add `source`, `quote` and `date_read`; when it is the user's choice, write `"source": "user"`. Without a convention, the convention row is `not_checked`.

## What never goes in

A value the user has not confirmed, a number you computed, a place you did not find in the thesis, and any rule of the school that is not in its file.
