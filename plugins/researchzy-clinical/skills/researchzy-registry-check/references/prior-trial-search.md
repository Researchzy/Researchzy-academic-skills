# Searching for registered trials before a study

The question is whether trials on the same question are finished, running or stopped. The answer is a list of what logged queries returned from one registry on one date, never a verdict that nobody has studied it. For a systematic review, use `researchzy-systematic-review` (plugin `researchzy-evidence`, when installed) instead: it searches several sources and screens with a protocol.

## Queries

- Split the question into the condition and the intervention. Write each with its synonyms and its other spellings: "knee osteoarthritis", "osteoarthritis of the knee", "gonarthrosis"; "exercise", "physiotherapy", "strength training".
- Use `query.cond` for the condition and `query.intr` for the intervention; `query.term` searches the whole record. Run each wording as its own logged search rather than one long query.
- Add no status, date, phase or location filter that the user did not ask for. Withdrawn, terminated and suspended trials are part of the answer: they show who tried and stopped.
- Send `countTotal=true` so that the first page reports the total, and `pageSize=100`. The parameters were checked against API 2.0.5 on 2026-11-18; if the API rejects one, read its documentation.

```
https://clinicaltrials.gov/api/v2/studies?format=json&countTotal=true&pageSize=100&query.cond=knee%20osteoarthritis&query.intr=exercise
```

## Pages and the log

- Save every page unchanged as `registry-check/search/<search>-p<n>.json`. When a page has a `nextPageToken`, fetch the next page with `&pageToken=<token>` added; the last page has none. A query with more pages than you can read is too broad: narrow it and log the narrower search.
- Save the version response as `registry-check/api-version.json` the same day.
- Log every search in `registry-check/search-log.json`:

```json
{"question": "Supervised exercise versus usual care for knee osteoarthritis pain",
 "searches": [{"id": "s1", "date": "2026-11-18", "pages": ["search/s1-p1.json"],
               "url": "https://clinicaltrials.gov/api/v2/studies?format=json&countTotal=true&pageSize=100&query.cond=knee%20osteoarthritis&query.intr=exercise"}],
 "relevance": [{"nct": "NCT99000101", "call": "similar", "reason": "Supervised exercise against usual care in knee osteoarthritis"}]}
```

| Field | Content |
|---|---|
| `id` | `s1`, `s2`: one per request series, used in the trial list's "Found by" |
| `url` | The first request exactly as sent, without `pageToken` |
| `date` | The day it was run, `YYYY-MM-DD` |
| `pages` | Every saved page of this search, in order |
| `relevance` | Optional: your call per trial, added after reading the list |

## The trial list

`search` writes `search.md` (the searches with their reported totals, every page with its SHA-256, then the trials) and `candidates.csv`. Each trial appears once, with the searches that found it, its status, start and primary completion dates with their types, enrolment with its type, whether results are posted, conditions and interventions. A field the saved page does not hold reads "not in page", which is not "none".

- A status says where the trial stands in the registry, not what it found: a completed trial may never have reported, and posted results are not a publication.
- An enrolment marked `ESTIMATED` is a target, not people enrolled.

## Relevance

Read each trial's record (open its own record when the page holds too little) and add a call:

| Call | Meaning |
|---|---|
| `similar` | Same population, intervention and comparison |
| `partial` | Shares the population or the intervention, not both, or a related comparison |
| `unrelated` | Returned by the query, but not on the question |

Every call needs a reason from the record's text, and names a trial in a saved page; the script refuses a call for any other number. Calls are labelled as yours, and an `unrelated` trial stays in the list.

## Published reports

The registry list shows trials, not their findings. With the `researchzy` plugin and an account, search `search_papers` for each completed or terminated trial: its NCT number, then its title words. The index matches titles and abstracts only, and whether it matches an NCT number as a keyword has not been confirmed, so try both. Save the results as JSON beside the pages, and report a paper as the trial's only when its title or abstract prints the number; otherwise say the link is your reading. Without Researchzy, say that published reports were not searched.

## What to tell the user

- The searches, the date and the registry; the number of trials, with their statuses as the registry gives them.
- The trials you judged similar, with their status, dates and enrolment type, and the withdrawn or terminated ones among them.
- When nothing was found: "These N searches of ClinicalTrials.gov on <date> returned no record." Never that the question is new, unstudied or a gap; other registries, other wordings and published trials were not searched.
