# Sections: what goes where, and how strongly to say it

Write in this order: tables and figure list, Methods, Results, Discussion, Introduction, abstract and title. The displays fix what was found; Methods and Results are then a description of them; the Discussion and Introduction can only promise what Results delivered; the abstract is a summary of a finished text.

## One job per paragraph

Give each paragraph one of these jobs and say which in the outline:

| Job | The paragraph answers |
|---|---|
| context | What is known that the reader needs? |
| gap | What is not known, and how do we know it is not? |
| aim | What did this study set out to do? |
| procedure | What was done, to what, in which order? |
| result | What was found, with which number? |
| comparison | How does this sit with earlier findings? |
| interpretation | What may explain it? |
| limitation | What could make the result wrong, and in which direction? |
| implication | What follows, and for whom? |

A paragraph that does two jobs is split. Its first sentence states its point; the rest supports that sentence. Do not end a paragraph by repeating its first sentence.

## What each section must and must not contain

| Section | Must contain | Must not contain |
|---|---|---|
| Title | the object of study and either the design or the main finding | a claim stronger than the Results; an undefined abbreviation |
| Abstract | aim; design and data; the main result with its number and uncertainty; a conclusion the design allows | a number that is not in the main text; a result not in Results; a citation, unless the venue wants one |
| Introduction | what is known, cited at its evidence grade; the gap; the aim or hypothesis. In computer science and engineering also two to four contributions, each pointing to the section or display that delivers it | the results in detail; a literature survey beyond what motivates the aim; "first" or "no study has" without a logged search |
| Methods | design; setting or data source; participants, samples or units and how they were chosen; variables and outcomes, with which were pre-specified; procedures; the analysis, with software and version as the author's files give them; approvals and registration | results; a method that Results never uses; a choice justified by how the result came out |
| Results | the flow of participants or data first; then findings in the order of the outline, each paragraph opening with the finding and its number; effect sizes with their uncertainty; every pre-specified outcome | interpretation, mechanism or comparison with other studies; an analysis that Methods does not describe; "a trend towards" for a result that did not meet the stated criterion |
| Discussion | the main finding in one or two sentences, without repeating its numbers; comparison with earlier work; possible explanations, worded as such; limitations; what follows | a new result; a second run through Results; a conclusion the design cannot carry |
| Conclusion | one paragraph, bounded as the Discussion is | anything not argued above |

Every analysis in Results has its method in Methods, and every method in Methods has its result in Results. Check both directions before the abstract is written.

## Where a result belongs

| Result | Main text | Caption | Supplement |
|---|---|---|---|
| Primary outcome | the finding, its number and uncertainty | what the display shows, units, n | — |
| Pre-specified secondary outcomes | one sentence each, with the number | — | full tables, if long |
| Unfavourable or null result of a pre-specified analysis | stated as plainly as a favourable one | — | never only here |
| Sensitivity and robustness analyses | one sentence: what was varied and whether the conclusion held | — | the numbers |
| Baseline or descriptive characteristics | only what the reader must know to judge the result | — | the rest, or a table |
| Detail needed to read a display (definitions, symbols, tests) | — | here | — |
| Per-item, per-site, per-seed detail | the range or the pattern | — | the table |

Before moving anything out of the main text, ask: would a reader judge the main claim differently if they never saw it? If yes, it stays. The text gives the pattern and the key numbers of a table; it does not read the table aloud.

## A strong verb needs a design feature

| Wording | Licensed by |
|---|---|
| causes, leads to, reduces, improves, prevents, the effect of | random assignment, or a design that identifies a causal effect under stated assumptions (name the design and the assumption) |
| is associated with, is correlated with, was more frequent in | an observational comparison |
| predicts | validation on data not used for fitting |
| outperforms, is better than | the same data, split and metric for both, with uncertainty or repeated runs |
| shows, demonstrates | direct evidence in a display of this paper |
| suggests, is consistent with, may | indirect or partial evidence |
| generalises to | a test on data from another source |
| the mechanism is, is mediated by | an experiment that changes the proposed mediator |

When you write a verb from the upper rows, the same sentence or the next names the feature that licenses it ("in this randomised comparison", "on the held-out test set"). If you cannot name it, use the weaker verb. Calibrate in both directions: one hedge per claim is enough, and a result that the design does establish is stated without one.

## Limitations

Each limitation has four parts: what it is; the direction in which it would move the result (towards no effect, away from it, over- or under-estimating, or unknown, said plainly); how large it could be, if the materials allow an estimate; and what was done about it. "Our study has limitations" followed by a list of nouns is not a limitation paragraph. If the direction is not clear from the author's materials, write `[Author input needed: direction of bias from …]`.

## Unfavourable results

- Report every pre-specified outcome and analysis, in the order they were specified, whatever the result.
- Do not replace an outcome, metric, subgroup or time point by one that looks better. If the author's materials contain such a switch, say so in Methods as a deviation and keep the original result.
- Do not describe a null result as "promising", "a trend" or "numerically better" without the number and its uncertainty beside it.
- If the author asks to leave out a pre-specified outcome or analysis, do not remove it: say that omitting it is selective reporting, and offer its shortest honest form (one sentence, with the numbers in a supplementary table). An exploratory analysis that was not pre-specified may be left out at the author's request; say once what a reader would miss and record it in `gaps.md`.

## Numbers and terms

- A quantity keeps one value and one precision in the abstract, the text and the tables. A percentage is given with its counts (`48/602 (8.0%)`).
- Choose one name for each concept in the outline and use only that; a second name reads as a second thing.
- Define an abbreviation at first use in the abstract and again at first use in the main text; do not define one that is used once.
