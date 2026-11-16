# Verdicts and what to do with them

Every verdict is in `reference-check/references.json` (`records[].status`) with the evidence behind it (`evidence`), the differences found (`differences`), the matching record (`found`) and flags (`flags`).

## How a verdict is reached

1. **By identifier.** A PMID is looked up in PubMed, a DOI in Crossref, an arXiv number at arXiv. A DOI Crossref does not know is looked up in the doi.org handle registry, which covers every registration agency, and then in DataCite.
2. **The identifier must lead to the cited work.** The record an identifier resolves to has to carry the cited title: fewer than half of the cited title's words in the record's title means the identifier belongs to another work. That record is then not used for anything else.
3. **By title**, when no identifier found the cited work: a Crossref search, and the Researchzy results the agent saved. A search returns something for any words, so a hit counts only when its title matches (token similarity 0.8 or more; in a plain-text reference line the hit's title must appear as a phrase), its authors could be compared and agree, and its year is within one of the cited year. Otherwise it is listed as a nearest real paper.
4. **Authors.** For a BibTeX entry, every cited family name is compared position by position with a PubMed, Crossref or DataCite record, and the number of authors is compared; against arXiv and Researchzy records, which have plain name strings, only the first author is compared. For a plain-text or TSV reference the check runs the other way round, because author lists are written in too many styles to parse: the record's first author must be named in the reference. Case, accents, hyphens and name particles are normalised. A BibTeX list ending in `and others` may be shorter than the record's.
5. **Year.** A cited year two or more away from every year of the record is a minor difference; one year off is a note, because online and print years differ.

## Per verdict

| Verdict | What it means | What to tell the user |
|---|---|---|
| `confirmed` | A record matches. | Nothing to do. Mention notes such as a DOI the entry lacks. |
| `mismatch`, author | The work exists; a cited author or the author count differs from the record. | Show cited against record. A wrong first author or an invented co-author is a serious error; offer the correction from `fixes.bib`. |
| `mismatch`, identifier belongs to a different work | The DOI is real but is another paper's. | Give the title the DOI resolves to. If the cited work was found, give its DOI; if not, the reference needs the author's attention. |
| `mismatch`, identifier does not exist but the work was found | The paper is real, its DOI, PMID or arXiv number is wrong. | Give the identifier of the record found. |
| `mismatch`, year | The year differs by two or more. | Show both years; the author decides which edition or version they cite. |
| `unconfirmed` | No record was found, or a registry did not answer. | List what was tried (`evidence`). Ask the author to confirm these by hand. Books, chapters, reports, theses, standards, software and web pages are often legitimately here. |
| `identifier_not_registered` | The identifier exists nowhere and no search found the work. | Say exactly that. This is the strongest signal that a reference is wrong or invented, but the conclusion is the author's. Show any nearest real paper. |

## Flags

| Flag | Meaning | What to tell the user |
|---|---|---|
| `retracted`, `partly_retracted` | The registry links a retraction notice to the work, or marks the record retracted. | Name the notice and its date. Citing a retracted paper needs a reason and usually a mention of the retraction. |
| `expression_of_concern` | The journal has published a concern about the work. | Name the notice. |
| `corrected` | A correction or erratum exists. | Suggest checking that the cited result is not the corrected one. |
| `update_notice` | The cited DOI or PMID is itself a retraction or correction notice. | The author probably means the paper the notice is about. |
| `preprint_published` | The cited preprint has a published version. | Give the published DOI; most journals prefer the published version. |
| `duplicate` | Two entries have the same DOI or PMID, or the same title and first author. | Keep one entry and point every citation to it. |
| `placeholder` | "in press", "forthcoming", "to appear" or e000 pages. | Update the entry before submission. |

## Known false alarms

- **A registry was down or rate-limited.** The reference stays `unconfirmed` and its evidence says "lookup failed". Run the script again later; answers already obtained are cached.
- **Old or regional DOIs.** Some older IEEE DOIs and DOIs registered with agencies outside Crossref and DataCite (for example Chinese and Japanese agencies) are confirmed to exist by doi.org but have no metadata the script can compare. They stay `unconfirmed` with "registered with another agency".
- **Titles in a non-Latin script.** They are not compared, so an identifier is accepted without a title check.
- **DOIs that follow the latest version.** A software or dataset DOI that always points at the newest release (a Zenodo "all versions" DOI) changes its record's title with every release, so an entry citing an older version is reported as "identifier belongs to a different work". Tell the user which version the DOI now resolves to and suggest the DOI of the version they used.
- **Translated or changed titles.** A preprint whose title changed on publication can be reported as "identifier belongs to a different work". Check the record the identifier resolves to before recommending a change.
- **Author lists cut short without `and others`.** Reported as an author-count mismatch. In BibTeX, end the list with `and others`, or cite all authors.
- **Collective authors.** Guideline bodies, consortia and collaborations are not compared name by name; the note says so.
- **A wrong DOI on a plain-text reference.** For a plain-text line the script looks for the words of the DOI's record title inside the line. When the other paper's title is two or three words that all occur in the line, the wrong DOI goes unnoticed unless the first author also differs.
- **Plain-text references are checked less closely than BibTeX.** Only the first author is compared, and co-authors are not. Give the `.bib` file when there is one.
