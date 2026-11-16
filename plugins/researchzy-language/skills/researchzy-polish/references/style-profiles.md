# Style profiles

A profile is a set of counts that describes how a group of texts is written: sentence length, words per paragraph, connectors, hedges and boosters per 1,000 words, "we", a passive-voice proxy, US or UK spelling, serial commas, dashes, abbreviations, and "significant" with or without a test nearby. It is a description of those texts, not a standard. It never contains their text.

## The author's own voice

- Use three or more texts the author wrote as the main writer (three is a convention; `--min` changes it). Papers in the same genre as the draft describe it best. Leave out texts drafted mainly by co-authors and drafts written with an AI tool: the profile would describe someone else's habits as the author's.
- Build:

  ```sh
  python3 "$SKILL_DIR/scripts/style_profile.py" build earlier1.txt earlier2.docx earlier3.md --out polish/profile-author.json
  ```

  Files are `.md`, `.tex`, `.txt` or `.docx`. Turn a PDF into text first and check that the text is complete.

## A target journal

### With the Researchzy tools (plugin `researchzy`, needs an account)

1. **Search.** Run `search_papers` with `query` set to two to five keywords of the manuscript's topic, `venue` set to the journal's name, `yearFrom` three years before the current year (a convention), `sort: year`, `pageSize: 50` and `detail: full`, which returns whole abstracts. Take a second page, or a second query with other topic words, until about 40 hits are in hand or the results run out.
2. **Save** the results as returned, with what was asked and when:

   ```json
   {"searches": [{"query": "night shift sleep nurses",
                  "filters": {"venue": "Journal of Sleep Research", "yearFrom": 2023},
                  "sort": "year", "date": "2026-11-13", "results": ["…the hits exactly as the tool returned them…"]}]}
   ```

3. **Build**, naming every spelling of the journal that the hits' `venue` field uses:

   ```sh
   python3 "$SKILL_DIR/scripts/style_profile.py" build --search-json polish/journal-hits.json \
     --venue "Journal of Sleep Research" --venue "J Sleep Res" --out polish/profile-journal.json
   ```

   Hits from another venue, hits without an abstract and duplicates are dropped and counted in `sample`.
4. **Know what the sample is.** The index matches keywords in titles and abstracts, so the hits are papers on the manuscript's topic in that journal, not a random sample of the journal. Only titles and abstracts are measured, so the profile describes abstracts: compare it with the draft's abstract, saved as its own file. The index may lag the newest issues.
5. **Too few.** Below 20 abstracts (a convention) the status is `not enough texts`. Widen the topic words or the years; do not drop the venue filter, which would describe other journals.

### Without the tools

Use journal papers the author supplies, as text files: `build paper1.txt … --kind journal --out polish/profile-journal.json`. Five papers is the conventional minimum here, because a full paper holds far more sentences than an abstract. Say in the delivery that connecting Researchzy would let the profile be built from the journal's recent papers.

## The profile file

| Field | Holds |
|---|---|
| `kind`, `basis`, `status`, `texts`, `minimum` | author or journal; what the texts are; `ok` or `not enough texts` |
| `sources` | per text: file name and SHA-256, or corpus id, DOI and year; and its counts |
| `sample` | for search results: each search's query, filters, sort and date; hits; drops by reason |
| `profile` | sentence length and words per paragraph (median and quartiles), rates per 1,000 words, the range of each across the texts, spelling, serial commas, "significant", the commonest connectors; for abstracts also title length, colons in titles, the share of structured abstracts and abstract length |

Never add text to this file or to anything else under `polish/`: no sentences, titles or abstracts from the papers.

## Using a profile

- `compare` writes notes such as "we per 1,000 words: 1.2 in the draft, 6.5–11.0 in the author's texts". Pass them to the author as observations. They are not errors and not instructions.
- Change nothing to match a profile unless the author asks for that change; then only within the agreed level, and never a claim word. A profile's hedge rate is never a reason to add or remove a hedge.
- What a profile may settle, with the author's agreement, are choices of equal meaning: US or UK spelling, the serial comma, one form of a term.
- A journal's abstracts are not its rules. Requirements such as word limits, structured abstracts or spelling come only from the journal's current author guidelines, supplied by the user or read in this session, with the address and the date read; otherwise they are not checked. Formatting to those requirements is `researchzy-submission` (plugin `researchzy-manuscript`, when installed).
- Never copy or closely follow a sentence of another paper, and never carry over its content.
- A profile is a writing aid. It says nothing about how any AI detector will read the text; do not present it that way.
