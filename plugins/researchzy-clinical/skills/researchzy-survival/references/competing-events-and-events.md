# Competing events and event counts

## Competing events

A competing event is one after which the event of interest can no longer happen, such as death from another cause before a relapse. Treating it as censoring and drawing 1 minus the Kaplan-Meier estimate describes a world in which the competing event cannot happen, and overstates the real incidence. `rs.km_table` and `rs.rmst` refuse data that hold competing codes for that reason.

Map the codes as the user confirms them: 0 censored, 1 the event of interest, 2, 3 ... competing events.

| Question | Function | Says |
|---|---|---|
| What share of patients has the event by time t, given that other events can come first? | `rs.cif(data, cause=1, group="arm", times=[...])` | Cumulative incidence (Aalen-Johansen), with a pointwise interval on the log(-log) scale from its delta-method standard error |
| Does the group change the rate of the event among patients still free of any event? | `rs.cox(data, [...])` and `rs.logrank(data, ...)`, which count competing codes as censored | A cause-specific hazard ratio and a cause-specific log-rank test |
| How long do patients live free of any event? | `rs.prepare` again with every event code mapped to 1, then `rs.km_table` | Event-free survival |

- A cause-specific hazard ratio is not the effect on the cumulative incidence: a treatment can lower the rate of the event and still change its incidence little when the competing event is common. Say which one the text reports.
- Report the cumulative incidence of the competing event as well: prepare the data again with the codes swapped (the competing code to 1 and code 1 to 2) and record those results under their own ids.
- Subdistribution (Fine-Gray) models estimate the effect on the cumulative incidence directly. They are not implemented here: say that they need a dedicated tool, and stop.
- `rs.cif` takes no entry times. Its intervals are pointwise.

## Events a comparison needs

For a log-rank test or a Cox model comparing two groups, Schoenfeld's formula gives the number of events:

D = (z(1 − α/s) + z(power))² / (p (1 − p) (ln HR)²)

with α the significance level, s the number of sides (1 or 2), power the planned power, p the share of patients allocated to one group and HR the hazard ratio to detect.

```python
rs.schoenfeld_events(0.70, alpha=0.05, power=0.80, allocation=0.5, sides=2,
                     event_probability=0.45, probability_source="<the user's source: paper or register, table, page>",
                     path="survival/power-events.json")
```

- The hazard ratio comes from a source the user names (a prior study, the smallest difference that would matter to them), never from the data the study will analyse and never from memory.
- Patients follow from the probability that a patient has the event during the planned accrual and follow-up: patients = events / probability. The function refuses a probability without its source. The formula ignores loss to follow-up; when the user gives a planned drop-out share, add it in the plan and say how.
- α, power and the allocation are the user's choices; 0.05 and 0.80 are conventions, not requirements.
- `path` writes the result to `survival/power-<name>.json`, where `check_survival.py` looks up its numbers in the text.

With the `researchzy` plugin connected (it needs a Researchzy account), `search_papers` finds a prior study of the same comparison; read the hazard ratio or the event rate in its PDF from `get_paper_files`, and record the DOI and the table or page in `probability_source`. The index matches keywords in titles and abstracts only, so it cannot promise to find every prior study. Without it, ask the user for the paper or the value.

A protocol that uses these numbers is written with `researchzy-protocol` (plugin `researchzy-clinical`); power for outcomes that are not times to an event goes to `researchzy-statistics` (plugin `researchzy-manuscript`), when installed.
