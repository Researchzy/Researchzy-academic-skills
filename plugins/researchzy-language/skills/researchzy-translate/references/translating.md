# Translating a unit

## What comes first

When two aims pull apart, the earlier one wins:

1. **What is claimed**: the quantity, the population, the direction of an effect, the condition it holds under.
2. **How strongly it is claimed**: hedges, negations, quantifiers, association against cause.
3. **The agreed terms** of `terms.tsv`.
4. **The structure**: units, lists and table rows stay where they are; sentences inside a unit may be split or joined.
5. **Fluency** in the target language.

A fluent sentence that moves a claim is a wrong translation. A stiff sentence that keeps it is a draft that `researchzy-polish` (same plugin, when installed) can smooth later without touching the claim.

## Claims and their strength (Chinese and English)

| Source | Translate as | Never as |
|---|---|---|
| 相关, 关联, 与…有关 | associated with, correlated with, related to | caused, led to, increased the risk (unless the source says so) |
| 导致, 引起, 使…增加 | caused, led to, increased | was associated with (that weakens the author's claim) |
| 可能, 或许, 也许 | may, might, possibly | (dropped), will, can |
| 提示, 似乎 | suggest, appear, seem | show, prove, demonstrate |
| 表明, 显示 | show, indicate | prove, confirm |
| 证实, 证明 | confirm, demonstrate | suggest |
| 约, 大约, 左右, 近 | approximately, about, nearly | (dropped) |
| 显著 with a test reported | statistically significant(ly) | — |
| 显著 without a test | marked(ly), substantial(ly) | significant (a reader takes it as a test) |
| 未见差异, 差异无统计学意义 | no significant difference was found; not statistically significant | there was no difference (a non-significant test is not evidence of no difference) |
| 不能排除 | cannot be ruled out | is excluded |
| 部分, 一些 | some, part of | most, the majority |
| 均, 全部 | all, each (check what "all" ranges over) | most |

The same table read from right to left covers English into Chinese: may → 可能, suggest → 提示, approximately → 约, was associated with → 与…相关.

When the source overclaims (a causal verb for an observational design, "significant" without a test), translate the claim as written and add a note; the author decides. Tense carries a claim too: a finding of this study stays in the past tense; moving it into the present generalises it beyond the sample.

## Chinese into English

- **Missing subjects.** Supply the subject the context gives (we, the participants, the authors of a cited study). When the context does not settle it, choose the likeliest and add a note.
- **Long comma-joined sentences.** Split them where the subject or the logic changes. Every clause survives the split; check the count.
- **Singular or plural, a or the.** Decide from the context (患者 in a sample of 37 is "patients"). If nothing decides it, note the choice.
- **Verb hidden in a noun.** 对数据进行了分析 is "the data were analysed", not "an analysis was conducted on the data".
- **等 at the end of a list.** It may close a complete list or mark examples. Write "such as" or "and others" only when the context shows the list is open.
- **Numbers and units.** Keep the digits and units of the source. Never convert units or round. 1.2万 is 12,000, 3亿 is 300 million; the checker reads both forms.
- **Dates.** 2024年3月15日 is "15 March 2024" in British style and "March 15, 2024" in American style; follow the journal.
- **Punctuation.** Replace Chinese punctuation (，。；：“”（）《》、) with English punctuation. The checker reports full-width punctuation left in English text.
- **Abbreviations.** Define each at its first use, as `terms.tsv` gives it: "time-restricted eating (TRE)".

## English into Chinese

- **Passive voice.** Prefer an active sentence or a sentence without a subject; keep the agent when the source names it.
- **Long noun phrases and relative clauses.** Reorder them into Chinese order; keep every modifier.
- **First use of a term.** 中文术语（English term, ABBR） at the first use, as `terms.tsv` gives it, and the Chinese term afterwards.
- **Numbers.** Keep the digits. "1.2 million" may become 120万 or 1,200,000, following the target journal; the checker reads both.
- **Punctuation.** Full-width punctuation in Chinese sentences; half-width inside formulas, citations and URLs.
- **English left behind.** A whole English clause left in the Chinese text is reported. Names kept in English (instruments, software, models) are not.

## The units file

`translation/units.translated.json` maps each unit id of `units.json` to its translated masked text:

```json
{
  "u0003": "From March 2023 to June 2024, 37 patients were enrolled, of whom 12 (32.4%) were women ⟦T0001⟧. Sleep quality was assessed with the ⟦T0002⟧Pittsburgh Sleep Quality Index⟦/T0002⟧ ⟦T0003⟧.",
  "u0004": "⟦T0004⟧ethics approval number⟦/T0004⟧"
}
```

- Tokens may move: Chinese and English order clauses differently. Each token still appears exactly once.
- A pair encloses the translation of what it enclosed in the source: ⟦T0002⟧…⟦/T0002⟧ was `\textbf{…}` around the instrument's name, ⟦T0004⟧…⟦/T0004⟧ is `[Author input needed: …]`.
- Headings, table rows and captions are one line each; `unmask` joins their lines.
- A unit you cannot translate stays out of the file and is reported as missing; say why in the notes.
- Translate in order, about 30 units per batch (a convention). Before each batch, reread the last few translated units, so that pronouns, tense and terms run on. After the last batch, read the whole output once from the top.

## Translator's notes

`translation/notes.md` is one table, one row per note:

```markdown
| Unit | Kind | Note |
|---|---|---|
| u0007 | source error | The text gives 37 patients, Table 1 gives 36. Translated as 37. |
| u0012 | glossary | 效应 rendered as "effect size", not "effect": the sentence reports a statistic. |
| u0015 | ambiguity | 他们 may mean the investigators or the participants; read as the participants. |
| u0019 | check warning | Negation count differs: 不确定 is rendered "uncertain", which the script does not count as a negation. |
| u0021 | name | No official English name for the ethics committee in the files; placeholder used. |
```

Kinds: `source error`, `glossary`, `ambiguity`, `untranslatable`, `check warning`, `name`. Each warning of `translation-check.md` that you keep needs a `check warning` row. Notes describe; they do not apologise or summarise the translation.
