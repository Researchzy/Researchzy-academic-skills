# Researchzy Evidence plugin

Version 2.2.0. Three skills for evidence synthesis: a systematic review from protocol to PRISMA 2020 flow, risk of bias and certainty of evidence, and meta-analysis. They run on your machine; risk of bias and meta-analysis work on the files you give them, and searching Researchzy's index needs the [`researchzy`](../researchzy) plugin and a Researchzy account.

| User goal | Skill | Result |
|---|---|---|
| A systematic review of one question | `researchzy-systematic-review` | A protocol with coded criteria, searches logged with their dates and counts, deduplication, screening with a quoted reason for every exclusion and a calibration sample you screen, an extraction table, and a PRISMA 2020 flow whose numbers a script computes from the per-record ledger |
| Risk of bias of the included studies, and certainty of the evidence | `researchzy-risk-of-bias` | Judgements per study, result and domain under the tool you register, each with a quote a script finds in the full text; traffic-light and summary plots; a summary of findings with a reason and the studies behind every downgrade |
| A meta-analysis from an extraction table | `researchzy-meta-analysis` | Effect sizes with declared conversions, pooled estimates with heterogeneity and a prediction interval, forest and funnel plots, sensitivity and subgroup analyses, and Results text checked against `results.json` |

Example prompts:

- `Run a systematic review: in adults, does time-restricted eating improve sleep compared with usual eating? Randomised trials since 2015.`
- `Assess the risk of bias of these three trials for the outcome body weight, then give me the summary-of-findings row.`
- `Pool this extraction table, look at heterogeneity, make the forest and funnel plots, and write the Results paragraph.`

## With Researchzy connected

Install the [`researchzy`](../researchzy) plugin and sign in, and the systematic review searches Researchzy's index of about 250 million papers beside PubMed and ClinicalTrials.gov, with every query logged; without it the review runs on PubMed, the trial register and your own database exports, and says so. Risk of bias and meta-analysis can then fetch the full text of a study the index holds, to quote it and to settle whether a value is an SD or an SE.

## Requirements

Python 3.10+ for the bundled scripts. The systematic review and the risk-of-bias checks need only the standard library. The meta-analysis needs numpy and scipy, and matplotlib for its plots; the risk-of-bias plots need matplotlib. PubMed and ClinicalTrials.gov are searched through their public interfaces, which need web access but no key. The third-party notices are in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
