# Author notes

Use this file when the user supplies informal author notes, short change notes, or notes in a
language other than English.

## Default behavior

- Accept reviewer summaries, author notes, manuscript-change notes, and mixed-language inputs.
- Draft the final point-by-point response letter in English unless the user explicitly asks for
  another language.
- Keep a short author confirmation section for unresolved author actions when it helps the author
  act. Write it in the user's language.
- Translate intent, not literal wording.
- Convert vague notes into concrete response evidence requirements.

## Common note conversions

| Author note | Problem | Better handling |
|---|---|---|
| `We already changed it` | Too vague | Ask what changed, where it appears, and whether revised text is available |
| `Revised as the reviewer asked` | No action mapping | Convert to `AUTHOR_INPUT_NEEDED` until action and location are known |
| `We added an experiment` | Missing evidence | Request experiment name, conditions, replicate/sample details, result summary, and figure/table location |
| `We added an analysis` | Missing analysis detail | Request analysis method, data source, key result, statistical output, and manuscript location |
| `This point is not important` | Defensive and unsupported | Reframe as scope, evidence, or claim-boundary reasoning if scientifically justified |
| `No time to do it` | High-risk excuse | Replace with study-design or scope boundary only if true; otherwise flag risk |
| `The reviewer misunderstood` | Accusatory | Reframe as manuscript clarity issue and add clarification |
| `See the main text` | Not traceable | Require section, page, line, figure, table, or supplement |
| `We think it is enough` | Unsupported sufficiency claim | Explain what evidence addresses the concern or mark remaining limitation |

## Author confirmation section

Use concise action notes, in the user's language:

```text
Author confirmation notes
- R1.1: Add the main result of the validation analysis, the sample size or dataset size, and the main-text location of Fig. 5.
- R1.2: Confirm the statistical test, the unit of replication, the sample size, and the multiple-comparison correction.
- R2.1: The animal validation cannot be claimed as done; reframe it as a scope statement plus a Discussion limitation.
```

## Drafting pattern for non-English notes

When the user supplies notes in another language:

1. Preserve reviewer comments in their supplied language unless asked to translate.
2. Build the tracker using English action labels.
3. Draft the response letter in polished English.
4. Add author confirmation notes only for decisions, missing facts, and high-risk issues.

## Tone correction examples

Author note:

```text
The reviewer did not understand our method.
```

Response stance:

```text
We agree that the original Methods description did not make this distinction sufficiently clear.
We have revised the Methods to clarify [specific distinction and location].
```

Author note:

```text
This experiment is beyond our capacity.
```

Response stance:

```text
We agree that this experiment would provide an additional test of [claim]. However, it would require
[new cohort/system/longitudinal design], which is outside the scope of the present study. We have
therefore softened the claim and added a limitation in [location].
```
