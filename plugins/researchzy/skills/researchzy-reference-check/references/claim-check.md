# Claim check

The reference check says a paper exists. The claim check asks whether the paper says what the manuscript says it says. It is slower: each checked citation means reading a source.

## 1. Choose the citations

`reference-check/references.json` lists every citation the script located under `citations`, with its file, line and sentence. `"check": true` marks sentences that carry something checkable:

- a number (`3.57%`, `n = 120`, `2.4-fold`);
- a comparison (outperforms, higher than, significantly, reduced);
- a claim of priority (first, only, state of the art);
- quoted words.

Default scope: the citations marked `check`. Agree a different scope with the user when the list is long: all citations, one section, or the ten claims the paper's argument rests on. Citations of references whose verdict is `identifier_not_registered` or `unconfirmed` cannot be checked; list them as not checked.

The script locates LaTeX, Pandoc and numeric citations. For author-year citations ("Smith et al. (2020) showed…") read the manuscript and add them yourself.

## 2. Get the source text

Try in this order and record which one you used in `read`:

1. A file the user supplied.
2. Researchzy: find the record (`lookups.json`, `for_full_text`, gives the `search_papers` call), then `get_pdf_download` with its `corpusId`. Follow the PDF rules of the `researchzy` skill: download before the URL expires, send no Researchzy credentials to the signed URL, check that the file is a PDF.
3. `researchzy-download`, for an open-access copy.
4. The abstract returned by `search_papers` or `get_paper` (pass `detail: full`). Save it as a text file. `read` is then `abstract`.

Save sources under `reference-check/sources/`. For a PDF you cannot read directly, make a text file with page markers:

```sh
python3 "$SKILL_DIR/scripts/check_claims.py" text reference-check/sources/he2016.pdf
```

Its output says how many words were extracted; under 400 words the file is an abstract or a scan without text, not a full text.

Getting a paper for this check does not add it to the user's library.

## 3. Judge each citing sentence

Read the relevant part of the source, not only a search hit: the sentence around a matching number can say the opposite. Then write one entry per citation in `reference-check/claims.json`:

```json
{"claims": [{
  "id": "c1",
  "ref_id": "he2016",
  "location": "main.tex:3",
  "sentence": "Residual networks reduced the top-5 error on ImageNet to 3.57%.",
  "verdict": "supported",
  "quote": "An ensemble of these residual nets achieves 3.57% error on the ImageNet test set",
  "page": 1,
  "source": "sources/he2016.pdf",
  "read": "full_text",
  "comment": "The figure is for an ensemble, which the sentence does not say."
}]}
```

| Verdict | Use when | Quote |
|---|---|---|
| `supported` | The source states what the sentence attributes to it: the same quantity, population, direction and condition. | Required |
| `partly_supported` | The source supports part of the sentence, or supports it under a narrower condition, with a different number, or less strongly. Say what differs in `comment`. | Required |
| `not_supported` | You read the relevant parts of the full text and the source does not say this, or says otherwise. | What the source says instead, when there is such a passage |
| `cannot_tell` | Only the abstract was available and it does not settle the claim. | No |
| `not_checked` | No text could be obtained. | No |

Rules for the quote:

- Copy it from the source, word for word, at least five words, from one passage. Do not join distant passages and do not repair the wording.
- Give the page when the source has pages. The script corrects it when it finds the quote on another page.
- For a number, the quote must contain the number and what it measures.

Compare five things before writing `supported`: the metric and its unit, the denominator or sample, the population or dataset, the direction of the effect, and the conditions (model, dose, time point). A matching number with a different denominator is `partly_supported`.

From an abstract, `supported` is allowed only when the abstract itself states the claim; the report marks it "abstract only". Never write `not_supported` from an abstract: use `cannot_tell`.

## 4. Verify the quotes

```sh
python3 "$SKILL_DIR/scripts/check_claims.py" check reference-check/claims.json
```

It writes `claims-checked.json` and `claims.md`. For each entry:

| Check | Meaning | Do |
|---|---|---|
| `quote_found` | The quote is in the source. | Nothing. |
| `quote_unresolved` | Most of the quote's words are there in order, some are missing. | Reread the passage and copy the quote again. |
| `quote_not_found` | The quote is not in the source. The verdict is not accepted. | Reread the source. Correct the quote, or change the verdict. |
| `quote_too_short` | Fewer than five words. | Quote the whole sentence. |
| `needs_quote` | A supported verdict without a quote. | Add the quote. |
| `no_source` | The source file is missing. | Fix the path, or set the verdict to `not_checked`. |

Run it again until no supported or partly supported verdict is left unaccepted, or report the ones that remain as unresolved.

Known limit: the match tolerates extraction noise between the quote's words, so a quotation that omits a word such as "not" can still be found. Reread any quote that turns on a negation or a qualifier.

## 5. Report

From `claims.md`: counts per verdict first, then `not_supported` and `partly_supported` citations with the sentence, what the source says and the page, then what could not be checked and why. For each problem suggest the smallest honest change: soften the sentence, correct the number, cite a different source, or remove the citation. Propose wording; change the manuscript only when the user asks.
