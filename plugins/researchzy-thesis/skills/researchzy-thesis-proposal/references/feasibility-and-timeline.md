# Feasibility and timeline

## `brief.json`

The student's own facts. The example is invented.

```json
{
  "level": "master",
  "field": "信息系统",
  "direction": "移动学习平台的持续使用",
  "period": {"start": "2026-11-20", "end": "2028-03-31", "source": "提交日期：研究生手册第2页；开始：学生给出的开题日期"},
  "resources": {
    "in_hand": ["本校学生问卷渠道（学院已同意）"],
    "obtainable": ["二十名学生访谈，需伦理审批"],
    "unavailable": ["平台后台使用日志"]
  },
  "preliminary": [{"what": "预实验 r = 0.42（n = 30）", "data_supplied": false, "source": "学生笔记"}],
  "questions": []
}
```

| Key | Content |
|---|---|
| `period` | `start`: the first day the planned work can begin, usually the proposal date. `end`: the date the thesis must be submitted. Both YYYY-MM-DD; `source` says where each comes from. When the school's files state the submission date, also record it as a milestone in `template.json`, so that its quote is checked |
| `resources` | Three lists, in the student's words |
| `preliminary` | Every pilot or earlier result the student mentions, and whether its data were supplied |
| `questions` | Filled at step 4 ([questions and design](questions-and-design.md)) |

The `template` and `timeline` commands print the period's length in months and days. Use that figure; do not count months by hand.

## The minimum executable version

In `plan.md`, after the designs:

1. **The dominant constraint**: the one resource or wait that limits the plan most.
2. **The minimum version**: what can be done with the "in hand" group alone, inside the period.
3. **What was cut**, item by item, and **what would bring each back** (an approval granted, access obtained, more time).
4. **What rests on "obtainable" resources**: the date by which each must be secured, and the fallback if it is not.

If the student has not described their resources, label the plan provisional and say what is missing.

## Waits

Ethics approval, data-access agreements, equipment or laboratory booking, recruitment and translating an instrument take time the student does not control. Give each its own phase in `timeline.csv`, before the work that needs it, and name it in that work's `depends_on`. Its length comes from the student or from the office's published times; otherwise the draft says `[Author input needed: expected time for ethics approval]` and the phase stays.

Leaving time between the last phase and the submission date is a convention, not a rule: how much is the student's and supervisor's choice.

## `timeline.csv`

```csv
phase,start,end,questions,depends_on,deliverable
P1 开题,2026-11,2026-12,,,开题报告
P2 伦理审批,2027-01-01,2027-02-28,,P1 开题,伦理审查批件
P3 数据收集,2027-03,2027-06,RQ1;RQ2,P2 伦理审批,问卷与访谈数据
P4 中期检查,2027-06-15,2027-06-30,,,中期报告
P5 分析与写作,2027-07,2028-01,RQ1;RQ2,P3 数据收集,论文初稿
```

| Column | Content |
|---|---|
| `phase` | A unique name, without `;` or `,` |
| `start`, `end` | YYYY-MM-DD, or YYYY-MM for the first (start) or last (end) day of a month; "2027年3月" also reads |
| `questions` | The question ids the phase serves, separated by `;`; empty for work that serves none |
| `depends_on` | Phases that must end before this one starts, separated by `;` |
| `deliverable` | What the phase produces |

A milestone of the template counts as present when a phase or a deliverable contains its name ("中期检查" in "P4 中期检查").

## The timeline check

```sh
python3 "$SKILL_DIR/scripts/proposal_check.py" timeline
```

It writes `thesis-proposal/timeline-check.md`; exit code 1 means a row failed.

| Row | `fail` means | Do |
|---|---|---|
| `date` | A date that does not exist (2027-02-30) or cannot be read | Correct it |
| `start_before_end` | A phase ends before it starts | Correct it |
| `in_period` | A phase starts before the period or ends after the submission date | Move, shorten or cut it, and say what the minimum version loses |
| `dependencies` | A phase starts before a phase it depends on ends, or depends on a phase that does not exist | Move it, or correct the dependency |
| `milestone` | A milestone of the template is missing, or ends after the template's date | Add or move the phase |

`not_checked` (no period in the brief, no template record) and `not_stated` (the template names no milestones) go to the student as they are. Overlaps and gaps are listed under the table without judgement: phases may overlap on purpose and a gap may be a holiday, so ask. A Gantt chart drawn from `timeline.csv` belongs to `researchzy-figures` (plugin `researchzy-manuscript`, when installed).
