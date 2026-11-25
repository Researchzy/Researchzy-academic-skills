# Fetching records

The script reads only files you saved. You fetch them from the public API of ClinicalTrials.gov, version 2, and save each response exactly as it came: no reformatting, no trimming, no merging. A saved file is the evidence for every record value in the report.

## Requests

| What | Request | Save as |
|---|---|---|
| The API version | `GET https://clinicaltrials.gov/api/v2/version` | `registry-check/api-version.json` |
| One record | `GET https://clinicaltrials.gov/api/v2/studies/<NCT>` | `registry-check/record-<NCT>.json` |
| A page of a search | `GET https://clinicaltrials.gov/api/v2/studies?format=json&countTotal=true&pageSize=100&query.cond=…` | `registry-check/search/s1-p1.json` ([prior-trial search](prior-trial-search.md)) |

- Fetch the API version on the day you fetch the records; the reports print it with its data timestamp.
- Write down the date you read each record: it goes in `items.json` as `record.read`.
- The number comes from the paper. If the API returns no study for it, report that and ask the user; do not try neighbouring numbers.
- If a request is refused, limited or answered with an error, read the API documentation on the registry's site and follow it. This skill states no rate limit: limits change, and the documentation of the day decides.
- Never use a record from a page you did not save, from memory, from another website or from a summary.

## What the script reads

These paths were read from API 2.0.5 on 2026-11-17. The API can change: when a path is missing from a saved record, the item it serves is `not_checked` with that reason, never filled in.

| Path | Used for |
|---|---|
| `protocolSection.identificationModule`: `nctId`, `briefTitle`, `officialTitle`, `acronym` | The record's number; title for the identity check |
| `protocolSection.conditionsModule`: `conditions`, `keywords` | Condition for the identity check |
| `protocolSection.armsInterventionsModule`: `interventions` (`name`, `otherNames`, `description`), `armGroups` (`label`) | Intervention for the identity check; intervention items |
| `protocolSection.sponsorCollaboratorsModule`: `leadSponsor.name`, `collaborators` | Sponsor for the identity check |
| `protocolSection.outcomesModule`: `primaryOutcomes`, `secondaryOutcomes`, `otherOutcomes`, each with `measure`, `description`, `timeFrame` | Outcome items |
| `protocolSection.designModule.enrollmentInfo`: `count`, `type` (`ACTUAL` or `ESTIMATED`) | Enrolment items |
| `protocolSection.statusModule.studyFirstSubmitDate` | Registration timing: the date the registration was first submitted, not the date it was posted |
| `protocolSection.statusModule.startDateStruct`: `date`, `type` | Registration timing; start-date items |
| `protocolSection.statusModule.studyFirstPostDateStruct`, `lastUpdatePostDateStruct` | Shown in the report; the version read |
| `protocolSection.statusModule`: `overallStatus`, `primaryCompletionDateStruct`; `hasResults` at the top level | The search's trial list |

Dates come as `YYYY-MM-DD` or `YYYY-MM`. A date given to the month is compared to the month; the report says so.

## Versions and history

The API gives only the current version of a record. On 2026-11-17 it had no public endpoint for earlier versions (`/api/v2/studies/<NCT>/history` answered 404), while the registry's website shows each record's history. So:

- Every comparison names the version it read: the last update posted (`lastUpdatePostDateStruct`) and the date you read it.
- When the record was updated after enrolment began, the outcomes as registered before enrolment were not seen: the script marks each outcome `not_checked` under As registered. When it was updated after the paper was published, the report says that the paper is compared with the record as it is now, not as the authors saw it.
- An earlier version comes only from the user, from the record's history on the website. If they can save it in the shape the API returns (a `protocolSection` with its modules), pass it with `--earlier`, and pair each outcome item with it (`earlier`). If they can save it only as a page or a PDF, compare it by reading: quote both texts, and report those comparisons as your reading, not the script's.

## Other registries

A paper may print other numbers: EudraCT, CTIS, ISRCTN, ChiCTR, ANZCTR, a national register. List each in `registrations`; the script reports it `not_checked`, because it reads ClinicalTrials.gov records only.

- Ask the user, in the first message, for those records if they have them; do not search other registries' websites on your own.
- With a record the user supplied, compare by reading as above, with quotes from both, and say which items were compared that way.
- A number that appears in both registries' records links them; the paper's word alone does not.
