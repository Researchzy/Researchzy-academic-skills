---
name: researchzy-writing
description: "Plan, draft or revise an empirical research paper (IMRaD) from the author's own results: claim ledger, gap report, outline with word budget, evidence-first drafting, scripted checks of numbers, placeholders and citation keys. Use to write a manuscript or polish a draft without changing its meaning."
---

# Researchzy Writing

This skill writes a research paper from what the author has: results, tables, figures, notes and a bibliography. Before any prose, every claim is tied to one of the author's results or to a cited paper and how far that paper was read. What is missing is marked with a placeholder, never invented. A script checks the draft's numbers, placeholders and citation keys, and what a revision changed.

It serves empirical, quantitative papers in IMRaD form: biomedical and life science, quantitative social science, computer science, engineering. For theory, humanities, law and qualitative work only the planning applies (steps 1 to 3: materials, claims and evidence, gaps). Say so to the user and do not apply the outline, the writing order or the section rules to such a paper.

It does not search the literature, verify references, review statistics, make figures, apply venue templates, build LaTeX or DOCX, write cover letters, or promise anything about AI-detection tools. Step 10 names the skills that do the first four. A language-only polish of a finished text, or a translation, goes to `researchzy-polish` or `researchzy-translate` (plugin `researchzy-language`, when installed).

The bundled script needs Python 3.10 or newer and nothing else. Resolve `SKILL_DIR` to the directory containing this `SKILL.md`. No account is needed; steps 2 and 7 say what the Researchzy tools add when they are connected.

## Three uses

| Use | The user wants | Do | Deliver |
|---|---|---|---|
| Plan | an outline, or to know whether the work is ready to write up | steps 1–4 | contribution, claim ledger, gap report, outline |
| Draft | a manuscript or a section | steps 1–8, reusing what is already in `writing/` | the checked draft and its open gaps |
| Revise | existing text improved | step 9; step 8 as well for a whole manuscript | the revised text and the list of edits that could change meaning |

A small job (one paragraph, an abstract for a finished paper) does not need the whole workflow: take the claims that text makes and their evidence from the author's files, write, and run the check on the result.

## Inputs

- **Results**: analysis output, tables, figures, logs, a protocol or preregistration.
- **Existing text**: a draft, a thesis chapter, a report, slides.
- **Bibliography**: the author's `.bib`, and cited papers the author has as files.
- **Venue**: the target journal or conference and its author instructions (word limits, required sections, abstract form, reporting guideline), as a file, a link or pasted text.

Ask once before starting, and only for what is missing: where the results are, the venue's instructions (or "no venue yet"), and for a revision the level of edit. Never state a venue's limit or format from memory: they change.

## Workflow

Everything goes in `writing/`. Read [Planning](references/planning.md) before steps 1 to 4.

1. **Inventory.** List in `writing/claims.md` what the author has: each results file, table, figure, draft and `.bib`, with what it contains. Note what a paper of this design needs and is absent (for example a sample-flow count, the analysis software, an ethics statement).

2. **Contribution and claim ledger.** Write the contribution in one sentence: what was studied, in what, by which design, the main result with its number, and its limit. Then list every claim the paper will make, one row each, in `writing/claims.md`: the claim, its evidence, the grade of that evidence and what the evidence cannot support.

   | Grade | The evidence is | A sentence may say |
   |---|---|---|
   | `own-result` | a number, table or figure in the author's files, with its location | the result, with that number |
   | `full-text` | a cited paper read in full in this session, with page or section | what the paper did and found |
   | `abstract` | a cited paper of which only the abstract was read | what the abstract reports, nothing about methods or limits |
   | `metadata` | a title, authors and year: a `.bib` entry or a search hit | that these authors studied this topic, and no finding |
   | `none` | your recollection | nothing: use a placeholder |

   With the Researchzy tools connected (plugin `researchzy`, needs an account), grade a paper by what the tools returned in this session: a `search_papers` or `list_library_papers` hit is `metadata`, an abstract from `get_paper` is `abstract`, a full text obtained with `get_pdf_download` and read is `full-text`. Without them, grade by the files the author supplied.

3. **Gap report.** In `writing/gaps.md`, list what the paper needs and the author does not have. Each gap becomes one placeholder in the draft, in exactly these forms:

   - `[Evidence needed: …]` a result, number or analysis that is not in the materials
   - `[Citation needed: …]` a statement that needs a source that is not in the `.bib`
   - `[Author input needed: …]` a fact only the author knows (ethics approval, funding, a choice between two values)

   After the colon, say what would fill it. Show the contribution, the ledger and the gaps to the user. For a plan, continue to step 4 and stop there. For a draft, do not wait for an answer: go on, and put each placeholder where its gap is.

4. **Outline.** In `writing/outline.md`, write each paragraph as its topic sentence, followed by its evidence slots (ledger rows, tables, figures) and its words. Set the word budget per section from the venue's limits as the author gave them; without limits, ask for a total or leave the budget open. Name the reporting guideline for the study design from [Reporting guidelines](references/reporting-guidelines.md) and get its current checklist as that file says.

5. **Draft, evidence first.** Read [Sections](references/sections.md). Write in this order: tables and figure list, Methods, Results, Discussion, Introduction, then abstract and title. Write to `writing/manuscript.md` with Pandoc citations (`[@key]`), or into the author's LaTeX files when they ask for that; copy each of their files to `writing/before/` before changing it.

6. **Keep the section rules while writing.** One job per paragraph. A strong or causal verb only with the design feature that licenses it, named in the text. Each limitation with the direction of its bias. Every pre-specified result reported, favourable or not. A sentence with no ledger row gets a placeholder or is not written.

7. **Citations.** Cite only keys in the author's `.bib` or records the Researchzy tools returned in this session, at the grade from step 2. For a record that is not in the `.bib`, add an entry to `writing/new-references.bib` from the returned fields only; do not complete a field from memory and do not edit the author's `.bib` unless asked. To fill a `[Citation needed: …]`, hand off to `researchzy` or `researchzy-literature-review` (step 10). Connecting Researchzy is what lets a missing citation be found and read in the session; without it the placeholder stays and goes to the author in `gaps.md`.

8. **Check.**

   ```sh
   python3 "$SKILL_DIR/scripts/manuscript_check.py" check writing/manuscript.md --bib refs.bib \
     --budget "Abstract=250,Introduction=600,Total=3500" --out writing
   python3 "$SKILL_DIR/scripts/manuscript_check.py" check main.tex sections/*.tex --bib refs.bib --final --out writing
   ```

   It reads `.md`, `.tex`, `.txt` and `.docx` (several files are one manuscript) and writes `writing/manuscript-check.md` and `.json`. Give the budget the author's limits; `Total` is the main text without abstract, tables and references. Repeat `--bib` for `writing/new-references.bib` when it exists. Run without `--final` while drafting and with `--final` before calling a manuscript finished: it then exits 1 on any error.

   | In the report | Do |
   |---|---|
   | error: a percentage disagrees with its n/N | Look up the right value in the author's results. If they do not settle it, write `[Author input needed: …]`; never choose one. |
   | error: a cited key is not in the `.bib` | Use the right key, or replace the citation with `[Citation needed: …]`. Never write the entry from memory. |
   | error: a section is over its budget | Cut text, not results. |
   | error with `--final`: a placeholder | Fill it from the author, or remove or narrow the sentence that needed it. Otherwise deliver the text as a draft with its gaps, not as final. |
   | warning | Look at each one: a number in the abstract that is not in the text, one quantity with two values, a term written two ways, an abbreviation without definition, mixed spelling, an uncited `.bib` entry. Fix it or note why it stays. |
   | not checked | The check did not run (no `--bib`, no `--budget`, no Abstract heading). Supply what it needs, or tell the user it was not checked. |

9. **Revise.** Read [Revising](references/revising.md). Agree the level of edit (default: light). Write the revision to a new file, or copy the author's file to `writing/before/` first when they want it edited in place. Then compare:

   ```sh
   python3 "$SKILL_DIR/scripts/manuscript_check.py" diff writing/before/paper.md paper.md --strict --out writing
   ```

   `writing/revision-check.md` lists numbers that changed, disappeared or appeared, citations dropped, added or moved to another sentence, hedges removed, intensifiers added, negations and directions that changed, and sentences it could not compare. With `--strict` it exits 1 when a number or citation changed. Undo every such change the author did not ask for, then give the user each remaining edit that could change meaning as a before and after pair. When the problem is the content and not the wording, say so and stop polishing.

10. **Hand off** (each when installed; if it is not, say that this part was not done):

    | Need | Skill | Plugin |
    |---|---|---|
    | Find or look up a paper for a citation | `researchzy` | `researchzy` |
    | Related work, the gap, a statement of novelty | `researchzy-literature-review` | `researchzy` |
    | References exist and support the sentences citing them | `researchzy-reference-check` | `researchzy-manuscript` |
    | Statistical reporting in Methods and Results | `researchzy-stats-review` | `researchzy-manuscript` |
    | Data and code availability statements | `researchzy-data-availability` | `researchzy-manuscript` |
    | Figures | `researchzy-figures` | `researchzy-manuscript` |
    | A critical read of the finished draft before submission | `researchzy-paper-review` | `researchzy-manuscript` |
    | Replies to reviewers | `researchzy-rebuttal` | `researchzy-manuscript` |

## Outputs

In `writing/`: `claims.md` (inventory, contribution, claim ledger), `gaps.md`, `outline.md`, `manuscript.md` (or the author's LaTeX files, with the originals in `before/`), `new-references.bib` when records were added, `manuscript-check.md` and `.json`, `revision-check.md` and `.json`.

## Rules

- Numbers, sample sizes, effects, dates and methods come from the author's files or from tool results in this session. Never from memory, and never a plausible value: write `[Evidence needed: …]`.
- Do not compute new results and do not change a number to make the text consistent. Report the disagreement and ask which value is right.
- Never remove an unfavourable or null result that the materials contain, blur it into vague wording, or report it only in a supplement.
- Wording follows the evidence grade. A paper known only by metadata supports "these authors studied this" and nothing else.
- "First", "no study has" and "little is known" are claims about the literature: make them only with a logged search from `researchzy-literature-review`, otherwise use `[Citation needed: …]`.
- Do not overwrite or delete the author's files. Write new files, or copy to `writing/before/` first.
- There is no score. The script's errors and exit code decide what it can check; "not checked" is never "passed"; the rest is these rules.
- The list of machine-sounding patterns in the revising reference is for a report only. Make no claim about how any AI detector will read the text.

## Related files

| File | Open when |
|---|---|
| [references/planning.md](references/planning.md) | Before steps 1 to 4: ledger format, evidence grades, gap report, outline and budget |
| [references/sections.md](references/sections.md) | Before drafting or restructuring any section |
| [references/revising.md](references/revising.md) | Before any revision, and when reading `revision-check.md` |
| [references/reporting-guidelines.md](references/reporting-guidelines.md) | Step 4, to name the guideline for the study design |
| `scripts/manuscript_check.py` | Steps 8 and 9; `--help` on either command lists its options |
