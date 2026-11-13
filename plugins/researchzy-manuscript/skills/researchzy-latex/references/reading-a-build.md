# Reading a build and fixing it

`latex_log.py parse` sorts the log into classes. This file says what each class usually means, which problems the agent may fix itself (a closed list) and which it only reports.

## Order of work

1. Fix the **first error** only, rebuild, parse again. Errors marked "may be caused by the first error" often vanish with it: TeX guesses its way past an error and every guess can produce more. With `-halt-on-error` a run stops at the first error, so one round shows one error.
2. Undefined references on a single run are normal; `latexmk` reruns until they settle. Judge them only on the log of a finished `latexmk` run.
3. Stop after five build rounds, or after a round that changed nothing, and report what is left.
4. A PDF built from a log with errors is not a result. TeX inserted or dropped material to continue; the page can look fine and be wrong.
5. A clean log is not a clean page. Look at the pages the report names (overfull boxes, missing characters, substituted fonts).

## Classes

| Class | Usually means | Agent may fix (closed list) |
|---|---|---|
| `error`: Undefined control sequence `\X` | A misspelled command, or the package that defines `\X` is not loaded | Add the missing `\usepackage` when the log names the command, the hint or the package's manual confirms the package, and the command is used the way that package defines it. A misspelled command name is reported |
| `error`: Missing `$` inserted | `_`, `^` or a math command in text, or a formula left open | Report |
| `error`: Runaway argument, File ended while scanning, Paragraph ended before | A `{` or an environment not closed | Report the place; the user's text decides where the brace belongs |
| `error`: Option clash for package | The package is loaded twice with different options, often once by the class | Merge the options into the first `\usepackage`, or put `\PassOptionsToPackage{options}{package}` before `\documentclass`. Never edit the class |
| `error`: Unicode character not set up, Invalid UTF-8 | The file's encoding is not declared, or pdfLaTeX has no glyph for one character | An encoding declaration: save the file as UTF-8, add `\usepackage[utf8]{inputenc}` where an older pdfLaTeX needs it, or `\DeclareUnicodeCharacter{code}{LaTeX for it}` in the preamble. Never map a character to nothing |
| `error`: Environment undefined | Misspelled environment, or its package is not loaded | Same rule as an undefined command |
| `missing_file`, kind `package` or `class` | A `.sty` or `.cls` that this TeX installation does not have | Never by itself: see "Missing packages" |
| `missing_file`, kind `graphics` | Wrong path, wrong extension, a file not copied, or a case mismatch | Correct the path or extension when exactly one file in the project matches the name. Several or none: report |
| `missing_file`, kind `input` | `\input` or `\include` of a file that is not there (`\include` only warns, so the chapter silently disappears) | Correct the path when exactly one file in the project matches. Otherwise report |
| `missing_file`, kind `font` | A font the engine cannot find | Report |
| `undefined_reference` | A `\ref` to a label that does not exist: a typo, or the labelled object was removed | When the hint names an existing label that is clearly the same name mistyped, change the `\ref` argument to it. Never rename a `\label`, never delete the `\ref`. No close label: report |
| `undefined_citation` | A key with no `.bib` entry, a `.bib` syntax error that made BibTeX skip the entry, or the bibliography tool did not run | Rerun the tool when it did not run. Never write or guess an entry: see SKILL.md, step 4. A near `.bib` key in the hint is reported, not applied |
| `duplicate_label` | The same `\label` key twice; every `\ref` to it may point to the wrong place | Report both places |
| `overfull` hbox | A line sticks out into the margin by the stated points: a long word, URL, formula or table | Report with file and line. Wording is the author's (`researchzy-writing`) |
| `overfull` vbox | Something is taller than the page: a float, table or long formula | Report |
| `font` | A font shape replaced by another (for example bold small caps), or a character missing from the font, which then vanishes from the PDF without an error | Report; a missing character is a lost character |
| `package_warning` | Anything else a package or LaTeX says, for example a float too large, a float specifier changed, an empty bibliography | Report the ones that change the output |
| `bibliography` | BibTeX or Biber errors and warnings from the `.blg`; a syntax error at a `.bib` line drops that entry | Report with file and line. A `.bib` syntax repair is the user's: the entry is bibliographic data |
| `rerun_needed` | Labels or the bibliography changed in the last run | Run `latexmk` again; if it remains after a finished run, labels are oscillating: report |

The fix list is closed. Also allowed: **stale auxiliary files.** When errors point into `<main>.aux`, `.toc`, `.lof`, `.lot`, `.out`, `.nav` or `.snm` from an earlier run (typical after an interrupted build or a changed class), move those files into `latex-build/stale-aux/` and rebuild. Do not delete them, and never move a `.bbl` that has no `.bib` beside it: it cannot be made again.

Every other change to the source is reported to the user with file, line and a proposed change, and made only when the user says so.

## Missing packages

1. Name the missing file and where it is loaded (`problems.md` gives both).
2. Check whether it is installed under another name or path: `kpsewhich <file>`.
3. Find which distribution package provides it, without installing: on TeX Live `tlmgr search --global --file /<file>` (needs the network); on MiKTeX its package manager; on a Linux system TeX, the distribution's file search.
4. Ask the user once, with the command that would install it, and stop until they answer. Installing may need administrator rights and changes their system. Other answers the user may give: they install it, they put the file in the project folder (when its licence allows), or the package is dropped by them.
5. Never replace a missing package with a different one, never write a stub that defines its commands, and never copy a package file from the internet into the project yourself.

## Files written by a build

`latexmk` writes `.aux`, `.log`, `.fls`, `.fdb_latexmk`, `.bbl`, `.blg`, `.out` and the PDF next to the main file. They are build outputs, so writing them is expected; the user's own files are never deleted or moved, and `latexmk -C` (which deletes the PDF and the `.bbl`) is never run.
