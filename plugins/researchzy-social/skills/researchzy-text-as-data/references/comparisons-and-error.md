# Comparisons and measurement error

The labelled variable is the measure. A dictionary and a topic model are comparisons: they are transparent, cheap and repeatable, and where they disagree with the labels they point at texts worth reading. Neither replaces the validation rounds.

## A dictionary

The user supplies `terms.csv` with the columns `category,term`: their own list, or one published with a paper. Record its source and the date in `protocol.json` under `dictionary` (`file`, `source`, `date`). With Researchzy connected, `search_papers` (keywords in titles and abstracts) finds papers that build a dictionary or measure the construct, and `get_paper_files` lets you read how the list was built and validated; the terms themselves still come from a file the user supplies. Never write a published dictionary from memory.

```sh
python3 "$SKILL_DIR/scripts/tad_compare.py" dictionary text-as-data/terms.csv --window 4 --kwic 20 --seed 1
```

| Part | What it does |
|---|---|
| Matching | Terms in Latin letters match whole words, ignoring case; terms in Chinese, Japanese or Korean script match anywhere in the text |
| Negation | A hit with a negator among the `--window` tokens before it, in its clause, counts as negated, not as a hit (a CJK character is one token). The default negators (不, 没, 未, 毫无, 并非, not, no, never, without, n't…) are a convention; `--negators FILE` replaces them, one per line |
| `scores.csv` | Hits and negated hits per unit and category |
| Coverage | Units with at least one hit, overall and per group, in `dictionary.md` |
| `kwic.csv` | Per category, a seeded sample of hits with 30 characters on each side and an empty `valid` column |
| Against the labels | For a category named like a class: of the units with a hit, how many the user gave that class; of the user's units of that class, how many have a hit (scored rounds only) |

The user reads `kwic.csv` and marks each hit `yes` or `no`: the share of valid hits is the dictionary's precision in context. Coverage alone proves nothing. A term that the context sample shows to mean something else is removed in a new version of the file, with the reason, and the counts are run again.

## Topic models

```sh
python3 "$SKILL_DIR/scripts/tad_compare.py" topics --k 4,5,6 --seeds 1,2,3 --method lda
```

- **Tokens.** Runs of Chinese characters become character bigrams; Latin words are lower-cased without English stop words. When the user supplies segmented text (words separated by spaces) in a column, pass `--segmented COLUMN`. Rare and very common tokens are dropped (`--min-df 2`, `--max-df 0.5`, conventions).
- **Stability.** Each seed's topics are matched to the first seed's by the share of top words they share. A topic's stability is its smallest share across the other seeds; below `--stable-min` (0.5, a convention) it is unstable. One run is not a result: an unstable topic is reported as such, never as a finding.
- **Coherence.** UMass coherence, the mean over pairs of top words of log((D(wi, wj) + 1) / D(wj)), counted in units. Values nearer zero mean top words that occur together more. Coherence is one input for choosing K, never the only one.
- **Reading.** `k<K>-reading.md` lists each topic's top words and its representative units in full. The user reads them and fills `text-as-data/topics/reading-log.csv`: `k,topic,units_read,name,read_by,date`. Run `topics` again with `--reading-log`: a name is written only when its row lists every representative unit as read, with a reader and a date. Names from top words alone are refused.

Write topics as "a topic whose top words are … and whose representative units concern …", not as a measured share of a construct.

## Measurement error

```sh
python3 "$SKILL_DIR/scripts/tad_ledger.py" correct --boot 1000
```

The passed round gives, for each class the user chose, the share of its units the model put in each class: the misclassification matrix M. The run's raw shares are what M does to the true shares, so `correct` solves raw = Mᵀ × corrected. In multi-label mode each class is corrected on its own, present or absent. The intervals come from resampling the round's units with the round's seed while the run's counts stay fixed, so they show the round's uncertainty only.

- A corrected share outside 0 to 1, or a very wide interval, means the round was too small for that class or group: say so, and draw a larger stratified round if the share matters.
- A class without units in the round cannot be corrected: the note says which.
- The correction assumes the round's error rates hold in the whole run. That holds for a random or proportionally stratified draw from the same corpus, under the frozen version.

## Errors by group

`error-note.md` gives, per group of each declared column, "Found" (units of a class the model found, of those the user gave it) and "Wrong" (units the model gave a class that the user gave another, of those it gave it), and the corrected shares per group. Leads name the largest differences between groups, with their counts. When error rates differ by group, the errors are differential: group comparisons of the class, and regressions with the group as a predictor, can be biased in either direction. The note explains this for the class as an outcome and as a predictor.

## Handing on

Give `researchzy-statistics` (plugin `researchzy-manuscript`, when installed) `run.csv`, `error-note.md`, `correct.json` and the passed round. It analyses the variable; it does not correct a regression for misclassification. Estimators that combine the model's labels on all units with the user's labels on the validation units exist; they are not computed here. Name them in the limitations as a step the user can take, and report the raw and the corrected shares side by side whatever their difference.
