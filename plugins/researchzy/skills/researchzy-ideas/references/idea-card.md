# The idea card

One card per idea, kept in the ledger. A card states the idea so that a result could go against it.

## Fields

| Key | Write | Too weak |
|---|---|---|
| `title` | Five to eight words that tell this idea from the others | "Idea 1" |
| `question` | One question, with its population or system and its comparison or outcome | A topic. Two questions joined by "and" |
| `claim_type` | One type from the table below: the strongest claim the planned evidence could support | The type the researcher hopes for |
| `hypothesis` | A statement that could be false: what differs, in which direction, under what condition, through what | "X affects Y". "X plays a role in Y" |
| `if_true` | What will be observed if the hypothesis holds: the measure and the pattern | "The results will support the hypothesis" |
| `if_rival` | The main rival explanation, by name, and what will be observed if it is right instead | "Results may differ". A rival that predicts the same pattern |
| `refuted_by` | The result that would make the researcher give the hypothesis up, with its measure and threshold | "No effect is found", with no size or interval |
| `undetermined_if` | What would leave the question open: too few cases, a manipulation that did not take, a measure that did not work | Left empty |
| `data` | The data, materials, instruments, access and skills the test needs, and which of them the researcher already has | "Public data" |
| `first_test` | The smallest piece of work that could go against the hypothesis | The whole project |
| `origin` | Where the idea came from: the review's gap with its search ids, the Paper Card idea, the operator, or "the user's own" | Left empty |

`question`, `claim_type` and `hypothesis` are needed to add a card. `refuted_by` is needed before an idea can be recommended. The ledger lists the other empty fields as open points.

## Claim types

| Type | It asserts | Evidence it needs at least | Overreach to watch for |
|---|---|---|---|
| `descriptive` | How much, how often, what exists | A defined population and a measure that captures the thing | A pattern read as an explanation |
| `associational` | Two things vary together | Both measured in the same units, with the comparison stated | Causal verbs: drives, leads to, improves |
| `predictive` | One thing forecasts another in new cases | Cases held out, or later in time | The predictor presented as the cause |
| `causal` | Changing one thing changes another | An intervention, or a design that rules out the main confounders by name | "Controlling for" with nothing named |
| `mechanistic` | Through what process the cause acts | Evidence on the step in between, not only on the two ends | A story with no measured step |

Choose the type from the evidence planned, then word the card to match: a card typed `associational` does not say "effect". For theory and for qualitative work, type the claim by what it asserts about its object: a property that holds for all cases of a formal object is `descriptive`; a model or an account of how a process unfolds is `mechanistic`. [Selection](selection.md) says what counts as a test there.

## Rules

- `if_true` and `if_rival` must differ on at least one thing that can be observed. When both predict the same observations, the study cannot tell them apart: choose another observable, another design or another rival.
- `refuted_by` must be a result that could really occur. "Refuted if the effect is exactly zero" is not one.
- Write what will be measured. Replace each abstract noun (performance, wellbeing, robustness, engagement) with its measure.
- One card, one hypothesis. Two hypotheses are two cards.
- Take nothing in a card from memory of a paper. A fact about prior work in `origin` or `if_rival` comes from the evidence base, with the paper named.

## Sharpening a vague hypothesis

Answer these in order and rewrite the hypothesis after each. Where the answer is the researcher's to give and they did not give it, choose the most testable reading, write it into the card, and list it in the report as your assumption.

1. What varies, and what is compared with what?
2. In whom or in what, and under which conditions?
3. In which direction, and how large a difference would matter?
4. Through what process? If nobody can say, lower the claim type by one rung.
5. What else would produce the same pattern? That is the rival.
6. What result would make you give it up? That is `refuted_by`.

## Evaluating an idea the user already has

Card it first in the user's own terms, as version 1, even when it is vague. Each improvement after that is a `revise`. The record then shows what the user proposed and what you changed, and the novelty check is run on the wording that will be recommended.

## Adding and changing cards

`card.json` holds one card or a list of cards:

```json
{
  "title": "Interleaved homework and method choice",
  "question": "Does interleaving homework problems across topics raise first-year calculus scores on problems where the student must choose the method?",
  "claim_type": "causal",
  "hypothesis": "Interleaved homework raises scores on method-choice problems more than on problems where the method is given.",
  "if_true": "Interleaved sections score higher on method-choice items; the gap on method-given items is near zero.",
  "if_rival": "Time on task: if the gain comes from extra practice, both item types improve alike, and the gain shrinks when homework time is held equal.",
  "refuted_by": "No difference on method-choice items, with an interval that excludes a gain of 0.2 SD.",
  "undetermined_if": "Fewer than 80% of students in the interleaved sections complete the homework.",
  "data": "Two course sections per condition, item-level exam scores, homework logs. The researcher teaches the course; approval to use course data is not yet given.",
  "first_test": "Two raters code last year's exam items as method-choice or method-given, to see whether the two types can be told apart.",
  "origin": "Gap 2 of literature-review/review.md (searches s4, s9)."
}
```

The card above is an invented illustration, not a finding.

```sh
python3 "$SKILL_DIR/scripts/idea_ledger.py" add card.json
python3 "$SKILL_DIR/scripts/idea_ledger.py" revise i1 --undetermined-if "…"
python3 "$SKILL_DIR/scripts/idea_ledger.py" revise i1 --hypothesis "…" --note "narrowed after the second attack"
```

## Versions

A change to `question` or `hypothesis` makes a new version of the idea. The ledger then sets its novelty back to `unsearched`, sets aside the closest works and drops the `difference` rating, because all three were judged against the earlier wording. A recommended or rejected idea becomes open again. Changes to the other fields keep the version, and so do changes of spacing or capitals.

Settle the wording before the novelty check. After a new version, run the logged queries again where they still fit, add the queries the new wording calls for, and review the other four ratings by hand.
