#!/usr/bin/env python3
"""Compare a translation with its source, unit by unit, and write the bilingual table.

  tr_check.py check SOURCE TRANSLATION --pair zh-en [--glossary terms.tsv] [--strict] [--out translation]
  tr_check.py table SOURCE TRANSLATION --pair zh-en [--glossary terms.tsv] [--out translation]

Both files (.md, .tex, .txt, or the text of a .docx) are split as tr_units.py splits them and the
units are paired in order; a unit without a counterpart is listed as not compared.

Errors
  numbers       value, percent sign, a unit symbol after the number (5 mg, 37 °C) and a bound (<, ≥).
                Full-width digits and thousands separators are normalised, 万, 亿, thousand and million
                multiplied out, "37–40%" read as 37% to 40%
  dates         compared as dates: 2024年3月 = March 2024
  citations     \\cite keys, [@key], @key and numbered citations; [1–3] = [1, 2, 3]
  latex         LaTeX command names, \\ref and \\label keys, the balance of braces
  maths         formulas and code, byte for byte
  placeholders  [Evidence needed: …], [Citation needed: …], [Author input needed: …], by type
  links         URLs and DOIs
  figures       figure, table and equation numbers: 图2 = Figure 2, 附表1 = Table S1, 式(3) = Eq. (3)
Warnings
  numbers       a number written as a word; a minus sign, precision, unit or bound written differently
  glossary      a term without its translation, a keep-as-is term translated, one translation for two terms
  length        a length ratio under half or over twice the document's median
  negation      negations counted in each language (zh-en and en-zh only)
  hedges        hedges and approximations counted in each language (zh-en and en-zh only)
  script        Han characters or full-width punctuation in a Latin-script translation; five or more
                lowercase Latin words in a row in a Chinese, Japanese or Korean one
  commentary    words to the reader: "Here is the translation", "以下是译文"

check writes translation-check.md and .json, table writes bilingual.md, under --out. A check that
lacks its input is "not checked", never passed. Exit codes: 0; 1 with --strict when there is an
error; 2 for a missing or unreadable input or a bad --pair. Standard library only; imports
tr_units.py from its own folder.
"""

from __future__ import annotations

import argparse
import csv
import difflib
import json
import re
import statistics
import sys
from collections import Counter
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tr_units as tu  # noqa: E402

LATIN = frozenset("en de fr es it pt nl sv da no nb fi pl cs sk sl hr ro hu tr id ms vi ca et lv lt".split())
DECIMAL_COMMA = frozenset("de fr es it pt nl sv da no nb fi pl cs sk sl hr ro hu tr id ru uk ca et lv lt".split())
FULL_WIDTH = str.maketrans("０１２３４５６７８９％．＜＞＝～－＋", "0123456789%.<>=~-+")
UNITS = (r"°C|°F|℃|mmHg|mmol|μmol|µmol|nmol|kcal|kPa|MPa|kHz|MHz|GHz|mg|μg|µg|ng|kg|mL|ml|μL|µL|dL|dl|mm|cm"
         r"|km|nm|μm|µm|ms|min|hrs?|wk|mo|yr|Hz|kB|KB|MB|GB|TB|kJ|kW|mW|mV|mA|mM|μM|µM|nM|IU|bpm"
         r"|g|L|m|h|d|s|J|W|V|A|K|U|M")
UNIT_NAMES = {"ml": "mL", "℃": "°C", "hr": "h", "hrs": "h", "dl": "dL", "KB": "kB"}
RANGE_PERCENT = re.compile(r"(\d)(?=\s*(?:[-–—~～至到]|to)\s*\d+(?:[.,]\d+)?\s?%)")
MAGNITUDE = {"万": 10 ** 4, "亿": 10 ** 8, "万亿": 10 ** 12, "thousand": 10 ** 3, "million": 10 ** 6,
             "billion": 10 ** 9, "trillion": 10 ** 12}


def number_pattern(comma: bool) -> re.Pattern:
    """A number, CJK-aware: a Han character next to it is a boundary (共纳入37名), a Latin letter is
    not (H2O, 3D), and an uppercase name before a hyphen hides it (COVID-19, IL-6)."""
    dec, sep = (",", r"[.\u2009\u202f\u00a0]") if comma else (r"\.", r"[,\u2009\u202f\u00a0]")
    return re.compile(
        rf"(?<![A-Za-z0-9_.,])(?<![A-Z][-–])(?P<sign>[-−–](?=[\d{dec}]))?"
        rf"(?P<num>\d{{1,3}}(?:{sep}\d{{3}})+(?:{dec}\d+)?|\d+(?:{dec}\d+)?|{dec}\d+)"
        r"(?P<mag>\s*(?:万亿|万|亿|(?:thousand|million|billion|trillion)(?![A-Za-z])))?"
        r"(?P<pct>\s?(?:%|‰|percent(?![A-Za-z])|per cent(?![A-Za-z])))?"
        rf"(?P<unit>\s?(?:{UNITS})(?:/[A-Za-zμµ]+[23²³]?)*(?![A-Za-z0-9]))?(?:(?<=[%‰])|(?![A-Za-z0-9_]|[.,]\d))")


NUMBER = {False: number_pattern(False), True: number_pattern(True)}
EN_NUMBERS = {w: i for i, w in enumerate("zero one two three four five six seven eight nine ten eleven twelve thirteen "
                                         "fourteen fifteen sixteen seventeen eighteen nineteen twenty".split())}
EN_NUMBERS.update(thirty=30, forty=40, fifty=50, sixty=60, seventy=70, eighty=80, ninety=90, hundred=100, thousand=1000)
EN_WORD = re.compile(r"\b(" + "|".join(EN_NUMBERS) + r")(?:-(one|two|three|four|five|six|seven|eight|nine))?\b", re.I)
ZH_WORD = re.compile(r"[零〇一二两三四五六七八九十百千万亿]+")
ZH_DIGIT = dict(zip("零〇一二两三四五六七八九", (0, 0, 1, 2, 2, 3, 4, 5, 6, 7, 8, 9)))
MONTHS = {name: i for i, names in enumerate(("jan january", "feb february", "mar march", "apr april", "may",
                                             "jun june", "jul july", "aug august", "sep sept september",
                                             "oct october", "nov november", "dec december"), 1)
          for name in names.split()}
EN_DATE = re.compile(r"\b(?:(?P<d1>\d{1,2})(?:st|nd|rd|th)?\s+)?(?P<mon>Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?"
                     r"|Apr(?:il)?|May|June?|July?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?"
                     r"|Dec(?:ember)?)\b\.?(?:\s+(?P<d2>\d{1,2})(?:st|nd|rd|th)?\b)?(?:,?\s+(?P<y>\d{4})\b)?")
ZH_DATE = re.compile(r"(?:(?P<y>\d{4})\s*年\s*)?(?P<m>\d{1,2})\s*月(?:\s*(?P<d>\d{1,2})\s*[日号])?")
ISO_DATE = re.compile(r"(?<![\d.])(?P<y>\d{4})[-/](?P<m>\d{1,2})[-/](?P<d>\d{1,2})(?!\d|\.\d)")
FIG = r"S?\d+[A-Za-z]?"
ZH_FIG = re.compile(rf"(?P<sup>附|补充)?(?<![试意地企代发列量])(?P<kind>图|表)\s*(?P<nums>{FIG}(?:\s*(?:[-–—~～、,，和与及至]"
                    rf"|以及)\s*(?P=kind)?\s*{FIG})*)|(?P<eq>公式|方程|式)\s*[（(]\s*(?P<eqn>{FIG})\s*[)）]")
EN_FIG = re.compile(rf"(?P<sup>\b(?:Supplementary|Supplemental|Suppl\.)\s+)?\b(?P<kind>Fig(?:ure)?s?\.?|Tables?"
                    rf"|Tab\.|Eq(?:uation)?s?\.?)\s*~?\s*(?P<nums>\(?{FIG}\)?(?:\s*(?:[-–—,&]|and|to)\s*\(?{FIG}\)?)*)",
                    re.I)
FIG_ITEM = re.compile(rf"({FIG})(?:\s*(?:[-–—~～]|至|to)\s*({FIG}))?")
CITE_COMMAND = re.compile(r"\\[A-Za-z]*cite[A-Za-z]*\*?")
REF_COMMAND = re.compile(r"\\(ref|eqref|cref|Cref|autoref|pageref|nameref|label)\*?\s*\{([^{}]*)\}")
# Negations and hedges, aligned across Chinese and English. Chinese compounds that are no negation
# or hedge in English (不同 different, 非常 very, 无论 regardless, 是否 whether, 未来 future) are left out.
NEGATION = {"zh": re.compile(r"没有|并非|未(?!来|知)|不(?![同断仅少过论管良适久])|无(?!论|菌|创|症状|关|疑)"
                             r"|(?<!除)非(?!常|线性|参数|劣|随机|典型)|(?<![是与])否(?!则)|勿"),
            "en": re.compile(r"\b(?:not(?!\s+only)|no(?!\.\s*\d)|never|none|neither|nor|without|cannot|unable"
                             r"|unlikely|insufficient|absent|absence|lack(?:s|ed|ing)?|fail(?:s|ed)?\s+to)\b|n['’]t\b",
                             re.I)}
HEDGE = {"zh": re.compile(r"可能|或许|也许|似乎|大概|大约|约(?!束|定|翰)|左右(?![两侧手])|提示(?!词)|推测|倾向于|初步"
                          r"|潜在|一定程度上|有望"),
         "en": re.compile(r"\b(?:may|might|could|possib(?:le|ly|ility|ilities)|probabl[ey]|(?:un)?likely|perhaps"
                          r"|potential(?:ly)?|seem(?:s|ed)?|appear(?:s|ed)?|suggest(?:s|ed|ing)?|approximately"
                          r"|roughly|nearly|almost|(?:around|about)(?=\s+[\d.])|tend(?:s|ed)?\s+to"
                          r"|preliminar(?:y|ily)|presumabl[ey]|speculat\w*|to\s+some\s+extent|partly|partially)\b"
                          r"|~(?=\s*\d)|≈", re.I)}
CJK = re.compile(r"[\u3000-\u303f\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af\uff01-\uff60]")
LATIN_RUN = re.compile(r"[A-Za-z][A-Za-z'’-]*(?:[ \t,;:()]+[A-Za-z][A-Za-z'’-]*)*")
COMMENTARY = re.compile(r"\b(?:here(?:'s| is| are) (?:the|my|your) (?:translation|translated)|below is the "
                        r"translation|the translation (?:is|follows)|translation:|translated text:|i hope this helps"
                        r"|let me know if)|以下(?:是|为)(?:译文|翻译)|(?:译文|翻译)(?:如下|[:：])|希望(?:对您|对你)?有(?:所)?帮助",
                        re.I)
CHECKS = (("numbers", "Numbers"), ("dates", "Dates"), ("citations", "Citations"), ("latex", "LaTeX commands"),
          ("maths", "Formulas and code"), ("placeholders", "Placeholders"), ("links", "URLs and DOIs"),
          ("figures", "Figure, table and equation numbers"), ("glossary", "Glossary"), ("length", "Length"),
          ("negation", "Negation"), ("hedges", "Hedges"), ("script", "Script"), ("commentary", "Commentary"))
MULTISETS = (("dates", "dates"), ("citations", "cites"), ("latex", "commands"), ("latex", "refs"), ("maths", "maths"),
             ("placeholders", "placeholders"), ("links", "links"), ("figures", "figures"))


def zh_value(word: str) -> int:
    total = section = digit = 0
    for ch in word:
        if ch in ZH_DIGIT:
            digit = ZH_DIGIT[ch]
            continue
        unit = {"十": 10, "百": 100, "千": 1000, "万": 10 ** 4, "亿": 10 ** 8}[ch]
        if unit >= 10 ** 4:
            total, section = (total + section + digit) * unit, 0
        else:
            section += (digit or 1) * unit
        digit = 0
    return total + section + digit


def date_of(m: re.Match, chinese: bool) -> str | None:
    """"2024-03-15", "2024-03" or "?-03"; None for "may" the verb or an abbreviation standing alone."""
    month = int(m.group("m")) if chinese else MONTHS[m.group("mon").lower()]
    day, year = (m.group("d") if chinese else m.group("d1") or m.group("d2")), m.group("y")
    if not 1 <= month <= 12 or (day and not 1 <= int(day) <= 31) \
            or (not chinese and not (year or day) and (m.group("mon") == "May" or len(m.group("mon")) < 4)):
        return None
    return f"{year or '?'}-{month:02d}" + (f"-{int(day):02d}" if day else "")


def figures_of(m: re.Match) -> list[str]:
    if m.groupdict().get("eqn"):
        return ["equation " + m.group("eqn").casefold()]
    kind = {"图": "figure", "表": "table"}.get(m.group("kind")) \
        or {"f": "figure", "t": "table", "e": "equation"}[m.group("kind")[0].lower()]
    labels = [(a + "-" + b if b else a).casefold().replace("s", "S", 1) for a, b in FIG_ITEM.findall(m.group("nums"))]
    return [f"{kind} {label if label.startswith('S') or not m.group('sup') else 'S' + label}" for label in labels]


def blank(pattern: re.Pattern, text: str, convert, found: list) -> str:
    """The text with each match that `convert` turns into values blanked out; the values go to `found`."""
    def one(m: re.Match) -> str:
        values = convert(m)
        found.extend(values)
        return " " if values else m.group(0)
    return pattern.sub(one, text)


def facts(text: str, tex: bool, lang: str) -> dict:
    """What a unit holds that must survive translation, and its countable words."""
    masked, tokens, _ = tu.mask(text, tex)
    f: dict = {"cites": [], "commands": [], "refs": [], "maths": [], "links": [], "placeholders": [], "braces": 0}
    for raw in tokens.values():
        piece = raw if isinstance(raw, str) else raw[0]
        if isinstance(raw, list) and tu.PLACEHOLDER.match(piece):
            f["placeholders"].append(re.search(r"evidence|citation|author", piece, re.I).group(0).lower())
        elif piece.startswith(("$", "\\(", "\\[", "`")) or (env := re.match(r"\\begin\s*\{([^{}]*)\}", piece)) \
                and tu.WHOLE_ENV.fullmatch(env.group(1)):
            f["maths"].append(piece)
        elif not piece.startswith("%"):
            command = CITE_COMMAND.match(piece)
            groups = [g for g in tu.arguments(piece, command.end()) if piece[g[0]] == "{"] if command else []
            if groups:
                f["cites"] += [k.strip() for k in piece[groups[-1][0] + 1:groups[-1][1] - 1].split(",") if k.strip()]
            elif "@" in piece:
                f["cites"] += re.findall(r"@([A-Za-z0-9_](?:[A-Za-z0-9_:.+/-]*[A-Za-z0-9_])?)", piece)
            elif re.fullmatch(r"[\[［][\d\s,，、;–—-]+[\]］]", piece):
                for a, b in re.findall(r"(\d+)(?:\s*[-–—]\s*(\d+))?", piece):
                    f["cites"] += [str(k) for k in range(int(a), min(int(b or a), int(a) + 200) + 1)]
            f["commands"] += re.findall(r"\\([A-Za-z@]+)", piece)
            f["refs"] += REF_COMMAND.findall(piece)
            f["links"] += [u.rstrip(".,;:").lower() for u in tu.URL.findall(piece)]
    if tex:
        bare = re.sub(r"\\[{}%]|(?<!\\)%[^\n]*", "", text)
        f["braces"] = bare.count("{") - bare.count("}")
    prose = tu.TOKEN.sub(lambda m: "" if isinstance(tokens.get(m.group(2)), list) else " ", masked)
    plain, f["dates"], f["figures"], f["numbers"] = RANGE_PERCENT.sub(r"\1%", prose.translate(FULL_WIDTH)), [], [], []
    for pattern, chinese in ((ISO_DATE, True), (ZH_DATE, True), (EN_DATE, False)):
        plain = blank(pattern, plain, lambda m, c=chinese: [d for d in [date_of(m, c)] if d], f["dates"])
    for pattern in (ZH_FIG, EN_FIG):
        plain = blank(pattern, plain, figures_of, f["figures"])
    for m in NUMBER[lang in DECIMAL_COMMA].finditer(plain):
        before = plain[:m.start()].rstrip()
        sign = "-" if m.group("sign") and not (before and re.match(r"[0-9%)）]", before[-1])) else ""  # 18 –65
        digits = re.sub(r"[^\d.,]", "", m.group("num"))
        digits = digits.replace(".", "").replace(",", ".") if lang in DECIMAL_COMMA else digits.replace(",", "")
        digits = "0" + digits if digits.startswith(".") else digits
        magnitude = MAGNITUDE.get((m.group("mag") or "").strip().lower(), 1)
        value = Decimal(digits) * magnitude
        bound = re.search(r"([<>≤≥]=?)\s*$", plain[max(0, m.start() - 4):m.start()])
        unit = (m.group("unit") or "").strip().replace("µ", "μ")
        f["numbers"].append({"raw": m.group(0).strip(), "sign": sign, "abs": abs(value), "pct": bool(m.group("pct")),
                             "canon": format(value.normalize(), "f") if magnitude > 1 else digits,
                             "unit": UNIT_NAMES.get(unit, unit), "bound": bound.group(1) if bound else ""})
    f["words"] = {Decimal(zh_value(w)) for w in ZH_WORD.findall(plain)}
    f["words"] |= {Decimal(EN_NUMBERS[a.lower()] + EN_NUMBERS.get(b.lower(), 0)) for a, b in EN_WORD.findall(plain)}
    f["negation"] = NEGATION[lang].findall(plain) if lang in NEGATION else []
    f["hedges"] = HEDGE[lang].findall(plain) if lang in HEDGE else []
    f.update(prose=prose, length=len(re.sub(r"\s", "", prose)))
    return f


def number_difference(n: dict, m: dict):
    """(severity, reason) for two numbers of the same size, or None when only the translation names
    the unit (5毫克 → 5 mg)."""
    if n["pct"] != m["pct"]:
        return "error", "the percent sign is " + ("lost" if n["pct"] else "added")
    for field in ("unit", "bound"):
        if n[field] and m[field] and n[field] != m[field]:
            return "error", f"the {field} {n[field]} became {m[field]}"
    if n["sign"] != m["sign"]:
        return "warning", "the minus sign differs: check that the words say the direction"
    if n["canon"] != m["canon"]:
        return "warning", "written at another precision"
    if n["unit"] and not m["unit"]:
        return "warning", f"the unit {n['unit']} is not written as a symbol: check the unit word"
    if n["bound"] != m["bound"]:
        return "warning", "the bound is a symbol on one side only: check the words"
    return None


def compare_numbers(a: list, b: list, words_a: set, words_b: set) -> list:
    """[(severity, message)]: identical numbers first, then the same size written differently, then
    the numbers left on either side, which are errors unless the other side has them as a word."""
    key = ("sign", "canon", "pct", "unit", "bound")
    a, b, out = list(a), list(b), []
    for same in (lambda n, m: all(n[k] == m[k] for k in key), lambda n, m: n["abs"] == m["abs"]):
        for n in list(a):
            twin = next((m for m in b if same(n, m)), None)
            if twin:
                a.remove(n)
                b.remove(twin)
                why = number_difference(n, twin)
                out += [(why[0], f"{n['raw']} → {twin['raw']}: {why[1]}")] if why else []
    out += [("warning", f"{n['raw']} is written as a word in the translation") if n["abs"] in words_b
            else ("error", f"{n['raw']} is not in the translation") for n in a]
    out += [("warning", f"{m['raw']} is written as a word in the source") if m["abs"] in words_a
            else ("error", f"{m['raw']} is in the translation but not in the source") for m in b]
    return out


def gone_and_new(a: list, b: list) -> str:
    gone, new = sorted((Counter(a) - Counter(b)).elements()), sorted((Counter(b) - Counter(a)).elements())
    return "; ".join(part for part in (gone and "not in the translation: " + ", ".join(gone),
                                       new and "not in the source: " + ", ".join(new)) if part)


def has_term(text: str, term: str) -> bool:
    """A glossary term in a text: a Latin term as whole words (plural allowed, hyphen = space, case
    kept for acronyms); any other term as written."""
    if not re.fullmatch(r"[\x00-\x7f]*[A-Za-z][\x00-\x7f]*", term):
        return term.casefold() in text.casefold()
    word = re.escape(term).replace(r"\-", r"[-\s]+").replace(r"\ ", r"[-\s]+")
    word = word[:-1] + "(?:y|ie)" if term.endswith("y") else word
    return bool(re.search(rf"(?<![A-Za-z0-9]){word}(?:s|es)?(?![A-Za-z0-9])", text, 0 if term.isupper() else re.I))


def load_glossary(path: Path) -> tuple[list, list]:
    """Entries of a TSV with the columns term, translation, field, note; a note starting with "="
    keeps the term as it is; "|" separates accepted translations. Also the glossary's own problems."""
    if not path.is_file():
        tu.fail(f"No such file: {path}")
    rows = [r for r in csv.reader(path.read_text(encoding="utf-8-sig").splitlines(), delimiter="\t")
            if r and any(c.strip() for c in r) and not r[0].lstrip().startswith("#")]
    header = [c.strip().lower() for c in rows[0]] if rows else []
    if header[:2] != ["term", "translation"]:
        tu.fail(f"{path}: the first row must be the header term, translation, field, note (tab-separated)")
    entries, problems, seen = [], [], {}
    for line, row in enumerate(rows[1:], 2):
        row = dict(zip(header, (c.strip() for c in row)))
        if not row.get("term"):
            continue
        keep = row.get("note", "").startswith("=") or row.get("translation") == "="
        translations = [] if keep else [t.strip() for t in row.get("translation", "").split("|") if t.strip()]
        entries.append({"term": row["term"], "keep": keep, "field": row.get("field", ""), "translations": translations})
        problems += [] if keep or translations else [f"line {line}: {row['term']} has no translation and no ="]
        for t in translations:
            other = seen.setdefault(t.casefold(), row["term"])
            if other != row["term"]:
                problems.append(f"one translation for two terms: {other} and {row['term']} are both {t}")
    return entries, problems


def glossary_findings(source: str, translation: str, entries: list) -> list[str]:
    present: dict = {}
    for e in entries:
        if has_term(source, e["term"]):
            present.setdefault(e["term"], []).append(e)
    out = []
    for term, group in present.items():
        wanted = [t for e in group for t in e["translations"]]
        if any(e["keep"] for e in group) and not has_term(translation, term):
            out.append(f"{term} is marked keep-as-is (=) but is not in the translation")
        elif wanted and not any(has_term(translation, t) for t in wanted):
            other = next(((e["term"], t) for e in entries if e["term"] not in present for t in e["translations"]
                          if has_term(translation, t)), None)
            out.append(f"{term}: {' / '.join(wanted)} is not in the translation"
                       + (f"; it has {other[1]}, the glossary's translation of {other[0]}" if other else ""))
    return out


def pair_units(a: list, b: list) -> tuple[list, list, list]:
    """Pairs of unit indexes in order. When the files split differently, units are matched on type,
    citations, formulas and numbers; the ones left over are not compared."""
    if [u["type"] for u in a] == [u["type"] for u in b]:
        return list(zip(range(len(a)), range(len(b)))), [], []

    def signature(u: dict) -> tuple:
        return u["type"], *(tuple(sorted(map(str, u["f"][k]))) for k in ("cites", "maths")), \
            tuple(sorted(n["canon"] for n in u["f"]["numbers"]))
    pairs, alone_a, alone_b = [], [], []
    matcher = difflib.SequenceMatcher(None, [signature(u) for u in a], [signature(u) for u in b], autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal" or (tag == "replace" and i2 - i1 == j2 - j1
                              and all(a[i]["type"] == b[i - i1 + j1]["type"] for i in range(i1, i2))):
            pairs += zip(range(i1, i2), range(j1, j2))
        else:
            alone_a, alone_b = alone_a + list(range(i1, i2)), alone_b + list(range(j1, j2))
    return pairs, alone_a, alone_b


def compare(args) -> dict:
    match = re.fullmatch(r"([a-z]{2,3})-([a-z]{2,3})", args.pair or "")
    if not match:
        tu.fail("--pair takes two language codes, source first: zh-en, en-zh, ja-en …")
    src_lang, tgt_lang = match.groups()
    sides = []
    for path, lang in ((Path(args.source), src_lang), (Path(args.translation), tgt_lang)):
        text, tex = tu.read_source(path)
        sides.append([dict(u, text=text[u["start"]:u["end"]], f=facts(text[u["start"]:u["end"]], tex, lang))
                      for u in tu.units_of(text, tex)])
    a, b = sides
    entries, problems = load_glossary(Path(args.glossary)) if args.glossary else (None, [])
    pairs, alone_a, alone_b = pair_units(a, b)
    source_of = {j: a[i] for i, j in pairs}
    findings: list = [{"check": "glossary", "severity": "warning", "message": p, "unit": "", "line": "",
                       "translation_unit": "", "translation_line": "", "source": "", "translation": ""}
                      for p in problems]

    def add(check: str, severity: str, message: str, s: dict | None, t: dict) -> None:
        """A finding on a source unit and its translation, or on a translation unit without a source."""
        findings.append({"check": check, "severity": severity, "message": message, "unit": s["id"] if s else "",
                         "line": s["line"] if s else "", "translation_unit": t["id"], "translation_line": t["line"],
                         "source": s["text"] if s else "", "translation": t["text"]})

    zh_en, ratios = {src_lang, tgt_lang} == {"zh", "en"}, []
    for i, j in pairs:
        s, t = a[i], b[j]
        fs, ft = s["f"], t["f"]
        for severity, message in compare_numbers(fs["numbers"], ft["numbers"], fs["words"], ft["words"]):
            add("numbers", severity, message, s, t)
        for check, field in MULTISETS:
            if Counter(map(str, fs[field])) != Counter(map(str, ft[field])):
                add(check, "error", gone_and_new(list(map(str, fs[field])), list(map(str, ft[field]))), s, t)
        if fs["braces"] != ft["braces"]:
            add("latex", "error", f"unbalanced braces: {{ minus }} is {fs['braces']} in the source, "
                                  f"{ft['braces']} here", s, t)
        if s["type"] == "kept":
            continue
        for message in glossary_findings(fs["prose"], ft["prose"], entries or []):
            add("glossary", "warning", message, s, t)
        ratios += [(ft["length"] / fs["length"], s, t)] if fs["length"] >= 30 else []
        for check in ("negation", "hedges") if zh_en else ():
            if len(fs[check]) != len(ft[check]):
                add(check, "warning", f"{len(fs[check])} in the source ({', '.join(fs[check]) or 'none'}), "
                                      f"{len(ft[check])} in the translation ({', '.join(ft[check]) or 'none'})", s, t)
    median = statistics.median(r for r, _, _ in ratios) if len(ratios) >= 3 else None
    for ratio, s, t in ratios if median else ():
        if not median / 2 <= ratio <= median * 2:
            add("length", "warning", f"length ratio {ratio:.2f} against the document's median {median:.2f}: content "
                                     + ("may be missing" if ratio < median else "may have been added"), s, t)
    for j, t in enumerate(b):
        prose, s = t["f"]["prose"], source_of.get(j)
        if tgt_lang in LATIN and CJK.search(prose):
            add("script", "warning", "Han characters or full-width punctuation left: "
                + " ".join(dict.fromkeys(CJK.findall(prose)))[:60], s, t)
        if tgt_lang in ("zh", "ja", "ko") and t["type"] != "kept":
            for run in LATIN_RUN.findall(prose):
                words = [w for w in re.findall(r"[A-Za-z][A-Za-z'’-]*", run) if w[0].islower()]   # names pass
                if len(words) >= 5:
                    add("script", "warning", f"{len(words)} lowercase Latin words in a row: {run[:80]}", s, t)
        if t["type"] != "kept" and COMMENTARY.search(t["text"]):
            add("commentary", "warning", f"words to the reader: {COMMENTARY.search(t['text']).group(0)}", s, t)
    state = "checked" if pairs else "not_checked: no unit could be compared"
    states = {key: state for key, _ in CHECKS}
    states.update(glossary=state if entries is not None else "not_checked: no --glossary given",
                  length="checked" if median else "not_checked: fewer than 3 units of 30 or more characters",
                  script="checked" if tgt_lang in LATIN or tgt_lang in ("zh", "ja", "ko")
                  else f"not_checked: no rule for {tgt_lang}",
                  negation=state if zh_en else "not_checked: only for zh-en and en-zh", commentary="checked")
    states["hedges"] = states["negation"]
    order = [key for key, _ in CHECKS]
    findings.sort(key=lambda x: (x["severity"] != "error", order.index(x["check"])))
    return {"tool": tu.TOOL, "pair": args.pair, "source": str(args.source), "translation": str(args.translation),
            "units": {"source": len(a), "translation": len(b), "compared": len(pairs)},
            "not_compared": {side: [{"id": u[k]["id"], "line": u[k]["line"], "text": u[k]["text"]} for k in alone]
                             for side, u, alone in (("source", a, alone_a), ("translation", b, alone_b))},
            "checks": states, "findings": findings, "_pairs": pairs, "_units": (a, b)}


def cell(value, limit: int = 240) -> str:
    text = re.sub(r"\s+", " ", str(value if value is not None else "")).replace("|", "\\|")
    return text if len(text) <= limit else text[:limit - 1] + "…"


def write_check(result: dict, out: Path) -> dict:
    findings, units, lone = result["findings"], result["units"], result["not_compared"]
    errors = sum(f["severity"] == "error" for f in findings)
    lines = ["# Translation check", "", f"`{result['source']}` → `{result['translation']}` ({result['pair']}): "
             f"{units['source']} source units, {units['translation']} translation units, {units['compared']} compared; "
             f"{errors} errors, {len(findings) - errors} warnings.", "", "| Check | State | Errors | Warnings |",
             "|---|---|---|---|"]
    for key, title in CHECKS:
        counts = Counter(f["severity"] for f in findings if f["check"] == key)
        state = result["checks"][key].replace("_", " ")
        lines.append(f"| {title} | {state} | {counts['error']} | {counts['warning']} |")
    lines += ["", "An error has to be fixed. A warning has to be looked at: fix it, or write in notes.md why the "
              "translation is right. A check that is not checked says nothing about the translation."]
    for severity, title in (("error", "Errors"), ("warning", "Warnings")):
        mine = [f for f in findings if f["severity"] == severity]
        lines += ["", f"## {title} ({len(mine)})", "", "| Unit | Check | Finding | Source | Translation |",
                  "|---|---|---|---|---|"] if mine else []
        for f in mine:
            where = f"{f['unit']} (line {f['line']})" if f["unit"] else "terms.tsv" if not f["translation_unit"] \
                else f"translation {f['translation_unit']} (line {f['translation_line']})"
            lines.append(f"| {where} | {f['check']} | {cell(f['message'])} | {cell(f['source'], 160)} "
                         f"| {cell(f['translation'], 160)} |")
    for side in ("source", "translation"):
        lines += ["", f"## Units of the {side} not compared ({len(lone[side])})", "", "Read these yourself.", ""] + [
            f"- {u['id']} (line {u['line']}): {cell(u['text'], 160)}" for u in lone[side]] if lone[side] else []
    lines += ["", "Not checked by this script: whether the translation is right, complete inside a sentence and "
              "idiomatic, and any change of meaning that keeps the numbers, citations, terms and counted words."]
    out.mkdir(parents=True, exist_ok=True)
    (out / "translation-check.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (out / "translation-check.json").write_text(json.dumps({k: v for k, v in result.items() if not k.startswith("_")},
                                                           indent=1, ensure_ascii=False), encoding="utf-8")
    return {"errors": errors, "warnings": len(findings) - errors,
            "by_check": dict(Counter(f["check"] for f in findings)),
            "not_checked": {k: v.partition(": ")[2] for k, v in result["checks"].items() if v != "checked"},
            "units": units, "not_compared": {k: [u["id"] for u in v] for k, v in lone.items()},
            "report": str(out / "translation-check.md")}


def write_table(result: dict, out: Path) -> dict:
    issues: dict = {}
    for f in result["findings"]:                    # keyed by source unit, or by translation unit when alone
        issues.setdefault(f["unit"] or "t:" + f["translation_unit"], []).append(f"{f['severity']}: {f['message']}")
    (a, b), paired = result["_units"], dict(result["_pairs"])
    rows = [(s["id"], s["id"], s["text"], b[paired[i]]["text"] if i in paired else "(not compared)")
            for i, s in enumerate(a) if s["type"] != "kept" or s["id"] in issues]
    rows += [("—", "t:" + b[j]["id"], "(no source unit)", b[j]["text"]) for j in range(len(b))
             if j not in paired.values()]
    lines = ["# Bilingual table", "", f"`{result['source']}` → `{result['translation']}` ({result['pair']}). "
             "Issues are the findings of tr_check.py check; kept blocks (formulas, code, tables) appear only with "
             "an issue.", "", "| Unit | Source | Translation | Issues |", "|---|---|---|---|"]
    lines += [f"| {u} | {cell(s, 2000)} | {cell(t, 2000)} | {cell('; '.join(issues.get(key, [])), 600)} |"
              for u, key, s, t in rows]
    out.mkdir(parents=True, exist_ok=True)
    (out / "bilingual.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"rows": len(rows), "table": str(out / "bilingual.md")}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Compare a translation with its source, unit by unit.")
    sub = parser.add_subparsers(dest="command", required=True)
    for name, text in (("check", "Write translation-check.md and .json"), ("table", "Write bilingual.md")):
        p = sub.add_parser(name, help=text)
        p.add_argument("source", help="The source file: .md, .tex, .txt or .docx")
        p.add_argument("translation", help="The translated file")
        p.add_argument("--pair", required=True, help="Language codes, source first: zh-en, en-zh, ja-en …")
        p.add_argument("--glossary", help="TSV with the columns term, translation, field, note")
        p.add_argument("--out", default="translation", help="Output folder (default: translation)")
        if name == "check":
            p.add_argument("--strict", action="store_true", help="Exit 1 when there is an error")
    args = parser.parse_args(argv)
    result = compare(args)
    summary = write_check(result, Path(args.out)) if args.command == "check" else write_table(result, Path(args.out))
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 1 if args.command == "check" and args.strict and summary["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
