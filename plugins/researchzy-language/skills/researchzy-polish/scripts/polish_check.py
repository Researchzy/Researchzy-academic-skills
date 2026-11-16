#!/usr/bin/env python3
"""Check a language polish: the polished text must say what the original said, and the change log must
account for every edit.

  polish_check.py survey FILE [--protect terms.txt]
  polish_check.py diff BEFORE AFTER [--level light|medium|heavy] [--protect terms.txt] [--max-footprint 0.5]
  polish_check.py log BEFORE AFTER changes.json [--level light|medium|heavy]

Every command takes --out (default: polish). Files are .md, .tex, .txt or .docx (text only). Sentences are
aligned in order; a sentence may become two and two may become one, and a sentence that moved is found too.

survey  survey.md and .json: candidates for the protected-term list, the claim words of each sentence, and
        leads for author queries.
diff    polish-check.md and .json. Errors: a number (with its sign, inequality, percentage direction word, unit
        or number word) changed, added or gone, or values that traded places; a numeric, author-year, \\cite
        or [@key] citation dropped, added or moved to another sentence; \\ref and \\label keys, formulas or
        code changed or reordered; a protected term counted differently; a sentence moved up or down the claim
        ladder (may < suggest < associated < show < cause < prove), or a changed negation, quantifier, scope
        word, "significant", intensifier, approximation, modal verb, contrast or consequence link, direction
        of a comparison, article before a cause-like noun, or result tense from past to present; at light a
        split, merged, moved or uncompared sentence or a changed paragraph count, at medium a moved sentence,
        at heavy a sentence moved to another paragraph. Warnings: a dropped unit, a split or merged sentence
        with citations, a new capitalised term, a paragraph whose share of changed words is above the
        convention for the level (light 20%, medium 50%, heavy 70%), a changed paragraph count.
log     log-check.md and .json and redline.md, a word-level redline; for two .tex files also
        redline-latexdiff.tex when latexdiff is installed. Problems: an entry whose before text is not in
        BEFORE or after text not in AFTER, a reason off the list or not allowed at the level, a changed or
        moved sentence that no entry covers.

Exit codes: 0; 1 when diff finds an error or log a problem; 2 for a usage error or a file that is missing or
cannot be read. Standard library only. Portions are derived from MIT-licensed code: see LICENSE-MIT.txt next
to this file and THIRD_PARTY_NOTICES.md in the plugin.
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import re
import shutil
import subprocess
import sys
import zipfile
from collections import Counter
from decimal import Decimal
from pathlib import Path
from xml.etree import ElementTree

TOOL = "researchzy-polish"
SUFFIXES = (".md", ".markdown", ".tex", ".txt", ".docx")
LEVELS = ("light", "medium", "heavy")
FOOTPRINT = {"light": 0.2, "medium": 0.5, "heavy": 0.7}             # conventions, not measured limits
REASONS = ("spelling", "grammar", "article", "preposition", "agreement", "punctuation", "word choice", "terminology",
           "tense", "format", "concision", "clarity", "transition", "reorder")
ALLOWED = {"light": REASONS[:10], "medium": REASONS[:13], "heavy": REASONS}
# Alignment: the cost of a sentence left unpaired, the extra cost of a split or merge, the share of each part of a
# split or merge that the other side must contain, and the least similarity of two sentences paired out of order.
SKIP, SPLIT_COST, PART_INSIDE, MOVE_FLOOR = 0.4, 0.05, 0.5, 0.5
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

# --- Reading: what a language edit must leave alone becomes a placeholder, kept in order ----------------------

FROZEN = (re.compile(r"^(```|~~~).*?^\1[^\n]*$|\$\$.*?\$\$|\\\[.*?\\\]|\\begin\{(verbatim|lstlisting|minted|comment"
                     r"|equation|align|gather|multline|eqnarray|displaymath|math)(\*?)\}.*?\\end\{\2\3\}", re.S | re.M),
          re.compile(r"\\\(.*?\\\)|(?<![\\$])\$(?=\S)[^$\n]+?(?<=\S)(?<!\\)\$(?!\d)|`[^`\n]+`"))
KEY = re.compile(r"\\(label|ref|eqref|autoref|[cC]ref|pageref|nameref|[vV]ref|includegraphics|input|include|url|href)\*?"
                 r"(?:\s*\[[^\]]*\])?\s*\{([^{}]*)\}|(https?://[^\s)\]}>]*[^\s)\]}>.,;:])"
                 r"|\b(10\.\d{4,9}/[^\s)\]}>]*[^\s)\]}>.,;:])")
KEY_KIND = {"label": "label", "includegraphics": "file", "input": "file", "include": "file", "url": "url", "href": "url"}
TEX_CITE = re.compile(r"\\[A-Za-z]*cite[A-Za-z]*\*?\s*((?:\[[^\]]*\]\s*)*)\{([^{}]*)\}")
PANDOC_GROUP = re.compile(r"\[[^\[\]]*@[^\[\]]*\]")
PANDOC_KEY = re.compile(r"(?<![\w.@\\/])-?@([A-Za-z0-9_](?:[\w:.+/-]*\w)?)")
NUMERIC_CITE = re.compile(r"\[\d{1,4}(?:\s*[-–,]\s*\d{1,4})*\]")
CROSS_REF = ("fig:", "tbl:", "tab:", "eq:", "sec:", "lst:")
NAME = r"[A-Z][^\W\d_]*(?:[-'’][A-Z]?[^\W\d_]+)*"
YEARS = r"(?:1[6-9]|20)\d\d[a-z]?(?:\s*,\s*(?:1[6-9]|20)\d\d[a-z]?)*"
LOCATOR = r"(?:\s*,\s*(?:pp?\.|ch\.|chap\.)\s*[\w–-]+)?"
AY_NARRATIVE = re.compile(rf"\b({NAME})(?:\s+(?:and|&)\s+{NAME}|\s+et\s+al\.?)?\s+\(({YEARS}){LOCATOR}\)")
AY_PART = re.compile(rf"(?:(?:see|e\.g\.|cf\.|also|for example)[,:]?\s+)*({NAME})"
                     rf"(?:(?:,\s*|\s+(?:and|&)\s+|\s+)(?:{NAME}|et\s+al\.?))*,?\s+({YEARS}){LOCATOR}")
PARENS = re.compile(r"\(([^()]*\b(?:1[6-9]|20)\d\d[a-z]?\b[^()]*)\)")
NOT_NAMES = frozenset("In On At By For From Since Until Before After During Between Table Figure Fig Section Appendix "
                      "January February March April May June July August September October November December "
                      "Spring Summer Autumn Fall Winter".split())
PH = re.compile(r"⟦([CFK])(\d+)⟧")


def fail(message: str):
    print(f"polish_check: {message}", file=sys.stderr)
    raise SystemExit(2)


def docx_text(path: Path) -> str:
    """The paragraphs of a .docx, headings as "#". Text that a tracked change deleted is left out."""
    try:
        with zipfile.ZipFile(path) as zf:
            root = ElementTree.fromstring(zf.read("word/document.xml"))
    except (OSError, KeyError, zipfile.BadZipFile, ElementTree.ParseError):
        fail(f"{path}: not a readable .docx file")
    out = []
    for p in root.iter(W + "p"):
        text = "".join((n.text or "") if n.tag == W + "t" else " " if n.tag in (W + "tab", W + "br") else ""
                       for n in p.iter()).strip()
        style = p.find(f"{W}pPr/{W}pStyle")
        level = re.match(r"(?i)heading\s*(\d)", style.get(W + "val", "")) if style is not None else None
        out.append(("#" * int(level.group(1)) + " " if level and text else "") + text)
    return "\n\n".join(out)


def read_text(path: Path) -> str:
    if not path.is_file():
        fail(f"no such file: {path}")
    if path.suffix.lower() not in SUFFIXES:
        fail(f"{path}: give a .md, .tex, .txt or .docx file")
    return docx_text(path) if path.suffix.lower() == ".docx" else path.read_text(encoding="utf-8", errors="replace")


def mask(text: str, tex: bool) -> tuple[str, dict]:
    """Formulas and code (F), cross-references, labels, files and links (K) and citations (C) become
    placeholders; the store keeps each original and its value, in order."""
    store: dict = {"F": [], "K": [], "C": []}

    def put(kind: str, original: str, value) -> str:
        store[kind].append((original, value))
        return f"⟦{kind}{len(store[kind]) - 1}⟧"

    def key(m) -> str:
        value = (f"{KEY_KIND.get(m.group(1), 'ref')}:{m.group(2).strip()}" if m.group(1)
                 else f"url:{m.group(3)}" if m.group(3) else f"doi:{m.group(4)}")
        return put("K", m.group(0), value)

    def tex_cite(m) -> str:
        notes = re.findall(r"\[([^\]]*)\]", m.group(1))
        post = ", " + " ".join(notes[-1].replace("~", " ").split()) if notes and notes[-1].strip() else ""
        return put("C", m.group(0), [k.strip() + post for k in m.group(2).split(",") if k.strip()])

    def pandoc(m) -> str:
        found = [(k.group(1), " ".join(part[k.end():].split()).lstrip(", ")) for part in m.group(0)[1:-1].split(";")
                 for k in [re.search(r"-?@([A-Za-z0-9_](?:[\w:.+/-]*\w)?)", part)] if k]
        items = [key + (f", {note}" if note else "") for key, note in found if not key.lower().startswith(CROSS_REF)]
        if items:
            return put("C", m.group(0), items)
        return put("K", m.group(0), "ref:" + ";".join(k for k, _ in found)) if found else m.group(0)

    def bare(m) -> str:
        ref = m.group(1).lower().startswith(CROSS_REF)
        return put("K" if ref else "C", m.group(0), f"ref:{m.group(1)}" if ref else [m.group(1)])

    def numeric(m) -> str:
        items = []
        for part in m.group(0)[1:-1].split(","):
            ends = [int(x) for x in re.split(r"\s*[-–]\s*", part.strip())]
            items += [f"[{k}]" for k in range(ends[0], ends[-1] + 1)] if 0 < ends[-1] - ends[0] <= 100 else [f"[{ends[0]}]"]
        return put("C", m.group(0), items)

    def author_year(m) -> str:
        found = [m] if m.re is AY_NARRATIVE else [AY_PART.fullmatch(x.strip()) for x in m.group(1).split(";")]
        parts = [(p.group(1), p.group(2)) if p else (None, "") for p in found]
        if any(name is None or name in NOT_NAMES for name, _ in parts):
            return m.group(0)
        return put("C", m.group(0), [f"{name.lower()} {y}" for name, years in parts for y in re.split(r"\s*,\s*", years)])

    if tex:
        body = re.search(r"\\begin\{document\}(.*?)(?:\\end\{document\}|\Z)", text, re.S)
        text = re.sub(r"(?<!\\)%[^\n]*", "", body.group(1) if body else text)
    else:
        text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    for pattern in FROZEN:
        text = pattern.sub(lambda m: put("F", m.group(0), " ".join(m.group(0).split())), text)
    for pattern, handle in ((KEY, key), (TEX_CITE, tex_cite), (PANDOC_GROUP, pandoc), (PANDOC_KEY, bare),
                            (NUMERIC_CITE, numeric), (AY_NARRATIVE, author_year), (PARENS, author_year)):
        text = pattern.sub(handle, text)
    return text, store


def restore(masked: str, store: dict) -> str:
    return PH.sub(lambda m: store[m.group(1)][int(m.group(2))][0], masked)


def squash(text: str) -> str:
    return " ".join(text.split())


# --- Numbers: a value with its sign, inequality, percentage direction and unit ---------------------------------

SMALL = {w: i for i, w in enumerate("zero _ two three four five six seven eight nine ten eleven twelve thirteen "
                                    "fourteen fifteen sixteen seventeen eighteen nineteen".split()) if w != "_"}
TENS = dict(zip("twenty thirty forty fifty sixty seventy eighty ninety".split(), range(20, 100, 10)))
ONES = dict(zip("one two three four five six seven eight nine".split(), range(1, 10)))
SCALE = {"hundred": 100, "thousand": 1000, "million": 10 ** 6, "billion": 10 ** 9}
_TENS, _ONES, _SMALL, _SCALE = ("|".join(d) for d in (TENS, ONES, SMALL, SCALE))
NUMBER_WORD = re.compile(rf"\b(?:({_TENS})(?:-({_ONES}))?|({_SMALL}))(?:\s+({_SCALE}))?\b|(?<!\d )\b({_SCALE})\b", re.I)
FOLD_WORD = re.compile(rf"\b({_SMALL}|{_TENS})-?fold\b", re.I)
# An integer, a decimal or a percentage; thousands separators are dropped. A digit glued to a word (COVID-19,
# top-5, 3D) is a name, not a number, and a hyphen after a number joins a range.
NUMBER = re.compile(r"(?<![\w.,])(?<![A-Za-z][-–])(?P<cur>[$€£¥])?(?P<sign>[-−])?"
                    r"(?P<num>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?|\.\d+)"
                    rf"(?P<scale>\s+(?:{_SCALE})\b)?(?P<pct>\s?%|\s+per\s?cent\b|\s+percentage\s+points?\b)?(?![\w]|[.,]\d)")
INEQ_WORDS = {"<": "less than|fewer than|lower than|below|under", "≥": "at least|no less than|no fewer than",
              ">": "more than|greater than|higher than|above|over|exceeding", "≤": "at most|no more than|up to"}
INEQ = re.compile(r"(<=|>=|[≤≥⩽⩾]|(?<![-=<>])[<>])\s*$|\b(" + "|".join(INEQ_WORDS.values()) + r")\s+$", re.I)
INEQ_NORM = {"<=": "≤", ">=": "≥", "⩽": "≤", "⩾": "≥", **{w: s for s, ws in INEQ_WORDS.items() for w in ws.split("|")}}
# A relative change carries its direction in the word beside it: "24% lower" and "24% higher" share every digit.
# Synonyms share a polarity, so "lower by 24%" and "a 24% reduction" agree.
CHANGE_UP = r"increase[sd]?|increasing|rise[sn]?|rose|gain(?:ed|s)?"
CHANGE_DOWN = r"decrease[sd]?|decreasing|reduction|reduced|reduces?|decline[sd]?|drop(?:ped|s)?|fell|falls?"
UP, DOWN = rf"higher|greater|larger|more|above|{CHANGE_UP}", rf"lower|less|fewer|smaller|below|{CHANGE_DOWN}"
AFTER_DIR = re.compile(rf"\s*({UP}|{DOWN})\b", re.I)
BEFORE_DIR = re.compile(rf"\b(?:(?P<w>{CHANGE_UP}|{CHANGE_DOWN})\s+(?:by\s+|of\s+)?"
                        r"|(?P<c>higher|greater|larger|more|lower|less|fewer|smaller)\s+by\s+)$", re.I)
UNITS = ("mg; µg μg ug mcg; ng; pg; kg; g; mL ml; µL μL uL; dL dl; L; mmol; µmol μmol umol; nmol; mol; mM; µM μM uM; "
         "nM; M; km; cm; mm; µm μm um; nm; m² m2; m; mmHg; kPa; Pa; Hz; kHz; MHz; GHz; °C ºC; °F; K; V; mV; W; kW; J; "
         "kJ; kcal; cal; ms; s sec secs second seconds; min mins minute minutes; h hr hrs hour hours; d day days; "
         "wk wks week weeks; mo month months; yr y yrs year years; bpm; IU; U; ppm; ppb; dB; kB KB; MB; GB; TB; fold; "
         "times ×; points point")
UNIT_FORMS = {form: group.split()[0] for group in UNITS.split(";") for form in group.split()}
_UNIT = "|".join(re.escape(u) for u in sorted(UNIT_FORMS, key=len, reverse=True))
UNIT = re.compile(rf"[ \u00a0\u202f-]?((?:{_UNIT})(?:/(?:{_UNIT}))*)(?![\w°µμ])")
ALPHA = re.compile(r"[^\W\d_]+(?:['’-][^\W\d_]+)*")
WORD = re.compile(r"[^\W_]+(?:['’-][^\W_]+)*")


def words_to_digits(text: str) -> str:
    """Number words as digits: "twenty-five" is 25, "three hundred" 300, "twice" 2 times. "One" alone stays a
    word: it is a pronoun as often as a number."""
    def value(m) -> str:
        words = [(w or "").lower() for w in m.groups()]
        if words[4]:
            return str(SCALE[words[4]])
        base = TENS[words[0]] + ONES.get(words[1], 0) if words[0] else SMALL[words[2]]
        return str(base * SCALE.get(words[3], 1))
    text = FOLD_WORD.sub(lambda m: f"{SMALL.get(m.group(1).lower(), TENS.get(m.group(1).lower()))}-fold",
                         re.sub(r"\btwice\b", "2 times", text, flags=re.I))
    return NUMBER_WORD.sub(value, text)


def numbers_in(plain: str) -> tuple[list, list]:
    """(value, unit) of each number, and the text as a stream of ("N", value) and ("W", word)."""
    text = words_to_digits(plain)
    found, spans = [], []
    for m in NUMBER.finditer(text):
        digits = m.group("num").replace(",", "")
        digits = "0" + digits if digits.startswith(".") else digits
        start, sign = m.start("cur") if m.group("cur") else m.start("num"), ""
        if m.group("sign"):
            before = text[:m.start("sign")].rstrip()
            if not before or not (before[-1].isdigit() or before[-1] in "%)"):
                start, sign = min(start, m.start("sign")), "-"
        if m.group("scale"):
            digits = format(Decimal(digits) * SCALE[m.group("scale").strip().lower()], "f")
            digits = digits.rstrip("0").rstrip(".") if "." in digits else digits
        ineq = INEQ.search(text[max(0, start - 30):start])
        bound = " ".join((ineq.group(1) or ineq.group(2)).lower().split()) if ineq else ""
        value = INEQ_NORM.get(bound, bound) + sign + digits
        pct, unit, end = (m.group("pct") or "").strip().lower(), "", m.end()
        if pct:
            unit, value = ("pp", value) if "point" in pct else ("", value + "%")
            after, before = AFTER_DIR.match(text, m.end()), BEFORE_DIR.search(text[max(0, m.start() - 40):m.start()])
            word = after.group(1) if after else (before.group("w") or before.group("c")) if before else None
            value += (" (up)" if re.fullmatch(UP, word, re.I) else " (down)") if word else ""
        elif u := UNIT.match(text, m.end()):
            unit, end = "/".join(UNIT_FORMS[p] for p in u.group(1).split("/")), u.end()
        found.append((value, (m.group("cur") or "") + (" " if m.group("cur") and unit else "") + unit))
        spans.append((start, end))
    chars = list(text)
    for s, e in spans:
        chars[s:e] = " " * (e - s)
    items = [(s, "N", v) for (s, _), (v, _) in zip(spans, found)]
    items += [(w.start(), "W", w.group(0).lower()) for w in ALPHA.finditer("".join(chars))]
    return found, [(kind, v) for _, kind, v in sorted(items)]


# --- Claim words: the ladder, and the other words whose change changes a claim ---------------------------------

MARKERS = (
    ("rung1", r"may|might|could|possibl[ey]|perhaps|potential(?:ly)?|conceivabl[ey]|plausibl[ey]"),
    ("rung2", r"suggest(?:s|ed|ing)?|indicat(?:e|es|ed|ing)|appear(?:s|ed|ing)?|seem(?:s|ed|ing)?|impl(?:y|ies|ied)"
              r"|(?:un)?likely|probabl[ey]|presumabl[ey]|apparently|tend(?:s|ed)? to|consistent with"),
    ("rung3", r"associat(?:ed|ion|ions)|correlat(?:e|es|ed|ion|ions)|linked (?:to|with)|link between"),
    ("rung4", r"show(?:s|ed|n|ing)?|finds?|found|demonstrat(?:e|es|ed|ing)|reveal(?:s|ed|ing)?"),
    ("rung5", r"caus(?:e|es|ed|ing|al|ally)|lead(?:s|ing)? to|led to|result(?:s|ed|ing)? in|dr(?:ive|ives|ove|iven|iving)"
              r"|due to|because|owing to|attributable to|contribut(?:e|es|ed|ing) to|induc(?:e|es|ed|ing)"),
    ("rung6", r"prov(?:e|es|ed|en|ing)|establish(?:es|ed|ing)?|confirm(?:s|ed|ing)?|clearly|definitely|undoubtedly"
              r"|conclusively|certainly|unequivocally|definitively"),
    ("negation", r"not|no|never|without|neither|nor|nobody|nothing|unlikely|non-?significant|insignificant"
                 r"|fail(?:s|ed|ing)? to|lack(?:s|ed|ing)?|absence of|unable"),
    ("quantifier: all", r"all|every|each|always|entire(?:ly)?"),
    ("quantifier: most", r"most|mostly|majority|usually|largely|predominantly"),
    ("quantifier: many", r"many|numerous|often|frequently|commonly"),
    ("quantifier: some", r"some|several|a few|sometimes|occasionally|partly|partially"),
    ("quantifier: few", r"(?<!a )few|rarely|seldom"),
    ("quantifier: none", r"none"),
    ("scope", r"only|solely|exclusively|merely"),
    ("significance", r"(?:non-?|in)?significan(?:t|tly|ce)"),
    ("intensifier", r"substantial(?:ly)?|marked(?:ly)?|dramatic(?:ally)?|considerabl[ey]|greatly|strongly|highly"
                    r"|remarkabl[ey]|very|extremely|profoundly|sharply|vastly|strikingly"),
    ("downtoner", r"slight(?:ly)?|somewhat|modest(?:ly)?|marginal(?:ly)?|mildly|minimal(?:ly)?|negligibl[ey]|a little"),
    ("approximation", r"approximately|roughly|nearly|almost|circa|(?:about|around|some)(?= \d)|[~≈](?= ?\d)"),
    ("modal", r"can|will|would|should|must|shall"),
    ("contrast", r"however|but|although|though|whereas|nevertheless|nonetheless|in contrast|by contrast|conversely"
                 r"|despite|in spite of|on the other hand|instead|rather than"),
    ("consequence", r"therefore|thus|hence|consequently|accordingly|as a result|thereby"
                    r"|so(?= (?:the|this|these|those|we|it|they|a|an|our|its|their|there)\b)"),
)
MARKER_RES = [(label, re.compile(rf"(?<![\w-])(?:{pattern})(?![\w-])")) for label, pattern in MARKERS]
LABELS = {"rung1": "rung 1 (may)", "rung2": "rung 2 (suggest)", "rung3": "rung 3 (associated)", "rung4": "rung 4 (show)",
          "rung5": "rung 5 (cause)", "rung6": "rung 6 (prove)"}
# "Table 2 shows" and "as shown in Figure 1" describe a display, not a claim.
NEAR_DISPLAY = re.compile(r"(?:table|figure|fig\.?|panel|appendix|supplement\w*)\s*\S{0,8}\s*$")
TO_DISPLAY = re.compile(r"\s*(?:in|by)\s+(?:table|figure|fig\b|panel|appendix|supplement)")
DIRECTION_UP = re.compile(r"\b(?:higher|greater|larger|more|above|increas(?:e|es|ed|ing)|rise|rises|rose|risen|better"
                          r"|improv(?:e|es|ed|ing|ement)|longer|faster|outperform(?:s|ed)?|exceed(?:s|ed)?|superior)\b")
DIRECTION_DOWN = re.compile(r"\b(?:lower|less|fewer|smaller|below|decreas(?:e|es|ed|ing)|reduc(?:e|es|ed|ing|tion)"
                            r"|declin(?:e|es|ed|ing)|drop(?:s|ped)?|fell|falls?|worse|worsen(?:s|ed|ing)?|shorter|slower"
                            r"|inferior|underperform(?:s|ed)?)\b")
ARTICLE = re.compile(r"\b(a|an|the|one of the)\s+(?:[a-z-]+\s+){0,2}?(cause|reason|factor|driver|determinant|explanation"
                     r"|mechanism|source|predictor|contributor|origin|basis)s?\b")
VERBS = ("show find increase decrease reduce improve differ predict correlate associate remain occur exceed outperform "
         "yield achieve cause affect demonstrate reveal indicate suggest appear seem tend lead").split()
PAST = {"was": "be", "were": "be", "had": "have", "did": "do", **{{"show": "showed", "find": "found", "lead": "led",
        "occur": "occurred"}.get(v, v + ("d" if v.endswith("e") else "ed")): v for v in VERBS}}
PRESENT = {"is": "be", "are": "be", "has": "have", "have": "have", "does": "do", "do": "do",
           **{v + "s": v for v in VERBS}, **{v: v for v in VERBS}}
AUX = frozenset("am is are was were be been being has have had".split())
NOT_FINITE = frozenset("to not did do does may might can could will would should must shall".split())
DISPLAY_WORDS = frozenset("table tables figure figures fig panel appendix supplement supplementary".split())


def lower_for_markers(plain: str) -> str:
    text = re.sub(r"\bMay(?=\s+\d)", "month", plain).lower().replace("’", "'")
    text = text.replace("cannot", "can not").replace("can't", "can not").replace("won't", "will not")
    return re.sub(r"n't\b", " not", text)


def markers_in(plain: str) -> list[tuple[str, str]]:
    low, out = lower_for_markers(plain), []
    for label, pattern in MARKER_RES:
        for m in pattern.finditer(low):
            if not (label.startswith("rung") and (NEAR_DISPLAY.search(low[max(0, m.start() - 25):m.start()])
                                                  or TO_DISPLAY.match(low, m.end()))):
                out.append((label, m.group(0)))
    return out


def tenses(low: str) -> Counter:
    """Finite past and present forms of be, have, do and common result verbs."""
    words, out = re.findall(r"[a-z]+", low), Counter()
    for i, word in enumerate(words):
        prev = words[max(0, i - 3):i]
        if set(prev) & DISPLAY_WORDS:
            continue
        if word in PAST and not (prev and prev[-1] in AUX):              # "was associated": a participle
            out[("past", PAST[word])] += 1
        elif word in PRESENT and not (word in VERBS and prev and prev[-1] in NOT_FINITE):
            out[("present", PRESENT[word])] += 1
    return out


def strength(marks: Counter) -> float:
    return max((k for k in (3, 4, 5, 6) if marks[f"rung{k}"]), default=0) - 0.5 * (marks["rung1"] + marks["rung2"])


# --- Paragraphs and sentences -------------------------------------------------------------------------------

SENTENCE_END = re.compile(r"[.!?][\"')\]}”’]*\s+(?=[\"'“‘(\[]?[A-Z0-9\\@⟦])")
NO_END = re.compile(r"\b(?:e\.g|i\.e|et al|vs|cf|Figs?|Eqs?|Refs?|Tabs?|Dr|Prof|approx|resp|ca|St|Mr|Mrs|Ms|No|Nos|Vol"
                    r"|pp?|Suppl)\.$")
HEADING = re.compile(r"^\s{0,3}#{1,6}\s+\S|^\s*\\(?:part|chapter|section|subsection|subsubsection|paragraph)\*?\s*[\[{]")
ITEM = re.compile(r"^\s*(?:(?:[-*+•]|\d+[.)])\s+|\\item\b)")
STOP = frozenset("the and for but with from into that this these those their there which who whom whose than then also are "
                 "was were been being has have had its our they them per via not".split())


def split_sentences(text: str) -> list[str]:
    out, start = [], 0
    for m in SENTENCE_END.finditer(text):
        if not NO_END.search(text[start:m.start() + 1]):
            out.append(text[start:m.end()].strip())
            start = m.end()
    return [s for s in out + [text[start:].strip()] if s]


def plain_text(masked: str, tex: bool) -> str:
    text = PH.sub(" ", masked)
    if tex:
        text = text.replace("~", " ").replace("\\%", "%").replace("\\&", "&").replace("\\\\", " ")
        text = re.sub(r"\\[A-Za-z]+\*?(?:\[[^\]]*\])?", " ", text).replace("{", " ").replace("}", " ")
    return squash(re.sub(r"[*`]|(?<!\w)_|_(?!\w)|^\s*(?:#+|>+)\s?", " ", text))


def sentence(masked: str, store: dict, tex: bool) -> dict:
    found, plain = PH.findall(masked), plain_text(masked, tex)
    numbers, stream = numbers_in(plain)
    words = [w.lower() for w in WORD.findall(plain)]
    cites = [item for kind, i in found if kind == "C" for item in store["C"][int(i)][1]]
    return {"text": squash(restore(masked, store)), "plain": plain, "words": words, "numbers": numbers, "stream": stream,
            "cites": cites, "keys": [store[kind][int(i)][1] for kind, i in found if kind != "C"], "marks": markers_in(plain),
            "bag": Counter(w[:6] for w in words if len(w) > 2 and w not in STOP and not w.isdigit())
            + Counter("#" + v for v, _ in numbers) + Counter("@" + c for c in cites)}


def parse(path: Path) -> dict:
    tex = path.suffix.lower() == ".tex"
    masked, store = mask(read_text(path), tex)
    units, current = [], []
    for line in masked.split("\n") + [""]:
        if not line.strip() or HEADING.match(line) or line.lstrip().startswith("|") or ITEM.match(line):
            if current:
                units.append(("text", " ".join(current)))
                current = []
        if HEADING.match(line) or line.lstrip().startswith("|"):
            units.append(("heading" if HEADING.match(line) else "table", line.strip()))
        elif line.strip():
            current.append(line.strip())
    sentences, para = [], 0
    for kind, text in units:
        found = [s for s in (sentence(x, store, tex) for x in ([text] if kind != "text" else split_sentences(text)))
                 if s["words"] or s["cites"]]
        for n, s in enumerate(found):
            s.update(para=para, n=n, kind=kind)
        sentences += found
        para += bool(found)
    if not sentences:
        fail(f"{path}: no text found")
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "sentences": sentences,
            "store": store, "text": restore(masked, store)}


# --- Alignment ------------------------------------------------------------------------------------------------

def share_in(x: Counter, y: Counter) -> float:
    return sum((x & y).values()) / max(1, sum(x.values()))


def dice(x: Counter, y: Counter) -> float:
    total = sum(x.values()) + sum(y.values())
    return 2 * sum((x & y).values()) / total if total else 1.0


def align(B: list, A: list) -> list[dict]:
    """Groups of corresponding sentences in order: one to one, one to two (a split), two to one (a merge), or one
    side alone. A split or merge must keep each part mostly inside the other side. Sentences then left alone on
    both sides are paired across the order when they are similar enough: those moved."""
    n, m = len(B), len(A)
    band, best = 25 + abs(n - m), {(0, 0): (0.0, None)}
    for i in range(n + 1):
        centre = i * m // max(n, 1)
        for j in range(max(0, centre - band), min(m, centre + band) + 1):
            if (i, j) not in best:
                continue
            for di, dj in ((1, 1), (1, 0), (0, 1), (2, 1), (1, 2)):
                ii, jj = i + di, j + dj
                if ii > n or jj > m:
                    continue
                step = SKIP
                if di and dj:
                    left, right = [B[k] for k in range(i, ii)], [A[k] for k in range(j, jj)]
                    parts, whole = (left, right) if di == 2 else (right, left)
                    one = sum((u["bag"] for u in whole), Counter())
                    if len(parts) == 2 and (parts[0]["para"] != parts[1]["para"]
                                            or min(share_in(u["bag"], one) for u in parts) < PART_INSIDE):
                        continue
                    step = 1 - dice(sum((u["bag"] for u in parts), Counter()), one) + SPLIT_COST * (di + dj == 3)
                if best[(i, j)][0] + step < best.get((ii, jj), (float("inf"),))[0]:
                    best[(ii, jj)] = (best[(i, j)][0] + step, (i, j))
    groups, cell = [], (n, m)
    while cell != (0, 0):
        i, j = best[cell][1]
        groups.insert(0, {"b": list(range(i, cell[0])), "a": list(range(j, cell[1])), "moved": False})
        cell = (i, j)
    alone_b, alone_a = [g["b"][0] for g in groups if not g["a"]], [g["a"][0] for g in groups if not g["b"]]
    moved = {}
    for score, i, j in sorted(((dice(B[i]["bag"], A[j]["bag"]), i, j) for i in alone_b for j in alone_a), reverse=True):
        if score >= MOVE_FLOOR and i not in moved and j not in moved.values():
            moved[i] = j
    return [{"b": g["b"], "a": [moved[g["b"][0]]], "moved": True} if g["b"] and not g["a"] and g["b"][0] in moved else g
            for g in groups if g["b"] or g["a"][0] not in moved.values()]


def changed_share(before: list, after: list) -> float:
    """The share of words that differ, against the longer side, so that deleting text cannot lower it."""
    if not before and not after:
        return 0.0
    matched = sum(b.size for b in difflib.SequenceMatcher(a=before, b=after, autojunk=False).get_matching_blocks())
    return 1 - matched / max(len(before), len(after))


def traded(sa: list, sb: list) -> list[tuple[str, str]]:
    """Numbers replaced in place by other numbers while the words around them stayed. Aligned with every value
    blanked, the streams say which number slot became which; a slot between aligned words whose value differs
    held another value before. A value that kept its place in the value-aware alignment moved with its words."""
    kept_a, kept_b = set(), set()
    for block in difflib.SequenceMatcher(a=sa, b=sb, autojunk=False).get_matching_blocks():
        if block.size >= 2:
            kept_a.update(range(block.a, block.a + block.size))
            kept_b.update(range(block.b, block.b + block.size))
    blank = [[(k, "" if k == "N" else v) for k, v in s] for s in (sa, sb)]
    return [(sa[block.a + k][1], sb[block.b + k][1])
            for block in difflib.SequenceMatcher(a=blank[0], b=blank[1], autojunk=False).get_matching_blocks()
            for k in range(1, block.size - 1) if sa[block.a + k][0] == "N" and block.a + k not in kept_a
            and block.b + k not in kept_b and sa[block.a + k][1] != sb[block.b + k][1]]


# --- diff -----------------------------------------------------------------------------------------------------

def load_terms(path: str | None) -> list[str] | None:
    if path and not Path(path).is_file():
        fail(f"no such file: {path}")
    return [t.strip() for t in Path(path).read_text(encoding="utf-8").splitlines()
            if t.strip() and not t.startswith("#")] if path else None


def count_term(term: str, text: str) -> int:
    return len(re.findall(rf"(?<![\w-]){re.escape(term)}(?![\w-])", text))


def where(units) -> str:
    return ", ".join(f"¶{u['para'] + 1}.{u['n'] + 1}" for u in units) or "-"


def listed(values: Counter) -> str:
    return ", ".join(sorted(values.elements())) or "nothing"


def compare(db: dict, da: dict, level: str, terms: list | None, limit: float) -> dict:
    B, A = db["sentences"], da["sentences"]
    groups, findings, counts = align(B, A), [], Counter()
    lost, gone, new = [], Counter(), Counter()

    def report(severity, check, code, message, b=(), a=()):
        findings.append({"severity": severity, "check": check, "code": code, "message": message,
                         "where": f"{where(b)} → {where(a)}", "before": " ".join(u["text"] for u in b),
                         "after": " ".join(u["text"] for u in a)})

    def said(units, label):
        return ", ".join(w for u in units for x, w in u["marks"] if x == label) or "nothing"

    for g in groups:
        b, a = [B[i] for i in g["b"]], [A[j] for j in g["a"]]
        if not (b and a):
            counts["removed or rewritten beyond comparison" if b else "new or rewritten beyond comparison"] += 1
            continue
        kind = "moved" if g["moved"] else "split" if len(a) > len(b) else "merged" if len(b) > len(a) else ""
        changed = squash(" ".join(u["text"] for u in b)) != squash(" ".join(u["text"] for u in a))
        counts[kind or ("edited" if changed else "unchanged")] += 1
        nb, na = [x for u in b for x in u["numbers"]], [x for u in a for x in u["numbers"]]
        vb, va = Counter(v for v, _ in nb), Counter(v for v, _ in na)
        streams = ([t for u in s for t in u["stream"] + [("S", "")]] for s in (b, a))
        if vb != va:
            gone, new = gone + (vb - va), new + (va - vb)
            report("error", "numbers", "number_changed", f"{listed(vb - va)} → {listed(va - vb)}", b, a)
        elif [v for v, _ in nb] != [v for v, _ in na] and (swaps := traded(*streams)):
            report("error", "numbers", "values_traded_places", f"the places that held {', '.join(x for x, _ in swaps)} "
                   f"now hold {', '.join(y for _, y in swaps)}", b, a)
        for value in sorted(vb.keys() & va.keys()):
            for ub, ua in zip([u for v, u in nb if v == value], [u for v, u in na if v == value]):
                if ub and ub != ua:
                    report("error" if ua else "warning", "numbers", "unit_changed" if ua else "unit_dropped",
                           f"{value} {ub} → {value} {ua}".rstrip(), b, a)
        cb, ca = Counter(c for u in b for c in u["cites"]), Counter(c for u in a for c in u["cites"])
        lost += [(c, b, a) for c in (cb - ca).elements()]
        if kind in ("split", "merged") and cb + ca:
            report("warning", "citations", f"cited_sentence_{kind}", "check that each citation still covers what it "
                   "covered: " + listed(cb | ca), b, a)
        if level == "light" and kind in ("split", "merged"):
            report("error", "structure", "split_or_merged", f"a sentence was {kind}: a light edit keeps sentence structure",
                   b, a)
        if not changed:
            continue
        mb, ma = (Counter(label for u in s for label, _ in u["marks"]) for s in (b, a))
        if rungs := [x for x in LABELS if mb[x] != ma[x]]:
            shift = strength(ma) - strength(mb)
            report("error", "claims", "claim_strength", ("moved up the ladder: " if shift > 0 else "moved down the ladder: "
                   if shift < 0 else "changed on the ladder: ") + "; ".join(
                       f"{LABELS[x]} {said(b, x)} → {said(a, x)}" for x in rungs), b, a)
        for label in sorted(x for x in set(mb) | set(ma) if x not in LABELS and mb[x] != ma[x]):
            report("error", "claims", label.split(":")[0].replace(" ", "_") + "_changed",
                   f"{label}: {said(b, label)} → {said(a, label)}", b, a)
        low_b, low_a = (lower_for_markers(" ".join(u["plain"] for u in s)) for s in (b, a))
        (up_b, up_a), (down_b, down_a) = ([r.findall(t) for t in (low_b, low_a)] for r in (DIRECTION_UP, DIRECTION_DOWN))
        if (up_b and down_a and not up_a and not down_b) or (down_b and up_a and not down_a and not up_b):
            report("error", "claims", "direction_changed", f"{', '.join(up_b or down_b)} → {', '.join(up_a or down_a)}",
                   b, a)
        arts = [", ".join(sorted(f"{'the' if x.group(1) == 'the' else 'a'} {x.group(2)}" for x in ARTICLE.finditer(t)))
                for t in (low_b, low_a)]
        if arts[0] != arts[1]:
            report("error", "claims", "article_changed", f"{arts[0] or 'nothing'} → {arts[1] or 'nothing'}", b, a)
        tb, ta = tenses(low_b), tenses(low_a)
        if shifted := sorted(v for k, v in tb if k == "past" and ta[("past", v)] < tb[("past", v)]
                             and ta[("present", v)] > tb[("present", v)]):
            report("error", "claims", "past_to_present", "from past to present tense: " + ", ".join(shifted), b, a)

    # Over the whole text: values and citations that left sentences nobody could compare, keys, terms.
    every = [Counter(v for u in s for v, _ in u["numbers"]) for s in (B, A)]
    for value in sorted(set(every[0]) | set(every[1])):
        net = every[1][value] - every[0][value]
        if -net - gone[value] > 0:
            report("error", "numbers", "number_disappeared", f"{value} ({-net - gone[value]}×) is no longer in the text",
                   [next(u for u in B if value in [v for v, _ in u["numbers"]])])
        if net - new[value] > 0:
            report("error", "numbers", "number_appeared", f"{value} ({net - new[value]}×) is new",
                   (), [next(u for u in A if value in [v for v, _ in u["numbers"]])])
    cited = [Counter(c for u in s for c in u["cites"]) for s in (B, A)]
    for key in sorted(set(cited[0]) | set(cited[1])):
        if cited[0][key] != cited[1][key]:
            dropped = cited[1][key] < cited[0][key]
            unit = [next(u for u in (B if dropped else A) if key in u["cites"])]
            report("error", "citations", "citation_dropped" if dropped else "citation_added",
                   f"{key}: cited {cited[0][key]}× before, {cited[1][key]}× after", *((unit, ()) if dropped else ((), unit)))
    for key, b, a in lost:
        if cited[1][key] >= cited[0][key]:
            report("error", "citations", "citation_moved", f"{key} left this sentence for another", b, a)
    for kind, title in (("K", "cross-references, labels, files and links"), ("F", "formulas and code")):
        xb, xa = ([v for _, v in d["store"][kind]] for d in (db, da))
        if Counter(xb) != Counter(xa):
            out, add = Counter(xb) - Counter(xa), Counter(xa) - Counter(xb)
            report("error", "keys", "key_changed" if kind == "K" else "formula_changed",
                   f"{title}: {listed(out)} → {listed(add)}", [u for u in B if set(u["keys"]) & set(out)][:1],
                   [u for u in A if set(u["keys"]) & set(add)][:1])
        elif xb != xa:
            report("warning" if level == "heavy" else "error", "keys", "order_changed", f"{title} are in another order")
    text_b, text_a = (" ".join(u["plain"] for u in s) for s in (B, A))
    for term in terms or []:
        if count_term(term, text_b) != count_term(term, text_a):
            report("error", "terms", "protected_term_changed", f"{term}: {count_term(term, text_b)}× before, "
                   f"{count_term(term, text_a)}× after")
    known = set(WORD.findall(text_b + " " + " ".join(original for original, _ in db["store"]["C"])))
    for u in A:
        for term in (m.group(0) for m in re.finditer(r"\b[A-Z][\w-]*", u["plain"]) if m.start() or m.group(0).isupper()):
            if term not in known and len(term) > 1:
                known.add(term)
                report("warning", "new_terms", "new_term", f"{term} is not in the original", (), [u])

    # Paragraphs: the share of changed words, sentences that moved, and sentences nobody could compare.
    reach, alone_a, paragraphs = {}, [g["a"][0] for g in groups if not g["b"]], []
    for g in groups:
        if g["b"] and g["a"] and not g["moved"]:
            reach.setdefault(B[g["b"][0]]["para"], set()).update(A[j]["para"] for j in g["a"])
    for p in sorted({u["para"] for u in B}):
        mine = [g for g in groups if g["b"] and B[g["b"][0]]["para"] == p]
        after = sorted([j for g in mine for j in g["a"]] + [j for j in alone_a if A[j]["para"] in reach.get(p, ())])
        share = changed_share([w for g in mine for i in g["b"] for w in B[i]["words"]],
                              [w for j in after for w in A[j]["words"]])
        paragraphs.append({"paragraph": p + 1, "sentences": f"{sum(len(g['b']) for g in mine)} → {len(after)}",
                           "changed_words": round(share, 3)})
        if share > limit:
            report("warning", "structure", "large_footprint", f"¶{p + 1}: {share:.0%} of the words changed; the convention "
                   f"for {level} is up to {limit:.0%}", [B[mine[0]["b"][0]]])
    for g in groups:
        b, a = [B[i] for i in g["b"]], [A[j] for j in g["a"]]
        inside = g["moved"] and a[0]["para"] in reach.get(b[0]["para"], ())
        if g["moved"] and (level != "heavy" or not inside):
            report("error", "structure", "sentence_moved", "the sentence moved " + ("within its paragraph: only a heavy "
                   "edit reorders sentences" if inside else "to another paragraph"), b, a)
        elif level == "light" and not (b and a):
            report("error", "structure", "not_compared", "no counterpart close enough to compare: a light edit keeps every "
                   "sentence recognisable", b, a)
    paras = [len({u["para"] for u in s}) for s in (B, A)]
    if paras[0] != paras[1]:
        report("error" if level == "light" else "warning", "structure", "paragraph_count",
               f"{paras[0]} paragraphs before, {paras[1]} after")
    checks = {key: "checked" for key, _ in CHECKS}
    checks["terms"] = "checked" if terms else "not_checked: no --protect file, or it is empty"
    letters = "".join(ALPHA.findall(text_b))
    if sum(map(str.isascii, letters)) < 0.7 * len(letters):
        checks["claims"] = "not_checked: the claim words are English and the text is not"
        findings = [f for f in findings if f["check"] != "claims"]
    return {"findings": findings, "counts": dict(counts), "paragraphs": paragraphs, "checks": checks, "groups": groups,
            "not_compared": {"before": [B[i]["text"] for g in groups if not g["a"] for i in g["b"]],
                             "after": [A[j]["text"] for g in groups if not g["b"] for j in g["a"]]}}


CHECKS = (("numbers", "Numbers and units"), ("citations", "Citations"), ("keys", "Cross-references, formulas and code"),
          ("terms", "Protected terms"), ("claims", "Claim strength"), ("structure", "Structure for the level"),
          ("new_terms", "New terms"))


def cell(value, width: int = 240) -> str:
    text = re.sub(r"\s+", " ", str(value if value is not None else "")).replace("|", "/")
    return text if len(text) <= width else text[:width - 1] + "…"


def table(header: tuple, rows) -> list[str]:
    return (["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
            + ["| " + " | ".join(cell(v) for v in row) + " |" for row in rows])


def write_diff_report(path: Path, r: dict) -> None:
    errors, warnings = ([f for f in r["findings"] if f["severity"] == s] for s in ("error", "warning"))
    s = r["summary"]
    lines = ["# Polish check", "", f"`{r['before']['path']}` → `{r['after']['path']}`, level {r['level']}.", "",
             f"{s['errors']} errors, {s['warnings']} warnings, {s['not_compared']} sentences not compared. "
             f"{s['sentences_before']} sentences before, {s['sentences_after']} after: "
             + ", ".join(f"{n} {k}" for k, n in sorted(r["counts"].items())) + ".", ""]
    lines += table(("Check", "State", "Errors", "Warnings"), [
        (title, r["checks"][key].replace("_", " "), sum(f["check"] == key for f in errors),
         sum(f["check"] == key for f in warnings)) for key, title in CHECKS])
    lines += ["", "An error is undone, or the edit becomes a question for the author. A warning is read and fixed or "
              "explained. A check that was not checked says nothing about the text. Places are ¶paragraph.sentence, "
              "before → after."]
    for title, rows in (("Errors", errors), ("Warnings", warnings)):
        if rows:
            lines += ["", f"## {title} ({len(rows)})", ""] + table(("Check", "Finding", "Where", "Before", "After"), [
                (f["code"].replace("_", " "), f["message"], f["where"], f["before"], f["after"]) for f in rows])
    lines += ["", "## Paragraphs", ""] + table(("Paragraph", "Sentences", "Words changed", f"Convention for {r['level']}"), [
        (f"¶{p['paragraph']}", p["sentences"], f"{p['changed_words']:.0%}", f"{r['footprint_limit']:.0%}")
        for p in r["paragraphs"]])
    for side, rows in r["not_compared"].items():
        if rows:
            lines += ["", f"## Not compared, {side} ({len(rows)})", "", "No counterpart close enough to compare: read "
                      "these yourself. A sentence that is new adds content.", ""] + [f"- {cell(t)}" for t in rows]
    lines += ["", "Not checked by this script: whether a reworded sentence keeps its meaning when its numbers, citations "
              "and listed words stay the same; claim words outside its lists; text in other languages."]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def cmd_diff(args) -> int:
    db, da = parse(Path(args.before)), parse(Path(args.after))
    limit = args.max_footprint if args.max_footprint is not None else FOOTPRINT[args.level]
    result = compare(db, da, args.level, load_terms(args.protect), limit)
    groups, errors = result.pop("groups"), sum(f["severity"] == "error" for f in result["findings"])
    result = {"tool": TOOL, "command": "diff", "level": args.level, "footprint_limit": limit,
              "before": {"path": db["path"], "sha256": db["sha256"]}, "after": {"path": da["path"], "sha256": da["sha256"]},
              "summary": {"errors": errors, "warnings": len(result["findings"]) - errors,
                          "not_compared": sum(1 for g in groups if not (g["b"] and g["a"])),
                          "sentences_before": len(db["sentences"]), "sentences_after": len(da["sentences"]),
                          "by_code": dict(Counter(f["code"] for f in result["findings"]))}, **result}
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "polish-check.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    write_diff_report(out / "polish-check.md", result)
    print(json.dumps({"level": args.level, **result["summary"], "checks": result["checks"],
                      "report": str(out / "polish-check.md")}, indent=2, ensure_ascii=False))
    return 1 if errors else 0


# --- survey ---------------------------------------------------------------------------------------------------

# Leads for author queries. A p above 0.05 is a convention for "not significant"; the author's alpha decides.
NOT_SIGNIFICANT = re.compile(r"\bp\s*(?:=|>|≥)\s*0?\.(?:0[5-9]|[1-9])\d*|not (?:statistically )?significant"
                             r"|non-?significant|insignificant|n\.s\.|did not reach (?:statistical )?significance"
                             r"|no significant", re.I)
COMPARATIVE = re.compile(r"\b(?:better|worse|higher|lower|greater|smaller|superior|inferior|improv\w*|outperform\w*"
                         r"|benefit\w*|advantage\w*|trend\w*)\b", re.I)
TEST = re.compile(r"\bp\s*[<=>≤≥]|\bCI\b|confidence interval|\b[tFzUWHQ]\s*\(|χ2|chi-?squared?|\btest(?:s|ed)?\b", re.I)


def cmd_survey(args) -> int:
    doc = parse(Path(args.file))
    S, kinds, names = doc["sentences"], {}, Counter()
    text = " ".join(u["plain"] for u in S)
    for u in S:
        for m in re.finditer(r"\b[^\W_][\w-]*[^\W_]", u["plain"]):
            t = m.group(0)
            if re.fullmatch(r"[A-Z][A-Z0-9]*[A-Z][A-Z0-9]*s?", t):
                kinds.setdefault(t, "abbreviation")
            elif re.search(r"\d", t) and re.search(r"[A-Za-z]", t) or "_" in t or re.search(r"[a-z][A-Z]", t):
                kinds.setdefault(t, "symbol or name with digits or capitals")
            elif t[0].isupper() and m.start() > 0:
                names[t] += 1
    kinds.update({t: "capitalised word, used twice or more" for t, k in names.items() if k > 1 and t not in kinds})
    candidates = sorted(({"term": t, "kind": k, "count": count_term(t, text)} for t, k in kinds.items()),
                        key=lambda c: (c["kind"], -c["count"], c["term"]))
    claims, queries = [], []
    for u in S:
        if u["marks"]:
            claims.append({"where": where([u]), "rungs": [f"{LABELS[x]}: {w}" for x, w in u["marks"] if x in LABELS],
                           "other": [f"{x}: {w}" for x, w in u["marks"] if x not in LABELS], "sentence": u["text"]})
        evidence = u["plain"] + " " + " ".join(u["keys"])
        if NOT_SIGNIFICANT.search(evidence) and COMPARATIVE.search(u["plain"]):
            queries.append({"where": where([u]), "why": "a comparison beside a result that is not significant",
                            "sentence": u["text"]})
        elif re.search(r"\bsignificant(?:ly)?\b", u["plain"], re.I) and not TEST.search(evidence):
            queries.append({"where": where([u]), "why": "'significant' with no test in the sentence: statistical or "
                            "everyday sense?", "sentence": u["text"]})
    counts = {"paragraphs": len({u["para"] for u in S}), "sentences": len(S), "words": sum(len(u["words"]) for u in S),
              "numbers": sum(len(u["numbers"]) for u in S), "citations": sum(len(u["cites"]) for u in S),
              "cross_references": len(doc["store"]["K"]), "formulas_and_code": len(doc["store"]["F"])}
    terms = [{"term": t, "count": count_term(t, text)} for t in load_terms(args.protect) or []]
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    result = {"tool": TOOL, "command": "survey", "file": {"path": doc["path"], "sha256": doc["sha256"]}, "counts": counts,
              "protected_terms": terms, "candidates": candidates, "claims": claims, "queries": queries}
    (out / "survey.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    lines = ["# Survey", "", f"`{doc['path']}`: " + ", ".join(f"{n} {k.replace('_', ' ')}" for k, n in counts.items()) + "."]
    if terms:
        lines += ["", "## Protected terms", ""] + table(("Term", "Occurrences"), [(t["term"], t["count"]) for t in terms])
    lines += ["", "## Candidates for the protected-term list", "", "Propose these to the author; the list is theirs.", ""]
    lines += table(("Term", "Kind", "Occurrences"), [(c["term"], c["kind"], c["count"]) for c in candidates])
    lines += ["", "## Claim words per sentence", "", f"{len(claims)} of {len(S)} sentences carry a listed claim word; "
              "the polish keeps each at its strength.", ""]
    lines += table(("Where", "Ladder", "Other claim words", "Sentence"), [
        (c["where"], "; ".join(c["rungs"]), "; ".join(c["other"]), cell(c["sentence"], 160)) for c in claims])
    lines += ["", "## Leads for author queries", "", "Leads to read, not verdicts." if queries
              else "None found by the script; read the text for others.", ""]
    lines += [f"- {q['where']} ({q['why']}): {cell(q['sentence'], 200)}" for q in queries]
    (out / "survey.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"file": doc["path"], **counts, "candidates": len(candidates), "query_leads": len(queries),
                      "sentences_with_claim_words": len(claims), "report": str(out / "survey.md")}, indent=2))
    return 0


# --- log ------------------------------------------------------------------------------------------------------

def contains(hay: str, needle: str) -> bool:
    return bool(needle) and re.search(rf"(?<!\w){re.escape(needle)}(?!\w)", hay) is not None


def redline(before: str, after: str) -> str:
    """A word-level redline in Markdown: deleted words struck through, inserted words in bold."""
    tb, ta = re.findall(r"\S+\s*", before), re.findall(r"\S+\s*", after)

    def mark(sign: str, tokens: list) -> str:                   # one mark per paragraph, around words only
        parts = re.split(r"(\n\s*\n\s*)", "".join(tokens))
        return "".join(p if i % 2 or not p.strip() else f"{sign}{p.rstrip()}{sign}{p[len(p.rstrip()):]}"
                       for i, p in enumerate(parts))

    matcher = difflib.SequenceMatcher(a=[t.strip() for t in tb], b=[t.strip() for t in ta], autojunk=False)
    return "".join("".join(ta[j1:j2]) if op == "equal" else mark("~~", tb[i1:i2]) + mark("**", ta[j1:j2])
                   for op, i1, i2, j1, j2 in matcher.get_opcodes())


def latexdiff(before: Path, after: Path, out: Path) -> str:
    if not before.suffix.lower() == after.suffix.lower() == ".tex":
        return "not applicable: the files are not LaTeX"
    if not (exe := shutil.which("latexdiff")):
        return "not installed: no latexdiff redline was produced"
    try:
        done = subprocess.run([exe, str(before), str(after)], capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"failed ({exc}): no latexdiff redline was produced"
    if done.returncode or not done.stdout.strip():
        why = (done.stderr.strip().splitlines() or ["no output"])[-1][:160]
        return f"failed ({why}): no latexdiff redline was produced"
    (out / "redline-latexdiff.tex").write_text(done.stdout, encoding="utf-8")
    return "written: redline-latexdiff.tex"


def cmd_log(args) -> int:
    db, da = parse(Path(args.before)), parse(Path(args.after))
    try:
        data = json.loads(Path(args.changes).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        fail(f"{args.changes}: not readable JSON ({exc})")
    entries = data.get("changes") if isinstance(data, dict) else data
    if not isinstance(entries, list):
        fail(f'{args.changes}: write {{"changes": [{{"id", "location", "before", "after", "reason"}}, …]}}')
    checked = []
    for k, e in enumerate(entries, 1):
        e = e if isinstance(e, dict) else {}
        before, after, given = squash(str(e.get("before") or "")), squash(str(e.get("after") or "")), e.get("reason") or []
        reasons = [str(r).strip().lower() for r in (re.split(r"[;,]", given) if isinstance(given, str) else given)
                   if str(r).strip()]
        problems = ([] if reasons else ["no reason"]) + [f'"{r}" is not on the list of reasons' if r not in REASONS else
                                                         f'"{r}" is not allowed at the {args.level} level'
                                                         for r in reasons if r not in ALLOWED[args.level]]
        problems += ["before and after are both empty"] if not (before or after) else []
        problems += ["before and after are the same"] if before and before == after and "reorder" not in reasons else []
        for side, value, doc in (("before", before, db), ("after", after, da)):
            hits = len(re.findall(rf"(?<!\w){re.escape(value)}(?!\w)", squash(doc["text"]))) if value else 1
            if not hits:
                ratio, near = max((difflib.SequenceMatcher(a=value, b=u["text"]).ratio(), u["text"])
                                  for u in doc["sentences"])
                hint = f' (closest: "{cell(near, 90)}")' if ratio > 0.6 else ""
                problems.append(f"{side} text is not in {doc['path']}{hint}")
            elif hits > 1 and len(value.split()) < 4:
                problems.append(f"{side} text occurs {hits} times: quote enough words to find it once")
        checked.append({"id": str(e.get("id") or f"#{k}"), "location": str(e.get("location") or ""), "reasons": reasons,
                        "before": before, "after": after, "problems": problems})
    uncovered = []
    for g in align(db["sentences"], da["sentences"]):
        b, a = [db["sentences"][i] for i in g["b"]], [da["sentences"][j] for j in g["a"]]
        tb, ta = squash(" ".join(u["text"] for u in b)), squash(" ".join(u["text"] for u in a))
        if b and a and tb == ta and not g["moved"]:
            continue
        cover = [e for e in checked if (e["before"] or e["after"]) and (not e["before"] or contains(tb, e["before"]))
                 and (not e["after"] or contains(ta, e["after"])) or contains(e["before"], tb) or contains(e["after"], ta)]
        if not cover or (g["moved"] and not any("reorder" in e["reasons"] for e in cover)):
            uncovered.append({"where": f"{where(b)} → {where(a)}", "before": tb, "after": ta, "why":
                              "a moved sentence needs an entry with reason reorder" if cover else "no entry covers it"})
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "redline.md").write_text(f"# Redline\n\n`{db['path']}` → `{da['path']}`. Deleted text is struck through "
                                    "(~~like this~~), inserted text is bold (**like this**).\n\n"
                                    f"{redline(db['text'].strip(), da['text'].strip())}\n", encoding="utf-8")
    state, bad = latexdiff(Path(args.before), Path(args.after), out), [e for e in checked if e["problems"]]
    summary = {"entries": len(checked), "entries_with_problems": len(bad), "changes_without_entry": len(uncovered),
               "reasons": dict(Counter(r for e in checked for r in e["reasons"]))}
    result = {"tool": TOOL, "command": "log", "level": args.level, "changes": args.changes, "summary": summary,
              "latexdiff": state, "entries": checked, "uncovered": uncovered}
    (out / "log-check.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    lines = ["# Change log check", "", f"`{args.changes}` against `{db['path']}` → `{da['path']}`, level {args.level}.", "",
             f"{len(checked)} entries, {len(bad)} with problems; {len(uncovered)} changed sentences without an entry. "
             f"Redline: redline.md. latexdiff: {state}.", ""]
    lines += table(("Entry", "Reason", "Problems"), [(e["id"], ", ".join(e["reasons"]), "; ".join(e["problems"]) or "none")
                                                     for e in checked])
    if uncovered:
        lines += ["", f"## Changes without an entry ({len(uncovered)})", ""] + table(("Where", "Why", "Before", "After"), [
            (x["where"], x["why"], x["before"], x["after"]) for x in uncovered])
    (out / "log-check.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({**summary, "latexdiff": state, "report": str(out / "log-check.md"),
                      "redline": str(out / "redline.md")}, indent=2, ensure_ascii=False))
    return 1 if bad or uncovered else 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Check a language polish against the original.")
    sub = parser.add_subparsers(dest="command", required=True)
    commands = {"survey": (cmd_survey, ("file",), "Protected-term candidates, claim words per sentence, query leads"),
                "diff": (cmd_diff, ("before", "after"), "What the polish changed that a language edit must not change"),
                "log": (cmd_log, ("before", "after", "changes"), "Check the change log; write the redline")}
    for name, (_, positional, text) in commands.items():
        p = sub.add_parser(name, help=text)
        for arg in positional:
            p.add_argument(arg)
        if name != "survey":
            p.add_argument("--level", choices=LEVELS, default="medium", help="light, medium (default) or heavy")
        if name != "log":
            p.add_argument("--protect", help="Protected terms, one per line; # starts a comment")
        if name == "diff":
            p.add_argument("--max-footprint", type=float, help="Share of changed words in a paragraph above which to warn "
                           "(default by level: light 0.2, medium 0.5, heavy 0.7)")
        p.add_argument("--out", default="polish", help="Output folder (default: polish)")
    args = parser.parse_args(argv)
    return commands[args.command][0](args)


if __name__ == "__main__":
    sys.exit(main())
