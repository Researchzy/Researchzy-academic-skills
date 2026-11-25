# Matching the paper to its record, item by item

Everything the comparison rests on is declared in `registry-check/items.json`: quotes from the paper, and for the record only field paths. The script reads the record's values itself, checks each quote against `paper.txt`, and compares. Paths in the file are read from `registry-check/`, then from the working directory.

## First: is it the paper's trial?

A registration number copied wrongly by one digit leads to another trial's record, and every comparison after that is meaningless. So the record is compared with the paper before any item.

- `identity` holds four quotes from the paper: `title`, `condition`, `intervention`, `sponsor` (the funder or sponsor the paper names). Each needs at least two words and a locator.
- The script compares each with the record's title fields, conditions and keywords, intervention names and arm labels, and sponsors: a field is `consistent` when at least half of the quote's content words occur in the record (a convention of this script), and `inconsistent` otherwise.
- `same`: title, condition and intervention agree. `partial`: some agree; confirm with the user. `different`: all three disagree, and nothing else is compared. `unconfirmed`: none is shown to agree (a quote is missing, or the paper is in another language); nothing else is compared.
- A paper not in English: add `translation`, your English rendering of the quote, to each identity entry and each outcome item. The quote is still checked against the paper; time points and numbers are read from the quote itself; the report marks every comparison made through a translation as such.
- Enrolment and dates are items, not identity: an ESTIMATED 200 against 150 randomised is the same trial.

## items.json

```json
{"paper": {"text": "paper.txt",
           "published": {"date": "2025-03-14", "quote": "Published online 14 March 2025", "locator": "p. 1"}},
 "record": {"file": "record-NCT99123456.json", "read": "2026-11-18"},
 "registrations": [{"registry": "ClinicalTrials.gov", "id": "NCT99123456", "quote": "ClinicalTrials.gov NCT99123456", "locator": "p. 1"},
                   {"registry": "EudraCT", "id": "2019-004567-12", "quote": "EudraCT 2019-004567-12", "locator": "p. 1"}],
 "identity": {"title": {"quote": "Supervised exercise versus usual care for knee osteoarthritis", "locator": "p. 1"},
              "condition": {"quote": "Adults with knee osteoarthritis were recruited", "locator": "p. 2"},
              "intervention": {"quote": "attended supervised exercise", "locator": "p. 2"},
              "sponsor": {"quote": "Lakeside University Hospital research fund", "locator": "p. 1"}},
 "items": [
   {"id": "O1", "kind": "outcome", "role": "primary", "locator": "p. 2, Methods",
    "quote": "The primary outcome was knee function (WOMAC physical function subscale) at 26 weeks",
    "record": "protocolSection.outcomesModule.secondaryOutcomes[0]",
    "disclosure": {"searched": "Methods, Discussion and the supplement"}},
   {"id": "O3", "kind": "outcome", "role": "secondary", "quote": "quality of life (EQ-5D-5L) at 26 weeks",
    "locator": "p. 2", "record": null, "disclosure": {"searched": "Methods and Discussion"}},
   {"id": "N1", "kind": "enrollment", "basis": "planned", "value": 200, "quote": "We planned to recruit 200 participants", "locator": "p. 2"},
   {"id": "D1", "kind": "date", "date": "2020-02-03", "quote": "Between 3 February 2020 and 30 June 2021", "locator": "p. 2",
    "record": "protocolSection.statusModule.startDateStruct"},
   {"id": "R1", "kind": "registration_claim", "claim": "prospective", "quote": "The trial was prospectively registered", "locator": "p. 1"},
   {"id": "I1", "kind": "intervention", "quote": "supervised exercise, two 45-minute sessions a week for 12 weeks", "locator": "p. 2",
    "record": "protocolSection.armsInterventionsModule.interventions[0]"}],
 "unreported": [{"record": "protocolSection.outcomesModule.secondaryOutcomes[1]", "searched": "Results, Tables 2 and 3, the supplement"}]}
```

The example is invented; the number is outside the range the registry has issued.

| Kind | Fields besides `id`, `quote`, `locator` | Compared with |
|---|---|---|
| `outcome` | `role` in the paper (`primary`, `secondary`, `other`); `record`: the path of one registered outcome, or `null`; `translation`, `earlier`, `disclosure` as needed | Its role, time points and measure |
| `enrollment` | `basis`: `planned` or `actual`; `value`: the number in the quote | `designModule.enrollmentInfo`, by its type |
| `date` | `date` as the paper gives it (`YYYY`, `YYYY-MM`, `YYYY-MM-DD`); `record`: a date path, such as `startDateStruct` or `studyFirstSubmitDate` | The date, to the precision both have |
| `registration_claim` | `claim`: `prospective` or `retrospective` | First submitted against the actual start |
| `intervention`, `other` | `record`: a path | Numbers and time quantities; the wording as a lead |

- Every quote of an item is one continuous passage, copied from `paper.txt`, of at least four words (or Han characters): the script reads time points and numbers from it, so words gathered from different sentences are refused. The value, date or number the item states must be in its quote.
- `registrations`: every number the paper prints, each with a quote that contains it. The ClinicalTrials.gov number must be the record's; any other registry stays `not_checked` ([fetching records](fetching-records.md)).

## Pairing outcomes

- List every outcome the paper reports, from Methods, Results, tables and the supplement, with the role the paper gives it. A primary outcome's quote should say "primary" (or 主要); the report flags one that does not.
- Pair each with at most one registered outcome: the same construct, measured the same way. Pair by what is measured, not by the role or the time point, since those are what the comparison tests. The pairing is your judgement and the report says so.
- An outcome with no registered counterpart gets `"record": null`: it is `inconsistent (added)`.
- For each registered outcome no item pairs, search the paper for it and add an `unreported` entry with where you looked; with a quote where the paper explains its absence, add `disclosure` to that entry. It is then `inconsistent (omitted)`. Without an entry it stays `not_checked`.
- With `--earlier`, give each outcome item `earlier`: the path of the same outcome in the earlier version, or `null` when that version lacks it.

## States and types

| State | Meaning |
|---|---|
| `consistent` | Every facet the script compares agrees |
| `inconsistent` | At least one facet differs; the types say which |
| `not_checked` | A facet could not be compared; the reason is given. Never a pass |

| Type | The difference |
|---|---|
| `role` | Primary in one, not in the other |
| `timepoint` | The paper's time point is not among the registered ones. "Week 12", "12 weeks", "12-week" and "第12周" are one time point; weeks are never turned into months, so "3 months" against "12 weeks" is a difference for a person to judge |
| `measure` | Two different named instruments, such as VAS against WOMAC. Other wording that differs is `not_checked` with "read both texts" |
| `added`, `omitted` | Reported but not registered; registered but not reported |
| `value` | A number or date differs |
| `timing` | The claim of prospective or retrospective registration disagrees with the record's dates |

## Disclosure

Every outcome that ends up `inconsistent`, against the current record or the earlier version, needs `disclosure`: a `quote` and `locator` where the paper states the change (a protocol amendment, a note in Methods), or `searched` with every place you looked. The report gives it beside the item. A paper that states a change has still changed the outcome; the report says both.
