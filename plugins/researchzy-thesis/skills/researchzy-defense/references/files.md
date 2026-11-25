# Files in defense/

All files are UTF-8. Paths inside the JSON files (reports, search records) are read from the working directory, else from `defense/`.

## thesis-pages.txt (written by `pages`; do not edit)

Header lines start with `#`: source file, SHA-256, date read, reader (`PyMuPDF`, `pdftotext` or `text`), `paged`, `status` (`ok`, or `not_checked:` with the reason), the runs of printed numbers and the tables and figures at the page of their caption. Then one block per page:

```text
===== PDF page 88: printed page 76 (arabic) =====
===== PDF page 25: printed page 13 (arabic, inferred) =====
===== PDF page 1: no printed page number =====
```

- **printed**: a line of its own among the first and last two lines of the page (`76`, `vii`, `- 76 -`, `Page 76 of 120`, `第 76 页`). When several lines qualify, the one that continues the previous page's run wins.
- **inferred**: the page shows no number (a chapter opening, a blank page) or one that breaks the run, and lies between two pages of the same run; it gets the number between them.
- **PDF page number**: no page shows a number at all, so pages are cited by their PDF page number.
- A text file is split at lines `[[page N]]` (N is the PDF page) or at form feeds; a text with neither has no pages (`paged: no`), and page anchors are then `not_checked`.

Check the runs against the PDF once. A caption is a line that starts with the label and goes on with a title ("Table 4.3 Regression results", "表4-3 样本的描述统计"); a sentence that mentions the table, and a line of a list of tables, are not captions.

## claims.json (you write it; the user confirms it)

```json
{"chapters": [{"id": "3", "title": "Method", "first_page": "33", "last_page": "57"}],
 "claims": [
   {"id": "C1", "kind": "claim", "quote": "Hypotheses H1 and H2 were supported", "page": "iii"},
   {"id": "H3", "kind": "hypothesis", "label": "H3", "result": "not_supported",
    "quote": "H3 was not supported (beta = 0.04, p = 0.61)", "page": "76"}]}
```

| Field | Content |
|---|---|
| `chapters` | Every chapter: `id`, `title`, `first_page` and `last_page` as printed. A question covers a chapter when it names it in `chapter` or an anchor falls in its pages |
| `claims[].id` | Unique; questions refer to it in `claims` |
| `kind` | `claim` (load-bearing, from the abstract or conclusions) or `hypothesis` (also a research question) |
| `quote`, `page` | Word for word from the thesis, with the printed page it is on; checked like an anchor |
| `label`, `result` | Hypotheses only: the label as the thesis writes it (H3, H2a, 假设3); `supported`, `partly_supported`, `not_supported` or `not_tested`, as the thesis states it |

## questions.json (you write it)

```json
{"questions": [
  {"id": "Q1", "category": "method", "hard": true, "chapter": "3", "claims": [],
   "question": "Why was the sampling frame limited to the membership register?",
   "source": {"type": "reviewer", "file": "reviews/report-1.txt", "ref": "Report 1, point 2",
              "quote": "The sampling frame excludes volunteers who are not registered members"},
   "follow_ups": [{"question": "How many helpers were not registered?", "follow_ups": [{"question": "…"}]}],
   "outline": {"opening": "…", "points": ["…"], "level": "bound",
               "anchors": [{"page": "33", "quote": "The sampling frame was the 2023 membership register of 14 clubs"}],
               "not_done": {"analysis": "…", "because": "…"}, "allow": ["0.71 | Smith et al. (2024), supplied by the user"]}}],
 "not_asked": {"application": "a theoretical thesis with no applied claim; agreed with the user"}}
```

| Field | Content |
|---|---|
| `id` | Unique: `Q1`, `Q2`, … |
| `category` | `opening`, `contribution`, `method`, `data`, `limitation`, `application` or `closing` |
| `question` | As an examiner would ask it |
| `source.type` | `reviewer` (needs `file` and the objection's `quote`; these questions come first), `audit` or `review` (`file`, `ref`), `thesis` (a signal at the anchors), `search` (`record` and `paper` with `title` or `doi` as the record gives it), `user` |
| `claims`, `chapter` | Optional links to claims.json |
| `hard`, `follow_ups` | Optional; a hard question needs follow-ups two levels deep |
| `outline` | [answer-outlines.md](answer-outlines.md) |
| `not_asked` | Optional: a category, chapter id or claim id that has no question, with the reason |

## check.md (written by `check`)

Rows grouped as `fail`, `manual`, `not_checked` and `pass`, each with where (`Q3 anchor 1`, `claim H3`, `coverage`), the check and the detail; then the numbers to know: each number of the outlines found in the thesis, with its printed page, PDF page and the sentence it is in. A number is `pass` on a cited page, `manual` when it is only elsewhere in the thesis, `fail` (`NOT_FOUND`) when it is nowhere and not allowed.

## session.jsonl (appended by `session`)

One JSON object per turn: `turn`, `time`, `question`, `asked` (the question's text), `answer` (as the student typed it), `verdict` (`solid`, `shaky`, `stuck`, `wrong`, `dodged`), `gap`, and `numbers` (each number of the answer with `in_thesis` and where, `allowed` and its source, or `not_in_thesis`). Never edit earlier lines; `revision-list.md` is rebuilt from all of them after every turn.
