# Registering the tool

The skill carries no tool. Each review registers one in `risk-of-bias/tool.json`, from the tool's own file or official page. Tools get new versions and some licences do not allow their text to be copied, so the registration records exactly what was read, where and when.

## Choosing a tool by design

Offer the user the families that fit the designs of the included studies, and let them confirm. Name no version yourself: before registering, find on the tool's official site (its developers' page, or the journal article that published it) which version is current, and whether a variant exists for the design at hand, such as cluster or crossover trials. Tell the user: "Tools get new versions; the official site decides which one is current."

| Included studies | Tool families to offer |
|---|---|
| Randomised trials | The Cochrane risk-of-bias tool for randomised trials (RoB 2) |
| Non-randomised studies of an intervention | ROBINS-I |
| Non-randomised studies of an exposure | ROBINS-E |
| Diagnostic test accuracy | QUADAS |
| Prognostic factor studies | QUIPS |
| Prediction model studies | PROBAST |
| Other designs, or the protocol names a tool | The tool the review protocol names; otherwise ask |

Use one tool per design. Studies assessed with different tools are never merged into one judgement, table or plot; `rob_check.py` keeps them apart.

## Getting the tool's text

1. A file the user gives: the official form, guidance document or cribsheet. Copy it into `risk-of-bias/tool-source/`.
2. Otherwise the official page, read in this session. Save what you read (the page as text, or the form you downloaded from it) in `risk-of-bias/tool-source/`, so that the registration can be compared with it later. A registration with only a web address is reported `not_checked` against its source.
3. Never a tool from memory, from a summary on another site, or from a copy found online that you have not confirmed to be the current version.

If neither 1 nor 2 works, stop and tell the user what is needed.

The tool's wording stays in `tool-source/` and `tool.json`, in the user's working directory. Exported tables and plots carry question ids and judgement labels only. Ask the user before putting item wording into anything that will be shared or published: many tool licences restrict it.

## tool.json

One tool as below, or several as `{"tools": [...]}`; with several, each study in `assessments.json` names its `tool`. The example is a fictional tool that shows the format:

```json
{"id": "demo", "name": "Demo appraisal tool (fictional)", "version": "0.1",
 "designs": ["parallel randomised trials"],
 "source": {"file": "tool-source/demo-guidance.pdf", "sha256": "…", "url": "https://…", "read": "2026-11-13"},
 "transcribed_by": "model", "checked_by": "",
 "answers": ["Y", "PY", "PN", "N", "NI", "NA"],
 "judgements": [{"id": "low", "label": "Low"}, {"id": "some", "label": "Some concerns"},
                {"id": "high", "label": "High"}, {"id": "ni", "label": "No information", "no_information": true}],
 "domains": [{"id": "D1", "name": "Assignment", "questions": ["1a", "1b"]},
             {"id": "D2", "name": "Missing outcome data", "questions": ["2a"]}],
 "overall": {"rule": "worst_or_higher", "locator": "guidance p. 9"},
 "mapping": {"D1": {"locator": "guidance p. 12, figure 3", "rules": ["see below"]}}}
```

| Field | Content |
|---|---|
| `id` | A short id, used in file names and as `tool` in `assessments.json` |
| `name`, `version` | Exactly as printed in the tool's file or on its page |
| `designs` | The studies it is used for in this review |
| `source.file`, `source.sha256` | The saved copy, relative to `risk-of-bias/`, and its hash from `rob_check.py hash` |
| `source.url` | The official page, when that is where it was read |
| `source.read` | The date it was read, `YYYY-MM-DD` |
| `transcribed_by`, `checked_by` | Who wrote this registration, and who checked it against the source |
| `answers` | The signalling-question answers, spelled as the tool spells them |
| `judgements` | The domain judgements, best first; the overall judgement uses the same list |
| `domains` | `id` and `name` as the tool numbers and names them, with their question ids. A question may be `{"id": "1a", "text": "…"}`; its text stays in the user's directory |
| `overall` | The rule type, and the locator where the tool states it |
| `mapping` | Optional: answers to judgements, below |

## Vocabulary rules

- Copy the labels. Do not rename, merge or add levels: a tool with three levels has no "moderate".
- List the ranked judgements from best to worst. The order is only an order, never a score.
- "No information", "unclear" and "insufficient information" are not a middle level. Register them with `"no_information": true`: the plots give them their own colour and symbol, and the overall rule leaves them out of the ranking.
- A signalling answer is not a judgement. A "no" may flag possible bias that the domain judgement then weighs; the tool's guidance says how.

## Overall rule types

| `rule` | Use when the tool says | `check` requires |
|---|---|---|
| `worst` | The overall judgement is the worst domain judgement | Equal to the worst ranked domain |
| `worst_or_higher` | At least the worst domain, and the assessor may judge it worse, for example when several domains each raise some concern | Not better than the worst ranked domain; worse only with a `reason` |
| `none` | The tool has no overall judgement | No overall judgement |

Read the rule in the tool's own text and give its page in `overall.locator`. An overall judgement of no information is accepted only when a domain is judged no information and a reason is given.

## Mapping answers to judgements (optional)

When the tool's guidance gives an algorithm, a flow chart or table that turns the answers of a domain into its judgement, transcribe it rule by rule, with the page it is on. A fictional example:

```json
"mapping": {"D1": {"locator": "guidance p. 12, figure 3", "rules": [
  {"if": {"1b": ["N", "PN"]}, "then": "high"},
  {"if": {"1a": ["Y", "PY"], "1b": ["Y", "PY"]}, "then": "low"},
  {"if": {}, "then": "some"}]}}
```

- Rules are tried in order; the first whose conditions all hold decides. `"if": {}` matches any answers: put it last.
- `then` is one judgement, or a list when the guidance leaves the choice among them to the assessor.
- Transcribe only what the document states, never a rule you infer. Ask the user to check the mapping against the document when they can, and record them in `checked_by`.
- A domain without a mapping is checked for support only; its judgement against its answers is `not_checked`.
- Some tools let the assessor depart from the algorithm with a reason. Only for those, write `departs_from_mapping` in the assessment; `check` lists every departure for the user.
