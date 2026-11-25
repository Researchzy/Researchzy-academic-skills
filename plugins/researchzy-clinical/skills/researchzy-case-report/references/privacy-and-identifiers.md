# Privacy and identifiers

The skill keeps the patient's identifiers out of the report, and out of the conversation as far as it can. It cannot promise either: a script finds only what it is told to look for and what its patterns describe, and whatever the agent reads is sent to the model provider.

## Scan before reading

1. The clinician removes what they can from the notes before sharing them: names, numbers, dates, places.
2. The identifiers go into `case-report/private/identifiers.json`, written by you from what the clinician says, or by the clinician alone. If the clinician wrote it, do not open it.
3. `case_check.py scan` reads the notes and prints only a category and a position (file, line, column, length) for each hit. Give these to the clinician, who corrects the notes in their own editor and runs the scan again.
4. Read the notes only when the scan is clean, or when the clinician has judged every remaining hit.

This lowers the exposure; it does not remove it. Tell the clinician so, once and plainly.

## identifiers.json

The file must exist; every key in it is optional, and each list holds strings. The example is invented.

```json
{"names": ["Jana Novak", "Jana", "诺娃克"],
 "initials": ["J.N."],
 "record_numbers": ["4471203"],
 "test_numbers": ["RX-2025-00881"],
 "hospitals": ["Riverside General Hospital", "滨江总医院"],
 "towns": ["Lakeport"],
 "employers": ["Lakeport Ferry Company"],
 "dates": ["2025-03-14", "1933-05-02"],
 "other": ["MV Northern Light"],
 "age_threshold": 90}
```

| Key | What goes in it |
|---|---|
| `names` | Every form: full name, family name, given name, nickname, the name in another script, relatives named in the notes |
| `initials` | As the notes write them; full stops make no difference |
| `record_numbers`, `test_numbers` | Hospital, clinic and insurance numbers; accession, specimen, image and order numbers |
| `hospitals`, `towns`, `employers` | Where the patient was treated, lives or works, in every language the notes use |
| `dates` | Birth, admission, procedures, death: any date the notes give in full |
| `other` | Anything else that points at this patient: a ship, a team, a club, a local event |
| `age_threshold` | The age in whole years at or above which an age counts as identifying. It is the user's choice, a convention rather than a law: ask for it. Without it, ages are reported as not checked |

## How entries are matched

- Case and accents are ignored: "NOVÁK", "Novák" and "novak" are one entry.
- Separators inside numbers and codes are ignored, and full-width digits are read as digits: "447 1203", "447-1203", "４４７１２０３".
- Initials match with or without full stops and spaces: "J.N.", "J. N.", "JN".
- A name of several words is also matched by each capitalised part and by its initials, so "Jana Novak" finds "Mrs Novak's" and "J.N.".
- Chinese, Japanese and Korean entries match anywhere in running text, because those scripts put no spaces between words.
- A Latin entry needs a non-letter on each side, so "Lakeport" is not found inside "Lakeporter"; a Han character counts as a non-letter ("根据Novak的").
- Where two entries overlap, the longer one is reported: "Lakeport Ferry Company" as an employer, not "Lakeport" as a town.

## The patterns

These need no entry. A pattern hit fails `check`, just as an entry does.

| Category | Finds | Examples |
|---|---|---|
| `date` | Dates with a day and a month | 2025-03-14, 14/03/2025, 14 March 2025, March 14, 2025年3月14日, 3月14日, 2025년 3월 14일, EXIF 2025:03:14 |
| `age` | Ages at or above `age_threshold` | 92-year-old, aged 92, 92 years, 92岁, 九十二岁, 92歳, 92세, nonagenarian |
| `phone`, `email`, `url`, `ip` | Contact details and addresses | +44 20 …, name@host, https://…, 192.0.2.44 |
| `long_number` | Six or more digits in a row, unless a unit follows | 4471203, but not 150000/μL or 250000 IU |
| `code` | Letters together with five or more digits | AB123456, RX-2025-00881 |
| `titled_name` | A title before a capitalised word | Mrs Novak, Dr. Hale, 王女士 |
| `institution` | A name ending in an institution word | … General Hospital, University of …, …医院, …病院, …병원 |
| `location` | A GPS position in an image's metadata | |

The patterns use digit lookarounds instead of word boundaries, because there is no word boundary between two Han characters: "于2025年3月14日入院" and "病历号4471203" are found.

Not hits:

- DOIs and PMIDs; inside a reference list, anything but list entries.
- A date equal to the date of a logged search (`search_date`), and an exact date the timeline approves (`approved`, still listed).
- An age band: "aged 90 or over", "90 years or older", "90岁及以上".
- A phrase the clinician confirms identifies nobody, written on its own line in `case-report/not-identifiers.txt` (`#` starts a comment), such as a rating scale named after a hospital. The hit is kept as `exempt` and never listed.

## What no script sees

Quasi-identifiers: a rare job or role ("the only ferry captain on the island", 岛上唯一的渡轮船长), a small place, an unusual accident, a public event with a date, a family relationship, an unusual combination of facts. The scan and the check list "the only (or sole) … in, on or at the …" and "…唯一的…" as unique descriptions; everything else you find by reading. Ask the clinician about each one, then generalise it ("a seafarer") or leave it out.

## Images

- `check` reads each image's file name and metadata bytes (EXIF, XMP, PNG text): list entries, dates, GPS. It never looks at the pixels, so every image is listed as not checked.
- Look at every image with the user for faces and eyes, tattoos, birthmarks, jewellery, clothing, rooms and windows, and for labels burned into it: names, dates, record numbers, hospital names, rulers with text.
- Crop to the finding. An image that could identify the patient needs consent that covers images. A bar over the eyes does not stop a face from being recognised.
- Export images without their metadata and give them neutral names (`figure1.jpg`). For radiology, export an image file from the viewer without the DICOM header; the script does not read DICOM files.
- Captions and alt text follow the rules of the text.

## Never

- Never repeat an identifier value in a message, a file or a summary; point at the file, line and column.
- Never put `case-report/private/` or the signed consent form into anything that is shared or uploaded.
- Never call the report de-identified, anonymised, HIPAA-compliant or safe to publish. Say which checks ran and what was not checked.
