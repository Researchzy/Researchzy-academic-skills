# PRISMA flow, extraction table and report

## Records, reports and studies

- A **record** is one title and abstract returned by one search. The same paper found by two searches is two records in one group: "records identified" counts records, and the duplicates are removed before screening.
- A **report** is a document about a study: a journal article, a conference abstract, a registry entry, a preprint. Screening decides groups of records; from full text on, each group is one report.
- A **study** is what reports describe: one trial, one cohort. `study` labels join the reports of one study. Studies are never more than reports, and the review gives both numbers.

## Where each number comes from

| Box | From the ledger |
|---|---|
| Records identified, per source | Records added with `records`, per source and kind |
| Duplicate records removed | Records identified minus the groups first found in this round |
| Records removed for other reasons | Groups with the `pre` decision `remove` |
| Records screened | The other new groups |
| Records excluded, per code | Final `ta` decisions `exclude` |
| Reports sought for retrieval | Final `ta` decisions `include` or `unsure` |
| Reports not retrieved | Final `ft` decisions `not_retrieved` |
| Reports assessed for eligibility | Final `ft` decisions `include` or `exclude` |
| Reports excluded, per code | Final `ft` decisions `exclude` |
| Reports of included studies | Final `ft` decisions `include` |
| Studies included | The distinct `study` labels of those reports; a report without a label is its own study |

Records from other methods (`--kind other`, such as reference lists) are screened like the rest and counted in the same flow; the identification box lists their source by name.

## Identities

`sr_prisma.py` evaluates each identity: OK when both sides are known and agree, FAIL when both are known and disagree, NOT_ASSESSED when a side is unknown (for example a previous version given only in part). NOT_ASSESSED is not OK and is reported as it is. A FAIL exits 1: run `check` to find the records behind it, and never report a flow with a FAIL.

1. records identified - duplicates removed - records removed for other reasons = records screened
2. records screened - records excluded = reports sought for retrieval
3. reports sought - reports not retrieved = reports assessed
4. reports assessed - reports excluded = reports included
5. records identified = records exported, by the search log
6. studies included <= reports of included studies

## Updates

Searches logged with `--round 2` belong to an update, and `sr_prisma.py --round 2` counts their records. A record already in the ledger from round 1 counts as a duplicate removed; only the new groups are screened. The studies and reports included in round 1 become the previous version, and the totals add the new ones. A new report of a study included before takes that study's label: it adds a report, not a study.

When the previous version was made outside this ledger, give its numbers with `--previous-studies N --previous-reports M`; a new report of one of its studies takes a label beginning with `previous:`. With only one of the two numbers, identity 6 is NOT_ASSESSED.

## Extraction table

`systematic-review/extraction.csv` uses the format of `researchzy-meta-analysis` (plugin `researchzy-evidence`, when installed; its effect-sizes reference is the authority). One row per arm of a study for each outcome and time point of the protocol; one row per study, with `arm` empty, for `ratio_ci`, `r` and `yi_se`. The header:

```
study,outcome,timepoint,arm,n,design,reported_as,value,spread,low,high,ci_level,events,cluster_size,icc,icc_source,corr,corr_source,units,reverse,locator,quote,notes
```

| Column | Content |
|---|---|
| `study` | The `study` label of the included reports: one label, and one row per arm, however many reports |
| `outcome`, `timepoint` | As the protocol names them, spelled the same in every row |
| `arm` | `control` for the comparator, any other name for an intervention arm; empty on study-level rows |
| `n` | Participants analysed in the arm (on a study-level row, in the study) |
| `design` | `parallel` (the default when empty), `cluster` or `crossover` |
| `reported_as` | `mean_sd`, `mean_se`, `mean_ci`, `change_sd`, `change_se`, `change_ci`, `median_iqr`, `median_range`, `change_median_iqr`, `change_median_range`, `events`, `ratio_ci`, `r` or `yi_se` |
| `value`, `spread`, `low`, `high`, `ci_level`, `events` | The numbers as printed; `reported_as` decides which are needed |
| `cluster_size`, `icc`, `icc_source` | Cluster trials: mean cluster size, intracluster correlation and where it comes from |
| `corr`, `corr_source` | Crossover trials: the within-person correlation and its source |
| `units`, `reverse` | The outcome's unit; `reverse` is `yes` when higher is better on this scale and lower elsewhere |
| `locator`, `quote` | Page, table or figure, and the words that carry the numbers, copied from the full text |
| `notes` | Whatever was inferred, such as "values are mean (SE), per the table's footnote" |

Any further column (dose, setting, country) is kept as a study characteristic. Copy numbers as printed: convert, impute or round nothing here, because conversions belong to `researchzy-meta-analysis`. A number the report does not give stays empty, and `notes` says so. `check` finds each quote in a full text of the study, and `value` (or `events`) among the quote's numbers.

## report.md

Every number comes from `prisma.json`, `check.md`, a calibration score or the extraction table. Use this structure:

```markdown
# <title>: a systematic review

<date> · protocol version <n> · searches from <first> to <last> (UTC)

## Methods
- Protocol and registration: <the registration sentence of prisma.json>. Amendments: <each, with its date and whether results had been seen>.
- Eligibility criteria: <frame>; the criteria with their codes (table).
- Information sources and searches: <each source, interface and date>; the full queries in Appendix A. <the index limits of searching.md, when the index was searched>
- Selection: <the model screened titles and abstracts after calibration against the user on <n> records (kappa <k>, include recall <r>, thresholds <…>)>, or <the model screened alone because <reason>>. Full texts were obtained from <…>; the full-text decisions were made by <…> and checked by <…>.
- Data collection: <who extracted which outcomes; every number carries its locator and a quote>.
- Risk of bias and synthesis: not part of this report <assessed with researchzy-risk-of-bias / pooled with researchzy-meta-analysis, when installed>.

## Results
- Study selection: <the counts of prisma.json in one paragraph>; Figure 1 is prisma.svg. Reports not retrieved: <number, and which>.
- Characteristics of the included studies: a table (study, design, population, n, intervention, comparator, outcomes, time points) from the extraction table and the full texts.

## Limitations
- Searches: <the index limits>; <incomplete searches and why>; <seeds the searches missed>; <sources not searched>.
- Screening: <the calibration result, or that the model screened alone>; <the audit result, if one was made>.
- Full texts not retrieved: <number>.

## Appendix A: searches
<the Searches table of prisma.md>

## Appendix B: full-text reports excluded, with reasons
<the table of prisma.md, with the criterion text for each code>
```
