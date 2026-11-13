# The source archive, the final PDF and revision diffs

## What a clean source archive holds

- The main `.tex` and every file it inputs, in the same folder layout, with relative paths only.
- The figures in the format the engine actually used (for pdfLaTeX a `.pdf` beats a `.png` of the same name; `latex_pack.py` follows the engine's order).
- `<main>.bbl`, named like the main file, so the receiving system does not need to run BibTeX or Biber. The `.bib` may go too. A `.bbl` written by biblatex can be read only by a compatible biblatex version; when the receiving system's version is unknown, say so to the user.
- Local `.cls`, `.sty`, `.bst`, `.bbx` and `.cbx` files the build reads, unchanged.
- No build outputs (`.aux`, `.log`, `.fls`, the PDF), no unused files, no comments unless the user asks to keep them, no absolute or `../` paths, and file names without spaces or non-ASCII characters (some systems refuse them; `latex_pack.py` warns).

Use the `.fls` of a finished build (`--fls`): it lists every file TeX actually read, including ones loaded by packages, which a scan of the source can miss (data files read by plotting packages, files named in macros).

The receiving system's own rules (folder layout, size limits, allowed file types, whether it runs BibTeX) are facts about that system: take them from its instructions as the user supplies them, with the date, or say they were not checked.

## The rebuild test

`latex_pack.py` prints three commands: unpack the archive into a new empty folder, build it there with the same `latexmk` command, parse the log. Run them. The archive is ready only when that build reports `ok`, or reports only warnings the original build also had. When it fails:

| Rebuild says | Cause | Do |
|---|---|---|
| A missing file the original build found | The scan missed it, or it lies outside the project | Pack again with `--fls`; a file outside the project is moved in by the user and its path changed |
| Undefined citations | No `.bbl`, or a stale one | Build the original once more, then pack again |
| An error the original did not have | Comment stripping touched something it should not have | Pack with `--keep-comments`, compare the two archives' files, and report the line |

Line numbers in the rebuilt log refer to the packed files, which have lost their comment-only lines. Do not fix the unpacked copy by hand: change the project or the pack and pack again, so the archive and the project stay the same paper.

## Anonymity leaks in sources

For a double-blind submission, the archive and PDF can name the authors even when the title page does not:

- comments (stripped by the packer unless kept) and text inside `comment` environments or `\iffalse` blocks (the packer warns; they are not removed);
- `\author`, `\thanks`, acknowledgements, funding notes and first-person self-citations ("our earlier work [12]");
- file and folder names (`smith-draft.tex`, `/home/jsmith/...` in a figure);
- PDF properties: `latex_log.py pdf` shows Title, Author, Creator and Producer, and `\hypersetup{pdfauthor=...}` sets them;
- the metadata inside figure files (author fields of PDF figures, image metadata).

This skill reports what it sees. The full anonymity check of a submission, across all files, is `researchzy-submission` (plugin `researchzy-manuscript`, when installed).

## The final PDF

Run `latex_log.py pdf` on the PDF that will be submitted, with `--page-size` from the kit when the kit states one.

| Fact | On `fail` or `manual` |
|---|---|
| `fonts_embedded` fail | A figure made outside LaTeX usually holds the font: export it again with fonts embedded (`researchzy-figures`, when installed). Base fonts used by the document itself point to a font setup the user should see |
| `type3_fonts` manual | In a pdfLaTeX build these are usually bitmap fonts: the document uses an encoding (often T1) whose scalable fonts are not loaded or not installed. A scalable font package fixes it, but a kit may prescribe its fonts: ask the user first. Figures can also carry Type 3 fonts |
| `page_size` fail | A geometry or paper option in the source, or the engine's default paper size; never squeeze content to fit |
| `properties` manual | Show the user; remove an author name for an anonymous submission with their agreement |
| `page_limit` | See [venue-kit.md](venue-kit.md) |

## A revision diff with latexdiff

For a revised paper, a PDF that marks additions and deletions helps reviewers and the author's response letter (`researchzy-rebuttal`, when installed).

1. Check `command -v latexdiff`. If it is not installed, say so and ask before installing anything.
2. Pack both versions (old and new), or use two clean copies, so neither project is touched.
3. In a new folder that holds a copy of the new version's files: `latexdiff --flatten <old>/main.tex <new>/main.tex > diff.tex` (`--flatten` follows `\input` and `\include`).
4. Build `diff.tex` there with the paper's `latexmk` command and parse its log. If the markup breaks a table or a formula, run latexdiff again with `--math-markup=0`, or exclude the failing command, and say which parts are not marked.
5. Give the user `diff.pdf`, and say that it was made from the two versions named, on that date.
