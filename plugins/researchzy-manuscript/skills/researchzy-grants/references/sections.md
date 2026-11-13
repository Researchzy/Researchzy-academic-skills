# The sections

The call decides which sections exist, what they are called and how long they are. Use its names as the headings of `grant/proposal.md`, in its order, so that the check can find them. The guidance below says what goes into each kind of section; it does not decide whether the call has one.

## Gap and significance

- **What is known.** Two to four sentences on the state of the question, each resting on a source the user gave or a paper read in this session. Without a source, write `[Citation needed: …]`.
- **What is missing.** The specific thing nobody has established, and why it has not been done (a method, data, access, a confusion). "No study has …" is a claim: make it only on the papers you have, and say how far the search went.
- **Why it matters.** What changes for whom if the gap closes: a decision that could be made, a method others could use, a cost avoided. Name the barrier and what removing it allows, not only how common the problem is.
- **Why now.** What has recently become possible or necessary: new data, a new method, a policy change. Only with a source.
- **What is new.** The advance over existing work, stated plainly. Keep apart what is new to the field from what is new to this team.

## The plan per aim

One subsection per aim, in the order of the aims page.

| Part | Contents |
|---|---|
| Design | What is compared with what, the unit of study, controls |
| Data | Where the data come from and how much; what is in hand and what will be collected |
| Analysis | The method for each question, and how the success criterion will be judged. A sample size needs its basis (effect size and its source); hand the calculation to `researchzy-statistics` (plugin `researchzy-manuscript`, when installed) |
| Expected outcomes | What each possible result would mean, including a null result |
| Risks and alternatives | The risk and alternative of `aims.json`, with what triggers the switch and when |

Write access to data, sites, facilities and partners only as the user has described it. An access the user has not confirmed is `[Author input needed: confirm access to …]`.

## Timeline

`grant/timeline.csv`, one row per milestone or deliverable, in project months from 1:

```csv
milestone,aim,start_month,end_month,description
M1,A1,1,6,Sampling sites set up
M2,A1,7,18,Monthly sampling complete
M3,A2,10,24,Retention estimate
M4,project,22,24,Final report
```

- `aim` is an aim id, several ids separated by `;`, or `project` for work that serves all aims (management, reporting).
- Every aim has at least one milestone; every milestone names an aim that exists; no milestone ends after the project period in the record.
- In the text, describe the phases and where aims overlap. A Gantt chart is a figure: hand it to `researchzy-figures` (plugin `researchzy-manuscript`, when installed), drawn from `timeline.csv`.

## Team and track record

- Who does what: each person's role tied to aims, and their time on the project if the user gives it.
- Track record from the user's CV and publication list only. A publication the user lists can be checked by DOI when Researchzy is connected; the index has no author search, so it cannot assemble anyone's record. Prior grants, awards and roles come from the user.
- Partners and collaborators: name them and their contribution only as the user's material states. A commitment the user has not confirmed is `[Author input needed: confirm … will …]`.

## Budget justification

`grant/budget.csv`, one row per cost line, amounts as plain numbers in the call's currency:

```csv
line,category,year,amount,aim,quantity,unit_cost,note
B1,consumables,1,12000,A1,12,1000,sampling kits
B2,personnel,2,30000,A2,,,research assistant
B3,travel,1,2500,project,,,
Total,,1,14500,,,,
Total,,,44500,,,,
```

- Required columns: `line`, `category`, `year`, `amount`, `aim`. Optional: `quantity`, `unit_cost`, `note`. The delimiter may be a comma, a semicolon or a tab; `12 000` and `12.000,50` are read as numbers.
- A row whose `line` or `category` is `Total` or `Subtotal` is a stated total: with a year, the sum of that year; without one, the grand total. Leave them out, or let the script check them.
- Every amount comes from the user: quotes, salary scales, institutional rates. Never compute a salary, an overhead, an indirect-cost rate or an inflation step the user did not give. A cost the user has not priced stays out of the table, and the text says `[Author input needed: cost of …]`.
- The justification text walks through the categories: what each line buys, why the project needs it, which aim it serves, and how the amount was reached (quantity times unit cost, a quote, the institution's scale). Every amount written in the text must be a line, a sum by year or category, or the total of the table; the `budget` command checks this.
- Read each budget rule of the record against the table yourself; the script lists them as `not_checked`.

## Impact

For each pathway to impact, give all six; one that lacks an owner or an assessment is an intention, not a plan.

| Part | Question |
|---|---|
| Activity | What will be done: a workshop, a dataset release, a tool, a guideline draft |
| Beneficiary | Who, specifically, gains: a named group of users, not "society" |
| Owner | Which team member is responsible |
| Resources | What it costs and where that is in the budget |
| Timing | When, in project months, with a milestone if it is a deliverable |
| Assessment | How you will know it worked: a count, feedback, uptake |

Keep outputs apart from outcomes. Outputs are what the project produces (papers, data, software, events); outcomes are what changes because of them, and the project can only enable those. Do not promise an outcome that depends on others' decisions.

## What is never drafted

Write a placeholder instead, and list it for the user:

| Never invent | Placeholder |
|---|---|
| Preliminary data, pilot results, figures of results | `[Evidence needed: …]` |
| Publications, citations, prior grants, awards | `[Citation needed: …]` or `[Author input needed: …]` |
| Partner commitments, access to sites, data or facilities | `[Author input needed: confirm …]` |
| Letters of support or commitment, in anyone's name | Not drafted; listed as an attachment for the user to obtain |
| Amounts, salaries, rates, effort | `[Author input needed: …]` |
| Ethics approvals, permits, institutional sign-offs | `[Author input needed: …]` |
