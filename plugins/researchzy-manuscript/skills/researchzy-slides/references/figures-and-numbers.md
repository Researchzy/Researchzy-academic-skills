# Figures and numbers

Two rules carry the skill: every figure on a slide is a region of the paper's own pages, unchanged, with a record of where it came from; and every number on a slide or in the notes is in the paper's text or is marked as somebody else's with its reason.

## Taking a figure from the paper

1. **Find the page.** The paper's figure list or captions say where each figure is. `paper_figure.py page paper.pdf --page N` renders the page to `slides/preview/page-NN.png` with a grid every tenth of the page, and lists the captions, embedded pictures and clusters of vector drawing on it with their boxes. Those boxes are a start, not the answer.
2. **Choose the box.** Open the preview. The box (x0, y0, x1, y1, fractions of the page from the top left) takes in the whole figure or the whole panel: axes, tick labels, axis titles, legend, panel letter, colour bar, scale bar and units. Leave out the caption (it becomes the source label and the notes) and any neighbouring text.
3. **Crop.** `paper_figure.py crop paper.pdf --page N --box … --id fig2a --label "Fig. 2a of Author et al. (Year)"`. It renders at 300 dpi, writes `slides/figures/fig2a.png` and a manifest row: id, file, the source PDF and its SHA-256, page, box, dpi, pixel size, the PNG's SHA-256, label and renderer.
4. **Look at the PNG.** Is everything named in step 2 inside, and nothing else? If a label is cut, crop again with `--replace` and a wider box. A crop of a single colour is refused: the box missed.
5. **Name it in the plan** with `Figure: fig2a`. `slide_plan.py check` fails when the id is not in the manifest, the file is missing, or the file was changed after it was cropped.

| Situation | What to do |
|---|---|
| A figure with several panels and one message per panel | Crop one panel per slide |
| A panel too dense to read when projected | Crop the part that carries the claim, if it stands alone with its axes; otherwise keep the panel and move the detail to the notes or a backup slide |
| The figure needs emphasis (an arrow, a highlight) | Say it in the title or a bullet; do not draw on the crop |
| The paper is a scan | Crops work; the number check will be `NOT_CHECKED`, because there is no text to search |
| The user's own figure file, or one made with `researchzy-figures` | Crop its PDF the same way (page 1, box `0,0,1,1`) so it gets a manifest row; the label names the file |

Never redraw, re-plot, recolour, retouch, annotate or upscale a figure, and never use an image model to make or "clean up" one. A redrawn data figure can move points, change axes or drop error bars without anyone noticing. New figures from data belong to `researchzy-figures` (plugin `researchzy-manuscript`, when installed); a diagram of the method can be described in bullets.

## The source label

Every figure carries a label under it in small type: "Fig. 2a of Author et al. (Year)" for the paper being presented, with the figure number exactly as the paper prints it. Author and year come from the paper's first page or the Researchzy record, never from memory. In a journal club the label is required on every figure, because the slide shows another group's work. If the slides will be shared outside the room, tell the user that reusing published figures publicly may need the publisher's permission; whether it does is not something this skill decides.

## Tables

- A small table, or the two rows of a table that carry the claim, may be retyped as bullets: "64 tokens: 12.9 GB, mean score 63.2". Keep the paper's rounding and units. The retyped numbers are checked against the paper's text like any others.
- A larger table is cropped like a figure. Do not retype it: retyping many numbers is where transcription errors happen, and a cropped table shows the paper's layout.
- Name the table in the bullets or the notes ("from Table 2") so the audience can find it.

## Numbers

| Where the number comes from | What the plan needs |
|---|---|
| The paper's text, with its rounding or rounded from it | Nothing: the check finds it |
| Only inside a figure or a table that was cropped | Read it off the paper with care; it will be `NOT_FOUND` if the text never states it, so either say it in words without the digits or add an `Allow:` line naming the figure ("Allow: 0.82 \| read from Fig. 3b of the paper") |
| The presenter (a remark, a date, the size of their own data) | `Allow: 2027 \| the presenter's plan` |
| Another paper (context in a journal club) | `Allow: 0.71 \| Smith et al. (2024), Table 2, supplied by the user`; never from memory |
| The arithmetic of the presenter ("half", "a third") | Prefer words; a computed number such as "2.1 times" that the paper does not print needs an `Allow:` line saying how it was computed from which two numbers |

Rules:

- Never write a number from memory, and never "improve" one: a slide that says 50% where the paper says 48.4% is wrong; 48% is a rounding the check accepts.
- Keep units and denominators: "48% less memory", not "48%". Say whether a figure is a mean, a median or a single run when the paper does.
- `found` means the digits occur in the paper. Read the sentence `plan-check.md` shows for each number, first for the rows found by rounding or without the percent sign: a 48 found in "48 participants" does not support "48% less memory".
- An `Allow:` line is for numbers that are honestly not from the paper. Using it to silence a `NOT_FOUND` that should be in the paper is fabrication: correct the number instead.
- Without the paper's text the check says `NOT_CHECKED`. Tell the user the numbers were not compared with the paper; never call them checked.
