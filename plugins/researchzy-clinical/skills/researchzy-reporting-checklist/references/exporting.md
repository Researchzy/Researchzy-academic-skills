# Exporting and handing over

`export` runs the checks again and writes nothing while any row fails.

## The list to upload

`checklist-filled.md` and `checklist-filled.csv` hold one row per item, in the checklist's order: id, topic, status and where the item is reported, such as "p. 9, lines 112-118 (Results)" or "Supplement p. 2 (Table S2)"; "Not applicable" and "Not reported" for the others. The head of the .md names the checklist, its version and design, the file and the date it was read, the licence statement as printed, and the texts with the start of their hashes. Neither file carries the item wording.

Many journals want their own form, filled in. When the user has it as .docx and python-docx is installed, write the places into a copy; never into the user's file:

```python
import csv, json, re, shutil
import docx

def words(text):
    return " ".join(re.findall(r"\w+", text.casefold()))

base = "reporting-checklist"
items = json.load(open(f"{base}/checklist.json", encoding="utf-8"))["items"]
places = {r["item"]: r["where_reported"] for r in csv.DictReader(open(f"{base}/checklist-filled.csv", encoding="utf-8"))}
shutil.copyfile(f"{base}/source/FORM.docx", f"{base}/checklist-filled.docx")
form = docx.Document(f"{base}/checklist-filled.docx")
COLUMN = 3                       # the form's page column, counted from 0: look at the form first
for table in form.tables:
    for row in table.rows:
        text = words(" ".join(cell.text for cell in row.cells))
        ids = [i["id"] for i in items if words(i["text"])[:60] in text]
        if ids and len(row.cells) > COLUMN:
            row.cells[COLUMN].text = "; ".join(f"{i}: {places[i]}" if len(ids) > 1 else places[i] for i in ids)
form.save(f"{base}/checklist-filled.docx")
```

Then open the copy and compare it with `checklist-filled.md` row by row: every item has its place, in the right column, and no cell outside that column changed. Give the user the copy and say that it was written by a script and compared by eye.

## gaps.md

For the authors, not for upload: each partly reported and not reported item with what is missing and the suggestion; the items marked not applicable, with their reasons, so that the authors can confirm them; every placeholder; the entries no person has reviewed. Go through it with the user. When they add text to the manuscript, it changes: see below.

## When the manuscript changes

1. Make its text again from the new PDF, under the same name.
2. Run `check`. The `document` row fails because the hash changed.
3. Reread every item against the new text: an added paragraph can make a not reported item reported, and a moved one changes pages and lines. Correct the statuses and the places.
4. Record the new hash (`hash`) and run `check` until nothing fails, then `export`.

A new checklist file or a new version is a new registration: step 2 of the workflow, then every item again.

## Hand-over

In this order: the checklist, its version, design and the date it was read; the licence statement as printed; the list to upload (and the filled form, if any); `gaps.md` with each placeholder and the question it needs answered; every `not_checked` row of `check.md`; the entries no person has reviewed. The counts by status are a summary, not a score.
