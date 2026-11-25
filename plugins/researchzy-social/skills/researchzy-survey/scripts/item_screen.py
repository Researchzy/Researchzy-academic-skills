#!/usr/bin/env python3
"""List candidate problems in a questionnaire's item table, for the agent and the user to judge.

  item_screen.py survey/items.csv
  item_screen.py survey/items.csv --max-words 25 --max-han 40 --min-items 3 --max-block 10

Reads items.csv (references/items-and-wording.md; English or Chinese column names and values) and lists for
a second look: items with a conjunction (and, or, 和, 以及 ...), one negation or two (not, never, 不, 没有 ...),
an absolute word (always, all, 总是, 从不 ...), more Latin words or Han characters than the limit, or a
leading phrase (don't you, most people, 难道, 众所周知 ...); constructs with fewer items than the limit; scales
with no source, a source without a page or table, permission unknown, or item text filled in while permission is
unknown; items whose keying is not stated; modified items to disclose; blocks longer than the limit; no attention
item, an attention item without its expected answer, no marker variable, predictor and outcome items in the same
block and wave; no exclusion-rules.json beside items.csv. The limits and word lists are conventions, printed
or listed here; a candidate is a question for a reader, not a verdict.

Writes item-screen.md beside items.csv (--out to change the folder) and prints a JSON summary. Standard
library only. Exit code 0 when the table was read; 2 when it cannot be read or lacks construct and item_id.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

ALIASES = {"construct": "构念 维度", "item_id": "item 题项编号 题号 编号", "text": "题项 题项文字 题目 文字",
           "keying": "方向 计分方向", "source": "出处 来源", "permission": "授权 授权状态", "changes": "改动 改动记录",
           "block": "区块", "role": "角色", "wave": "波次", "expected": "期望答案"}
VOCAB = {"permission": {"licensed": "licensed", "已授权": "licensed", "open": "open", "公开": "open", "开放": "open",
                        "unknown": "unknown", "未知": "unknown"},
         "keying": {"forward": "forward", "正向": "forward", "reverse": "reverse", "反向": "reverse"},
         "role": {"自变量": "predictor", "因变量": "outcome", "中介": "mediator", "调节": "moderator", "控制": "covariate",
                  "注意力": "attention", "注意力题": "attention", "标记": "marker", "标记变量": "marker", "开放题": "open",
                  "人口学": "demographic", "其他": "other"}}
NOT_CONSTRUCT = {"attention", "marker", "open", "demographic", "other"}
WORDS = {   # what a reader looks at twice; each list is a convention, not a rule of wording
    "conjunction": r"\b(?:and|or|as well as)\b|以及|并且|而且|或者|还是|(?<!参)与|(?<![以涉])及(?!时)|和(?!谐)|或(?![者许])",
    "negation": r"\b(?:not|no|never|none|nobody|nothing|neither|nor|cannot|disagree|dislike|unable|unlikely|unwilling)\b|n't\b"
                r"|不(?!断|仅|过|管|论|久|少|止|同(?!意))|没有|没(?!有)|无(?!论)|非(?!常)|未(?!来)|(?<!是)否(?!则)|勿",
    "absolute": r"\b(?:always|never|all|every|everyone|everything|nobody|none|nothing|completely|totally|absolutely|entirely)\b"
                r"|总是|从不|从来|永远|所有|每次|每个人|一切|完全|绝对|一定|全部|根本",
    "leading": r"\b(?:don't you|wouldn't you|isn't it|aren't you|do you agree that|most people|as you know|experts (?:say|agree)"
               r"|everyone knows|surely|obviously|of course)\b|难道|你不认为|您不认为|你不觉得|您不觉得|众所周知|大家都知道"
               r"|专家认为|大多数人|多数人都|显然|不是吗|对吧",
}
LOCATOR = re.compile(r"\bp{1,2}\.\s*\d|\bpages?\s*\d|\btab(?:le|\.)\s*\d|第\s*\d+\s*页|\d+\s*页|表\s*\d", re.I)
OWN = re.compile(r"user'?s own|own items?|self-written|自编|自拟|本研究编制", re.I)     # items the user wrote: no page
HAN = re.compile(r"[㐀-鿿豈-﫿]")


def fail(message: str):
    print(f"item_screen: {message}", file=sys.stderr)
    raise SystemExit(2)


def norm(text) -> str:
    return " ".join(unicodedata.normalize("NFKC", str(text or "")).split())


def read_items(path: Path) -> tuple:
    """(items as dicts with the canonical field names, the fields the table has)."""
    if not path.is_file():
        fail(f"no such file: {path}")
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        fail(f"{path} is neither UTF-8 nor GB18030 text")
    rows = list(csv.reader(io.StringIO(text, newline=""), delimiter=max(",;\t", key=text.split("\n", 1)[0].count)))
    names = {}
    for i, name in enumerate(rows[0] if rows else []):
        name = norm(name).casefold()
        field = next((f for f, alias in ALIASES.items() if name == f or name in alias.split()), None)
        names.setdefault(field, i)
    if "construct" not in names or "item_id" not in names:
        fail(f"{path} needs the columns construct and item_id (构念, 题项编号); see references/items-and-wording.md")
    items = []
    for n, row in enumerate(rows[1:], 2):
        if any(cell.strip() for cell in row):
            item = {f: norm(row[i]) if i < len(row) else "" for f, i in names.items() if f}
            for field in ("permission", "keying", "role"):
                value = item.get(field, "")
                item[field] = VOCAB[field].get(value, VOCAB[field].get(value.casefold(), value.casefold()))
            items.append({**item, "row": n})
    return items, set(names) - {None}


def screen(items: list, fields: set, args, folder: Path) -> tuple:
    found, not_checked = [], []

    def add(check, subject, detail, construct=""):
        found.append({"check": check, "subject": subject, "construct": construct, "detail": detail})

    for item in items:
        text, subject = item.get("text", ""), item["item_id"] or f"row {item['row']}"
        if text and item["role"] != "attention":
            for check, pattern in WORDS.items():
                hits = [m.group(0) for m in re.finditer(pattern, text, re.I)]
                if hits and check == "negation":
                    check = "double_negation" if len(hits) > 1 else check
                if hits:
                    add(check, subject, "words: " + ", ".join(dict.fromkeys(hits)), item["construct"])
            han, words = len(HAN.findall(text)), len(re.findall(r"[A-Za-z0-9']+", HAN.sub(" ", text)))
            if han > args.max_han or words > args.max_words:
                add("long", subject, f"{han} Han characters, {words} words (limits {args.max_han} and {args.max_words})",
                    item["construct"])
        if "keying" in fields and item["role"] not in NOT_CONSTRUCT and item["keying"] not in ("forward", "reverse"):
            add("keying", subject, "keying not stated as forward or reverse (正向/反向)", item["construct"])
        if item.get("changes"):
            add("modified", subject, f"changed from the source: {item['changes']} (disclose in the methods)", item["construct"])
    constructs = defaultdict(list)
    for item in items:
        if item["role"] not in NOT_CONSTRUCT and item["construct"]:
            constructs[item["construct"]].append(item)
    for name, members in constructs.items():
        if len(members) < args.min_items:
            add("few_items", name, f"{len(members)} item(s), fewer than {args.min_items}")
        sources = {m.get("source", "") for m in members} - {""}
        cited = {s for s in sources if not OWN.search(s)}
        if "source" in fields and not sources:
            add("no_source", name, "no source: name the paper and the page or table the items come from")
        elif cited and not any(LOCATOR.search(s) for s in cited):
            add("source_without_page", name, "source names no page or table: " + "; ".join(sorted(cited)))
        permissions = {m.get("permission", "") for m in members}
        if "permission" in fields and permissions & {"unknown", ""}:
            add("permission_unknown", name, "permission unknown or not stated: plan only, without item text, until it is known")
            if any(m.get("text") for m in members):
                add("text_without_permission", name, "item text is filled in although permission is unknown: remove it, "
                                                     "and never write a scale's items from memory")
        for value in sorted(permissions - {"licensed", "open", "unknown", ""}):
            add("permission_value", name, f"permission {value!r} is not licensed, open or unknown")
    not_checked += [f"{check}: no {field} column" for check, field in (("no_source", "source"), ("permission_unknown", "permission"),
                    ("keying", "keying"), ("long_block", "block")) if field not in fields]
    if "block" in fields:
        for block, n in Counter(i["block"] for i in items if i["block"] and i["role"] not in ("open", "demographic")).items():
            if n > args.max_block:
                add("long_block", block, f"{n} items in one block, more than {args.max_block}")
    if "role" not in fields:
        not_checked.append("attention, marker and predictor-outcome checks: no role column")
    else:
        attention = [i for i in items if i["role"] == "attention"]
        if not attention:
            add("no_attention", "questionnaire", "no item with role attention")
        for item in attention:
            if not item.get("expected"):
                add("attention_without_expected", item["item_id"], "no expected answer: write the answer that passes")
        if not any(i["role"] == "marker" for i in items):
            add("no_marker", "questionnaire", "no marker variable: it must be chosen now, before fielding")
        waves = {i.get("wave", "") for i in items if i["role"] in ("predictor", "outcome")}
        if "block" in fields:
            for (block, wave), roles in group(items).items():
                if {"predictor", "outcome"} <= roles:
                    add("predictor_outcome_same_block", block or "(no block)", "predictor and outcome items in one block"
                        + (f", wave {wave}" if wave else ""))
        else:
            not_checked.append("predictor_outcome_same_block: no block column")
        if len(waves) <= 1 and any(i["role"] == "outcome" for i in items):
            add("one_wave", "questionnaire", "predictors and outcomes are measured in one wave: plan other procedural remedies")
    if not (folder / "exclusion-rules.json").is_file():
        add("no_exclusion_rules", "questionnaire", f"no exclusion-rules.json in {folder}: write the rules before fielding")
    return found, not_checked


def group(items: list) -> dict:
    roles = defaultdict(set)
    for item in items:
        roles[(item["block"], item.get("wave", ""))].add(item["role"])
    return roles


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="List candidate problems in a questionnaire's item table.")
    parser.add_argument("items", help="items.csv (references/items-and-wording.md)")
    parser.add_argument("--max-words", type=int, default=20, help="Latin words per item before it is long (convention: 20)")
    parser.add_argument("--max-han", type=int, default=30, help="Han characters per item before it is long (convention: 30)")
    parser.add_argument("--min-items", type=int, default=3, help="items a construct needs (convention: 3)")
    parser.add_argument("--max-block", type=int, default=10, help="items in one block or matrix (convention: 10)")
    parser.add_argument("--out", help="Output folder (default: the folder of items.csv)")
    args = parser.parse_args(argv)
    path = Path(args.items)
    items, fields = read_items(path)
    folder = Path(args.out) if args.out else path.parent
    found, not_checked = screen(items, fields, args, folder)
    limits = {"max_words": args.max_words, "max_han": args.max_han, "min_items": args.min_items, "max_block": args.max_block}
    lines = ["# Item screen", "", f"Table: `{path}`, {len(items)} rows, SHA-256 `{hashlib.sha256(path.read_bytes()).hexdigest()}`.",
             "Limits (conventions the user may change): " + ", ".join(f"{k} {v}" for k, v in limits.items()) + ".", "",
             "Each row is a candidate for a second look, not a verdict. Judge it, and record the decision in "
             "wording-review.csv or the design notes.", "", "| Check | Item or scope | Construct | Detail |", "|---|---|---|---|"]
    lines += [f"| {f['check']} | {f['subject']} | {f['construct']} | {f['detail'].replace('|', '/')} |" for f in found]
    lines += ["", "## Not checked", "", *([f"- {n}" for n in not_checked] or ["None."]), ""]
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "item-screen.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"items": len(items), "limits": limits, "counts": dict(Counter(f["check"] for f in found)),
                      "candidates": found, "not_checked": not_checked, "report": str(folder / "item-screen.md")},
                     indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
