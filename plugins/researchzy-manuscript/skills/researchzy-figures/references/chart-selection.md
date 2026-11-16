# Choosing the chart

Choose from three things, in this order: the comparison the message makes, the `design` in the profile, and the n per group. The chart type the user named is a starting point; if the profile rules it out, say why and propose the replacement before drawing.

## From the data to a chart

| The data | The message is about | Draw | Keep in mind |
|---|---|---|---|
| Independent groups, n under 5 per group | values in each group | Every point, with a short line at the median or mean | No box, bar or error bar: there is nothing to summarise |
| Independent groups, n 5 to 9 | values in each group | Every point with a median or mean line; a box only underneath the points | Jitter sideways only, never along the value axis |
| Independent groups, n 10 to 29 | values in each group | A box plot with the points on top, or points with the mean and its interval | Say what the box, whiskers and interval are |
| Independent groups, n 30 or more | the distributions | Box plot, violin with quartile lines, ECDF, or histogram | Give the bin width or the bandwidth |
| `paired`: the same units under two conditions | the change within a unit | A line joining each unit's two values, or the differences as points against a zero line | Units with one value are shown apart or reported as left out |
| `repeated_over_time`, up to about 30 units | trajectories | One thin line per unit, the group summary on top | The same unit keeps its line; do not pool rows |
| `repeated_over_time`, many units | the trend | A summary line with an interval band, n stated per time point | Name the interval; mark where n changes |
| `replicates`: several rows per unit and condition | values per unit | One value per unit, or small points for rows nested under a larger point per unit | n is the number of units |
| Two numeric measures | their relation | Scatter plot; above 5,000 points hexagonal bins or a 2D density | A fitted line only with the model named |
| One numeric measure, one group | its distribution | Histogram or ECDF | A histogram depends on its bins; an ECDF does not |
| Counts or proportions per category | amounts | Bars from zero or a dot plot, sorted by value unless the categories have an order | Give the denominator with a proportion |
| Parts of a whole | composition | One stacked bar per whole, five parts at most | Only the bottom part has a common baseline |
| Composition over time | how shares shift | Stacked areas from zero, or one small panel per part | |
| Categories by conditions, many cells | a pattern across a matrix | Heatmap with a perceptually uniform scale and a labelled colour bar | A diverging scale only around a meaningful centre |
| Estimates with intervals for several outcomes or studies | effect sizes | Forest plot: a point and an interval per row, a reference line | Order the rows by a stated rule |
| One row per group (summaries only) | reported values | Points or bars of the given values; error bars only from a column that states them | Do not rebuild a distribution from a mean and an SD |
| Positive values spanning two orders of magnitude, or skewed | values across groups | A log axis, or median and interquartile range | Zeros and negatives cannot go on a log axis: say how they are shown |
| Counts of participants or samples through a study | who was kept and why | Flow diagram ([diagrams.md](diagrams.md)) | The counts must add up |

## Use this instead of that

| Instead of | Use | Why |
|---|---|---|
| A bar of means, with or without error bars | Points, box with points, or an ECDF | Very different data give the same bar; the bar's length says nothing about spread |
| Mean with SD or SEM for skewed data | Median with interquartile range, or a log axis | The mean follows the tail, and mean minus SD can fall below the smallest value |
| Side-by-side groups for paired data | Paired lines or a plot of differences | The pairing is the evidence; unlinked groups hide it |
| A violin or density curve for fewer than 30 values | Points, a box with points, or an ECDF | With few values the shape is the smoothing, not the data |
| A density curve for bounded data (counts, percentages, times) | ECDF or histogram | The curve runs past the limits into values that cannot occur |
| A pie or donut chart | Sorted bars, or one stacked bar | Angles and arcs are compared poorly |
| A radar chart | A table, a dot plot, or small multiples | The enclosed area changes with the order and scaling of the axes |
| Two y axes on one panel | Two aligned panels that share the x axis | Where the lines cross depends only on how the two scales were chosen |
| 3D bars or perspective | The same data in 2D | Depth hides marks and distorts lengths |
| A scatter of more than 5,000 opaque points | Hexagonal bins, a 2D density, or small transparent rasterized points | Overprinting hides where most points are |
| A rainbow colour scale | viridis or cividis; a diverging scale around a real centre | Rainbow scales show boundaries the data do not have |
| Stacked bars to compare the inner parts | Grouped dots or one small panel per part | Parts without a common baseline cannot be compared |
| A line through unordered categories | Points or bars | A line claims the values in between exist |
| More than about seven lines with a legend | Direct labels, small multiples, or colour for the few lines the message is about and grey for the rest | A long legend makes the reader match colours one by one |
| Bars with stars for significance | Points with the effect size and its interval | A star shows that a test was run, not how large the effect is; tests belong to `researchzy-stats-review` |
| A bar axis cut above zero "to show the difference" | Points, which may start anywhere, or a plot of the difference itself | A cut bar shows a ratio that is not there |
| A heatmap of ten numbers or fewer | A table | The reader wants the numbers |

## When a table is better than a figure

Use a table when:

- the reader will need the exact values, to reuse them or compare them with their own;
- there are about six numbers or fewer: a sentence or a small table carries them;
- the rows have different units or kinds of measure, so no shared axis exists;
- the results are methods by datasets and the message is which method does best where. Mark the best value per column and say how it was chosen.

Use a figure when the message is a shape: a trend, a distribution, a relation between two measures, an interaction. Do not show the same numbers as both unless the venue asks for it.

## What the profile rules out

`profile_data.py` lists charts under `ruled_out` with these thresholds. They are this skill's working values; a field with a stricter convention overrides them.

| Condition in the profile | Ruled out |
|---|---|
| Smallest group has n under 5 | Bars of means, box plots, violins, density curves |
| Smallest group has n 5 to 9 | Bars of means, violins, density curves |
| Smallest group has n 10 to 29 | Violins, density curves |
| One row per group | Any distribution or error bar computed from the file |
| `paired` | Independent-groups plots |
| `repeated_over_time` | One pooled line or scatter over all rows |
| `replicates` | Any plot or n that counts rows as independent observations |
| Skewness of 1 or more in absolute value (n of 8 or more), or positive values spanning a factor of 100 | Mean with SD or SEM on a linear axis |
| A group column with more than 8 levels | One colour per level |
| More than 5,000 rows | A scatter of single opaque markers |

n counts units when the profile has an id column, rows otherwise. A ruled-out chart is drawn only when the user asks for it after hearing the reason; the caption then states n and what the marks are.
