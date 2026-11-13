# Synthesis

A review is not a list of summaries. It answers the brief's questions by setting papers against each other.

## Before writing

1. **Themes from the table.** Read down the `theme`, `method` and `result` columns of the extraction and group the included papers into three to six themes that follow from the questions: approaches, populations, mechanisms, periods. Each paper belongs mainly to one. A theme with a single paper is a sign either of a gap or of a search that missed its neighbours; check which.
2. **What each section may cite.** List the papers of each theme before drafting its section, and write the section from those rows. This keeps a citation from drifting into a paragraph because its title sounds right.
3. **Coverage.** Make a small table of theme against number of papers, how many were read in full, and the span of years. Where a cell is thin, either search again or name the thinness in the text.

## Writing a theme

- Open with what the papers of the theme establish together, in one or two sentences.
- Compare inside sentences. "One trial finds the effect in adults [@key1], while a larger one finds it only at the highest dose [@key2]" tells the reader more than two paragraphs that each describe one paper.
- When papers disagree, look for the condition that differs: population, dose, measure, time scale, dataset, definition. State it. If nothing explains the disagreement, say that it is unresolved.
- Give numbers with what they measure and in whom. Take them from the `result` and `locator` fields; if a number is not in the extraction, do not write it.
- End with what the theme leaves open.

## How strongly to say it

Match the wording to the evidence in the ledger, not to the confidence of the papers' own abstracts.

| Evidence among the included papers | Wording |
|---|---|
| Several independent studies, different groups and data, agree | "X is well supported", "consistently" |
| Two or three studies agree, or several from one group or one dataset | "X has been reported", "evidence from … suggests" |
| One study | "one study found", with its design and size |
| Studies disagree | State both sides and the condition that may separate them |
| Read from the abstract only | "the authors report", and nothing about method or limitations |

Count independent support, not papers. Three papers from one lab on one cohort are one line of evidence. A review article that repeats a finding is not a further study of it.

## Gaps

A gap is a claim about the literature, so it needs evidence of absence:

- Name the searches that looked for it (their ids in the search log) and what they returned.
- Say how sure you are: a gap seen after several phrasings, a recent-years search and a check of the reviews is firmer than one seen after a single query.
- Distinguish "not studied" from "studied, with mixed results" and from "studied in a neighbouring field under another name".

## The comparison table

One row per core paper, or per included paper in a quick map. Columns that carry the comparison for this topic, for example: design or method, data or sample, main result, conditions or limits. Give the table a caption that states what it shows, not only what it contains.

## Limitations to state

- The index: what it covers, and the newest publication date seen.
- The search: the passes run, the results looked at out of those reported, and that papers citing the core works could not be traced forward.
- Reading depth: how many included papers were read in full and how many from the abstract.
- Anything excluded by the scope that a reader might expect.

## Before delivering

- `review_ledger.py check review.md` reports `ok`.
- Each question of the brief has an answer in the conclusion, even if the answer is "the included studies do not settle this".
- Every number, "first", "largest" and "state of the art" in the text can be traced to a row of `papers.csv` with a locator.
- No sentence describes the method or limitations of a paper whose `read` is `abstract`.
