# Findings, verdicts and the second round

A finding is one problem, written so that the author can find it, check it and close it. `scripts/review_check.py check` enforces what is on this page; the file format is at the end.

## The contract

| Field | What goes in it |
|---|---|
| `id` | `F1`, `F2`, … in the order found. An id is never reused or renumbered, also after a finding is withdrawn. |
| `location` | Section, paragraph, table, figure or line: enough to find the place without searching. |
| `quote` | The passage at issue, copied word for word from the file given to `--manuscript`: one passage, five words or more (twelve characters in a script without Latin words). For a table, the row; for a figure, its caption. |
| `where_looked` | In place of `quote`, only for something missing from the paper: the sections, tables and files searched for it. "The paper does not report X" is a claim about what was read, so it names what was read. |
| `observation` | What the manuscript says or shows there. A fact a reader can confirm; no judgement yet. |
| `basis` | The criterion it fails: what a claim of this type needs, arithmetic that does not add up, a statement elsewhere in the manuscript, a retrieved record. Not taste. |
| `why_it_matters` | Which claim or conclusion changes if this stays open. |
| `fix` | The smallest change that is enough. One fix, not a list of things the authors could consider. |
| `closure_test` | What is true of the revised manuscript once this is closed, checkable by reading it. |

One finding per problem; the same problem in several places is one finding that lists the places. A finding that affects no claim is minor, or is not a finding.

**Choosing the fix.** Prefer, in this order: narrow the claim to what the evidence shows; state the limit or disclose the missing detail; re-analyse data the authors have; new work. Ask for a new experiment only when no narrower claim would be worth publishing, and say what it has to show.

## Four separate judgements

| Field | Value | Use when |
|---|---|---|
| `severity` | `critical` | A load-bearing claim fails, or cannot be evaluated as written; the main conclusion would change. Always blocking. |
| | `major` | A main claim needs narrowing, more support or a disclosure. A reviewer will very probably raise it. |
| | `minor` | Worth fixing; no conclusion depends on it. |
| `evidence_status` | `confirmed` | The manuscript itself shows the problem: its text, a table, the arithmetic. |
| | `reporting_gap` | Something needed to judge is not reported. The work may be sound; the manuscript does not show it. |
| | `unresolved` | It cannot be settled from what was provided: it needs the data, the code or the authors. |
| `blocking` | `true` / `false` | `true`: the manuscript should not go out until this is closed. `false`: it can go out with this open, at a known risk. |
| `fixability` | `existing_data` | The fix is rewording, narrowing, disclosing, or re-analysing what the authors have. |
| | `new_work` | The fix needs an experiment, data or an analysis that does not exist yet. |
| | `not_fixable_now` | A property of the design. The claim has to go or be reframed. |

Keep them apart: a suspicion is `unresolved`, not a milder `confirmed`, and a serious gap in reporting is still a `reporting_gap`. There is no quota. No critical and no major finding is a result; do not promote minor findings to fill a tier, and do not add praise to balance criticism.

## Verify your own findings

Before any verdict, take every `critical` and `major` finding back to the manuscript. Search all of it, with the supplement, for the place where the authors already answer the point: limitations, footnotes, appendix, captions, a later section. State the strongest reply they could give from their own text. For "this number is wrong" or "this cannot work", redo the arithmetic or build the counter-case first.

| `verification.outcome` | Meaning | Then |
|---|---|---|
| `confirmed` | Nothing in the manuscript answers it. | Keep it. |
| `downgraded` | It is partly answered, or weaker than first written. | Lower `severity` or `blocking`, and rewrite the observation. |
| `refuted` | The manuscript already deals with it, or the reading was wrong. | Leave it in the file; the script drops it from the report. |

`verification.note` says what was reread and what it showed. Two of your own passes agreeing is not confirmation; the text is.

## Two verdicts

| Verdict | `scientific`: do the load-bearing claims follow from the evidence shown | `submission`: should this version go out |
|---|---|---|
| `hold` | A central claim fails and no rewording rescues it. | A blocking finding needs new work, or is not fixable now. |
| `revise` | The claims follow once narrowed or completed from existing material. | Every blocking finding can be closed with existing material. |
| `ready` | Every load-bearing claim is supported. | Nothing was found that should delay it. |
| `not_assessable` | What was provided or read is not enough to say. | The same. |

The least fixable blocking finding decides, not an average of the findings. A finding stands unless it was refuted or, in a second round, resolved. The script refuses `ready` for either verdict when the coverage of `manuscript` is not `read`; for `submission` while any blocking finding stands; and for `scientific` while a blocking finding that is `confirmed` or `unresolved` stands, or a claim is rated `unsupported` or `contradicted`. A blocking `reporting_gap` allows a scientific `ready` only when the missing item is not needed to judge the claims, such as a required statement; otherwise the scientific verdict is `not_assessable`.

Each verdict has a one-sentence `reason` naming the findings behind it. No score, no rating, no chance of acceptance.

## Second round

Work on a copy, `paper-review/round-2/findings.json`, so the first round stays as it was. Ids stay; a new problem gets a new id.

1. Run `recheck` on the copy with the revised files. It reports each quoted passage as `unchanged`, `changed` or `gone`. A passage with a word added inside it can still read as `unchanged`.
2. For each finding, read the revised text and apply its `closure_test`. Judge from the manuscript before reading the authors' response: "we fixed it" is not evidence.
3. Record `recheck.status`, then run `check` on the copy with the revised files. A finding that still stands has to be quotable from them: where its passage was reworded, set `quote` to the new wording.

| Status | Meaning | Needs |
|---|---|---|
| `resolved` | The closure test is met. | The old passage changed or gone, or `recheck.quote`: the new text that meets the test, word for word. The finding leaves the verdict rules. |
| `partial` | Part of the fix is there. | `note`: what is left. |
| `open` | Nothing relevant changed. | Nothing. |
| `regressed` | The revision made it worse. | `note`. Something newly broken is a new finding. |

## `findings.json`

```text
{"title": "…", "target": "…",            the manuscript's title; the venue aimed at, or "not stated"
 "summary": "…",                         the question, the design and the main claims; no judgement
 "strengths": ["…"],                     optional
 "coverage": [{"item": "manuscript",     manuscript, supplement, data and code are required items
               "status": "read",         read | partly_read | not_read | not_provided
               "note": "main.tex"}],     required for partly_read and not_read
 "claims": [{"id": "C1", "claim": "…",   optional: the load-bearing claims
             "location": "Abstract",
             "type": "causal",           causal | generalisation | improvement | priority | formal | descriptive
             "evidence": "Table 2",      where the manuscript supports it
             "support": "limited",       supported | limited | unsupported | contradicted | not_assessable
             "mismatch": ["scope"],      direction | magnitude | population | outcome | timepoint |
             "note": "…"}],              causal_language | scope
 "checks": {                             each status: done | skipped; skipped needs "note"
   "novelty": {"status": "done", "searches": [{"query": "…", "total": 41}],
               "closest_works": [{"corpusId": 1, "title": "…", "year": 2024, "cited": false,
                                  "differs": "…"}]},
   "references": {"status": "skipped", "note": "…"},
   "statistics": {"status": "done", "note": "…"}},
 "findings": [{"id": "F1",
               "severity": "major",              critical | major | minor
               "evidence_status": "confirmed",   confirmed | reporting_gap | unresolved
               "blocking": true,                 true | false; a critical finding is always blocking
               "fixability": "existing_data",    existing_data | new_work | not_fixable_now
               "location": "Section 4.2, Table 3",
               "quote": "…",                     verbatim from the manuscript, five words or more
               "where_looked": "…",              instead of a quote, for something missing from the paper
               "observation": "…", "basis": "…", "why_it_matters": "…", "fix": "…", "closure_test": "…",
               "claims": ["C1"],                 optional: the claims it bears on
               "verification": {                 required for critical and major
                 "outcome": "confirmed",         confirmed | refuted | downgraded
                 "note": "…"},                   what was reread and what it showed
               "recheck": {                      second round only
                 "status": "resolved",           resolved | partial | open | regressed
                 "quote": "…", "note": "…"}}],   quote: verbatim from the revised manuscript
 "verdicts": {                                   each verdict: hold | revise | ready | not_assessable
   "scientific": {"verdict": "revise", "reason": "…"},
   "submission": {"verdict": "hold", "reason": "…"}},
 "referee": {"venue": "…", "ai_use_confirmed": true,       with --referee only
             "recommendation": "…", "to_editor": "…"}}
```

`check` prints a JSON summary. Each entry of `errors` has `where`, `problem` and a `message` saying what to change. Correct `findings.json` and run it again; do not edit `review.md` to get around an error.

Known limit: the quote match allows for words that text extraction puts between the quote's words, so a quote that leaves out a word such as "not" is still found. Reread any quote that turns on a negation or a qualifier.
