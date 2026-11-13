# Generating candidates

## What a candidate is

A candidate is one sentence that names three things:

> We do not know **the unknown**. **The mechanism** would explain it. **The evidence** would tell, because it looks different when the mechanism is absent.

Illustration (invented for this file, not a finding): "We do not know whether interleaved homework helps students choose a method or only gives them more practice; if it trains method choice, the gain should appear on problems where the method is not given and not on the others; item-level exam scores from interleaved and blocked course sections would tell."

A sentence that cannot be completed is not yet a candidate. These are not candidates:

- a topic ("X in Y");
- a method without a question ("apply X to Y");
- a wish ("a better model of X");
- a paper the user already holds, restated.

## How to run the operators

1. Pick three or four operators from the situation table below.
2. Run each one to its required output, using only the evidence base: the review's gaps, the Paper Card, the abstracts read in step 2, and what the user told you. When the required output cannot be written from that, the run is empty. Note it in one line and move on. Do not fill the blank from memory.
3. Collect six to ten candidates in the sentence form. Fewer is fine when the evidence base is thin; say so.
4. Merge:

   | The two candidates share | Do |
   |---|---|
   | Unknown, mechanism and evidence | One candidate. Keep the clearer wording |
   | The unknown, with different mechanisms | Keep both. They are rivals, and one study may separate them: name each as the other's `if_rival` |
   | The mechanism, with different unknowns | Keep both |
   | Only the topic | Unrelated. Keep both |

5. Write a card for each candidate that is left. In the report, name the operators that ran empty and the candidates that were merged.

## Operators

| Operator | What it does | Must output | An empty run looks like |
|---|---|---|---|
| Gap to question | Turns a gap a review logged into a question whose answer matters | The gap with its search ids; the unknown; who would act differently once it is answered | "More research is needed on X". The gap restated with no mechanism. "Nobody has studied X in Y" with no reason the answer would differ in Y |
| Unexplained observation | Starts from a result that does not fit: an outlier, a failed replication, something the user saw | The observation as it was seen, before any reading of it; at least two explanations of different kinds (artefact, selection, real effect); what would separate them | One explanation, the hoped-for one. An observation nobody could see again |
| Rival explanation | Takes an accepted finding and names another process that gives the same data | The finding and its paper; the rival, named; one observation on which the two differ | A rival called "confounding" or "noise" with no variable named. No observation separates the two |
| Untested assumption | Lists what a method or a line of work takes for granted and picks one that nobody measured | The assumption; where it is relied on (paper and section); what fails if it is false; how it could be measured | An assumption already known to be violated and already handled. A consequence nobody can name |
| Contradiction | Sets two results that disagree side by side and looks for the condition that differs | Both results with their numbers; the condition that may separate them; a design that varies only that condition | The two papers measure different things, so they do not disagree. "Results are mixed" |
| Boundary | Pushes a known result to a scale, population, dose, time span or setting where its mechanism should stop working | The result; the boundary; the reason the mechanism predicts a change there | "Test it on another dataset, country or species" with no reason to expect a different answer |
| Transfer | Brings a method or model from another field | What plays the role of what; the one place where the mapping fails; what the method would show that current ones cannot | The match is only in the vocabulary. No stated gain over the current method |
| What changed | Looks for a new dataset, instrument, policy, price or event that makes an old question answerable | What became available and when; the question it unblocks; why that question was blocked before | The new thing is the whole idea ("use the new instrument"). No question behind it |
| Claim ladder | Moves a known claim one rung: descriptive, associational, predictive, causal, mechanistic. Up when the lower rung is solid, down when a causal story rests on a description nobody made | The current rung and the evidence for it; the next rung; the design the next rung needs | A jump to "the mechanism" with data that can only show an association |
| Decision backward | Starts from a decision somebody has to make and finds the unknown that blocks it | The decision and who makes it; the unknown; how each answer would change the decision | "Relevant to policy makers" with no decision named. Either answer leads to the same action |

An operator's output is raw material, not yet a candidate: finish the sentence (unknown, mechanism, evidence) before counting it.

## Which operators to try

| The researcher's situation | Try first | Why |
|---|---|---|
| Has a finished review with logged gaps | Gap to question, Contradiction | The gaps and the disagreements are already documented with their searches |
| Has an odd result or an observation of their own | Unexplained observation, Rival explanation | The observation is theirs; the work is to keep more than one reading of it alive |
| Has just read one paper (a Paper Card) | Rival explanation, Untested assumption, Boundary | A single paper offers its own limits and assumptions, not a view of the field |
| Holds data, an instrument or access that others lack | What changed, Boundary | The advantage is the ability to answer, so look for questions that were blocked |
| Brings a method or skill from another field | Transfer, Untested assumption | Outsiders see what a field takes for granted; check the mapping before the promise |
| Works in a crowded area where the obvious questions are taken | Untested assumption, Rival explanation, Claim ladder | Depth is still open where breadth is not |
| Has a hypothesis that feels vague (Sharpen entry) | Claim ladder, Rival explanation | Fixing the rung and the rival is most of the sharpening |
| Needs the work to matter to practice or to a funder | Decision backward | Value is settled first, and the question follows from it |
| Has little time, or is new to the field | Contradiction, Boundary (with a stated reason) | Both start from published results and need one focused study. Avoid Transfer: learning two fields takes the time available |

## When the whole run is empty

Stop generating and tell the user when any of these holds after two passes:

- every candidate comes from the same single paper;
- every candidate has the form "apply X to Y";
- no candidate names evidence that would tell.

The evidence base is too thin. Offer `researchzy-literature-review` for a map of the field, or ask the user for the observation or the puzzle that brought them here. Do not pad the list to reach six.
