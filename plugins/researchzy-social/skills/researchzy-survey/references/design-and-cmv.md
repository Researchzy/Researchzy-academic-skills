# Flow, checks and the pretest

## `survey/design.md`

Write it before fielding, in this order:

1. **Flow.** Consent, screening, each block with its items, the attention items in place, demographics, the closing page. Note which blocks are randomised and whether the platform can export the order it showed.
2. **Attention items**, each with its expected answer.
3. **Marker variable.**
4. **Where predictors and outcomes sit**: different blocks, different pages, different waves, or the reason they cannot be apart.
5. **Procedural remedies** (the table below).
6. **Second review** of the wording: who, when.

## Choices with costs

Practice differs on these; present them as choices and record the user's decision with its reason.

| Choice | One way | The other | What it costs |
|---|---|---|---|
| Demographics | Last, so they do not prime the constructs | First, when they decide routing or quotas | First: priming and early break-off; last: missing when people quit |
| Reverse-keyed items | Some in each scale, to catch acquiescence and straight-lining | None or few | Reversed items can form a method factor and confuse some readers; without them straight-lining is harder to tell from agreement |
| Midpoint | Keep it | Drop it | Dropping forces a side on the truly neutral |
| Failing one attention item | Flag only | Exclude | Excluding on one item removes honest people who misread once |
| Measurement occasions | One sitting | Waves with a time lag | Waves cost attrition and a matching key; one sitting leaves only the other remedies |

## Attention items

- An instructed item tells the respondent which answer to give ("For this row please choose disagree"). Write the expected answer into `items.csv` and `design.md`; the audit compares with it.
- One or two in a survey of ordinary length; spread them, inside blocks of similar items, never as the first item of a page.
- A blank answer is not a failure: the audit counts blanks apart.
- An item answered wrongly by very many people may be unclear, and one answered right by almost everyone may show nothing; the audit lists both (a convention).
- Do not use an item where any answer is "wrong" unless the expected answers are written down.

## The marker variable

Choose it now; it cannot be added after the data are in. It is a variable that theory says is unrelated to the substantive constructs, answered in the same format (same scale, same points), placed near them. Record why it should be unrelated. Its statistical use belongs to `researchzy-psychometrics` (plugin `researchzy-social`, when installed).

## Procedural remedies for common method variance

Every remedy claimed in a paper must point at something in this questionnaire. Write the table in `design.md`:

| Remedy | What it does | Where in this questionnaire | Cost |
|---|---|---|---|
| Separate predictor and outcome in time | Breaks shared mood and memory between the measures | Wave 1: workload; wave 2, two weeks later: burnout | Attrition; a key to match the waves |
| Separate them on the page | Weakens carry-over from one answer to the next | Different pages, different instructions | Little |
| Different sources | The outcome rated by someone else | Supervisor rates performance | Access, matching |
| Different formats or anchors | Breaks a habit of answering | Agreement scale for one, frequency for the other | Harder comparison |
| Anonymity and no right answers | Reduces answering to please | The introduction says so; no names collected | None |
| Clear, short items | Less guessing, less answering by mood | The wording review | Time |
| Marker variable | Allows a later statistical check | Item M1 | One item |

`item_screen.py` reports `predictor_outcome_same_block`, `one_wave` and `no_marker`. Each one is resolved in the design or kept with the user's reason. No remedy shows that common method variance is absent; write "we reduced it by", not "we ruled it out".

## The pretest plan

Write `survey/pretest.md` before the first interview. Fix the criteria and actions first, so that the results cannot bend them.

| Stage | Look at | Criterion (the user's, a convention) | Action when met |
|---|---|---|---|
| Cognitive interviews | How each item is understood, and the answer process | Two or more people read an item differently from its intent | Rewrite the item and test it in the next round |
| Cognitive interviews | Words people stumble over or ask about | Any | Replace or define the word |
| Pilot | Time to complete | Median above the time the invitation promises | Shorten, or change the invitation |
| Pilot | Blank and break-off per item | An item left blank by many, or a page where many stop | Read the item and the page again |
| Pilot | Attention items | Passed by almost nobody, or by everybody | Reword or move the item |
| Pilot | Export | The audit cannot read a column it needs | Change the platform settings before fielding |

- Run the pilot export through step 7 of the workflow: a column problem found now costs nothing.
- Log each round in `survey/pretest-log.md`: date, who (counts, never names), what was seen, what changed, the version of `items.csv` after it.
- Pilot respondents do not enter the main sample; record how they are kept out.
