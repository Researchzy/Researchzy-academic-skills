# Bands, reasons and the cascade plan

## Two questions, answered apart

1. **Does the venue cover the topic?** This skill answers it, from the tallies, the venue filter pass and the venue's own scope statement.
2. **Can this article type and this design clear the venue's bar?** This skill does not judge it. A critical read of the manuscript is the job of `researchzy-paper-review` (plugin `researchzy-manuscript`, when installed). Write "Design and rigour: not judged here" for every venue, unless that review was done in this session; then cite its main concern in one clause.

Only two hard blocks come from this skill, and only from facts read in this session: the venue does not accept the article type (its author instructions say so), or a recorded fact conflicts with a constraint the user gave (open access required and the venue is subscription only; a recorded fee above the user's ceiling). A blocked venue leaves the shortlist, or stays as `stretch` with the block named when the user asked for it.

## Bands

Each venue gets exactly one band. A band says how well the evidence places the topic in the venue, and what is known to stand in the way. It is not a chance of acceptance.

| Band | Topic evidence needed | And |
|---|---|---|
| `strong fit` | At least three similar papers since the cutoff year, or at least two in each stream; and at least two on-topic papers from the venue filter pass | No known block; the scope statement, when read, names the topic or its field |
| `plausible` | At least one similar paper, or two references, or one on-topic paper from the venue filter pass | No known block |
| `stretch` | Any of: the evidence is only older references; the venue filter found nothing recent; the venue was added by judgement with no paper from the index; the scope statement read in this session asks for something the manuscript may not have (for example results of broad interest beyond one field) | Name what makes it a stretch |

The thresholds are counts of returned rows, so they move with the queries. When the counts fall just short of a band, give the lower band and say why in the reason.

## The reason

One or two sentences, written from the evidence and nothing else:

- the counts and years from `tally.md`, or "added by judgement" and why;
- what the venue filter pass found;
- the scope statement's words, when read;
- for `plausible` and `stretch`, what holds it back.

No adjectives about the venue's prestige, no remembered metric, no "top", "leading" or "high-impact". If the user asks for metrics, say that they are not checked by this skill and leave them for the user to read on the venue's site or in their library's databases.

## Order

Order the shortlist by band (`strong fit` first), then by the amount of evidence. Put a venue that meets the user's constraints before one that does not or is unknown. Never compute a score or a weighted total.

## Cascade plan

A table of three to five steps, each a venue on the shortlist, with when to move to it.

| Step | When | Choose |
|---|---|---|
| 1 | First submission | The venue the user prefers among the `strong fit` ones, or the user's ambitious `stretch` when they ask for it, followed by `strong fit` ones |
| 2 | After a desk rejection (returned without review) | Read the editor's letter. Scope: the next venue with the strongest topic evidence. Interest or novelty: a venue with a narrower readership in the same field. Design or reporting: fix the manuscript first (`researchzy-paper-review`), then go on |
| 3 | After a rejection following review | The reviews show what to fix. Mark each concern fixable in the text, fixable with new work, or not fixable; fix what can be fixed (`researchzy-rebuttal` helps list and answer them). Then a venue of the same band, or a same-publisher transfer when offered |
| 4 | After a second rejection | Revisit the band of every remaining venue with what the reviews said |

Never write a number of weeks or days in the plan unless `facts.json` records it; write "after the time the venue states".

### Same-publisher transfer

Some publishers offer to pass a rejected manuscript, and sometimes its reviews, to another of their journals. Whether this venue's publisher does, and on what terms, is a fact to confirm on its site. Never assume it from the publisher's name. Accepting a transfer is still a new submission to a venue the user should judge on the same evidence.

### Presubmission inquiry

Some venues accept a short inquiry (an abstract and a few lines on why it fits) before a full submission. It is worth sending when the open question is whether the editors see the topic as theirs or of enough interest, not when the risk is the design. Whether the venue accepts inquiries is a fact to confirm on site.

### Before moving to the next venue

- Reformat to the new venue's instructions: `researchzy-latex` and `researchzy-writing` (plugin `researchzy-manuscript`, when installed).
- Remove any mention of the earlier venue or its reviews from the manuscript.
- Check the new venue's policy on preprints and earlier submissions.
- Write a new cover letter: `researchzy-submission` (same plugin, when installed).
- Submit to one venue at a time.

## What was checked about a venue

Report, per venue, what was looked up and what came back, in these words:

| Situation | Write |
|---|---|
| Crossref `found` | "Registered with Crossref as <title>, <publisher>; DOIs deposited in <years>" |
| Crossref `not_matched` | "Crossref has no journal of this exact name; nearest: <titles>" |
| Crossref `not_found` | "Not in Crossref's journal list (expected for a conference)" when it is a conference; otherwise "Not in Crossref's journal list" |
| DOAJ `listed` | "Listed in DOAJ; fee, licence and review model as declared to DOAJ" |
| DOAJ `not_found` | "Not listed in DOAJ (expected for a subscription or hybrid journal)" |
| Either `lookup_failed` or not looked up | "Not checked: <registry> did not answer" or "not looked up" |

The skill never calls a venue safe, legitimate, reputable or predatory. A venue absent from both registries, with no page read and no paper from the index, is reported in exactly those terms, and the user decides.
