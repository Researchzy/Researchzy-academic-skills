# Protocol

The protocol fixes the question, the criteria and the methods before any record is screened. The user confirms it once, before the searches start. Every later change is an amendment, and the report states it.

## Frame

| Frame | Use for | `elements` keys |
|---|---|---|
| PICO | Effects of an intervention | `population`, `intervention`, `comparator`, `outcome` |
| PECO | Effects of an exposure that nobody assigned | `population`, `exposure`, `comparator`, `outcome` |
| PIRD | Accuracy of a test | `population`, `index_test`, `reference_standard`, `diagnosis` |
| PCC | Other questions about a concept in a context, such as prevalence or experience | `population`, `concept`, `context` |

A request to map a field rather than answer one question is a scoping or narrative review: hand it to `researchzy-literature-review` (plugin `researchzy`, when installed).

## Criteria and codes

- One condition per code. `I1`, `I2`, … say what a study must have. `E1`, `E2`, … are the reasons to exclude a record, each written so that a quote from a title, an abstract or a full text can show it.
- Cover the frame and the study: population, intervention or exposure, comparator, outcome, design, and type of report (an editorial or a protocol without results is not a study report).
- `exclusion_order` lists every E code once. A record that fails several criteria is excluded under the first of them in this order, so each record has one reason and the counts per reason add up. Put first the criteria that are quickest to judge from a title (convention): type of report, design, population.
- Never renumber or reuse a code. Changing what a code means is an amendment, and `check` lists the decisions made under the old meaning.

## The other fields

| Field | Content |
|---|---|
| `outcomes` | `name`, `role` (`primary` or `secondary`), `measures`, `timepoints` (a list; `["any"]` when any time point counts) |
| `designs` | The designs that count, for example parallel, crossover and cluster randomised trials |
| `sources` | Every source to search, including one that cannot be searched, with the reason |
| `limits` | Date, language or publication-type limits, each with `limit` and `reason`. None by default: every limit can drop eligible studies |
| `calibration` | `kappa_min`, `recall_min`, `user_screens` (true or false), and `declined_reason` when false |
| `registration` | `status`: `registered`, `planned` or `not_registered`; when registered also `registry`, `id`, `date` (YYYY-MM-DD) |
| `seeds` | Papers the user knows must be found, each with a `doi`, `pmid`, `nct` or `title` |

The calibration thresholds are conventions that the user can change: kappa at least 0.60, and an include recall of 1.0, meaning that the model includes or marks unsure every sampled record that the user includes or marks unsure.

## Registration

Take the registry, the number and the date from the user; never look them up on the registry's pages, guess or complete them. The sentence for the report comes from `prisma.json` (`registration`), which compares the registration date with the first logged database or register search:

| Situation | The sentence says |
|---|---|
| Registered before the first search | "prospectively registered with <registry> (<id>) on <date>, before the first search on <date>" |
| Registered on the day of the first search, or later | "registered … the day of" or "after the first search on <date>" |
| Registration planned | "not registered (registration is planned)" |
| Not registered | "not registered" |

Never call a registration prospective in your own words.

## Example

```json
{
  "title": "Prehabilitation exercise before knee replacement: a systematic review",
  "question": "In adults awaiting knee replacement, does supervised exercise before surgery improve function afterwards compared with usual care?",
  "framework": "PICO",
  "elements": {"population": "adults awaiting primary total knee replacement",
               "intervention": "supervised exercise programme before surgery",
               "comparator": "usual care or education only", "outcome": "physical function after surgery"},
  "criteria": [
    {"code": "I1", "text": "Randomised controlled trial"},
    {"code": "I2", "text": "Adults awaiting primary total knee replacement"},
    {"code": "I3", "text": "Supervised exercise before surgery against usual care or education"},
    {"code": "E1", "text": "Not a randomised controlled trial"},
    {"code": "E2", "text": "Revision surgery or other joints only"},
    {"code": "E3", "text": "No exercise before surgery"},
    {"code": "E4", "text": "No outcome measured after surgery"},
    {"code": "E5", "text": "Not a study report (editorial, comment, protocol without results)"}],
  "exclusion_order": ["E5", "E1", "E2", "E3", "E4"],
  "outcomes": [{"name": "Physical function", "role": "primary", "measures": "validated function scales",
                "timepoints": ["6 weeks after surgery", "12 months after surgery"]},
               {"name": "Length of hospital stay", "role": "secondary", "timepoints": ["index admission"]}],
  "designs": ["randomised controlled trial, parallel or cluster"],
  "sources": ["Researchzy index", "PubMed", "ClinicalTrials.gov"],
  "limits": [],
  "calibration": {"kappa_min": 0.6, "recall_min": 1.0, "user_screens": true},
  "registration": {"status": "not_registered"},
  "seeds": [{"doi": "<a DOI the user gave>"}]
}
```

## Amendments

Edit `protocol.json` and record the change:

```sh
python3 "$SKILL_DIR/scripts/sr_ledger.py" protocol systematic-review/protocol.json --amend "E3 now also excludes home exercise without supervision" --results-seen yes
```

`--results-seen yes` means that screening results had been seen when the change was made; after a failed calibration it is always yes. Add the amendment to `protocol.md` and to the report's methods. `check` fails while `protocol.json` differs from the recorded version.

## protocol.md

Write it from `protocol.json` in this order: title and date; the question and its frame; a table of the criteria (code, criterion); the exclusion order; outcomes; designs; sources; limits with reasons; who screens and the calibration thresholds; registration; amendments. End with this section, filled from the protocol:

```markdown
## Registry summary

Fields as understood on <date>; the registry's current form takes precedence.

- Review title:
- Question:
- Sources and planned search dates:
- Population; intervention or exposure; comparator:
- Outcomes, with time points (primary, secondary):
- Study designs:
- Eligibility criteria (codes and texts):
- Screening and data extraction: <the model screens and extracts; the user calibrates it on a sample of records>
- Risk of bias and synthesis: <planned, and with what, or not planned>
```
