---
name: researchzy-ideas
description: "Develop research ideas: generate them from a topic, an observation or a review's gaps, sharpen one hypothesis, or evaluate an idea you already have. Checks novelty against real papers with logged searches and recommends only ideas that passed the checks. Use when choosing a research question."
---

# Researchzy Ideas

This skill develops research ideas that can be checked before a researcher commits months to one. Every idea becomes a card that names the result that would refute it. Its novelty is judged only from logged searches of Researchzy's index, bound to the idea's current wording. An idea is marked recommended only when the bundled ledger finds the checks in the record. "No candidate qualifies" is an allowed result.

It does not run pilot experiments, judge fit to a venue or journal, or ask a second model to score ideas. It does not write a literature review: for a map of a field's gaps, hand over to `researchzy-literature-review`, which comes with this plugin.

## Requirements

- The Researchzy tools (`search_papers`, `get_paper`, `list_library_papers`, `get_pdf_download`), for the evidence base and the novelty check. **If they are not connected**, say so once and work without them: skip the library look, the search in step 2 and step 5; generate or sharpen the ideas; leave every idea's novelty `unsearched` and `difference` unrated; and tell the user that nothing can be recommended until the index has been searched. Do not judge novelty from memory or from web snippets.
- Python 3.10 or newer for the ledger. Resolve `SKILL_DIR` to the directory containing this `SKILL.md`.

## Inputs

| Entry | The user brings | Do |
|---|---|---|
| Generate | A topic, an observation, or the gaps of a literature review | Every step: six to ten candidates, then a card for each one left after merging |
| Sharpen | One hypothesis that is still vague | Steps 1 and 2, then step 4 onward for one card |
| Evaluate | An idea they already have | Steps 1 and 2, then step 4 onward. Card the idea first as the user stated it; every later improvement is a `revise`, so the record shows what you changed |

Before starting, ask once, in one message, for whatever the user has not said: the field; the kind of question (descriptive, associational, predictive, causal or mechanistic; theory; qualitative); the data they hold or can get; equipment and compute; the months available; their skills. If they do not answer, go on and mark the gates `unknown`.

## Workflow

Everything goes in `ideas/`. The ledger keeps the record:

```sh
python3 "$SKILL_DIR/scripts/idea_ledger.py" <command> …
```

1. **Brief.** Record the answers: `brief --field "…" --question-type causal --data "…" --equipment "…" --months 18 --skills "…"`. Then see what the user already holds: `list_library_papers` with `query` (scope `personal`, then `shared`), two or three queries, each logged with `search base --tool list_library_papers --query "…" --total N`. A candidate that restates a paper in the library is not an idea.

2. **Evidence base.** Use the first of these that exists, and write on each card (`origin`) what the idea came from:

   | Exists | Take from it |
   |---|---|
   | `literature-review/review.md` | The rows of its Gaps table, with their search ids and how sure the review was; the papers in `papers.csv` |
   | A Paper Card (`paper-card.md`) | The ideas of its section 16, as seeds. They are hypotheses, not novelty claims, and pass every step below |
   | Neither | A short search: four to six queries (two by relevance, one `sort: year`, one `sort: citationCount`, one with `review` or `survey`), each logged with `search base --query "…" --total N --sort year`. Read the abstracts of the 10–15 most relevant results (`detail: full`). This is a look around, not a review: state no gap from it |

   If the user wants the gaps of a field mapped first, hand over to `researchzy-literature-review` and come back with its `review.md`.

3. **Generate** (Generate entry only). Read [Generating](references/generating.md). Choose three or four operators from its situation table and run each to its required output. Write every candidate as one sentence that names the unknown, the mechanism and the evidence that would tell. Merge the candidates that share all three.

4. **Card.** Read [Idea card](references/idea-card.md). Write one card per candidate as JSON; `add card.json` prints the ids (`i1`, `i2`, …). Fill what is still empty with `revise i1 --refuted-by "…"`.

5. **Novelty check.** Read [Novelty](references/novelty.md). For each idea, search by intent (`duplicate`, `mechanism`, `adjacent`, `skeptic`), with a recent pass sorted by year and a canonical pass sorted by citations. Log every search when it is run, with the `total` the tool reported:

   ```sh
   python3 "$SKILL_DIR/scripts/idea_ledger.py" search i1 --intent duplicate \
     --query '"interleaved practice" calculus' --total 37 --sort year --filter yearFrom=2023
   python3 "$SKILL_DIR/scripts/idea_ledger.py" search i1 --intent skeptic --query '…' --failed "CODE: userMessage"
   ```

   Save the three to five closest works as the tool returned them, add `what_it_solved`, `overlap`, `difference`, `why_it_matters` and `read`, mark the one with the largest overlap `"decisive": true`, and record them with `closest i1 closest.json`. Read the decisive work in full: `get_pdf_download` with its `corpusId`, then `researchzy-deep-read` (plugin `researchzy-reading`, when installed) or your own reading of the PDF; record it again with `"read": "full_text"`. Then `novelty i1 --status differentiated`, `overlap_found` or `inconclusive`. The ledger refuses `differentiated` without completed searches of two intents, one of them `duplicate`, and a closest work.

6. **Gates and assumptions.** Read [Selection](references/selection.md). Gates first: `gate i1 data=confirmed ethics=plausible equipment=confirmed skills=plausible time=unknown`; a blocked gate carries its reason, `data=blocked:"…"`. Then one `assume i1 --text "…" --risk 4 --months 2 --test "…"` for each assumption. A blocked gate ends the idea as it stands: `revise` it so the block no longer applies, or `reject` it.

7. **Rate.** `rate i1 value=2:"…" difference=2:"…" testability=3:"…" feasibility=2:"…" information_gain=1:"…"`, with the anchors in Selection. Each score is 0 to 3 and needs a reason that points to the record. Do not add, average or weight the scores.

8. **Attack.** State the strongest objections and record what became of each: `attack i1 --attack "…" --basis "…" --change "…" --residual "…"`. When the answer changes the question or the hypothesis, `revise i1 --hypothesis "…" --note "…"`. That is a new version: its novelty is `unsearched` again, and step 5 is repeated for the new wording.

9. **Minimum first study.** For each idea still standing: `study i1 decision="…" support="…" refute="…" undetermined="…" null_value="…" budget="…" first_action="…"`.

10. **Recommend or reject.** `recommend i1` succeeds only when novelty is `differentiated` for the current version, the decisive closest work was read in full text, no gate is `blocked`, all five dimensions are rated and the card has a refuting result. Otherwise it lists what is missing and exits 1: do that work, or leave the idea open. Recommend the strongest idea first; the export keeps that order. `reject i2 --reason "…" --restart-if "…"` keeps a rejected idea with the condition that would reopen it.

11. **Export and report.** `export` writes `ideas/ideas.md` and `ideas/novelty-log.md`. Tell the user, in this order: the recommended ideas, each with its open points and first action; the open ideas and what each lacks; the rejected ideas and their restart conditions. Give the `readerUrl` of the closest works. When nothing is recommended, say that no candidate qualifies and what would change that.

When `ideas/ideas.json` already exists, run `status` and continue from what is missing; do not start over.

## Outputs

| File | Holds |
|---|---|
| `ideas/ideas.json` | The ledger: brief, cards and their versions, searches, closest works, gates, assumptions, ratings, attacks, first studies |
| `ideas/ideas.md` | The idea cards: recommended, then open, then rejected with their restart conditions |
| `ideas/novelty-log.md` | Every search with its date, intent, idea version and count; the closest works; earlier wordings |

`export` rewrites the two Markdown files. Change the ledger, not the files.

## Rules

- Never call an idea novel, new or the first. Say "differentiated within the searches logged", and name the closest work and how it differs.
- "Already done" needs a named paper in the closest-work table. Neighbouring work is information and concurrent work is a race; neither rejects an idea by itself.
- A tool error is logged with `--failed`, with its `code` and `userMessage`. It is not zero results and counts toward no intent.
- Take papers, numbers and findings only from tool results or files in this session. Describe a closest work only as far as it was read.
- When the ledger refuses, do the missing work or report it. Do not set a status or a rating you cannot justify in order to pass.
- Ratings stay separate: no total, no rank by sum, no "8 out of 10".
- A gate is `confirmed` only on the user's word or a document. Do not confirm it for them.
- Do not save papers to the user's library or create collections unless asked.

## Related files

| File | Open when |
|---|---|
| [references/generating.md](references/generating.md) | Before step 3: the operators, and which to try in the researcher's situation |
| [references/idea-card.md](references/idea-card.md) | Before step 4, when sharpening a hypothesis, and before any `revise` |
| [references/novelty.md](references/novelty.md) | Before step 5, and whenever a novelty status is set or reported |
| [references/selection.md](references/selection.md) | Before steps 6 to 9: gates, assumption risk, rating anchors, attacks, first study, and what "test" means for theory and qualitative work |
| `scripts/idea_ledger.py` | Every step; `--help` on any command lists its options |
