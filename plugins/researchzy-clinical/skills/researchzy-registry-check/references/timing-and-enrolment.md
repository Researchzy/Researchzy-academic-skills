# Timing, enrolment, versions and wording

## When the trial was registered

The script compares two dates of the record, never a date you type:

- `studyFirstSubmitDate`: when the registration was first submitted. This is the registration date. The date it was first posted (`studyFirstPostDateStruct`) comes later, after the registry's review, and is shown but not used.
- `startDateStruct`: the start of enrolment, with its `type`. Only an `ACTUAL` start says when enrolment began; an `ESTIMATED` one is a plan.

| Record | Registration timing |
|---|---|
| First submitted on or before the actual start | Before enrolment began |
| First submitted after the actual start | After enrolment began, by the number of days shown |
| Start `ESTIMATED`, or either date missing | Cannot be told: `not_checked` |
| Start given to the month, submitted in that month | Cannot be told: `not_checked` |

A `registration_claim` item holds the paper's own words ("prospectively registered", "前瞻性注册", "retrospectively registered"). The claim is `inconsistent (timing)` when the dates say otherwise. A paper that makes no claim gets no item; the report still states the timing.

Whether a registration made after the start was acceptable is a rule of journals, funders and laws, which differ and change. This skill states none: report the dates and the claim, and leave the rule to the user or the journal.

## Enrolment and its type

`enrollmentInfo.count` means different things by its `type`:

| Record | Compare with | Item `basis` |
|---|---|---|
| `ESTIMATED` | The size the paper says was planned (from the sample size calculation or the protocol) | `planned` |
| `ACTUAL` | The number the paper says were enrolled | `actual` |

- Give both items when the paper gives both numbers. The one whose basis does not match the record's type is `not_checked`, with the reason: an estimate is not an enrolment, and an actual count is not the plan.
- The registry's actual count may include people enrolled but not randomised, or the reverse. The script shows both numbers with the record's type; say which count the paper gives ("randomised", "enrolled", "analysed") and let the reader weigh a difference.
- The planned size as registered is in the earlier version, if the user supplies one; the current record may have replaced it with the actual count.

## Which version was compared

Every report names the record's last update (`lastUpdatePostDateStruct`) and the date you read it. Two cases need saying in the report:

- **Updated after the paper was published** (`paper.published`): the paper is compared with the record as it is now, not as its authors saw it. A difference may come from a later edit of the record.
- **Updated after enrolment began**: the outcomes as registered before enrolment were not seen, so every outcome's As registered state is `not_checked`, unless the user supplies an earlier version ([fetching records](fetching-records.md)). An earlier version that was itself posted after the start is not a version from before enrolment; the report says so.

## Wording the report

- Name the difference and its type, and show both texts: "The record registers the WOMAC pain subscale at 12 weeks as the primary outcome; the paper reports knee function at 26 weeks as primary (record: secondary outcome)." Then say whether the paper states the change, with its quote, or where you looked.
- Never write "outcome switching", "selective reporting", "misconduct", "fraud", "spin" or "hidden"; never guess why a difference arose or whether results drove it. Whether it biases the result is judged in `researchzy-risk-of-bias` (plugin `researchzy-evidence`, when installed), which can take `compare.md` as evidence.
- `not_checked` items are reported as not checked, with the reason. Never fold them into "consistent", and never count states into a score.
- For a reviewer, the useful request is the result of every registered outcome at its registered time point, whatever its direction, and the reason for each change. The wording of referee comments belongs to `researchzy-paper-review` (plugin `researchzy-manuscript`, when installed).
- For an author checking their own paper, list what to add: a statement of each change and its date, or the registered outcome that is missing. Never suggest editing the record or the paper so that they appear to agree.
