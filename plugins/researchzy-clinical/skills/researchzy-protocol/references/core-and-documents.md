# The core record and the three documents

The protocol, the registry draft and the analysis plan disagree when each is typed separately: the time point drifts, a sample size is retyped from an older draft, an outcome drops out of one of them. So every fact they share is written once, in `protocol/core.json`, and each document copies it. `protocol_check.py check` then confirms, item by item, that each document says what the record says.

## `core.json`

The example is **invented**; every value of a real record comes from the user's material or from a recorded calculation.

```json
{
  "study": "Supervised exercise versus usual care for knee osteoarthritis: two-arm randomised trial",
  "time_rule": {"month": "4 weeks", "source": "the user, message of 2026-11-18"},
  "outcomes": [
    {"id": "O1", "role": "primary", "measure": "Knee pain, WOMAC pain subscale", "key_terms": ["WOMAC", "pain|疼痛"],
     "timepoints": ["12 weeks"]},
    {"id": "O2", "role": "secondary", "measure": "Function, WOMAC function subscale", "key_terms": ["function|功能"],
     "timepoints": ["12 weeks", "26 weeks"]},
    {"id": "O3", "role": "secondary", "measure": "Adverse events", "key_terms": ["adverse|不良"], "timepoints": [],
     "documents": ["protocol", "registry"]}
  ],
  "numbers": [
    {"id": "randomised", "label": "participants randomised", "value": 120,
     "from": {"file": "statistics/power.json", "key": "inflation.n_total"}},
    {"id": "analysed_pp", "label": "analysed per protocol", "value": 110, "documents": ["sap"],
     "from": {"stated_by": "user", "note": "expected completers, user's message of 2026-11-18"}}
  ],
  "texts": [
    {"id": "population", "label": "primary analysis population", "documents": ["protocol", "sap"],
     "text": "all randomised participants, analysed in the arm to which they were assigned"}
  ]
}
```

| Key | Content |
|---|---|
| `outcomes` | `id`; `role`: `primary`, `secondary`, `exploratory` or `other`; `measure`; `timepoints`, each one time point ("12 weeks", "第12周"), or `[]` when there is none; `key_terms`: words every quote must contain, with `\|` between alternatives (`pain\|疼痛` for a bilingual set) |
| `numbers` | `id`, `label`, `value` as the documents print it (10 for "10%"), `from` (below) |
| `texts` | `id`, `label`, `text`: wording every document copies, such as an analysis population or a registry item |
| `documents` | Optional on any entry: which of `protocol`, `registry`, `sap` must state it. Default: all three |
| `time_rule` | Optional: how many weeks or days the user counts as one month, and who said so |

Write the record once, after the one question to the user, and change it afterwards only through the amendment log.

## Numbers are computed once

| Number | Computed by | `from` |
|---|---|---|
| Sample size of a comparison | `researchzy-statistics` (plugin `researchzy-manuscript`), `power.py` | `{"file": "statistics/power.json", "key": "inflation.n_total"}` (with attrition) or `"result.n_total"`; per group `"inflation.n_per_group.0"` |
| Events and patients for a time-to-event outcome | `researchzy-survival` (this plugin), `rz_survival.schoenfeld_events(..., path="survival/power-<name>.json")` | `{"file": "survival/power-<name>.json", "key": "events"}` or `"patients"` |
| A number the user gives (expected completers, sites) | the user | `{"stated_by": "user", "note": "where it comes from"}` |

`check` reads the file and compares; a proportion printed as a percentage takes `"factor": 100`. When the calculation is not installed or refuses (an effect "from experience" has no source, so `power.py` will not run), leave the number out of `core.json`, write `[Evidence needed: source of the expected effect]` in the sample-size section, and ask the user for a prior study, a pilot or the smallest effect that matters to them.

## Time points

`check` reads "12 weeks", "week 12", "12-week", "twelve weeks", "12周", "第12周" and "第十二周" as one time point, and "12 and 26 weeks", "weeks 12 and 26" or "12、26周" as two. Days convert to weeks (day 84 is week 12) and years to months. Months never equal weeks or days unless `time_rule` says how the user counts a month: months vary in length and protocols differ, so "3 months" and "12 weeks" may or may not be the same visit. Ask; never pick a rule yourself.

## `locations.json`

For every item and every document that must state it, the passage of the document that states it, copied word for word (at least three words; a Han character counts as one):

```json
{"O1": {"protocol": {"quote": "The primary outcome is knee pain (WOMAC pain subscale) at 12 weeks", "locator": "6.1"},
        "registry": {"quote": "WOMAC pain subscale, 12 weeks", "locator": "Primary outcome"}},
 "randomised": {"protocol": {"quote": "We will randomise 120 participants", "locator": "8"}}}
```

Quote the passage that gives the value, not one that only names the item. For a role, `check` reads the quote, then its line (a table row such as `| Primary outcome | … |`), then its headings.

## The three documents

Section orders below are conventions; a guideline file the user gives, or the institution's template, decides instead. Write no guideline item numbers unless the user's guideline file is open in this session.

- `protocol.md`: title and registration; background and rationale; objectives; design; setting; eligibility; interventions or exposures; outcomes with their time points; participant timeline; sample size; recruitment; assignment and blinding; data collection and management; statistical methods (summary, details in `sap.md`); monitoring and adverse events; ethics and consent; dissemination.
- `sap.md`: the estimand (population, treatment condition, variable, handling of intercurrent events, summary measure); analysis populations; the primary analysis; missing data; multiplicity; sensitivity and subgroup analyses, all fixed before data are seen. Never a rule that picks the test after looking at the data ("t test if normal, otherwise …"): name one analysis and, as a sensitivity analysis, the other.
- `registry.md`: the registry's own fields, named and ordered as on its form or page. Save that form or page in `protocol/registry-source/` with its address and the date read; without it, write the fields as `[Author input needed: registry field list]` and say that the draft follows no registry yet.

Institution-specific parts (committee, insurance, data protection officer, funding) are `[Author input needed: …]`. What is missing from the literature is `[Citation needed: …]`.

## What `check` reports

| State | Do |
|---|---|
| `consistent` | Nothing |
| `inconsistent` | The detail names the kind: `missing` (no quote), `number`, `time point`, `role`, `measure` or `wording`. Correct the document from `core.json`; if the record itself is wrong, change it through an amendment, then fix every document |
| `quote_not_found` | Copy the passage again from the document; never edit a document to make a quote fit |
| `not_checked` | The document does not exist yet |

Leads (lines that announce a primary outcome that no quote covers) do not fail: read each, and either add it to the record, delete it, or leave it when it only talks about the declared one. `check` exits 1 while any item is `inconsistent` or `quote_not_found`, or a recorded number differs from its file.
