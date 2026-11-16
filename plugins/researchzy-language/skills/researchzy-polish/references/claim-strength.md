# Claim strength

A polish keeps every claim exactly as strong as the author made it. Wording that sounds more confident, or more careful, changes what the paper says, so a move in either direction is an error: the author may agree to a change of strength, but that is content, and it is decided outside the polish.

## The ladder

`polish_check.py` finds these words in each sentence (with their other forms: "suggests", "suggested") and compares the sentence before and after; for a split or merge it compares the group of sentences.

| Rung | Means | Words |
|---|---|---|
| 1 | possible | may, might, could, possibly, perhaps, potential(ly), conceivably, plausibly |
| 2 | suggested | suggest, indicate, appear, seem, imply, likely, unlikely, probably, presumably, apparently, tend to, consistent with |
| 3 | associated | associated, association, correlated, correlation, linked to or with, link between |
| 4 | shown | show, find, found, demonstrate, reveal |
| 5 | caused | cause, causal, lead to, result in, drive, due to, because, owing to, attributable to, contribute to, induce |
| 6 | certain | prove, establish, confirm, clearly, definitely, undoubtedly, conclusively, certainly, unequivocally |

A changed count on any rung is an error. The report says whether the sentence moved up (a hedge gone, a stronger verb added) or down. Swapping words on the same rung ("suggest" for "indicate", "might" for "may", "linked to" for "associated with") is allowed. "Table 2 shows" and "as shown in Figure 1" describe a display and are not counted.

## Other words that carry the claim

| Class | Words | Why it matters |
|---|---|---|
| negation | not, no, never, without, neither, nor, unable, fail to, lack, absence of, non-significant | "did not differ" and "was similar" are different findings |
| quantifier | all, every, each, always / most, majority, usually / many, often / some, several, a few, partly / few, rarely / none | "few" denies, "a few" affirms; "some" to "most" generalises |
| scope | only, solely, exclusively, merely | removing "only" widens the claim |
| significance | significant(ly), non-significant, significance | a statistical claim; never swap it for "notably" or "markedly" |
| intensifier, downtoner | substantially, markedly, very, strongly … / slightly, somewhat, modestly, marginally … | the size the author claimed |
| approximation | approximately, about or around before a number, roughly, nearly, almost, ~ | removing it makes a number exact |
| modal | can, will, would, should, must, shall | ability, prediction, recommendation and necessity are different claims |
| contrast | however, but, although, whereas, nevertheless, despite, in contrast … | a transition may change only inside its class |
| consequence | therefore, thus, hence, consequently, as a result, so (before a clause) | adding one asserts an inference the author did not make |
| direction | higher, increase, better … against lower, decrease, worse … | a flip says the opposite |
| article before a cause-like noun | a or the before cause, reason, factor, driver, determinant, mechanism, predictor, source … | "a cause" is one of several; "the cause" is the only one |
| tense of results | was, were, had, showed, found, increased … becoming is, are, has, shows … | the present generalises a finding from the sample to everyone |

## Safe to fix, and not safe

Non-native writing often needs edits that are pure language. These are safe: articles (except before a cause-like noun), agreement ("the data was" or "were", following the paper's own usage), prepositions, word order that keeps every word's role, plural forms ("informations", "researches"), a missing subject, run-on sentences split at a full stop (medium).

These look like mistakes and are not language edits; leave them, and ask when in doubt:

| Pair | The difference |
|---|---|
| may not / cannot | possibly not, against impossible |
| must not / need not | forbidden, against not required |
| should / will | a recommendation, against a prediction |
| can / may | ability, against possibility |
| few / a few | hardly any, against some |
| did not differ / was similar | no evidence of a difference, against evidence of similarity |
| significantly / notably, markedly | a test result, against a size |
| may suggest / suggests | two hedges are stronger doubt than one; keep both unless the author drops one |
| was associated / is associated | in this sample, against in general |
| slightly better (not significant) / similar | a claim the evidence may not carry: a query, not an edit |

## What the script does not see

Read every edited sentence yourself as well. The script misses:

- a claim word outside its lists ("supports", "highlights", "underscores", "affects"), and a change of meaning that keeps the same listed words;
- a change of who did what (an active sentence that names the wrong actor), of population, comparator or time point;
- "one" as a number (it is skipped because it is so often a pronoun);
- a result tense moved from past to present with a verb outside its list;
- text in languages other than English, whose claims are reported as not checked.

And it can raise an error over a harmless edit: "could not" (ability) rewritten as "were unable to", "whereas" replaced by "while" (not on the contrast list, because it is also a word of time), "twenty five" without a hyphen (read as 20 and 5) written as 25, a place or name followed by a year in brackets ("Ireland (2019)") read as a citation and then rewritten. Keep the original wording in such cases; the polish does not need the change.
