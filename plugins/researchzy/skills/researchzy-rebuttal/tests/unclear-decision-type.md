# Test: unclear revision decision type

## Input

```text
Reviewer 1:
1. Please clarify the validation design.

Reviewer 2:
1. The Discussion should better explain the study limitations.

Please prepare the point-by-point responses and the manuscript revision plan.
```

## Expected behavior

- Recognize that the requested complete response and manuscript plan need a package-level strategy, but the editorial decision type is missing.
- Ask one concise question before drafting: whether this is `Major Revision` or `Minor Revision`.
- Ask the question in the user's language.
- Pause decision-dependent package strategy and complete response-letter drafting until the user answers or supplies the decision letter; continue independent inspection of supplied comments and missing evidence.

## Forbidden behavior

- Do not infer Major Revision from the validation comment.
- Do not infer Minor Revision from the small number of visible comments.
- Do not produce a generic point-by-point response that treats both decision types as equivalent.
- Do not ask again if a subsequently supplied editor letter explicitly states the decision type.

## Pass/fail checklist

- [ ] The decision-type question is asked before substantive drafting.
- [ ] No revision type is guessed.
- [ ] No Major/Minor strategy is selected prematurely.
- [ ] The user is invited to provide the decision letter if its wording is unclear.
