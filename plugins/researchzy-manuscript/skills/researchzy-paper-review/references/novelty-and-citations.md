# Novelty and missing citations

This step tests what the manuscript says about the literature against records a search returned in this session. It uses Researchzy's `search_papers` and `get_paper`, which come with the `researchzy` plugin and need a Researchzy account. Without them the step is skipped and the review says so.

## When Researchzy is not connected

Set `checks.novelty` to `{"status": "skipped", "note": "Researchzy is not connected."}` and give no `closest_works`. Then:

- Do not judge novelty and do not name prior work from memory. A remembered title may belong to no paper, and one invented reference in a review costs the reviewer the author's trust in the rest.
- Each `priority` claim in the claim table still becomes a finding with status `unresolved`: quote the claim, and make the fix "confirm it with a literature search, or drop the word". Severity follows how much of the paper rests on the claim.
- Tell the user that installing the `researchzy` plugin and signing in adds this check.

## With Researchzy connected

1. **Decide what to test.** Take every `priority` claim from the claim table. Then write the contribution down in the field's ordinary words: the problem, the method, the setting or population, the main result.

2. **Search.** Use short queries of two to five distinctive words; put a phrase in double quotes to keep its words together. The index matches words as written, so run the variants as separate queries: synonyms, an abbreviation and its expansion, British and American spelling. Run at least these:

   | Search for | Query | Options |
   |---|---|---|
   | The same problem with the same kind of method | problem words + method words | default sort |
   | The same method on another problem | method words | default sort |
   | Recent work on the problem | problem words | `yearFrom` three years back, or `sort: year` |
   | Earlier surveys | problem words + `review` or `survey` | |
   | Each "first", "only" or "state of the art" | the words for the thing claimed to be first | |

   Log each query when it is run, with the `total` the tool reported, under `checks.novelty.searches`. For the user's own draft, also search their library (`list_library_papers` with `query`): authors often hold a paper they forgot to cite. In referee mode, queries use general terms only: see [Referee mode](referee-mode.md).

3. **Choose the three to five closest works.** A work is close when a reviewer who knows it would ask how the manuscript differs from it. Read each abstract (`get_paper` with `detail: full` when the search result was brief). When the comparison turns on a detail the abstract does not give, read the full text: `get_pdf_download`, or `researchzy-deep-read` (plugin `researchzy-reading`, when installed).

4. **Compare.** For each closest work record, under `checks.novelty.closest_works`:

   | Field | Content |
   |---|---|
   | `corpusId`, `title`, `year` | As the tool returned them. |
   | `cited` | `true` when the work is in the manuscript's reference list. Look for its title or DOI there; do not assume. |
   | `differs` | One or two sentences setting the manuscript against the work on problem, method, data or setting, and result, and saying whether the work appeared clearly earlier, at about the same time, or later. Say when this rests on the abstract alone. |

5. **Turn the comparison into findings.**

   | The search shows | Finding |
   |---|---|
   | An earlier work did what a `priority` claim says had not been done | Quote the claim. Basis: the record and what its abstract or text says. Fix: drop or narrow the claim and state the difference. Major when the contribution rests on the claim. |
   | A closest work is not cited | No quote; `where_looked` is the reference list and the related-work section. Minor, or major when it is the obvious comparison. A work from about the same time is to be cited, not to be beaten. |
   | A closest work is cited, and the manuscript's account of it looks wrong | Hand it to `researchzy-reference-check`, whose claim check compares the citing sentence with the source. |
   | The comparison leaves out a baseline that the retrieved works all use | A finding on the `improvement` claim, with those records as basis. |
   | Nothing close came back | No finding. The report lists the searches. |

## Rules

- The review names a paper only when a tool returned it in this session and it is listed in `closest_works` with its `corpusId`. This covers findings, suggested citations and the referee report. The script refuses a listed work without a `corpusId`, and any listed work when the check was skipped.
- "No closer work was found" is a statement about the logged searches. Never write that the work is novel.
- From an abstract, report what the abstract says and nothing about methods or limitations.
- The index can lag the newest publications by some months and has no "cited by" search. State the newest publication year seen, and that later work may be missing.
- Citation counts do not make a work close, and a missing citation is not a finding because the work is famous.
- Searching and reading do not add papers to the user's library. Save only when asked.
- Report a tool failure with its `code` and `userMessage`. An error is not an empty result: when the searches failed, the status is `skipped`.
