# Building the question bank

A useful question could only be asked of this thesis. "What are the limitations of your study?" fits any thesis; "Your sampling frame was the club membership register: what about volunteers who never registered?" fits one, and it points to the page where the student must look. Every question in `questions.json` names such a place.

## Categories

| Category | What the examiners test | Usual anchors |
|---|---|---|
| `opening` | Whether the student can state the problem, the answer and why it matters, briefly | Abstract, introduction, conclusion |
| `contribution` | What is new against the closest work; what a reader can now do or believe | Literature chapter, discussion, the claims |
| `method` | Why this design, sample, measure, model or procedure, and not the obvious alternative | Method chapter, design tables |
| `data` | Where the data came from, what was lost on the way, what the numbers mean | Sample description, response or attrition, data tables |
| `limitation` | Whether the student knows how far the results reach and what would overturn them | Limitations section, unsupported hypotheses |
| `application` | Who could use the results, under which conditions, and with what caution | Discussion, implications |
| `closing` | What the student would do differently, what comes next | Future work, reflections |

## Where questions come from, in this order

1. **The reviewers' written reports.** Each objection becomes one question, worded close to the report and marked `source.type: reviewer` with the objection quoted. These come first in the bank because the examiners have already written them down. A report that only praises a point gives no question.
2. **Checks already run.** Each failure in `thesis-audit/report.json` (a number that differs between abstract and chapter, a table never cited) and each critical or major finding in `paper-review/findings.json` is a question an examiner can find too. Do not repeat the review here; read its results.
3. **Signals in the thesis.** The tables below. Each question is anchored at the page where the signal is.
4. **Close recent work**, with Researchzy (below).
5. **The student's own worries**, when they name them (`source.type: user`).

## Signals that predict questions

For any thesis:

| Signal | Question it raises |
|---|---|
| The abstract or conclusion claims more than the results chapter shows | Which result supports this exact wording? |
| A hypothesis or research question that was not supported, or only in part | What does this mean for the model or argument; was the test able to detect an effect? |
| A choice stated without a reason (sample, period, measure, case, corpus) | Why this, and what would have changed with the obvious alternative? |
| A number reported differently in two places | Which is right, and does anything depend on it? |
| No comparison with the closest existing work | How does this differ from what is already known? |
| A limitation mentioned in one sentence | How far does it reach; which results does it not affect? |

By kind of study (use the rows that fit; a thesis can mix them):

| Kind of study | Signals |
|---|---|
| Survey or observational data | Who could not be sampled; response or attrition; how constructs were measured and validated; missing data; model choice; causal wording without a design that supports it; size of effects against their significance |
| Experiment or laboratory work | Controls; allocation and blinding; number of runs or replicates; how outliers or failed runs were handled; whether the effect was large enough to detect |
| Qualitative study | How participants or cases were chosen and when collection stopped; the researcher's position; how codes or themes were derived and checked; another reading of the same material; what transfers to other settings |
| Engineering or computational work | Baselines and whether they were tuned as carefully; datasets and splits; ablations; cost and scale; where the method fails; whether code and data are available |
| Humanities or theoretical work | Why this archive, corpus or set of texts; definitions of key terms; readings that cut against the argument; the scope of the conclusion |

### Choices not made

List each point where a competent researcher could reasonably have chosen differently. For each, decide whether the other choice would change what is being studied (another population, outcome or question) or only the estimate (another model, filter or coding rule). The first gives a "why this question" question; the second a "would the result hold" question. When the thesis tested the alternative, anchor the answer there; when it did not, the outline says so (`not_done`).

### Rival explanations

For the main finding, name one or two other explanations that fit the same evidence and the observation that would tell them apart. If the thesis contains that observation, the question is easy to defend; if not, it is a real gap and the outline bounds it.

## Filter before writing outlines

For each candidate question, look for the place where the thesis already answers it. Found: the question stays, with that place as its anchor and level `defend`. Not found: the question stays as a real gap, with level `bound` or `adopt`. Drop only duplicates. The same model writes the question and looks for the answer, so this filter is not an independent review; say so when handing over.

## Follow-ups

Mark the questions most likely to hurt as `hard: true`. Give each two levels of follow-up: the next question if the first answer is good, and the one after it. The other questions may have one level or none.

```json
"follow_ups": [{"question": "Would a smaller register have changed the result?",
                "follow_ups": [{"question": "Then why not weight the sample?"}]}]
```

## Close recent work (Researchzy)

`search_papers` matches keywords in titles and abstracts; it has no author search and no list of citing papers. Build queries from the thesis's own key terms, one concept pair at a time, with `yearFrom` two or three years before the defence; sort by relevance and read up to the first page of results. Save each result exactly as returned in `defense/search/`, one file per query. A returned paper qualifies when it addresses the same question, population or method and is absent from the thesis's reference list (search `thesis-pages.txt` for its title or first author). For each, one `contribution` question: how does your work differ from this paper? The question names the paper as the record gives it; `defense_check.py check` fails a paper that is not in the saved record. If the user wants to read it first, `get_paper_files` and `researchzy-deep-read` (plugin `researchzy-reading`, when installed) help. Never add a paper from memory, and never suggest one the search did not return.

## Size of the bank

A convention, not a rule: about 20 to 30 questions for a master's thesis and 30 to 50 for a doctorate, with at least one per category and chapter. The user may ask for more or fewer.
