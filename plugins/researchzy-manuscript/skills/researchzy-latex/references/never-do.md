# What never to do

Each of these makes a build pass or a paper fit by changing what the paper says or hiding what is wrong. None is allowed, even when the user's deadline is close; when one looks like the only way, tell the user and let them decide.

| Never | Why |
|---|---|
| Delete, comment out, or wrap in `\iffalse ... \fi` or a `comment` environment any text, figure, table, equation, citation or `\ref` to get past an error | The build passes and the paper silently loses content. `latex_guard.py compare` reports it as a content change |
| Write a `.bib` entry from memory, invent a citation key, or point a `\cite` at a different paper | That is a fabricated reference. Missing entries go to the user, `researchzy-citation-finder` or `researchzy-reference-check` |
| Rename a `.bib` key, or a `\label` that a `\ref` uses correctly | Every other `\ref` or `\cite` to it changes meaning or breaks. The two evident cases in the closed list (a `\cite` key one suffix away from its entry, a duplicate label on the object an undefined `\ref` means) are fixed in the `\cite` or the duplicate, never in the `.bib` |
| Silence errors or warnings: run without `-halt-on-error` to get a PDF, use `latexmk -f`, `\batchmode` or `\nonstopmode` in the source, raise `\hbadness`, `\vbadness` or `\hfuzz`, load a package that filters warnings, or redefine `\PackageWarning` | The log stops telling the truth, and the next problem goes unseen |
| Define a missing command or environment as nothing (`\providecommand{\SI}[2]{}`, an empty environment), or map an unknown character to nothing | The error disappears and so does the content it would have printed |
| Turn on draft mode (`draft` option of the class or of `graphicx`) to get past missing figures | The PDF shows empty boxes where the figures should be |
| Edit, patch or rename a venue's `.cls`, `.sty`, `.bst`, `.bbx` or `.cbx` file, or copy it under another name with changes | The venue checks submissions against its own files; a changed file can be grounds for rejection and is replaced at production. Fix the paper, or pass options the way the kit's instructions say |
| Add layout overrides to make a paper fit or look better: negative `\vspace` or `\vskip`, `\baselinestretch`, `\linespread`, `\setstretch`, `\geometry` or margin lengths, `\small`, `\footnotesize` or `\scriptsize` around whole floats or sections, `\looseness`, `\enlargethispage`, smaller `\textfloatsep` and similar lengths, `\resizebox` or `\scalebox` on text, compression packages | These break the venue's format rules, which editors check, and they move the problem rather than solve it. Length is cut in the text, by the author (`researchzy-writing`) |
| Copy the preamble of the old paper into a venue's kit | Its margins, fonts, spacing and package options override the kit. Move content, and add only the packages the content needs |
| Change the year in a style-file name, or rebuild a venue's template from memory or from a copy found elsewhere | Kits change between years and between submission and final versions. The kit comes from the user |
| Run `latexmk -C`, delete the user's PDF, `.bbl` or auxiliary files, or overwrite any file the user wrote | `-C` deletes the PDF and the `.bbl`; a `.bbl` without its `.bib` cannot be made again. Write new files, move stale ones aside |
| Add `-shell-escape` without asking | It lets the document run any program on the machine. Some packages need it; the user decides |
| Install a TeX package or distribution without asking | It changes the user's system and may need administrator rights |
| Post-process the final PDF (for example with Ghostscript to embed fonts) without telling the user | It makes a different file. Fix the source of the problem, and if the user agrees to post-processing, check the new PDF again |
| Report a build as clean when the log could not be read, a tool was missing, or the log still holds errors | "Not checked" is never "passed" |
