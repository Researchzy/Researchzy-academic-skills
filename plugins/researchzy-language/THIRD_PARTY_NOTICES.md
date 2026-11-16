# Third-party components

The skills of this plugin are Researchzy's own, under the [Apache License 2.0](licenses/Apache-2.0.txt), except for the parts of two scripts listed below.

## researchzy-polish scripts

Added on 2026-11-13 (version 2.2.0). `SKILL.md`, the reference files and the tests are Researchzy's
own; parts of `skills/researchzy-polish/scripts/polish_check.py` and `scripts/style_profile.py` are
derived from [Aperivue/medsci-skills](https://github.com/Aperivue/medsci-skills), commit
`4e7b3d08e0d17935644a0e281c944764da4b2601`, MIT License ([text](licenses/medsci-skills-MIT.txt),
kept beside the scripts as `LICENSE-MIT.txt`). medsci-skills is a third-party project; bundling
parts of it does not imply endorsement by its authors.

- `skills/humanize/scripts/check_rewrite_fidelity.py`: the share of changed words (taken as it
  is), the number pattern, the rule that tells a minus sign from a range, the binding of an
  inequality and of a direction word to its number, the citation patterns with page locators, and
  the detection of values or citations that traded places. Some of these reached this plugin
  through Researchzy's `researchzy-writing` (plugin `researchzy-manuscript`), which took them from
  the same file. Researchzy runs the trade detection per aligned group of sentences and added
  units, number words, scale words, currencies, author-year citations, cross-reference keys, the
  claim-strength ladder, alignment across split and merged sentences, the change-log check and the
  style profiles.

`skills/researchzy-translate/` is Researchzy's own.
