# Search tactics

## How `search_papers` matches

- A `query` is matched against titles and abstracts and needs most of its words. Papers whose title contains the whole query rank first.
- Prefer two to five distinctive keywords to a sentence. Put a phrase in double quotes to keep its words together: `"sleep deprivation" hippocampus`.
- The index matches words as written. It does not know that `tumour` and `tumor`, `model` and `models`, or `LLM` and `large language model` are the same thing. Write the variants as separate queries.
- There is no author search. To find a known author's paper, search its title.
- Queries in languages other than English find little.
- Keyword searches take `sort` (`relevance`, `citationCount`, `year`, `influency`), `yearFrom`, `yearTo`, `fieldOfStudy` (the index's own field names, such as `Computer Science` or `Medicine`), `venue` and `hasPdfInS3`. Up to 50 results a page (`pageSize`), brief by default; `detail: full` returns whole abstracts and every author.
- The result reports `total`, `totalPages` and `hasMore`. Log `total` for every query: it is what tells a reader how much of the hits you looked at.
- The index may lag the last few months. Note the newest publication date you see, and state it under the review's limitations.

## Building the queries

For each question of the brief:

1. Split it into two or three concepts (a population or system, an intervention or method, an outcome).
2. For each concept list the terms a paper might use: synonyms, the abbreviation and its expansion, singular and plural, British and American spelling, the older name of the same thing.
3. Combine one term per concept into a query. Run the handful of combinations that matter, not every one.

Example, for "does sleep loss impair memory encoding":

```
"sleep deprivation" memory encoding
"sleep loss" hippocampus encoding
"sleep restriction" learning
"total sleep deprivation" "episodic memory"
```

## Reading the counts

| What you see | What to do |
|---|---|
| `total` in the thousands, results drift off topic after the first page | Add a concept or quote the central phrase. Do not page through thousands. |
| `total` under ten | Drop a concept, unquote a phrase, or try the variant spellings. |
| The same papers in every query | The vocabulary is covered. Stop adding variants; move to the next pass. |
| A seed paper never appears | Read its title and abstract for the words it uses, and search with those. |
| A sorted search returns well-cited papers on something else | Sorting ranks a loosely matched set. Quote the phrases and add a field or year filter, and screen every result. |

Look at the first one or two pages of a relevance search (40–100 results) unless the hits are still on topic. Record how many you looked at with `--fetched`; the ledger counts the rest as not looked at, and the review says so.

## The passes

- **relevance.** The default sort with tight queries. Most included papers come from here.
- **foundational.** `sort: citationCount` or `sort: influency`. Use quoted phrases only, because sorting by citations brings highly cited papers that merely mention a word. Expect to exclude most of what comes back.
- **recent.** `sort: year`, or `yearFrom` three years back with the default sort. Recent papers have few citations; do not hold that against them.
- **reviews.** Add `review`, `survey`, `systematic review` or `meta-analysis` to the topic words. An earlier review tells you the field's own map and vocabulary. Check whether the user's question is already answered by one.
- **contrary.** Add `replication`, `failed to replicate`, `null`, `no effect`, `negative result`, `limitations`, `critique`, `bias` or `reanalysis`. A review that reports only confirmations misstates the field. If this pass finds nothing, say that it was run and found nothing.
- **chain.** Titles taken from the reference lists of core papers, searched one by one.
- **library.** `list_library_papers` with `query`: what the user already holds on the topic.

## Logging

One `search` entry per query, at the time it is run:

```sh
python3 "$SKILL_DIR/scripts/review_ledger.py" search --query '"sleep deprivation" memory encoding' \
  --pass relevance --question 1 --total 412 --fetched 50 --filter yearFrom=2005
```

Then add the papers worth screening with `add <file> --search <id>`. Papers you dismissed on the title alone need no entry; the difference between "looked at" and "new papers" in the log accounts for them.

## When to stop

Stop searching when a new query brings almost only papers already in the ledger, every seed has been found by a search, and each question of the brief has papers for it, or a logged, empty-handed search that shows it has none.
