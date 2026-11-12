# Diagrams

This skill draws one kind of diagram: a flow chart of boxes and arrows, drawn by code. Typical uses are the flow of participants or samples through a study, the steps of an analysis pipeline, and a decision procedure.

It does not draw anything else. Tell the user so, and do not substitute, when they ask for:

- a graphical abstract, a "hero" figure, an illustration of an organism, device or mechanism;
- a model architecture drawn as artwork;
- any picture from an image-generation model. Generated images cannot be checked against the data and many venues restrict them.

For those, offer a plain box-and-arrow draft that the user or an illustrator can redraw, and say that it is a draft.

## Rules

- **Counts come from a file.** Every number in a box is read from a data file, and the script asserts that they add up: each box equals the one before it minus what left. If they do not add up, stop and show the user the step that fails; do not adjust a number.
- **One direction.** Top to bottom or left to right. Side boxes (exclusions) all on the same side.
- **Same grid.** Boxes of one kind have the same width and are aligned; arrows are straight, horizontal or vertical.
- **Same text.** Use the figure style: one font size, sentence case, a label and at most one line of numbers per box. Put longer explanations in the caption.
- **No decoration.** No shadows, gradients or icons. White boxes with a 0.6 pt outline; colour only when it encodes something, with a legend.
- **About twelve boxes at most.** A larger flow is split, or the detail goes into a table.
- Export with `rz.save` and run `check_figure.py`, as for any figure. Pass the counts file in `data=[...]`.

## Skeleton

The counts file has one row per step: `step,label,n,excluded,reason`.

```python
import csv
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
import rz_figure as rz

DATA = "data/flow.csv"
with open(DATA, newline="", encoding="utf-8") as handle:
    steps = list(csv.DictReader(handle))
for above, below in zip(steps, steps[1:]):
    assert int(above["n"]) - int(below["excluded"]) == int(below["n"]), f"counts do not add up at: {below['label']}"

rz.apply_style()
fig, ax = plt.subplots(figsize=rz.figsize_mm(89, 22 * len(steps)))
ax.set_axis_off()
ax.set_xlim(0, 10)
ax.set_ylim(0, 3 * len(steps))
arrow = {"arrowstyle": "-|>", "linewidth": 0.6, "color": "black"}


def box(x, y, text, width=4.4, height=1.6):
    ax.add_patch(FancyBboxPatch((x, y), width, height, boxstyle="round,pad=0,rounding_size=0.15",
                                facecolor="white", edgecolor="black", linewidth=0.6))
    ax.text(x + width / 2, y + height / 2, text, ha="center", va="center")


for i, step in enumerate(steps):
    y = 3 * (len(steps) - 1 - i) + 0.7
    box(0.3, y, f"{step['label']}\nn = {step['n']}")
    if i:
        ax.annotate("", xy=(2.5, y + 1.6), xytext=(2.5, y + 3), arrowprops=arrow)          # from the box above
        box(5.4, y + 1.5, f"{step['reason']}\nn = {step['excluded']}", width=4.3, height=1.3)
        ax.annotate("", xy=(5.4, y + 2.15), xytext=(2.5, y + 2.15), arrowprops=arrow)      # to the exclusion box

rz.save(fig, "fig_flow", data=[DATA])
```

Look at the PNG afterwards: text that does not fit its box is the usual fault. Shorten the label or widen the box; do not shrink the font.

## Other tools

- A reporting guideline with an official flow-diagram template (for trials, systematic reviews, diagnostic studies) takes precedence: fill in the template's boxes with counts from the file.
- In a LaTeX manuscript the same chart can be written in TikZ, and where Graphviz is installed, as a DOT file. The rules above and the checker apply to the exported PDF all the same; `axes` is then NOT_CHECKED, which is expected for a diagram.
