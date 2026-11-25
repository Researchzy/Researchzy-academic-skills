# Third-party components

The skills of this plugin are Researchzy's own, under the [Apache License 2.0](licenses/Apache-2.0.txt), except for the parts of the scripts listed below. All of them come from [Aperivue/medsci-skills](https://github.com/Aperivue/medsci-skills), commit `4e7b3d08e0d17935644a0e281c944764da4b2601`, MIT License ([text](licenses/medsci-skills-MIT.txt), Copyright (c) 2026 Aperivue), and each skill keeps the license beside its scripts as `scripts/LICENSE-MIT.txt`. medsci-skills is a third-party project; bundling parts of it does not imply endorsement by its authors.

Added on 2026-11-18 (version 2.3.0).

## researchzy-psychometrics and researchzy-path-models scripts

- `scripts/rz_results.py` and `scripts/check_results.py` are copies of the files of the same name in `researchzy-statistics` (plugin `researchzy-manuscript`), unchanged. That plugin's notices list their derivation from `skills/analyze-stats/scripts/run_analysis.py` and `skills/analyze-stats/scripts/check_generated_code.py`.
- Their other scripts are Researchzy's own.

## researchzy-qualitative scripts

- `scripts/quote_match.py` is a copy of the file of the same name in `researchzy-reference-check` (plugin `researchzy-manuscript`), unchanged. That plugin's notices list its derivation from `skills/verify-refs/scripts/_quote_match.py`.
- `scripts/qual_ledger.py` and `scripts/rz_agreement.py` are Researchzy's own.

## researchzy-survey and researchzy-text-as-data

All of their files are Researchzy's own. `researchzy-text-as-data/scripts/rz_agreement.py` is a copy of the file of the same name in `researchzy-qualitative`, unchanged.
