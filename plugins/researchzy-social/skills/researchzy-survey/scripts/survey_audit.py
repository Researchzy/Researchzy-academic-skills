#!/usr/bin/env python3
"""Audit returned survey data for response quality before analysis. It reads the data and writes no
cleaned dataset.

  survey_audit.py columns data/export.csv --header-row 1 --skip-rows 2     the columns, to declare them
  survey_audit.py audit data/export.csv                                     settings: survey/audit-settings.json
  survey_audit.py audit data/export.xlsx --settings survey/audit-settings.json --rules survey/exclusion-rules.json

audit computes per respondent, from the columns audit-settings.json declares (references/audit-settings.md):
attention items against their expected answers, blanks counted apart; straight-lining per block on the raw
answers before any reverse scoring (one value throughout, distinct values, share of the most common answer);
the longest run of identical answers in presentation order; total duration against the sample median; pauses
between page times; repeated IDs, identical answer vectors under different IDs, repeated IP or panel IDs;
the missing share and the last answered item; empty, short and identical open answers; declared item pairs.
Every threshold is a named setting (references/exclusion-rules.md) printed with its value and origin; the
defaults are conventions. An indicator whose column is not declared or not in the file is not_checked, never
zero; an answer that cannot be judged leaves its cell empty, never 0.

Exclusions are counted only under the rules of exclusion-rules.json (--rules; default <out>/exclusion-rules.json
when it exists). Without rules nobody is excluded. A rule that is undated, dated after fielding started, or
rests on a threshold changed since it was written is post hoc.

Writes flags.csv, audit.json and data-quality.md in --out (default survey) with the SHA-256 of the data,
settings and rules files, and prints a JSON summary. CSV and TSV need only the standard library (a quoted cell
may span lines); .xlsx needs openpyxl and .sav needs pyreadstat: without them the file is not read and the
audit is not_checked, with the package named. Exit code 0 when the report is written, also when a package is
missing; 2 when an input cannot be read or the settings or rules are malformed.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import re
import statistics
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

TOOL = "researchzy-survey"
MISSING = frozenset({"", "na", "n/a", "nan", "null", "none", "#n/a", ".", "nat", "<na>"})
# name: (default, the flags it governs, what it sets). The defaults are conventions met in practice, not findings.
SETTINGS = {
    "attention_fail_min": (1, ("attention",), "wrong answers to attention items that flag a respondent"),
    "attention_pass_low": (0.80, (), "an attention item passed by a smaller share may be unclear (lead)"),
    "attention_pass_high": (0.98, (), "an attention item passed by a larger share may be too easy to show anything (lead)"),
    "straightline_min_items": (5, ("straightline",), "answered items a block needs before one value throughout is flagged"),
    "long_run_min": (None, ("long_run",), "a run of identical answers this long is flagged; null: reported only"),
    "fast_share_of_median": (0.33, ("fast",), "a total duration under this share of the sample median is flagged"),
    "fast_seconds_per_item": (None, ("fast",), "a total duration under this many seconds per answered item is flagged"),
    "slow_multiple_of_median": (3, ("slow",), "a total duration over this multiple of the sample median is flagged"),
    "pause_seconds": (1800, ("pause",), "a gap between page times at least this long is flagged"),
    "duplicate_min_answered": (0.5, ("duplicate_answers",), "share of items answered before identical vectors are compared"),
    "open_text_short_units": (3, ("open_text_short", "open_text_identical"),
                              "an open answer with fewer words or Han characters is short and is not compared"),
    "item_missing_share": (0.10, (), "items left blank by a larger share of respondents are listed (lead)"),
}
FLAGS = ("attention", "straightline", "long_run", "fast", "slow", "pause", "duplicate_id", "duplicate_answers",
         "duplicate_ip", "duplicate_panel", "break_off", "open_text_empty", "open_text_short", "open_text_identical",
         "inconsistent")
VALUES = ("attention_wrong", "attention_blank", "duration_s", "longest_run", "longest_pause_s", "missing_share",
          "pairs_inconsistent")
AUTOMATION = ("fast", "open_text_identical", "duplicate_answers", "duplicate_ip")      # two of them: a lead
KEYS = frozenset({"header_row", "skip_rows", "delimiter", "sheet", "missing", "value_labels", "recoded", "id", "blocks",
                  "attention", "duration", "start_time", "time_format", "fielding_start", "ip", "panel_id",
                  "page_times", "open_text", "pairs", "settings"})
UNITS = {"seconds": 1, "minutes": 60, "milliseconds": 0.001}
CONDITION = re.compile(r"^\s*([a-z_]+)\s*(?:(>=|<=|>|<|=)\s*(-?\d+(?:\.\d+)?))?\s*$")
HAN = re.compile(r"[㐀-鿿豈-﫿]")
HINTS = (("id", r"^id$|[^a-z]id$|response.?id|respondent|编号|序号"), ("duration", r"duration|seconds|时长|用时|耗时"),
         ("ip", r"^ip$|ip.?address|ip地址"), ("time", r"date|time|时间|日期"))
CAP = 12                                       # rows shown per lead; the rest are counted


def fail(message: str):
    print(f"survey_audit: {message}", file=sys.stderr)
    raise SystemExit(2)


def key(text) -> str:
    """Text as compared: NFKC (full-width digits and brackets), case and spacing make no difference."""
    return " ".join(unicodedata.normalize("NFKC", str(text)).casefold().split())


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path, what: str) -> dict:
    if not path.is_file():
        fail(f"no {what} at {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (ValueError, UnicodeDecodeError) as exc:
        fail(f"{path} is not valid JSON: {exc}")
    if not isinstance(data, dict):
        fail(f"{path} must hold a JSON object")
    return data


def number_like(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def show(value) -> str:
    return "null" if value is None else f"{value:g}" if number_like(value) else str(value)


def day(text):
    text = str(text or "").strip()
    try:
        return date.fromisoformat(text) if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text) else None
    except ValueError:
        return None


def moment(text: str, fmt):
    """A timestamp as a naive UTC datetime, or None. ISO forms and 2026/3/2 10:15:00 need no time_format."""
    text = unicodedata.normalize("NFKC", text).strip().replace("Z", "+00:00")
    text = re.sub(r"^(\d{4})/(\d{1,2})/(\d{1,2})", lambda m: f"{m[1]}-{int(m[2]):02d}-{int(m[3]):02d}", text)
    try:
        value = datetime.strptime(text, fmt) if fmt else datetime.fromisoformat(text)
    except ValueError:
        return None
    return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value


def gap(start, end):
    return (end - start).total_seconds() if start and end and end >= start else None


def units(text: str) -> int:
    """Words as a reader counts them: a Han character is one, a run of letters or digits is one."""
    return len(HAN.findall(text)) + sum(1 for word in HAN.sub(" ", text).split() if any(c.isalnum() for c in word))


def longest(values: list) -> int:
    """The longest run of equal consecutive answers; a blank breaks the run."""
    best = run = 0
    previous = None
    for value in values:
        run = run + 1 if value is not None and value == previous else int(value is not None)
        best, previous = max(best, run), value
    return best


def cell_text(value) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    text = value.isoformat(sep=" ") if isinstance(value, datetime) else str(value)
    return "" if text in ("NaT", "<NA>", "nan") else text


def fields(text: str, delimiter: str) -> int:
    """How many of the first 20 records share the most common number of fields, when that is above one."""
    try:
        counts = [len(r) for r, _ in zip(csv.reader(io.StringIO(text[:20000], newline=""), delimiter=delimiter), range(20))]
    except csv.Error:
        return 0
    mode = max(set(counts), key=counts.count) if counts else 0
    return counts.count(mode) if mode > 1 else 0


def read_table(path: Path, header_row=1, skip_rows=(), sheet=None, delimiter=None) -> tuple:
    """(header, [(spreadsheet row, cells)], info); header is None when the package that reads the file is missing."""
    if not path.is_file():
        fail(f"no such file: {path}")
    suffix = path.suffix.lower()
    if suffix in (".xlsx", ".xlsm", ".sav"):
        package = "pyreadstat" if suffix == ".sav" else "openpyxl"
        try:
            module = __import__(package)
        except ImportError:
            return None, [], {"format": suffix[1:], "not_read": f"{package} is not installed"}
        try:
            if suffix == ".sav":
                frame, _ = module.read_sav(str(path))
                grid = [[str(c) for c in frame.columns]] + [[cell_text(v) for v in row] for row in frame.itertuples(index=False)]
                header_row, skip_rows, info = 1, (), {"format": "sav"}
            else:
                sheets = module.load_workbook(path, read_only=True, data_only=True)
                table = sheets[sheet] if sheet else sheets.worksheets[0]
                grid = [[cell_text(v) for v in row] for row in table.iter_rows(values_only=True)]
                info = {"format": "xlsx", "sheet": table.title}
        except Exception as exc:          # the package's own errors: a damaged file, a sheet that does not exist
            fail(f"could not read {path}: {exc}")
    else:
        raw = path.read_bytes()
        for encoding in ("utf-8-sig", "gb18030", "latin-1"):
            try:
                text = raw.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        if not delimiter:
            delimiter = "\t" if suffix in (".tsv", ".tab") else max(",;\t", key=lambda d: fields(text, d))
        try:
            grid = list(csv.reader(io.StringIO(text, newline=""), delimiter=delimiter))
        except csv.Error as exc:
            fail(f"could not read {path} as delimited text: {exc}")
        info = {"format": "tsv" if delimiter == "\t" else "csv", "encoding": encoding, "delimiter": delimiter}
    if len(grid) < header_row:
        fail(f"{path} has no row {header_row} to take the column names from")
    header, skip = [str(c).strip() for c in grid[header_row - 1]], set(skip_rows)
    skipped = {n: row for n, row in enumerate(grid, 1) if n in skip and n > header_row}
    rows = [(n, (row + [""] * len(header))[:len(header)]) for n, row in enumerate(grid, 1)
            if n > header_row and n not in skip and any(str(c).strip() for c in row)]
    if not rows:
        fail(f"{path} has no data rows under row {header_row}")
    return header, rows, {**info, "header_row": header_row, "skipped_rows": sorted(skipped), "skipped": skipped}


def check_settings(cfg: dict, path: Path) -> dict:
    unknown = sorted(set(cfg) - KEYS)
    problems = [f"unknown key(s) {', '.join(unknown)}; known: {', '.join(sorted(KEYS))}"] if unknown else []
    for i, block in enumerate(cfg.get("blocks") or []):
        block = block if isinstance(block, dict) else {}
        items, scale = block.get("items"), block.get("scale")
        if not (block.get("name") and isinstance(items, list) and items and all(isinstance(x, str) for x in items)):
            problems.append(f"blocks[{i}] needs a name and a list of item columns")
        elif not (isinstance(scale, list) and len(scale) == 2 and all(map(number_like, scale)) and scale[0] < scale[1]):
            problems.append(f'blocks[{i}] ({block["name"]}) needs "scale": [lowest, highest]')
        elif set(block.get("reversed") or []) - set(items):
            problems.append(f"blocks[{i}] ({block['name']}): reversed names a column that is not one of its items")
    for i, item in enumerate(cfg.get("attention") or []):
        if not (isinstance(item, dict) and isinstance(item.get("item"), str) and item.get("expected") not in (None, "", [])):
            problems.append(f'attention[{i}] needs "item" and "expected" (the accepted answer or answers)')
    for i, pair in enumerate(cfg.get("pairs") or []):
        if not (isinstance(pair, dict) and isinstance(pair.get("items"), list) and len(pair["items"]) == 2
                and number_like(pair.get("max_difference"))):
            problems.append(f'pairs[{i}] needs two "items" and "max_difference"')
    duration, page = cfg.get("duration"), cfg.get("page_times")
    if duration is not None and not (isinstance(duration, dict) and duration.get("unit", "seconds") in UNITS
                                     and (duration.get("column") or (duration.get("start") and duration.get("end")))):
        problems.append('duration needs "column" and "unit" (seconds, minutes, milliseconds), or "start" and "end"')
    if page is not None and not (isinstance(page, dict) and isinstance(page.get("columns"), list)
                                 and page.get("kind") in ("timestamps", "seconds")):
        problems.append('page_times needs "columns" and "kind" (timestamps or seconds)')
    if not isinstance(cfg.get("value_labels") or {}, dict) or not all(map(number_like, (cfg.get("value_labels") or {}).values())):
        problems.append("value_labels must map each answer label to a number")
    if not (isinstance(cfg.get("header_row", 1), int) and cfg.get("header_row", 1) >= 1
            and all(isinstance(n, int) for n in cfg.get("skip_rows") or [])):
        problems.append("header_row must be a row number from 1, and skip_rows a list of row numbers")
    if cfg.get("fielding_start") and not day(cfg["fielding_start"]):
        problems.append("fielding_start must be a date, YYYY-MM-DD")
    if problems:
        fail(f"{path} is not in the format of references/audit-settings.md:\n  - " + "\n  - ".join(problems))
    return cfg


def load_rules(path: Path) -> dict:
    data, problems, seen = read_json(path, "rules file"), [], set()
    rules = data.get("rules")
    if data.get("written") and not day(data["written"]):
        problems.append("written must be a date, YYYY-MM-DD")
    if not isinstance(rules, list) or not rules or not all(isinstance(r, dict) for r in rules):
        problems.append("rules must be a non-empty list of objects")
        rules = []
    if not isinstance(data.get("settings", {}), dict):
        problems.append("settings must be an object")
    for i, rule in enumerate(rules):
        rid, when = str(rule.get("id", "")).strip(), rule.get("when")
        where = f"rules[{i}] {rid}".strip()
        if not rid or rid in seen:
            problems.append(f"{where}: every rule needs its own id")
        seen.add(rid)
        if rule.get("written") and not day(rule["written"]):
            problems.append(f"{where}: written must be a date, YYYY-MM-DD")
        if not (isinstance(when, list) and when and all(isinstance(c, str) for c in when)):
            problems.append(f"{where}: when must be a list of conditions")
            continue
        rule["_conditions"], rule["_k"] = [], rule.get("at_least", len(when))
        for text in when:
            match = CONDITION.match(text)
            if not match or match[1] not in FLAGS + VALUES or (match[1] in FLAGS) == bool(match[2]):
                problems.append(f"{where}: {text!r} is not a condition. A flag stands alone ({', '.join(FLAGS)}); "
                                f"a value takes a comparison, as in attention_wrong >= 2 ({', '.join(VALUES)})")
            else:
                rule["_conditions"].append((match[1], match[2], float(match[3]) if match[2] else None))
        if not (isinstance(rule["_k"], int) and not isinstance(rule["_k"], bool) and 1 <= rule["_k"] <= len(when)):
            problems.append(f"{where}: at_least must be a whole number from 1 to the number of conditions")
    if problems:
        fail(f"{path} is not in the format of references/exclusion-rules.md:\n  - " + "\n  - ".join(problems))
    return data


def resolve(declared: dict, ruled: dict, rules_label: str) -> dict:
    """Each setting: audit-settings.json first, then the rules file, then the default (a convention)."""
    places = (("audit-settings.json", declared), (rules_label, ruled))
    for where, block in places:
        if not isinstance(block, dict) or set(block) - set(SETTINGS):
            fail(f'"settings" in {where} must be an object of known settings: {", ".join(SETTINGS)}')
    out = {}
    for name, (default, governs, meaning) in SETTINGS.items():
        found = []
        for where, block in places:
            if name in block:
                entry = block[name] if isinstance(block[name], dict) else {"value": block[name]}
                if "value" not in entry or entry["value"] is not None and (not number_like(entry.get("value")) or entry["value"] < 0):
                    fail(f"setting {name} in {where} must be a number of 0 or more, or null")
                found.append((where, entry))
        where, entry = found[0] if found else ("default, a convention", {"value": default})
        out[name] = {"value": entry.get("value"), "default": not found, "from": where, "source": str(entry.get("source", "")),
                     "date": str(entry.get("date", "")), "governs": list(governs), "meaning": meaning,
                     "as_ruled": next((e.get("value") for w, e in found if w == rules_label), default)}
    return out


def compute(header: list, rows: list, cfg: dict, st: dict) -> tuple:
    """(one dict per respondent, {indicator: (state, detail)}, the tables of the report)."""
    index, not_found, state, extra = {}, [], {}, {}
    for i, name in enumerate(header):
        index.setdefault(key(name), i)

    def col(name):
        i = index.get(key(name)) if name else None
        if name and i is None and name not in not_found:
            not_found.append(name)
        return i

    missing = MISSING | {key(token) for token in cfg.get("missing") or []}
    labels = {key(label): float(v) for label, v in (cfg.get("value_labels") or {}).items()}
    value, blank = (lambda name: st[name]["value"]), (lambda text: key(text) in missing)

    def number(text):
        found = labels.get(key(text))
        if found is None:
            try:
                found = float(unicodedata.normalize("NFKC", text))
            except ValueError:
                return None
        return found if math.isfinite(found) else None

    id_i = col(cfg.get("id"))
    out = [{"row": n, "id": cells[id_i].strip() if id_i is not None else ""} for n, cells in rows]
    blocks, scale_of, problems = [], {}, defaultdict(Counter)
    for block in cfg.get("blocks") or []:
        present = [(name, i) for name, i in ((name, col(name)) for name in block["items"]) if i is not None]
        for name, i in present:
            scale_of[i] = (*block["scale"], name in (block.get("reversed") or []))
        blocks.append({**block, "present": present, "order_i": col(block.get("order_column")), "constant": 0})
    attention = [(a["item"], col(a["item"]), a["expected"] if isinstance(a["expected"], list) else [a["expected"]])
                 for a in cfg.get("attention") or []]
    answer_cols = sorted({i for b in blocks for _, i in b["present"]} | {i for _, i, _ in attention if i is not None})
    pairs = [(p, col(p["items"][0]), col(p["items"][1])) for p in cfg.get("pairs") or []]

    def raw(cells, i):
        """The answer on the questionnaire's own scale; a reverse scoring done in the file is undone."""
        if blank(cells[i]):
            return None
        found, (low, high, reverse) = number(cells[i]), scale_of.get(i, (None, None, False))
        problem = "not a number" if found is None else "out of range" if low is not None and not low <= found <= high else ""
        if problem:
            problems[header[i]][problem] += 1
            return None
        return low + high - found if reverse and cfg.get("recoded") else found

    item_cols = sorted(set(scale_of) | {i for _, a, b in pairs for i in (a, b) if i is not None})
    answers = [{i: raw(cells, i) for i in item_cols} for _, cells in rows]

    present = [(name, i, expected) for name, i, expected in attention if i is not None]
    if not present:
        state["attention"] = ("not_checked", "the attention columns are not in the file" if attention else "no attention item declared")
    else:
        tally = {name: Counter() for name, _, _ in present}
        fail_min = value("attention_fail_min")
        for r, (_, cells) in zip(out, rows):
            r["attention_wrong"] = r["attention_blank"] = 0
            for name, i, expected in present:
                given = number(cells[i])
                outcome = "blank" if blank(cells[i]) else "correct" if any(
                    key(e) == key(cells[i]) or (given is not None and number(str(e)) == given) for e in expected) else "wrong"
                tally[name][outcome] += 1
                r["attention_wrong"] += outcome == "wrong"
                r["attention_blank"] += outcome == "blank"
            wrong, gaps = r["attention_wrong"], r["attention_blank"]
            r["attention"] = None if fail_min is None else True if wrong >= fail_min else None if wrong + gaps >= fail_min else False
        extra["attention_items"] = []
        for name, _, expected in present:
            seen = tally[name]["correct"] + tally[name]["wrong"]
            rate = round(tally[name]["correct"] / seen, 3) if seen else None
            note = ("" if rate is None else "may be too easy to show anything" if rate > value("attention_pass_high")
                    else "may be unclear or keyed wrongly" if rate < value("attention_pass_low") else "")
            extra["attention_items"].append({"item": name, "expected": expected, **tally[name], "pass_rate": rate, "note": note})
        state["attention"] = ("checked", f"{sum(r['attention_wrong'] > 0 for r in out)} gave a wrong answer; "
                                         f"{sum(r['attention_blank'] > 0 for r in out)} left an attention item blank, counted apart")

    min_items, runs_known = value("straightline_min_items"), False
    for b in blocks:
        b["checkable"] = min_items is not None and len(b["present"]) >= min_items
    for r, v, (_, cells) in zip(out, answers, rows):
        hits, unknown, runs = [], False, []
        for b in blocks:
            usable = [v[i] for _, i in b["present"] if v[i] is not None]
            r[f"{b['name']}_distinct"] = len(set(usable)) if usable else None
            r[f"{b['name']}_modal_share"] = round(max(Counter(usable).values()) / len(usable), 3) if usable else None
            if b["checkable"] and len(usable) < min_items:
                unknown = True
            elif b["checkable"] and len(set(usable)) == 1:
                hits.append(b["name"])
                b["constant"] += 1
            if b["order_i"] is not None:
                members = {i for _, i in b["present"]}
                shown = [i for i in (index.get(key(x)) for x in re.split(r"[|,;\s]+", cells[b["order_i"]]) if x) if i in members]
                order = shown if sorted(shown) == sorted(members) else None
            else:
                order = None if b.get("randomised") else [i for _, i in b["present"]]
            if order:
                runs.append(longest([v[i] for i in order]))
                r[f"{b['name']}_run"] = runs[-1]
        r["straightline_blocks"] = hits
        r["straightline"] = True if hits else None if unknown else False
        r["longest_run"] = max(runs) if runs else None
        runs_known = runs_known or bool(runs)
    if min_items is None:
        state["straightline"] = ("no_threshold", "straightline_min_items is null")
    elif not any(b["checkable"] for b in blocks):
        state["straightline"] = ("not_checked", f"no block has {show(min_items)} item columns in the file" if blocks
                                 else "no item block declared")
    else:
        state["straightline"] = ("checked", "; ".join(
            f"{b['name']} ({len(b['present'])} items, {len(b.get('reversed') or [])} reverse-keyed): {b['constant']}"
            if b["checkable"] else f"{b['name']}: too few items to check" for b in blocks))
    lengths = [r["longest_run"] for r in out if r["longest_run"] is not None]
    if not runs_known:
        state["long_run"] = ("not_checked", "item order was randomised and the export has no display order" if blocks
                             else "no item block declared")
    elif value("long_run_min") is None:
        state["long_run"] = ("no_threshold", f"longest run: median {show(statistics.median(lengths))}, highest "
                                             f"{max(lengths)}; long_run_min is null, so nothing is flagged")
    else:
        for r in out:
            r["long_run"] = None if r["longest_run"] is None else r["longest_run"] >= value("long_run_min")
        state["long_run"] = ("checked", f"a run of {show(value('long_run_min'))} or more identical answers in presentation order")

    if not answer_cols:
        state["break_off"] = ("not_checked", "no item column declared or found")
    else:
        empty = Counter()
        for r, (_, cells) in zip(out, rows):
            given = [not blank(cells[i]) for i in answer_cols]
            empty.update(i for i, g in zip(answer_cols, given) if not g)
            last = max((k for k, g in enumerate(given) if g), default=-1)
            r["missing_share"], r["_answered"] = round(1 - sum(given) / len(given), 3), sum(given)
            r["last_answered"], r["break_off"] = header[answer_cols[last]] if last >= 0 else "", last < len(given) - 1
        limit = value("item_missing_share")
        extra["items_missing"] = [{"item": header[i], "blank": empty[i], "share": round(empty[i] / len(rows), 3)}
                                  for i in answer_cols if limit is not None and empty[i] / len(rows) > limit]
        stops = Counter(r["last_answered"] or "(none)" for r in out if r["break_off"])
        extra["break_off_points"] = dict(stops.most_common())
        state["break_off"] = ("checked", "item columns in file order; last answered: " + (
            ", ".join(f"{k} ({n})" for k, n in stops.most_common(3)) or "none stopped early"))

    duration, durations, start_i = cfg.get("duration"), [None] * len(rows), col(cfg.get("start_time"))
    fmt = cfg.get("time_format")
    if duration and duration.get("column") and col(duration["column"]) is not None:
        i, factor = col(duration["column"]), UNITS[duration.get("unit", "seconds")]
        seconds = lambda text: number(re.sub(r"\s*(?:秒|s|secs?|seconds)$", "", text.strip(), flags=re.I))  # noqa: E731  "300秒"
        durations = [None if seconds(c[i]) is None or seconds(c[i]) < 0 else seconds(c[i]) * factor for _, c in rows]
    elif duration and not duration.get("column") and None not in (col(duration["start"]), col(duration["end"])):
        start_i = col(duration["start"]) if start_i is None else start_i
        durations = [gap(moment(c[col(duration["start"])], fmt), moment(c[col(duration["end"])], fmt)) for _, c in rows]
    extra["starts"] = [t for t in (moment(cells[start_i], fmt) for _, cells in rows) if t] if start_i is not None else []
    known = [d for d in durations if d is not None]
    if not known:
        why = "no duration declared" if not duration else "no duration could be read from the declared column(s)"
        state["fast"] = state["slow"] = ("not_checked", why)
    else:
        median, share, per_item, multiple = statistics.median(known), *map(value, (
            "fast_share_of_median", "fast_seconds_per_item", "slow_multiple_of_median"))
        for r, d in zip(out, durations):
            r["duration_s"] = None if d is None else round(d, 1)
            r["fast"] = None if d is None else bool(share is not None and d < share * median
                                                     or per_item is not None and d < per_item * r.get("_answered", 0))
            r["slow"] = None if d is None or multiple is None else d > multiple * median
        floors = ([f"{show(share)} × the median {median:.0f} s = {share * median:.0f} s"] if share is not None else []) + (
            [f"{show(per_item)} s per answered item"] if per_item is not None else [])
        state["fast"] = ("checked", "under " + " or ".join(floors)) if floors else ("no_threshold", "both fast settings are null")
        state["slow"] = ("checked", f"over {show(multiple)} × the median = {multiple * median:.0f} s") if multiple is not None \
            else ("no_threshold", "slow_multiple_of_median is null")
        extra["median_duration_s"] = round(median, 1)

    page = cfg.get("page_times")
    page_cols = [i for i in (col(c) for c in page["columns"]) if i is not None] if page else []
    if len(page_cols) < (2 if page and page["kind"] == "timestamps" else 1):
        state["pause"] = ("not_checked", "the page-time columns are not in the file" if page else "no page times declared")
    else:
        limit = value("pause_seconds")
        for r, (_, cells) in zip(out, rows):
            if page["kind"] == "timestamps":
                times = [t for t in (moment(cells[i], fmt) for i in page_cols) if t]
                gaps = [g for g in (gap(a, b) for a, b in zip(times, times[1:])) if g is not None]
            else:
                gaps = [g for g in (number(cells[i]) for i in page_cols) if g is not None]
            r["longest_pause_s"] = round(max(gaps), 1) if gaps else None
            r["pause"] = None if not gaps or limit is None else max(gaps) >= limit
        state["pause"] = ("checked", f"a gap of {show(limit)} s or more between page times") if limit is not None \
            else ("no_threshold", "pause_seconds is null")

    for flag, name, label, link in (("duplicate_id", "id", "ID", "same_id_as"), ("duplicate_ip", "ip", "IP address", "same_ip_as"),
                                    ("duplicate_panel", "panel_id", "panel ID", "same_panel_id_as")):
        i = col(cfg.get(name))
        if i is None:
            state[flag] = ("not_checked", f"the {label} column {cfg[name]} is not in the file" if cfg.get(name)
                           else f"no {label} column declared")
            continue
        seen = {}
        for r, (_, cells) in zip(out, rows):
            k = key(cells[i])
            r[flag] = None if k in missing else k in seen
            if r[flag]:
                r[link] = seen[k]
            seen.setdefault(k, r["row"])
        repeated = Counter(key(cells[i]) for _, cells in rows if not blank(cells[i]))
        state[flag] = ("checked", f"{sum(n > 1 for n in repeated.values())} value(s) occur more than once; "
                                  "the later rows are flagged")

    least = value("duplicate_min_answered")
    if not answer_cols:
        state["duplicate_answers"] = ("not_checked", "no item column declared or found")
    else:
        first_of = {}
        for r, (_, cells) in zip(out, rows):
            vector = tuple(None if blank(cells[i]) else key(cells[i]) for i in answer_cols)
            given = [x for x in vector if x is not None]
            if len(given) < (least or 0) * len(vector):
                r["duplicate_answers"] = None
            elif len(set(given)) < 2:
                r["duplicate_answers"] = False                  # one value throughout: left to straight-lining
            else:
                first = first_of.setdefault(vector, r)
                r["duplicate_answers"] = first is not r and (not r["id"] or key(first["id"]) != key(r["id"]))
                if r["duplicate_answers"]:
                    r["same_answers_as"] = first["row"]
        state["duplicate_answers"] = ("checked", "the same answers to every item as an earlier row with another ID; "
                                                 "answers with one value throughout are left to straight-lining")

    opens = [(name, col(name)) for name in cfg.get("open_text") or []]
    opens, short_units, groups = [(n, i) for n, i in opens if i is not None], value("open_text_short_units") or 0, defaultdict(list)
    if not opens:
        for flag in ("open_text_empty", "open_text_short", "open_text_identical"):
            state[flag] = ("not_checked", "the open-text columns are not in the file" if cfg.get("open_text")
                           else "no open-text column declared")
    else:
        for r, (_, cells) in zip(out, rows):
            texts = [(name, cells[i].strip()) for name, i in opens]
            r["open_text_empty"] = any(blank(t) for _, t in texts)
            r["open_text_short"] = any(not blank(t) and units(t) < short_units for _, t in texts)
            r["open_text_identical"] = False
            for name, t in texts:
                if not blank(t) and units(t) >= short_units and re.sub(r"[\W_]+", "", key(t)):
                    groups[(name, re.sub(r"[\W_]+", "", key(t)))].append((r, t))
        extra["identical_open_text"] = []
        for (name, _), members in sorted(groups.items(), key=lambda g: -len(g[1])):
            if len(members) > 1:
                for r, _ in members:
                    r["open_text_identical"] = True
                extra["identical_open_text"].append({"column": name, "text": members[0][1][:120],
                                                     "rows": [r["row"] for r, _ in members]})
        state["open_text_empty"] = ("checked", "an open-text answer left blank")
        state["open_text_short"] = ("checked", f"under {show(short_units)} words or Han characters")
        state["open_text_identical"] = ("checked", f"{len(extra['identical_open_text'])} group(s) of identical answers; "
                                                   "every member is flagged")

    usable = [(p, a, b, *(p.get("scale") or scale_of.get(b, (None, None))[:2])) for p, a, b in pairs if None not in (a, b)]
    if not usable:
        state["inconsistent"] = ("not_checked", "the pair columns are not in the file" if pairs else "no item pair declared")
    else:
        for r, v in zip(out, answers):
            r["pairs_inconsistent"], unknown = 0, False
            for p, a, b, low, high in usable:
                if v[a] is None or v[b] is None or (p.get("reversed") and low is None):
                    unknown = True
                    continue
                r["pairs_inconsistent"] += abs(v[a] - (low + high - v[b] if p.get("reversed") else v[b])) > p["max_difference"]
            r["inconsistent"] = True if r["pairs_inconsistent"] else None if unknown else False
        state["inconsistent"] = ("checked", "; ".join(f"{p['items'][0]} and {p['items'][1]}{' (one reversed)' if p.get('reversed') else ''}"
                                                      f" differ by more than {show(p['max_difference'])}" for p, *_ in usable))
    for flag in FLAGS:                          # an indicator that is not checked leaves every cell unjudged
        if state[flag][0] != "checked":
            for r in out:
                r.pop(flag, None)
    extra.update(not_found=not_found, problems={k: dict(v) for k, v in problems.items()},
                 pairs=[{"items": p["items"], "reversed": bool(p.get("reversed")), "max_difference": p["max_difference"]}
                        for p, *_ in usable])
    return out, state, extra


def apply_rules(rules, out: list, st: dict, fielding) -> list:
    results = []
    for rule in (rules or {}).get("rules", []):
        written = day(rule.get("written") or rules.get("written"))
        why = ["undated"] if written is None else [f"written {written}, after fielding started on {fielding}"] \
            if fielding and written > fielding else []
        used = {name for name, _, _ in rule["_conditions"]}
        why += [f"{name} is {show(s['value'])} here and was {show(s['as_ruled'])} when the rules were written"
                for name, s in st.items() if used & set(s["governs"]) and s["value"] != s["as_ruled"]]
        for r in out:
            truth = []
            for name, op, limit in rule["_conditions"]:
                v = r.get(name)
                truth.append(v if v is None or op is None else
                             {">=": v >= limit, ">": v > limit, "<=": v <= limit, "<": v < limit, "=": v == limit}[op])
            met, open_ = sum(t is True for t in truth), sum(t is None for t in truth)
            if met >= rule["_k"]:
                r.setdefault("excluded_by", []).append(rule["id"])
            elif met + open_ >= rule["_k"]:
                r.setdefault("undetermined_by", []).append(rule["id"])
        results.append({"id": rule["id"], "description": str(rule.get("description", "")), "when": rule["when"],
                        "at_least": rule["_k"], "written": str(written or ""),
                        "status": "post_hoc" if why else "a_priori" if fielding else "timing_not_known",
                        "why": why, "excluded": sum(rule["id"] in r.get("excluded_by", []) for r in out),
                        "only_this_rule": sum(r.get("excluded_by") == [rule["id"]] for r in out),
                        "undetermined": sum(rule["id"] in r.get("undetermined_by", []) and not r.get("excluded_by") for r in out)})
    return results


def table(header: tuple, rows) -> list:
    cell = lambda v: re.sub(r"\s+", " ", "" if v is None else v if isinstance(v, str) else show(v)).replace("|", "/").strip()  # noqa: E731
    return ["| " + " | ".join(header) + " |", "|" + "---|" * len(header), *("| " + " | ".join(map(cell, row)) + " |" for row in rows)]


def report(ctx: dict) -> list:
    files, counts, state, st, out = ctx["files"], ctx.get("counts"), ctx["indicators"], ctx["settings"], ctx.get("out", [])
    data, rules = files["data"], files.get("rules")
    lines = ["# Survey data quality", "",
             f"- Data: `{data['path']}` ({data['format']}), SHA-256 `{data['sha256']}`",
             f"- Settings: `{files['settings']['path']}`, SHA-256 `{files['settings']['sha256']}`",
             f"- Exclusion rules: `{rules['path']}`, SHA-256 `{rules['sha256']}`" if rules else
             "- Exclusion rules: none (no exclusion-rules.json)", f"- Fielding started: {ctx['fielding']}", ""]
    if ctx.get("not_read"):
        return lines + [f"The data file was not read: {ctx['not_read']}. Every indicator is not_checked. Export the "
                        "data as CSV, or install the package with the user's consent, and run the audit again.", ""]
    lines += ["## Respondents", "", *table(("", "n"), [("Rows received", counts["received"]),
              ("Excluded by rules written before fielding", counts["excluded_a_priori"]),
              ("Excluded only by post hoc rules", counts["excluded_post_hoc"]),
              ("Excluded by rules whose date cannot be compared with fielding (declare fielding_start)",
               counts["excluded_timing_not_known"]),
              ("Not decided: a rule rests on an answer that could not be judged (kept)", counts["undetermined"]),
              ("Analysed", counts["analysed"])]), ""]
    if not rules:
        lines += ["No exclusion rules were written, so nobody is excluded. The flags below are counts, not decisions. "
                  "Rules written now, after the data came in, are post hoc.", ""]
    flagged = lambda f: sum(r.get(f) is True for r in out)  # noqa: E731
    lines += ["## Indicators", "", "Flagged is a count, not an exclusion. Not judged: the answers needed were blank.", "",
              *table(("Indicator", "State", "Flagged", "Not judged", "Detail"),
                     [(f, s, flagged(f) if s == "checked" else "-", sum(f in r and r[f] is None for r in out) if s == "checked"
                       else "-", d) for f, (s, d) in state.items()]), ""]
    checked = [f for f in FLAGS if state[f][0] == "checked"]
    both = Counter((a, b) for r in out for i, a in enumerate(checked) for b in checked[i + 1:] if r.get(a) is True and r.get(b) is True)
    lines += ["## Overlap between indicators", "", "Respondents by the number of flags they carry: " + ", ".join(
        f"{k}: {n}" for k, n in sorted(Counter(sum(r.get(f) is True for f in checked) for r in out).items())) + ".", ""]
    lines += [*table(("Flag", "Flag", "Both"), [(a, b, n) for (a, b), n in both.most_common()]), ""] if both else []
    if ctx["rules"]:
        lines += ["## Rules", "", *table(("Rule", "When", "Written", "Status", "Excludes", "Only this rule", "Not decided", "Why post hoc"),
                  [(r["id"], f"{r['at_least']} of: " + "; ".join(r["when"]), r["written"] or "undated", r["status"], r["excluded"],
                    r["only_this_rule"], r["undetermined"], "; ".join(r["why"])) for r in ctx["rules"]]), ""]
    extra = ctx["extra"]
    if extra.get("attention_items"):
        lines += ["## Attention items", "", *table(("Item", "Expected", "Correct", "Wrong", "Blank", "Pass rate", "Lead"),
                  [(a["item"], ", ".join(map(str, a["expected"])), a["correct"], a["wrong"], a["blank"], a["pass_rate"], a["note"])
                   for a in extra["attention_items"]]), ""]
    if "items_missing" in extra:
        lines += ["## Missing answers", "", "Reported only; how to handle them is decided in the analysis plan.", "",
                  "Respondents who stopped before the last item, by the last item they answered: " + (", ".join(
                      f"{k}: {n}" for k, n in extra["break_off_points"].items()) or "none") + ".", ""]
        lines += table(("Item", "Blank", "Share"), [(m["item"], m["blank"], m["share"]) for m in extra["items_missing"]]) + [""] \
            if extra["items_missing"] else [f"No item is blank for more than {show(st['item_missing_share']['value'])} of respondents.", ""]
    if extra["problems"]:
        lines += ["Answers that are not numbers or lie outside the declared scale, read as blank: " + "; ".join(
            f"{item}: " + ", ".join(f"{n} {kind}" for kind, n in kinds.items()) for item, kinds in extra["problems"].items()) + ".", ""]
    if extra.get("identical_open_text"):
        lines += ["## Identical open answers", "", "Whether an answer means anything needs a reader; a common phrase can "
                  "repeat without meaning anything.", "", *table(("Column", "Answer", "Rows"), [(g["column"], g["text"],
                  ", ".join(map(str, g["rows"][:CAP])) + (f" and {len(g['rows']) - CAP} more" if len(g["rows"]) > CAP else ""))
                  for g in extra["identical_open_text"][:CAP]]), ""]
    leads = [r for r in out if sum(r.get(f) is True for f in AUTOMATION) >= 2]
    lines += ["## Leads: possibly automated responses", "", "Rows with two or more of: fast, identical open answer, the same "
              "answers as another ID, a repeated IP address. This is a lead, not a finding: a file with one row per "
              "respondent shows no mouse or keyboard behaviour, no paste events, no device, and no timing within a page, "
              "so it cannot show who or what answered.", "", ", ".join(f"row {r['row']} ({', '.join(f for f in AUTOMATION if r.get(f) is True)})"
              for r in leads[:CAP]) + (f", and {len(leads) - CAP} more" if len(leads) > CAP else "") if leads else "None.", ""]
    lines += ["## Settings", "", "A default is a convention, not a finding; the user may change it.", "",
              *table(("Setting", "Value", "From", "Source given", "Date", "Sets"), [(n, show(s["value"]), s["from"], s["source"], s["date"],
                     s["meaning"]) for n, s in st.items()] + [(f"pair {' / '.join(p['items'])}", show(p["max_difference"]),
                     "audit-settings.json", "", "", "largest difference accepted" + (" after reversing the second" if p["reversed"] else ""))
                                                                for p in extra["pairs"]]), ""]
    gone = [f"{f}: {d}" for f, (s, d) in state.items() if s == "not_checked"]
    lines += ["## Not checked", "", *([f"- {g}" for g in gone] or ["None."]), ""]
    if extra["not_found"]:
        lines += ["Declared columns that are not in the file: " + ", ".join(extra["not_found"]) + ".", ""]
    return lines


def cmd_columns(args) -> int:
    path = Path(args.data)
    header, rows, info = read_table(path, args.header_row, args.skip_rows or (), args.sheet, args.delimiter)
    result = {"file": str(path), **{k: v for k, v in info.items() if k != "skipped"}}
    if header is not None:
        result.update(rows=len(rows), columns=[])
        for i, name in enumerate(header):
            values = [cells[i].strip() for _, cells in rows if cells[i].strip()]
            below = next((row[i] for _, row in sorted(info["skipped"].items()) if i < len(row) and row[i].strip()), "")
            hint = next((role for role, pattern in HINTS if re.search(pattern, key(name))), "")
            if not hint and values and 2 * sum(units(v) >= 3 and not re.fullmatch(r"[\d.:\s/-]+", v) for v in values) > len(values):
                hint = "open_text"
            result["columns"].append({"column": i + 1, "name": name, "text_below": below.strip()[:80], "filled": len(values),
                                      "examples": list(dict.fromkeys(v[:40] for v in values))[:3], "looks_like": hint})
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


def cmd_audit(args) -> int:
    folder, data = Path(args.out), Path(args.data)
    settings_path = Path(args.settings) if args.settings else folder / "audit-settings.json"
    cfg = check_settings(read_json(settings_path, "settings file"), settings_path)
    rules_path = Path(args.rules) if args.rules else folder / "exclusion-rules.json"
    rules = load_rules(rules_path) if args.rules or rules_path.is_file() else None
    label = f"exclusion-rules.json ({rules.get('written') or 'undated'})" if rules else "exclusion-rules.json"
    st = resolve(cfg.get("settings") or {}, (rules or {}).get("settings") or {}, label)
    targets = {name: folder / name for name in ("flags.csv", "audit.json", "data-quality.md")}
    if data.resolve() in {p.resolve() for p in targets.values()}:
        fail(f"{data} is one of this script's output files; give the data file itself")
    header, rows, info = read_table(data, cfg.get("header_row", 1), cfg.get("skip_rows") or (), cfg.get("sheet"), cfg.get("delimiter"))
    files = {"data": {"path": str(data), "sha256": sha256(data), **{k: v for k, v in info.items() if k != "skipped"}},
             "settings": {"path": str(settings_path), "sha256": sha256(settings_path)},
             "rules": {"path": str(rules_path), "sha256": sha256(rules_path), "written": rules.get("written", "")} if rules else None}
    ctx = {"tool": TOOL, "schema_version": 1, "files": files, "settings": st}
    if header is None:
        ctx.update(not_read=info["not_read"], fielding="not known", indicators={f: ("not_checked", info["not_read"]) for f in FLAGS})
    else:
        out, state, extra = compute(header, rows, cfg, st)
        if cfg.get("fielding_start"):
            fielding, source = day(cfg["fielding_start"]), "fielding_start in audit-settings.json"
        elif extra["starts"]:
            fielding, source = min(extra["starts"]).date(), "the earliest start time in the data"
        else:
            fielding, source = None, "not known: declare fielding_start in audit-settings.json"
        results = apply_rules(rules, out, st, fielding)
        status = {r["id"]: r["status"] for r in results}
        excluded = [r for r in out if r.get("excluded_by")]
        prior = sum(any(status[x] == "a_priori" for x in r["excluded_by"]) for r in excluded)
        late = sum(all(status[x] == "post_hoc" for x in r["excluded_by"]) for r in excluded)
        counts = {"received": len(out), "excluded_a_priori": prior, "excluded_post_hoc": late,
                  "excluded_timing_not_known": len(excluded) - prior - late,
                  "undetermined": sum(bool(r.get("undetermined_by")) and not r.get("excluded_by") for r in out),
                  "analysed": len(out) - len(excluded)}
        ctx.update(fielding=f"{fielding} ({source})" if fielding else source, indicators={f: state[f] for f in FLAGS}, counts=counts, rules=results,
                   extra={k: v for k, v in extra.items() if k != "starts"}, out=out)
    folder.mkdir(parents=True, exist_ok=True)
    targets["data-quality.md"].write_text("\n".join(report(ctx)), encoding="utf-8")
    written, out = [targets["data-quality.md"], targets["audit.json"]], ctx.get("out", [])
    if header is not None:
        flags = [f for f in FLAGS if ctx["indicators"][f][0] == "checked"]
        names = ["row", "id", *flags, *[v for v in VALUES if any(r.get(v) is not None for r in out)],
                 *dict.fromkeys(c for r in out for c in r if c.endswith(("_distinct", "_modal_share", "_run")) and c not in VALUES),
                 *[c for c in ("straightline_blocks", "last_answered", "same_id_as", "same_answers_as", "same_ip_as",
                               "same_panel_id_as") if any(c in r for r in out)], "excluded", "excluded_by", "undetermined_by"]
        with targets["flags.csv"].open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(names)
            for r in out:
                r["excluded"] = True if r.get("excluded_by") else None if r.get("undetermined_by") else False
                writer.writerow(["" if r.get(c) is None else ";".join(r[c]) if isinstance(r[c], list) else int(r[c])
                                 if isinstance(r[c], bool) else r[c] for c in names])
        written.append(targets["flags.csv"])
    indicators = {f: {"state": s, "detail": d, **({"flagged": sum(r.get(f) is True for r in out),
                                                   "not_judged": sum(f in r and r[f] is None for r in out)} if s == "checked" else {})}
                  for f, (s, d) in ctx["indicators"].items()}
    full = {**{k: v for k, v in ctx.items() if k != "out"}, "indicators": indicators}
    targets["audit.json"].write_text(json.dumps(full, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    brief = {"files": files, "fielding": ctx["fielding"], "counts": ctx.get("counts"), "not_read": ctx.get("not_read"),
             "indicators": {f: i.get("flagged", i["state"]) for f, i in indicators.items()},
             "columns_not_found": ctx.get("extra", {}).get("not_found"),
             "rules": [{k: r[k] for k in ("id", "status", "excluded", "undetermined")} for r in ctx.get("rules", [])],
             "outputs": [str(p) for p in written]}
    print(json.dumps({k: v for k, v in brief.items() if v is not None}, indent=2, ensure_ascii=False))
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Audit returned survey data for response quality before analysis.")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("columns", help="List the columns with the text below them, to write audit-settings.json")
    p.add_argument("data", help="The export: CSV, TSV, .xlsx (openpyxl) or .sav (pyreadstat)")
    p.add_argument("--header-row", type=int, default=1, help="The row that holds the column names (default 1)")
    p.add_argument("--skip-rows", type=int, nargs="*", help="Further header rows to skip, by row number")
    p.add_argument("--sheet", help="The sheet of an .xlsx file (default: the first)")
    p.add_argument("--delimiter", help="The delimiter of a text file (default: detected)")
    p = sub.add_parser("audit", help="Compute the indicators, count exclusions under the rules, write the report")
    p.add_argument("data", help="The export: CSV, TSV, .xlsx (openpyxl) or .sav (pyreadstat)")
    p.add_argument("--settings", help="The declared columns and settings (default: <out>/audit-settings.json)")
    p.add_argument("--rules", help="The exclusion rules (default: <out>/exclusion-rules.json when it exists)")
    p.add_argument("--out", default="survey", help="Output folder (default: survey)")
    args = parser.parse_args(argv)
    return cmd_columns(args) if args.command == "columns" else cmd_audit(args)


if __name__ == "__main__":
    sys.exit(main())
