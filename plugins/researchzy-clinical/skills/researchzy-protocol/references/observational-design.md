# Comparative observational studies: the target trial table

When an observational study compares treatments, exposures or strategies, write first the randomised trial it would ideally be, then how the data imitate each part of it. The table makes the design choices visible before any data are analysed, and it exposes the commonest error: follow-up that starts at a different moment from eligibility or assignment.

## When to write it

Write it for every comparative question about the effect of a treatment, an exposure or a strategy on an outcome. Skip it for descriptive studies (prevalence, incidence, natural history), diagnostic accuracy and prediction, and say so in the protocol.

## The table

Put it in `protocol.md`, under the design, with one row per part:

| Part | The trial we would run | How these data imitate it | Departure and its consequence |
|---|---|---|---|
| Eligibility | Who could enter, judged from information available at time zero | The codes, measurements and look-back windows that apply the same criteria | Criteria the data cannot apply |
| Treatment strategies | Each strategy in full: what, when, how long, what counts as stopping or switching | How a record shows each strategy started | Strategies the data cannot tell apart |
| Assignment | Randomised | Adjustment for the confounders listed in `definitions.csv`, with the method named in `sap.md` | Confounders not measured |
| Time zero | The moment eligibility is met, the strategy is assigned and follow-up starts, all at once | The date that plays that role in the data | Any gap between the three |
| Follow-up | From time zero to the outcome, death, loss, or the end of the window | Where the records end and how loss is recognised | Losses the data cannot see |
| Outcome | The outcome and its time point, as in `core.json` | The codes or measurements and their validity | Misclassification expected |
| Causal contrast | Intention-to-treat or per-protocol effect | What can be estimated from these data | — |
| Analysis | The comparison the trial would make | The estimator named in `sap.md` | — |

Fill the third column only with what the user's data source documents; an element the data cannot supply is `[Author input needed: …]`, never a guess about what a database contains. Then classify the emulation for the user, in words: close (no departure that could change the answer), partial (departures, each with its expected direction), or not credible (time zero cannot be aligned, or a key confounder is missing).

## Time zero

Eligibility, assignment and the start of follow-up coincide at time zero. Three common ways to break that:

- **Immortal time.** Follow-up starts before the strategy is known: a person counted as "treated" from diagnosis had to survive until treatment began. Start follow-up when the strategy is assigned, or use a landmark at a fixed time after diagnosis (people who die or leave before it are excluded from both groups), or code treatment as a time-varying status.
- **Prevalent users.** People already on a treatment at entry are the ones who tolerated it and stayed alive. Prefer new users: no use during a stated look-back window before time zero.
- **Grace periods.** When a strategy allows starting within a period ("within 3 months of diagnosis"), people who fit both strategies during that period must be handled by a rule stated in advance (cloning with censoring, or assignment at random); say which.

Each of these is a decision for the user, written in the protocol before the analysis. State the time zero as a sentence that the analysis plan copies word for word into `core.json` as a text item.

## What goes elsewhere

- Weighting, matching, doubly robust estimation and E-values: `researchzy-causal-inference` (plugin `researchzy-manuscript`, when installed). The table names the estimator; that skill runs it.
- A landmark or time-varying analysis of a time-to-event outcome: `researchzy-survival` (this plugin, when installed), with the time zero copied from the protocol.
- Whether a confounder set is sufficient is a subject-matter judgement: list the confounders with their sources in `definitions.csv` and let the user and their collaborators decide.
