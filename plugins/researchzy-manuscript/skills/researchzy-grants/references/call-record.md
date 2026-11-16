# The call record

Everything this skill knows about a funder comes from the call text the user supplied. The record, `grant/requirements.json`, holds what that text demands, each entry with the call's own words, so that `grant_check.py call` can confirm the words are really there.

## No call text

Stop. Tell the user that the sections, their order, the limits, the criteria and the budget rules all come from the call, and that you will not take them from memory, because funders change them between rounds and between schemes. Ask for the call document, the guide for applicants, or the URL of the call page. If the user then asks for the aims or objectives page on its own, you may draft it ([aims](aims.md)); say that it is not yet fitted to any call.

## Getting the text

- PDF: `pdftotext -layout call.pdf grant/call.txt`. The form feeds it writes between pages let the script report the page a quote is on. A scanned PDF gives no text; ask for a text version.
- Web page: save the page's text as `grant/call.txt`, with its URL and the date at the top.
- Several documents (call, guide for applicants, evaluation guide, FAQ, amendment): put each in its own text file and concatenate them into `grant/call.txt` in that order, with a heading line naming each. A record checked against one file cannot quote another.

## Reading a call

Read the whole text once before writing anything. Then look for each item below and record where it is.

| Look for | Typical places | Record as |
|---|---|---|
| Identifier, funder, scheme, stage or round | Title page, header | `call` |
| Sections, their order, which are required | "Structure of the proposal", templates, part A/B | `sections` |
| Limits: number, unit, what counts (references, tables, captions, spaces) | Next to each section, a formatting annex | `limit`, `total_limit` |
| Review criteria and their weights | "Evaluation", "assessment", "selection criteria" | `criteria` |
| Budget cap, currency, project duration, eligible and ineligible costs, overhead rules | "Funding", "budget", "financial rules" | `budget` |
| Deadline with time and time zone | Key dates | `deadline` |
| Who may apply | "Eligibility", "who can apply" | `eligibility` |
| Font, margins, line spacing, file type | Formatting annex | `formatting` |
| Rule on AI tools in writing the proposal | Guide for applicants, conduct rules, FAQ | `ai_policy` |
| Required documents beside the proposal | "Annexes", "supporting documents" | `attachments` |

- **Amendments and FAQ.** Ask whether there is a corrigendum, an amendment or an FAQ for this round, and read it last: a later document overrides an earlier one. Quote the later one.
- **Several schemes in one call.** Record only the scheme or stage the user chose. If they did not say and the limits differ, that is the one question to ask.
- **Ambiguity.** If the call is unclear (a limit "of about two pages", criteria named in two different ways), record what it says, quote it, and tell the user. Do not resolve it from what funders usually mean.
- **Date read.** `date_read` is the day you read the text. Calls change; a record is valid for the version read on that day.

## The format

Every key below must be present. When the call says nothing about an item, write the string `"not_stated"`: that separates "the call is silent" from "nobody looked". Every stated entry has a `quote` (copied word for word from the call, at least three words, from one place, with no ellipsis) and a `locator` (page, section or paragraph).

| Key | Value |
|---|---|
| `call` | `identifier`, `funder`, `mechanism` (scheme and stage), `source` (file or URL), `date_read` (YYYY-MM-DD). `identifier` and `mechanism` may be `"not_stated"`. |
| `sections` | List of `{name, required, limit, quote, locator}`. `name` is the call's own name for the section; the proposal uses it as the heading. `required` is `true`, `false` or `"not_stated"`. |
| `limit` | `"not_stated"`, or `{value, unit, counts}` with `unit` one of `words`, `characters`, `pages`. It may carry its own `quote` and `locator`; otherwise the section's are used, and they must contain the number. |
| `counts` | `"not_stated"`, or an object with any of `references`, `tables`, `figure_captions`, `spaces`, each `"included"`, `"excluded"` or `"not_stated"`. A key left out is `"not_stated"`. |
| `total_limit` | A limit for the whole proposal, or `"not_stated"`. |
| `criteria` | List of `{name, weight, quote, locator}`; `weight` as the call writes it ("30%", "x2") or `"not_stated"`. |
| `budget` | `{cap, currency, period, rules}`. `cap`: `{value, quote, locator}`. `currency`: a code or symbol as the call writes it. `period`: the project duration, `{months, quote, locator}`. `rules`: list of `{rule, quote, locator}`, the rule in your words and the quote in the call's. Each part may be `"not_stated"`, or the whole `budget`. |
| `deadline`, `eligibility`, `formatting`, `ai_policy` | `{value, quote, locator}`: `value` in your words. |
| `attachments` | List of `{name, required, quote, locator}`. |

The example below is **invented**: the Example Foundation and its call do not exist, and none of its numbers describes a real funder.

```json
{
  "call": {"identifier": "EF-DISC-07", "funder": "The Example Foundation (invented)",
           "mechanism": "Discovery Grants, full proposal", "source": "grant/call.txt",
           "date_read": "2026-11-12"},
  "sections": [
    {"name": "Summary", "required": true,
     "limit": {"value": 150, "unit": "words", "counts": "not_stated"},
     "quote": "a Summary of no more than 150 words", "locator": "p. 1, section 2.1"},
    {"name": "Research plan", "required": true,
     "limit": {"value": 1200, "unit": "words", "counts": {"references": "excluded", "tables": "included"},
               "quote": "at most 1,200 words, excluding the reference list", "locator": "p. 1, section 2.3"},
     "quote": "The Research plan sets out", "locator": "p. 1, section 2.3"},
    {"name": "Data plan", "required": false, "limit": "not_stated",
     "quote": "Applicants may add a Data plan", "locator": "p. 2, section 2.6"}
  ],
  "total_limit": "not_stated",
  "criteria": [
    {"name": "Significance", "weight": "40%", "quote": "Significance of the question (40%)", "locator": "p. 2, section 3"}
  ],
  "budget": {"cap": {"value": 120000, "quote": "up to EUR 120,000 per project", "locator": "p. 2, section 4"},
             "currency": "EUR",
             "period": {"months": 24, "quote": "for a period of 24 months", "locator": "p. 2, section 4"},
             "rules": [{"rule": "No equipment.", "quote": "Equipment is not an eligible cost", "locator": "p. 2, section 4"}]},
  "deadline": {"value": "15 May, 14:00 local time", "quote": "no later than 14:00 on 15 May", "locator": "p. 1"},
  "eligibility": "not_stated",
  "formatting": "not_stated",
  "ai_policy": {"value": "AI use must be declared in the form.", "quote": "declare the use of generative AI tools",
                "locator": "p. 3, section 6"},
  "attachments": [{"name": "Letter from the host", "required": true,
                   "quote": "a letter from the host institution", "locator": "p. 3, section 5"}]
}
```

## Checking the record

```sh
python3 "$SKILL_DIR/scripts/grant_check.py" call grant/call.txt
```

Quotes are compared after setting aside case, spacing, words split at a line break, curly or straight quotes, dashes and hyphens. The command writes `grant/call-check.md` and exits 1 when a quote is not in the text, or when a limit, the cap or the period has no usable quote.

| State | Do |
|---|---|
| `quote_found` | Nothing. If the note says the value is not in the quote, compare them: "two pages" is 2, "1,500 words" is 1500. |
| `quote_not_found` | Copy the passage again from the call. Never edit the call text to make a quote match. |
| `no_quote`, `quote_too_short` | Add the call's words. If the call does not say it, the entry is `"not_stated"`. |
| `not_stated` | Report it to the user as silent in the call. Do not fill it from memory. |

`check` reports the record as `not_checked` until `call` has passed on the current version of the file.

## The requirement matrix

Before drafting, add a table to `grant/criteria.md`, after the review table ([review](review.md)), with one row per requirement of the record that is not a section or a criterion: budget rules, deadline, eligibility, formatting, AI policy, attachments.

```markdown
## Requirements

| Requirement | Call | Where in the draft | Gap |
|---|---|---|---|
| Equipment is not eligible | p. 2, section 4 | budget.csv | None |
| Letter from the host | p. 3, section 5 | Attachment, not drafted | The applicant obtains it |
```

The script does not read this table; it is the list you and the user work through. `report.md` lists the same items as `not_checked`.
