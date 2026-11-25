# Reading the audit

`data-quality.md` is written for an appendix; `audit.json` holds the same and more; `flags.csv` has one row per respondent with the spreadsheet row number, the ID, every flag (`1`, `0`, empty when not judged), the raw values, and the rule that excluded the row.

## States

| State | Means | Say |
|---|---|---|
| `checked` | Computed for every respondent whose answers allow it | The count flagged, and how many could not be judged |
| `not_checked` | The column is not declared or not in the file, or the file was not read | What was missing; never "none found" |
| `no_threshold` | Computed and reported, but its setting is null, so nothing is flagged | The values, and that no threshold was set |

## What each indicator shows, and what it does not

| Indicator | Shows | Does not show |
|---|---|---|
| `attention` | The respondent gave an answer other than the instructed one | Why: misreading, a confusing item, or not reading. A pass rate far from the rest points at the item |
| `straightline` | One answer throughout a block | Inattention, when the block has no reverse-keyed items: real agreement looks the same. With reverse-keyed items, one answer throughout contradicts itself |
| `long_run` | Many identical answers in a row as shown | Anything when the order shown is unknown |
| `fast` | A total time below the setting | Speed per page; a respondent who quit early also looks fast |
| `slow`, `pause` | A long total, a long gap | Inattention: people take breaks |
| `duplicate_id` | The same ID twice | Whether the later row is a resubmission or a data error |
| `duplicate_answers` | Identical answers under two IDs | The same person; two careful people rarely match on every item, but short scales can |
| `duplicate_ip` | One address, two rows | The same person: households, offices and universities share addresses |
| `break_off`, missing | Where answers stop and which items are left blank | Why, or how to handle it; that is decided in the analysis plan |
| `open_text_*` | Blank, very short or identical answers | Meaning. A common phrase ("没有意见", "no comment") repeats without meaning anything |
| `inconsistent` | A declared pair disagrees beyond its tolerance | Which answer is true |

**Automated or AI-written responses.** The report lists rows with two or more of: fast, an identical open answer, the same answers as another ID, a repeated IP address. It is a lead for the user to read, never a finding: a file with one row per respondent shows no mouse or keyboard behaviour, no paste events, no device, and no timing within a page. Never write that a respondent "is a bot".

## Overlap

Indicators that come from one behaviour overlap: a straight-liner is often fast. Report the overlap table, and count respondents, not flags: "12 straight-lined a block; 8 were fast; 3 of them were both".

## The paragraph for the methods or appendix

Write it from `data-quality.md` only, with each number as it is there:

> We received N responses. Before fielding (rules dated D) we decided to exclude respondents who [rule R1 in words] or [rule R2]. [k] respondents failed the attention item and [b] left it blank; [s] gave one answer throughout the support block, which contains two reverse-keyed items; [f] completed the survey in under [x] seconds, [o] of whom also straight-lined. [d] responses repeated an earlier ID. The rules excluded [e]; we analysed [N − e]. Thresholds and their sources are listed in Table S[n]. IP addresses were not exported, so duplicate submissions from one address were not checked.

In Chinese, the same order: 收到问卷 N 份；发放前（日期 D）确定的剔除规则为……；注意力题答错 k 份、空答 b 份；……；按规则剔除 e 份，最终分析 N − e 份。导出数据中没有 IP 地址，因此未检查同一 IP 的重复作答。

- Name every `not_checked` indicator and why.
- A post hoc rule is reported as such, with its date and what changed. Its exclusions stand apart in the counts.
- When no rules were written before fielding, say so plainly: "Exclusion rules were not specified before data collection." Report the flags as counts and exclude nobody unless the user decides, and then label those rules post hoc.
- Settings are conventions: "the cut-off we set (0.33 of the median duration)", never "the standard cut-off".
- Do not write that the data are "clean" or "of high quality". Write what was checked, what was found and what was not checked.

## Hand-offs

| What | To |
|---|---|
| The analysis with and without the excluded respondents; missing-data handling; non-response | `researchzy-statistics` (plugin `researchzy-manuscript`) |
| Reliability, validity, statistical tests of common method variance with the marker variable | `researchzy-psychometrics` (plugin `researchzy-social`) |
| Coding the open answers | `researchzy-qualitative` (plugin `researchzy-social`) |

All when installed. Give them `flags.csv` and the rules; they read `excluded` and never edit the data.
