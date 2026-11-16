# Review against the call's criteria

Reviewers score a proposal against the criteria the call publishes, so the review uses those criteria and nothing else: not a generic rubric, not what this funder's panels are said to like. It produces a table of weaknesses and revisions. It gives no score, no ranking and no estimate of the chance of funding: none of these can be known from the text, and a number would read as one.

## `grant/criteria.md`

Start the file when the record is written (step 3 of the workflow), with the first two columns filled: which section will answer each criterion. Fill the other columns at the review.

```markdown
# Review against the call's criteria

| Criterion | Where addressed | Evidence | Weakness | Revision |
|---|---|---|---|---|
| Significance | Background; Aims | Gap paragraph cites three studies read in full | The size of the problem rests on one regional survey | Add the user's national figures, or narrow the claim |
| Feasibility | Research plan; Timeline | Pilot in hand; sites agreed | Aim 2 depends on Aim 1 and its fallback is one sentence | Say which earlier data the fallback uses |
| Value for money | Budget justification | Every line tied to an aim | Travel line serves no aim | Tie it to the dissemination milestone, or remove it |
```

Layout rules the script relies on:

- The first table whose header begins `| Criterion | Where addressed |` is the review table. Other tables (the requirement matrix) may follow it.
- **Criterion**: the name exactly as in `requirements.json`. One row per criterion of the record, and no rows for criteria the call does not have.
- **Where addressed**: headings of the proposal, separated by `;`, written as in the proposal (numbering and case do not matter). A criterion with no section that answers it is a gap in the draft, not in the table.
- If the call gives sub-questions under a criterion, keep them in the Evidence cell of that criterion's row, or add a row per sub-question only when the record lists them as criteria.

## Filling a row

Read the proposal as a reviewer holding only the call and this criterion.

1. **Evidence.** What in the proposal answers the criterion: a sentence, a result, a table. Point at it. If you cannot point at anything, the evidence is "none" and the weakness is the whole criterion.
2. **Weakness.** The most serious gap a reviewer would find: a claim without support, a step without a method, an aim without a fallback, a cost without a reason, a mismatch with the call's wording. One or two per criterion, the important ones first. Say "none found" only after reading the sections listed.
3. **Revision.** The smallest change that fixes it. If the fix needs something only the user has (data, a letter, a figure), the revision is the placeholder to add or the question to ask.

Then make the revisions in the proposal, or list them for the user when they need the user's input.

## Weights

When the record gives weights, spend the review's attention, and the proposal's words, in proportion. A criterion that carries most of the weight and is answered in one paragraph is a weakness in itself. Do not combine the rows into a weighted total.

## The coherence pass

After the review and before the final check, read the proposal once for agreement between its parts. The script checks the links that live in files; you check the ones that live in prose.

| Pair | Agree when | Checked by |
|---|---|---|
| Aims page and plan | Same aims, same order, same titles; every aim has a plan subsection; no plan without an aim | you |
| Aims and success criteria | The plan judges each aim by the criterion on the aims page | you |
| Aims and timeline | Every aim has a milestone; milestones name aims that exist; all fall within the period | script |
| Aims and budget | Every aim has a budget line; every line names an aim or `project` | script |
| Plan and budget | Every costed activity appears in the plan; every activity that needs money has a line (staff for analysis, travel for fieldwork) | you |
| Plan and timeline | The order of work in the plan is the order in the timeline; a dependency in `aims.json` is visible as an order in time | you |
| Budget text and table | Every amount in the text is a line or a sum of the table | script (`budget --proposal`) |
| Team and plan | Every task has someone who can do it; nobody is listed without a task | you |
| Impact and budget | Each impact activity has resources and an owner | you |
| Proposal and call | Every required section, criterion and attachment of the record is addressed | script and the requirement matrix |

Report what you changed and what is left for the user.

## Before the final check

- Every placeholder is either filled from the user's material or listed for the user with the question it needs answered.
- Section limits pass on the final text. Page limits are measured on the file that will be submitted: export it, then run `check --pdf`. Formatting rules (font, margins) are read against the exported file by eye.
- The AI-policy rule of the call has been shown to the user, and any declaration it requires is in the list of things for the user to do.
- `check --final` and `budget --proposal` exit 0, or every remaining `fail` is reported with its reason.
