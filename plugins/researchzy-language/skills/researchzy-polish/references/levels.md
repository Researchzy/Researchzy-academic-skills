# Levels, reasons and the author's questions

A polish improves how a text reads. The author checked the claims of their own text, not of yours, so the level fixes in advance how far the wording may move, and the log shows every move.

## The three levels

| | light | medium (default) | heavy |
|---|---|---|---|
| Sentences | each stays one sentence, in place | may be rewritten, split in two or merged | as medium, and reordered inside their paragraph |
| Words | single words and short phrases | any wording that keeps each proposition | as medium |
| Reasons allowed | spelling, grammar, article, preposition, agreement, punctuation, word choice, terminology, tense, format | the light reasons, and concision, clarity, transition | all, including reorder |
| The script treats as an error | a split, merge, move or sentence it cannot pair; a changed paragraph count | a moved sentence | a sentence moved to another paragraph |
| Share of a paragraph's words changed before it warns (a convention; `--max-footprint` changes it) | 20% | 50% | 70% |

Choose the lowest level that does the job. A heavy edit is for a paragraph whose order hides its point; it is never a licence to restructure the argument, which is `researchzy-writing`'s work.

## What no level changes

- A number: its value, precision, sign, unit, the inequality before it and the direction word bound to a percentage ("12% lower"). A number word is a number: "three" may become "3", never "four".
- A citation, and the sentence it supports. Splitting a cited sentence or merging two must leave each citation beside the claim it supported.
- `\ref`, `\label`, `\cite` keys, file names, links, formulas and code, in their order.
- Every protected term, as often as before.
- Each sentence's claim words: see [claim strength](claim-strength.md).
- The paragraphs: none added, removed or moved.
- Nothing is added: no fact, example, reason, citation or conclusion, however plausible.

## When a sentence stays as it is

Return a sentence unchanged when it is grammatical, says one thing clearly, and uses the terms of the rest of the paper. Do not rewrite for variety, for a preferred rhythm or to match neighbouring sentences. An unchanged sentence needs no log entry and carries no risk.

## The reasons

| Reason | Use for |
|---|---|
| spelling | a misspelling, or the agreed US or UK spelling |
| grammar | tense form, verb form, word order, a missing or doubled word |
| article | a, an, the, or none (never before a cause-like noun: see the claim reference) |
| preposition | the preposition a word takes ("differ from", "consistent with") |
| agreement | subject and verb, noun and pronoun, singular and plural |
| punctuation | commas, colons, hyphens, quotation marks |
| word choice | a more precise or more usual word with the same meaning and strength |
| terminology | one form for one term throughout ("follow-up", not also "followup") |
| tense | a tense that is wrong for its place, such as a method in the present; never a result moved from past to present |
| format | how a number, unit or abbreviation is written, when the value stays the same ("P<0.05" to "P < 0.05") |
| concision | words removed that carry nothing: "in order to" to "to", "it is important to note that" deleted |
| clarity | a sentence rebuilt so that its subject, verb and object are easy to find |
| transition | a linking word added, removed or replaced inside its own class (an addition for an addition, a contrast for a contrast) |
| reorder | a sentence moved inside its paragraph |

## `changes.json`

```json
{"level": "medium",
 "changes": [
  {"id": "c1", "location": "¶2.1", "before": "the sleep quality of nurses who works night shifts were worse",
   "after": "the sleep quality of nurses who work night shifts was worse", "reason": "agreement"},
  {"id": "c2", "location": "¶3.2", "before": "Adherence were high, 41 of 48 nurses",
   "after": "Adherence was high: 41 of 48 nurses", "reason": ["agreement", "punctuation"]}]}
```

- `location` is the paragraph and sentence as the survey and the check report write them (`¶2.1`).
- `before` and `after` are copied exactly from the two files, with enough words to occur once (four or more). One entry may cover a whole sentence or one edit in it; a sentence with several kinds of edit gets several reasons or several entries.
- A moved sentence gets an entry whose `before` and `after` are that sentence and whose reasons include `reorder`.
- An edit you made and then undid has no entry.

## `queries.md`

Write a question instead of an edit when:

| You see | Ask |
|---|---|
| A claim beyond its evidence: "better", "improved" or "a trend" for a difference that was not significant | Whether to report the difference without the comparison, and give the wording that would do so |
| "significant" with no test in reach | Whether a test supports it, or the everyday sense was meant |
| Two values for one quantity, or a number that disagrees with its fraction | Which value is right; change neither |
| A term written two ways in about equal numbers | Whether these are one concept or two |
| Stacked hedges ("may possibly suggest") | Whether the doubled uncertainty is meant; keep it until the author answers |
| A sentence whose meaning cannot be told (who did what, which group is meant) | What it means, with the two readings |
| A sentence that needs content: a missing number, method or citation | Use the house placeholders: `[Evidence needed: …]`, `[Citation needed: …]`, `[Author input needed: …]` |

Each question: its number, the place, the sentence as it stands, what the doubt is, and at most two options. The sentence itself stays as the author wrote it.

## Reading the reports

| Finding in `polish-check.md` | Do |
|---|---|
| number changed, appeared, disappeared, unit changed, values traded places | Restore the author's numbers; a format change that the script still flags is undone too |
| citation dropped, added or moved; cited sentence split or merged | Put each citation back beside its claim |
| key, formula or order changed | Restore it exactly |
| protected term changed | Restore each occurrence |
| claim strength or any other claim word changed | Restore the original wording, or keep it and ask the author ([claim strength](claim-strength.md)) |
| sentence moved, split or merged, not compared (by level) | Undo the move, or agree a higher level with the author first |
| new term | Remove added content; if the term is a fair rendering (an abbreviation defined earlier), say why it stays |
| large footprint | Reread the paragraph against the original; cut back to the level |

In `log-check.md`, an entry whose text is not found was copied wrongly: copy it again from the files. A change without an entry needs one, or the edit is undone.
