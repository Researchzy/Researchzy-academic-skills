# Reporting guidelines by study design

A reporting guideline is a checklist, agreed by a field, of what a paper of a given design has to report. Many journals require the completed checklist with the submission. This file only helps to name the right one. It contains no checklist items on purpose: guidelines are revised, and items recalled from memory are often from an old version or wrong.

## How to use it

1. Take the study design from the author's materials (the protocol or the Methods), not from the title. If the venue's instructions name a guideline, that one applies.
2. Find the row. When two rows apply (a randomised trial of an AI system; a cohort built from routine health records), both guidelines apply.
3. Get the current checklist from the guideline's own website, or ask the author for the checklist file the venue wants. Record in `writing/outline.md` which guideline, which version and the date you obtained it.
4. Give every item that applies an evidence slot in the outline, in the paragraph where it will be reported. An item the materials cannot answer goes into `writing/gaps.md` as `[Author input needed: …]` or `[Evidence needed: …]`.
5. If you cannot obtain the checklist, say so and name the guideline; do not write items from memory.

Filling in the checklist form for submission is the author's task. Offer the item-to-location mapping from the outline when they ask.

## Study design to guideline

| Study design | Guideline | What it is for |
|---|---|---|
| Randomised trial | CONSORT | Reporting how a trial was designed, run and analysed, and the flow of participants |
| Protocol of a trial | SPIRIT | What a trial protocol has to define before the trial starts |
| Trial of an intervention that includes an AI system | CONSORT-AI (protocol: SPIRIT-AI) | The extra items on the AI system, its inputs and its use in the trial |
| Non-randomised evaluation of an intervention | TREND | Reporting intervention studies without random assignment |
| Cohort, case-control or cross-sectional study | STROBE | Reporting observational studies in epidemiology |
| Observational study on routinely collected health data | RECORD | Additions to STROBE on data sources, linkage and code lists |
| Mendelian randomisation study | STROBE-MR | Additions to STROBE on instruments and their assumptions |
| Genetic association study | STREGA | Additions to STROBE on genotyping and population structure |
| Systematic review or meta-analysis | PRISMA | Reporting the search, selection, synthesis and flow of studies |
| Protocol of a systematic review | PRISMA-P | What a review protocol has to specify |
| Scoping review | PRISMA-ScR | Reporting a review that maps a field without pooling effects |
| Meta-analysis of observational studies | MOOSE | Reporting the pooling of observational evidence |
| Synthesis of qualitative studies | ENTREQ | Reporting how qualitative findings were searched and combined |
| Diagnostic accuracy study | STARD | Reporting the test, the reference standard and the flow of participants |
| Prediction model, by regression or machine learning: development or validation | TRIPOD+AI | Reporting how a model was built, tested and performs |
| Study that uses a large language model in health research | TRIPOD-LLM | Reporting the model, the prompts and the evaluation |
| AI in medical imaging | CLAIM | Reporting data, reference standard, model and evaluation in imaging AI |
| Reliability or agreement study | GRRAS | Reporting how raters or methods were compared |
| Animal experiment | ARRIVE | Reporting in vivo experiments so that they can be judged and repeated |
| Case report | CARE | Reporting a single patient's course completely |
| Quality improvement study | SQUIRE | Reporting what was changed in a system of care, why and with what result |
| Qualitative research | SRQR | Reporting qualitative studies of any approach |
| Interviews and focus groups | COREQ | Reporting the research team, the method and the analysis |
| Economic evaluation | CHEERS | Reporting costs, outcomes, perspective and model |
| Clinical practice guideline | RIGHT | Reporting how a guideline's recommendations were reached |
| Sex and gender in any study | SAGER | Reporting sex and gender in design, analysis and interpretation |

## Fields without a guideline of this kind

Computer science, engineering, physics and much of quantitative social science have no single design-based guideline. There the venue's own checklist applies (a reproducibility or ethics checklist, an artifact form, a preregistration template). It comes from the author's venue instructions; ask for it at the start and treat its items as in step 4. Do not list a venue's checklist items from memory.

## Limits

- The table names guidelines; it does not say which version is current. Check on the guideline's site.
- Many guidelines have extensions for particular designs (cluster trials, non-inferiority trials, abstracts, harms, network meta-analyses). Look for one on the guideline's site when the design is a variant.
- A guideline says what to report, not how the study should have been done. Following it does not make a design stronger, and the wording rules in [Sections](sections.md) still apply.
