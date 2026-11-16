# Declarations, the title page, highlights

Every statement is drafted from `authors.json`. Where a fact is missing, the draft carries `[Author input needed: …]` and the fact goes on the list in `report.md`. Headings and order follow the venue's guidelines; when they give none, use the headings below, which `check_package.py` recognises.

A statement may be typed into a submission form instead of, or as well as, the manuscript. Where both exist, they must say the same: put the same sentences in both, and rerun the check after any change.

## Author contributions

- **Needs:** each author's roles, from the authors. Optionally the degree of each role (lead, equal, supporting) when the venue asks for it.
- **Form:** one line per role or per author, with the initials or names used consistently: "M.O.: Conceptualization, Investigation, Writing – original draft. T.L.: Formal analysis, Writing – review & editing."
- **Avoid:** roles that are not CRediT terms ("statistical analysis", "study design", "data collection", "manuscript writing"); initials that two authors share (write the names out); deciding roles or author order for the authors. Author order and equal contribution are the authors' decision and are never judged here.

The fourteen CRediT roles (ANSI/NISO Z39.104), written exactly so: Conceptualization; Data curation; Formal analysis; Funding acquisition; Investigation; Methodology; Project administration; Resources; Software; Supervision; Validation; Visualization; Writing – original draft; Writing – review & editing. Every author has at least one. A venue that does not use CRediT may ask for a sentence per author instead; then follow its wording, still from the authors' answers.

## Competing interests

- **Needs:** for each author, the interests they declare (employment, consultancies, honoraria, shares, patents, advisory roles, grants from parties with a stake in the result, personal relationships), or their own confirmation that they have none.
- **Form:** "T.L. received consulting fees from Example Ltd. The other authors declare no competing interests."
- **Avoid:** a blanket "none" for an author who has not answered; a "none" in one place and a declared interest in another (the script compares them); judging whether an interest is relevant, which is the author's and the editor's call. Some venues use their own disclosure form: the authors fill and sign it themselves.

## Funding

- **Needs:** each funder's name as the funder writes it, each grant number, the recipient when the venue asks, and the funder's role in the study (often "The funder had no role in …", which only the authors can confirm).
- **Avoid:** a grant number typed twice in two forms (the script flags near-identical numbers); funders listed in the acknowledgements but not here; "no funding" without the authors' confirmation.

## Ethics and consent

- **Needs:** the approving body, the approval id and date, the type of consent, and registration ids (trial, protocol, preregistration) with the registry. For animal work, the licence or approval and the guideline followed.
- **Form:** "The study was approved by the [body] (approval [id]). Participants gave written informed consent." The approval id must be identical in the manuscript, the title page, the letter and the form.
- **Avoid:** "ethics approval was not required" unless the authors say so and give the reason; an approval id from memory or from an earlier paper.

## Data and code availability

Draft these with `researchzy-data-availability` (plugin `researchzy-manuscript`, when installed). This skill checks only that each required statement is present, is not a placeholder, and that repository links do not break anonymity. Never turn "available on request" into a repository claim, or the reverse.

## Use of AI tools

- **Needs, from the authors:** each tool (name and version or model, as the authors know it), what it was used for (language editing, drafting, code, analysis, figures, literature search), which parts of the work it touched, and how the authors checked its output.
- **This session counts.** Drafting the letter, the title page or the statements with this skill is use of an AI tool that the authors may have to disclose. Say so to the authors when you ask about AI use, and let them decide.
- **Placement** (methods, acknowledgements, a separate statement, the letter, a form) is the venue's rule: take it from the guidelines.
- **Avoid:** a "no AI tools were used" sentence the authors did not confirm; listing an AI tool as an author or in the contributions; inferring use from files or logs without asking. AI as the subject of the research is described in the methods, not in this statement.

## Acknowledgements

- **Needs:** whom to thank and for what, as the authors list them. People named should have agreed to be named; that is the authors' to confirm.
- **Avoid:** thanking reviewers or editors of this submission; in a double-blind review, the section goes on the title page or is removed from the reviewed file, as the guidelines say.

## Title page

- **Contents:** the exact title; the authors in byline order; numbered affiliations; the corresponding author with email; equal-contribution and present-address notes; and whatever else the guidelines place there (word counts, keywords, running title, statements in a double-blind review).
- **Numbering:** affiliations are numbered in the order they first appear in the author list. Generate the author block instead of typing it:

  ```sh
  python3 "$SKILL_DIR/scripts/check_package.py" --authors submission/<venue-slug>/authors.json --author-block
  ```

- **Avoid:** an affiliation that differs from `authors.json` (the script compares them); a corresponding author without an email; counts that disagree with the manuscript.

## Highlights, key points, significance statements

Write them only when the venue asks, in the form and limits recorded in `requirements.json`.

- Each item is one finding or implication that the manuscript supports with a result; numbers in them must be in the manuscript.
- Plain words, no abbreviations a general reader would not know, no citations, no priority claims without a search.
- A significance statement is for readers outside the field: the problem, what was found, why it matters, without repeating the abstract's sentences.
- `check_package.py` counts the items of `highlights.*` (one per bullet, or one per line) and the characters of each, spaces included.
