# The approach

The approach is chosen before the first code is written, because it decides what a code is, whether a second coder's agreement means anything, and who settles the themes. The user chooses; you explain the consequences. Record the choice in `qualitative/protocol.json`, and what it implies in `qualitative/approach.md`.

## Three approaches

| | Reflexive thematic analysis | Codebook thematic analysis | Grounded theory |
|---|---|---|---|
| A code is | The researcher's reading of a passage, expected to change as the reading deepens | A category with a definition, inclusion and exclusion rules, applied to passages | First open codes close to the words, then relations between categories (axial), then a core category (selective) |
| The codebook | A record of how the codes developed | Fixed at each version; a change starts a new version | Grows by constant comparison; each version records a stage |
| A second person | A partner in discussion; disagreement is material for reflection | Codes a sample blind, to calibrate the codebook | Compares codes; can calibrate the codes once they are stable |
| Agreement coefficient | None | Kappa and alpha per code | Per code, on a stable version of the codebook |
| Themes or categories | Built by the researcher as patterns of shared meaning | Built from the codes; the codebook may anticipate them | Categories, and one core category, tied to the codes by memos |
| `qual_ledger.py` | `check`, `support`, `export`; `sample` and `score` refuse | Every command | Every command |

In grounded theory, add a `level` column to `codebook.csv` (`open`, `axial`, `selective`); the script does not check it. Write memos as you go: they carry the comparisons that join codes into categories.

## protocol.json

```json
{"approach": "codebook", "decided_by": "user", "date": "2026-11-18",
 "settings": {
   "min_participants": {"value": 2, "default": true, "source": "convention", "date": "2026-11-18"},
   "kappa_min": {"value": 0.7, "default": false, "source": "the user's study protocol, section 3.2 (protocol.pdf)",
                 "date": "2026-11-18"}}}
```

| Field | Content |
|---|---|
| `approach` | `reflexive`, `codebook` or `grounded` |
| `decided_by`, `date` | Who chose the approach, and when |
| `settings` | Each setting: `value`, `default` (true when the user accepted the convention below), `source` (the paper, protocol or file the value comes from; required when `default` is false), `date` |

| Setting | Default convention | Used by |
|---|---|---|
| `min_participants` | 2 | `support` and the findings leads: fewer participants than this is flagged as low support |
| `kappa_min` | 0.60 | `score`: a code below it is `below_threshold` |
| `alpha_min` | 0.667 | `score`, as above |
| `sample_size` | 30 units | `sample`, unless `--size` is given |
| `min_unit_words` | 5 (a CJK character counts as a word) | `sample`: shorter turns are left out of the pool |

These defaults are conventions, not rules of any method: every output names the value used and where it came from. When the user takes a value from a paper or a protocol, write that source; when the source is a paper, cite only one the user gave or one read in this session.

## approach.md

Write it in plain words, half a page:

1. The approach and why the user chose it, in their words.
2. What a code is here, and what the codebook records.
3. Whether agreement is measured, and why.
4. Who decides codes, themes, their names and saturation: the researcher.
5. What the model does: it proposes codes (`coder` `model`), the researcher accepts or changes them (`checked_by`), and every quote is checked against the transcript by script.

## A coefficient under reflexive analysis

When the user asks for kappa "for the reviewers", do not compute it, and explain:

- Here a code is an interpretation, not a category with a correct answer. Agreement between two readers would measure how alike their readings are, while the approach treats a different reading as something to think with.
- A coefficient in the paper would invite the reviewer to judge the analysis by a standard the chosen method does not use, and it would be easy to misread as evidence of quality.

Offer what speaks to the same worry instead: a reflexivity statement (the researcher's position and how it shaped the reading); the trail of how codes developed (`codebook-changes.csv`, the memos); the support table with "k of N participants" (`support.md`); and how a co-researcher's reading was used (what was discussed, what changed as a result).

If the user wants agreement measured after all, that is a change of method, not a way to obtain a number: codebook thematic analysis defines and applies codes differently from the start. It is the user's decision. If they make it, update `protocol.json` and `approach.md`, run a calibration round on the codebook as it now stands, and report the change and when it happened in the methods. Scores from rounds made under another approach are not presented as quality evidence; `check` lists them as a lead.

## Writing the methods

Report what happened, from the files:

- The approach, and the reason given in `approach.md`.
- What the model did: the host and model name as the host reports them, and the dates; how many codings it proposed, how many a person checked (`checked_by`), how many the researcher made directly. Count them from `codings.jsonl`, never by estimate.
- For codebook analysis and grounded theory: each calibration round as [calibration](calibration.md) describes, with the thresholds and their source, the codes that could not be estimated, and what changed in the codebook after the round.
- Under reflexive analysis: no coefficient; the reflexivity statement and the trail above.
- That quotes were checked against the transcripts by script, and how identifiers were screened.

Never present the model as a second human coder, and never present agreement between the model and the user as evidence that the model reads as a person would.
