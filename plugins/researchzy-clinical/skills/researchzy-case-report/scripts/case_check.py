#!/usr/bin/env python3
"""Keep the patient of a case report unidentifiable, and its timeline, consent and similar cases sourced.

  case_check.py scan notes/visit-notes.md notes/notes-zh.docx    before anyone reads the notes
  case_check.py check --notes notes/visit-notes.md [--final]     the draft and the files beside it

Both read the patient's own identifiers from case-report/private/identifiers.json (--ids) and report
each hit as a category, file, line, column and length, never its value; a file name holding one is
printed with that part replaced by asterisks.

scan   Text, Markdown, CSV, JSON, .docx and image files (name, metadata bytes), or folders. Also
       lists unique descriptions ("the only ferry captain on the island", 岛上唯一的…).
check  Identifiers in draft.md (or --draft, .md or .docx with its headers, notes, comments, their
       authors and the document properties), timeline.csv, captions.md and figures/ (names,
       metadata). timeline.csv: relative times never go backwards, each quote is in the notes, an
       exact date has approved_by. consent.json: the statement generated from it is in the draft;
       status unknown keeps the placeholder. similar-cases.json: each row is a paper of a saved
       result logged in searches.json, each filled cell's quote is in the saved abstract or full
       text, the count the draft states equals the rows. Wording leads (first, only, proves, caused,
       should, doses; 首例, 唯一, 证明, 导致, 应当, 剂量) are listed for review and never fail.

Identifiers come from the list (case, accents and digit separators ignored; initials with or without
full stops; Han, kana and Hangul inside running text) and from patterns with digit lookarounds, not \\b,
so that they work between Han characters (references/privacy-and-identifiers.md lists them). DOIs and
PMIDs are never hits, a reference list is searched for list entries only, and not-identifiers.txt
lists exempt phrases. Pixels are never looked at. Writes scan.md, or check.md and check.json.

Exit codes: 0 nothing found or failed; 1 (scan) an identifier found, (check) a check failed; 2 an
input cannot be read or is not in the format of the references. Standard library only.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import unicodedata
import zipfile
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree

sys.path.insert(0, str(Path(__file__).resolve().parent))
from quote_match import match_quality, tokens  # noqa: E402

LIST_KEYS = {"names": "name", "initials": "initials", "record_numbers": "record_number", "test_numbers": "test_number",
             "hospitals": "hospital", "towns": "town", "employers": "employer", "dates": "date", "other": "other"}
TEXT = {".md", ".markdown", ".txt", ".text", ".csv", ".tsv", ".json", ".html", ".htm", ".tex", ".xml", ".yaml", ".yml"}
IMAGES = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".gif", ".bmp", ".webp", ".heic"}
WORD = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
CJK = "぀-ヿ㐀-䶿一-鿿豈-﫿가-힣"
STATES = ("pass", "fail", "not_checked")
GRADES = ("ABSENT", "PARTIAL", "INTERLEAVED", "EXACT")
MIN_QUOTE_TOKENS = 3            # a Han character is one token: 停药后好转 is five
NOT_REPORTED = ("not reported", "未报告", "未報告")
CONSENT_PLACEHOLDER = "[Author input needed: consent for publication]"
PLACEHOLDER = re.compile(r"\[\s*(?:Evidence|Citation|Author input) needed\b[^\]]*\]", re.I)
ZH_DIGITS = dict(zip("零〇一二两三四五六七八九", (0, 0, 1, 2, 2, 3, 4, 5, 6, 7, 8, 9)))
NUMBER_WORDS = "one two three four five six seven eight nine ten eleven twelve".split()

MONTHS = "jan feb mar apr may jun jul aug sep oct nov dec".split()
MONTH = (r"(?P<mon>jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|(?-i:May|MAY)|june?|july?|aug(?:ust)?"
         r"|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)")
YEAR = r"(?P<y>(?:19|20)\d\d)"
DATES = (rf"(?<!\d){YEAR}[-/.:](?P<m>\d{{1,2}})[-/.:](?P<d>\d{{1,2}})(?!\d)",
         r"(?<!\d)(?:(?P<y>(?:19|20)?\d\d)\s*[年년]\s*)?(?P<m>\d{1,2})\s*[月월]\s*(?P<d>\d{1,2})\s*[日号號일]",
         r"(?<![\d./-])(?P<a>\d{1,2})[./-](?P<b>\d{1,2})[./-](?P<y>(?:19|20)?\d\d)(?![\d./-])",
         rf"(?<![a-z0-9])(?P<d>\d{{1,2}})(?:st|nd|rd|th)?[\s-]+(?:of\s+)?{MONTH}\.?(?:,?[\s-]+{YEAR})?(?![a-z])",
         rf"(?<![a-z0-9]){MONTH}\.?\s+(?P<d>\d{{1,2}})(?:st|nd|rd|th)?(?:,?\s+{YEAR})?(?![a-z0-9])")
AGES = (r"(?<!\d)(?P<n>\d{1,3})\s*-?\s*(?:years?|yrs?|y/o|y\.o\.|yo|y)(?:\s*-?\s*(?:old|of\s+age))?(?![a-z])",
        r"(?<![a-z])aged?\s*:?\s*(?P<n>\d{1,3})(?!\d)", r"(?<!\d)(?P<n>\d{1,3})\s*(?:周岁|岁|歲|歳|세|살)",
        r"(?:年龄|年齡|年齢|나이)\s*:?\s*(?P<n>\d{1,3})(?!\d)", r"(?P<z>[零〇一二两三四五六七八九十百]{1,6})\s*(?:周岁|岁|歲|歳)",
        r"(?P<w>nonagenarian|(?:super)?centenarian|九旬)")
BAND = r"(?!\s*(?:\+|(?:years?\s+)?(?:or|and)\s+(?:over|older|above|more)|(?:及|或)?以上))"   # "aged 90 or over" is a band
AGE_WORDS = {"nonagenarian": 90, "centenarian": 100, "supercentenarian": 110, "九旬": 90}
PHONES = (r"(?<![a-z0-9+])\+\d{1,3}[\s.-]?(?:\(\d{1,4}\)[\s.-]?)?\d{1,4}(?:[\s.-]?\d{2,4}){1,4}(?!\d)",
          r"(?<!\d)\(\d{2,5}\)\s?\d{3,4}[\s.-]?\d{3,4}(?!\d)", r"(?<![\d.-])\d{3,4}[.-]\d{3,4}[.-]\d{4}(?![\d.-])",
          r"(?:tel|phone|mobile|fax|电话|手机)\s*[:.]?\s*\+?\d[\d\s().-]{5,16}\d")
PATTERNS = [(c, v, re.compile(p, re.I if c == "date" else 0)) for c, v, p in (
    ("email", "low", r"[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}"),
    ("url", "low", r"(?:https?://|www\.)[^\s<>()\[\]{}\"'|，。；、）]+(?<![.,;:!?])"),
    ("ip", "low", r"(?<![\d.])(?:(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(?![\d.])"),
    *(("date", "base", p) for p in DATES), *(("phone", "low", p) for p in PHONES), *(("age", "low", p + BAND) for p in AGES),
    ("code", "base", r"(?<![A-Za-z0-9])[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*(?![A-Za-z0-9])"),
    ("long_number", "low", r"(?<!\d)\d{6,}(?!\d)"),
    ("titled_name", "base", r"(?<![A-Za-z])(?:Mr|Mrs|Ms|Miss|Mx|Dr|Prof|Mme|Mlle|Herr|Frau|Sr|Sra)\.?[ \t]+[A-Z][A-Za-z'’-]+"),
    ("titled_name", "base", r"(?![该此这那位名个一某其患者年的和与及由给对向])[一-鿿](?:先生|女士|小姐|太太|大爷|大妈|阿姨|奶奶|爷爷)"),
    ("institution", "base", r"(?<![A-Za-z])(?!(?:The|A|An|Our|This|That|Her|His|Their|Its|Each|Any|One|General)\s)(?:[A-Z]"
                            r"[A-Za-z'’.&-]*\s+){1,5}(?:Hospital|Clinic|Infirmary|University|Medical Cent(?:er|re))(?![A-Za-z])"),
    ("institution", "base", r"(?<![A-Za-z])(?:Hospital|Clinic|Infirmary|University)\s+(?:of|de|del|di)\s+[A-Z][A-Za-z'’-]*"),
    ("institution", "base", r"[一-鿿]{2,10}?(?P<inst>医院|醫院|病院|卫生院|衛生院|诊所|診所|医学院|醫學院|大学|大學)"),
    ("institution", "base", r"[가-힣]{2,10}\s?(?P<inst>병원|의원|대학교)"))]
DATE_RX = [rx for category, _, rx in PATTERNS if category == "date"]
GENERIC = ("患者", "病人", "入住", "就诊于", "就诊", "转至", "转入", "转往", "送往", "送至", "回到", "上级", "当地", "附近", "基层", "综合",
           "专科", "社区", "乡镇", "县级", "市级", "省级", "三甲", "二甲", "外院", "大学", "大學", "一家", "多家", "某", "该", "本", "我",
           "其", "在", "于", "到", "从", "由", "经", "被", "和", "与", "及", "的", "了", "曾", "已")
UNIT_AFTER = re.compile(r"\s*(?:iu|u|units?|mg|mcg|μg|ug|g|kg|ml|l|mmol|μmol|nmol|cells?|copies|cps|/\s*(?:l|ml|μl|ul|mm3|hpf))"
                        r"(?![a-z])")
UNIT_TOKEN = re.compile(r"\d+(?:iu|u|units?|mg|mcg|ug|g|kg|ml|l|mmol|cells|copies)", re.I)
MASK = re.compile(r"(?:https?://)?(?:dx\.)?doi\.org/\S+|(?<![\d.])10\.\d{4,9}/[^\s\])>,;，。]+"
                  r"|(?:pmid|pmcid)\s*:?\s*(?:pmc)?\d+|(?<![a-z])pmc\d{5,}", re.I)
REF_HEAD = re.compile(r"\s*(?:#{1,6}\s*)?[*_]{0,2}\s*(?:references|bibliography|literature cited|参考文献|參考文獻|参考資料"
                      r"|참고문헌)\s*[*_]{0,2}\s*[:：]?\s*", re.I)
LEADS = {lead: re.compile(p) for lead, p in (
    ("rarity", r"(?<![a-z])(?:first (?:reported |documented |known |published |described )?(?:case|report|description)|only "
               r"(?:(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten) )?(?:(?:reported|known|documented|published|other"
               r"|similar) )*(?:case|report)|never (?:been )?(?:previously )?(?:reported|described)|unique case|no (?:previous"
               r"|prior|earlier|other) (?:case|report))s?(?![a-z])|首例|首次报[道告]|唯一(?:一)?例|从未(?:有|被)?报[道告]|尚未(?:见|有)?报[道告]"
               r"|未见(?:类似|相关)?报[道告]|仅(?:有)?[\d一二两三四五六七八九十]+例"),
    ("proof", r"(?<![a-z])(?:prove[sdn]?|proving|this case (?:shows|demonstrates|confirms|establishes))(?![a-z])|证明|证实了"),
    ("cause", r"(?<![a-z])(?:caused|causes|causing|led to|induced|resulted in|attributable to)(?![a-z])|导致|引起|所致|诱发"),
    ("advice", r"(?<![a-z])(?:should(?: not|n't)?|must(?: not)?|ought to|(?:we|i) (?:recommend|suggest|advise)|(?:is|are) "
               r"(?:recommended|contraindicated))(?![a-z])|应当|应该|不应|不宜|必须|我们建议|建议|禁用|慎用"),
    ("dose", r"(?<![a-z0-9.])\d+(?:\.\d+)?\s*(?:mg|g|mcg|μg|ug|iu|units?|ml)(?:\s*/\s*(?:kg|day|d|m2))?(?![a-z0-9])|剂量"
             r"|(?:每日|每天|每次)\s*\d|\d+(?:\.\d+)?\s*(?:毫克|微克|克)"),
    ("unique_description", r"(?<![a-z])the (?:only|sole) (?!(?:reported |known |documented |published )?(?:case|report|patient)s?"
                           r"(?![a-z]))(?:[a-z-]+ ){1,3}?(?:in|on|at|of|for) (?:the|this|our|a|her|his|their)(?![a-z])"
                           r"|[一-鿿]{0,4}(?:唯一|仅有)的(?!病例|报道|报告|一例)"))}
SEARCH_MARK = re.compile(r"search|检索|table\s*s\d|表\s*s\d")
COUNT = re.compile(r"(?<![\w.])(?P<n>\d+|" + "|".join(NUMBER_WORDS) + r")\s+(?:(?:similar|relevant|published|other|additional"
                   r"|further|eligible|matching|related|comparable|previous|prior|case)\s+){0,3}(?:report|case|article|publication"
                   r"|paper)s?(?![a-z])|(?<!\d)(?P<z>\d+|[一二两三四五六七八九十]+)\s*(?:篇|例|份)")
SENTENCE = re.compile(r"(?:[^.!?。！？\n]|[.!?](?=\S))+")
OBTAINED = re.compile(r"consent[^.。]{0,80}(?:was|were|has been|had been|is) obtained|obtained[^.。]{0,40}consent"
                      r"|已获得[^。]{0,30}知情同意|知情同意[^。]{0,15}已获得")
FIGURE_MENTION = re.compile(r"(?<![a-z])fig(?:ure)?s?\.?\s*\d|图\s*\d")
TIME = re.compile(r"(?P<u>hour|day|week|month|year)s?\s*(?P<n>[+-]?\d+(?:\.\d+)?)(?:\s*(?:-|–|to)\s*\d+(?:\.\d+)?)?"
                  r"|第\s*(?P<zn>[+-]?\d+(?:\.\d+)?)\s*(?P<zu>小时|天|日|周|星期|个月|月|年)"
                  r"|(?P<bn>\d+(?:\.\d+)?)\s*(?P<bu>小时|天|日|周|星期|个月|月|年)前", re.I)
DAYS = {"hour": 1 / 24, "day": 1, "week": 7, "month": 30.4375, "year": 365.25, "小时": 1 / 24, "天": 1, "日": 1, "周": 7,
        "星期": 7, "个月": 30.4375, "月": 30.4375, "年": 365.25}
GIVERS = {"patient": ("the patient", "患者本人"), "parent_or_guardian": ("the patient's parent or guardian", "患者的父母或监护人"),
          "next_of_kin": ("the patient's next of kin", "患者的近亲属"), "legal_representative": ("the patient's legal representative",
                                                                                         "患者的法定代理人")}
FORMS = {"written": ("Written", "书面"), "electronic": ("Electronic", "电子"), "verbal_documented": ("Verbal", "口头")}
SCOPES = {"text": ("this case report", "本病例报告"), "images": ("images", "图片"), "video": ("video", "视频")}
NEEDS = {"obtained": ("given_by", "scope", "form", "source"), "waived": ("waived_by", "reason", "source"),
         "not_obtained": ("reason",), "unknown": ()}
SENTENCES = {"obtained": ("{form} informed consent for publication of {what} was obtained from {giver}{noted}.",
                          "已获得{giver}的{form}知情同意{noted}，同意发表{what}。"),
             "waived": ("The requirement to obtain consent for publication was waived by {by} ({reason}).",
                        "{by}豁免了发表本病例报告所需的知情同意（{reason}）。"),
             "not_obtained": ("Consent for publication was not obtained ({reason}).", "未获得发表本病例报告的知情同意（{reason}）。")}


def fail(message: str):
    print(f"case_check: {message}", file=sys.stderr)
    raise SystemExit(2)


def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:            # a UnicodeDecodeError is a ValueError
        fail(f"{path} cannot be read as JSON ({exc if isinstance(exc, json.JSONDecodeError) else type(exc).__name__}).")


def table(header: tuple, rows: list) -> list:
    cell = lambda value: " ".join(str(value).split()).replace("|", "/")  # noqa: E731
    return ["| " + " | ".join(h.capitalize() for h in header) + " |", "|" + "---|" * len(header),
            *("| " + " | ".join(cell(v) for v in row) + " |" for row in rows)] if rows else ["None."]


def tally(items: list, key: str) -> str:
    return ", ".join(f"{k} {n}" for k, n in Counter(item[key] for item in items).items())


def views(text: str) -> tuple:
    """(base, map, low, map): no accents or full-width forms; low in lower case; map[i] = index in text."""
    base, low, bmap, lmap = [], [], [], []
    for i, ch in enumerate(text):
        if ch <= "　" or "＀" <= ch <= "￯":
            ch = "".join(c for c in unicodedata.normalize("NFKD", ch) if not unicodedata.combining(c))
        base.append(ch)
        low.append(ch.casefold())
        bmap += [i] * len(ch)
        lmap += [i] * len(low[-1])
    return "".join(base), bmap + [len(text)], "".join(low), lmap + [len(text)]


def fold(text: str) -> str:
    return views(text)[2]


def zh_number(text: str) -> int:
    """九十二 is 92, 一百零三 is 103."""
    total = current = 0
    for ch in text:
        if ch in ZH_DIGITS:
            current = ZH_DIGITS[ch]
        else:
            total, current = total + (current or 1) * (10 if ch == "十" else 100), 0
    return total + current


def canon(match) -> set:
    """{(month, day, year % 100 or None)} of a date match: both readings of 03/04/2025."""
    g = {k: v for k, v in match.groupdict().items() if v}
    year = int(g["y"]) % 100 if "y" in g else None
    if "a" in g:
        pairs = ((int(g["a"]), int(g["b"])), (int(g["b"]), int(g["a"])))
    else:
        pairs = ((int(g["d"]), int(g["m"]) if "m" in g else MONTHS.index(g["mon"][:3].lower()) + 1),)
    return {(month, day, year) for day, month in pairs if 1 <= month <= 12 and 1 <= day <= 31}


def dates_in(text: str) -> set:
    base = views(text)[0]
    return {c for rx in DATE_RX for m in rx.finditer(base) for c in canon(m)}


def same_date(a: tuple, b: tuple) -> bool:
    return a[:2] == b[:2] and (None in (a[2], b[2]) or a[2] == b[2])


def list_matchers(ids: dict) -> list:
    """(category, view, regex) for each entry of identifiers.json, and the parts and initials of a name."""
    out = []

    def initials(letters):
        return r"(?<![A-Za-z])" + r"\.?\s?".join(map(re.escape, letters)) + r"\.?(?![A-Za-z])"

    for key, category in LIST_KEYS.items():
        for raw in ids.get(key) or []:
            value = " ".join(str(raw).split())
            low = fold(value)
            if len(low.replace(" ", "")) < 2:
                continue
            if re.search(f"[{CJK}]", value):
                out.append((category, "low", r"\s*".join(map(re.escape, low.replace(" ", "")))))
            elif category == "initials":
                out.append((category, "base", initials([c.upper() for c in views(value)[0] if c.isalpha()])))
            elif re.search(r"\d", low):
                compact = re.sub(r"[\s./_-]+", "", low)
                edges = (r"(?<!\d)", r"(?!\d)") if compact.isdigit() else (r"(?<![a-z0-9])", r"(?![a-z0-9])")
                out.append((category, "low", edges[0] + r"[\s./_-]?".join(map(re.escape, compact)) + edges[1]))
            else:
                out.append((category, "low", r"(?<![a-z0-9])" + r"[\s_-]+".join(map(re.escape, re.split(r"[\s_-]+", low)))
                            + r"(?![a-z0-9])"))
                parts = [w for w in re.split(r"[\s-]+", views(value)[0]) if len(w) > 1 and w[0].isupper()]
                if category == "name" and len(parts) > 1:
                    out += [("name", "base", rf"(?<![A-Za-z0-9])(?:{re.escape(p)}|{re.escape(p.upper())})(?![A-Za-z0-9])")
                            for p in parts] + [("initials", "base", initials([p[0] for p in parts]))]
    return [(category, view, re.compile(pattern)) for category, view, pattern in dict.fromkeys(out)]


def judge(category: str, m, ctx: dict) -> tuple:
    """(state, start) of a pattern match: state None when it identifies nobody, else hit, approved
    (an exact date the timeline approves) or search_date (the date of a logged search)."""
    g, text, start = m.groupdict(), m.group(0), m.start()
    if category == "date":
        found = canon(m)
        state = next((s for s, known in (("approved", ctx["approved"]), ("search_date", ctx["search_dates"]))
                      if any(same_date(a, b) for a in found for b in known)), "hit")
        return (state if found else None), start
    if category == "age":
        if ctx["threshold"] is None:
            return None, start
        years = int(g["n"]) if g.get("n") else zh_number(g["z"]) if g.get("z") else AGE_WORDS[g["w"]]
        return ("hit" if years >= ctx["threshold"] else None), start
    if category == "institution" and g.get("inst"):
        head = prefix = text[:-len(g["inst"])].rstrip()
        while (word := next((w for w in GENERIC if prefix.startswith(w)), None)):
            prefix = prefix[len(word):]
        return ("hit" if len(prefix) >= 2 else None), start + len(head) - len(prefix)
    digits = sum(c.isdigit() for c in text)
    keep = {"phone": digits >= 7, "long_number": not UNIT_AFTER.match(m.string, m.end()),
            "code": 5 <= digits < len(text.replace("-", "")) and not UNIT_TOKEN.fullmatch(text)}.get(category, True)
    return ("hit" if keep else None), start


def find(text: str, ctx: dict, refs: bool = False, kinds=None) -> list:
    """Identifier hits in one piece of text as {category, column, length, state}: list entries first,
    then the patterns (only `kinds` when given; none in a reference list); an overlap keeps the first."""
    base, bmap, low, lmap = views(text)
    taken, hits = [], []

    def take(category, vmap, begin, end, state):
        s, e = vmap[begin], vmap[end - 1] + 1
        if not any(s < b and a < e for a, b in taken):
            taken.append((s, e))
            hits.append({"category": category, "column": s + 1, "length": e - s, "state": state})

    found = [(m.span(), category, bmap if view == "base" else lmap) for category, view, rx in ctx["list"]
             for m in rx.finditer(base if view == "base" else low)]
    for (begin, end), category, vmap in sorted(found, key=lambda f: f[0][0] - f[0][1]):     # the longest entry first
        take(category, vmap, begin, end, "hit")
    if refs:
        return hits
    base, low = (MASK.sub(lambda m: " " * len(m.group(0)), view) for view in (base, low))
    exempt = [(lmap[m.start()], lmap[m.end() - 1] + 1) for rx in ctx["allow"] for m in rx.finditer(low)]
    for category, view, rx in PATTERNS:
        vmap = bmap if view == "base" else lmap
        for m in rx.finditer(base if view == "base" else low) if not kinds or category in kinds else ():
            state, begin = judge(category, m, ctx)
            if state:
                s, e = vmap[begin], vmap[m.end() - 1] + 1
                exempted = state == "hit" and any(a <= s and e <= b for a, b in exempt)
                take(category, vmap, begin, m.end(), "exempt" if exempted else state)
    return hits


def leads(text: str, ctx: dict, kinds) -> list:
    """Wording leads as {lead, column, length}. A rarity claim whose sentence carries the date of a
    logged search is bound to that search and is not listed."""
    (low, lmap), out = views(text)[2:], []
    for lead in kinds:
        for m in LEADS[lead].finditer(low):
            s, e = lmap[m.start()], lmap[m.end() - 1] + 1
            if lead == "rarity":
                begin = max(text.rfind(p, 0, s) for p in ".!?。！？\n") + 1
                end = min([i for i in (text.find(p, e) for p in ".!?。！？\n") if i >= 0], default=len(text))
                if any(same_date(a, b) for a in dates_in(text[begin:end]) for b in ctx["search_dates"]):
                    ctx["bound"] += 1
                    continue
            out.append({"lead": lead, "column": s + 1, "length": e - s})
    return out


def shown(path, ctx: dict) -> str:
    """A path as the reports print it: any identifier in it replaced by asterisks."""
    text = str(path)
    for h in find(text, ctx):
        if h["state"] == "hit":
            text = text[:h["column"] - 1] + "*" * h["length"] + text[h["column"] - 1 + h["length"]:]
    return text


def docx_units(path: Path) -> list:
    """(where, text): paragraphs, headers, footers, notes, comments, their authors, document properties."""
    out = []
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        for name in sorted(n for n in names if n.startswith("word/") and n.endswith(".xml")):
            root, part = ElementTree.fromstring(archive.read(name)), name[5:-4]
            label = "paragraph" if part == "document" else f"{part} paragraph"
            texts = ["".join(t.text or "" for t in p.iter(WORD + "t")) for p in root.iter(WORD + "p")]
            out += [(f"{label} {i}", text) for i, text in enumerate(texts, 1) if text.strip()]
            people = {v for el in root.iter() for k, v in el.attrib.items() if k in (WORD + "author", WORD + "initials")}
            out += [(f"{part} author", person) for person in sorted(people)]
        for name in ("docProps/core.xml", "docProps/app.xml", "docProps/custom.xml"):
            for el in ElementTree.fromstring(archive.read(name)).iter() if name in names else ():
                if len(el) == 0 and (el.text or "").strip() and el.tag.split("}")[-1] not in ("created", "modified", "lastPrinted"):
                    out.append((f"property {el.tag.split('}')[-1]}", el.text.strip()))     # not the file's own timestamps
    return out


def scan_file(path: Path, ctx: dict, name: str, lead_kinds=()) -> tuple:
    """(hits, leads, not checked, body) of a file: its name, its text, a .docx's or image's metadata."""
    hits = [dict(h, file=name, line="file name") for h in find(path.name, ctx)]     # folders are masked in `name`, not checked
    found, missed, body, suffix = [], [], "", path.suffix.lower()
    try:
        if suffix in TEXT or suffix == ".docx":
            pieces, refs = docx_units(path) if suffix == ".docx" else list(
                enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1)), False
            body = "\n".join(text for where, text in pieces if suffix != ".docx" or where.startswith("paragraph "))
            for where, text in pieces:
                refs = bool(REF_HEAD.fullmatch(text)) or (refs and not re.match(r"\s{0,3}#{1,6}\s", text))
                hits += [dict(h, file=name, line=where) for h in find(text, ctx, refs)]
                found += [dict(x, file=name, line=where) for x in leads(text, ctx, lead_kinds)]
        elif suffix in IMAGES:
            with path.open("rb") as handle:     # EXIF, XMP and PNG text sit near the start or the end
                data = handle.read(1 << 20)
                handle.seek(max(len(data), path.stat().st_size - (1 << 18)))
                data += handle.read()
            hits += [dict(h, file=name, line="metadata") for h in find(data.decode("latin-1"), ctx, kinds={"date"})]
            # XMP names its GPS fields; binary EXIF has the GPS directory's tag 0x8825 (type 4) in either byte order
            if re.search(rb"GPSLatitude|GPSLongitude", data) or re.search(rb"\x88\x25\x00\x04|\x25\x88\x04\x00", data[:65536]):
                hits.append(dict(category="location", file=name, line="metadata", column=0, length=0, state="hit"))
            missed.append(f"{name}: the picture itself was not looked at (faces, tattoos, jewellery, labels burned into it)")
        else:
            missed.append(f"{name}: a {suffix or 'file without an extension'} file is not read; only its name was checked")
    except (OSError, UnicodeDecodeError, zipfile.BadZipFile, ElementTree.ParseError, KeyError) as exc:
        missed.append(f"{name}: could not be read ({type(exc).__name__})")
    return hits, found, missed, body


def context(args) -> dict:
    path, allow = Path(args.ids or Path(args.dir) / "private" / "identifiers.json"), Path(args.dir) / "not-identifiers.txt"
    if not path.is_file():
        fail(f"no identifiers file at {path}. Write the patient's own identifiers there first (references/privacy-and-identifiers.md).")
    ids = read_json(path)
    ids = ids if isinstance(ids, dict) else {"(not an object)": None}
    threshold, unknown = ids.get("age_threshold"), sorted(set(ids) - set(LIST_KEYS) - {"age_threshold"})
    if unknown or any(not isinstance(ids.get(k, []), list) for k in LIST_KEYS) or not (
            threshold is None or type(threshold) is int and 0 < threshold < 150):
        fail(f"{path}: the keys are {', '.join(LIST_KEYS)}, each a list of strings, and age_threshold, a whole number of years.")
    allow = [a.strip() for a in allow.read_text(encoding="utf-8-sig").splitlines()] if allow.is_file() else []
    entries = ", ".join(f"{LIST_KEYS[k]} {len(ids[k])}" for k in LIST_KEYS if ids.get(k)) or "none"
    return {"list": list_matchers(ids), "threshold": threshold, "approved": set(), "search_dates": set(), "bound": 0,
            "allow": [re.compile(r"\s+".join(map(re.escape, fold(a).split()))) for a in allow if a and not a.startswith("#")],
            "missed": [] if threshold else ["ages: identifiers.json has no age_threshold"],
            "about": f"Identifiers from {path}: {entries}. Ages: " + (f"{threshold} years and over (the user's threshold)."
                                                                      if threshold else "not checked (no age_threshold).")}


def expand(names: list, ctx: dict) -> list:
    out = []
    for name in map(Path, names):
        if name.is_dir():
            out += sorted(p for p in name.rglob("*") if p.is_file() and not p.name.startswith("."))
        elif name.is_file():
            out.append(name)
        else:
            fail(f"no such file or folder: {shown(name, ctx)}")
    return out


def finish(path: Path, lines: list, result: dict, code: int) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if path.name == "check.md":
        path.with_suffix(".json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return code


def cmd_scan(args) -> int:
    ctx, hits, quasi = context(args), [], []
    files, missed, keep = expand(args.files, ctx), list(ctx["missed"]), ("category", "file", "line", "column", "length")
    for path in files:
        found, found_leads, unread, _ = scan_file(path, ctx, shown(path, ctx), ("unique_description",))
        hits, quasi, missed = hits + [h for h in found if h["state"] == "hit"], quasi + found_leads, missed + unread
    lines = ["# Identifier scan", "", "Internal working report: categories and positions, never values. Fix each hit in the "
             "file itself, in your own editor, and run the scan again.", "", ctx["about"], f"Files read: {len(files)}.", "",
             f"**{len(hits)} hit(s)**" + (f": {tally(hits, 'category')}." if hits else "."), "",
             *table(keep, [[h[k] for k in keep] for h in hits]), "", "## Unique descriptions (quasi-identifiers: ask the clinician)",
             "", *table(keep[1:], [[x[k] for k in keep[1:]] for x in quasi]), "", "## Not checked", "",
             *([f"- {x}" for x in missed] or ["Nothing."]), "", "A scan finds what the list and the patterns describe. Read the "
             "notes for what they cannot: a rare job, a small place, an unusual event, a relative's name."]
    return finish(Path(args.dir) / "scan.md", lines, {
        "ok": not hits, "hits": [{k: h[k] for k in keep} for h in hits], "counts": tally(hits, "category"),
        "quasi_identifiers": [{k: x[k] for k in keep[1:]} for x in quasi], "not_checked": missed,
        "report": str(Path(args.dir) / "scan.md")}, 1 if hits else 0)


def text_of(path: Path, ctx: dict) -> str:
    try:
        if path.suffix.lower() == ".docx":
            return "\n".join(text for where, text in docx_units(path) if where.startswith("paragraph "))
        return path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError, zipfile.BadZipFile, ElementTree.ParseError, KeyError) as exc:
        fail(f"{shown(path, ctx)} cannot be read as text or .docx ({type(exc).__name__}).")


def check_timeline(d: Path, notes: list, ctx: dict, add) -> None:
    path = d / "timeline.csv"
    if not path.is_file():
        return add("timeline", "timeline.csv", "not_checked", "No timeline.csv.")
    lines = text_of(path, ctx).splitlines()
    reader = csv.DictReader(lines, delimiter=max(",;\t", key=(lines[0] if lines else "").count))
    columns = {name: (name or "").strip().lower() for name in reader.fieldnames or []}
    missing = [c for c in ("time", "event", "where", "quote") if c not in columns.values()]
    if missing:
        fail(f"{path} lacks the column(s) {', '.join(missing)} (references/timeline-and-writing.md).")
    times, order, quotes, dates, approved, previous = [], [], [], [], 0, None
    for raw in reader:
        row, n = {columns[k]: (v or "").strip() for k, v in raw.items() if k in columns}, reader.line_num
        m = TIME.fullmatch(" ".join(views(row["time"])[0].split()))
        days = None if not m else float(m["n"]) * DAYS[m["u"].lower()] if m["u"] else float(m["zn"]) * DAYS[m["zu"]] \
            if m["zu"] else -float(m["bn"]) * DAYS[m["bu"]]
        if days is None:
            times.append(f"line {n}: not a relative time (Day 0, Week 6, 第6周, 3天前)")
        elif previous and days < previous[0]:
            order.append(f"line {n} ({row['time']}) comes after line {previous[1]} ({previous[2]})")
        previous = (days, n, row["time"]) if days is not None else previous
        if not row["where"] or len(tokens(row["quote"])) < MIN_QUOTE_TOKENS:
            quotes.append(f"line {n}: " + ("no location in the notes" if not row["where"] else "no quote of 3 words or more"))
        elif notes:
            grade = max((match_quality(row["quote"], text)["grade"] for text in notes), key=GRADES.index)
            quotes += [f"line {n}: not found in the notes ({grade})"] if grade in GRADES[:2] else []
        if row.get("exact_date"):
            found = dates_in(row["exact_date"])
            if found and row.get("approved_by"):
                ctx["approved"] |= found
                approved += 1
            else:
                dates.append(f"line {n}: " + ("an exact date that no one approved (approved_by is empty)" if found else
                                              "exact_date is not a date this script can read"))
    for check, problems, ok in (("timeline_times", times, "Every row has a relative time."),
                                ("timeline_order", order, "The relative times never go backwards."),
                                ("timeline_quotes", quotes, notes and "Every row's quote was found in the notes."),
                                ("exact_dates", dates, f"{approved} approved exact date(s); every other time is relative.")):
        add(check, "timeline.csv", "fail" if problems else "pass" if ok else "not_checked",
            "; ".join(problems) + "." if problems else ok or "No notes given (--notes): the quotes were not looked for.")


def papers_in(node) -> list:
    """The paper objects of a saved search result, whatever wraps them."""
    if isinstance(node, list):
        return [p for item in node for p in papers_in(item)]
    if not isinstance(node, dict):
        return []
    return [node] if node.get("title") or node.get("corpusId") else [p for v in node.values() for p in papers_in(v)]


def check_searches(d: Path, ctx: dict, add) -> dict:
    path, results, problems = d / "searches.json", {}, []
    data = read_json(path) if path.is_file() else {"searches": []}
    entries = data.get("searches") if isinstance(data, dict) else data
    if not isinstance(entries, list) or not all(isinstance(e, dict) for e in entries):
        fail(f"{path} must hold a list \"searches\" of objects (references/similar-cases.md).")
    for entry in entries:
        sid = str(entry.get("id") or "").strip() or "(no id)"
        missing = [k for k in ("id", "query", "date", "total", "file") if entry.get(k) in (None, "")]
        if missing or sid in results or type(entry["total"]) is not int or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(entry["date"])):
            problems.append(f"{sid}: " + (f"{', '.join(missing)} missing" if missing else "the id is used twice" if sid in results
                                          else "total must be the number the search returned, date YYYY-MM-DD"))
            continue
        try:
            saved = json.loads((d / str(entry["file"])).read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            problems.append(f"{sid}: its saved result cannot be read as JSON")
            continue
        total = saved.get("total") if isinstance(saved, dict) else None
        if type(total) is int and total != entry["total"]:
            problems.append(f"{sid}: total {entry['total']} in the log, {total} in the saved result")
        results[sid] = papers_in(saved)
        ctx["search_dates"] |= dates_in(str(entry["date"]))
    add("searches", "searches.json", "fail" if problems else "pass" if results else "not_checked", "; ".join(problems) + "."
        if problems else f"{len(results)} logged search(es), each with its saved result." if results else "No search was logged.")
    return results


def check_similar(d: Path, results: dict, draft, add) -> None:
    path = d / "similar-cases.json"
    if not path.is_file():
        return add("similar_cases", "similar-cases.json", "not_checked",
                   "No table of similar cases: the draft carries [Evidence needed: …] in its place.")
    data = read_json(path)
    columns, rows = (data.get("columns"), data.get("rows")) if isinstance(data, dict) else (None, None)
    if not (isinstance(columns, list) and columns and all(isinstance(c, str) for c in columns)
            and isinstance(rows, list) and all(isinstance(r, dict) for r in rows)):
        fail(f"{path} needs \"columns\", a list of names, and \"rows\", a list of objects (references/similar-cases.md).")
    doi = lambda v: re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", str(v or "").strip(), flags=re.I).lower()  # noqa: E731
    title = lambda v: "".join(re.findall(r"\w+", fold(str(v or ""))))  # noqa: E731
    origin, cells = [], []
    for i, row in enumerate(rows, 1):
        rid, papers = str(row.get("id") or f"row {i}"), results.get(str(row.get("search") or ""))
        paper = next((p for p in papers or [] if doi(row.get("doi")) and doi(p.get("doi")) == doi(row.get("doi"))
                      or title(row.get("title")) and title(p.get("title")) == title(row.get("title"))), None)
        source = d / str(row["source"]) if row.get("source") else None
        if paper is None or source and not source.is_file():
            origin.append(f"{rid}: " + ("its search is not a logged search with a saved result" if papers is None else
                                        f"not among the papers of the saved result of {row['search']}" if paper is None
                                        else "its source file is missing"))
            continue
        text = source.read_text(encoding="utf-8-sig", errors="replace") if source else " ".join(
            str(paper.get(k) or "") for k in ("title", "abstract", "abstractText"))
        for column in columns:
            cell, where = (row["cells"] if isinstance(row.get("cells"), dict) else {}).get(column), f"{rid} / {column}"
            if isinstance(cell, str) and fold(cell.strip()) in NOT_REPORTED:
                continue
            if not isinstance(cell, dict) or not str(cell.get("value") or "").strip():
                cells.append(f"{where}: no value (write \"not reported\" when the source does not give it)" if cell is None
                             else f"{where}: a filled cell is {{\"value\", \"quote\"}}")
                continue
            quote, low = str(cell.get("quote") or ""), fold(str(cell.get("quote") or ""))   # numbers also as words: six, 六
            grade = "missing" if not quote else "too short" if len(tokens(quote)) < MIN_QUOTE_TOKENS else \
                match_quality(quote, text)["grade"]
            quoted = set(re.findall(r"\d+(?:\.\d+)?", low)) | {str(zh_number(z)) for z in re.findall("[零〇一二两三四五六七八九十百]+", low)}
            quoted |= {str(k) for k, w in enumerate(NUMBER_WORDS, 1) if re.search(rf"(?<![a-z]){w}(?![a-z])", low)}
            if grade not in GRADES[2:]:
                cells.append(f"{where}: the quote is " + (f"not in the source ({grade})" if grade in GRADES else grade))
            elif not set(re.findall(r"\d+(?:\.\d+)?", fold(str(cell["value"])))) <= quoted:
                cells.append(f"{where}: a number of the value is not in its quote")
    for check, problems, ok in (("similar_case_rows", origin, f"All {len(rows)} rows are papers of a logged search's saved result."),
                                ("similar_case_cells", cells, "Every filled cell's quote is in its source, with the value's numbers.")):
        add(check, "similar-cases.json", "fail" if problems else "pass", "; ".join(problems[:12]) + (
            f"; and {len(problems) - 12} more." if len(problems) > 12 else ".") if problems else ok)
    claims, low = [], fold(draft or "")
    for sentence in (s for s in SENTENCE.finditer(low) if SEARCH_MARK.search(s.group(0))):
        for m in COUNT.finditer(sentence.group(0)):
            raw = m["n"] or m["z"]
            count = int(raw) if raw.isdigit() else NUMBER_WORDS.index(raw) + 1 if raw in NUMBER_WORDS else zh_number(raw)
            claims.append((low[:sentence.start()].count("\n") + 1, count))
    wrong = [f"line {line} says {n}" for line, n in claims if n != len(rows)]
    add("similar_case_count", "draft", "not_checked" if not claims else "fail" if wrong else "pass",
        f"The table has {len(rows)} rows; " + "; ".join(wrong) + "." if wrong else f"The draft's count equals the {len(rows)} rows."
        if claims else "No sentence of the draft names the search and states how many reports it found.")


def consent_sentence(record: dict) -> tuple:
    """(statement, problems): the consent statement built from the fields of consent.json, never a stock text."""
    status, scope, k = record.get("status"), record.get("scope"), int(record.get("language", "en") == "zh")
    if status not in NEEDS:
        return None, [f"status must be one of {', '.join(NEEDS)}"]
    problems = [f"{key} is missing" for key in NEEDS[status] if not record.get(key)]
    problems += ['language must be "en" or "zh"'] if record.get("language", "en") not in ("en", "zh") else []
    if status == "obtained" and not problems:
        problems += [f"given_by must be one of {', '.join(GIVERS)}"] if record["given_by"] not in GIVERS else []
        problems += [f"form must be one of {', '.join(FORMS)}"] if record["form"] not in FORMS else []
        problems += ["scope must be a list of text, images, video"] if not isinstance(scope, list) or set(scope) - set(SCOPES) else []
    if problems or status == "unknown":
        return (None if problems else CONSENT_PLACEHOLDER), problems
    fields = {"reason": str(record.get("reason") or "").strip(), "by": str(record.get("waived_by") or "").strip()}
    if status == "obtained":
        media = [SCOPES[s][k] for s in ("images", "video") if s in scope]
        parts = ([SCOPES["text"][k]] if "text" in scope else []) + ([("the accompanying ", "所附")[k] + (" and ", "和")[k].join(media)]
                                                                     if media else [])
        relation = str(record.get("relationship") or "").strip() if record["given_by"] != "patient" else ""
        fields |= {"what": (" and ", "及")[k].join(parts), "form": FORMS[record["form"]][k],
                   "giver": (f"the patient's {relation}", f"患者的{relation}")[k] if relation else GIVERS[record["given_by"]][k],
                   "noted": (" and recorded in the medical record", "（已记录于病历）")[k] if record["form"] == "verbal_documented" else ""}
    return SENTENCES[status][k].format(**fields), []


def check_consent(d: Path, draft, figures: bool, final: bool, ctx: dict, add) -> str:
    path = d / "consent.json"
    record = read_json(path) if path.is_file() else {"status": "unknown"}
    record = record if isinstance(record, dict) else {}
    sentence, problems = consent_sentence(record)
    status, name = record.get("status"), "consent.json" if path.is_file() else "consent.json (missing)"
    if problems:
        add("consent_record", name, "fail", "; ".join(problems) + " (references/consent.md).")
        return "Not generated: consent.json is incomplete."
    add("consent_record", name, ("fail" if final else "not_checked") if status == "unknown" else "pass",
        f"Status {status}." + (" The draft keeps the placeholder; a --final run fails on it." if status == "unknown" else ""))
    if draft is None:
        add("consent_statement", "draft", "not_checked", "No draft.")
    elif status != "obtained" and OBTAINED.search(fold(draft)):
        add("consent_statement", "draft", "fail", f"The draft says that consent was obtained; consent.json says {status}.")
    else:
        found = match_quality(sentence, draft)["grade"] == "EXACT"
        add("consent_statement", "draft", "pass" if found else "fail", "The draft carries the statement generated from "
            "consent.json." if found else "The draft does not carry the statement generated from consent.json (in check.md).")
    if status == "obtained" and "images" not in record["scope"] and (figures or FIGURE_MENTION.search(fold(draft or ""))):
        add("consent_scope", "consent.json", "fail", "The report has figures, but the scope of the consent does not include images.")
    if any(h["state"] == "hit" for h in find(sentence, ctx)):
        return "Withheld: the generated statement contains an identifier. Reword the free-text fields of consent.json."
    return sentence


def cmd_check(args) -> int:
    d, ctx, rows, later, hits, found = Path(args.dir), context(args), [], [], [], []
    add, missed = (lambda *row: rows.append(row)), list(ctx["missed"])  # noqa: E731
    check_timeline(d, [text_of(path, ctx) for path in expand(args.notes, ctx)], ctx, lambda *row: later.append(row))
    results = check_searches(d, ctx, lambda *row: later.append(row))   # first: approved and search dates are no hits
    draft_path, folder = Path(args.draft or d / "draft.md"), Path(args.figures or d / "figures")
    if draft_path.suffix.lower() not in (".md", ".markdown", ".txt", ".docx"):
        fail(f"{shown(draft_path, ctx)}: give the draft as .md, .txt or .docx.")
    images, draft = expand([folder], ctx) if folder.is_dir() else [], None
    missed += [] if folder.is_dir() else [f"{shown(folder, ctx)}: no such folder, so no image file was checked"]
    for path, role in [(draft_path, "draft"), (d / "timeline.csv", "timeline"), (d / "captions.md", "captions"),
                       *((p, "figure") for p in images)]:
        name = shown(path, ctx)
        if not path.is_file():
            add("identifiers", name, "not_checked", "Not found.") if role != "timeline" else None
            continue
        file_hits, file_leads, unread, body = scan_file(path, ctx, name, LEADS if role in ("draft", "captions") else ())
        draft, hits, found, missed = body if role == "draft" else draft, hits + file_hits, found + file_leads, missed + unread
        real, unread = [h for h in file_hits if h["state"] == "hit"], unread if role != "figure" else []
        add("identifiers", name, "fail" if real else "not_checked" if unread else "pass", f"{len(real)} hit(s): "
            f"{tally(real, 'category')}." if real else "; ".join(unread) if unread else "No identifier found.")
    rows += later
    consent = check_consent(d, draft, bool(images), args.final, ctx, add)
    check_similar(d, results, draft, add)
    open_items = [f"line {draft[:m.start()].count(chr(10)) + 1} ({m.group(0)[1:].split(' needed')[0].strip()})"
                  for m in PLACEHOLDER.finditer(draft or "")]
    add("placeholders", "draft", ("fail" if args.final else "not_checked") if open_items else "pass",
        f"{len(open_items)} open: {', '.join(open_items)}." if open_items else "No placeholder is left.")
    counts, keep = {state: sum(r[2] == state for r in rows) for state in STATES}, ("lead", "file", "line", "column", "length")
    shown_hits = [{k: h[k] for k in ("category", "file", "line", "column", "length", "state")} for h in hits
                  if h["state"] in ("hit", "approved")]
    lines = ["# Case report check", "", "Internal working report: categories and positions, never values. Do not upload it.", "",
             f"Run: {'final' if args.final else 'draft'}. {ctx['about']}", "",
             f"{len(rows)} checks: {counts['pass']} pass, {counts['fail']} fail, {counts['not_checked']} not checked.", "",
             *table(("Check", "Subject", "State", "Detail"), rows), "", "## Identifier hits", "",
             *table(("Category", "File", "Line", "Column", "Length", "State"), [h.values() for h in shown_hits]), "",
             f"## Leads for review (never a failure; {ctx['bound']} rarity claim(s) bound to a dated search)", "",
             *table(keep, [[x[k] for k in keep] for x in found]), "", "## Consent statement", "", consent, "",
             "## Not checked (never a pass)", "", *([f"- {x}" for x in missed] or ["None."])]
    return finish(d / "check.md", lines, {
        "ok": not counts["fail"], "final": args.final, "counts": counts, "failed": [f"{r[0]}: {r[1]}" for r in rows if r[2] == "fail"],
        "not_checked": [f"{r[0]}: {r[1]}" for r in rows if r[2] == "not_checked"] + missed, "hits": shown_hits,
        "leads": [{k: x[k] for k in keep} for x in found], "rarity_bound_to_a_search": ctx["bound"],
        "consent_statement": consent, "report": str(d / "check.md")}, 1 if counts["fail"] else 0)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Keep a case report's patient unidentifiable and its sources checkable.")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--dir", default="case-report", help="The case report folder (default: case-report)")
    common.add_argument("--ids", help="The identifiers file (default: <dir>/private/identifiers.json)")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("scan", parents=[common], help="Report identifiers in files by category and position only")
    p.add_argument("files", nargs="+", help="Files or folders: text, Markdown, CSV, JSON, .docx, images")
    p = sub.add_parser("check", parents=[common], help="Check the draft, timeline, captions, images, consent and similar cases")
    p.add_argument("--notes", nargs="*", default=[], help="The clinician's notes, in which the timeline's quotes must be found")
    p.add_argument("--draft", help="The draft, .md or .docx (default: <dir>/draft.md)")
    p.add_argument("--figures", help="The folder of image files (default: <dir>/figures)")
    p.add_argument("--final", action="store_true", help="Before submission: open placeholders and unknown consent fail")
    args = parser.parse_args(argv)
    return cmd_scan(args) if args.command == "scan" else cmd_check(args)


if __name__ == "__main__":
    sys.exit(main())
