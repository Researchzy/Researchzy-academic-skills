# The glossary

The glossary is settled before the first unit is translated, because every later change of a term means finding and retranslating every unit that holds it. The script reads it in step 5 and warns about each place where the translation does not follow it.

## Format

`translation/terms.tsv`, tab-separated, UTF-8, with this header row:

```text
term	translation	field	note
限时进食	time-restricted eating|TRE	nutrition	define at first use: time-restricted eating (TRE)
睡眠潜伏期	sleep onset latency	sleep	user's earlier paper, methods.docx
匹兹堡睡眠质量指数	Pittsburgh Sleep Quality Index|PSQI	sleep	name of the instrument
PSQI		sleep	=
随机对照试验	randomized controlled trial|RCT	methods	US spelling (user)
```

| Column | Content |
|---|---|
| `term` | The term as it is written in the source language |
| `translation` | Its translation. Several accepted forms are separated by `\|`, for example the full form and its abbreviation after the first use |
| `field` | The subject the translation belongs to, when the same term is translated differently in different fields. Two rows for one term in different fields are both accepted |
| `note` | `=` at the start keeps the term exactly as written (abbreviations, gene and protein symbols, species names, software, units). Anything after it, or in a note without `=`, is free text: where the translation comes from, how to introduce it |

Lines starting with `#` are comments. A term of Latin letters is matched as whole words, in any case unless it is all capitals, with a plural ending allowed and a hyphen equal to a space; any other term is matched as written.

## Building the candidate list

Read the whole source first. Propose a row for:

- technical terms of the field, interventions, exposures and outcomes;
- instruments, scales, questionnaires and guidelines, under their official names;
- group, arm, variable and model names;
- statistical terms whose translation depends on the field;
- abbreviations, with their full form;
- institutions, committees and funders, under their official names.

Leave out words with one obvious translation. In `note`, give the basis of each proposal: the user's glossary, a file of the user's (their earlier paper in the target language is the best source), or "proposed". Show the list to the user in step 1 and wait for a confirmation or corrections.

## Rules

- **One term, one translation** throughout the document. The only planned variation is the full form at the first use and its abbreviation afterwards, both listed with `|`.
- **One translation, one term.** Two different source terms must not share a translation, unless the user confirms that they mean the same thing; then list one of them only.
- **First use.** In English, define an abbreviation at its first use in the abstract and again in the main text (a convention; the journal's rule overrides it). In Chinese, write 中文（English, ABBR） at the first use.
- **Official names are looked up, not made.** Take the English name of an instrument, guideline, institution, committee or funder from the user's files. If none gives it, the translation is `[Author input needed: official English name of …]`, and the row says so.
- **Kept as written** (`=`): gene and protein symbols, Latin species names, software and model names, units, statistical symbols, and abbreviations the field uses untranslated.
- **A deviation is explained.** When a sentence needs another word than the glossary's (a different sense of the same term), use it and write a `glossary` note with the reason. Do not edit the glossary to silence the warning unless the user agrees.

## Choosing between candidates with Researchzy

When two English candidates compete (for example "sleep onset latency" and "sleep latency") and the Researchzy tools are connected (plugin `researchzy`, account needed), a search of each candidate as a quoted phrase shows which the literature's titles and abstracts use more:

- Run `search_papers` with `query` set to the quoted phrase, and `fieldOfStudy` or `yearFrom` when they narrow the field. Record the query, the `total` and the date in the row's `note`.
- The signal is loose: the index matches keywords in titles and abstracts only, has no stemming (singular and plural are separate searches), and `total` is approximate. Present it to the user as a hint, never as the decision.
- The same tools can give the English title of a paper the source names in Chinese (`search_papers` with its DOI). Use only a record the tool returned; do not translate a published title yourself.

Without the tools, the user chooses, and the row's note says so.

## What the check reports

| Warning | Meaning | Do |
|---|---|---|
| `X: Y is not in the translation` | The source unit holds term X; the translation unit holds none of its accepted translations | Use the agreed translation, or keep the other word and write a `glossary` note |
| `…; it has Z, the glossary's translation of W` | The translation used the rendering of another term | Usually a slip: two terms were merged into one translation |
| `X is marked keep-as-is (=) but is not in the translation` | A term to keep as written was translated or dropped | Restore it as written |
| `one translation for two terms` | Two rows give the same translation | Ask the user whether the two terms mean the same thing |
| `… has no translation and no =` | A row is incomplete | Complete it, or mark it `=` |
