# The slide plan

`slides/plan.md` is the only source of the deck: `slide_plan.py` checks it, `build_deck.py` turns it into `deck.tex`, `notes.md` and `deck.pptx`. Change the plan and build again; do not edit the built files.

## Layout

```markdown
---
title: Windowed attention halves the memory of long-document transformers
subtitle: A. Example and B. Sample, Example Conference 2026
presenter: A. Example
affiliation: Example University
event: Machine Learning Seminar, 12 November 2026
minutes: 10
talk: conference
paper: paper.pdf
doi: 10.1234/example.5678
aspect: 16:9
---

Seconds: 20
Notes: Thank you. One message today: a fixed window halves the memory and costs no accuracy.

## Peak memory falls by 48% at 16,384 tokens
- 31.2 GB dense against 16.1 GB with the window
- The saving grows with the length of the input
Figure: fig1a
Source: Fig. 1a of Example and Sample (2026)
Seconds: 90
Notes: This is the main result. Short inputs need about the same memory either way.
As the inputs get longer, the dense curve bends upwards and ours stays almost straight.

So the saving is largest exactly where you need it.

## Use a 256-token window as the default for long documents
- Half the memory, no measurable loss on the four tasks
Seconds: 45
Allow: 2027 | the presenter's plan, not in the paper
Notes: We will test tasks that need many hops in 2027. Thank you.

# Backup

## Removing the 16 global tokens costs 3.1 points on question answering
- Same inputs, same training
Notes: If asked why the global tokens are needed.
```

## The front block

Between two `---` lines at the top, one `key: value` per line. Quotes around a value are optional.

| Key | Required | Content |
|---|---|---|
| `title` | yes | The talk's title: the title frame and slide 1 of the check |
| `minutes` | yes | The time you speak, without the questions that follow |
| `talk` | yes | `conference`, `seminar`, `journal-club`, `lightning`, `lecture` or `defence` |
| `subtitle`, `presenter`, `affiliation`, `event` | no | The title frame. Copy them from the paper's record, never from memory |
| `paper` | no | The paper as `.pdf` or `.txt`, relative to the working folder or to the plan; `check` uses it when `--paper` is not given |
| `doi` | no | Printed small on the title frame |
| `aspect` | no | `16:9` (default) or `4:3` |

## The slides

- Lines after the front block and before the first `## ` belong to the **title frame**: `Seconds:`, `Notes:` and `Allow:` only.
- `## ` starts a slide; the rest of the line is its title. Write the title as a claim (see writing-the-talk.md).
- `- ` (or `* `) starts a bullet. One line per bullet.
- `# Backup` on its own line: every slide after it is a backup slide. Backup slides are built after `\appendix`, are off the clock and are not counted in the slide budget; their notes and numbers are checked like any others.
- No other headings: `###` or a second `#` heading is reported as a line the scripts cannot read.

| Field | Content |
|---|---|
| `Figure: fig1a` | At most one per slide: an id of `slides/figures/manifest.json`, written by `paper_figure.py crop` |
| `Source: …` | The label under the figure. Without it the manifest's label is used |
| `Seconds: 90` or `Seconds: 1:30` | Time planned for the slide |
| `Notes: …` | What you will say. It continues on the following lines until a bullet, a field or a heading; a blank line starts a new paragraph. A line that starts with `- ` ends the notes and becomes a bullet |
| `Allow: 2027 \| why` | A number on this slide or in its notes that is not from the paper: the number as written, a bar, then whose number it is |
| `Kind: section` | A divider slide: its title only, centred. Exempt from the title rule and from "empty" |
| `Kind: closing` | The closing slide. Without it, the last slide before `# Backup` is the closing slide |

Field names may be written in any case. A line that fits none of these is an error in `check` and stops the build.

## The budget: conventions, not rules

The check compares the plan with these working figures. They are conventions collected from practice, not requirements of any venue: when the organisers give a slide limit or a pace, or the user has a habit, use theirs with `--slides-per-minute` and `--words-per-minute`.

| Talk | Slides per minute | Words on a slide: median, most | Use for |
|---|---|---|---|
| `conference` | 1.0 | 40, 60 | A contributed talk at a meeting |
| `seminar` | 1.0 | 40, 60 | A group or departmental seminar |
| `journal-club` | 1.0 | 50, 70 | Presenting someone else's paper |
| `lightning` | 1.5 | 25, 40 | Talks of five minutes or less |
| `lecture` | 0.7 | 40, 70 | Teaching: slides stay up longer |
| `defence` | 0.8 | 45, 65 | A thesis defence or a job talk |

Slides are counted from the title frame to the last slide before `# Backup`. Words are those of the title and the bullets; notes do not count. Speech is estimated at 140 words a minute.

| Check | Error (exit 1) | Flag | Not checked |
|---|---|---|---|
| slides | More than the budget plus 25% | | |
| time | Seconds above the slot by more than 5% | Seconds fill under 75% of the slot | A slide without `Seconds:` |
| speech | Notes take more than the slot plus 10% to say | Notes take under half the planned time to say | A slide without notes |
| words, bullets | | Over the most allowed; median over the working figure; more than 6 bullets | |
| titles | | A filing label ("Results", "Main results", "Introduction") or a title of one or two words. The title frame, the closing slide, section slides and backup slides are exempt | |
| empty | | Neither a bullet nor a figure | |
| figures | Id not in the manifest, file missing, or file changed since it was cropped | No source label | |
| numbers | A numeral not found in the paper and not allowed | An `Allow:` number the slide does not use | No paper text: every numeral is `NOT_CHECKED` |

## How numbers are matched

- A numeral is a run of digits with an optional sign, decimals, exponent and `%` (or "percent"). A digit glued to a letter before it (p53, H2O, T4) is part of a name and is not checked. Numbers written as words ("half", "three") are not checked.
- Checked: the title (of the title frame too), the bullets and the notes. Not checked: the subtitle, presenter, affiliation, event, DOI and source labels, and anything inside a figure.
- Before matching: thousands separators (`16,384`, `16 384`) are removed, the Unicode minus becomes `-`, the space before `%` is ignored.
- **Found** when the paper prints the same value, or prints more decimals that round to the value on the slide (48.4 in the paper, 48 on the slide). A negative number on the slide needs a negative one in the paper; an unsigned one matches either. A percentage on the slide whose value appears in the paper only without `%` is found but marked "no percent sign in the paper".
- Found means the digits occur in the paper, not that they mean the same thing there. `plan-check.md` lists every number with the sentence it was found in, rows found by rounding or without the percent sign first: read those.
