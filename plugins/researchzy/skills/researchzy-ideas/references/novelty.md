# Novelty check

The check cannot prove that an idea is new. It can show that a defined set of searches, run on a given day against the idea as it is now worded, found no work that already covers it, and it can name the works that come closest. Every statement about novelty is therefore tied to the log.

## Before searching

Take two or three concept groups from the card: the unknown, the mechanism, and the population or setting. For each, list the words a paper might use. `search_papers` matches words as written in titles and abstracts: it does not treat singular and plural, British and American spelling, or an abbreviation and its expansion as the same, so write the variants as separate queries. Use two to five distinctive keywords, with phrases in double quotes. There is no author search; to find a known paper, search its title.

## Searches by intent

| Intent | The question it asks | Build the query from | Passes |
|---|---|---|---|
| `duplicate` | Has this question been asked, with this kind of evidence? | Unknown + setting + outcome | Recent and canonical, at least two phrasings |
| `mechanism` | Has this mechanism been proposed or tested, for this outcome or a nearby one? | Mechanism + outcome | Canonical, then recent |
| `adjacent` | Is this known under another name, in a neighbouring field or population? | The other field's words for the unknown; another `fieldOfStudy` | Relevance |
| `skeptic` | Is there evidence against the premise: null results, failed replications, critiques? | Topic words + `replication`, `null`, `"no effect"`, `critique`, `limitations` | Relevance |
| `citation` | Who cites the closest works? | Not available: the index has no cited-by search | The ledger records this for every idea |

The two passes:

- **Recent:** `sort: year`, or `yearFrom` three years back with the default sort. This is where concurrent work shows.
- **Canonical:** `sort: citationCount`, with quoted phrases only, because a sorted search ranks a loosely matched set. This is where the established answer shows.

Run all four available intents when the idea is to be recommended. The ledger's minimum for `differentiated` is completed searches of two intents, one of them `duplicate`. With many candidates, run `duplicate` for all of them first and the other intents only for those still standing. Titles taken from the reference list of the decisive paper may be looked up one by one; log each under the intent it serves. That recovers earlier work, not later work.

## Logging

Log each search when it is run, with the `total` the tool reported:

```sh
python3 "$SKILL_DIR/scripts/idea_ledger.py" search i1 --intent duplicate \
  --query '"interleaved practice" calculus "method selection"' --total 37 --sort year --filter yearFrom=2023
python3 "$SKILL_DIR/scripts/idea_ledger.py" search i1 --intent skeptic \
  --query 'interleaving "no effect"' --failed "RATE_LIMITED: try again later"
```

- A search that returned nothing is `--total 0`. A search the tool did not answer is `--failed`, with its `code` and `userMessage`; it counts toward no intent. Run it again later.
- A search of the user's library (`--tool list_library_papers`) shows whether they already hold the closest work. It does not count toward an intent, because the library is not the index.
- A small `total` is not a sign of novelty. It is as often a vocabulary miss: try the variants before reading a low count as absence.
- A `total` in the thousands that drifts off topic says the query is loose. Tighten it; do not page through.

## The closest works

From everything the searches returned, choose the three to five works that a reviewer would hold against the idea: the same unknown, the same mechanism for the same outcome, or the same data and design. Not the most cited and not the newest. When fewer than three come close, record those and say so; do not pad the table.

Save them as returned by the tool, and add the comparison:

```json
[{"corpusId": 123456, "title": "…", "authors": ["…"], "authorCount": 3, "year": 2021, "venue": "…",
  "doi": "…", "readerUrl": "…",
  "what_it_solved": "…", "overlap": "…", "difference": "…", "why_it_matters": "…",
  "read": "abstract", "decisive": true}]
```

```sh
python3 "$SKILL_DIR/scripts/idea_ledger.py" closest i1 closest.json
```

| Field | Write |
|---|---|
| `what_it_solved` | What the work established, as far as it was read |
| `overlap` | What it shares with the idea: question, mechanism, data, design |
| `difference` | What the idea would add that this work does not contain |
| `why_it_matters` | What that difference changes in what can be concluded. "It has not been done" is not an answer |
| `read` | `metadata`, `abstract` or `full_text` |
| `decisive` | `true` on one work only: the decisive one, described below |

How far a work was read limits what may be written about it:

| `read` | May state |
|---|---|
| `metadata` | Nothing about its method or result. Get the abstract (`get_paper`, or `search_papers` with `detail: full`) before comparing |
| `abstract` | What the abstract reports, marked as such |
| `full_text` | Method, data and results, with the page or section |

Running `closest` again with the same `corpusId` updates the record, so `read` can be raised after reading.

**The decisive work** is the one with the largest overlap: if its difference turned out to be nothing, the idea would be a repeat. Mark it `"decisive": true` and read it in full before any recommendation; the ledger does not accept another work read in full in its place. Get the PDF with `get_pdf_download` and its `corpusId`; when Researchzy holds no PDF, use `researchzy-download` (plugin `researchzy-reading`, when installed) or ask the user for the file. Hand the reading to `researchzy-deep-read` (plugin `researchzy-reading`, when installed), or read it yourself. Record `full_text` only when the methods and the results were read. When no full text can be had, the idea stays open: tell the user which paper to supply.

## Status

| Status | Set it when | Tell the user |
|---|---|---|
| `unsearched` | No index search has completed for this version: a new idea, a revised wording, every search failed, or the tools are not connected | Novelty was not checked |
| `inconclusive` | Searches ran and do not settle it: one intent only, an intent whose searches failed, too many results to look through, or the difference hangs on a paper read only in the abstract. The ledger sets this at the first completed search | What was searched, and what would settle it |
| `overlap_found` | A named closest work covers the question with the same mechanism and comparable evidence | The paper, what little remains, and the choices: change the idea, repeat the work on purpose, or reject |
| `differentiated` | Completed searches of at least two intents including `duplicate`; every closest work has a remaining difference; the difference changes what can be concluded | "Within the searches logged, no work was found that …; the closest is …, which differs in …" |

```sh
python3 "$SKILL_DIR/scripts/idea_ledger.py" novelty i1 --status differentiated --note "…"
```

`differentiated` means only "within the searches logged". The ledger refuses it without the searches, without a closest work, or while a closest work has no stated difference. It refuses `overlap_found` without a closest work that has a stated overlap.

## Rules

- **"Already done" needs a named paper.** Without a work in the table whose overlap covers the idea, the status is not `overlap_found`, and "this has surely been done" is not a reason to reject.
- **Neighbours are information, not a veto.** A field with close work is a field where the question matters. Reject for overlap only when the remaining difference changes nothing.
- **Concurrent work is a race, not a veto.** A recent preprint on the same question goes in the table with its date. Tell the user; the decision to race, to differentiate or to stop is theirs.
- **A changed idea needs a new search.** After any `revise` of the question or hypothesis, the earlier searches and closest works no longer count.
- **A failed search is not zero results**, and zero results from one phrasing are not absence.
- **Never state from memory** that a paper exists, what it found, or that nothing exists.

## When it stays inconclusive

After a second round of queries with the status still `inconclusive`, or when every phrasing returns thousands of results, the question needs a review, not more spot checks. Hand over to `researchzy-literature-review` with the question, the queries already run (`ideas/novelty-log.md`) and the closest works. When it has finished, log the searches that bear on the idea and set the status.

To re-check an idea later, run its logged queries again with `yearFrom` set to the year of the last check, and log them as new searches.
