# Assembling the thesis

The school's file is the carrier: the thesis is built inside a copy of its Word template or with its LaTeX class, so the cover, page setup, styles, headers and section breaks stay the school's. The papers bring their text, figures, tables, equations and citations, and change nothing but their layout.

## The chapter plan

Write `thesis-build/plan.md` before moving anything, and show it to the user:

| Chapter | Source | Status | Kind |
|---|---|---|---|
| 1 Introduction | new | — | bridging, drafted from the papers |
| 2 … | paper1/main.tex | published | paper, text unchanged |
| 3 … | paper2.docx | accepted | paper, text unchanged |
| 4 General discussion | new | — | bridging |

Then list the front matter in the order the rules give (cover, declarations, abstracts, contents, lists of figures and tables, abbreviations, symbols) and the back matter (references, appendices, publications, acknowledgements). Where the rules give no order, follow the template and say so. A chapter that will differ from its published version (corrections the user asks for, a merged literature review) is marked in the plan and in the reuse table.

## Snapshot first

```sh
python3 "$SKILL_DIR/scripts/thesis_parts.py" snapshot papers/ -o thesis-build/before.json
```

The folder holds the papers as they were published or accepted (.tex, .docx or .md). Take the snapshot before any change, and a new one, under a new name, after each round of assembly.

## Word: fill a copy of the template

1. Copy the template to `thesis-build/thesis.docx`. Never start a new document, and never edit the user's template.
2. Fill the cover and declaration fields only with what the user gave; leave signatures and dates to the user.
3. Bring each chapter in from its source:
   - From a .docx paper, copy body paragraphs as whole XML elements (python-docx is in the Researchzy agent image), so that Zotero, EndNote and Mendeley fields, cross-references and equations come along. Never retype a citation or a number.
   - Map each paragraph to the template's style for its role: body text, headings by level, captions, references. Remove direct font and size formatting that overrides the template; this changes the look, not the text.
   - From LaTeX or Markdown, `pandoc --reference-doc=template.docx` gives the template's styles; insert the resulting body into the copy. Citations then become plain text and live fields cannot be made: tell the user.
4. Sections: the front matter in its own section with the numbering the rules ask for, the main matter in a new section that starts where the rules say, and no restart after that. A landscape page is a section of its own.
5. Headings use the template's automatic numbering. Delete numbers typed into heading text; captions and cross-references use fields, numbered by chapter if the rules ask.
6. Run `format_check.py docx thesis-build/thesis.docx`. `field_balance` must pass before the user opens the file. Then ask the user to open it in Word, update all fields (contents, captions, cross-references), and refresh citations in the citation manager on a copy.

## LaTeX: the school's class is a kit

Building, reading logs and moving a paper into a class belong to `researchzy-latex` (plugin `researchzy-manuscript`, when installed), whose venue-kit procedure applies to a school's class unchanged: record the class with its source and date, build its sample untouched, move content and not the preamble, add only the packages the content needs, and compare before and after. Each paper becomes a chapter file, `\include`d by the class's main file; its bibliography is merged ([reuse and front matter](reuse-and-front-matter.md)). Never copy a paper's margins, fonts or spacing into the thesis, and never edit the class file. Without that skill, build with the class's documented command and report the log as it is.

## The content check

After assembly, snapshot the result and compare:

```sh
python3 "$SKILL_DIR/scripts/thesis_parts.py" snapshot thesis-build/thesis.docx -o thesis-build/after.json
python3 "$SKILL_DIR/scripts/thesis_parts.py" diff thesis-build/before.json thesis-build/after.json
```

Give a LaTeX thesis's chapter folder instead of the .docx. Name with `--unpublished` only the papers the reuse table records as not published (submitted, in preparation), whose text the user may still change. Then:

| Row | Do |
|---|---|
| `fail`: a published sentence changed | Restore the published wording. If the user changed it on purpose, keep their change, mark the chapter as differing from the published version in the reuse table, and tell them |
| `fail`: removed | Find where it went; restore it unless the user removed it on purpose (same as above) |
| `manual`: numbers or citation form only | Check that the new figure, table or equation number points at the same object |
| New text | Expected for bridging chapters and front matter; anything else in a paper chapter is a change |

A request to tidy, polish or reword a published chapter is declined for that chapter: the thesis reproduces the published version, and changes to it are the user's own decision, sometimes bound by the publisher's terms. If the user makes changes, the diff shows them and the reuse statement says so. New bridging text can be drafted with `researchzy-writing` (plugin `researchzy-manuscript`, when installed).

## Never

- Rebuild the thesis from extracted text, paste through the clipboard or drive a word processor's interface.
- Change the template's styles or page setup to fit a paper; the thesis takes the template's.
- Change a sentence of a published paper silently, including "small" fixes of spelling or terms.
- Keep two reference lists, or flatten live citation fields to text without telling the user.
