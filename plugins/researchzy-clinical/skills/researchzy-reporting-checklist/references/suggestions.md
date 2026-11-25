# Suggestions for what is missing

A suggestion tells the authors what to add for a partly reported or not reported item, so that they can write it. It goes into `gaps.md`, never into the list to upload, and never into the manuscript.

## What a suggestion says

- What to add, in the item's terms, and where: "In Methods, after the paragraph on recruitment, state …".
- Only what the item asks for. Do not suggest new analyses, new data or a different design: the checklist asks what is reported, not how the study should have been done.
- One suggestion per item, short. Drafting the paragraph is `researchzy-writing` (plugin `researchzy-manuscript`, when installed), with the authors.
- Facts that the manuscript or the supplement already contains may be used as they are written there ("all 530 eligible workers").

## Facts only the authors have

Every fact the documents do not contain goes into a placeholder, never into the suggestion's own words:

| Placeholder | For |
|---|---|
| `[Author input needed: …]` | Names of committees, funders, sites and people; approval and registration numbers; dates; numbers of participants; decisions the authors made |
| `[Evidence needed: …]` | A result that would have to come from the data |
| `[Citation needed: …]` | A source the text must cite |

```text
Wrong: State that the Riverside ethics committee approved the study (approval 2023-114).
Right: Name the ethics committee and give the approval number: [Author input needed: name of the ethics committee and approval number].
```

## What check compares

`check` fails a suggestion that holds a date or a code (a registry-shaped id such as NCT…, CRD42…, ISRCTN… or ChiCTR…, an approval number such as 2023-114) that neither the manuscript nor the supplement contains, outside a placeholder. A plain number that the documents do not contain is `not_checked`: it may be a convention, such as a 95% interval; if it is a number about this study, move it into a placeholder.

- Numbers count as the documents write them: "12-week" holds 12; "2023-114" must appear as 2023-114; "1,234" and "1234" are the same; full-width digits count as ordinary digits, and numbers touching Chinese characters ("样本量为312人") are read.
- Dates count whatever the form: "12 March 2019", "March 12, 2019", "2019-03-12" and "2019年3月12日" are the same date; "March 2019" is found when the documents give that month.
- An item id with a letter ("item 8b") is not a fact.
- Names and words are not compared, and numbers written as words are not read: the rule binds them all the same.

On a failure, put each named fact into a placeholder. If the fact is in the documents in another form, copy it as the documents write it.
