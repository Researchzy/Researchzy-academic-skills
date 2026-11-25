# Themes, negative cases, support and saturation

## Themes

```csv
theme,codes,decided_by,definition
Silence as protection,silence;carrying_on,LZ,Staying quiet to avoid being marked as difficult
Work that follows people home,after_hours_contact;family_strain,model,
```

The rows are invented. `theme`, `codes` (separated by `;`) and `decided_by` are required; `definition` and `note` are free.

- The researcher builds, names and decides themes. You may propose a candidate theme: the codes and quotes behind it, two or three possible names and what each would claim, written with `decided_by` `model` until the researcher decides. `check` lists such themes as leads.
- A theme is a claim about shared meaning across the data, not a summary of a single code and not a topic of the interview guide.
- `check` fails a theme without codes, a theme that names a code missing from the current codebook (with the change that explains it), a theme whose codes have no coding that passes check, and an empty `decided_by`.

## Negative cases

Look for passages that do not fit each theme, and sort each into one of four types; each type has a different consequence.

| `type` | What it is | Consequence |
|---|---|---|
| `counter_example` | A passage that contradicts what the theme claims | Narrow the claim, state the exception, or give the theme up; say which in the findings |
| `boundary_case` | A passage at the edge of a definition, fitting partly | Sharpen the definition, or the inclusion and exclusion rules (a codebook change) |
| `dimensional_variation` | The theme is there, in another degree or form | Describe the dimension; it enriches the theme rather than refuting it |
| `insufficient_data` | The data say nothing either way | A direction for the next interviews or questions; it is never filled with invented or imagined cases |

```csv
theme,type,coding,note,decided_by
Silence as protection,counter_example,C0187,P4 raised the rota openly and was supported,LZ
Silence as protection,insufficient_data,,No data from staff on day shifts only: ask in the next round of interviews,LZ
```

The first three types name the coding whose passage shows the case, and `check` requires that coding's quote to pass. `insufficient_data` needs a `note` saying what is missing and where to look.

## Support

`support` counts, for each code and theme, the distinct participants and sources behind it, from the codings that pass every check; the interviewer's words never count. It writes `support.md` and flags each theme or code with fewer participants than the `min_participants` setting as low support. A flagged theme stays; the flag tells the reader how far it reaches.

- Write support as a count: "4 of 12 participants", "in 3 of 6 focus groups".
- Words that generalise ("most", "the majority", "generally", "participants felt", "普遍", "大多数", "一致认为") need counts that bear them out, and then the count beside them. `check --findings` lists each such word as a lead with the support of the themes named in the same paragraph.
- A count describes reach, not importance: a theme held by two participants can still matter. Say what the number is, and do not weigh themes by it.
- Codings no person has checked count like the others; `check` lists them, and the methods say how many there were.

## Saturation

`support.md` ends with a table of the codes each source added for the first time, in the order of `sources.csv`, and the running total. Read it as evidence for a judgement, not as the judgement:

- New codes that stop appearing in the later sources suggest that, for these questions, further sources of the same kind added little. Another order could look different: say in which order the sources were analysed.
- New codes that keep appearing late suggest that more data, or different data, would add more.
- No number of interviews makes saturation; a stated rule ("no new code in the last three sources") is a convention, to be reported as the researcher's.

The researcher writes the judgement, with the table and with what the approach means by saturation ([approach](approach.md)).

## The audit trail

A reader should be able to follow each finding back to the words it rests on, and each code to the decision that shaped it:

| From | To | Kept in |
|---|---|---|
| A quote in the findings | A coding | `check --findings` |
| A coding | The passage, speaker and offsets in a transcript | `codings.jsonl`, `check` |
| A code | Its definition, version and every change, with who decided | `codebook.csv`, `codebook-changes.csv` |
| A theme | Its codes and who decided it | `themes.csv` |
| The codebook | The calibration rounds and what changed after each | `calibration/` |
| The analysis | The researcher's thinking, and yours, kept apart | `memos/` |

`export.csv` puts the coded passages in one table for the appendix or for import into other software. It leaves out nothing about who coded what.

## Handing on

The findings chapter is written by `researchzy-writing` (plugin `researchzy-manuscript`, when installed) from these files: the themes with their support, the negative cases with their consequences, and quotes from the ledger. Run `check --findings` on every draft before it leaves the user's hands.
