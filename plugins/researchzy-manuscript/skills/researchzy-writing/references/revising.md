# Revising without changing the meaning

A revision improves how a text reads. It does not change what the text claims. The author has checked the claims of the old text, not of yours, so every edit that could change a claim is shown to them.

## Levels of edit

| Level | What changes | What stays |
|---|---|---|
| 1. Proofread | spelling, grammar, punctuation, one spelling convention, one form of each term, abbreviation definitions | every sentence, in its place |
| 2. Light edit (default) | word choice, wordiness, sentence length; sentences split or merged inside a paragraph | every claim, number, citation and hedge; the order of paragraphs |
| 3. Restructure | the order of sentences and paragraphs, topic sentences, transitions | every claim, number and citation, though they may move |
| 4. Content | claims added, removed or changed | — this is not a revision: go back to the claim ledger |

Use level 2 unless the user names another. Say which level you used. Level 3 needs the user's request, because moved sentences cannot be compared one to one.

## What levels 1 to 3 never change

- A number, its unit, its precision, its sign, or the comparison sign before it.
- Which sentence a citation is attached to.
- A hedge (may, might, suggests, appears, approximately, likely) or its absence.
- A negation, or the direction of a comparison (higher, lower, more, fewer).
- The name of a defined term or abbreviation.
- The order in which results are reported.
- Nothing is added: no new fact, example, citation, reason or conclusion, however plausible.

## Procedure

1. Keep the original. Write the revision to a new file; if the author wants their own file edited, copy it to `writing/before/` first.
2. Edit at the agreed level.
3. Run `manuscript_check.py diff BEFORE AFTER --strict --out writing` and read `writing/revision-check.md`.
4. Undo what the table below says to undo. Run the comparison again until what is left is intended.
5. Give the user the revised text and the list of meaning-risk edits.

## Reading `revision-check.md`

| Section of the report | What it means | Do |
|---|---|---|
| Numbers: changed in a sentence | a value left a sentence or entered it | Restore the original value. Keep the change only if the author asked for it; then list it. |
| Numbers: same values, other order | values may have traded places between quantities | Check each value against the original sentence; restore if any moved to another quantity. |
| Numbers: disappeared, appeared | a value is in the text less or more often than before | A disappeared value was in a sentence you removed or rewrote: restore it. An appeared value is new content: remove it unless it is in the author's materials. |
| Citations: dropped, added | a key is cited less or more often | Restore a dropped citation. An added one needs a ledger row. |
| Citations: moved | the key is still there but in another sentence | Put it back with the claim it supported. |
| Hedges removed, intensifiers added | the sentence now claims more | Restore the original strength, unless the evidence grade in the ledger supports the stronger wording; then list it. |
| Negation changed, direction changed | the sentence may say the opposite | Read both sentences. "Did not differ" rewritten as "was similar" is harmless; anything else is restored. |
| Sentences with no counterpart | the script could not pair them, so it did not compare them | Compare these by eye and list what changed. They are not checked, not clean. |

With `--strict` the command exits 1 while any number or citation differs. That is the gate for levels 1 and 2. At level 3, moved citations are expected: read the list instead.

The script compares numerals, citation keys and a fixed list of words. It does not see a number written as a word, a changed unit, or a claim that changed while its words stayed on the list. Read your own edits as well.

## The list for the author

After the revised text, give every remaining meaning-risk edit as a pair, with one line on why you made it:

```markdown
### Edits that could change meaning (3)

1. Results, paragraph 2 — hedge removed
   Before: These data suggest that the effect may persist at 12 months.
   After:  The effect persisted at 12 months.
   Why: Table 3 reports the 12-month estimate directly (ledger C7, own-result). Revert if you prefer the hedge.
2. …
```

An empty list is stated as such: "No edit changed a number, a citation, a hedge, a negation or a direction; N sentences were rewritten too far for the script to compare and were checked by reading."

## When the problem is the content

Stop polishing and say so when any of these is true. Better wording would hide the problem.

| What you see | What to tell the author |
|---|---|
| A paragraph has no claim: it describes activity, not a finding | Which finding it should state, or that it can go |
| A claim has no evidence in the materials | The claim, and `[Evidence needed: …]` or `[Citation needed: …]` at its place |
| The conclusion says more than Results | The sentence, the result it rests on, and the wording the design allows |
| Methods omits what a reader needs to repeat the analysis | The missing item, as `[Author input needed: …]` |
| The order of the argument is wrong | That the outline needs changing, not the sentences: go back to planning |
| Two places give different values for one quantity | Both values and their locations; ask which is right |

Offer to continue once the content is settled. Do not rewrite around the gap.

## Machine-sounding patterns: report only

Some readers take the patterns below as a sign of text written without attention. List where they occur and offer a plainer version; change them only at level 2 or above, and only where the meaning is untouched.

- An opening sentence that announces importance without saying anything ("plays a crucial role in").
- The same transition word opening several sentences in a row.
- Groups of three by habit, where the content has two items or four.
- Intensifiers and praise with no number behind them (highly, remarkably, novel, robust).
- A closing sentence that restates the paragraph.
- Announcing instead of saying ("It is worth noting that", "It should be emphasised that").
- Stacked hedges on one claim ("may potentially suggest").
- Every sentence of a paragraph at the same length and rhythm.
- A long dash or a colon in most sentences.
- A conclusion that would fit any paper in the field.

Human writers produce all of these too. This list makes no statement about who or what wrote a text, and removing the patterns promises nothing about the verdict of any AI detector. Do not tell the user otherwise.
