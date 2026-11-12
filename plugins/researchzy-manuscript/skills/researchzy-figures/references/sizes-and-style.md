# Sizes and style

A figure is drawn at the size it is printed. Everything below is a default: the venue's author guidelines win, then the user's wishes. The rules in [honest-encoding.md](honest-encoding.md) are not defaults.

## Widths

Values collected in November 2026. Venues change them: confirm the width against the venue's current author guidelines or its template before drawing, and tell the user which value you used and where it came from.

| Venue | One column (mm) | Middle (mm) | Full width (mm) | Note |
|---|---|---|---|---|
| Nature journals | 89 | 120–136 | 183 | Page height 247 mm |
| Science | 57 | 121 | 184 | Three-column page; some guides give 55 / 120 / 183 |
| Cell Press | 85 | 114 | 174 | |
| Elsevier journals | 90 | 140 | 190 | |
| PNAS | 87 | 114 | 178 | |
| IEEE journals | 88.9 (3.5 in) | | 182 (7.16 in) | |
| BMC | 85 | | 170 | |
| NeurIPS, ICLR | | | 139.7 (5.5 in) | One text column |
| ICML | 82.6 (3.25 in) | | 171.5 (6.75 in) | |
| AAAI | 83.8 (3.3 in) | | 177.8 (7.0 in) | |

- **No venue yet:** draw at 89 mm, or 183 mm for a multi-panel figure, and say so. Most layouts take these with little change.
- **LaTeX manuscript:** measure instead of looking up. Put `\the\columnwidth` (or `\the\textwidth`) in the document, compile, and convert the printed TeX points: mm = pt × 0.3515.
- **Height:** as small as the content allows, and under the page height minus room for the caption. Start from a height of 0.6 to 0.75 of the width for one panel.
- **In the manuscript:** include the file without scaling (`\includegraphics{figures/fig1.pdf}`). With `width=\columnwidth` LaTeX rescales the figure and its text with it; a figure drawn at 120 mm and placed in an 89 mm column has its 8 pt text printed at 5.9 pt. `check_figure.py --width-mm` judges the text at the width given.

## Text

| Item | Default in `apply_style()` | Range venues ask for |
|---|---|---|
| Font | Arial, then Helvetica, Liberation Sans, Nimbus Sans, DejaVu Sans | A sans-serif face; some ask for the body font |
| Axis labels, annotations | 8 pt | 7–9 pt |
| Tick labels, legend | 7.5 pt | 6–8 pt |
| Panel labels | 8 pt bold, top left, outside the plot area: `ax.set_title("a", loc="left", fontweight="bold")` | Lowercase or uppercase by venue |
| Smallest text anywhere | 5 pt at print width (`--min-pt 5`) | 5–7 pt; raise `--min-pt` to the venue's value |

- Every glyph counts, including sub- and superscripts and exponents on a log axis, which matplotlib draws at 0.7 of their text. For a 5 pt floor, text that carries a script must be 7.2 pt or more; that is why the tick default is 7.5 pt. `apply_style(font_pt=7)` gives 7 and 6.5 pt, and then scripts fall under 5 pt.
- The first font that exists on the machine is used. `apply_style()` returns it and `save()` records it under `fonts`. Arial is absent on most Linux machines; Liberation Sans has the same letter widths, DejaVu Sans is wider and can make labels collide. Tell the user when a fallback was used.
- No title inside the figure: the caption carries it. Axis labels name the quantity and its unit: "Sleep latency (min)".
- For another font, change the list before drawing: `matplotlib.rcParams["font.sans-serif"] = ["Helvetica Neue", *rz.FONTS]`.

## Lines and marks

| Item | Default | Keep within |
|---|---|---|
| Axes and ticks | 0.6 pt | 0.5–0.8 pt |
| Data lines | 1.2 pt | 1.0–1.5 pt |
| Markers | 4 pt | 3–4 pt |
| Error bars | 0.6–0.9 pt, caps 2 pt | |
| Any line | | Not under 0.25 pt: thinner lines can vanish in print |

Top and right spines are off, there is no grid, and the legend has no frame. Add a grid only when the reader must read values off the plot, in light grey at 0.4 pt.

## Colour

The palette is Okabe and Ito's eight colours, built to stay distinct under the common colour-vision deficiencies. `rz.PALETTE` holds them in this order:

| # | Name | Hex | Lightness L* |
|---|---|---|---|
| 1 | blue | `#0072B2` | 46 |
| 2 | orange | `#E69F00` | 71 |
| 3 | bluish green | `#009E73` | 58 |
| 4 | black | `#000000` | 0 |
| 5 | vermillion | `#D55E00` | 54 |
| 6 | sky blue | `#56B4E9` | 70 |
| 7 | reddish purple | `#CC79A7` | 61 |
| 8 | yellow | `#F0E442` | 89 |

- The first four also differ in lightness by 10 or more, so they survive a grayscale print. From the fifth on they do not: orange and sky blue, or vermillion and bluish green, print as one grey.
- **Second cue.** Whenever a figure has more than one series, separate them by something besides colour: marker shape, line style, hatching, or a label placed at the line. `rz.series_style(i)` returns colour, marker and line style together: `ax.plot(x, y, **rz.series_style(i))`. The checker cannot see the second cue, so a `grayscale` FAIL stays in its report; name the cue when you report it.
- Yellow is too light for thin lines and text on white. Use it for fills.
- The same group has the same colour in every panel and every figure of the manuscript.
- Colour only what the message is about. Context series go in grey (`"0.6"`).
- Continuous values: `viridis` (the default) or `cividis`. Diverging values: a diverging map centred on the reference value with `matplotlib.colors.TwoSlopeNorm(vcenter=...)`. Never `jet` or `rainbow`.
- More than eight groups do not get eight more colours: see [chart-selection.md](chart-selection.md).

## File formats

| File | When | How |
|---|---|---|
| PDF, vector | Always: the file for the manuscript | `rz.save`; fonts embedded as TrueType (`pdf.fonttype 42`), never Type 3 |
| PNG, 300 dpi | Always: the file to look at, and for slides and web | `rz.save` |
| TIFF | Only when the submission system demands it | From the PNG: `Image.open(png).convert("RGB").save(tiff, compression="tiff_lzw", dpi=(300, 300))` with Pillow; no alpha channel |
| SVG or EPS | Only on request | `fig.savefig("figures/fig1.svg")` after `rz.save`; never with `bbox_inches="tight"` |

- Line art saved as a raster needs 600 dpi or more to stay sharp; that is the reason to submit vector files.
- Dense layers (tens of thousands of points) inside a vector file: pass `rasterized=True` for that layer. `rz.save` renders it at 300 dpi.
- Photographs and micrographs keep their own pixels: place them with `imshow(..., interpolation="none")` and check that the print width gives 300 dpi or more.
- Run `check_figure.py` on every file that will be submitted, including a converted TIFF.
