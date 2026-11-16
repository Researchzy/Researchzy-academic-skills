# Selection: gates, assumptions, ratings, attacks, first study

The order is fixed: what blocks the idea, then what it rests on, then the ratings, then the attacks, then the first study. A rating cannot buy back a blocked gate.

## Gates

```sh
python3 "$SKILL_DIR/scripts/idea_ledger.py" gate i1 data=confirmed ethics=plausible \
  equipment=confirmed skills=plausible time=blocked:"needs two field seasons; one is left"
```

| Gate | The question |
|---|---|
| `data` | Do the data, samples, participants or sources exist, and can this researcher get them? |
| `ethics` | Can the work be done with the approvals, consent and licences it needs, and without harm it cannot justify? |
| `equipment` | Are the instruments, compute, lab or field access there? |
| `skills` | Can the researcher, or someone committed to the project, do each step? |
| `time` | Does the first result fit in the months the brief gives? |

| Status | Means | Needs |
|---|---|---|
| `confirmed` | The user said so, or a document read in this session shows it | Say which, as a note |
| `plausible` | Usual for this kind of work; nothing was checked | Nothing |
| `unknown` | Nobody in this conversation knows | A note on what would settle it |
| `blocked` | Known not to be available within the brief's constraints | The reason (the ledger requires it) and what would lift it |

Do not confirm a gate on the user's behalf. A blocked gate ends the idea as it stands: change the idea so the block no longer applies (`revise`), or reject it with the lifting of the block as the restart condition. All five gates must have a status before the ledger accepts a rating.

## Assumptions

List what must hold for the first result to mean anything. Two kinds: about the world (the effect exists, the mechanism operates in this setting) and about the method (the measure captures the thing, there are enough cases, the instrument is precise enough).

```sh
python3 "$SKILL_DIR/scripts/idea_ledger.py" assume i1 --text "Raters can tell the two item types apart" \
  --risk 4 --months 1 --test "Two raters code 60 items; agreement is computed"
```

| Risk | The assumption |
|---|---|
| 1 | Is established: shown repeatedly in this setting |
| 2 | Probably holds: shown in a nearby setting, with no reason to expect otherwise |
| 3 | Could go either way |
| 4 | Is more likely to fail than to hold: no direct evidence, and a reason for doubt |
| 5 | Is a long shot, or goes against existing evidence |

`--months` is the time until a result that tells whether the assumption holds, not the length of the project.

The riskiest assumption is the one with the highest risk; among equals, the one that takes longest to test. It should be testable early, which here means within the first quarter of the months in the brief. When it has risk 3 or more and takes longer, the ledger says so in `status`, in `recommend` and in the export, and you say so to the user. Then find a cheaper test of the same assumption that answers sooner, or reorder the plan so that this test is the first study, or keep the plan and state that the project's main risk cannot be retired before month N.

More than two assumptions at risk 4 or 5 means the idea needs several unlikely things to hold at once. Narrow it until at most two remain.

Scoring each assumption for its risk and for the time needed to test it, and testing the riskiest one first, follows Fischbach, M. A. (2024). Problem choice and decision trees in science and engineering. *Cell*, 187(8), 1828–1833. https://doi.org/10.1016/j.cell.2024.03.012

## Ratings

Five dimensions, each 0 to 3, each with a reason that points to something in the record: a gate, a closest work, an assumption, a field of the card.

```sh
python3 "$SKILL_DIR/scripts/idea_ledger.py" rate i1 value=2:"…" difference=2:"…" testability=3:"…" \
  feasibility=2:"…" information_gain=1:"…"
```

| Dimension | 0 | 1 | 2 | 3 |
|---|---|---|---|---|
| `value`: what changes once the question is answered | Nothing anyone does or believes | One more data point in a settled picture | What a defined group does or believes, if the result comes out one way | The same, whichever way the result comes out; or other work is waiting on the answer |
| `difference`: against the closest works | A closest work already answers it | Another sample or setting, with no reason to expect a different answer | A mechanism, a design or a setting that could change the answer, for a stated reason | Something the closest works name as open or get wrong, and the difference changes what can be concluded |
| `testability`: can a result go against it | No stated result would count against it | A refuting result is stated, but the rival predicts the same observations, or the measure does not exist yet | `if_true` and `if_rival` differ on something measurable with existing methods | The same, with thresholds fixed in advance and the test inside the first study |
| `feasibility`: against the gates and assumptions | A gate is blocked | No gate blocked, but two or more unknown, or the riskiest assumption cannot be tested early | At most one gate unknown, and the riskiest assumption can be tested early | Every gate confirmed, and the first study fits its budget with what the researcher already has |
| `information_gain`: what each outcome teaches | Only a positive result could be interpreted | A null result would rule out one way of doing it | Either outcome rules out a stated explanation | Either outcome changes what the researcher, or the field, does next |

Rules:

- When two levels both seem to fit, give the lower one unless the record holds a fact for the higher.
- `difference` is rated only once a closest work is recorded for the current version, and `feasibility` is 0 while a gate is blocked. The ledger enforces both.
- No total, no average, no weights, no "7 out of 15". A 0 is not balanced by a 3 elsewhere: say what the 0 means for the idea.
- Compare ideas dimension by dimension, in words.

## The adversarial pass

Write the objections of a critic who wants the idea dropped. At least two: one on `difference`, built on the nearest closest work, and one on the inference, built on the rival explanation. Other sources: the measure, the riskiest assumption, "what would anyone do with the answer".

```sh
python3 "$SKILL_DIR/scripts/idea_ledger.py" attack i1 --attack "…" --basis "…" --change "…" --residual "…"
```

| Field | Write |
|---|---|
| `attack` | The objection in one or two sentences, at its strongest |
| `basis` | What it rests on: a closest work, a logged search, a gate, an assumption. Write "reasoning only" when it rests on none |
| `change` | What was changed in the idea in answer, or "none" |
| `residual` | What is still true of the objection after the change, or "none" |

An objection answered only with better wording leaves its whole content as residual. When the change touches the question or the hypothesis, `revise` the card: that is a new version, and its novelty is checked again. Do not ask another model to judge the idea; the user decides.

## The minimum first study

The smallest piece of work whose result changes what the researcher does about the idea. Write the rules before any result exists.

```sh
python3 "$SKILL_DIR/scripts/idea_ledger.py" study i1 decision="…" support="…" refute="…" undetermined="…" \
  null_value="…" budget="…" first_action="…"
```

| Field | Write |
|---|---|
| `decision` | What will be decided once the result is in: go on, change the idea, stop |
| `support` | The result that counts as support, with its measure and threshold |
| `refute` | The result that counts against the hypothesis |
| `undetermined` | The results that settle nothing, and what would be done then |
| `null_value` | What a null result would be worth, and to whom |
| `budget` | A cap in time, and in money or compute where they matter. At the cap without a determined result, stop and plan again; do not extend |
| `first_action` | Something that can be done this week with what is at hand |

## What "test" means outside quantitative empirical work

| Kind of work | `if_true` | `refuted_by` | First study |
|---|---|---|---|
| Theory, formal models, mathematics | A consequence that can be derived, and a special case where known results are recovered | A counterexample, a step of the derivation that fails, or a known result it contradicts | The smallest non-trivial case, worked through; a search for a counterexample in the simplest setting |
| Qualitative and interpretive work | What would be seen in the cases if the account holds, including in a contrasting case | A case the account cannot absorb without changing, or a comparison case with the same outcome and without the proposed process | Two or three cases chosen to differ on the proposed process, one of them expected to go against it |
| Methods and tools | Performance on a stated task against the strongest simple alternative | The simple alternative does as well, within a margin fixed in advance | The smallest task on which the difference should show |

The gates apply unchanged; for theory, `data` covers access to the prior results and proofs the work builds on.
