---
name: researchzy-literature-review
description: "Write a literature review from real papers: scope the questions, search Researchzy's index with a logged strategy, screen, read the core papers in full, and synthesize by theme with a comparison table, gaps and BibTeX. Use for related work, a survey of a field, or what is known about a topic."
---

# Researchzy Literature Review

This skill turns a topic into a review that a reader can check: every cited paper is a record Researchzy's index returned, every search is logged with its counts, and every statement about a paper's methods or results comes from text that was actually read.

It needs the Researchzy tools (`search_papers`, `get_paper`, `list_library_papers`, `get_pdf_download`). If they are not connected, say so and stop: do not write a review from memory or from web snippets. The bundled ledger script needs Python 3.10 or newer. Resolve `SKILL_DIR` to the directory containing this `SKILL.md`.

It writes a narrative or scoping review with a transparent search. It is not a PRISMA systematic review with dual screening and risk-of-bias assessment; say so if the user asks for one and hand it to `researchzy-systematic-review` (plugin `researchzy-evidence`, when installed), or offer this as the first pass.

## Two sizes

| | Quick map | Full review |
|---|---|---|
| Papers included | 10–15 | 30–50 |
| Read in full | 3–5 core papers | 8–12 core papers |
| Output | One page of findings and a comparison table | Themed synthesis, comparison table, gaps, limitations |

Choose from the request ("related work for my paper" is usually a quick map; "survey the field" a full review), or ask.

## Workflow

Everything goes in `literature-review/`. The ledger keeps the books:

```sh
python3 "$SKILL_DIR/scripts/review_ledger.py" <command> …
```

1. **Brief.** Restate the topic as two or three questions a paper could answer, with the scope (period, fields, what is out), the inclusion criteria, the size, and any papers the user already knows (seeds). Show it to the user and wait for a yes or corrections; skip the wait only if the user already gave all of it. Record it with `brief`.

2. **Library first.** Search the user's library with `list_library_papers` (`query`, scope `personal`, then `shared`). Log it (`search --tool list_library_papers --pass library`) and add the relevant papers with `add --library`. Look each seed up by DOI, arXiv number or title and add it with `add --seed`.

3. **Search.** Read [Search tactics](references/search-tactics.md). For each question run the passes below, a few queries each, and log every query with the `total` the tool reported. A quick map may leave out `foundational` and `recent` when the question does not need them; `relevance`, `reviews` and `contrary` are always run:

   | Pass | What it finds | How |
   |---|---|---|
   | `relevance` | The core of the topic | 2–5 distinctive keywords, phrases in quotes, default sort |
   | `foundational` | The works everyone builds on | `sort: citationCount` or `influency`, quoted phrases only |
   | `recent` | The current frontier | `sort: year`, or `yearFrom` the last three years |
   | `reviews` | Earlier surveys | the topic words plus `review`, `survey`, `meta-analysis` |
   | `contrary` | Null results, failed replications, critiques | the topic words plus `replication`, `null`, `no effect`, `limitations`, `critique` |

   Save every paper whose title or abstract touches the question as JSON, as returned (`corpusId`, `title`, `authors`, `authorCount`, `year`, `venue`, `doi`, `arxiv`, `citationCount`, `hasReadablePdf`, `readerUrl`, and the abstract when there is one), and add them with `add results.json --search s3`. The ledger removes duplicates. Add generously and decide in the next step: a ledger that holds only the papers you meant to include has no record of what was screened out.

4. **Screen.** Judge every candidate against the criteria from its title and abstract: `decide <id> --include` or `--exclude --reason "…"`. Use a small fixed set of reasons so the counts mean something (off topic, wrong population, wrong study type, outside the period, not a research paper). When a record has no abstract, call `get_paper`; if there is still none, decide on the title and say so in the reason. Citation counts never decide inclusion.

5. **Seed check.** Run `status`. A seed listed under `seeds_not_found_by_any_search` means the queries miss part of the topic: add the vocabulary that paper uses and search again.

6. **Choose the core and read it.** Mark the papers the review rests on with `decide <id> --include --core`; the seeds usually belong here. Get their full text: `get_pdf_download` with the `corpusId`, then `researchzy-download` (plugin `researchzy-reading`, when installed), then the abstract. Record how far each included paper was read with `read <id> --depth full_text|abstract|metadata`. A core paper whose full text cannot be had stays core, and the review's limitations name it.

7. **Follow the references.** From the reference lists of three to five core papers, pick the works that several of them cite or that the text leans on, look each up with `search_papers`, and add what the index has (`--pass chain`). The index has no "cited by" search, so later papers come only from the `recent` pass.

8. **Extract.** For every included paper record one row with `extract`: `theme`, `question`, `method`, `data`, `result` (with its number), `limits`, `relation` (to other included papers) and `locator` (page or section). Write method and result only from what was read; leave a field empty rather than infer it from the title.

9. **Write.** Read [Synthesis](references/synthesis.md) and start from the [review template](references/review-template.md). Cite with the ledger's keys as `[@key]`. Run `export` for `papers.csv`, `references.bib` and `search-log.md`.

10. **Check, then deliver.** `check literature-review/review.md` must report `ok`: no citation outside the ledger, none of an excluded paper, none of a paper that was not read. Fix the review, not the ledger. Run `status` once more: every pass under `passes_not_run` and every paper under `core_not_read_in_full` is either dealt with or named in the review's limitations. Then give the user `review.md`, the comparison table, `references.bib` and the search log, with the `readerUrl` of the core papers. Offer to save the included papers to a collection; create or fill one only when the user says yes.

## Updating a review

When `literature-review/ledger.json` exists and the user asks to continue or update, do not start over. Run the logged queries again (for an update, with `yearFrom` set to the newest year already covered), add the results, and screen only the new candidates. Tell the user what is new since the last run before rewriting anything.

## Rules

- Cite only papers in the ledger with decision `included`. A paper the index does not have (a book, a report the user supplied) may be added by hand; the check lists it as not from the index, and the review must say so.
- Never state a method, sample size, number or conclusion of a paper you have only metadata for. From an abstract, say what the abstract reports and no more.
- "No study has…" and "little is known about…" are claims. Make them only with the searches that support them, and say which.
- Do not invent or complete bibliographic fields. Use what the tools returned.
- Do not save papers to the user's library, or create collections, unless asked.
- Report failures of the tools with their `code` and `userMessage`; an error is not an empty result.

## Related files

| File | Open when |
|---|---|
| [references/search-tactics.md](references/search-tactics.md) | Before step 3, and whenever a search returns too much, too little or the wrong thing |
| [references/synthesis.md](references/synthesis.md) | Before writing |
| [references/review-template.md](references/review-template.md) | The structure of `review.md` |
| `scripts/review_ledger.py` | Every step; `--help` on any command lists its options |
