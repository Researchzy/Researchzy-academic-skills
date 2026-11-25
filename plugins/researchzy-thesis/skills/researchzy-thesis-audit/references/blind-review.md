# Blind review

Two scripts look at the blind copy. `check_anonymity.py` (the same file as in `researchzy-submission`) finds identity words. `thesis_audit.py blind` checks that the blind copy differs from the full copy only by what was removed. Neither changes a file.

## The identity list

Ask the user for these, in the same message that confirms `audit.json`. Never take a name, number or title from a web page or from memory. Write them into `thesis-audit/authors.json`, the format `check_anonymity.py` reads:

| Identity item | Field in `authors.json` |
|---|---|
| The author's name | `authors[0].name`; the name in the other script (pinyin, or the Chinese name) in `name_native` |
| Supervisors and co-supervisors | Further entries in `authors`, with `"role": "supervisor"` (the role is for people; the script ignores it) |
| School, college or department, laboratory | `affiliations` of each person, one item per unit: `"清华大学"`, `"经济管理学院"` |
| Email | `email` |
| Student number | `anonymity.other` |
| Grant numbers | `funding[].grant_number` |
| Ethics approval and registration ids | `ethics[].approval_id`, `registrations[].id` |
| The author's own publications | Their titles in `anonymity.other`; conferences where the work was shown in `anonymity.earlier_venues` |
| Project, survey, lab or user names | `anonymity.other`, `handles`, `repositories` |

```json
{
  "authors": [
    {"name": "张明远", "name_native": "Zhang Mingyuan", "role": "author", "email": "zmy@example.edu.cn",
     "affiliations": ["清华大学", "经济管理学院"]},
    {"name": "李国强", "name_native": "Li Guoqiang", "role": "supervisor", "affiliations": ["清华大学"]}
  ],
  "funding": [{"grant_number": "71872001"}],
  "anonymity": {"other": ["2021210345", "移动支付使用意愿的影响因素研究"], "earlier_venues": []}
}
```

The names, numbers and title above are invented.

- An identifier with Han characters is found anywhere in running text (本文在清华大学完成). A Latin identifier needs word boundaries, and a Han character next to it counts as one (学号2021210345).
- An affiliation part that is one Latin word (a city) is dropped as too common; a Chinese unit name is kept.
- A two-character Chinese name can occur inside other words. Every hit is shown with its text: look at each one before calling it a leak.

## What `check_anonymity.py` scans

Run it on `thesis-audit/blind/`, which holds only the copied blind files (`.docx`, `.pdf`, `.tex`, figures). It reads the body, headers and footers, footnotes and comments; tracked-change and comment authors; the creator, last-modified-by, company and manager properties; PDF properties and text through Poppler; text in image metadata; file names and home-folder paths. It flags acknowledgement and funding headings, 致谢, 基金资助 and 资助项目 included, and English self-citation phrasing ("our previous work"). It writes `thesis-audit/anonymity.md`; exit code 1 means a hit.

## What you look at by hand

- Chinese self-citation phrasing: 笔者前期研究, 本课题组, 我们此前的研究, 本人已发表.
- The cover page, the declaration pages (原创性声明, 授权使用说明), the acknowledgements, the list of the author's publications (攻读学位期间取得的研究成果) and the CV: whether each is removed, blanked or kept is the school's rule.
- Figures as pictures: logos, maps, photographs, questionnaire screenshots with a school name; scanned forms.
- Indirect identification: a named survey or panel only one group runs, a field site, 本校, 我院.
- The PDF that will be uploaded: run `check_anonymity.py` on it too, because a PDF built later can carry other properties.

Report each of these as `manual`, with what you saw and where.

## Comparing with the full copy

```sh
python3 "$SKILL_DIR/scripts/thesis_audit.py" blind --full thesis.docx --blind thesis-audit/blind/thesis-blind.docx
```

The two copies are split into sections, one per heading, and compared section by section:

| Row | Fails or needs a look when |
|---|---|
| numbers agree with the full copy | A section of the blind copy shows a number the full copy does not have there: results must not change between copies |
| headings agree with the full copy | A heading is missing from the blind copy or appears only there. Removed identity sections (致谢, declarations, publications, CV) are listed as a lead instead |
| numbers removed in the blind copy | `manual`: a number present only in the full copy. Confirm each one is an identifier (student number, grant number) and not a result |

Compare a source with a source: two `.docx` files, two main `.tex` files or two Markdown files. A PDF is refused (exit code 2), because its page numbers, running heads and line breaks would differ from the source; check a PDF with `check_anonymity.py` only.

## School rules

Which pages are dropped, whether self-citations are blinded or written in the third person, and whether the acknowledgements stay are the school's rules. Take them only from the school's file, quoted with page and date. When there is no file or it is silent, the rule is `not_stated`: report the hits and let the user decide.
