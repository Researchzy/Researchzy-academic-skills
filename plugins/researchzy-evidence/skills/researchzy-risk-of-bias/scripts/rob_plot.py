#!/usr/bin/env python3
"""Traffic-light and summary plots of the risk-of-bias judgements.

  rob_plot.py [--dir risk-of-bias] [--weighted] [--formats pdf png svg]

For each tool and outcome: traffic-light-<tool>-<outcome> (studies by domains, then the overall
judgement) and summary-<tool>-<outcome> (the share of studies at each judgement, domain by
domain), as PDF, PNG (300 dpi) and SVG in --dir. Every judgement has its own colour and symbol,
so the plots read in grayscale and with colour-vision deficiency; a judgement of no information
is a state of its own (sky blue, "?"), never folded into a ranked one. --weighted makes the
summary bars shares of the total weight, from each result's "weight" in assessments.json, when
every result of the outcome has one.

Draws only when rob_check.py check finds no failure (exit code 1 otherwise). Without matplotlib
it draws nothing, says so in the JSON summary and exits 0.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rob_check as rc  # noqa: E402

# Okabe-Ito colours from best to worst, by the number of ranked levels the tool has. The symbols
# and hatches repeat the order, so colour is never the only cue.
COLOURS = {2: ("#009E73", "#D55E00"), 3: ("#009E73", "#F0E442", "#D55E00"),
           4: ("#009E73", "#F0E442", "#D55E00", "#000000"),
           5: ("#009E73", "#F0E442", "#E69F00", "#D55E00", "#000000")}
SYMBOLS = {2: "+x", 3: "+−x", 4: "+−x!", 5: "+−~x!"}
HATCHES = ("", "//", "xx", "\\\\", "--")
NO_INFORMATION = ("#56B4E9", "?", "..")


def styles(t: dict):
    """{judgement id: (colour, symbol, hatch)} for one tool; None when it has more ranked levels than colours."""
    ranked = sorted(t["rank"], key=t["rank"].get)
    if len(ranked) not in COLOURS:
        return None
    found = {j: (COLOURS[len(ranked)][i], SYMBOLS[len(ranked)][i], HATCHES[i]) for i, j in enumerate(ranked)}
    return {**found, **{j: NO_INFORMATION for j in t["ni"]}}


def ink(colour: str) -> str:
    """Black or white, whichever reads on the colour."""
    red, green, blue = (int(colour[i:i + 2], 16) / 255 for i in (1, 3, 5))
    return "white" if 0.2126 * red + 0.7152 * green + 0.0722 * blue < 0.35 else "black"


def draw(plt, patch, t: dict, outcome: str, entries: list, weights: list, base: Path, formats: list) -> list:
    style, (cols, heads) = styles(t), rc.columns(t)
    grid = [[rc.judgement(r, c) for c in cols] for _, r in entries]
    order = sorted(t["rank"], key=t["rank"].get) + sorted(t["ni"] & {j for line in grid for j in line})
    legend = [patch(facecolor=style[j][0], hatch=style[j][2], edgecolor="black", linewidth=0.5,
                    label=f"{style[j][1]}  {t['labels'][j]}") for j in order]
    names = [f"D{i}: {d['name']}" for i, d in enumerate(t["domains"], 1)]
    stem, paths = re.sub(r"[^A-Za-z0-9._-]+", "-", f"{t['id']}-{outcome}"), []

    fig, ax = plt.subplots(figsize=(max(4.5, 1.6 + 0.5 * len(cols)), 1.4 + 0.42 * len(entries)), layout="constrained")
    for i, line in enumerate(grid):
        for k, j in enumerate(line):
            colour, symbol, _ = style[j]
            ax.scatter(k, i, s=330, color=colour, edgecolors="black", linewidths=0.5)
            ax.text(k, i, symbol, ha="center", va="center", fontsize=9, fontweight="bold", color=ink(colour))
    ax.set_xticks(range(len(cols)), heads)
    ax.set_yticks(range(len(entries)), [sid for sid, _ in entries])
    ax.set(xlim=(-0.6, len(cols) - 0.4), ylim=(len(entries) - 0.4, -0.6))
    ax.xaxis.tick_top()
    ax.tick_params(length=0)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.set_title(f"{t['raw'].get('name')}: {outcome}", fontsize=9, loc="left", pad=22)
    fig.legend(handles=legend, loc="outside lower center", ncol=min(len(legend), 3), fontsize=8, frameon=False,
               title="; ".join(names), title_fontsize=7)
    paths += save(plt, fig, base / f"traffic-light-{stem}", formats)

    fig, ax = plt.subplots(figsize=(6.5, 1.3 + 0.36 * len(cols)), layout="constrained")
    total = sum(weights)
    for k in range(len(cols)):
        left = 0.0
        for j in order:
            share = sum(w for w, line in zip(weights, grid) if line[k] == j) / total
            if share:
                colour, symbol, hatch = style[j]
                ax.barh(k, share, left=left, color=colour, hatch=hatch, edgecolor="black", linewidth=0.5)
                if share >= 0.06:
                    ax.text(left + share / 2, k, symbol, ha="center", va="center", fontsize=8, fontweight="bold",
                            bbox={"boxstyle": "circle,pad=0.2", "facecolor": "white", "linewidth": 0.5})
                left += share
    ax.set_yticks(range(len(cols)), [n if len(n) <= 40 else n[:39] + "…" for n in names] + (["Overall"] if None in cols else []))
    ax.set(xlim=(0, 1), ylim=(len(cols) - 0.5, -0.5))
    ax.set_xticks([0, 0.25, 0.5, 0.75, 1], ["0%", "25%", "50%", "75%", "100%"])
    ax.set_xlabel("Share of the total weight" if len(set(weights)) > 1 else "Share of studies")
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    fig.legend(handles=legend, loc="outside lower center", ncol=min(len(legend), 4), fontsize=8, frameon=False)
    return paths + save(plt, fig, base / f"summary-{stem}", formats)


def save(plt, fig, stem: Path, formats: list) -> list:
    paths = [stem.with_name(f"{stem.name}.{ext}") for ext in formats]
    for path in paths:
        fig.savefig(path, dpi=300)
    plt.close(fig)
    return [str(path) for path in paths]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Draw traffic-light and summary plots of risk-of-bias judgements.")
    parser.add_argument("--dir", default="risk-of-bias", help="The output folder (default: risk-of-bias)")
    parser.add_argument("--weighted", action="store_true", help="Summary bars as shares of each result's weight")
    parser.add_argument("--formats", nargs="+", default=["pdf", "png", "svg"], choices=["pdf", "png", "svg"])
    args = parser.parse_args(argv)
    base = Path(args.dir)
    rows, ctx = rc.run_checks(base)
    failures = sum(r["status"] == "fail" for r in rows)
    summary = {"drawn": [], "notes": []}
    if failures:
        summary.update(failures=failures, message="rob_check.py check fails: fix the assessments first")
        print(json.dumps(summary, indent=2))
        return 1
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.patches import Patch
    except ImportError:
        summary.update(matplotlib="not installed", message="no plot drawn: matplotlib is not installed")
        print(json.dumps(summary, indent=2))
        return 0
    summary["matplotlib"] = matplotlib.__version__
    for t, outcome, entries in rc.by_outcome(ctx):
        weights = [r.get("weight") for _, r in entries]
        if styles(t) is None:
            summary["notes"].append(f"{t['id']}: more than {max(COLOURS)} ranked judgement levels; not drawn")
            continue
        if args.weighted and not all(type(w) in (int, float) and w > 0 for w in weights):
            summary["notes"].append(f"{t['id']} / {outcome}: not every result has a positive weight; summary unweighted")
        use = weights if args.weighted and all(type(w) in (int, float) and w > 0 for w in weights) else [1] * len(entries)
        summary["drawn"] += draw(plt, Patch, t, outcome, entries, use, base, args.formats)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
