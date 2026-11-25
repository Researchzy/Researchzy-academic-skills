# Variable definitions

Every exposure, intervention, outcome, covariate and eligibility criterion the protocol relies on gets one row of `protocol/definitions.csv`, and every row says where its definition comes from. A definition written from memory can carry a superseded cutoff, mix two versions of a guideline, or invent one, so the source's own words are saved and quoted.

## `definitions.csv`

```csv
variable,role,definition,cutoff,unit,source_id,quote,locator,ad_hoc,justification
Responder,outcome,Improvement of WOMAC pain from baseline to 12 weeks,≥ 20,%,,,,yes,"Chosen with the user for this trial, 2026-11-18; a sensitivity analysis uses the continuous score"
Knee osteoarthritis,eligibility,[Citation needed: diagnostic criteria the user names],,,,,,no,
Pain at baseline,covariate,WOMAC pain subscale at the baseline visit,,,dict-v2,"Baseline pain was recorded on the WOMAC pain subscale",Data dictionary sheet 2 row 14,no,
```

The rows are **invented**; they show the format.

| Column | Content |
|---|---|
| `variable` | The name the protocol uses for it, the same words in every document; names in another language after `\|` (`Responder\|应答者`) |
| `role` | `exposure`, `intervention`, `outcome`, `covariate`, `eligibility` or `other` |
| `definition` | What counts and what does not, the time window, and where the value is recorded |
| `cutoff`, `unit` | A threshold as the documents print it (`≥ 20` and `%`); empty when there is none |
| `source_id` | The name of the saved source text, `sources/<source_id>.txt` |
| `quote`, `locator` | At least five words copied from that text, and where they stand (page, section, table, row) |
| `ad_hoc` | `yes` when the definition is the study's own choice |
| `justification` | For an ad hoc row: why this definition, who chose it and when, and which sensitivity analysis tests it |

## Where a definition comes from, in this order

1. **The user's data dictionary or case report form**, for variables of an existing data source: copy the code and its meaning word for word. When the dictionary is silent, ask the data owner through the user; never infer a code's meaning from the data.
2. **A guideline, consensus statement or published definition** the user supplies, or one read in this session. With the `researchzy` plugin connected (it needs a Researchzy account), search with `search_papers` once per synonym and language (the index matches titles and abstracts, without stemming), read the full text through `get_paper` or `get_paper_files`, save it, and quote it. The index has no retraction data and no cited-by lists, so a later version of a guideline is not found by following citations: ask the user which version applies. Without Researchzy, the user supplies the files.
3. **The study's own choice**: `ad_hoc` `yes`, with its justification and a sensitivity analysis.
4. **Nothing yet**: the definition is `[Citation needed: …]` and the row stays open. A diagnostic criterion named without its document (for example "ACR criteria") is such a row: never write its items from memory.

## `sources/`

Each source is a UTF-8 text file whose first lines say where it came from and when it was read, then a blank line, then the text:

```text
Source: the guideline's title, version and publisher as printed, or the file the user gave
Read: 2026-11-18

…the text, extracted from the PDF or copied from the page…
```

Keep page markers when the extraction gives them. Never edit a saved source to make a quote fit; extract it again and say so.

## The check

```sh
python3 "$SKILL_DIR/scripts/protocol_check.py" definitions
```

| State | Meaning |
|---|---|
| `ok` | The quote is in the saved source (EXACT or INTERLEAVED), or an ad hoc row has its justification |
| `fail` | No source and no placeholder; a missing or unlabelled source file; a quote not in it; no locator; an ad hoc row without a reason; a cutoff a document gives differently |
| `open` | `[Citation needed: …]`: not a pass; listed for the user |
| `not_checked` | A cutoff that no line of `protocol.md` or `sap.md` gives next to the variable's name |

For cutoffs, the command reads every line of `protocol.md` and `sap.md` that names the variable and takes the numbers tied to a comparison (≥, >, at least, or more, 以上, 及以上, 不低于…) and followed by the row's unit. A line whose numbers do not include the table's cutoff fails. Use the variable's name from the table in the documents, so that the line can be found.

The match tolerates extraction noise between words, so a quote that lacks "not" or a digit can still be found: reread every quote that turns on a negation or a number.
