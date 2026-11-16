---
name: researchzy-latex
description: "Build a LaTeX paper with its own engine and bibliography tool, turn the log into a short problem list, fix only mechanical problems with a content check, move a paper into a venue kit the user supplies, and pack a source archive that rebuilds. Use when a paper will not compile or before submission."
---

# Researchzy LaTeX

This skill gets a LaTeX paper to build cleanly and ready to hand over. It finds how the project is built, builds it, reads TeX's own log (and the BibTeX or Biber log) into a short list of problems with file and line, and by default only reports them. When the user asks for fixes, it fixes problems from a closed list of mechanical ones and proves with a before-and-after snapshot that no content changed. It also moves a paper into a venue's kit that the user supplies, packs a clean source archive and proves it rebuilds, and reads the facts of the final PDF.

It does not cut or rewrite text to fit a page limit (`researchzy-writing`), fix or add references (`researchzy-reference-check`), make figures (`researchzy-figures`), sync with Overleaf, or make posters or slides. It carries no templates and no facts about any venue: no style-file names, page limits or margins. A venue's rules come from the kit the user gives, and are recorded with their source and date.

## Requirements

- A TeX distribution with `latexmk` and the project's engine (pdfLaTeX, XeLaTeX or LuaLaTeX) and bibliography tool (BibTeX or Biber). If `latexmk` is missing, say so and ask before installing anything.
- Python 3.10 or newer; the scripts use the standard library only. `pdfinfo` and `pdffonts` (Poppler) for PDF facts; without them those facts are `not_checked`. `latexdiff` only for revision diffs.
- No account and no network. Researchzy's tools add nothing to building a paper, with one exception in step 4.

Resolve `SKILL_DIR` to the directory containing this `SKILL.md`. Everything the skill writes goes in `latex-build/` in the user's working directory; the build itself writes its usual files (`.aux`, `.log`, `.bbl`, the PDF) next to the main file.

## Inputs

- The project folder, or its main `.tex` file.
- The mode: **diagnose** (the default: build, parse, report) or **fix** (also change the source, within the closed list). Fix only when the user asks for fixes.
- For a move into a venue's kit: the kit's files or its official URL, the venue, year, track and stage (submission or final).
- For an archive: whether comments may be removed (default yes) and whether the submission is anonymous.

Ask at most once, in one message, for what is missing and changes the result. Do not ask about the mode when the request says it ("why does this not compile" is diagnose; "make it compile" is fix).

## Workflow

1. **Detect.**

   ```sh
   python3 "$SKILL_DIR/scripts/latex_log.py" detect path/to/project
   ```

   It prints the main file, the engine and the bibliography tool, each with its evidence, and the `latexmk` command with the folder to run it in. Exit 1 means it could not decide: several main files, or signals that conflict (for example a `% !TEX program = pdflatex` line in a file that loads `fontspec`). Show the user the candidates or the conflict and ask; do not guess. Read its `notes`: a package that needs `-shell-escape` is named, never added without the user's yes.

2. **Build** with exactly the command `detect` printed (here the one for pdfLaTeX), in its folder, keeping the output:

   ```sh
   mkdir -p latex-build
   (cd path/to/project && latexmk -pdf -file-line-error -halt-on-error -interaction=nonstopmode main.tex) > latex-build/build-1.out 2>&1
   ```

   Never `latexmk -C`, never `-f`, never without `-halt-on-error`. A missing `latexmk` or engine is reported, not worked around.

3. **Parse the log.**

   ```sh
   python3 "$SKILL_DIR/scripts/latex_log.py" parse path/to/project/main.log --out latex-build
   ```

   It reads `main.blg` beside the log when there is one, and writes `latex-build/problems.md` and `problems.json`. `build.status` is `ok`, `incomplete` (undefined references or citations, or a rerun pending), `failed` (any error; a PDF next to such a log is not a good build) or `not_checked` (no log: nothing was checked, exit 2). Overfull hboxes under 5 pt are left out (`--hbox-pt` changes it); every overfull vbox is listed.

4. **Report** (diagnose mode ends here). Tell the user, in this order: the build status; the first error with file, line and context; missing files (a missing package is named with the file that loads it); undefined citations and references; duplicate labels; then overfull boxes, font problems and other warnings, counts first. Read [reading a build](references/reading-a-build.md) for what each class means and what to propose. A `\cite` key with no entry is never filled in by this skill: say which keys, and that `researchzy-citation-finder` (plugin `researchzy`, needs a Researchzy account) can find the paper and `researchzy-reference-check` (plugin `researchzy-manuscript`) can verify an entry the user adds.

5. **Fix** (only in fix mode).
   1. Snapshot first: `python3 "$SKILL_DIR/scripts/latex_guard.py" snapshot path/to/project/main.tex -o latex-build/before.json`.
   2. Fix the first error if it is on the closed list in [reading a build](references/reading-a-build.md): a mistyped `\ref` target, an evident `\cite` key or duplicate label, a figure or input path or extension, a package option clash, an encoding declaration, outline fonts in place of Type 3 bitmap fonts, a negative space that makes text overlap, stale auxiliary files, or a `\usepackage` for a command the log names. Anything else: report it with a proposed change and wait.
   3. Missing package: name the file, give the install command, ask once, and stop until the user answers.
   4. Rebuild (step 2, `build-2.out`, ...) and parse (step 3). Repeat at most five rounds, and stop early after a round that changed nothing.
   5. Snapshot again (`-o latex-build/after.json`, a new name each time), then compare and scan:

      ```sh
      python3 "$SKILL_DIR/scripts/latex_guard.py" compare latex-build/before.json latex-build/after.json --out latex-build
      python3 "$SKILL_DIR/scripts/latex_guard.py" overrides path/to/project/main.tex --out latex-build
      ```

      `compare` exits 1 when a label, citation, figure, float or section title was removed or renamed, a layout override was added, or the word count moved more than 0.1 per cent (at least 2 words); a corrected figure path is listed apart and is not a change. Undo a change, or show it to the user with its reason. `overrides` lists every negative space, spacing, margin and font-size override in the source with file and line; report them, never add one ([what never to do](references/never-do.md)).
   6. Tell the user every edit: file, line, before and after, and why.

6. **Move into a venue's kit** (when asked). Follow [venue kit](references/venue-kit.md): the kit comes from the user and is recorded in `latex-build/kit.md` with venue, year, track, stage, source and date; build the kit untouched first; move content, not the preamble, into a new folder; add only the packages the content needs; snapshot and compare old against new; scan overrides; check the page limit only with the kit's own statement of what it counts.

7. **Pack a source archive** (when asked, or before a submission that takes sources). Build first so that `main.bbl` and `main.fls` are current, then:

   ```sh
   python3 "$SKILL_DIR/scripts/latex_pack.py" pack path/to/project/main.tex --out latex-build/source --fls path/to/project/main.fls
   ```

   It copies only the used files into the new folder, removes comments safely, includes `main.bbl`, and writes `latex-build/source.tar.gz`, `source.zip` and `source.MANIFEST.md` (kept files, left-out files and why, warnings). It refuses a folder that exists and is not empty. Exit 1 lists files the build needs that are missing or outside the project: report them. Then run the three rebuild commands it prints; the archive is ready only when the rebuilt log parses as `ok`. See [archive and PDF](references/archive-and-pdf.md), including anonymity leaks in sources.

8. **Check the final PDF.**

   ```sh
   python3 "$SKILL_DIR/scripts/latex_log.py" pdf path/to/project/main.pdf --out latex-build
   ```

   Pages, page size, fonts not embedded, Type 3 fonts and document properties, each `pass`, `fail`, `manual` or `not_checked`; exit 2 when Poppler is missing. Add `--page-size a4`, `letter` or `WxHmm` only when the kit or the user states the size. A page limit is checked only with `--max-pages`, `--limit-source "<file or URL, date read>"` and `--content-pages` (the pages the limit counts, which you read off the PDF).

9. **Revision diff** (when asked, and `latexdiff` is installed): see [archive and PDF](references/archive-and-pdf.md).

## Outputs

| File in `latex-build/` | Content |
|---|---|
| `build-N.out` | The output of each `latexmk` run |
| `problems.md`, `problems.json` | The parsed log: build status, problems by class, first error |
| `before.json`, `after.json`, `compare.md`, `overrides.md` | Snapshots, the content comparison, the override scan |
| `kit.md` | The venue's kit: source, date, quoted rules (kit moves only) |
| `source/`, `source.tar.gz`, `source.zip`, `source.MANIFEST.md` | The source archive and its manifest |
| `source-rebuild/` | `problems.md` of the archive built in an empty folder |
| `pdf-facts.md`, `pdf-facts.json` | Facts of the final PDF |

## Rules

- Diagnose is the default. In fix mode, change only what the closed list allows, snapshot before and compare after, and tell the user every edit.
- Never delete, comment out or hide content, citations or figures; never silence an error; never edit a venue's class or style file; never add a layout override. [What never to do](references/never-do.md) gives the reason for each.
- Never write a `.bib` entry or a citation key. Never rename a `.bib` key, or a label that a `\ref` uses correctly; the two exceptions are in the closed list.
- A build with errors in its log has failed, whatever the PDF looks like. No log, or a missing tool, is `not_checked`, never clean.
- No venue facts from memory: page limits, page sizes, fonts and style names come only from the kit or a page the user supplies, quoted with source and date.
- Ask before installing anything, before `-shell-escape`, and before downloading a kit from a URL the user did not give.
- Never overwrite or delete the user's files; new files go in `latex-build/`.

## Related files

| File | Open when |
|---|---|
| [references/reading-a-build.md](references/reading-a-build.md) | Steps 4 and 5: what each problem class means, the closed fix list, missing packages |
| [references/never-do.md](references/never-do.md) | Before any fix, and whenever a fix would remove, hide or squeeze something |
| [references/venue-kit.md](references/venue-kit.md) | Step 6: moving a paper into a venue's kit, and any page-limit question |
| [references/archive-and-pdf.md](references/archive-and-pdf.md) | Steps 7 to 9: the archive, the rebuild test, anonymity leaks, PDF facts, latexdiff |
| `scripts/latex_log.py` | Steps 1, 3 and 8; `--help` on each command |
| `scripts/latex_guard.py` | Step 5 and the kit move: snapshot, compare, overrides |
| `scripts/latex_pack.py` | Step 7 |
