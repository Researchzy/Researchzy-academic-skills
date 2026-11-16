# Third-party components

The skills of this plugin are Researchzy's own, under the [Apache License 2.0](licenses/Apache-2.0.txt), except for the parts of the scripts listed below. All of them come from [Aperivue/medsci-skills](https://github.com/Aperivue/medsci-skills), commit `4e7b3d08e0d17935644a0e281c944764da4b2601`, MIT License ([text](licenses/medsci-skills-MIT.txt), Copyright (c) 2026 Aperivue), and each skill keeps the license beside its scripts as `scripts/LICENSE-MIT.txt`. medsci-skills is a third-party project; bundling parts of it does not imply endorsement by its authors.

Added on 2026-11-13 (version 2.2.0).

## researchzy-meta-analysis scripts

- `scripts/rz_results.py` and `scripts/check_results.py` are copies of the files of the same name in `researchzy-statistics` (plugin `researchzy-manuscript`), unchanged. That plugin's notices list their derivation from `skills/analyze-stats/scripts/run_analysis.py` and `skills/analyze-stats/scripts/check_generated_code.py`.
- `scripts/effect_sizes.py`: from `skills/meta-analysis/scripts/check_ratio_ci_symmetry.py`, the reading of a printed ratio and its interval, the bound on log-scale asymmetry that rounding of the printed values can explain, and the test for an impossible interval. Researchzy refuses an impossible interval instead of reporting it, reports asymmetry as a warning, and returns the log ratio and its variance for pooling.
- `scripts/meta_pool.py` and `scripts/check_meta.py` are Researchzy's own.

## researchzy-risk-of-bias scripts

- `scripts/quote_match.py` is a copy of the file of the same name in `researchzy-reference-check` (plugin `researchzy-manuscript`), unchanged. That plugin's notices list its derivation from `skills/verify-refs/scripts/_quote_match.py`.
- `scripts/rob_check.py`, `scripts/sof_check.py` and `scripts/rob_plot.py` are Researchzy's own.

## researchzy-systematic-review

All of its files are Researchzy's own.
