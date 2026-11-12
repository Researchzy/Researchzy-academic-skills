#!/usr/bin/env python3
"""Style, size, axis audit and export for publication figures drawn with matplotlib.

Copy this file next to the plotting scripts (figures/rz_figure.py) and import it there:

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import rz_figure as rz

    rz.apply_style()
    fig, axes = plt.subplots(1, 2, figsize=rz.figsize_mm(183, 70))
    ...                                    draw from the data file, never from typed-in numbers
    rz.save(fig, "fig1-response", data=["data/response.csv"])

  apply_style()                 rcParams for print; returns the font that will really be used
  figsize_mm(width, height)     a figsize in inches from millimetres
  PALETTE, MARKERS, LINESTYLES  Okabe-Ito colours and the second cue; series_style(i) pairs them
  audit_axes(fig)               findings about bars, filled areas, twin axes and log axes
  save(fig, name, data=[...])   figures/<name>.pdf, <name>.png (300 dpi), <name>.figure.json

save() never crops the canvas, so the files have exactly the size asked for. The record lists the
script and the data files with their SHA-256, the package versions, the size in mm, the fonts used
and what audit_axes() found.

  python3 rz_figure.py          print the font and versions on this machine (exit code 2
                                when matplotlib is missing)

Needs matplotlib 3.6 or newer.
"""

from __future__ import annotations

import hashlib
import json
import platform
import re
import sys
from pathlib import Path

try:
    import matplotlib as mpl
    import numpy as np
    from cycler import cycler
    from matplotlib import font_manager
    from matplotlib.collections import LineCollection, PathCollection, PolyCollection
    from matplotlib.container import BarContainer
except ImportError as exc:  # pragma: no cover - depends on the machine
    if __name__ == "__main__":
        print("rz_figure needs matplotlib (python3 -m pip install matplotlib).", file=sys.stderr)
        raise SystemExit(2)
    raise ImportError("rz_figure needs matplotlib (python3 -m pip install matplotlib).") from exc

__version__ = "1.0.0"

# Okabe and Ito's eight colours (Color Universal Design, 2008). The order is ours: the first four
# also differ in lightness, so they stay apart in a grayscale print; from the fifth on a second
# cue is needed. Yellow is last because it is too light for thin lines and text on white.
PALETTE = {
    "blue": "#0072B2",
    "orange": "#E69F00",
    "bluish green": "#009E73",
    "black": "#000000",
    "vermillion": "#D55E00",
    "sky blue": "#56B4E9",
    "reddish purple": "#CC79A7",
    "yellow": "#F0E442",
}
MARKERS = ("o", "s", "^", "D", "v", "P", "X", "*")
LINESTYLES = ("-", "--", ":", "-.", (0, (5, 1)), (0, (3, 1, 1, 1)), (0, (1, 1)), (0, (6, 2, 1, 2)))
FONTS = ["Arial", "Helvetica", "Liberation Sans", "Nimbus Sans", "DejaVu Sans"]
DPI = 300
MM_PER_INCH = 25.4


def series_style(index: int) -> dict:
    """Colour, marker and line style for series number `index`: two cues, not colour alone."""
    colours = list(PALETTE.values())
    return {"color": colours[index % len(colours)], "marker": MARKERS[index % len(MARKERS)],
            "linestyle": LINESTYLES[index % len(LINESTYLES)]}


def figsize_mm(width_mm: float, height_mm: float) -> tuple:
    """A matplotlib figsize (inches) for a canvas of width_mm by height_mm."""
    if not (width_mm > 0 and height_mm > 0):
        raise ValueError("figsize_mm needs a positive width and height in millimetres.")
    return (width_mm / MM_PER_INCH, height_mm / MM_PER_INCH)


def font_report() -> dict:
    """The font matplotlib resolves for the current rcParams, and whether it is the first choice."""
    families = list(mpl.rcParams["font.family"])
    wanted = []
    for family in families:
        wanted += list(mpl.rcParams.get(f"font.{family}", [family]))
    path = font_manager.findfont(font_manager.FontProperties(family=families))
    used = font_manager.get_font(path).family_name
    return {"first_choice": wanted[0], "used": used, "fallback": used.lower() != wanted[0].lower()}


def apply_style(font_pt: float = 8.0) -> dict:
    """Set rcParams for a figure that is printed at the size it is drawn. Returns font_report().

    Labels are font_pt; ticks and legend half a point smaller. Mathtext sub- and superscripts are
    drawn at 0.7 of their text, so the default 7.5 pt ticks keep exponents above a 5 pt floor.
    """
    small = font_pt - 0.5
    style = {
        "font.family": "sans-serif", "font.sans-serif": FONTS, "mathtext.default": "regular",
        "font.size": font_pt, "axes.labelsize": font_pt, "axes.titlesize": font_pt,
        "figure.titlesize": font_pt, "figure.labelsize": font_pt,
        "xtick.labelsize": small, "ytick.labelsize": small,
        "legend.fontsize": small, "legend.title_fontsize": small,
        "axes.linewidth": 0.6, "xtick.major.width": 0.6, "ytick.major.width": 0.6,
        "xtick.minor.width": 0.4, "ytick.minor.width": 0.4,
        "xtick.major.size": 3.0, "ytick.major.size": 3.0, "xtick.minor.size": 1.5, "ytick.minor.size": 1.5,
        "lines.linewidth": 1.2, "lines.markersize": 4.0, "lines.markeredgewidth": 0.5,
        "patch.linewidth": 0.6, "hatch.linewidth": 0.5, "errorbar.capsize": 2.0,
        "axes.spines.top": False, "axes.spines.right": False, "axes.grid": False,
        "axes.prop_cycle": cycler(color=list(PALETTE.values())), "image.cmap": "viridis",
        "legend.frameon": False,
        "figure.constrained_layout.use": True, "figure.facecolor": "white",
        "savefig.dpi": DPI, "savefig.bbox": "standard", "savefig.facecolor": "white",
        "pdf.fonttype": 42, "ps.fonttype": 42, "svg.fonttype": "none",
    }
    mpl.rcParams.update({key: value for key, value in style.items() if key in mpl.rcParams})
    return font_report()


# ---------------------------------------------------------------------------------------------
# Axis audit


def _is_data(transform, ax, column: int) -> bool:
    """Whether a transform maps this coordinate (0 = x, 1 = y) through the data scale."""
    try:
        return bool(transform.contains_branch_seperately(ax.transData)[column])
    except Exception:
        return False


def _zero_problem(ax, axis: str, bases: list, what: str):
    """Why marks whose length encodes a value do not show it from zero, or None when they do."""
    scale = ax.get_xscale() if axis == "x" else ax.get_yscale()
    if scale == "log":
        return f"{what} on a logarithmic {axis} axis, which has no zero: use points or a step line"
    low, high = sorted(ax.get_xlim() if axis == "x" else ax.get_ylim())
    tolerance = 1e-9 * max(abs(low), abs(high), 1e-300)
    if not any(abs(base) <= tolerance for base in bases):
        return f"{what} start at {min(bases, key=abs):g}, not at zero"
    if low > tolerance or high < -tolerance:
        return f"the {axis} axis runs from {low:g} to {high:g}, which cuts {what} off from zero"
    return None


def _area_base(vertices, t_column: int):
    """The constant edge of a filled area (its baseline), or None for a band or another shape.

    An area chart is filled between a curve and one constant; a band (an interval around a line,
    a violin) is filled between two curves, and a rectangle between two constants.
    """
    groups: dict = {}
    for row in vertices:
        if np.isfinite(row[0]) and np.isfinite(row[1]):
            groups.setdefault(round(float(row[t_column]), 12), []).append(float(row[1 - t_column]))
    values = list(groups.values())
    if len(values) < 2 or any(len(group) < 2 for group in values):
        return None
    tolerance = 1e-9 * max(max(abs(v) for v in group) for group in values) or 1e-300
    shared = []
    for candidate in values[0]:
        if all(any(abs(candidate - v) <= tolerance for v in group) for group in values[1:]) \
                and not any(abs(candidate - s) <= tolerance for s in shared):
            shared.append(candidate)
    return shared[0] if len(shared) == 1 else None


def _log_values(ax, column: int):
    """The plotted coordinates of lines, error bars and scatter points along one axis."""
    for line in ax.lines:
        if _is_data(line.get_transform(), ax, column):
            yield line.get_xdata(orig=False) if column == 0 else line.get_ydata(orig=False)
    for collection in ax.collections:
        if isinstance(collection, LineCollection) and _is_data(collection.get_transform(), ax, column):
            for segment in collection.get_segments():
                yield np.asarray(segment)[:, column]
        elif isinstance(collection, PathCollection) and _is_data(collection.get_offset_transform(), ax, column):
            offsets = np.ma.filled(np.ma.asarray(collection.get_offsets(), dtype=float), np.nan)
            if len(offsets):
                yield offsets[:, column]


def audit_axes(fig) -> list:
    """Encodings that mislead, as a list of {"rule", "axes", "detail"}; empty when none was found.

    bar_not_from_zero      bars that do not start at zero, a bar axis that excludes zero, bars on a log axis
    area_not_from_zero     the same for an area filled between a curve and a constant
    twin_axes              two axes with data on the same panel (two scales for one space)
    log_axis_nonpositive   zero or negative values on a log axis, which are silently left out

    `axes` is the index in fig.axes. A finding is a fact about the drawing, not a verdict: marks
    that show an interval and not an amount (floating range bars, shading between a curve and a
    threshold) are reported too, and are the accepted exception.
    """
    findings = []
    places: dict = {}
    for index, ax in enumerate(fig.axes):
        bases: dict = {}
        for container in ax.containers:
            if isinstance(container, BarContainer) and len(container.patches):
                axis = "x" if getattr(container, "orientation", "vertical") == "horizontal" else "y"
                bases.setdefault(axis, []).extend(
                    float(p.get_x() if axis == "x" else p.get_y()) for p in container.patches)
        for axis, values in bases.items():
            problem = _zero_problem(ax, axis, values, "bars")
            if problem:
                findings.append({"rule": "bar_not_from_zero", "axes": index, "detail": problem})

        bases = {}
        for collection in ax.collections:
            if not isinstance(collection, PolyCollection):
                continue
            for path in collection.get_paths():
                for axis, t_column in (("y", 0), ("x", 1)):
                    if not _is_data(collection.get_transform(), ax, 1 - t_column):
                        continue
                    base = _area_base(path.vertices, t_column)
                    if base is not None:
                        bases.setdefault(axis, []).append(base)
                        break
        for axis, values in bases.items():
            problem = _zero_problem(ax, axis, values, "filled areas")
            if problem:
                findings.append({"rule": "area_not_from_zero", "axes": index, "detail": problem})

        for axis, column in (("x", 0), ("y", 1)):
            if (ax.get_xscale() if axis == "x" else ax.get_yscale()) != "log":
                continue
            bad = 0
            for values in _log_values(ax, column):
                try:
                    values = np.ma.filled(np.ma.asarray(values, dtype=float), np.nan)
                except (TypeError, ValueError):
                    continue
                bad += int(np.sum(np.isfinite(values) & (values <= 0)))
            if bad:
                findings.append({"rule": "log_axis_nonpositive", "axes": index,
                                 "detail": f"the {axis} axis is logarithmic and {bad} plotted coordinate(s) "
                                           "are zero or negative: they are left out without a warning"})

        if ax.has_data():
            places.setdefault(tuple(round(v, 6) for v in ax.get_position().bounds), []).append(index)

    for members in places.values():
        if len(members) > 1:
            findings.append({"rule": "twin_axes", "axes": members[0],
                             "detail": "axes " + " and ".join(map(str, members)) + " share one panel with separate "
                                       "scales: draw two aligned panels (secondary_yaxis is fine for a unit conversion)"})
    return findings


# ---------------------------------------------------------------------------------------------
# Export


def _shown(path: Path) -> str:
    """A path relative to the working directory when it is inside it, so the record can travel."""
    path = path.resolve()
    try:
        return path.relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _file_entry(path) -> dict:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"rz_figure.save: no such file: {path}")
    content = path.read_bytes()
    return {"path": _shown(path), "sha256": hashlib.sha256(content).hexdigest(), "bytes": len(content)}


def _fonts_used(fig) -> list:
    names = set()
    for text in fig.findobj(mpl.text.Text):
        if text.get_visible() and text.get_text().strip():
            names.add(font_manager.get_font(font_manager.findfont(text.get_fontproperties())).family_name)
    return sorted(names)


def versions() -> dict:
    found = {"python": platform.python_version(), "rz_figure": __version__,
             "matplotlib": mpl.__version__, "numpy": np.__version__}
    for name in ("seaborn", "pandas", "scipy"):  # only what the plotting script imported
        module = sys.modules.get(name)
        if module is not None:
            found[name] = getattr(module, "__version__", "unknown")
    return found


def save(fig, name: str, data=(), out: str = "figures", script=None, overwrite: bool = False, quiet: bool = False) -> dict:
    """Write <out>/<name>.pdf, <name>.png (300 dpi) and <name>.figure.json; return the record.

    data       the files the figure was drawn from (hashed into the record); empty only for a diagram
    script     the plotting script; by default the file that calls save()
    overwrite  replace a PDF or PNG of this name that this module did not write

    The canvas is saved whole (never bbox_inches="tight"), so the physical size is the figsize.
    """
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", name or ""):
        raise ValueError(f"rz_figure.save: {name!r} is not a usable file name (letters, digits, '.', '_', '-').")
    directory = Path(out)
    pdf, png, record_path = (directory / f"{name}{suffix}" for suffix in (".pdf", ".png", ".figure.json"))
    ours = False
    if record_path.is_file():
        try:
            ours = json.loads(record_path.read_text(encoding="utf-8")).get("tool") == "researchzy-figures"
        except (ValueError, AttributeError):
            ours = False
    if (pdf.exists() or png.exists()) and not (ours or overwrite):
        raise FileExistsError(f"rz_figure.save: {pdf} or {png} exists and was not written by rz_figure. "
                              "Choose another name, or pass overwrite=True.")

    data_files = [_file_entry(path) for path in ([data] if isinstance(data, (str, Path)) else data)]
    if script is None:
        caller = sys._getframe(1).f_code.co_filename
        script = caller if Path(caller).is_file() else None
    directory.mkdir(parents=True, exist_ok=True)
    with mpl.rc_context({"savefig.bbox": "standard", "pdf.fonttype": 42}):
        # dpi also sets the resolution of rasterized layers inside the PDF; no creation date,
        # so the same script and data give the same bytes.
        fig.savefig(pdf, dpi=DPI, metadata={"CreationDate": None})
        fig.savefig(png, dpi=DPI)

    width, height = (float(v) * MM_PER_INCH for v in fig.get_size_inches())
    fonts = _fonts_used(fig)
    first_choice = font_report()["first_choice"]
    record = {
        "tool": "researchzy-figures", "schema_version": 1, "name": name,
        "script": _file_entry(script) if script else None,
        "data": data_files,
        "outputs": [_file_entry(pdf), _file_entry(png)],
        "size_mm": {"width": round(width, 2), "height": round(height, 2)},
        "dpi": DPI,
        "fonts": {"first_choice": first_choice, "used": fonts,
                  "fallback": bool(fonts) and first_choice not in fonts},
        "packages": versions(),
        "axis_findings": audit_axes(fig),
    }
    record_path.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if not quiet:
        print(json.dumps({"pdf": _shown(pdf), "png": _shown(png), "record": _shown(record_path),
                          "size_mm": record["size_mm"], "fonts": record["fonts"],
                          "data_files": len(data_files), "axis_findings": record["axis_findings"]},
                         ensure_ascii=False))
    return record


if __name__ == "__main__":
    print(json.dumps({"font": apply_style(), "packages": versions()}, indent=2))
