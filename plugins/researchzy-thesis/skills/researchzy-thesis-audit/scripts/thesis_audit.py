#!/usr/bin/env python3
"""Check a whole thesis for mechanical consistency before review or defence. Reports; edits nothing.

  thesis_audit.py check --audit thesis-audit/audit.json [--bib refs.bib] [--aux main.aux]
  thesis_audit.py abstracts thesis-audit/abstract-zh.txt thesis-audit/abstract-en.txt
  thesis_audit.py blind --full thesis.docx --blind thesis-blind.docx

check reads the files audit.json lists (.tex following \\input and \\include; .md, .txt; .docx with
tables, footnotes, outline levels, 标题 1 styles, SEQ and REF fields) and checks abbreviations, key
numbers, table N (writing n-ledger.csv), figure and table callouts, citations and hypotheses against
what audit.json declares; it writes report.md, report.json and the abstracts it finds. abstracts
lists numbers in one abstract and not the other (万 and 亿 multiplied out). blind lists numbers and
headings that differ between the full and the blind copy (identity words: check_anonymity.py).

Rows are pass, fail, not_checked or manual; only what is certain fails, and inferences are leads.
Output goes to --out (default thesis-audit). Exit codes: 0 nothing failed; 1 a row failed; 2 an
input could not be read or audit.json is malformed. Standard library only.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import unicodedata
import zipfile
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path
from xml.etree import ElementTree

TOOL = "researchzy-thesis-audit"
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
HAN = "\u3400-\u9fff"
CAP = 12                                        # leads shown per group; the rest are counted
TEXT_PARTS = ("abstract", "body", "appendix")   # parts whose prose is checked
# A number, CJK-aware (adapted from tr_check.py): a Han character next to it is a boundary
# (样本量为312人), a Latin letter is not (H3, 3D), and an uppercase name before a hyphen hides it.
NUMBER = re.compile(r"(?<![A-Za-z0-9_.,])(?<![A-Z][-–])(?P<sign>[-−–](?=[\d.]))?(?P<num>\d{1,3}(?:,\d{3})+(?:\.\d+)?"
                    r"|\d+(?:\.\d+)?|\.\d+)(?P<mag>\s*(?:万亿|万|亿))?(?P<pct>\s?(?:[%‰]|per\s?cent\b))?"
                    r"(?:(?<=[%‰t])|(?![A-Za-z0-9_]|[.,]\d))")
NUM_F = r"(?:\d{1,2}|[A-Z](?=\s*[-–—.]\s*\d))(?:\s*[-–—.]\s*\d{1,3})?"          # 3-4, 3.4, A-1, 5
KINDS = r"(?:(?<![附续试意地企构蓝代发列量报外仪年课时])(?P<zh>图|表)|(?<![A-Za-z])(?P<en>Fig(?:ure)?s?\.?|Tables?))"
FLOAT_CALL = re.compile(rf"{KINDS}\s*~?\s*(?P<num>{NUM_F})(?!\d)(?P<more>(?:\s*(?:[,，、]|和|与|及|以及|至|到|~|and|to|&)\s*"
                        rf"(?:图|表|Figs?\.?|Figures?|Tables?)?\s*~?\s*{NUM_F}(?!\d))*)")
CAPTION = re.compile(rf"^\s*(?:(?P<zh>图|表)|(?P<en>Figure|Fig\.|Table))\s*(?P<num>{NUM_F})(?:\s*[:.]\s*|\s+|$|(?=[{HAN}]))"
                     r"(?P<title>.*)$")
NOT_TITLE = re.compile(r"^(?:所示|显示|表明|可见|中|的|是|为|给出|列出|说明|展示|描述|反映|呈现|和|与|及|对|将|(?:shows?|presents?"
                       r"|summari[sz]es|reports?|lists?|gives?|illustrates?|displays?|describes?|is|are|was|and|in|of)\b)", re.I)
YEAR = r"(?:19|20)\d{2}[a-z]?"
SURNAME = r"(?:(?:van|von|de|der|den|du|da|di|la|le)\s+)*[A-Z][A-Za-z'’\-]+"
AY_ITEM = re.compile(rf"^\s*(?:see\s+|e\.g\.,?\s+|参见|见)?(?P<name>{SURNAME}|[{HAN}]{{1,4}}?)(?:\s*(?:et\s+al\.?|等人?"
                     rf"|(?:and|&|和|与|、)\s*(?:[A-Z][A-Za-z'’\-]+|[{HAN}]{{2,4}})))?\s*[,，]?\s*(?P<year>{YEAR})"
                     r"(?:\s*[,，:]\s*(?:pp?\.\s*)?\d+(?:[-–]\d+)?)?\s*$")
NARRATIVE_EN = re.compile(rf"(?P<name>{SURNAME})(?:\s+et\s+al\.?|\s+(?:and|&)\s+[A-Z][A-Za-z'’\-]+)?(?:'s)?\s*"
                          rf"\(\s*(?P<year>{YEAR})(?:\s*[,，:;][^()]*)?\)")
NARRATIVE_ZH = re.compile(rf"(?P<name>[{HAN}]{{2,10}}?)(?:等人?|[和与][{HAN}]{{2,4}})?\s*\(\s*(?P<year>{YEAR})\s*\)")
NOT_NAME = set("In On At The Table Figure Fig Since From Until By Before After During See Model Study Survey Data".split())
CITE_PAREN = re.compile(rf"\([^()]*{YEAR}[^()]*\)|\[\d{{1,3}}(?:\s*[-–,，]\s*\d{{1,3}})*\]")
TEX_CITE = re.compile(r"\\([A-Za-z]*cite[A-Za-z]*)\*?\s*(?:\[[^\]]*\]\s*){0,2}\{([^{}]*)\}")
PANDOC_KEY = re.compile(r"(?<![\w.@\\/])-?@([A-Za-z0-9_](?:[\w:.+/-]*\w)?)")
NUMERIC_CITE = re.compile(r"\[(\d{1,3}(?:\s*[-–,，]\s*\d{1,3})*)\]")
ABBR = r"[a-z]?[A-Z]{2,8}"
ABBR_USED = re.compile(rf"(?<![A-Za-z0-9\\-])({ABBR})s?(?![A-Za-z0-9]|-[A-Z0-9])")
DEF_SHORT = re.compile(rf"\(\s*(?:(?:以下|下文)?(?:简称|下称|即)\s*)?(?P<abbr>{ABBR})s?\s*\)")
DEF_PAIR = re.compile(rf"\(\s*(?P<long>[A-Za-z][A-Za-z'’\- ]{{3,80}}?)\s*[,，;]\s*(?:简称\s*)?(?P<abbr>{ABBR})s?\s*\)")
DEF_AFTER = re.compile(rf"(?<![A-Za-z0-9\\-])(?P<abbr>{ABBR})s?\s*\(\s*(?P<long>[{HAN}][{HAN}·]{{1,19}}|[a-z][A-Za-z'’\- ]{{4,80}}?)"
                       r"\s*\)")
ABBR_KNOWN = frozenset("DNA RNA PCR USA UK EU UN WHO FDA HIV AIDS PDF URL HTML API CPU GPU ID OK AM PM BC AD USD EUR "
                       "GBP ISO IEEE ACM NA AND OR NOT".split())       # nobody defines these (manuscript_check.py)
HYP = re.compile(r"(?<![A-Za-z0-9])H(\d{1,2})([a-z]?)(?:\s*[-–~至]\s*H?(\d{1,2})([a-z]?))?(?![A-Za-z0-9])"
                 r"|假设\s*H?(\d{1,2})([a-z]?)|Hypothes[ie]s\s+(\d{1,2})([a-z]?)")
N_LABEL = re.compile(r"^(?:N|n|样本量|样本数|有效样本(?:量|数)?|观测值数?|观测数|观察值|observations|obs\.?|sample size)$", re.I)
N_EQ = re.compile(r"(?<![A-Za-z])([Nn])\s*=\s*(\d[\d,]*)(?![\d.])")
N_WORD = re.compile(r"(?:样本量|样本数|有效样本(?:量|数)?|观测值|观测数)\s*(?:为|是|:|=)?\s*(\d[\d,]*)(?![\d.])")
PART_RE = [(part, re.compile(rf"^(?:{pattern})$", re.I)) for part, pattern in (
    ("abstract", r"(?:中文|内容)?摘要"), ("abstract_en", r"abstract|英文摘要"),
    ("abbreviations", r"(?:主要)?(?:英文)?(?:缩略语|缩略词|缩写词?|符号)(?:表|说明|对照表|注释表)?|listof(?:abbreviations|acronyms"
                      r"|symbols)|abbreviations|acronyms|nomenclature"),
    ("references", r"参考文献|references|bibliography|workscited"), ("acknowledgements", r"致谢|谢辞|鸣谢|后记|acknowledge?ments?"),
    ("toc", r"目录|目次|插图(?:清单|目录)|附?图(?:清单|目录)|表格?(?:清单|目录)|(?:table)?of?contents|listof(?:figures|tables)"),
    ("appendix", r"(?:附录|appendix|appendices)[a-z0-9一二三四五六七八九十]?.*"),
    ("back", r"(?:攻读|在读|在学).{0,14}(?:成果|论文)|个人简历|作者简介|作者简历|.*(?:原创性|独创性|版权使用|授权使用).*|声明"
             r"|curriculumvitae|declaration|publications?"))]
CHAPTER_RE = re.compile(r"^(?:第\s*(?P<zh>[0-9一二三四五六七八九十]+)\s*章|chapter\s+(?P<en>\d+)|(?P<n>\d{1,2})(?=\s|\.(?!\d)))", re.I)
GREEK = {"beta": "β", "alpha": "α", "chi": "χ", "le": "≤", "leq": "≤", "ge": "≥", "geq": "≥", "times": "×", "%": "%", "&": "&"}


class InputError(Exception):
    """An input that cannot be read: exit code 2."""


def norm(text: str) -> str:
    """NFKC (full-width digits, brackets and colons to ASCII), keeping the Chinese comma: 148，164 is two numbers."""
    return unicodedata.normalize("NFKC", text.replace("，", "\ue000")).replace("\ue000", "，")


def fold(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)).casefold()


def zh_int(word: str) -> int:
    digits = dict(zip("一二三四五六七八九", range(1, 10)))
    tens, ten, ones = word.partition("十")
    return int(word) if word.isdigit() else (digits.get(tens, 1) * 10 + digits.get(ones, 0)) if ten else digits.get(word, 0)


def numbers_in(text: str) -> list:
    out = []
    for m in NUMBER.finditer(text):
        digits = m.group("num").replace(",", "")
        shift = {"万": 4, "亿": 8, "万亿": 12}.get((m.group("mag") or "").strip(), 0)
        value = Decimal(digits).scaleb(shift)
        out.append({"value": -value if m.group("sign") else value, "places": len(digits.partition(".")[2]) - shift,
                    "pct": bool(m.group("pct")), "start": m.start(), "end": m.end(), "token": m.group(0).strip()})
    return out


def same(a: dict, b: dict) -> bool:
    """Equal at the coarser of the two precisions: 0.416 and 0.42 agree, 0.42 and 0.24 do not."""
    return a["pct"] == b["pct"] and abs(a["value"] - b["value"]) <= max(Decimal(5).scaleb(-x["places"] - 1) for x in (a, b))


def fnum(text: str) -> str:
    return re.sub(r"\s*[-–—.]\s*", "-", text.strip())


def callouts(text: str) -> list:
    """(kind, number, start, end) for 图3-4, 表3-2和表3-5, Figure 3.2, Tables 3.1 to 3.3."""
    out = []
    for m in FLOAT_CALL.finditer(text):
        items = [("fig" if (m.group("zh") or m.group("en"))[0] in "图Ff" else "tab", fnum(m.group("num")))]
        for sep, word, num in re.findall(rf"(至|到|~|to|[,，、]|和|与|及|以及|and|&)\s*(图|表|Figs?\.?|Figures?|Tables?)?\s*~?"
                                         rf"\s*({NUM_F})", m.group("more")):
            (kind, last), num = items[-1], fnum(num)
            new = ("fig" if word[0] in "图Ff" else "tab") if word else kind
            (a, _, i), (b, _, j) = last.rpartition("-"), num.rpartition("-")
            if new == kind and sep in ("至", "到", "~", "to") and a == b and i.isdigit() and j.isdigit():
                items += [(kind, f"{a}-{k}" if a else str(k)) for k in range(int(i) + 1, min(int(j), int(i) + 50) + 1)]
            else:
                items.append((new, num))
        out += [(kind, item, m.start(), m.end()) for kind, item in items]
    return out


def plain_numbers(text: str) -> list:
    """Numbers outside citations, float callouts and chapter references."""
    for pattern in (CITE_PAREN, FLOAT_CALL, re.compile(r"第\s*\d+\s*[章节]|\b(?:Chapter|Section)\s+\d+(?:\.\d+)*")):
        text = pattern.sub(lambda m: " " * len(m.group(0)), text)
    return numbers_in(text)


def has_citation(text: str) -> bool:
    return bool("[@" in text or CITE_PAREN.search(text) or NARRATIVE_EN.search(text) or NARRATIVE_ZH.search(text))


def part_of(title: str):
    key = re.sub(r"\s+", "", norm(title)).strip("：:.。").casefold()
    return next((part for part, pattern in PART_RE if pattern.match(key)), None)


def bare_heading(text: str):
    """A short paragraph that is a part name (摘 要, 参考文献) or a chapter title (第3章 研究设计)."""
    s = text.strip()
    return 1 if (len(s) <= 20 and part_of(s)) or (len(s) <= 30 and re.match(r"^第\s*[0-9一二三四五六七八九十]+\s*章(?:\s|$)", s)) else None


def caption_of(text: str, styled: bool):
    """(kind, number) of a caption: styled (题注, SEQ, \\caption), or a short typed line 图3-4 … that is no sentence."""
    m = CAPTION.match(text)
    title = m.group("title").strip() if m else ""
    if not m or (not styled and (len(title) > (150 if m.group("en") else 60) or "。" in title or NOT_TITLE.match(title))):
        return None
    return "fig" if (m.group("zh") or m.group("en"))[0] in "图F" else "tab", fnum(m.group("num"))


ROLE_PART = {"abstract": "abstract", "chapter": "body", "results": "body", "conclusion": "body", "appendix": "appendix",
             "abbreviations": "abbreviations", "references": "references", "other": "other"}
INPUT = re.compile(r"\\(?:input|include|subfile)\s*\{([^{}]+)\}|\\input\s+([^\s{}\\%]+)")
HEAD_TEX = re.compile(r"\\(chapter|section|subsection|subsubsection)(\*?)\s*(?:\[[^\]]*\])?\s*(?=\{)")
REF = re.compile(r"\\(?:ref|eqref|autoref|[cC]ref|pageref|nameref|vref)\*?\s*\{([^{}]+)\}")
AC = re.compile(r"\\(?:ac[slfp]?|acr(?:short|long|full)|[gG]ls(?:pl)?)\*?\s*\{([^{}]+)\}")
ACRO = re.compile(r"\\newacronym\s*(?:\[[^\]]*\])?\s*\{([^{}]+)\}\s*\{([^{}]+)\}\s*\{([^{}]+)\}")
NOTE = re.compile(r"^\s*(?:注|资料来源|数据来源|notes?\b|source\b)", re.I)


def record(state: dict, where, orig: str, kind: str = "text", **extra) -> dict:
    return {"file": state["file"], "path": state["path"], "role": state["role"], "where": where, "orig": orig.strip(),
            "text": norm(orig).strip(), "kind": kind, "part": state["part"], "lang": state["lang"], "chapter": state["chapter"],
            "block": state["block"], "table": None, "cites": [], "refs": [], "acs": [], "spans": [], **extra}


def on_heading(state: dict, title: str, level: int, numbered: bool = False, starred: bool = False) -> None:
    part, m = part_of(title), CHAPTER_RE.match(norm(title).strip())
    if part:
        state["part"], state["lang"] = {"abstract": ("abstract", "zh"), "abstract_en": ("abstract", "en")}.get(part, (part, None))
    elif level != 1 or starred or (state["part"] in ("front", "other") and state["role"] == "thesis" and not (m or numbered)):
        return                                   # a section, an unnumbered chapter, or a title page heading
    elif state["part"] != "appendix":
        state["counter"] = zh_int(m.group("zh") or m.group("en") or m.group("n")) if m else state["counter"] + 1
        state["part"], state["chapter"], state["lang"] = "body", str(state["counter"]), None
    state["block"] += 1


def tex_plain(text: str) -> str:
    text = re.sub(r"\\item\s*\[([^\]]*)\]", r"\1 ", re.sub(r"H_\{?(\d+[a-z]?)\}?", r"H\1", text))
    text = TEX_CITE.sub(" [@] ", re.sub(r"\\multi(?:column|row)\s*\{[^{}]*\}\s*\{[^{}]*\}|" + ACRO.pattern, " ", text))
    text = re.sub(r"\\(?:label|ref|eqref|autoref|[cC]ref|pageref|nameref|vref|ac[slfp]?|acr(?:short|long|full)|[gG]ls(?:pl)?"
                  r"|includegraphics|bibliography(?:style)?|addbibresource|cline|[vh]space|bibitem|caption|chapter|section"
                  r"|subsection|subsubsection)\*?\s*(?:\[[^\]]*\]\s*)*(?:\{[^{}]*\})?", " ", text).replace("\\\\", " ")
    text = re.sub(r"\\([A-Za-z]+|[%&,;! ])\*?(?:\[[^\]]*\])?", lambda m: GREEK.get(m.group(1), " "), text)
    return re.sub(r"[{}$^_]", "", text).replace("~", " ")       # a citation is left as [@] for has_citation()


def braced(text: str, i: int) -> str:
    """The brace group that opens at text[i], two levels deep; what there is of it when it does not close."""
    return re.match(r"\{((?:[^{}]|\{(?:[^{}]|\{[^{}]*\})*\})*)", text[i:]).group(1)


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError as exc:
        raise InputError(f"{path}: cannot be read ({exc.strerror or exc})")


def enter(state: dict, path: Path, ctx: dict) -> None:
    """A file starts: its role in audit.json sets the part it begins in."""
    state.update(file=ctx["display"](path), path=path, role=ctx["roles"].get(path, state["role"]))
    ctx["order"].append(state["file"])
    if path in ctx["roles"] and ROLE_PART.get(state["role"]):
        state["part"], state["lang"], state["block"] = ROLE_PART[state["role"]], ctx["langs"].get(path), state["block"] + 1


def read_tex(path: Path, state: dict, recs: list, ctx: dict) -> None:
    """A LaTeX file, each \\input or \\include read where it stands (the tree walk of latex_guard.py)."""
    if path in ctx["seen"]:
        return
    ctx["seen"].add(path)
    ctx.setdefault("tex_root", path.parent)
    enter(state, path, ctx)
    in_doc, floating, rows, tabular = "\\begin{document}" not in (source := read_text(path)), None, [], False
    for n, raw in enumerate(source.split("\n"), 1):
        line, where = re.sub(r"(?<!\\)%.*", "", raw), f"line {n}"
        for key, short, long in ACRO.findall(line):
            ctx["acronyms"][key.strip()] = short.strip()
            ctx["acronym_defs"].append(record(state, where, f"{short} {long}", "acronym", abbr=short.strip(), long=long.strip()))
        if not in_doc:
            in_doc = "\\begin{document}" in line
            continue
        for m in INPUT.finditer(line):
            target = (m.group(1) or m.group(2)).strip()
            found = next((base / name for base in (ctx["tex_root"], path.parent) for name in
                          ([target] if target.endswith(".tex") else [target + ".tex", target]) if (base / name).is_file()), None)
            if found is None:
                raise InputError(f"{state['file']} {where}: \\input or \\include target {target!r} does not exist")
            saved = {k: state[k] for k in ("file", "path", "role")}
            read_tex(found.resolve(), state, recs, ctx)
            state.update(saved)
        line = INPUT.sub(" ", line)
        if re.search(r"\\(?:bibliography|printbibliography)\b|\\begin\{thebibliography\}", line):
            state["part"], state["block"] = "references", state["block"] + 1
        state["part"] = "appendix" if "\\appendix" in line else state["part"]
        for begin, env in re.findall(r"\\(begin|end)\s*\{([A-Za-z]+)\*?\}", line):
            if re.fullmatch(r"c?abstract|eabstract|englishabstract|abstract[a-z]+", env):
                if begin == "begin":
                    state["saved"], state["block"] = (state["part"], state["lang"]), state["block"] + 1
                    state["part"], state["lang"] = "abstract", "en" if env.startswith("e") or env.endswith("en") else None
                else:
                    state["part"], state["lang"] = state.get("saved", ("body", None))
            elif env in ("figure", "table", "sidewaysfigure", "sidewaystable", "longtable", "wrapfigure", "wraptable"):
                if begin == "begin":
                    floating, rows = {"kind": "tab" if "tab" in env else "fig", "caption": None, "label": None}, []
                    tabular = env == "longtable"
                elif floating:
                    for r in rows if floating["kind"] == "tab" else ():
                        r["table"], r["cap"] = (floating["caption"] or {}).get("fnum"), floating["caption"]
                    floating, tabular = None, tabular and env != "longtable"
            elif env in ("tabular", "tabularx", "tabu", "array"):
                tabular, state["tabs"] = begin == "begin", state["tabs"] + (begin == "begin")
        heading, caption = HEAD_TEX.search(line), re.search(r"\\caption\s*(?:\[[^\]]*\])?\s*(?=\{)", line)
        labels = re.findall(r"\\label\s*\{([^{}]+)\}", line)
        ctx["labels"].update(dict.fromkeys(labels, where))
        extra = {"refs": REF.findall(line), "acs": [k.strip() for m in AC.findall(line) for k in m.split(",")],
                 "cites": [(name, k.strip()) for name, keys in TEX_CITE.findall(line) for k in keys.split(",") if k.strip()]}
        bibitem, text = re.search(r"\\bibitem\s*(?:\[[^\]]*\])?\s*\{([^{}]+)\}(.*)", line), tex_plain(line).strip()
        if bibitem:
            recs.append(record(state, where, tex_plain(bibitem.group(2)), "bibitem", key=bibitem.group(1).strip()))
        elif heading:
            level = ("chapter", "section", "subsection", "subsubsection").index(heading.group(1)) + 1
            on_heading(state, tex_plain(braced(line, heading.end())), level, numbered=True, starred=bool(heading.group(2)))
            recs.append(record(state, where, tex_plain(braced(line, heading.end())), "heading", level=level))
        elif caption and floating:
            key = (state["chapter"], floating["kind"])
            state["seq"][key] += 1
            floating["caption"] = record(state, where, tex_plain(braced(line, caption.end())), "caption", fkind=key[1], typed=False,
                                         fnum=f"{key[0]}-{state['seq'][key]}" if key[0] else str(state["seq"][key]), computed=True,
                                         label=floating["label"] or (labels[0] if labels else None))
            recs.append(floating["caption"])
        elif tabular and "&" in line:                       # one row per line: a & b \\
            cells = [tex_plain(c).strip() for c in re.split(r"(?<!\\)&", line.split("\\\\")[0])]
            rows.append(record(state, where, " | ".join(cells), "row", cells=cells, tbl=(path, state["tabs"]), **extra))
            recs.append(rows[-1])
        elif text or extra["cites"] or extra["refs"] or extra["acs"]:
            recs.append(record(state, where, text, "note" if floating else "text", source=raw.strip(), **extra))
            rows += [recs[-1]] if floating else []
        if floating and labels:
            floating["label"] = floating["label"] or labels[0]
            if floating["caption"] is not None and floating["caption"]["label"] is None:
                floating["caption"]["label"] = labels[0]


def read_md(path: Path, state: dict, recs: list, ctx: dict) -> None:
    enter(state, path, ctx)
    fence, table = False, 0
    for n, raw in enumerate(read_text(path).split("\n"), 1):
        where, s = f"line {n}", raw.strip()
        fence ^= s.startswith(("```", "~~~"))
        if fence or not s or s.startswith(("```", "~~~")) or re.fullmatch(r"\|?(\s*:?-{3,}:?\s*\|?)+", s):
            table = table if s else 0
            continue
        extra = {"cites": [("pandoc", k) for k in PANDOC_KEY.findall(s) if not k.lower().startswith(("fig:", "tbl:", "eq:", "sec:"))]}
        heading, image = re.match(r"^(#{1,6})\s+(.*?)\s*#*$", s), re.match(r"^!\[(.*?)\]\(", s)
        legend = re.match(r"^(?:Table)?:\s(.*)", s)
        if heading or bare_heading(s):
            title, level = (heading.group(2), len(heading.group(1))) if heading else (s, 1)
            on_heading(state, title, level, numbered=bool(CHAPTER_RE.match(norm(title))))
            recs.append(record(state, where, title, "heading", level=level))
        elif s.startswith("|"):
            table, cells = table or n, [c.strip() for c in s.strip("|").split("|")]
            recs.append(record(state, where, " | ".join(cells), "row", cells=[norm(c) for c in cells], tbl=(path, table), **extra))
        else:
            text = image.group(1) if image else legend.group(1) if legend else re.sub(r"^\[\^[^\]]+\]:\s*", "", s)
            found = caption_of(norm(text), bool(image or legend))
            recs.append(record(state, where, text, "caption", fkind=found[0], fnum=found[1], typed=True, **extra) if found else
                        record(state, where, text, "footnote" if s.startswith("[^") else "text", **extra))


def paragraph_text(p) -> tuple:
    """Visible text of a .docx paragraph (w:delText left out), field result spans (start, end, SEQ|REF|…), note ids."""
    simple = {id(t): (f.get(W + "instr", "").split() or [""])[0].upper() for f in p.iter(W + "fldSimple") for t in f.iter(W + "t")}
    out, spans, stack, notes, size = [], [], [], [], 0
    for node in p.iter():
        tag, kind = node.tag, node.get(W + "fldCharType")
        if tag in (W + "t", W + "tab", W + "br", W + "cr"):
            text = (node.text or "") if tag == W + "t" else " "
            field = simple.get(id(node)) or next(((f[0].split() or [""])[0].upper() for f in stack[::-1] if f[1] is not None), None)
            spans += [(size, size + len(text), field)] if field else []
            out.append(text)
            size += len(text)
        elif tag == W + "instrText" and stack:
            stack[-1][0] += node.text or ""
        elif tag == W + "fldChar" and kind == "begin":
            stack.append(["", None])
        elif tag == W + "fldChar" and stack and kind == "separate":
            stack[-1][1] = size
        elif tag == W + "fldChar" and stack and kind == "end":
            stack.pop()
        elif tag in (W + "footnoteReference", W + "endnoteReference"):
            notes.append(node.get(W + "id"))
    return "".join(out), spans, notes


def read_docx(path: Path, state: dict, recs: list, ctx: dict) -> None:
    try:
        with zipfile.ZipFile(path) as archive:
            parts = {n: ElementTree.fromstring(archive.read(f"word/{n}.xml")) for n in ("document", "styles", "footnotes", "endnotes")
                     if f"word/{n}.xml" in archive.namelist() or n == "document"}
    except (OSError, zipfile.BadZipFile, KeyError, ElementTree.ParseError) as exc:
        raise InputError(f"{path}: not a readable .docx file ({exc})")
    enter(state, path, ctx)
    body = parts["document"].find(W + "body")
    val = lambda node, tag: node.find(tag).get(W + "val") if node.find(tag) is not None else None              # noqa: E731
    styles = {s.get(W + "styleId"): (val(s, W + "name") or "", val(s, W + "basedOn"), val(s, f"{W}pPr/{W}outlineLvl"),
                                     s.find(f"{W}pPr/{W}numPr") is not None) for s in parts.get("styles", body).iter(W + "style")}
    note_place, count = {}, Counter()

    def blocks(parent):           # paragraphs and tables, also inside content controls (w:sdt)
        for child in parent:
            if child.tag == W + "sdt":
                yield from blocks(c for content in child.iterfind(W + "sdtContent") for c in content)
            elif child.tag in (W + "p", W + "tbl"):
                yield child

    for block in blocks(body):
        if block.tag == W + "tbl":
            count["t"] += 1
            for i, tr in enumerate(block.iter(W + "tr"), 1):
                cells = [" ".join(paragraph_text(p)[0].strip() for p in tc.iter(W + "p")).strip() for tc in tr.iter(W + "tc")]
                count["p"] += sum(1 for _ in tr.iter(W + "p"))
                recs += [record(state, f"table {count['t']}, row {i}", " | ".join(cells), "row", cells=[norm(c) for c in cells],
                                tbl=(state["file"], count["t"]))] if any(cells) else []
            continue
        count["p"] += 1
        text, spans, refs = paragraph_text(block)
        note_place.update((ref, (state["part"], state["chapter"])) for ref in refs)
        sid, level, numbered, seen = val(block, f"{W}pPr/{W}pStyle"), None, block.find(f"{W}pPr/{W}numPr") is not None, set()
        name = styles.get(sid, ("",))[0] or sid or ""
        while sid in styles and sid not in seen:
            seen.add(sid)
            level, numbered, sid = level if level is not None else styles[sid][2], numbered or styles[sid][3], styles[sid][1]
        level, named = val(block, f"{W}pPr/{W}outlineLvl") or level, re.match(r"(?i)^(?:heading|标题)\s*(\d)$", name.strip())
        level = int(level) + 1 if level is not None and int(level) < 9 else int(named.group(1)) if named else bare_heading(text)
        seq = any(k == "SEQ" for *_, k in spans)
        found = text.strip() and caption_of(norm(text), seq or "caption" in name.casefold() or "题注" in name)
        if level and text.strip() and not found:
            on_heading(state, text, level, numbered=numbered)
        found = {"fkind": found[0], "fnum": found[1], "typed": not seq} if found else {}
        recs += [record(state, f"paragraph {count['p']}", text, "caption" if found else "heading" if level else "text", spans=spans,
                        level=level, **found)] if text.strip() else []
    for name in ("footnote", "endnote"):
        for note in parts.get(f"{name}s", ElementTree.Element("x")).iter(W + name):
            text = " ".join(paragraph_text(p)[0] for p in note.iter(W + "p")).strip()
            if text and note.get(W + "type") not in ("separator", "continuationSeparator", "continuationNotice"):
                part, chapter = note_place.get(note.get(W + "id"), (state["part"], state["chapter"]))
                recs.append({**record(state, f"{name} {note.get(W + 'id')}", text, "footnote"), "part": part, "chapter": chapter})


def attach_tables(recs: list) -> None:
    """Rows of a table get the number of the caption just above (or below) it; 注：… and Note: … under it join it."""
    groups = defaultdict(list)
    for i, r in enumerate(recs):
        groups[r.get("tbl")] += [i] if r["kind"] == "row" and r["table"] is None and r.get("tbl") else []
    for rows in (v for v in groups.values() if v):
        near = [j for j in (*range(rows[0] - 1, rows[0] - 4, -1), rows[-1] + 1, rows[-1] + 2) if 0 <= j < len(recs)]
        caption = next((recs[j] for j in near if recs[j]["kind"] == "caption" and recs[j]["fkind"] == "tab"), None)
        number = caption["fnum"] if caption else f"unnumbered ({recs[rows[0]]['file']} {recs[rows[0]]['where']})"
        notes = [j for j in range(rows[-1] + 1, min(rows[-1] + 3, len(recs)))
                 if recs[j]["kind"] == "text" and NOTE.match(recs[j]["text"])]
        for j in rows + notes:
            recs[j]["table"], recs[j]["kind"] = number, recs[j]["kind"] if recs[j]["kind"] == "row" else "note"



def place(r) -> str:
    return f"{r['file']} {r['where']}"


def finding(message: str, r=None) -> dict:
    return {"message": message, **({"file": r["file"], "where": r["where"], "snippet": (r.get("source") or r["orig"])[:120]}
                                   if r else {"file": ""})}


def row(check: str, rule: str, state: str, detail: str = "", findings=()) -> dict:
    return {"check": check, "rule": rule, "status": state, "detail": detail, "findings": list(findings)}


def verdict(problems) -> str:
    return "fail" if problems else "pass"


def lead(leads: list, check: str, group: str, items: list) -> None:
    if items:
        leads.append({"check": check, "group": group, "count": len(items), "items": items[:CAP]})


def expands(abbr: str, phrase: str) -> bool:
    """Could the phrase be the long form: same first letter, the letters in order (manuscript_check.py)."""
    letters, wanted = iter(re.sub(r"[^a-z]", "", phrase.lower())), re.sub(r"[^a-z]", "", abbr.lower())
    long_enough = len(phrase.split()) >= 2 or len(phrase) > len(wanted) + 2
    return phrase[:1].lower() == wanted[:1] and all(c in letters for c in wanted) and long_enough


def long_before(text: str, start: int, abbr: str) -> tuple:
    before = text[:start].rstrip()
    han = re.search(rf"[{HAN}·]{{1,20}}$", before)
    words = re.findall(r"[A-Za-z][A-Za-z'’\-]*", before[-160:]) if before[-1:].isalpha() and not han else []
    return ("zh", han.group(0)) if han else next((("en", " ".join(words[-k:])) for k in range(1, min(len(words), len(abbr) + 3) + 1)
                                                  if expands(abbr, " ".join(words[-k:]))), (None, None))


def definitions(text: str) -> list:
    """(abbr, language, long form, start, end): 技术接受模型（TAM）, perceived usefulness (PU), TAM（技术接受模型）,
    感知有用性（Perceived Usefulness，PU）, （以下简称TAM）."""
    out, taken = [], []
    for m in DEF_PAIR.finditer(text):
        abbr, long = m.group("abbr"), m.group("long").strip()
        if expands(abbr, long):
            lang, before = long_before(text, m.start(), abbr)
            out += [(abbr, "en", long, *m.span())] + [(abbr, lang, before, *m.span())] * (lang == "zh")
            taken.append(m.start())
    for m in DEF_SHORT.finditer(text):
        lang, long = long_before(text, m.start(), m.group("abbr"))
        out += [(m.group("abbr"), lang, long, *m.span())] if long and m.start() not in taken else []
    for m in DEF_AFTER.finditer(text):
        abbr, long, lang = m.group("abbr"), m.group("long").strip(), "zh" if re.match(f"[{HAN}]", m.group("long")) else "en"
        out += [(abbr, lang, long, *m.span())] if lang == "zh" or expands(abbr, long) else []
    return out


def same_long(lang: str, a: str, b: str) -> bool:
    """English: equal after case, hyphens, plurals, -ing and doubled letters. Chinese: where the term starts is
    unknown (本文采用技术接受模型), so one must end with the other or both share the last three characters."""
    if lang == "en":
        stem = lambda w: re.sub(r"(?:ings?|ed|es|s)$", "", w) if len(w) > 4 else w                   # noqa: E731
        words = [[stem(re.sub(r"(.)\1+", r"\1", w).replace("z", "s")) for w in re.findall(r"[a-z]+", fold(s)) if w not in ("the", "a")]
                 for s in (a, b)]
        return words[0] == words[1]
    forms = lambda s: [s] + [s[:-len(t)] for t in ("方法", "模型", "分析", "法") if s.endswith(t) and len(s) > len(t) + 1][:1]  # noqa: E731
    tail = lambda x, y: next((k for k in range(min(len(x), len(y)), 0, -1) if x[-k:] == y[-k:]), 0)        # noqa: E731
    return any(x.endswith(y) or y.endswith(x) or tail(x, y) >= 3 for x in forms(a) for y in forms(b))


def list_entry(r: dict):
    """An entry of the list of abbreviations: a table row or a line that starts with the abbreviation."""
    m = re.match(rf"^\s*({ABBR})s?\s*(?::|\t|—|–|-|\s)\s*(.+)$", r["text"]) if r["kind"] != "row" else None
    head, rest = (r["cells"][0].strip(), " ".join(r["cells"][1:])) if r["kind"] == "row" else m.groups() if m else ("", "")
    zh, en = re.search(rf"[{HAN}][{HAN}·]*", rest), re.findall(r"[A-Za-z][A-Za-z'’\-]*(?:\s+[A-Za-z][A-Za-z'’\-]*)+", rest)
    return (head, [("zh", zh.group(0))] * bool(zh) + [("en", max(en, key=len))] * bool(en)) if re.fullmatch(ABBR, head) else None


def check_abbreviations(recs: list, ctx: dict, convention) -> tuple:
    defs, uses, listed, rows, leads = defaultdict(list), defaultdict(list), {}, [], []
    for i, r in enumerate(recs):
        entry = list_entry(r) if r["part"] == "abbreviations" and r["kind"] in ("row", "text") else None
        if entry:
            listed.setdefault(entry[0], r)
            defs[entry[0]] += [(lang, long, r, "list", i) for lang, long in entry[1]]
        if r["part"] not in TEXT_PARTS or r["kind"] not in ("text", "footnote", "note", "caption", "row", "heading"):
            continue
        scope, text = (f"abstract-{r['lang']}" if r["part"] == "abstract" else "body"), r["text"]
        for abbr, lang, long, a, b in definitions(text):
            defs[abbr].append((lang, long, r, scope, i))
            text = text[:a] + " " * (b - a) + text[b:]
        for abbr in [m.group(1) for m in ABBR_USED.finditer(text)] + [ctx["acronyms"].get(k, k) for k in r["acs"]]:
            uses[abbr].append((r, i, scope))
    for d in ctx["acronym_defs"]:
        listed.setdefault(d["abbr"], d)
        defs[d["abbr"]].append(("zh" if re.search(f"[{HAN}]", d["long"]) else "en", d["long"], d, "list", -1))
    conflicts = []
    for abbr, lang in ((abbr, lang) for abbr in sorted(defs) for lang in ("zh", "en")):
        clusters = []
        for long, r in [(long, r) for language, long, r, _, _ in defs[abbr] if language == lang]:
            home = next((c for c in clusters if same_long(lang, c[0][0], long)), None)
            home.append((long, r)) if home else clusters.append([(long, r)])
        if len(clusters) > 1:
            conflicts.append(finding(f"{abbr} has {len(clusters)} {'Chinese' if lang == 'zh' else 'English'} long forms: "
                                     + "; ".join(f"{c[0][0]} ({place(c[0][1])})" for c in clusters), clusters[1][0][1]))
    rows.append(row("abbreviations", "one long form per abbreviation", verdict(conflicts) if defs else "not_checked",
                    f"{len(defs)} abbreviations with a definition" if defs else "no definition was recognised", conflicts))
    body_defs = {a for a, items in defs.items() if any(s == "body" for *_, s, _ in items)}
    used = {a for a, items in uses.items() if any(s == "body" for _, _, s in items)} | body_defs
    problems = [finding(f"{a} is in the list of abbreviations and never used in the text", listed[a])
                for a in sorted(set(listed) - used)]
    problems += [finding(f"{a} is defined in the text and missing from the list of abbreviations",
                         next(r for _, _, r, s, _ in defs[a] if s == "body")) for a in sorted(body_defs - set(listed))]
    rows.append(row("abbreviations", "list of abbreviations against the text", verdict(problems) if listed else "not_checked",
                    f"{len(listed)} entries in the list" if listed else "no list of abbreviations (缩略语表, List of Abbreviations, "
                    "\\newacronym) was found", problems if listed else ()))
    lead(leads, "abbreviations", "used two or more times and never defined", [
        f"{a}: used {len(body)} times, first at {place(body[0][0])}" + ("; defined only in an abstract" if a in defs else "")
        for a, body in sorted((a, [x for x in items if x[2] == "body"]) for a, items in uses.items())
        if len(body) >= 2 and a not in set(listed) | body_defs | ABBR_KNOWN and not re.fullmatch(r"[IVXLC]+", a)])
    if convention not in ("once", "per_chapter"):
        return rows + [row("abbreviations", "definitions under the convention", "not_checked", "no convention in audit.json")], leads
    twice, early = [], []
    for abbr in sorted(body_defs):
        at = sorted({i for *_, s, i in defs[abbr] if s == "body"})
        seen, per = sorted(i for _, i, s in uses.get(abbr, []) if s == "body"), Counter(recs[i]["chapter"] for i in at)
        if convention == "once":
            twice += [f"{abbr}: defined {len(at)} times ({', '.join(place(recs[i]) for i in at[:4])})"] if len(at) > 1 else []
            early += [f"{abbr}: used at {place(recs[seen[0]])} before its definition at {place(recs[at[0]])}"] \
                if seen and seen[0] < at[0] else []
        else:
            twice += [f"{abbr}: defined {n} times in chapter {c}" for c, n in sorted(per.items(), key=str) if n > 1]
            early += [f"{abbr}: used in chapter {c} without a definition there"
                      for c in sorted({recs[i]["chapter"] for i in seen} - set(per), key=str)]
    lead(leads, "abbreviations", f"defined again under the convention \"{convention}\"", twice)
    lead(leads, "abbreviations", "used before or without a definition under the convention", early)
    return rows, leads


LOCATION = re.compile(r"^(?:(?P<abs>abstract(?:-(?:zh|en))?)|chapter\s+(?P<ch>[0-9A-Za-z]+)(?P<text>\s+text)?"
                      r"|(?P<fk>table|figure)\s+(?P<fn>\S+)|(?P<role>results|conclusion))$", re.I)


def scope_of(recs: list, loc: str, resolve) -> list:
    m = LOCATION.match(str(loc).strip())
    if not m and resolve(loc) is None:
        raise InputError(f"audit.json: {loc!r} is neither a place (abstract-zh, chapter 3, chapter 3 text, table 3-2, results, "
                         "conclusion) nor a file")
    if not m:
        return [r for r in recs if r["path"] == resolve(loc)]
    if m["abs"]:
        return [r for r in recs if r["part"] == "abstract" and r["lang"] == (m["abs"][9:] or r["lang"])]
    if m["ch"]:
        kinds = ("text", "footnote") if m["text"] else ("text", "footnote", "note", "caption", "row", "heading")
        return [r for r in recs if r["part"] == "body" and str(r["chapter"]) == m["ch"].upper() and r["kind"] in kinds]
    if m["fk"]:
        kind, number = ("tab" if m["fk"].lower() == "table" else "fig"), fnum(m["fn"])
        return [r for r in recs if (kind == "tab" and r["table"] == number) or (r["kind"] == "caption" and r["fnum"] == number
                                                                                and r["fkind"] == kind)]
    return [r for r in recs if r["role"] == m["role"].lower() and r["part"] in TEXT_PARTS]


def labelled(r: dict, labels: list, value: dict) -> list:
    """Numbers next to a label (样本量为321人, 312 valid responses), outside sentences that cite a study."""
    out, text = [], r["text"]
    numbers, ends = plain_numbers(text), [0, len(text)] + [m.end() for m in re.finditer(r"[。！？!?;；]|\.(?=\s|$)", text)]
    for m in (m for label in labels for m in re.finditer(re.escape(norm(label)), text, re.I)):
        start, stop = max(e for e in ends if e <= m.start()), min(e for e in ends if e >= m.end())
        after = [n for n in numbers if m.end() <= n["start"] <= m.end() + 12 and n["end"] <= stop]
        before = [n for n in numbers if m.start() - 12 <= n["end"] <= m.start() and n["start"] >= start]
        pick = after[0] if after else before[-1] if before else None
        out += [pick] if pick and pick["pct"] == value["pct"] and not has_citation(text[start:stop]) else []
    return out


def check_key_numbers(recs: list, declared: list, resolve) -> tuple:
    rows, leads = [], []
    for k in declared or []:
        found = numbers_in(norm(str(k.get("value"))))
        if len(found) != 1:
            raise InputError(f"audit.json: {k.get('value')!r} is not one number")
        value = found[0]
        for loc in k.get("appears_in") or []:
            name, scope = f"{k.get('id', '')} {k['value']} ({k.get('meaning', '')}) in {loc}".strip(), scope_of(recs, loc, resolve)
            hits = [r for r in scope if any(same(n, value) for n in plain_numbers(r["text"]))]
            near = [(r, n) for r in scope for n in labelled(r, k.get("labels") or [], value) if not same(n, value)]
            listed = [f"{n['token']} ({place(r)})" for r, n in near]
            if hits:
                rows.append(row("key_numbers", name, "pass", f"found at {place(hits[0])}"))
                lead(leads, "key_numbers", f"{name}: another value next to a label", listed)
            else:
                rows.append(row("key_numbers", name, "fail", ("not found" if scope else f"nothing was read at {loc}")
                                + ("; next to a label: " + ", ".join(listed) if near else ""),
                                [finding(f"{n['token']} next to a label where {k['value']} was declared", r) for r, n in near]))
    return rows or [row("key_numbers", "declared numbers", "not_checked", "audit.json declares no key numbers")], leads


def check_table_n(recs: list, declared: list) -> tuple:
    """Every N of every table into the ledger; n, and N values adding up to the table's largest N, are subgroups."""
    tables, ledger, rows, by_value = defaultdict(list), [], [], defaultdict(list)
    for r in recs:
        if (r["table"] and r["kind"] in ("row", "note")) or (r["kind"] == "caption" and r["fkind"] == "tab" and r["fnum"]):
            tables[r["table"] or r["fnum"]].append(r)
    for tid, items in tables.items():
        found = []
        for r in items:
            cells, cited = r.get("cells") or [r["text"]], has_citation(r["text"])
            if r["kind"] == "row" and N_LABEL.match(cells[0].strip()):
                found += [("n" if cells[0].strip() == "n" else "N", n["value"], r, "N row", cited)
                          for cell in cells[1:] for n in numbers_in(cell) if not n["places"] and not n["pct"]]
            else:
                found += [(m.group(1), Decimal(m.group(2).replace(",", "")), r, "N =", cited) for c in cells for m in N_EQ.finditer(c)]
                found += [("N", Decimal(m.group(1).replace(",", "")), r, "text", cited) for c in cells for m in N_WORD.finditer(c)]
        big = [v for kind, v, _, _, cited in found if kind == "N" and not cited]
        top, parts = max(big, default=None), [v for v in dict.fromkeys(big) if v != max(big)]
        for kind, value, r, source, cited in found:
            kind = "cited study" if cited else "subgroup" if kind == "n" or (parts and sum(parts) == top and value != top) else kind
            ledger.append({"table": tid, "file": r["file"], "where": r["where"], "kind": kind, "value": int(value), "source": source,
                           "note": f"subgroups add up to {top}" if kind == "subgroup" and top else ""})
            by_value[int(value)] += [tid] if kind == "N" else []
    for d in declared or []:
        tid, allowed = fnum(str(d.get("table", ""))), d.get("n") if isinstance(d.get("n"), list) else [d.get("n")]
        ns, rule = [e for e in ledger if e["table"] == tid and e["kind"] == "N"], f"N of table {tid}"
        bad, wanted = [e for e in ns if e["value"] not in allowed], ", ".join(map(str, allowed))
        if bad:
            rows.append(row("table_n", rule, "fail", f"N = {', '.join(str(e['value']) for e in bad)}; declared {wanted}",
                            [finding(f"N = {e['value']}", next(r for r in tables[tid] if r["where"] == e["where"])) for e in bad]))
        elif ns or any(n["value"] in allowed for r in tables.get(tid, []) for n in numbers_in(r["text"])):
            rows.append(row("table_n", rule, "pass", "the N row agrees" if ns else "no N row; the value is in the table"))
        else:
            rows.append(row("table_n", rule, "fail", f"{wanted} not in the table" if tid in tables else "no such table"))
    distinct, leads = {v: ", ".join(dict.fromkeys(t)) for v, t in sorted(by_value.items(), reverse=True) if t}, []
    lead(leads, "table_n", "tables report different N (state the exclusion, or correct)",
         [f"N = {v}: table {t}" for v, t in distinct.items()] if len(distinct) > 1 else [])
    return rows or [row("table_n", "declared N of tables", "not_checked", "audit.json declares no table N")], leads, ledger


FLOAT_NAMES = {"fig": ("图", "Figure ", "figure"), "tab": ("表", "Table ", "table")}


def check_floats(recs: list, ctx: dict) -> tuple:
    caps = [r for r in recs if r["kind"] == "caption" and r["part"] in TEXT_PARTS]
    if not caps:
        return [row("floats", "figures and tables", "not_checked", "no figure or table caption was recognised")], []
    calls, refs, leads, unsure, uncited = [], set(), [], [], []
    for r in (r for r in recs if r["part"] in TEXT_PARTS and r["kind"] in ("text", "footnote", "note", "row")):
        refs.update(r["refs"])
        calls += [(k, n, r, any(s < b and a < e and t == "REF" for s, e, t in r["spans"])) for k, n, a, b in callouts(r["text"])]
    exists, guessed = {(c["fkind"], c["fnum"]) for c in caps}, {c["fkind"] for c in caps if c.get("computed")}
    labels = set(ctx["labels"]) | {c["label"] for c in caps if c.get("label")}
    missing = [finding(f"\\ref{{{key}}}: no such label", r) for r in recs for key in r["refs"] if key not in labels]
    for kind, number, r, _ in (c for c in calls if (c[0], c[1]) not in exists):
        name = FLOAT_NAMES[kind][0 if re.search(f"[{HAN}]", r["text"]) else 1] + number
        if kind in guessed:
            unsure.append(f"{name} at {place(r)}")
        else:
            missing.append(finding(f"{name} is called but no caption has that number", r))
    called = {(k, n) for k, n, _, _ in calls}
    for c in (c for c in caps if (c["fkind"], c["fnum"]) not in called and not (c.get("label") and c["label"] in refs)):
        name = f"{FLOAT_NAMES[c['fkind']][2]} {c['fnum'] or c.get('label')}"
        if c.get("computed") and any(k == c["fkind"] for k, *_ in calls):
            unsure.append(f"{name} (numbered by counting, no .aux): {c['orig'][:60]}")
        else:
            uncited.append(finding(f"{name} is never called in the text", c))
    counted = Counter((c["fkind"], c["fnum"]) for c in caps if not c.get("computed") and c["fnum"])
    twice = [finding(f"{FLOAT_NAMES[k][2]} {n} has {count} captions", next(c for c in caps if (c["fkind"], c["fnum"]) == (k, n)))
             for (k, n), count in counted.items() if count > 1]
    series = defaultdict(set)
    for c in caps:
        pre, _, i = (c["fnum"] or "").rpartition("-")
        series[(c["fkind"], pre)] |= {int(i)} if i.isdigit() else set()
    lead(leads, "floats", "gaps in the numbering", [f"{FLOAT_NAMES[k][2]} {pre + '-' if pre else ''}{i} is missing"
                                                    for (k, pre), have in sorted(series.items()) for i in range(1, max(have or {1}))
                                                    if i not in have])
    lead(leads, "floats", "callouts and floats that depend on counted numbers (run with --aux)", unsure)
    lead(leads, "floats", "numbers typed by hand in .docx, not made by a SEQ or REF field",
         [f"caption {c['orig'][:40]} ({place(c)})" for c in caps if c["path"].suffix == ".docx" and c["typed"]]
         + [f"callout {FLOAT_NAMES[k][0]}{n} ({place(r)})" for k, n, r, field in calls if r["path"].suffix == ".docx" and not field])
    return [row("floats", "every callout has its figure or table", verdict(missing), f"{len(calls) + len(refs)} callouts", missing),
            row("floats", "every figure and table is called", verdict(uncited), f"{len(caps)} captions", uncited),
            row("floats", "no number twice", verdict(twice), "", twice)], leads


def read_bib(path: Path) -> dict:
    text, entries = read_text(path), {}
    starts = [m for m in re.finditer(r"@(\w+)\s*\{\s*([^,\s{}]+)\s*,", text)
              if m.group(1).lower() not in ("comment", "string", "preamble")]
    for m, nxt in zip(starts, starts[1:] + [None]):
        block = text[m.end(): nxt.start() if nxt else len(text)]
        author = re.search(r"\b(?:author|editor)\s*=\s*(\{(?:[^{}]|\{[^{}]*\})*\}|\"[^\"]*\")", block, re.I)
        year = re.search(r"\b(?:year|date)\s*=\s*[{\"]?\s*(\d{4}[a-z]?)", block, re.I)
        first = re.split(r"\s+and\s+", re.sub(r"[{}\"]", "", author.group(1)))[0] if author else ""
        entries[m.group(2)] = {"name": first.split(",")[0].strip(), "year": year.group(1) if year else "", "num": None,
                               "key": m.group(2), "place": f"{path.name} line {text.count(chr(10), 0, m.start()) + 1}"}
    return entries


def entry_of(text: str, where: str, key=None) -> dict:
    num = re.match(r"^\s*(?:\[(\d{1,3})\]|(\d{1,3})[.、)]\s)", text)
    body = text[num.end():].strip() if num else text.strip()
    year, han = re.search(rf"(?<!\d)({YEAR})(?!\d)", body), re.match(rf"[{HAN}·]+", body)
    return {"num": int(num.group(1) or num.group(2)) if num else None, "key": key, "place": where,
            "year": year.group(1) if year else "", "name": han.group(0) if han else re.split(r"[,.(]", body, maxsplit=1)[0].strip()}


def author_year(text: str) -> list:
    items = (AY_ITEM.match(item) for m in re.finditer(r"\(([^()]{4,240})\)", text) for item in re.split(r"[;；]", m.group(1)))
    out = [(a.group("name"), a.group("year")) for a in items if a and a.group("name") not in NOT_NAME]
    out += [(m.group("name"), m.group("year")) for m in NARRATIVE_EN.finditer(text) if m.group("name") not in NOT_NAME]
    return out + [(m.group("name"), m.group("year")) for m in NARRATIVE_ZH.finditer(text)]


def name_match(cited: str, listed: str) -> bool:
    if re.search(f"[{HAN}]", cited):
        return bool(listed) and (cited.endswith(listed) or (len(cited) == 1 and listed.startswith(cited)))
    return fold(cited).split()[-1] in {w for w in re.findall(r"[a-z'’\-]+", fold(listed)) if len(w) > 1}


def check_citations(recs: list, ctx: dict, bib: dict, aux_cites: set) -> tuple:
    rows, leads, keys, nocite, close, problems, matched = [], [], defaultdict(list), set(), [], [], set()
    for name, key, r in ((name, key, r) for r in recs for name, key in r["cites"]):
        keys[key].append(r) if name != "nocite" else nocite.add(key)
    items = {r["key"]: entry_of(r["text"], place(r), r["key"]) for r in recs if r["kind"] == "bibitem"}
    typed = [entry_of(r["text"], place(r)) for r in recs
             if r["part"] == "references" and r["kind"] in ("text", "row") and r["path"].suffix != ".tex"]
    numbered, plain = [e for e in typed if e["num"] is not None], [e for e in typed if e["num"] is None and e["year"]]
    texts = [r for r in recs if r["part"] in TEXT_PARTS and r["kind"] in ("text", "footnote", "note", "row", "caption")]
    known = set(bib) | set(items)
    pool = [*bib.values(), *items.values(), *plain]
    if keys:
        missing = [finding(f"{k} is cited but not in the .bib or \\bibitem list", rs[0]) for k, rs in keys.items() if k not in known]
        rows.append(row("citations", "cited keys are in the list", verdict(missing) if known else "not_checked",
                        f"{len(keys)} keys" if known else "keys are cited but no .bib (--bib) or \\bibitem list was given", missing))
    cites = [(name, year, r) for r in texts for name, year in author_year(r["text"])]
    for name, year, r in cites:
        same_name = [e for e in pool if name_match(name, e["name"]) and e["year"][:4].isdigit()]
        hits = [e for e in same_name if e["year"][:4] == year[:4] and len({year[4:], e["year"][4:]} - {""}) < 2]
        matched.update(id(e) for e in hits)
        problems += [] if hits else [finding(f"{name} {year}: no entry with this surname and year in the list", r)]
        close += [f"{name} {year} ({place(r)}): {e['name']} {e['year']} ({e['place']})" for e in same_name
                  if not hits and abs(int(e["year"][:4]) - int(year[:4])) == 1]
    printed = set(items) or ({k for k in bib if "*" in nocite} | ((nocite | aux_cites | set(keys)) & set(bib)))
    uncited = [finding(f"{k} is in the reference list and never cited in the text") for k in sorted(printed - set(keys))
               if not any(id(e) in matched for e in (bib.get(k), items.get(k)) if e)]
    uncited += [finding(f"{e['name']} {e['year']} ({e['place']}) is in the reference list and never cited")
                for e in plain if id(e) not in matched]
    if cites:
        rows.append(row("citations", "author-year citations have an entry", verdict(problems) if pool else "not_checked",
                        f"{len(cites)} author-year citations" if pool else "no list with authors and years was found", problems))
        lead(leads, "citations", "the same surname, one year apart", close)
    spans = [re.findall(r"(\d+)(\s*[-–]\s*(\d+))?", m.group(1)) for r in texts for m in NUMERIC_CITE.finditer(r["text"])]
    numbers = {x for found in spans for a, _, b in found for x in (range(int(a), min(int(b), int(a) + 100) + 1) if b else [int(a)])}
    if numbered:
        listed = {e["num"] for e in numbered}
        gaps = [finding(f"[{n}] is cited but the list has no entry {n}") for n in sorted(numbers - listed)]
        gaps += [finding(f"entry [{n}] is never cited") for n in sorted(listed - numbers)]
        rows.append(row("citations", "numbered citations against the numbered list", verdict(gaps) if numbers else "not_checked",
                        f"{len(listed)} entries" if numbers else "no [n] citation was found", gaps if numbers else ()))
    if keys or plain or items:
        rows.append(row("citations", "every entry in the list is cited", verdict(uncited), f"{len(printed) + len(plain)} entries"
                        + (f"; {len(set(bib) - printed)} .bib entries are not printed (never cited)" if bib else ""), uncited))
    return rows or [row("citations", "citations", "not_checked", "no citation or reference list was recognised")], leads


def hypotheses(text: str) -> set:
    out = set()
    for m in HYP.finditer(text):
        n, s, n2, s2 = m.group(1, 2, 3, 4) if m.group(1) else (*(m.group(5, 6) if m.group(5) else m.group(7, 8)), None, None)
        if n2 and s and s2 and n == n2:
            out |= {f"H{int(n)}{chr(c)}" for c in range(ord(s), ord(s2) + 1)}
        elif n2 and not s and not s2:
            out |= {f"H{i}" for i in range(int(n), min(int(n2), int(n) + 20) + 1)}
        else:
            out |= {f"H{int(n)}{s}"} | ({f"H{int(n2)}{s2}"} if n2 else set())
    return {h for h in out if not h.startswith("H0")}


def check_hypotheses(recs: list, declared, resolve) -> list:
    if not declared or not declared.get("labels"):
        return [row("hypotheses", "declared hypotheses", "not_checked", "audit.json declares no hypotheses")]
    labels, rows = [next(iter(hypotheses(norm(str(x)))), str(x)) for x in declared["labels"]], []
    covers = lambda found, label: label in found or any(f.startswith(label) and f[len(label):].isalpha() for f in found)  # noqa: E731
    for side in ("results", "conclusion"):
        scope = [r for loc in declared.get(side) or [side] for r in scope_of(recs, loc, resolve)]
        found = set().union(*(hypotheses(r["text"]) for r in scope))
        rows += [row("hypotheses", f"{label} in the {side}", verdict(not covers(found, label)) if scope else "not_checked",
                     ("found" if covers(found, label) else "not mentioned") if scope else f"nothing was read at {side}")
                 for label in labels]
        extra = sorted(f for f in found if f not in labels and not any(x.startswith(f) and x[len(f):].isalpha() for x in labels))
        if side == "results":
            rows.append(row("hypotheses", "no undeclared hypothesis in the results", verdict(extra), ", ".join(extra),
                            [finding(f"{f} appears in the results and is not a declared hypothesis",
                                     next(r for r in scope if f in hypotheses(r["text"]))) for f in extra]))
    return rows



def read_aux(path: Path, labels: dict, cites: set) -> None:
    """Printed numbers of labels (\\newlabel) and cited keys (\\citation), following \\@input."""
    text = read_text(path)
    for key, number in re.findall(r"\\newlabel\{([^{}]+)\}\{\{((?:[^{}]|\{[^{}]*\})*)\}", text):
        labels[key] = re.sub(r"\\[A-Za-z@]+\s*|[{}]", "", number).strip()
    cites.update(k.strip() for keys in re.findall(r"\\citation\{([^{}]+)\}", text) for k in keys.split(","))
    for name in re.findall(r"\\@input\{([^{}]+)\}", text):
        if (path.parent / name).is_file() and path.parent / name != path:
            read_aux(path.parent / name, labels, cites)


def load(files: list, roles: dict, langs: dict) -> tuple:
    """Read the files in order; a file reached through \\input or \\include is read where it is included."""
    cwd = Path.cwd()
    ctx = {"display": lambda p: p.relative_to(cwd).as_posix() if p.is_relative_to(cwd) else str(p), "roles": roles, "langs": langs,
           "seen": set(), "order": [], "labels": {}, "acronyms": {}, "acronym_defs": []}
    state, recs = {"part": "front", "lang": None, "chapter": None, "counter": 0, "block": 0, "seq": Counter(), "tabs": 0}, []
    for path in files:
        reader = {".tex": read_tex, ".md": read_md, ".markdown": read_md, ".txt": read_md, ".docx": read_docx}.get(path.suffix.lower())
        if reader is None:
            raise InputError(f"{path}: give .tex, .md, .txt or .docx (compare the source files of a PDF)")
        if path not in ctx["seen"]:
            state["role"] = roles.get(path, "thesis")
            reader(path, state, recs, ctx)
            ctx["seen"].add(path)
    for r in (r for r in recs if r["part"] == "abstract" and r["lang"] is None):   # \begin{abstract}: language by script
        r["lang"] = "zh" if len(re.findall(f"[{HAN}]", r["text"])) > 0.3 * len(re.findall(r"[^\W\d_]", r["text"])) else "en"
    attach_tables(recs)
    return recs, ctx


def finish(out: Path, name: str, files: list, rows: list, leads: list, extra: dict) -> int:
    out.mkdir(parents=True, exist_ok=True)
    cell, counts = (lambda v: " ".join(str(v).split()).replace("|", "\\|")), Counter(r["status"] for r in rows)
    lines = [f"# Thesis audit: {name}", "", "Read in this order: " + ", ".join(files) + ". Nothing was changed in any file.", "",
             f"{counts['fail']} failed, {counts['pass']} passed, {counts['not_checked']} not checked, {counts['manual']} for a "
             "person to look at. Not checked is never a pass. Leads are inferences: they never fail a check.", "",
             "| Check | Rule | Status | Detail |", "|---|---|---|---|"]
    lines += [f"| {r['check']} | {cell(r['rule'])} | {r['status']} | {cell(r['detail'])} |" for r in rows]
    for r in (r for r in rows if r["findings"] and r["status"] in ("fail", "manual")):
        lines += ["", f"## {r['status']}: {r['check']}, {r['rule']}", ""] + [f"- {f['message']}" + (
            f" ({f['file']} {f['where']}): {cell(f['snippet'])}" if f["file"] else "") for f in r["findings"]]
    for g in leads:
        lines += ["", f"## Lead: {g['check']}, {g['group']} ({g['count']})", ""] + [f"- {cell(x)}" for x in g["items"]] + (
            [f"- and {g['count'] - len(g['items'])} more"] if g["count"] > len(g["items"]) else [])
    (out / f"{name}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    summary = {"tool": TOOL, "command": name, "ok": not counts["fail"], "counts": dict(counts), "report": str(out / f"{name}.md"),
               "rows": [{k: r[k] for k in ("check", "rule", "status", "detail")} for r in rows],
               "leads": [{k: g[k] for k in ("check", "group", "count")} for g in leads]}
    print(json.dumps({**summary, **extra}, indent=2, ensure_ascii=False))
    return 1 if counts["fail"] else 0


def cmd_check(args) -> int:
    audit_path, out, labels, aux_cites, bib = Path(args.audit), Path(args.out), {}, set(), {}
    try:
        audit = json.loads(audit_path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise InputError(f"{audit_path}: cannot be read as JSON ({exc})")
    if not isinstance(audit, dict) or not isinstance(audit.get("files"), list) or not audit["files"]:
        raise InputError("audit.json needs a \"files\" list in reading order")

    def resolve(name):
        return next((p.resolve() for p in (Path(name), audit_path.parent / name) if p.is_file()), None)

    entries = {resolve(str(e.get("path", ""))): e for e in (e if isinstance(e, dict) else {"path": e} for e in audit["files"])}
    if None in entries:
        raise InputError(f"audit.json: file not found: {entries[None].get('path')}")
    roles, langs = ({p: e.get(key, default) for p, e in entries.items()} for key, default in (("role", "thesis"), ("language", None)))
    recs, ctx = load(list(entries), roles, langs)
    if args.aux:
        read_aux(Path(args.aux), labels, aux_cites)
    for r in (r for r in recs if r.get("label") in labels):
        r["fnum"], r["computed"] = fnum(labels[r["label"]]), False
    for r in (r for r in recs if r.get("cap")):
        r["table"] = r["cap"]["fnum"]
    for name in args.bib or []:
        bib.update(read_bib(Path(name)))
    results = [check_abbreviations(recs, ctx, (audit.get("abbreviations") or {}).get("convention")),
               check_key_numbers(recs, audit.get("key_numbers"), resolve), check_table_n(recs, audit.get("table_n")),
               check_floats(recs, ctx), check_citations(recs, ctx, bib, aux_cites)]
    rows = [r for result in results for r in result[0]] + check_hypotheses(recs, audit.get("hypotheses"), resolve)
    leads, written = [g for result in results for g in result[1]], []
    out.mkdir(parents=True, exist_ok=True)
    with (out / "n-ledger.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["table", "file", "where", "kind", "value", "source", "note"])
        writer.writeheader()
        writer.writerows(results[2][2])
    for lang in ("zh", "en"):
        text = "\n".join(r["orig"] for r in recs if r["part"] == "abstract" and r["lang"] == lang and r["kind"] != "heading")
        if text:
            written.append(str(out / f"abstract-{lang}.txt"))
            Path(written[-1]).write_text(text + "\n", encoding="utf-8")
    (out / "report.json").write_text(json.dumps({"tool": TOOL, "files": ctx["order"], "rows": rows, "leads": leads}, indent=2,
                                                ensure_ascii=False), encoding="utf-8")
    return finish(out, "report", ctx["order"], rows, leads, {"abstracts_written": written, "n_ledger": str(out / "n-ledger.csv")})


def cmd_abstracts(args) -> int:
    keep = lambda n: n["pct"] or n["places"] or abs(n["value"]) >= 10                                   # noqa: E731
    numbers = [[(n, r) for r in load([Path(p).resolve()], {}, {})[0] for n in plain_numbers(r["text"]) if keep(n)]
               for p in (args.first, args.second)]
    rows = [row("abstracts", f"numbers of {name_a} in {name_b}", verdict(lonely), f"{len(numbers[a])} numbers", lonely)
            for a, b, name_a, name_b in ((0, 1, args.first, args.second), (1, 0, args.second, args.first))
            for lonely in [[finding(f"{n['token']} is in {name_a} and not in {name_b}", r) for n, r in numbers[a]
                            if not any(same(n, m) for m, _ in numbers[b])]]]
    return finish(Path(args.out), "abstracts", [args.first, args.second], rows, [], {})


def cmd_blind(args) -> int:
    """Numbers and headings, section by section: a section is the text under one heading."""
    def sections(path):
        out, head, seen = defaultdict(list), "(before the first heading)", Counter()
        for r in load([Path(path).resolve()], {}, {})[0]:
            seen[r["text"]] += r["kind"] == "heading"
            head = " ".join(r["text"].split()) + f" ({seen[r['text']]})" * (seen[r["text"]] > 1) if r["kind"] == "heading" else head
            out[head].append(r)
        return out

    full, blind = sections(args.full), sections(args.blind)

    def numbers(rs):
        return Counter(f"{n['value'].normalize()}{'%' * n['pct']}" for r in rs for n in numbers_in(r["text"]))

    headings = [finding(f"heading only in the blind copy: {h}", blind[h][0]) for h in blind if h not in full]
    changed, removed, expected = [], [], []
    for head, items in full.items():
        identity = part_of(head) in ("acknowledgements", "back") or items[0]["part"] in ("acknowledgements", "back")
        if head not in blind:
            expected += [head] if identity else []
            headings += [] if identity else [finding(f"heading missing from the blind copy: {head}", items[0])]
            continue
        a, b = numbers(items), numbers(blind[head])
        where = next((r for r in blind[head] if numbers([r]) - a), blind[head][0])
        changed += [finding(f"{head}: full copy {', '.join(a - b) or '-'} -> blind copy {', '.join(b - a)}", where)] if b - a else []
        removed += [finding(f"{head}: only in the full copy: {', '.join(a - b)}", items[0])] if a - b and not b - a else []
    rows = [row("blind", "numbers agree with the full copy", verdict(changed), f"{len(full)} and {len(blind)} sections", changed),
            row("blind", "headings agree with the full copy", verdict(headings), "", headings),
            row("blind", "numbers removed in the blind copy (confirm each only identifies)", "manual" if removed else "pass",
                "", removed)]
    leads = []
    lead(leads, "blind", "identity sections removed", expected)
    return finish(Path(args.out), "blind", [args.full, args.blind], rows, leads, {})


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Mechanical consistency checks for a whole thesis.")
    sub = parser.add_subparsers(dest="command", required=True)
    check, abstracts, blind = (sub.add_parser(name, help=text) for name, text in (
        ("check", "abbreviations, key numbers, table N, floats, citations, hypotheses"),
        ("abstracts", "numbers in one abstract and not in the other"), ("blind", "numbers and headings: full against blind copy")))
    check.add_argument("--audit", required=True, help="thesis-audit/audit.json")
    check.add_argument("--bib", action="append", help="a .bib file (repeat for several)")
    check.add_argument("--aux", help="main.aux of the built LaTeX thesis: printed float numbers and cited keys")
    for name, p in (("first", abstracts), ("second", abstracts), ("--full", blind), ("--blind", blind)):
        p.add_argument(name, **({"required": True} if name.startswith("-") else {}))
    for p in (check, abstracts, blind):
        p.add_argument("--out", default="thesis-audit", help="output folder (default: thesis-audit)")
    args = parser.parse_args(argv)
    try:
        return {"check": cmd_check, "abstracts": cmd_abstracts, "blind": cmd_blind}[args.command](args)
    except InputError as exc:
        print(f"thesis_audit: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
