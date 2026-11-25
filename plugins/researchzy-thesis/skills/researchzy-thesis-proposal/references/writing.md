# Literature, wording and the check

## The literature basis

The ledger is `review_ledger.py` from `researchzy-literature-review`, kept in `thesis-proposal/literature`. Every command takes `--dir thesis-proposal/literature` before the command name.

| Step | Command |
|---|---|
| Scope | `brief --topic "…" --question "RQ1 …" --size quick` |
| Log a search, before adding its results | `search --query '"移动学习" 信任' --total 212 --pass relevance` |
| Add what the search returned, as saved JSON | `add results.json --search s1` |
| Add the supervisor's or the student's papers | `add supervisor.json --seed` |
| Decide | `decide <key> --include`, or `decide <key> --exclude --reason "…"` |
| Record how far a paper was read | `read <key> --depth full_text --source <file>` (or `abstract`, `metadata`) |
| Counts, passes not run, papers not read | `status` |
| `papers.csv`, `references.bib`, `search-log.md` | `export` |

- **Size.** A proposal needs a quick map: the papers that frame each question, the earlier reviews and the contrary findings. A full review is the job of `researchzy-literature-review` (plugin `researchzy`, when installed).
- **The supervisor's list, with Researchzy.** Look each entry up with `search_papers` by `doi`, or by `query` with its exact title. A record whose title, authors and year match is added with `add --seed`. No match, or a DOI that returns a different paper: add the entry as given (title, authors, year, DOI) with `--seed` and exclude it with the reason ("not found in the index by DOI or title", "DOI 10.… belongs to another paper: <its title>"). Report each one to the student; none is cited.
- **Without Researchzy.** Add only the papers the student supplies, as given, and record what was read. They carry no index id; the check lists them as `user_supplied`, and the limitations say the literature was not searched. Whether such references exist is checked by `researchzy-reference-check` (plugin `researchzy-manuscript`, when installed).
- **Coverage.** Researchzy's index matches keywords in titles and abstracts; it has no author search, no cited-by lists and no retraction data, and how much Chinese-language literature it holds is not known. Add the student's Chinese sources by hand; they are then `user_supplied`.
- **Reading depth.** `full_text`: methods, samples and numbers may be described. `abstract`: say only what the abstract reports. `metadata` or `none`: do not describe the paper at all; the check fails a citation of it.

## Gaps and novelty

A gap is a statement about searches. Write it with the searches it rests on:

- "在 2026-11-18 对 Researchzy 索引的 6 次检索中（检索式见 literature/search-log.md），没有找到在高校移动学习平台情境下检验信任与持续使用意愿的研究。"
- "None of the 212 records returned by the searches in Appendix A tested …"

Never write "国内尚无相关研究", "no study has examined" or "for the first time" without them; the check lists such sentences as `gap_claims`.

## Wording the plan

| Kind | How |
|---|---|
| Expected results | "预期…", "拟检验…", "we expect", "we will test whether"; never the past tense |
| Hypotheses | Stated as hypotheses, each tied to a question id |
| Pilot result with data | Past tense, with the numbers from the student's file and the file's name |
| Pilot result without data | The student's attributed statement, not built on: "据学生的预调查记录（数据未提供），…"; or `[Author input needed: pilot data for …]`. No sample size, claim or hypothesis rests on it |
| Resources and access | Only as `brief.json` records them; an unconfirmed access is `[Author input needed: confirm access to …]` |
| The supervisor's project | Only what the student or the supervisor wrote |

Placeholders take the house forms: `[Evidence needed: …]`, `[Citation needed: …]`, `[Author input needed: …]`. A section the template requires but the student cannot fill yet keeps its heading and a placeholder; it is never dropped.

## The `manual` rows

`check` reads `proposal.md`, `template.json`, `brief.json`, `matrix.csv`, `timeline.csv` and the ledger. Besides the failures in SKILL.md it gives these `manual` rows, which go to the student unchanged:

| Row | What the student does |
|---|---|
| `section_limit` with an approximate limit | Decides, with the supervisor, whether the count is close enough |
| `no_open_placeholders` | Fills each placeholder listed under the table |
| `citations_abstract_only` | Confirms the draft says no more than the abstracts report, or supplies the full text |
| `citations_user_supplied` | Accepts that these were not checked against an index; the limitations say so |
| `result_sentences` | Confirms each sentence is their own data, or it becomes a placeholder |
| `gap_claims` | Names the searches, or rewords |
| `template_item`, `conflict` | Provides the signature, table or attachment; decides which file governs |

`not_checked` rows say what was missing (no ledger, no `matrix.csv`, no questions yet); `not_stated` rows say the template is silent. Neither is a pass.

## Export and hand-over

- **Word template.** With pandoc, `pandoc thesis-proposal/proposal.md -o thesis-proposal/proposal.docx --reference-doc <the school's .docx>` takes the template's styles. Citations stay as keys unless the school's citation style is supplied as a CSL file; then add `--citeproc --bibliography thesis-proposal/literature/references.bib --csl <file>`. Without pandoc, say that the export was not done and hand over `proposal.md`.
- **Form templates.** When the template is a table of labelled cells, do not rebuild it. Write `thesis-proposal/form-map.md` with one row per cell: the label as the template's text shows it, the section of `proposal.md` that fills it, and its limit. The student pastes the text. Filling and formatting the school's file belongs to `researchzy-thesis-build` (plugin `researchzy-thesis`, when installed).
- **Hand-over.** Give `proposal.md` (and `proposal.docx`), `report.md`, `timeline-check.md` and `template-check.md`, with the files read and their dates, every reference of the supervisor's list that was excluded and why, every `manual`, `not_checked` and `not_stated` row, and the open placeholders.
