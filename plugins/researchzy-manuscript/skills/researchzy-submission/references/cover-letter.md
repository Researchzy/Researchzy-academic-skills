# The cover letter

Write a letter only when `requirements.json` marks it `required` or `optional`. When the venue does not accept one, do not write it, and put what it would have carried (a related manuscript, an opposed reviewer) where the guidelines say.

A letter is read by an editor deciding whether to send the paper out for review. It does one job the abstract cannot: it says why this paper belongs in this venue now, and it discloses what the editor must know before deciding. Everything in it must be checkable against the manuscript or `authors.json`.

## What it contains

| Part | Content | Facts come from |
|---|---|---|
| Request | The title, word for word as in the manuscript; the article type; the venue | `requirements.json`, the manuscript |
| The question and the answer | One or two sentences: what was asked and the main result, with its number | The manuscript's results, rephrased, not copied from the abstract |
| What is new | One or two sentences: what this adds to the work it builds on, named | The manuscript's introduction and its citations |
| Why this venue | One sentence tied to the venue's stated scope or to recent papers it published on the topic | The guidelines; with Researchzy, `search_papers` with `venue` |
| Declarations | Only what the editor must see before review: competing interests, related manuscripts under consideration or in press, a preprint, prior consideration of this work by another venue when the authors want to say so, opposed reviewers when there is no form for them | `authors.json`; the authors |
| Statements the venue asks for | For example that all authors approved the submission and that the work is not under consideration elsewhere, only when the guidelines ask for them in the letter and the authors confirm them | The guidelines; the authors |
| Close | The corresponding author's name and contact | `authors.json` |

## What it must not do

- **Repeat the abstract.** `check_package.py` lists every letter sentence that is a copy of an abstract sentence. Say what the abstract does not: why it matters to this venue's readers, what it changes.
- **Claim priority without a search.** "First", "novel", "unprecedented", "groundbreaking", "unique" are claims about the literature. Keep one only when a logged search supports it (`researchzy-literature-review`, plugin `researchzy`, when installed) and say what it is first at; otherwise write the specific advance instead ("the first to measure X in Y" becomes "measures X in Y over three seasons, where earlier studies used single surveys").
- **State numbers the manuscript does not have.** Counts of words, figures and tables, sample sizes and effect sizes must equal the manuscript's; the script compares them. Prefer no counts at all unless the guidelines ask for them.
- **Argue with future reviewers**, pre-empt objections, or ask for a fast decision.
- **Name-drop**: no praise of the editor, no "as discussed with", no names of people who read the draft unless they are in the acknowledgements.
- **Leak the drafting**: no line numbers of internal drafts, file names, tool names or comments about how the text was produced.
- **Invent a declaration.** A competing interest, a related manuscript or a preprint comes from the authors; if they have not answered, write `[Author input needed: …]`.
- **Carry identifying details into a blinded review.** The letter normally goes only to the editor, but check the guidelines; if it is shared with reviewers, it is blinded like the manuscript.

## First submission and submission after a rejection elsewhere

| | First submission | After a rejection elsewhere |
|---|---|---|
| Fit sentence | Written for this venue | Rewritten for this venue: a sentence aimed at the earlier venue is the commonest leftover |
| Title, counts, article type | As in the manuscript | Rechecked: the manuscript usually changed |
| Earlier reviews | Not applicable | Mention them only if the authors choose to, or the venue asks; then say briefly what changed in response. Never attach the earlier reviews without the authors' decision |
| Transfer | Not applicable | If the manuscript comes through a publisher's transfer service, follow that service's instructions instead of writing a new letter from scratch |
| Leftovers to search for | None | The earlier venue's name, its article-type names, its formatting terms, its editor's name. Add the earlier venue to `anonymity.earlier_venues` so `check_anonymity.py` finds it |

## Skeleton

Plain text, one page or less. Replace every bracket; leave the ones you cannot fill as `[Author input needed: …]`.

```text
Dear [Author input needed: editor's name, or "Editor"],

We submit "[exact title]" for consideration as a [article type] in [venue].

[The question, in one sentence.] [The main result, with its number, in different words from the abstract.]

[What this adds to the named earlier work, in one or two sentences.]

[Why the venue's readers need it: one sentence tied to the venue's stated scope or to its recent papers on the topic.]

[Declarations the editor must see: competing interests, related manuscripts, a preprint, opposed reviewers when there is no form.]

[Statements the guidelines ask for in the letter, as the authors confirmed them.]

Sincerely,
[Corresponding author], on behalf of all authors
[Affiliation], [email]
```

No length is a rule of this skill. When the guidelines give a length, it is in `requirements.json` and the script checks it; when they do not, keep the letter to what the parts above need.
