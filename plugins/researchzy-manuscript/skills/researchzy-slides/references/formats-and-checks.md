# Output formats and checks

## Beamer and PDF: always

Beamer is the format this skill can both build and check without an office suite: compiling the `.tex` is the rendering, the log reports what did not fit, and the PDF can be looked at page by page. So the plan is always built as `slides/deck.tex` and compiled to `slides/deck.pdf`.

- **Theme.** Beamer's default theme with a few colour and font settings in the preamble: no theme packages, no institutional templates, so it compiles on any TeX installation that has Beamer. Pages are 16 x 9 cm (12.8 x 9.6 for 4:3); projected, 11 pt type reads like about 23 pt on a 13.33-inch PowerPoint slide, so the sizes are comparable.
- **Compile** with the command `build_deck.py` prints, which runs in `slides/`:

  ```sh
  latexmk -pdf -cd -interaction=nonstopmode -halt-on-error -file-line-error slides/deck.tex
  ```

  `-xelatex` instead of `-pdf` when the build says the plan has characters pdflatex's fonts lack. For Chinese, Japanese or Korean text xelatex also needs a font with those characters; ask the user which one before changing the preamble.
- **No TeX installation:** say so. `deck.tex` is still written and compiles anywhere with a TeX distribution that includes Beamer. Ask before installing anything.
- **Notes** are in `\note{}` and do not appear in `deck.pdf`. `notes.md` holds them with the time of each slide. To print notes pages, the user can add `\setbeameroption{show notes}` (or `show notes on second screen=right` for a presenter view) to the preamble of a copy.
- **Backup slides** come after `\appendix`: the frame numbers read "4 / 9" in the talk and "1 / 1" in the backup.

### Reading the deck check

`slide_plan.py deck slides/deck.tex slides/deck.pdf --plan slides/plan.md` reads the `.tex`, its log and the PDF.

| Finding | Meaning | Fix |
|---|---|---|
| Frames or pages differ from the plan | The deck is not the plan, or the build is older than the plan | Build and compile again |
| The plan changed after the build | `build.json` records another plan | Build and compile again |
| Overfull vbox above 5 pt | The frame's content runs off the bottom | Shorten the slide in the plan: fewer or shorter bullets, or split it, or move text to the notes. Then build again |
| Overfull hbox above 5 pt | A line or figure runs past the right edge (often a long word or URL) | Shorten or break the text in the plan |
| File not found | A graphic or package is missing | Crop the figure again; for a package, report it |
| Undefined reference | A `\ref` without a label: the plan's text contained one | Remove it from the plan |
| Characters dropped | The font lacks a character | Compile with `-xelatex`, or replace the character |
| Log not current | The log is from another version of the `.tex` | Compile again |

Overfull boxes under 5 pt do not show on a slide and are ignored. Fix through the plan, not by editing `deck.tex`: a build refuses to overwrite a `deck.tex` that was edited after it was written, and `--force` keeps the edited copy as `deck.edited.tex`.

### Looking at the frames

No check sees everything. Render the frames and open at least the title frame, every slide with a figure and the slide with the most words:

```sh
pdftoppm -r 80 -png slides/deck.pdf slides/preview/frame
```

Look for: a title longer than two lines; bullets that run into the figure; a figure too small to read from the back of a room (its smallest text should be at least as large as the bullets); a source label that is missing or cut; anything off the edge. Fix in the plan, build, compile, look again. Stop after two rounds and report what still needs the user's eye.

## PowerPoint: when python-pptx is installed

`build_deck.py build slides/plan.md --pptx` also writes `slides/deck.pptx` from the same plan: the same slides, the same figures with their labels, the notes in the notes pane, slide numbers, on a 13.33 x 7.5 inch page (10 x 7.5 for 4:3). Titles are 30 pt and body text 22 pt; nothing is below the 20 pt floor except the slide number and the source label. When a slide's text would not fit at that size, the slide is reported as over-full; the type is never shrunk and slides are not split, because the plan is the source. Shorten the plan and build again.

Without python-pptx the build says so and writes the Beamer deck only. Ask before installing it.

The PPTX is never rendered here. `slide_plan.py deck slides/deck.pptx --plan slides/plan.md` reads it as XML: slide count, words, the smallest type, shapes off the slide, text in boxes of zero size, notes, pictures against the manifest. Its layout is always `NOT_RENDERED`: fonts, line breaks and spacing are decided by the program that opens it, and the text box estimates can be wrong. The default font is whatever PowerPoint or LibreOffice substitutes for the template's font.

## What to tell the user

- Which files there are: `deck.pdf` to present, `deck.tex` to edit in LaTeX, `deck.pptx` to edit in PowerPoint (if built), `notes.md`, `plan.md` as the source, `figures/manifest.json` as the record of every figure.
- What was checked: the plan check and the deck check, with their statuses, and that the frames were looked at.
- What was not: `NOT_CHECKED` items with their reasons; that numbers inside figures were not compared; that the PPTX layout was not rendered and each slide should be opened and looked at, the figure slides first.
- How to change the deck: edit `plan.md` and build again, or edit `deck.tex` or `deck.pptx` directly and stop rebuilding from the plan.
