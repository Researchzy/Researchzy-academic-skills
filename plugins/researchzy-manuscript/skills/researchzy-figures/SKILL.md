---
name: researchzy-figures
description: "Make publication figures from data: profile the data, choose a chart it can support, draw it with matplotlib at the venue's column width, export PDF and PNG with a record, and check the file's size, fonts and colours. Use for a new figure, or to check a figure file before submission."
---

# Researchzy Figures

This skill turns a data file into a figure for a paper and then checks the exported file, not the code that drew it. The order is fixed: agree what the figure must show, profile the data, choose a chart the data can support, draw it from a script at the printed size, export it with a record of what it was made from, run the checker, and look at the result.

It draws with Python (matplotlib, optionally seaborn). The checker reads any exported PDF, PNG or TIFF, so it also checks figures made in R or a drawing program. The skill does not use image-generation models, and the only diagrams it draws are flow charts drawn by code. It does not run statistical tests or decide what an error bar should be.

Resolve `SKILL_DIR` to the directory containing this `SKILL.md`. The scripts need Python 3.10 or newer. Drawing needs matplotlib 3.6 or newer; the profiler and the checker need nothing else, and the checker compares colours only when Pillow is installed. If matplotlib is missing, say so and ask before installing anything. No account is needed; the Researchzy tools are not used.

## Inputs

- A data file with a header row: CSV, TSV or Excel (Excel needs pandas). One row per observation is best. A table of summaries is accepted, but then no distribution can be drawn.
- What the figure should show and where it will be published.
- Or a figure file that already exists: go to "Checking a figure made elsewhere".

## Workflow

Everything goes in `figures/` in the user's working directory. Run every command from that directory.

1. **Write the figure contract.** Fill in five items from the request and the files; mark the ones you cannot fill.

   | Item | What it is | When unknown |
   |---|---|---|
   | Message | The one sentence the figure must make a reader believe | Ask |
   | Destination | The venue and the column type, which give the width in mm ([sizes and style](references/sizes-and-style.md)) | Ask; with no venue yet, use 89 mm and say so |
   | One point | The unit of analysis: a subject, a sample, a run. Not "a row" | Ask. Never guess |
   | n | Units per group | Step 2 gives it |
   | Error bars | Standard deviation, standard error, confidence interval and its level, interquartile range, or none | Ask, if the figure will have any |

2. **Profile the data.**

   ```sh
   python3 "$SKILL_DIR/scripts/profile_data.py" data/trial.csv
   python3 "$SKILL_DIR/scripts/profile_data.py" data/trial.csv --id subject --group treatment --na -999
   ```

   It writes `figures/trial.profile.json` and prints the role it gave each column (`id`, `group`, `time`, `measure`, `other`), the `design`, the smallest n per group, the charts it rules out, and notes on missing values. The roles are guesses from names and values: when one is wrong, run it again with `--id`, `--group`, `--time`, `--measure` or `--pair` (the column that links paired observations).

   | `design` | Meaning |
   |---|---|
   | `independent` | Each unit appears once |
   | `paired` | The same units appear in several groups |
   | `repeated_over_time` | The same units appear at several time points |
   | `replicates` | Several rows per unit and condition: rows are not n |
   | `no_id_column` | No column names the unit; rows are assumed independent |

   Now ask the user, once and in one message, for every contract item still open. Do not draw while the unit of analysis is unknown (`no_id_column` and the user has not said what a row is) or while the figure is to carry error bars whose meaning is unknown. A polished figure of the wrong unit is worse than none.

3. **Choose the chart.** Read [chart selection](references/chart-selection.md). Pick from the data pattern and the message, apply its substitutions, and decide whether a table would serve better. Do not draw a chart listed under `ruled_out` unless the user asks for it after hearing the reason. Tell the user the choice and the reason in one or two lines.

4. **Write one script per figure**, `figures/<name>.py`. Copy the style module next to it once, so that the folder runs on any machine:

   ```sh
   mkdir -p figures && cp -n "$SKILL_DIR/scripts/rz_figure.py" figures/
   ```

   ```python
   """Figure 1. <the message>. One point: <unit>. n: <per group>. Error bars: <definition, or none>. Width: 89 mm."""
   import matplotlib
   matplotlib.use("Agg")
   import matplotlib.pyplot as plt
   import pandas as pd                      # or the csv module
   import rz_figure as rz

   DATA = "data/trial.csv"
   table = pd.read_csv(DATA)

   rz.apply_style()                         # print sizes, Okabe-Ito colours, embedded fonts
   fig, ax = plt.subplots(figsize=rz.figsize_mm(89, 60))
   ...                                      # ax.plot(x, y, **rz.series_style(0))
   rz.save(fig, "fig1_response", data=[DATA])
   ```

   - The script reads the data file. It contains no typed-in data values, and every exclusion is written in it with its reason.
   - Size the canvas with `figsize_mm` to the width of the contract. No title inside the figure; panels are labelled a, b, c.
   - Give each series a second cue besides colour (`series_style` pairs colour, marker and line style).
   - Read [honest encoding](references/honest-encoding.md) before drawing bars, areas, log axes or anything with missing values, and [library pitfalls](references/library-pitfalls.md) before using seaborn, error bars or mathtext.
   - For a flow chart, read [diagrams](references/diagrams.md).

5. **Export.** Run `python3 figures/fig1_response.py`. `rz.save` writes `figures/<name>.pdf` (vector), `<name>.png` (300 dpi) and `<name>.figure.json` (script and data files with SHA-256, package versions, size in mm, fonts, axis findings), and prints a summary. If `fonts.fallback` is true, the first-choice font is not on this machine: tell the user which font was used. `axis_findings` lists bars or filled areas that do not start at zero, twin axes, and zero or negative values on a log axis: fix them now.

6. **Check the files.**

   ```sh
   python3 "$SKILL_DIR/scripts/check_figure.py" figures/fig1_response.pdf figures/fig1_response.png --width-mm 89
   ```

   Add `--min-pt` or `--min-dpi` only to match a requirement the venue states. Every check is `PASS`, `FAIL` or `NOT_CHECKED`; the exit code is 1 when any check fails.

   | Check | On `FAIL` |
   |---|---|
   | `width` | Change `figsize_mm`. Never rescale the exported file |
   | `min_font_size` | Enlarge the text the report names. A sub- or superscript is drawn at 0.7 of its text |
   | `fonts` | Type 3 or not embedded: export through `rz.save`; from R use `cairo_pdf` |
   | `resolution` | Export again at the right size. Do not upsample |
   | `colour_vision` | Use palette colours for the pair named. A pair that includes a grid or annotation colour is not a problem: say so |
   | `grayscale` | Give the two series of each pair a second cue. The checker cannot see the cue, so the FAIL stays: report it with the cue |
   | `axes` | Fix the figure. Marks that show an interval, not an amount, are the only exception ([honest encoding](references/honest-encoding.md)) |

   A `NOT_CHECKED` is reported to the user as not checked, with its reason. It is never a pass.

7. **Look at the figure.** Open `figures/<name>.png` and check what no script sees: the message is visible without the caption; no text overlaps, is cut off or covers data; the series can be told apart; axis labels carry units; the same group has the same colour in every panel. Then revise: change the script, export, check, look. Do this at most twice. After the second round stop: deliver the latest version the checker accepts, or if none does, the latest one with its failures listed, and say what you would still change.

8. **Hand over.** Give the user the script, the PDF, the PNG and the record, the checker's final statuses, and the facts a caption needs: what one point is, n per group, what the summary mark and the error bars are, and what was missing or excluded. Test each of these against the plotted rows ([honest encoding](references/honest-encoding.md)). Significance marks, the choice of test and the wording of error-bar definitions go to `researchzy-stats-review` (plugin `researchzy-manuscript`, when installed); until then the figure carries no stars or p-values except ones the user supplied in a file. The caption's wording goes to `researchzy-writing` (same plugin, when installed).

## Checking a figure made elsewhere

Run step 6 on the file, with the print width. For R, export with `ggsave("fig.pdf", width = 89, height = 60, units = "mm", device = cairo_pdf)` and a PNG at `dpi = 300` first. Without a record from `rz.save`, `axes` is `NOT_CHECKED`: read the plotting code or the picture for bars cut off from zero, twin axes and log axes, and say that this was done by eye. Then do steps 7 and 8. Do not redraw the figure unless asked.

## Outputs

| File in `figures/` | Content |
|---|---|
| `<data>.profile.json` | Roles, n per group, missing values, range and skew, design, ruled-out charts |
| `<name>.py`, `rz_figure.py` | The plotting script and the style module it imports |
| `<name>.pdf`, `<name>.png` | The figure: vector, and 300 dpi |
| `<name>.figure.json` | Script and data hashes, package versions, size, fonts, axis findings |

## Rules

- Never type data values into a script, and never change, drop or add a value to improve the picture. A figure of placeholder data has `placeholder` in its file name and on its canvas.
- The rules in honest-encoding.md bind every figure. Sizes, fonts and colours are defaults that the venue or the user may change.
- Never report `NOT_CHECKED` as passed, and never loosen `--min-pt`, `--min-dpi` or `--tolerance-mm` to turn a `FAIL` into a `PASS`.
- Never save with `bbox_inches="tight"`: it changes the physical size.
- The widths in the reference are dated. Confirm the width against the venue's current author guidelines, or ask the user for them, and say which value you used.
- `rz.save` refuses to replace a PDF or PNG it did not write. Choose another name; do not delete or overwrite the user's figures.
- No image-generation models, for any part of a figure.

## Related files

| File | Open when |
|---|---|
| [references/chart-selection.md](references/chart-selection.md) | Step 3, and whenever the user names a chart type |
| [references/sizes-and-style.md](references/sizes-and-style.md) | Setting the width, fonts, line widths, colours or the file format |
| [references/honest-encoding.md](references/honest-encoding.md) | Before drawing bars, areas, log axes or missing values; on an `axes` FAIL; before writing caption facts |
| [references/library-pitfalls.md](references/library-pitfalls.md) | Before using seaborn, error bars or mathtext; when the size or the text comes out wrong |
| [references/diagrams.md](references/diagrams.md) | The user asks for a flow chart, a schematic or a graphical abstract |
| `scripts/profile_data.py` | Step 2; `--help` lists the options |
| `scripts/rz_figure.py` | Steps 4 and 5; run it alone to print the font and versions on this machine |
| `scripts/check_figure.py` | Step 6, and for any figure file made elsewhere |
