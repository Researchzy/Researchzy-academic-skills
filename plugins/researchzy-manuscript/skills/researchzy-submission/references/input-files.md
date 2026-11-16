# The two input files

`check_package.py` and `check_anonymity.py` read two files in `submission/<venue-slug>/`. The first holds what the venue asks for; the second holds what only the authors know. Neither is ever filled from memory: the first comes from guidelines the user supplied, the second from the authors.

The examples below use an invented journal, the *Journal of Invented Ecology*, and invented authors. None of their numbers describe a real venue.

## requirements.json

Build it from the author guidelines the user gave (a file, a pasted text, or a page the user pointed to and you read in this session). Read the guidelines for the article type and the stage the user named: rules for an initial submission, a revision and a final version often differ.

```json
{
  "venue": "Journal of Invented Ecology (invented example)",
  "article_type": "Research article",
  "stage": "initial submission",
  "source": "author-guidelines.pdf supplied by the user",
  "date_read": "2026-11-13",
  "review_model": "double-blind",
  "limits": [
    {"name": "abstract_words", "value": 200, "counts": "unstructured abstract", "source": "author-guidelines.pdf p. 3", "date_read": "2026-11-13"},
    {"name": "main_text_words", "value": 6000, "counts": "Introduction to Discussion, without references, tables and legends", "include": [], "source": "author-guidelines.pdf p. 3", "date_read": "2026-11-13"},
    {"name": "highlights_count", "min": 3, "value": 5, "source": "author-guidelines.pdf p. 4", "date_read": "2026-11-13"},
    {"name": "highlight_characters", "value": 90, "counts": "characters including spaces", "source": "author-guidelines.pdf p. 4", "date_read": "2026-11-13"},
    {"name": "display_items", "value": 8, "source": "author-guidelines.pdf p. 5", "date_read": "2026-11-13"}
  ],
  "required_statements": ["author_contributions", "competing_interests", "funding", "ethics", "data_availability", "ai_use",
                          {"name": "patient_consent", "headings": ["Patient consent", "Consent for publication"]}],
  "required_files": [{"name": "figures", "pattern": "figure*", "extensions": ["tif", "eps", "pdf"], "max_mb": 10}],
  "deliverables": [
    {"name": "cover-letter", "status": "required"},
    {"name": "title-page", "status": "required"},
    {"name": "highlights", "status": "required"},
    {"name": "graphical-abstract", "status": "optional"},
    {"name": "suggested-reviewers", "status": "optional"},
    {"name": "significance-statement", "status": "not_accepted"}
  ],
  "not_found": ["keyword limit", "reference limit", "cover letter length: a letter is required, no length is given"]
}
```

### What to extract

| Field | Take from the guidelines | When they are silent |
|---|---|---|
| `venue`, `article_type`, `stage` | The names the guidelines use | Ask the user |
| `source`, `date_read` | The file name and page, or the URL; today's date | Never leave empty: without them every limit is `not_checked` |
| `review_model` | single-blind, double-blind, open, or what the venue calls it | Write `not stated`; `check_anonymity.py` can still be run |
| `limits` | Each number with its unit, what it counts and the page it is on | Leave the limit out and add it to `not_found` |
| `required_statements` | Every declaration the venue asks for, by the names below | Leave it out |
| `required_files` | File types and sizes the venue states | Leave it out |
| `deliverables` | Each item as `required`, `optional` or `not_accepted` | Leave it out; do not assume a letter is required |

Limit names the script measures: `title_characters`, `title_words`, `abstract_words`, `main_text_words`, `keywords`, `figures`, `tables`, `display_items`, `references`, `highlights_count`, `highlight_characters`, and `<file>_words` or `<file>_characters` for a package file (`cover_letter_words`, `significance_statement_words`). Any other name is recorded and reported as `not_checked`, to be checked by hand. `value` is a maximum, `min` a minimum.

Statement names: `author_contributions`, `competing_interests`, `funding`, `ethics`, `data_availability`, `code_availability`, `ai_use`, `acknowledgements`. For a statement the venue names differently, give it as an object with the headings to look for, as `patient_consent` above.

### The scope of a limit

A word limit means nothing until you know what it counts. Record it in `counts`, in the guidelines' own words, and set `include` on `main_text_words` when the venue counts more than the script's default.

- The script's main text runs from the first section heading after the abstract to the reference list, headings included. It leaves out the title block, abstract, keywords, tables, figure and table captions, end statements (contributions, funding, competing interests, data availability and the like), the reference list, appendices, citation markers and inline maths.
- `"include": ["captions", "statements", "tables", "references", "abstract"]` adds any of those parts back.
- Character limits count spaces unless the guidelines say otherwise; say which in `counts`.
- A page limit cannot be measured from the source: leave it to `researchzy-latex` (plugin `researchzy-manuscript`, when installed) or check the built PDF by hand.
- When the guidelines give a range of article types, record only the type the user named.

If the guidelines contradict themselves (two different numbers on two pages), record both pages in `source`, use the stricter number, and tell the user.

## authors.json

Ask the authors. Send one message that lists every field still empty; do not fill a field from a CV, a web page, an earlier paper or a guess. A field the authors have not answered stays a placeholder, which `check_package.py` lists under "still to supply or confirm".

```json
{
  "authors": [
    {"name": "Mira Okafor", "family_name": "Okafor", "name_native": "", "initials": "M.O.",
     "affiliations": ["Department of Ecology, Invented University, Northtown, Freeland"],
     "email": "m.okafor@invented.example", "orcid": "0000-0000-0000-0000",
     "corresponding": true, "equal_contribution": false,
     "roles": ["Conceptualization", "Investigation", "Writing – original draft"],
     "competing_interests": "none", "handles": ["mokafor"]},
    {"name": "Tomas Lindqvist", "initials": "T.L.",
     "affiliations": ["Institute of Soils, Example Institute, Southport, Freeland"],
     "roles": ["Formal analysis"],
     "competing_interests": "[Author input needed: competing interests of T.L., or confirmation of none]"}
  ],
  "funding": [{"funder": "Invented Science Foundation", "grant_number": "ISF-0000-0000", "recipient": "M.O."}],
  "ethics": [{"body": "Invented University Ethics Board", "approval_id": "IEB-0000-000", "consent": "written informed consent"}],
  "registrations": [{"registry": "[Author input needed: registry]", "id": "[Author input needed: registration id]"}],
  "ai_use": "[Author input needed: tools used, for what, how the output was checked; this package was drafted with an AI assistant]",
  "acknowledgements": "[Author input needed: people to thank, with their consent]",
  "preprints": [{"server": "[Author input needed]", "doi": ""}],
  "anonymity": {"handles": [], "repositories": ["soil-memory"], "earlier_venues": [], "other": ["Northtown Soil Survey"]}
}
```

- `authors` is in byline order. `initials` are the ones the contributions statement uses; `family_name` is needed when the family name is not the last word of `name`.
- `roles` use only the CRediT terms ([declarations](declarations.md)).
- `competing_interests` is a sentence per author, or `none` once the author has said so. Never write `none` for an author who has not answered.
- `funding` is a list, or the word `none` when the authors confirm there was no funding.
- `ethics` and `registrations`: one entry per approval or registration. Leave a list empty only when the authors confirm that none applies, and write the statement they confirmed ("The study used no human or animal subjects").
- `ai_use`: what the authors told you about their use of AI tools, including this session ([declarations](declarations.md)).
- `anonymity` lists other words that identify the authors: user names, repository and project names, the names of cohorts or sites, earlier venues where the work was presented.
