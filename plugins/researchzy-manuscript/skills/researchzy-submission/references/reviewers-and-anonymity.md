# Reviewers and anonymity

## Suggested reviewers

Only when `requirements.json` marks suggested reviewers `required` or `optional`. Names come from the authors, or from Researchzy results the authors accept (below). Never propose a person from memory: a name you recall may be wrong, retired, or a close collaborator.

Write `submission/<venue-slug>/reviewers.md`:

| Name | Institution | Email | Expertise, tied to a paper | Source | Conflict (authors confirm) |
|---|---|---|---|---|---|
| [from the authors] | [from the authors] | [from the authors] | "Works on soil moisture memory: [title, year]" | authors / Researchzy `search_papers`, query "…" | [Author input needed: confirm none of the conflicts below] |

- **Expertise** names a paper of theirs on the manuscript's topic, so the editor can see why they are suitable.
- **Email and institution** come from the authors or from the person's own institutional page that the authors give; the Researchzy index has neither.
- **Conflict** is confirmed by the authors for each name, never filled by you. Leave the placeholder until they answer.
- **Spread:** suggest people from more than one group and, where the field allows, more than one country, unless the authors have a reason not to.

### What counts as a conflict

Ask the authors to confirm, for each suggested reviewer, that none of these applies. The time windows are the venue's when its guidelines give them; otherwise ask the authors to apply their own judgement and say which window they used.

- Co-authored a paper, preprint or grant with any author recently.
- Works, or recently worked, at the same institution or department as an author.
- Supervised an author, or was supervised by one.
- Collaborates with an author now, including on a project not yet published.
- Has a personal relationship, a financial interest in the result, or a known dispute with an author.
- For a review or meta-analysis: authored studies included in it.

### With Researchzy connected (plugin `researchzy`, account needed)

1. Run `search_papers` with the manuscript's topic keywords, recent years (`yearFrom`) and `sort` by relevance; save the results to `submission/<venue-slug>/reviewer-candidates.json` as returned.
2. Offer the authors of the closest papers as candidates, each with the paper that makes them a candidate. The authors accept or reject each one.
3. Partial conflict flag: look up the manuscript's own references by `doi` and save those results too. A candidate who is a co-author of one of those papers together with a manuscript author is flagged `shared paper found: [title]`. Every other candidate is `not checked`: the index has no author search, no affiliations and no complete publication lists, so finding no shared paper proves nothing.
4. Names in the index can be written differently from one paper to another; same-name matches are leads, not identities.

### Opposed reviewers

Only when the venue allows it. Each entry is a name and a short factual, impersonal reason: "direct competitor on the same question; preprint of a competing study under review elsewhere", "co-author on a dispute about the same data". Never a remark on competence or character. Keep the list short; the editor may not honour it.

## Anonymity for double-blind review

Run `check_anonymity.py` on the folder of files the reviewers will see, with the title page and the letter passed as `--identified` when the venue keeps them from reviewers. It reads text, LaTeX, Office files, PDF properties (with Poppler) and image metadata, and it never changes a file. Fix what it lists in the source files, rebuild, and run it again.

Self-citation is not forbidden: most venues ask that the authors' own work be cited in the third person ("Okafor et al. (2021) showed" instead of "we showed in our earlier work"), and some ask for "Anonymous (2021)" with the entry withheld. Follow the guidelines; do not replace every self-citation by default, which can make the paper harder to review.

### Checklist beyond the script

- **Figures as pictures:** names, institution logos, map labels, photographs of buildings or sites, screenshots that show a user name, axis labels from a lab's internal code names. The script reads metadata only.
- **Supplementary material:** every file, including spreadsheets, notebooks and code archives, goes through the same check. Unzip archives into a separate folder and run the script on it. Look at notebook outputs, Git history (`.git` folders must not be uploaded), and configuration files with user names.
- **Links:** code and data links point to an anonymised copy or are given to the editor only, as the guidelines say. A link to a personal page, a lab page or a named repository identifies the authors even if the page is empty.
- **Indirect identification:** a named cohort, site, instrument, local dataset or project acronym that only one group uses; funding and ethics ids; "our institution's hospital".
- **Earlier venues:** mentions of a workshop or conference where the work was presented, and replies to earlier reviewers.
- **The submission system's PDF:** after uploading, open the PDF the system builds, search it for each author's family name, and check its properties. The system sometimes adds files, metadata or a cover page of its own.
- **Your own report files:** `report.md`, `anonymity.md`, `authors.json` and `requirements.json` are working files. Never upload them.
