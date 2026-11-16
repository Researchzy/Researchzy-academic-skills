# Searching

Search several sources, each with a query written for it, and log every search when it runs. The log is the methods section; nothing about a search is reported from memory.

## Build the strategy

1. Split the question into two or three concepts: population, intervention or exposure, and outcome or design. The comparator is rarely searched.
2. For each concept list its terms: synonyms, an abbreviation and its expansion, singular and plural, British and American spellings, older names. Show the lists to the user with the protocol.
3. Write one query per source from these lists, in that source's syntax. Add no date or language limit that the protocol does not state.

## Researchzy index (`search_papers`)

- Pass `query` (a tool call takes exactly one of `query`, `doi`, `arxiv`). Double quotes keep a phrase together. Filters: `yearFrom`, `yearTo`, `fieldOfStudy`, `venue`, `hasPdfInS3`. Keep the default relevance order. Up to 50 results a page: fetch pages until `hasMore` is false.
- The index matches the keywords against titles and abstracts and needs most of a query's words; there is no Boolean logic and no stemming. Run each variant as its own logged search, for example `"knee replacement" prehabilitation`, `"knee arthroplasty" prehabilitation`, `"knee replacement" "preoperative exercise"`.
- Save each page as the tool returned it under `systematic-review/raw/` (`s1-p1.json`, `s1-p2.json`), and log the reported `total`, the number of pages and `--last-page` when `hasMore` was false.

When the index was searched, these limits go into the methods and the limitations, in these words or close to them:

1. The Researchzy index matches keywords in titles and abstracts; it is not a Boolean search.
2. It does not reduce words to their stems, so singular and plural forms and synonyms were searched as separate logged queries.
3. The total it reports for a query is approximate.
4. It has no cited-by lists, so no forward citation searching was done.
5. It holds no retraction data, so whether an included study has been retracted was not checked.

## PubMed

Use a PubMed connector when the agent has one. Otherwise use the public E-utilities, with no API key and no email address:

```
https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&retmode=json&retmax=500&retstart=0&term=<query>
https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pubmed&retmode=xml&id=<PMID>,<PMID>,...
```

- Write the query with subject headings (`[mh]`) and title-abstract words (`[tiab]`), combined with AND and OR, URL-encoded.
- `esearch` returns the count, which is `--total`, and the PMIDs, page by page with `retstart`. Fetch the records with `efetch` in batches of up to 200 PMIDs and save each batch as XML. `--pages` is the number of batches; `--last-page` when every PMID was fetched.
- Send at most one request per second (this skill's rule).
- When a connector returns PMIDs but no records, fetch those PMIDs with `efetch`. When PubMed cannot be reached at all, log nothing for it and say in the report that it was not searched.

## ClinicalTrials.gov

For questions about trials, search the registry through its public API, version 2; never read its web pages:

```
https://clinicaltrials.gov/api/v2/studies?format=json&countTotal=true&pageSize=100&query.term=<expression>
```

Add `&pageToken=<nextPageToken>` for each further page and save every page. `totalCount` on the first page is `--total`; the last page has no `nextPageToken`. Log it with `--kind register`. If a request is refused, read the API documentation on the registry's site instead of guessing parameters.

## The user's exports

Subscription databases (Embase, Scopus, Web of Science, CINAHL and others) are searched by the user through their institution. Ask for a RIS export of all results, the query exactly as run, the platform, the date, and the number of results the database reported. Log it with `--interface "<platform>, run by the user"`, the user's `--date` and `--total`, and add the file with `--format ris`. Never log in to a database on the user's behalf.

## The log

| Field | Option | Note |
|---|---|---|
| Source | `--source` | "Researchzy index", "PubMed", "ClinicalTrials.gov", "Embase" |
| Kind | `--kind` | `database`, `register`, or `other` (reference lists, papers known to the user) |
| Interface | `--interface` | `search_papers`, "E-utilities", "API v2", "Ovid, run by the user" |
| Date | `--date` | UTC; the default is now |
| Query | `--query` | Exactly as sent |
| Filters | `--filter name=value` | Each filter as sent, repeatable |
| Reported total | `--total` | As the source reported it |
| Exported | `--exported` | Only when it differs from the records you will add; otherwise the records added count |
| Pages | `--pages`, `--last-page` | Pages fetched; whether the last one was reached |
| Round | `--round` | 1, or 2 and up for an update |

A search that exported fewer records than its reported total without reaching the last page is incomplete: fetch the rest, or record the reason with `search --id s3 --incomplete-reason "…"`. An explained gap is a warning that the limitations repeat; an unexplained one is an error. Correct a wrong entry with `search --id`; the change is dated.

## Known papers and other methods

`check` names every seed that no database or register search found (SEED_NOT_FOUND). Read that paper's title and abstract for the words it uses, and search again with them. If it is still missing, log a search with `--kind other --source "known to the user"` and add its record so that it is screened; the limitations name the seeds the searches missed.

The reference lists of included studies may be searched too: look up each candidate with `search_papers` by DOI or title and log those searches with `--kind other --source "reference lists"`.

## Updates

Run every logged query again with `--round 2` and a lower date bound: `yearFrom` for the Researchzy index (whole years, so records screened before come back and count as duplicates), `mindate`, `maxdate` and `datetype=edat` for PubMed, and the API's first-posted date filter for ClinicalTrials.gov.

## Never

- Call a search complete, comprehensive or exhaustive.
- Read registry web pages, or log in to a subscription database.
- Add a paper from memory: a paper enters the review only as a record of a logged search.
