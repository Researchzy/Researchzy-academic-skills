# Honest encoding

These rules bind every figure. Style (fonts, colours, spacing) may follow the venue or the user's taste; these may not be traded for a better-looking picture. When the user asks for something a rule forbids, say what the rule protects, offer the honest alternative, and draw the forbidden version only if they still ask, with the caption saying what was done.

`rz_figure.audit_axes` checks the rows marked "script" from the figure object, and `check_figure.py` reports them under `axes`. The rest is checked by reading the script and the rendered figure.

## By encoding

| Encoding | Rule | Why | Checked by |
|---|---|---|---|
| Bar length | Bars start at zero and the value axis includes zero. No bars on a log axis: use points or a step line. | A bar's length is read as the amount; a cut bar shows a ratio that is not in the data. | script: `bar_not_from_zero` |
| Filled area | An area filled down to a baseline starts at zero. A band between two curves (an interval) is not an area and may sit anywhere. | Same as bars. | script: `area_not_from_zero` |
| Position (points, lines) | The axis need not include zero. Choose limits that show the data, and keep them equal across panels that are to be compared. | Position is read against the axis, not against zero. | you |
| Two scales | No second y axis with its own data. Use two aligned panels sharing the x axis. A second axis that only converts units (°C and °F) is fine. | With two scales, where the series cross and which looks larger is an artefact of the scaling. | script: `twin_axes` |
| Log axis | Say in the axis label or caption that it is logarithmic. Zero and negative values cannot be drawn: state how many there are and how they are shown (a separate mark at the axis edge, or a symmetric-log axis with its linear range stated). | The plotting library leaves them out silently. | script: `log_axis_nonpositive` |
| Size | Scale a marker's area with the value, not its radius or width. Give a size legend. | Doubling the radius quadruples the ink. | you |
| Colour scale | Sequential data: a scale that gets lighter or darker in one direction. Diverging scale only with a meaningful centre, placed at that value. Always a colour bar with units. | Uneven scales create steps the data do not have. | you |
| Axis breaks | Avoid. If one is needed, mark it on the axis and never run a bar or a line across it. | A hidden break is a hidden truncation. | you |
| Aspect | Do not stretch a panel to make a slope look steeper or flatter than in its sibling panels. | Slopes are compared by eye. | you |

Marks that show an interval and not an amount are reported by the script too: floating range bars (as in a Gantt chart) as `bar_not_from_zero`, shading between a curve and a threshold as `area_not_from_zero`. They are the accepted exception: say in the hand-over that these marks are intervals.

## Missing, excluded and transformed data

- Missing is not zero. Leave the gap: no bar, no point, a break in the line. Do not join the points on either side of a missing value, and do not fill it by interpolation unless the caption says so.
- Values recorded as "below detection limit", "ND" or "<0.1" are not numbers. Show them with their own mark at the limit, or state how many there are.
- Every observation in the data file is either drawn or accounted for: "3 of 48 excluded (recording failed)". Exclusions are decided before plotting and written in the script, with the reason.
- No silent sampling. If only part of a large data set is drawn, the caption says which part and how it was chosen.
- Smoothing, binning, normalisation and log transforms are stated with their parameters (window, bin width, reference group).
- Outliers stay in the figure. If the axis is limited to exclude one, mark that it lies off-scale and give its value.

## n, units and summaries

- State n for every group, in the figure or the caption, and say what n counts: subjects, samples, runs, not rows.
- Technical replicates are not n. Combine them per unit first, or draw them as small marks under the unit's mark.
- A summary mark (mean, median) is named. An error bar or band is named: standard deviation, standard error, confidence interval with its level, or interquartile range. An unnamed error bar is an error.
- Use the same summary and the same error-bar definition in panels that are compared.
- With few points (under 10 per group), draw the points; a summary may be added but does not replace them.
- Significance marks, the choice of test and the wording of the error-bar definition are handed to `researchzy-stats-review`. Do not add stars from a test you ran yourself unless the user asked for that test.

## Never

- Never change, drop, move or add a data value to improve the picture.
- Never type numbers into the plotting script. The script reads the data file; a number that is not in a file does not go into a figure.
- Never draw invented or "example" data in a figure meant for a manuscript. A placeholder figure carries the word "placeholder" in its file name and on the canvas.
- Never rebuild raw data from a published summary (points simulated from a mean and an SD).
- Never present a selected run, cell or image as "representative" without saying how it was selected.

## Testing the caption against the rows

Before handing over, read each statement of the caption and of any title-like text in the figure, and check it against every plotted row, not against the overall impression:

1. "A is higher than B": true for which rows? If it holds on average but not for every unit, say "on average" or "in 10 of 12 subjects".
2. Every number in the caption (n, percentages, medians) is recomputed from the data file by the script or by a command, not copied from an earlier draft.
3. Group names, units and the order of panels in the caption match the figure.
4. What was held fixed and what varied is stated when panels show different conditions.
5. The caption says what a point is, what the summary mark is and what the error bars are, and names anything left out.

A caption that fails a test is reworded to what the rows support. The figure is not adjusted to fit the caption.
