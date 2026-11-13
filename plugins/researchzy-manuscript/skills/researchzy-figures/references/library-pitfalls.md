# matplotlib and seaborn: what goes wrong

Not a manual. These are the mistakes that produce a figure of the wrong size, with unreadable text, or with marks that mean something other than the caption says. The matplotlib items were checked with matplotlib 3.10; the seaborn items describe seaborn 0.13.

## Size and layout (matplotlib)

| Mistake | What happens | Do instead |
|---|---|---|
| `savefig(..., bbox_inches="tight")` | The canvas is cropped to the ink: the file is no longer the width that was asked for, and its text is rescaled when it is placed | Never pass it. `rz.save` saves the whole canvas; let the layout engine use the space |
| `plt.subplots()` with the default `figsize` | A 6.4 × 4.8 in canvas (163 × 122 mm), then shrunk in the manuscript | `figsize=rz.figsize_mm(width_mm, height_mm)` |
| `fig.tight_layout()` or `subplots_adjust()` after `apply_style()` | `apply_style()` turns on constrained layout. `tight_layout()` replaces it; `subplots_adjust()` is ignored with a warning | Call neither. Constrained layout already fits labels, legends and colour bars |
| A legend that covers data | Hidden points | `fig.legend(loc="outside upper right")` (works with constrained layout), or label the lines directly |
| Text placed by hand in figure coordinates | Cut at the canvas edge without warning | `ax.annotate` in axes coordinates; look at the PNG |
| `ax.set_xticklabels(labels)` alone | Labels attached to whatever ticks exist: wrong labels after a limit change | `ax.set_xticks(positions, labels)` |
| `plt.show()` in a script | Blocks or fails without a display | `matplotlib.use("Agg")` before importing `pyplot`; only save |

## Text and fonts (matplotlib)

| Mistake | What happens | Do instead |
|---|---|---|
| Assuming Arial is there | On Linux it usually is not; matplotlib falls back without an error, and with DejaVu Sans the labels are wider | Read the font that `apply_style()` returns and `save()` records |
| `"$R^2$"`, `"mL$^{-1}$"`, log-axis tick labels | Sub- and superscripts are drawn at 0.7 of the text (0.49 on the second level): 4.9 pt on a 7 pt label | Keep text with scripts at 7.2 pt or more for a 5 pt floor, or write "per mL" |
| Default `pdf.fonttype` (3) | Type 3 fonts in the PDF: rejected by many submission systems, not editable | `apply_style()` and `rz.save` set 42 |
| `ax.set_title("Results of ...")` | A title inside the figure repeats the caption | Use the title only for panel labels |
| `fontsize="small"` and other relative sizes | Sizes drift from the style | Leave sizes to the style, or give points |

## Marks and data (matplotlib)

| Mistake | What happens | Do instead |
|---|---|---|
| `ax.errorbar(x, y, yerr=upper_limit)` | `yerr` is a distance from the point, not the end of the bar | `yerr=[y - low, high - y]` for an interval given by its ends |
| `ax.bar` with `set_ylim(bottom > 0)` or `set_yscale("log")` | Bars that do not start at zero | Points; `audit_axes` reports it |
| `ax.twinx()` to add a second measure | Two scales in one panel | `plt.subplots(2, 1, sharex=True)` |
| A log axis with zeros or negative values | They disappear without a warning, and an error bar that reaches zero is cut | Count them first; see [honest-encoding.md](honest-encoding.md) |
| `dropna()` or `interpolate()` before `ax.plot` | The line runs straight across the gap | Keep the NaN: matplotlib breaks the line there |
| Marker `s=` in `scatter` taken as a diameter | `s` is an area in points squared | Pass an area proportional to the value |
| `ax.hist(values)` | Ten bins, whatever the data | Choose the bins (`bins="fd"` or explicit edges) and state the width |
| `ax.boxplot(..., labels=...)` | Renamed `tick_labels` in 3.9 | `tick_labels=` |
| `matplotlib.cm.get_cmap("viridis")` | Deprecated since 3.7 | `matplotlib.colormaps["viridis"]` |
| A scatter of 50,000 vector points | A PDF of many megabytes that opens slowly | `rasterized=True` on that layer |
| The default colour cycle (`tab10`) | Red and green, and blue and purple, merge for readers with a colour-vision deficiency | `apply_style()` sets the palette; pass colours from `rz.PALETTE` |

## seaborn

| Mistake | What happens | Do instead |
|---|---|---|
| `sns.set_theme()` after `rz.apply_style()` | seaborn overwrites fonts, sizes, grid and palette | Do not call it, or call `rz.apply_style()` after it |
| Figure-level functions (`relplot`, `catplot`, `displot`, `lmplot`, `pairplot`, `jointplot`) | They make their own figure, sized by `height` and `aspect` in inches | Axes-level functions with `ax=ax` (`scatterplot`, `boxplot`, `stripplot`, `lineplot`, `histplot`, `ecdfplot`) |
| `barplot`, `pointplot`, `lineplot` with default error bars | The bar is a bootstrapped 95% confidence interval of the mean, not an SD or SEM, and changes from run to run | Set it and say it: `errorbar="sd"`, `"se"`, `("ci", 95)`, `("pi", 50)` or `None`; add `seed=1` for a bootstrap. `ci=` is the old name and is deprecated |
| `lineplot` on repeated measures | Rows with the same x are averaged into one line | `units="subject", estimator=None` for one line per unit |
| `lineplot` with missing values | Rows with NaN are dropped, so the line bridges the gap | Plot with matplotlib, or draw each unbroken stretch separately |
| `palette=` without `hue=` | Deprecated in 0.13 | `hue=` the same variable and `legend=False` |
| Numbers on the x axis of `boxplot`, `stripplot`, `barplot` | Treated as categories: evenly spaced, whatever their values | `native_scale=True` |
| `violinplot(scale=...)`, `bw=` | Renamed in 0.13 | `density_norm=`, `bw_method=` or `bw_adjust=` |
| `kdeplot` and violins on bounded data | The curve extends past the smallest and largest value (`cut` defaults to 3 for `kdeplot`, 2 for `violinplot`) | `cut=0`, or an ECDF |
| `histplot` or `kdeplot` with `hue=` | Densities are normalised over all groups together (`common_norm=True`), so a small group looks flat | `common_norm=False` to compare shapes |
| `stripplot` | The jitter is random: the figure differs on every run | `np.random.seed(1)` before it, or `swarmplot` |
| `boxplot` under a `stripplot` | Outliers are drawn twice | `showfliers=False` in the box plot |

## Before export

- The script reads the data file named in `rz.save(..., data=[...])` and contains no typed-in values.
- One `rz.save` per figure; no other `savefig` for the PDF or PNG.
- Random steps (jitter, bootstrap, subsampling) have a fixed seed, so that running the script again gives the same figure.
