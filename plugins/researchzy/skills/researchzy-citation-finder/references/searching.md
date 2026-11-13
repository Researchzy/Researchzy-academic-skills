# From a sentence to searches

A sentence is a poor query. The index matches words, not meaning, so a sentence has to be taken apart and rebuilt as a few short keyword sets before anything is searched.

## What `search_papers` can and cannot do

- A `query` is matched against titles and abstracts only, and a paper must contain most of the query's words. Short queries of distinctive words work; long ones return nothing or noise.
- Words are matched as written. There is no stemming and no synonym list: `nap` and `naps`, `tumour` and `tumor`, `PSQI` and `Pittsburgh Sleep Quality Index` are different queries.
- There is no author search ("Okoro et al. showed" cannot be searched by name: search the title, or the finding's words), no cited-by list, and no retraction data.
- Keyword searches take `sort` (`relevance`, `citationCount`, `year`, `influency`), `yearFrom`, `yearTo`, `fieldOfStudy`, `venue` and `hasPdfInS3`, up to 50 results a page. The `total` it reports is approximate.
- A `doi` or `arxiv` search looks one paper up and takes no filters. Pass exactly one of `query`, `doi`, `arxiv`.
- Queries in languages other than English find little.

## 1. Take the claim apart

Write down four parts of the sentence before the first query. The example sentence is invented: "Rotating night shifts reduce recall accuracy in hospital nurses."

| Part | Question | Example |
|---|---|---|
| Entity | What is measured or acted on? | recall accuracy |
| Relation | What does the sentence say happens, and in which direction? | reduce: goes down |
| Condition | Population, setting, exposure, dose, time | rotating night shifts; hospital nurses |
| Boundary | What does the sentence not claim? | not all shift workers; not lasting harm |

A sentence that makes two claims (two verbs with their own objects, often joined by "and" or "while") needs a source for each. The ledger holds one paper per target: search for both, give the verdict for the part the placeholder's note names, and when the other part is unsupported use `partial` with a wording that drops it. Suggest that the user split the sentence; after the split, `targets` gives each half its own id.

## 2. What each need looks for

| Need | The source to find | Not good enough | Search with |
|---|---|---|---|
| `finding` | The primary study that reports the result, with matching population, design and direction | A review that mentions it; a later paper that repeats it | Entity + condition words; add design words (`trial`, `cohort`, `randomized`) when the sentence implies one |
| `method` | The paper that introduced or validated the method, instrument, scale, dataset or software the sentence names | A paper that merely used it | The quoted name, and the abbreviation as a second query; `sort: citationCount`; `yearTo` near the method's origin when known from the manuscript |
| `number` | The source that measured that figure for that population and period: a primary study, a registry or survey report | A paper quoting the figure from elsewhere: follow its reference list to the origin | The quantity, the population and the place; `sort: year` when the sentence is about the present |
| `background` | A review or a widely cited primary paper that states the general point | A paper on a neighbouring topic that touches it in passing | The topic words plus `review` or `overview`; `sort: citationCount` |

`not_needed` is for the author's own result, a definition the manuscript gives, and knowledge that a reader of the venue would not expect to see cited. Give the reason in a few words ("our Table 2", "definition in Methods").

## 3. Look at what the author already has

- `targets --bib refs.bib` lists, under `in_bib`, entries whose titles share words with the target. An entry in the `.bib` is a lead, not support: look it up (`search --doi`, or its title as a query), save the result and read it like any other candidate.
- Search the user's library with `list_library_papers` (`query`, scope `personal`, then `shared`). Log it with `--tool list_library_papers`; it does not count toward `not_found`, because the library is not the index.

## 4. Write the queries

- Two to five words per query, with phrases in double quotes: `"night shift" recall nurses`.
- Two to four queries per target. Vary one thing at a time: a synonym (`memory` for `recall`), singular and plural, British and American spelling, the abbreviation and its expansion, a broader term (`shift work`), a narrower one (`"three consecutive night shifts"`).
- One query in the opposite direction: the entity with words for the other result (`"no effect"`, `"no association"`, `increased`, `improved`). A paper that contradicts the sentence is a result to report, not a reason to stop.
- `fieldOfStudy` removes homonyms (a `model` in biology and in computer science). Year filters only when the sentence is about a period.
- Never paste the sentence or the placeholder's note as the query.

Queries for the example, in the order to run them:

```
"night shift" recall nurses
"shift work" "episodic memory"
"night shifts" memory nurses
"night shift" recall "no effect"
```

## 5. Read the counts

| What you see | Do |
|---|---|
| `total` 0, or a handful of off-topic hits | Drop a word, unquote a phrase, try the variants |
| `total` in the thousands, hits drift off topic after the first few | Add a condition word or quote the central phrase; do not page through |
| The same papers in every query | The vocabulary is covered; stop varying |
| A sorted search returns famous papers on something else | Sorting ranks a loose set: quote the phrases and add a field filter |

Read the titles and abstracts of the first page (20 to 50 results). Record how many you looked at with `--looked-at`; without it the ledger counts the records in the saved file.

## 6. Save and log

Save each tool result as returned, unedited, as `citations/results/<target>-<n>.json`, then log it:

```sh
python3 "$SKILL_DIR/scripts/citation_ledger.py" search t1 --query '"night shift" recall nurses' \
  --total 57 --looked-at 20 --saved citations/results/t1-1.json
python3 "$SKILL_DIR/scripts/citation_ledger.py" search t1 --query '"shift work" memory' --failed "RATE_LIMITED: try again later"
```

A search the tool did not answer is logged with `--failed` and its `code` and `userMessage`. It is not an empty result and does not count toward `not_found`; run it again later. The same query with the same sort and filters counts once.

## 7. When to stop

Stop searching a target when a candidate has passed the reading step, or after three to four distinct keyword searches have found nothing that holds. Do not keep adding queries to reach a result: `not_found` with its queries listed is an honest outcome, and the map shows the reader what was tried.
