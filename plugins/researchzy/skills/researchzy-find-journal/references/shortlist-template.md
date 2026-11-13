# Shortlist template

Write `journal-shortlist/shortlist.md` in this layout. `venue_tally.py check` reads the `##` headings, the `###` venue headings under `## Shortlist`, the `- Band:` and `- Reason:` lines, and the tables under `## Added by judgement`, `## Facts to confirm` and `## Cascade plan`. Keep those headings word for word; a number before a heading (`## 4. Facts to confirm`) is allowed.

```markdown
# Journal shortlist: <short title of the manuscript>

<date> · <article type> · evidence: tally.md, facts.md

## Brief

- Manuscript: <title, or one line on what it reports>
- Article type: <research article, letter, review, methods paper, conference paper, …>
- Constraints: <open access required, fee ceiling, speed, language; or "none given">
- Excluded by the user: <venues, or "none">

## Evidence

<Three or four sentences from tally.md: how many searches, similar papers and references were counted,
how many references had no venue or were not found, how many papers were found twice. Name the
venues that lead both streams.>

## Shortlist

### 1. <Venue name as written in tally.md>

- Band: strong fit
- Reason: <one or two sentences: which evidence puts the topic in scope, and what could still stop it>
- Origin: tallies (<n> similar papers, <m> references, <years>)
- Recent papers on the topic: `<query>` with the venue filter, <rows returned> rows; "<title>" (<year>); "<title>" (<year>); "<title>" (<year>)
- Registries: <the wording from bands-and-cascade.md for its Crossref and DOAJ status>
- Scope: <the scope statement in a few words, or "not read">
- Constraints: <met / not met / unknown, per constraint, from recorded facts only>
- Design and rigour: not judged here (researchzy-paper-review)

### 2. <Venue name>

- Band: plausible
- Reason: <…>
- Origin: added by judgement (see below)
- …

## Added by judgement

| Venue | Why it was added | Evidence found for it |
|---|---|---|
| <venue> | <reason> | <venue-filter search: rows returned, or "none"> |

## Facts to confirm

| Venue | Field | Value | Source | Date read |
|---|---|---|---|---|
| <venue> | Scope statement | confirm on site | | |
| <venue> | Fee | <value copied from facts.md> | <its URL> | <its date> |

## Cascade plan

| Step | Venue | When | Why |
|---|---|---|---|
| 1 | <venue> | First submission | <…> |
| 2 | <venue> | After a desk rejection | <…> |
| 3 | <venue> | After a rejection following review | <…> |

<Same-publisher transfer and presubmission inquiry, in two or three sentences.>

## What was not checked

- <venues not looked up, lookups that failed, facts left to confirm on site, the design bar>
```

When every venue came from the tallies, write `None.` under `## Added by judgement` and no table.

## The shortlist

- One `### <n>. <Venue>` heading per venue, five to eight venues. Write the venue's name as it appears in `tally.md` (any of the spellings listed there), or exactly as in the judgement table.
- `- Band:` is one of `strong fit`, `plausible`, `stretch` and nothing else. `- Reason:` is never empty. See [bands and cascade](bands-and-cascade.md).
- A venue that is not in `tally.json` must have a row under `## Added by judgement`, or `check` fails.
- A preprint server is not a venue. If the user wants to post a preprint, say so in the Brief, not in the shortlist.

## The facts-to-confirm table

Nine rows per shortlisted venue, one per field, in this order. The Field cell is the label as written here.

| Field | What to look for | Where it can come from in this session |
|---|---|---|
| Scope statement | The journal's aims and scope, quoted or closely summarised | The venue's aims page (DOAJ gives its address) |
| Article types accepted | Whether the manuscript's article type is listed | The author instructions |
| Length limits | Word, page or figure limits for that article type | The author instructions |
| Open-access model | Fully open, hybrid or subscription; licence | DOAJ for a listed journal; the venue's site |
| Fee | Article processing charge or page charges, with currency | DOAJ for a listed journal; the venue's fee page |
| Peer-review model | Single-blind, double-blind, open | DOAJ for a listed journal; the venue's site |
| Time to decision | What the venue itself reports, with what it measures | The venue's site. DOAJ's weeks are submission to publication, not to decision |
| Indexing | Where the venue says it is indexed, or DOAJ listing | DOAJ; the venue's site |
| Preprint policy | Whether a posted preprint is accepted | The author instructions |

Each Value cell is one of two things:

1. A value copied from the "Rows for the facts-to-confirm table" section of `facts.md`, with the Source and Date read cells copied from the same row. It comes from `lookup` or from `fact` (a page you opened in this session). `check` matches the value, the URL and the date against `facts.json`.
2. The exact words `confirm on site`, with Source and Date read left empty.

Nothing else: no "about", no remembered figure, no "varies", no empty cell. A value from DOAJ stays worded as `facts.md` gives it ("as declared to DOAJ").

## Numbers anywhere in the report

`check` takes every sentence and table cell that contains "impact factor", "acceptance rate", "APC", "article processing charge", "fee", "week" or "day", and requires each number in it to be in a recorded fact (under a venue's heading, a fact of that venue). Write such a number only when `facts.json` holds it. In the cascade plan and elsewhere, write "after the time the venue states" rather than a number of weeks. Web addresses, dates written as 2026-11-12, text in double quotes (paper titles) and fenced code are not read; put titles in quotes.

`check` also fails on the words "probability", "chance of acceptance", "likelihood of acceptance", "odds of acceptance", and on a percentage in the same sentence as "accept" (outside a recorded acceptance rate). Do not use them even to say that none is given.

## Excluded venues

A venue the user excluded (`tally --exclude`) must not be a shortlist heading, a row of the judgement table, a row of the facts table, or a venue of the cascade plan. Mentioning it in the Brief is expected.

## What `check` reports

`ok`, the venues `from_tally` and `added_by_judgement`, the count of sourced cells and of `confirm on site` cells, and `problems` with the rule and line: `layout`, `origin`, `band`, `facts_table`, `cascade`, `excluded`, `unsourced_number`, `prediction`. `notes` are not failures: a shortlist outside five to eight venues, and venues never looked up in the registries, which belong under "What was not checked".
