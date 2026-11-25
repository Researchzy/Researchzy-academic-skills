# Reading the checks

Every row is one of five states. Only `pass` is a pass.

| State | Meaning | Do |
|---|---|---|
| `pass` | Measured, and it agrees with a stated rule (or with the template, which the row says) | Nothing |
| `fail` | Measured, and it breaks a stated rule, or the file is broken (skipped heading level, unpaired field) | Fix the thesis, never the record, then run the check again |
| `manual` | A person has to look: a value seen only in the template, a pending conflict, a wider margin in a PDF, a font of another name, a page in another size | Show the user what the row says and what to look at |
| `not_checked` | No rule could be read, no rules file, a tool or package missing, chapter 1 not found | Report it with its reason. It is never a pass |
| `not_stated` | The rules say nothing about it; the measured value is in the row | Report it as silent in the rules |

## `format_check.py docx`

Read from the file's XML, which Word follows. LibreOffice in a sandbox renders some things differently and may lack the school's fonts, so a .docx is judged from its XML, never from a rendering.

| Check | Measures | Not shown |
|---|---|---|
| `page_size`, `margins` | Each section's paper and the distance from the edge to the text; a gutter counts on the binding side (top when the document says so); with mirrored margins, left means inside | Where the text really reaches; a landscape section is `manual` |
| `page_numbers.front`, `.main` | Per section, whether a header or footer it uses (its own or inherited) holds a page field, the number format, and where numbering starts or restarts | Position (see the PDF check); numbers typed as text |
| `body_size`, `body_font.east_asian`, `body_font.latin`, `line_spacing`, `first_line_indent` | One row for the style that carries most body text, resolved through document defaults and its basedOn chain; then rows listing body paragraphs whose own formatting differs. Body text is the main matter without headings, tables, captions, contents entries and the reference list | Table styles; text in text boxes; with the document grid on, Word may snap lines to it |
| `heading_levels` | A heading more than one level below the one before it | Whether the levels suit the content |
| `typed_heading_numbers` | A number typed at the start of a heading that also has automatic numbering, so Word shows both | Typed numbers on headings without automatic numbering, which are allowed |
| `contents_field`, `field_balance` | A TOC field exists; every field that begins also ends | Whether the fields are up to date: the user updates them in Word |

The table of styles in use lists each paragraph style's resolved fonts, size, spacing, indent and outline level, and the paragraphs whose direct formatting overrides the style. Use it to find a style brought in with a paper. Chapter 1 is the first first-level heading with automatic numbering, or one that reads 第1章 or Chapter 1; if that is wrong, give `--main-starts <¶>`.

## `format_check.py pdf`

The measurements hold for the PDF the user exported and nothing else. Odd PDF pages are taken as right-hand pages.

| Check | Measures | Not shown |
|---|---|---|
| `page_size` | Each page, within 1 mm (a convention, `--tolerance-mm`) | |
| `margins.<side>` | Where text and images reach, without running heads (the same text on several pages) and page numbers. Text inside the margin on any page fails | A margin set wider than the rule: ink gives only a lower bound, so that row is `manual` |
| `body_size` | The size that carries most characters, then pages of at least 200 characters mostly in another size (`manual`) | Whether those pages are a chapter, tables or references |
| `body_font.east_asian`, `.latin` | The font carrying most Chinese and most Latin characters at the body size | Whether a different name is the same face: `manual` |
| `page_numbers.front`, `.main`, `.position` | The number printed in the top or bottom band of each page; roman or arabic before and after the page where chapter 1 starts; restarts and gaps against the expected sequence; position | Numbers in an unusual form (such as 3-1) |
| `fonts_embedded` | Fonts the file does not embed | |

Chapter 1 is the first page, after contents pages, with a chapter-1 heading larger than the body text; otherwise give `--main-starts <PDF page>`. Without PyMuPDF every row is `not_checked`.

## `format_check.py compare` and `rules`

`compare` lists each paragraph style in use whose resolved values differ from the template's style of the same id, styles the template lacks (`style_added`, usually brought in with a paper), and sections whose page setup is not one of the template's. All are `manual`: the written rules decide, and the template may be older. `rules` is read in [the rules record](rules-record.md).

## `thesis_parts.py`

| Row | Meaning |
|---|---|
| `sentence` (`fail`) | A sentence of a published paper is in no file of the assembled thesis: changed (the closest new sentence is shown) or removed |
| `sentence` (`manual`) | Only figure, table, equation or chapter numbers, or the form of a citation, differ; or the paper is unpublished |
| New text | Sentences only in the thesis: bridging chapters, front matter, or edits to look at |
| `one_work_two_keys`, `one_key_two_works`, `one_key_two_files`, `key_repeated` | See [reuse and front matter](reuse-and-front-matter.md) |
| `two_long_forms`, `defined` | Abbreviation candidates; leads for the user to confirm, never failures |
| `csl_sample` | `manual` with the rendered sample; `not_checked` without pandoc or with a dependent style |

The text comparison sets aside case, blanks, quote and dash characters, and the content of citation and cross-reference fields. A number next to a Chinese character is data: 样本量为312人 against 样本量为321人 fails.
