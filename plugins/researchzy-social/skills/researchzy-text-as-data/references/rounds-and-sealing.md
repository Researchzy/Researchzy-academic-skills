# Rounds and sealing

A round compares your labels with the user's on the same units, each made without seeing the other. It tests the instruction file, the codebook and the model together, as they stood when the round was drawn. Run the first round once the protocol, codebook and instructions are settled, and before the full run.

## Drawing

`tad_ledger.py sample` draws `sample_size` units (or `--size`) and writes `rounds/round<N>-sample.json` (seed, pool size, the corpus, codebook and instruction hashes, each unit with its groups and the hash of its text), `round<N>-model.csv` and `round<N>-user.csv`, plus `round<N>-second.csv` with a second coder. Each file has the columns `unit, text, label, note`, with `label` empty.

| Left out of the pool | Why |
|---|---|
| Units drawn for an earlier round | A new round brings new units, so a revision is tested on units it was not written from |
| Units in `exposed.txt` | Their labels were where you could read them |
| Units quoted in the instructions or the codebook | Their label is in the text you follow |
| Units with an empty text | There is nothing to label |

- `--stratify product_line` gives each group units in proportion to its size in the pool. Proportional draws keep the round's error rates representative of the corpus, which `correct` assumes.
- The seed is the protocol's seed + N − 1 unless `--seed` is given; it is recorded, and the same seed on the same files draws the same units.
- After scoring, read the counts per class: a class with few units in the user's labels has a wide interval. When it matters and is rare, draw the next round larger.

## Leakage, both ways

| Direction | How it happens | Guard |
|---|---|---|
| The user's labels reach you | A label column in the corpus; the user's file filled before the seal; labels pasted in the chat; examples taken from drawn units | `sample` refuses label columns and exposes their units; `seal` refuses a filled user file and exposes the round; `sample` refuses instructions that quote a drawn unit |
| Your labels reach the user | Showing your file, or discussing units before the score | Give the user only their file; show nothing until the score |
| The instructions fit the round | Editing them after reading the round's texts | `seal` and `score` refuse instructions or a codebook changed after the draw |

The user may label their copy before or after your seal, as long as their labels reach the folder and the chat only after it.

## The seal

`tad_ledger.py seal --host H --model M --batch-size B` checks that every unit of the model's file has a class and an unchanged text, that the file has no extra column, and that the user's files are still empty. It writes `round<N>-seal.json`: the SHA-256 of the model's file, the instruction file and its SHA-256, the codebook version and SHA-256, host, model, sampling settings, batch size, format and time.

- **Host and model**: the product (for example Claude Code, Codex or the Researchzy Agent) and the model name it shows you now. Never fill in a version you were not shown.
- **Sampling settings** (temperature and the like) usually cannot be set or read in an agent session; they are recorded as `not controllable`. When the host shows them, pass `--sampling` with what it shows.
- **Batch size and format**: how many units you labelled at once and how they were shown (`--format`, by default the round file's CSV rows). The full run keeps both; a larger batch or another presentation is another procedure.

## What score computes

| Figure | Single-label | Multi-label |
|---|---|---|
| Kappa | Cohen's kappa from the full table; chance from each coder's own margins | Per class, on present or absent |
| Alpha | Krippendorff's alpha, nominal, with a seeded bootstrap interval | Per class |
| Per class | Precision, recall, F1, support (the user's count), the model's count | The same, per class |
| Overall | Accuracy; macro-F1 over the classes that occur in the user's labels | Exact-match accuracy; macro-F1 |
| Errors | Confusion matrix (rows: the user; columns: the model) and where each class's errors went | Units each class was missed in or added to |

Intervals are percentile intervals over the round's units resampled with replacement (`--boot`, 1000 by default), seeded with the round's seed; a report lists resamples where a figure could not be computed. Every disagreement is listed with its text.

A class that does not occur in the user's labels is **not estimable**: the round says nothing about it. It is never reported as 0 or 1, it is left out of macro-F1, and `check-run` reports it as not validated. A kappa or alpha with chance agreement of 1 (one class only) is not estimable as well.

| Status | Meaning |
|---|---|
| `passed` | Kappa, alpha, macro-F1 and every estimable class's F1 reach their thresholds |
| `below_threshold` | At least one falls short; the reasons are listed |
| `not_assessable` | A figure the status needs could not be estimated |

Read a disagreement as material for the codebook, not as an error to count against either side: ask which definition or which instruction would have settled it.

## A scored round is final

`score` refuses a round scored before. After a revision, draw a new round with new units; never edit a filled file and score it again. Every score and `check-run` report lists the rounds drawn and their statuses, so a pass after several failures is visible to a reader.

## A second coder

When `second_coder` is true, `score` reports agreement between the two people first. It shows how far people agree on these units under this codebook; judge the model's figures against it, not against 1, and report the two separately.

## What the figures show

How far the model and this user agree on these units, under this instruction file, this codebook and this model. They do not show that the model reads as a person would, they say nothing about the user's own consistency, and they do not carry over to another version of any of the three, to another language, genre or period, or to another model.

## Reporting a round

For each round: units and how they were drawn (pool, seed, groups), codebook version and instruction hash, who labelled and in which order (the seal), host and model, thresholds and their source, kappa, alpha, macro-F1 and per-class F1 with intervals, classes not estimable, and what changed afterwards.
