# Input and probe

## Data shapes

- **One row per patient**: an id, the exit time (event or censoring) counted from time zero in one unit, the event code, the group and the covariates. Optional: the date of time zero and the date each grouping variable became known, which let the probe check time zero.
- **Start-stop rows**: one row per patient and period, with the entry time, the exit time, the event code at the exit and the covariate values of that period. They carry a variable that changes during follow-up (a treatment started later). A patient's periods must not overlap, and only the last one can end in the event. Pass `--start` to the probe and `entry=` to `rs.prepare`.
- When the file holds dates only, compute the times in the analysis script (exit date minus the date of time zero) and say so in the plan.

## Event codes

statsmodels uses the status column as a weight: a code 2 counts as two events, and the Kaplan-Meier estimate is wrong without a warning. Every analysis therefore starts from a mapping the user confirmed: 0 censored, 1 the event, 2, 3 ... competing events.

| Codes in the file | Ask | `--map` and `mapping=` |
|---|---|---|
| 0 and 1 | Nothing, unless the codebook says otherwise | none, or `0=0,1=1` |
| 1 and 2 | What each means: some software writes 1 = censored and 2 = event, but only the user's codebook decides | for that meaning `1=0,2=1` and `{"1": 0, "2": 1}` |
| Words or booleans (dead/alive, TRUE/FALSE) | What each means | `alive=0,dead=1` |
| 0, 1, 2 with competing events | Which event is of interest | `0=0,1=1,2=2` |

For survival free of any event, map every event code to 1. Record the mapping and the date it was confirmed in `plan.md`.

## What the probe lists, and what to ask

| Check | Finding | Ask or do |
|---|---|---|
| `times` | Missing or not a number | Correct the source, or leave the row out with its reason |
| `times` | Negative | An entry error or a time zero after the event: ask. Never take the absolute value |
| `times` | Zero | An event or censoring on the day of time zero: ask whether the patient belongs in the analysis. Keep or leave out, with the reason |
| `times` | Start not before the exit | Correct the source or leave the row out |
| `ids` | Identical rows | Duplicates: keep one, leave the others out as "duplicate of row N" |
| `ids` | Different rows with one id | Start-stop rows (run again with `--start`) or two records of one patient: the user decides |
| `groups` | A group without events | It gets no hazard ratio: merge it with another level or leave it out; the user decides |
| `complete_cases` | Missing covariates | Complete cases per model with n stated; `rs.cox` lists the rows it leaves out. Imputation is not done here: if the plan needs it, say so and stop |
| `ties` | Events at shared times | Efron's method, which `rs.cox` always uses; name it in the methods |
| `followup` | A curve stays above 0.5 | Its median will be not reached: plan to report it so |
| `time_zero` | A variable known after time zero | Immortal time: see below |

`parameters` counts events per parameter, a categorical covariate counting its levels minus one. Conventions such as 10 or 20 events per parameter appear in the literature; they are conventions, not laws, and the probe applies none. Give the user the count; the user chooses the covariates, never a p-value screen.

`followup` gives the reverse Kaplan-Meier median follow-up (censoring counted as the event) and the longest time per group. The probe prints row numbers and counts, never an id, a date or another value of a row.

## Time zero and immortal time

Time zero is the moment at which eligibility, the assignment to a group and the start of follow-up coincide; in a trial, randomisation. When a group is defined by something that happens later (adjuvant treatment started within six months, a response at a later visit), its patients are credited with the time before it happened, during which they had to survive to join the group: immortal time, which favours that group. The probe checks it from dates (`--zero-date` with `--known-date VAR=DATECOL`) or from the user's word (`--known-at-zero VAR`); otherwise it is `not_checked`, and you ask.

Two remedies, chosen in the plan before any result:

**Landmark analysis.** Choose the landmark L. Keep the patients alive and under follow-up at L, class them by their status at L, and count time from L. Keep the index that `read_csv` gave, so that row numbers stay those of the file, and carry over the user's `DROP` decisions that concern the rows kept.

```python
LANDMARK = 182                                              # days, from the plan
days = pd.to_numeric(raw["days"], errors="coerce")
alive = raw[days > LANDMARK].copy()
delay = (pd.to_datetime(alive["adjuvant_start"], errors="coerce") - pd.to_datetime(alive["diagnosis_date"])).dt.days
alive["adjuvant_at_landmark"] = (delay <= LANDMARK).map({True: "yes", False: "no"})
alive["days_after_landmark"] = days[alive.index] - LANDMARK
landmark = rs.prepare(alive, time="days_after_landmark", event="status", mapping={"1": 0, "2": 1}, time_unit="days",
                      time_zero="182 days after diagnosis (landmark, plan section 3)", id="patient_id", source=DATA,
                      drop={row: why for row, why in DROP.items() if row - 1 in alive.index})
```

Patients who die or are censored before L are not in this analysis: say how many, and that the result applies to patients alive at L.

**Start-stop rows.** Split each patient's follow-up at the date the variable changes: a row from 0 to the change with the old value and no event, and a row from the change to the exit with the new value and the patient's event. Then `rs.prepare(..., entry="start", id="patient_id")` and `rs.cox(...)` with the variable as a covariate. A Kaplan-Meier curve of a changing group then has entry times; say so under the figure.

Planning time zero, the estimand and a target-trial design belongs to `researchzy-protocol` (plugin `researchzy-clinical`, when installed).

## Rows the user leaves out

`rs.prepare(..., drop={row: reason})` takes the probe's row numbers. Each reason says what was wrong and who decided, for example `"negative time: entry error (user, 2026-11-18)"`. The rows and reasons go into every result's `excluded`, beside the rows each model leaves out for a missing value. The data file is never edited.
