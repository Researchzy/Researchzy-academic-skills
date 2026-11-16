# Planning: claims, evidence, gaps, outline

The plan is four short files in `writing/`. They are written before any prose and kept up to date while drafting: a sentence that has no row in the ledger is not written.

The examples below are invented for illustration. Do not reuse their numbers.

## 1. Inventory (top of `claims.md`)

| File | What it is | What it can support |
|---|---|---|
| `results/cox_models.txt` | model output, 3 models | hazard ratios with intervals, sample sizes |
| `tables/table1.csv` | baseline characteristics by group | who was studied |
| `draft_intro.docx` | the author's introduction, 2 pages | background claims, to be checked against the `.bib` |
| `refs.bib` | 41 entries | citation keys; each entry alone is `metadata` |

Then one line on what a paper of this design needs and is not there. Each such item goes into the gap report.

## 2. The contribution in one sentence

Fill five slots, then join them:

- **Object**: what was studied, and in what or whom.
- **Design**: how (trial, cohort, benchmark on fixed splits, simulation).
- **Result**: the main finding, with its number or direction.
- **Evidence**: where that result is (table, figure, file).
- **Limit**: the condition under which it holds.

"In a registry cohort of 1,204 adults after stroke (object, design), home monitoring was associated with fewer recurrent strokes over 24 months (result; Table 2), in patients who were offered a monitor at discharge (limit)."

It must be a statement that a result could have contradicted. If the slots cannot be filled from the inventory, the paper is not ready to draft: say which slot is empty and put it in the gap report.

## 3. Claim ledger (`claims.md`)

One row per claim the paper will make, in the order of the argument.

| ID | Claim | Kind | Evidence | Grade | Cannot support |
|---|---|---|---|---|---|
| C1 | Recurrent stroke was less frequent with monitoring (48/602 against 71/602). | result | `results/cox_models.txt`, model 2; Table 2 | own-result | that monitoring caused the difference: the cohort is not randomised |
| C2 | Trials report lower blood pressure with home monitoring. | background | `[@baker2018]`, p. 4, read from the author's PDF | full-text | effects on stroke: the trial did not measure it |
| C3 | Monitoring after stroke has been studied in routine care. | background | `[@chen2020]`, `.bib` entry only | metadata | any finding of that study |
| C4 | No cohort has followed patients beyond one year. | novelty | none | none | the claim itself: `[Citation needed: search for cohorts with follow-up over 12 months]` |

- **Kind** is one of `result`, `method`, `background`, `interpretation`, `novelty`.
- **Evidence** names a file and a place in it (table, row, line, page), or a citation key and how the paper was read.
- A value you derive from the author's numbers (a percentage from counts, a difference) is marked "derived" with its arithmetic, for the author to confirm.
- **Cannot support** is filled for every row. It is what stops a sentence from saying more than its evidence.

## Evidence grades

| Grade | What you have | A sentence may | A sentence may not |
|---|---|---|---|
| `own-result` | a number, table or figure in the author's files, located | state the result with its number, unit and uncertainty, as the file gives them | give a number that is not in the files; turn an association into a cause |
| `full-text` | the cited paper, read in full in this session, with page or section | say what the paper did and found, with its population, conditions and numbers; compare it with the author's result | go beyond the passage read |
| `abstract` | the abstract only | report what the abstract states, attributed ("the authors report") | describe methods, sample, limitations or any number that is not in the abstract |
| `metadata` | title, authors, year, venue: a `.bib` entry or a search hit | say that these authors studied this topic | state any finding, direction, number or method |
| `none` | recollection | nothing | be written: use `[Citation needed: …]` |

A statement needs no citation only when it has no number, no name and no comparison, and a textbook of the field states it. Everything else has a row.

With the Researchzy tools, the grade follows the tool results of this session, not what the paper's title suggests: a hit from `search_papers` or `list_library_papers` is `metadata`; an abstract returned by `get_paper` is `abstract`; a full text obtained through `get_pdf_download` and read is `full-text`. Notes from `researchzy-deep-read` or a Paper Card (plugin `researchzy-reading`) count as `full-text` for the pages they cover. A paper raised to a higher grade gets its row updated.

## 4. Gap report (`gaps.md`)

| ID | Placeholder | Needed for | Who can fill it | If it is not filled |
|---|---|---|---|---|
| G1 | `[Evidence needed: number lost to follow-up in each group]` | Results, first paragraph; C1 | author, from the registry export | the flow of participants cannot be reported |
| G2 | `[Citation needed: cohort studies of monitoring with follow-up over 12 months]` | Introduction, gap; C4 | `researchzy-literature-review` | C4 is removed |
| G3 | `[Author input needed: ethics committee and approval number]` | Methods | author | the statement is left out and flagged |

Rules for placeholders:

- Exactly three types: `[Evidence needed: …]`, `[Citation needed: …]`, `[Author input needed: …]`. The text after the colon says what would fill it, specifically enough that someone else could go and get it.
- One placeholder per missing item, at the place in the text where the item belongs.
- A placeholder leaves the text in one of two ways: the item arrives, or the sentence that needed it is removed or narrowed to what the evidence supports. Never by a guess, and never by deleting the placeholder and keeping the sentence.
- The final check (`--final`) fails while any placeholder remains. A text with open gaps is delivered as a draft, with `gaps.md`.

## 5. Outline (`outline.md`)

Per section: its word budget. Per paragraph: one job, a topic sentence, evidence slots, words.

```markdown
## Results (budget 900)

1. [result] Of 1,204 patients, 602 were monitored; the groups were similar at baseline.
   Evidence: Table 1; G1 (flow). 120 words.
2. [result] Recurrent stroke was less frequent with monitoring.
   Evidence: C1, Table 2, Figure 1. 150 words.
3. [result] The difference was smaller in patients over 80. Evidence: C6, Table 3. 120 words.
```

- The topic sentences, read alone and in order, must give the paper's argument. If they do not, fix the outline, not the prose.
- A paragraph with an empty evidence slot is a gap: add it to `gaps.md`.
- For a paper with a reporting guideline, each checklist item that applies gets a slot in the paragraph where it will be reported.

**Word budget.** The limits are the venue's, as the author supplied them. Record in `outline.md` where they came from (the file or link, and its date). When the author has only a total, propose a split and ask for confirmation; a common starting point for an IMRaD paper is Introduction 10–15%, Methods 25–30%, Results 25–30%, Discussion 25–30%. When there is no limit at all, leave the budget open and report the counts. Pass the budget to the check as `--budget "Abstract=250,Introduction=600,Total=3500"`; `Total` is the main text without abstract, tables and references.

## Papers outside IMRaD

For theory, humanities, law and qualitative work, use sections 1 to 4 with these changes: the evidence is a source, a passage, a case, a proof or a transcript excerpt, located in the same way; `own-result` means the author's own material (data, corpus, derivation). Stop after the gap report. The outline format, the writing order, the section rules and the number checks assume a quantitative empirical paper and do not transfer.
