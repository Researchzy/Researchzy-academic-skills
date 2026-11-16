# Assessing studies

## Before judging

- One entry per study; in it, one result per outcome the review assesses. Judge results, not papers: blinding can matter for a self-reported outcome and not for a weight read from a scale, and missing data can differ between time points.
- Write the target first: the effect of interest (for a trial, of assignment to the intervention or of adhering to it; the tool names its own options) and the numerical result (outcome, time point, analysis). Write it before you look at which group did better, because knowing the direction colours the reading.
- Read the full text: methods, results, flow diagram, tables, supplementary material, and the protocol or registration when the tool asks about planned outcomes or analyses. An abstract supports almost no judgement.

## Answering and judging

- Answer every signalling question in the tool's vocabulary: "probably yes" or "probably no" when the paper implies the answer without stating it, the tool's no-information answer when it says nothing.
- No information is not the same as not done. A paper silent on how allocation was concealed gives no information about it: write "not reported", and "not done" only when the paper says so.
- Judge the domain from its answers under the tool's guidance. With a registered mapping, `check` compares the two.
- Reporting is not bias. An item the paper omits is no information about that item; the question is what the omission leaves unknown about this result. A number you could not extract goes in `note`, not into the judgement.
- Do not let the size, direction or significance of the effect, the journal, the funder or the authors' standing move a judgement, unless the tool asks about one of them.

## Quotes and locators

- Copy each quote word for word from the saved text: at least five words, from one passage. Do not repair the wording, translate it, or join distant passages with an ellipsis.
- Quote the passage that answers the question, not one that only mentions its keyword.
- Give a locator a reader can follow: "p. 4, Methods, Randomisation", "Table 2", "Supplement S1, p. 3". Printed journal pages can differ from the pages of the file; `check` reports the page of the text file on which it found the quote.
- A quote from a protocol or registration is found only when that text is saved as one of the study's texts (kind `protocol` or `registration`). Name the text with `text` when the same words could occur in several.
- For no information, `searched` lists every place you looked: sections, tables, supplement, protocol, registration.
- Known limit: the match tolerates extraction noise between words, so a quote that lacks "not" or a digit can still be found. Reread every quote that turns on a negation or a number.

## assessments.json

```json
{"assessments": [{
  "study": "alder2021",
  "tool": "demo",
  "texts": [{"path": "texts/alder2021.txt", "kind": "full_text", "sha256": "…"},
            {"path": "texts/alder2021-registration.txt", "kind": "registration", "sha256": "…"}],
  "results": [{
    "outcome": "weight",
    "result": "body weight at 12 weeks, kg, all randomised participants",
    "target": "effect of assignment to the intervention",
    "assessor": "model", "checked_by": "", "weight": 40.0,
    "domains": {
      "D1": {"answers": {"1a": "Y", "1b": "NI"}, "judgement": "some",
             "support": [{"quote": "five or more words copied from the text", "locator": "p. 2, Methods"}],
             "no_information": {"searched": "Methods, supplementary appendix, trial registration"},
             "note": ""},
      "D2": {"answers": {"2a": "Y"}, "judgement": "low",
             "support": [{"quote": "…", "locator": "p. 3, Figure 1"}]}},
    "overall": {"judgement": "some", "reason": ""}}]}]}
```

| Field | Content |
|---|---|
| `study` | The study's id, used once |
| `tool` | The registered tool's `id`; may be left out when only one tool is registered |
| `texts` | Each saved text: `path` (relative to `risk-of-bias/`), `kind` (`full_text`, `abstract`, `protocol`, `registration`, `supplement`, `other`) and `sha256` from `rob_check.py hash` |
| `outcome` | The outcome's id; `sof.json` uses the same id |
| `result`, `target` | The numerical result assessed, and the effect of interest |
| `assessor`, `checked_by` | `model` for your assessments; the reviewer's name once a person has checked the entry |
| `weight` | Optional: the study's weight in the pooled analysis of this outcome, for the CSV and `rob_plot.py --weighted` |
| `domains` | For every domain of the tool: `answers`, `judgement`, `support` (quotes with `locator`, optional `text`), `no_information.searched`, `note`, and `departs_from_mapping` only where the tool allows departures |
| `overall` | `judgement`, and `reason` when the rule asks for one; left out when the tool's rule is `none` |

## What check reports, and what to do

| Check | On `fail` |
|---|---|
| `tool` | Complete `tool.json` from the tool's source |
| `tool_file` | The tool file changed or was never hashed: register the tool again from the file as it is now, and recheck every judgement if the version changed |
| `text` | A text is missing, unhashed, changed or too short. If it was re-extracted on purpose, record the new hash and reread the judgements that rest on it. A text under 400 words that is all there is gets kind `abstract` |
| `complete` | Add the missing target, assessor, judgement or answer, or use the tool's vocabulary |
| `quote` | `PARTIAL`: reread the passage and copy it again. `ABSENT`: find the passage, or change the judgement. Never edit the text file |
| `support` | Add a quote, or `no_information.searched` |
| `overall` | Correct the overall judgement, or give the reason the rule asks for |
| `mapping` | The judgement contradicts the registered mapping: correct the answers or the judgement. If the mapping was transcribed wrongly, correct it from the document. When no rule matches, the mapping is incomplete |
| `departure` | Not a failure: listed for the user's review |

## A second assessor

When a person assesses the same results independently, keep their entries in a separate file, compare them domain by domain, settle disagreements by discussion, and record the agreed entry with that person in `checked_by`. Report agreement for each tool separately, never one figure across tools.
