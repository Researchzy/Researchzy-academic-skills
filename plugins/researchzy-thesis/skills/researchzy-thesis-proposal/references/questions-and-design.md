# Questions and design

## Candidate questions

The student owns the choice. Offer two or three candidates, then stop until they decide.

For each candidate give:

| Part | What it says |
|---|---|
| Question | One sentence a study could answer: who or what, which outcome, in which setting |
| Basis | Where it comes from: a line of the student's notes, the supervisor's project, a logged search and what it returned |
| What it needs | Data, method, access and time, in terms of the brief's three resource groups |
| Main risk | What would most likely stop it inside the degree period |

- Build candidates from the student's direction and material, not from what seems fashionable. More ideas and a novelty rating belong to `researchzy-ideas` (plugin `researchzy`, when installed).
- Log the searches behind a candidate in the ledger like any other search (step 5).
- Do not offer a candidate that needs a resource from the "unavailable" group, unless you say what change removes that need.
- When the student brings a question, check it against the brief the same way and say what it needs; do not replace it with your own.
- Do not rank candidates, score them or predict which one the committee will approve.

Record the chosen questions in `brief.json`:

```json
"questions": [
  {"id": "RQ1", "text": "信任如何影响本校学生对移动学习平台的持续使用意愿？"},
  {"id": "RQ2", "text": "学生对平台的信任是怎样形成的？"}
]
```

Ids are short and unique; `matrix.csv`, `timeline.csv` and the draft use them.

## `matrix.csv`

One row per question; a question with two strands may have two rows. Every cell is filled, and a placeholder counts as empty.

```csv
question,content,method,data,phase,output
RQ1,信任对持续使用意愿的影响,问卷调查与结构方程模型,本校学生问卷（学院已同意）,P3 数据收集;P5 分析与写作,第4章
RQ2,信任形成的过程,半结构化访谈,二十名学生访谈（需伦理审批）,P3 数据收集,第5章
```

| Column | Content |
|---|---|
| `question` | An id from `brief.json` |
| `content` | What the study does for this question, in a phrase |
| `method` | The design and the analysis |
| `data` | Where the data come from, and whether they are in hand, obtainable or not yet known |
| `phase` | Phases of `timeline.csv`, separated by `;`, written exactly as there |
| `output` | What it produces: a chapter, a dataset, a paper |

The check fails a question with no row or with an empty cell. When the student cannot yet name a data source, the cell says so in words ("尚未确定：候选为…") and the draft carries `[Author input needed: data source for RQ2]`; an empty cell is not a plan.

## Two designs compared

In `plan.md`, compare at least two reasonable designs before choosing one:

| | Design A | Design B |
|---|---|---|
| The question it answers best | | |
| Data needed | | |
| Method and analysis | | |
| What it can conclude, and what it cannot | | |
| Resources and waits | | |
| Limits | | |

Then state the choice, the second choice and the condition that would switch to it, for example: "if access to course records is not granted by the end of P2, RQ1 moves to the survey design". No design is favoured by habit or by field: the question, the data the student can get and the time available decide.

Hand on, when installed: sample size and power to `researchzy-statistics` and a causal design to `researchzy-causal-inference` (plugin `researchzy-manuscript`); a questionnaire to `researchzy-survey` and an interview study to `researchzy-qualitative` (plugin `researchzy-social`).
