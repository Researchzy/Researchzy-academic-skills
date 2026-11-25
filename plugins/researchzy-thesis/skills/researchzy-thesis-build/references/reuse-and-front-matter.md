# Reuse, bridging chapters and front matter

## The reuse table

`thesis-build/reuse.csv` has one row per paper in the thesis:

| Column | Content |
|---|---|
| `paper`, `chapter` | The source file and the chapter it becomes |
| `doi`, `title`, `journal`, `year` | From the publisher's record (see below), never from memory |
| `status` | `published`, `accepted`, `submitted` or `in_preparation`, as the user says |
| `licence` | The licence or permission as the user's document words it, with the document and the date: an open licence named on the article page, a publisher's author-rights page, a permission letter |
| `derivatives` | `allowed`, `not_allowed` or `not_stated`, read from that document |
| `contributions` | Who did what, from the user or the paper's own contribution statement |
| `differs` | `no`, or what differs from the published version and who decided it |
| `statement` | The draft statement for the thesis |

- **Bibliographic fields.** With the `researchzy` plugin connected (it needs a Researchzy account), call `search_papers` with `doi` for each published paper, save each result in `thesis-build/reuse-lookup/<paper>.json`, and copy title, venue and year from it. A record that does not match what the user gave goes back to the user. The index holds no licences, no publisher terms and no author contributions. Without Researchzy, take the fields from the published PDF's first page or the user's files.
- **Licences and permission.** Only the user's documents count. When a licence forbids derivatives, or the permission is missing or unclear, the chapter reproduces the published text unchanged (layout aside) and the statement keeps `[Author input needed: permission from <publisher> to reuse <title> in a thesis]`. Never write that permission exists.
- **Contributions.** Never infer them from the author order. A missing one is `[Author input needed: contributions of <co-author> to <title>]`.

When the rules prescribe a form for the statement, use it and quote it in `rules.json` (topic `reuse_statement`). Otherwise offer a plain draft for the user to adapt:

> Chapter 3 reproduces "<title>", published in <journal> (<year>), <doi>, under <licence or permission>. <Contributions.> The text is unchanged apart from layout.

> 第3章为已发表论文《<题名>》，载于<期刊>（<年份>），<DOI>，依据<许可或授权>使用。<作者贡献。>除版式外，正文未作改动。

## Bridging chapters

The introduction, literature review, general discussion and conclusion are new text. Draft them only from the papers' own claims, results and limitations, citing the papers; leave gaps as `[Evidence needed: …]`, `[Citation needed: …]` or `[Author input needed: …]`. New literature belongs to `researchzy-literature-review` (plugin `researchzy`, when installed) and the prose to `researchzy-writing` (plugin `researchzy-manuscript`, when installed). The abstract in a second language goes to `researchzy-translate` (plugin `researchzy-language`, when installed).

## Front matter

Order and content come from the rules; where they are silent, from the template, and the user is told. Declarations of originality and authorisation forms are the user's to complete and sign: never fill in a signature, a date or a statement of fact about the user. The contents list and the lists of figures and tables are fields in Word or commands in LaTeX, never typed.

## Abbreviations and symbols

```sh
python3 "$SKILL_DIR/scripts/thesis_parts.py" abbreviations papers/ thesis-build/chapters/
```

`abbreviations.md` lists every definition found ("long form (ABBR)", "长形式（ABBR）", "(long form, ABBR)"), where it is, and how often the abbreviation is used. It is a draft: show it to the user, who confirms each long form. A Chinese and an English long form of the same abbreviation are one entry. An abbreviation with two long forms in the same language (`two_long_forms`) needs the user's decision: one meaning in the thesis's list, and for the chapter that used the other meaning, a note in the list or at the chapter's start, since the published text keeps its wording. Whether abbreviations are defined once or per chapter is a rule of the school, recorded in `rules.json` if stated. Symbols are listed from the equations by hand and confirmed the same way.

## The merged bibliography

```sh
python3 "$SKILL_DIR/scripts/thesis_parts.py" bib paper1/refs.bib paper2/refs.bib
```

| Row | Do |
|---|---|
| `one_work_two_keys` (`fail`) | Keep one key; change the citation commands in the thesis copy that use the other. In a citation manager, merge the duplicate items in the user's library |
| `one_work_two_keys` (`manual`) | Same title, other year: often a conference and a journal version. Ask the user which the chapter cites |
| `one_key_two_works` | Give one entry a new key and change the citations of that chapter in the thesis copy |
| `one_key_two_files` (`manual`) | The same work with different fields: keep the fuller entry |
| `key_repeated` | Remove the duplicate entry from the merged file |

Changing a citation key changes no visible text. Whether each entry exists and is correct belongs to `researchzy-reference-check` (plugin `researchzy-manuscript`, when installed).

## The citation style

Use the style the rules name, in the edition they name. Find its official CSL file (the repository of CSL styles, or the school's or publisher's page), download it in this session, and record the URL, the date and the file's `title` and `updated` in `rules.json` (a `note` on `reference_standard`). Never bundle a style, never take one from memory, and never fetch an edition the rules do not name, even when the user mentions a newer one: that is a conflict for the user. A dependent style only names its parent; download the parent too. Then:

```sh
python3 "$SKILL_DIR/scripts/thesis_parts.py" csl-sample thesis.bib style.csl --keys key1,key2,key3
```

Show the user the sample beside the examples in the rules before formatting the whole list. In Word with a citation manager, the user selects the same style there.
