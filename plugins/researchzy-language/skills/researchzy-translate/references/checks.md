# What tr_check.py compares

`tr_check.py check` splits the source and the translation the way `tr_units.py` does and pairs the units in order. When both files split into the same sequence of unit types, unit k of one is unit k of the other. When they do not (a paragraph was added, merged or split, or the output was edited by hand), units are matched on their type, citations, formulas and numbers, and the rest are listed as **not compared**: read them yourself, and prefer to regenerate the output with `unmask`, which keeps the structure.

Each finding names the source unit (`u0007` is the id in `units.json`) and its line, or "translation u0002" for a unit that exists only in the translation, and quotes both texts. Formulas, citations and other tokens are taken out before numbers, dates and words are read, so the year in `\cite{liu2022}` or a number inside `$…$` is never compared as prose.

## Errors

| Check | What must match in each pair of units | Known false alarms |
|---|---|---|
| `numbers` | Every number with its value, its percent sign, a unit symbol written after it (5 mg, 37 °C, 10 ms, mg/kg) and a bound before it (<, >, ≤, ≥). Full-width digits and thousands separators are normalised; 万, 亿, thousand, million and billion are multiplied out, so 1.2万 equals 12,000; "37–40%" is read as 37% to 40%. A number glued to Han characters counts (共纳入37名); one inside a name does not (COVID-19, IL-6, H2O, 3D) | A list written "1,2" without a space is not read on either side, so a change inside it goes unseen |
| `dates` | Dates compared as dates: 2024年3月15日 = 15 March 2024 = March 15, 2024 = 2024-03-15; 2024年3月 = March 2024; 3月15日 = 15 March. A year alone is a number. "may" the verb is never a date | 1月龄 (one month of age) is read as January |
| `citations` | `\cite`-family keys, `[@key]`, `@key` (also glued to Han characters) and numbered citations in half- or full-width brackets; [1–3] equals [1, 2, 3], and ［1，2］ equals [1, 2] | A citation note in `\cite[第3页]{key}` stays untranslated, because the whole command is one token |
| `latex` | The multiset of LaTeX command names, the keys of `\ref`, `\eqref`, `\cref`, `\label` and similar, and, in `.tex` files, the balance of `{` and `}` in each unit against the source's | — |
| `maths` | Every formula (`$…$`, `$$…$$`, `\(…\)`, `\[…\]`, maths environments) and every code span, byte for byte | A formula retyped with different spacing is reported: copy it, do not retype it |
| `placeholders` | `[Evidence needed: …]`, `[Citation needed: …]`, `[Author input needed: …]`, by type and count | — |
| `links` | URLs and DOIs, ignoring case and trailing punctuation | — |
| `figures` | Figure, table and equation numbers: 图2 = Figure 2 = Fig. 2; 图2和图3 = Figures 2 and 3; 图2-4 = Figures 2–4; 附表1 = Table S1 = Supplementary Table 1; 式(3) = Eq. (3) = Equation (3). 代表, 发表, 试图 and similar words are not references | A reference made with `\ref` carries no number in the text and is compared by its key under `latex` |

## Warnings

| Check | What it reports | Tolerated false alarms |
|---|---|---|
| `numbers` | A number that is a word on the other side (3组 → three groups, Twelve → 12名); the same value with a different minus sign, precision (0.50 → 0.5), unit symbol only on one side, or bound only on one side | 5 mg → 5毫克 warns although it is right: the unit word is not read |
| `glossary` | A term without its agreed translation; a term marked `=` that was translated; one translation for two terms; an incomplete row. Not checked without `--glossary` | A term that needs another sense in one sentence: keep it and write a note |
| `length` | A unit whose ratio of translation length to source length (characters without spaces) is under half or over twice the median ratio of the document. Only units with 30 or more source characters count; fewer than three such units: not checked. These thresholds are working values | A unit that is mostly names, numbers or a list |
| `negation` | Different numbers of negations: 不, 未, 没有, 无, 非, 否, 并非, 勿 against not, no, never, none, neither, nor, without, cannot, unable, unlikely, insufficient, absent, lack, fail to, n't. Compounds that are not negations in English are left out (不同, 不断, 不仅, 非常, 无论, 是否, 未来, 非线性, 无症状). Chinese and English only | A negation that English carries in a prefix (不确定 → uncertain, 不一致 → inconsistent) |
| `hedges` | Different numbers of hedges and approximations: 可能, 或许, 也许, 似乎, 大概, 约, 左右, 提示, 推测, 倾向于, 初步, 潜在 against may, might, could, possibly, likely, perhaps, potential, seem, appear, suggest, approximately, about or around before a number, roughly, nearly, almost, tend to, preliminary, ~. Added hedges are reported as well as lost ones, because both change the claim. Chinese and English only | 提示 → indicate; "could" meaning ability ("could not be reached") |
| `script` | Han characters or full-width punctuation left in a translation into English or another Latin-script language; five or more lowercase Latin words in a row in a translation into Chinese, Japanese or Korean (capitalised words, such as names, are not counted). Not checked for other targets | A Chinese name kept beside its romanisation; an English title kept in a Chinese text; Chinese cell text in a kept LaTeX table (it is not a unit; see SKILL.md step 2) |
| `commentary` | Words addressed to the reader: "Here is the translation", "Translation:", "I hope this helps", 以下是译文, 译文如下 | A heading that really is "Translation:" |

## Other language pairs

`--pair` takes two language codes, source first (`ja-en`, `de-zh`). Numbers, dates (Chinese, Japanese and English date forms), citations, LaTeX, formulas, placeholders, links and figure numbers are checked for every pair. Negations and hedges are counted only for Chinese and English. For targets that write decimals with a comma (de, fr, es, it, pt, nl, ru and others), "3,5" is read as 3.5 on that side. Do not report a pair as fully checked when the report says a check was not run.

## What no script checks

- Whether the translation is right, idiomatic and complete inside a sentence: a clause dropped from a long sentence passes when it held no number, citation, term or counted word.
- A change of meaning that keeps every number, citation and term: "higher" for "lower", a wrong subject, a scope widened from the sample to everyone.
- Numbers written as words on both sides, and units written as words.

So after the script, read each pair of the bilingual table once, slowly, for claims. The script proves the invariants; the reading checks the meaning.
