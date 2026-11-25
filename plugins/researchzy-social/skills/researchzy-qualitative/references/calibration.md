# Calibration

A calibration round compares your coding with the user's on the same passages, each made without seeing the other. It applies to codebook thematic analysis and grounded theory; under reflexive analysis `sample` and `score` refuse ([approach](approach.md)). Run the first round after the user has coded a few passages and you have stated your style, and before you code the bulk, so that problems surface while they are cheap to fix.

## The unit

A unit is one participant turn: the text from a participant's label to the next label. In a source without speaker labels (an open answer, a field note) it is a paragraph. The pool leaves out:

- interviewer turns;
- turns shorter than the `min_unit_words` setting (a CJK character counts as a word);
- sources the user has not confirmed as de-identified;
- units drawn in an earlier round, so a new round brings new units;
- units that overlap a passage the user has already coded, because you have seen their codes there.

## A round, step by step

1. **Draw.** `qual_ledger.py sample --seed <integer>` draws `sample_size` units (or `--size`) at random and writes `calibration/round<N>-sample.json` (seed, pool size, codebook version, the units with their offsets and hashes) and `round<N>-model.csv`. Record the seed in the chat. The same seed on the same files draws the same units.
2. **Code first.** Fill the `codes` column of `round<N>-model.csv`: codes of the current codebook separated by `;`, or `none` when no code applies. Code each unit as you would in the bulk, from the codebook alone; put doubts in `note`.
3. **Seal.** `qual_ledger.py seal` refuses a file with an empty cell or a code outside the codebook. It records the file's SHA-256 in `round<N>-seal.json` and only then writes `round<N>-user.csv`, which has the same units and an empty `codes` column. The order of the two codings can thus be shown afterwards.
4. **The user codes blind.** Give the user `round<N>-user.csv`. They fill `codes` in a spreadsheet, or answer in the chat while you write their answers into the file word for word. Show them none of your codes and do not discuss the units until the round is scored.
5. **Score.** `qual_ledger.py score` writes `round<N>-score.json` and `round<N>-score.md`. It refuses when the model's file changed after the seal, when the codebook changed since the draw, or when the round was scored before.

A scored round is final. To try again, revise what needs revising and draw a new round with a new seed: never edit a filled file and score it again.

## What is computed

Because one unit may carry several codes, each code is scored on its own, as present or absent in each unit:

| Column | Meaning |
|---|---|
| Model, User, Both | Units in which the model, the user, and both applied the code |
| Kappa | Cohen's kappa; chance agreement from each coder's own rate of using the code |
| Alpha | Krippendorff's alpha for nominal data, from the coincidence matrix |
| Bootstrap interval | Percentile interval for alpha over units resampled with replacement (1000 resamples by default, seeded with the round's seed); it lists the resamples in which alpha could not be computed |
| Status | `passed` when kappa and alpha reach `kappa_min` and `alpha_min`; `below_threshold`; or `not_estimable` |

A code is **not estimable** when both coders applied it to every unit, or when neither applied it to any: chance agreement is then certain and the formula divides zero by zero. It is never reported as 1 or as 0. Such a code was not calibrated by this round; say so, and if it matters, draw a round from sources where it varies.

A code applied to one or two units gives a coefficient that rests on those units alone; its interval, and the number of resamples without it, show this. Read the counts before the coefficient.

## Status of the round, and what to do

| Status | Meaning | Do |
|---|---|---|
| `passed` | Every estimable code reaches both thresholds | Code the rest. List the codes that were not estimable |
| `below_threshold` | At least one code falls short | Go through every disagreement with the user, using the text in `score.md`. Sharpen definitions, inclusion and exclusion rules; record the change in `codebook-changes.csv`; draw a new round |
| `not_assessable` | No code could be estimated | Draw a larger round, or one from sources where the codes vary |

Disagreements are material for the codebook, not errors to be counted against either coder: for each one, ask which definition would have settled it.

## Thresholds

`kappa_min` and `alpha_min` are settings of `protocol.json` with their source and date; the defaults (0.60 and 0.667) are conventions, labelled as such in `score.md`. A threshold the user takes from a paper or a protocol is recorded with that source before the round is scored, never after the result is seen.

## What the figures show

They show how far the model and this user agree on these units under this version of the codebook. They do not show that the model codes as a person would, they say nothing about how consistently the user codes, and they do not carry over to a later version of the codebook or to another model. When the host changes the model, run a new round.

## Reporting

For each round: the units and how they were drawn (participant turns, pool size, seed), the codebook version, who coded and in which order (the seal), the thresholds and their source, per-code kappa and alpha with the interval, the codes that were not estimable, and what changed afterwards. When a second person also coded, report their agreement with the user separately and never merge it with the model's; `python3 "$SKILL_DIR/scripts/rz_agreement.py" table.csv` computes kappa and alpha from a table with one row per unit and one column per coder (for several codes per unit, one table per code with present or absent).
