# The aims or objectives page

Write this page before any other section. Every later section serves an aim, every milestone and budget line points at one, and a reviewer who reads only this page should know what will be done and why it matters. Use the call's name for the page (aims, objectives, work packages) and its limit.

## The logic of the page

In this order, one short paragraph or sentence each:

1. **The problem.** What is not working or not known, and for whom. A fact from the user's material or a paper read in the session, not a general claim about importance.
2. **What is known and what is missing.** The specific gap this project closes. A gap is a claim about the literature: base it on papers you have, or write `[Citation needed: …]`.
3. **The overall objective.** One sentence: what the project will establish by its end.
4. **The hypothesis or question.** Testable, with what would count as an answer.
5. **The aims.** Usually two to four, each a block as below. The call may fix the number; if it does not, use as many as the work needs.
6. **The payoff.** What will be possible after the project that is not possible now, and for whom. Keep it to what the aims can deliver.

## The aim block

Each aim has, in the page and in `aims.json`:

| Part | What it says | Test |
|---|---|---|
| Title | A verb and an object: measure, test, build, compare | Could someone tell when it is done? |
| What will be learned | What the field will know at the end, **whatever the result** | Does a negative result still teach something? If not, the aim is a bet; say so. |
| Approach | One or two sentences; the detail goes in the plan | Matches the plan section |
| Success criterion | An observable result with a threshold, and how it is measured | A reviewer could check it in the final report |
| Dependency | Which other aim's result it needs, if any | See independence below |
| Fallback | What this aim does if the result it depends on does not come | Required whenever there is a dependency |
| Risk and alternative | The most likely way it fails, and what is done instead | The alternative is a different route, not "try harder" |

## Independence of aims

Aims that each need the previous one's success form a chain, and one failure stops everything after it. Prefer aims that run in parallel and inform each other: the result of one cross-checks or sharpens another, but is not its input.

- When a real dependency exists (a model needs the data another aim collects), record it in `depends_on` and give a `fallback` that lets the dependent aim go ahead without it: existing data, a pilot, a smaller version, a different source. The script fails an aim that depends on another and has no fallback.
- Make the dependency honest. An aim that "builds on the findings of Aim 1" depends on it, even if the text avoids saying so.
- Two aims that are the same work cut in two are one aim.

## Commitment matched to evidence

Promise in proportion to what is already known. Judge each aim's central claim on the user's material and on papers read in the session, and choose the wording from the strength.

| Strength | What it means here | How to write the aim |
|---|---|---|
| `shown` | The applicant's own data, or a published result read in the session, already shows the effect or the method works in this setting | Deliver: "We will produce …", with a firm success criterion |
| `indicated` | A pilot, a related setting or indirect results point this way, without settling it | Test: "We will test whether …", with the criterion that decides it |
| `reasoned` | It follows from established work, but nobody has tried it here | Explore: "We will determine whether …", with a criterion for stopping and a fallback |
| `open` | No evidence either way | Keep it small: a bounded part of the work and the budget, a stop rule, and what a null result will show |

- Never raise a strength by writing confidently. A pilot the user has not described is not evidence: write `[Evidence needed: pilot result for …]`.
- Results that exist are written in the past tense with their source. Expected results are written as expectations. Do not mix them in one sentence.
- Keep quantitative targets within what the evidence supports; a target the user has not set is `[Author input needed: target for …]`.

## `aims.json`

```json
{"aims": [
  {"id": "A1",
   "title": "Measure how far fragments travel downstream",
   "learned": "Transport distances per size class, whether or not the bed retains fragments",
   "success_criterion": "Monthly counts at six sites for 12 months, with fewer than two missed samplings per site",
   "evidence": "indicated",
   "depends_on": [],
   "fallback": "",
   "risk": "High flows prevent sampling for weeks",
   "alternative": "Sample from bridges with a pump during high flows",
   "milestones": ["M1", "M2"],
   "budget_lines": ["B1", "B4"]},
  {"id": "A2",
   "title": "Test whether the river bed retains fragments",
   "learned": "Whether the bed acts as a sink, a source or neither",
   "success_criterion": "A retention estimate whose interval excludes zero, or a bound showing retention is below 5%",
   "evidence": "reasoned",
   "depends_on": ["A1"],
   "fallback": "Use transport rates from the user's earlier survey if A1's counts are late",
   "risk": "Coring disturbs the bed",
   "alternative": "Sediment traps left for one season",
   "milestones": ["M3"],
   "budget_lines": ["B2", "B3"]}
]}
```

This example is invented, and so are its numbers. In a real project every value comes from the user or from text read in the session.

| Field | Rule |
|---|---|
| `id` | Short and unique: `A1`, `O2`, `WP3`. The same ids appear in `timeline.csv` and `budget.csv`. |
| `learned`, `success_criterion`, `risk`, `alternative` | Required. An open placeholder counts as missing. |
| `depends_on` | List of other aims' ids, or empty. |
| `fallback` | Required when `depends_on` is not empty. |
| `evidence` | Optional: `shown`, `indicated`, `reasoned`, `open`. Not checked by the script. |
| `milestones`, `budget_lines` | The ids of this aim's rows in `timeline.csv` and `budget.csv`. The script checks both directions: every id listed exists and names this aim, and every row naming this aim is listed. |
