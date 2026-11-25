# What each check recognises

`thesis_audit.py check` reads every file into paragraphs (lines in LaTeX and Markdown), each with its file, line or paragraph number, part (abstract, body, appendix, references…) and chapter. Full-width digits, brackets and colons count as their ASCII forms, and a Han character next to a number is a boundary, so 样本量为321人 yields 321. The table says what fails and what is only a lead.

| Check | Fails (certain) | Lead only (inferred) |
|---|---|---|
| abbreviations | One abbreviation with two different long forms in the same language; an entry of the list of abbreviations never used in the text; an abbreviation defined in the text and missing from the list | An uppercase word used twice or more and never defined; a second definition, or a use before the definition, under the convention |
| key_numbers | A declared value missing from a declared place | Another value next to a label in a place that has the declared value |
| table_n | A declared table whose N differs, or that does not exist | Tables whose N differ (from `n-ledger.csv`) |
| floats | A callout to a figure or table with no caption of that number; a `\ref` to a missing label; a figure or table never called; two captions with one number | A gap in the numbering; numbers typed by hand in `.docx`; numbers that rest on counting because there is no `.aux` |
| citations | A cited key missing from the `.bib` or `\bibitem` list; a printed entry never cited; `[n]` with no entry n, or entry n never cited; an author-year citation with no entry of that surname and year | An entry with the same surname one year apart |
| hypotheses | A declared label absent from the results or the conclusion; a label in the results that was never declared | None |

## Abbreviations

- Definitions recognised: 技术接受模型（TAM）, technology acceptance model (TAM), 感知有用性（Perceived Usefulness，PU）, TAM（技术接受模型）, （以下简称TAM）, `\newacronym{key}{TAM}{…}`. Uses: the bare abbreviation (also glued to Han characters: 采用SEM方法), and `\ac{key}`, `\acs`, `\acl`, `\gls` for keys defined with `\newacronym`.
- The list of abbreviations is a part headed 缩略语表, 主要符号表, List of Abbreviations or similar, read as table rows or lines that start with the abbreviation; `\newacronym` entries count as the list.
- Chinese and English long forms are compared apart, because one abbreviation normally has one of each. English forms agree when they match after case, hyphens, plurals, -ing and doubled letters (modelling, modeling). The start of a Chinese term is unknown (本文采用技术接受模型), so two Chinese forms agree when one ends with the other or both end in the same three characters, with or without a tail such as 模型 or 方法. 感知有用性 and 感知易用性 differ.
- Each abstract is its own scope. Common abbreviations (DNA, ISO, USA …) and Roman numerals are never leads.

## Key numbers and table N

- A number in a citation, a float callout (表3-2) or a chapter reference (第3章) is not read as a value.
- A table's N comes from a row labelled N, n, 样本量, 有效样本, 观测值 or Observations, or from N = 312 or 样本量为312 in the table, its caption or the note under it (注：…).
- Lowercase n is a subgroup. N values in one table that add up to its largest N are subgroups (n = 148 and n = 164 with N = 312). An N in a row or note that cites a study (Davis（1989）, N = 107) is that study's sample, marked `cited study`. None of these is compared.

## Figures and tables

- Callouts: 图3-4, 表 4.3, 表3-2和表3-5, 图3-1至3-3, Figure 3.2, Fig. 3.2, Tables 3.1 and 3.2. Not callouts: 量表3, 代表5, 附表1, and entries of the table of contents or the lists of figures.
- Captions: a LaTeX `\caption`, a `.docx` paragraph with a SEQ field or a caption style (Caption, 题注), a Markdown image or `Table:` line, or a short typed line such as 表3-2 样本描述性统计 that does not read as a sentence (表3-2显示… is a sentence).
- LaTeX numbers are certain only with `--aux`, which holds the printed number of every label (`\newlabel`), following `\@input` into the `.aux` of included chapters. Without it, floats are numbered by counting per chapter; a typed callout that does not match a counted number becomes a lead, not a failure.
- In `.docx`, a number inside a REF or SEQ field is made by Word; a typed one goes stale when tables move, which is why typed numbers are a lead.

## Citations

- Keys: `\cite`, `\citep`, `\citet`, `\parencite`, `\autocite` and the rest; `\nocite`; Pandoc `[@key]` and `@key`. A `.bib` entry is printed only when it is cited or `\nocite`d (or `\nocite{*}`, or listed as `\citation` in the `.aux`); unprinted entries are counted, not failed.
- Numbered lists ([1], 1.) are checked against [n], [3-5] and [1, 4] in the text.
- Author-year: (Davis, 1989), （王明，2020；Davis，1989）, Davis (1989), Venkatesh et al. (2003), 王明（2020）, 2021a. An entry is matched by the first author's surname (a Chinese name may be preceded by other words in the sentence: 此外王明（2020）) and the year; a letter after the year must agree when both have one.
- Whether an entry exists outside the thesis is not checked here.

## Hypotheses

H1, H2a, H1–H3, H2a–H2c, 假设1, 假设H1 and Hypothesis 1 are recognised; H0 is ignored. "Stated" means present in the declared place, not supported: a results table that lists H3 as 不支持 counts as presence.

## Known limits

- One LaTeX table row per line (`a & b \\`); a row spread over lines is read only up to its first line.
- Text inside images, text boxes drawn as pictures, and equations typeset as images are not read.
- Paragraph numbers in `.docx` count every paragraph, also those in tables, the same way `check_anonymity.py` counts them.
