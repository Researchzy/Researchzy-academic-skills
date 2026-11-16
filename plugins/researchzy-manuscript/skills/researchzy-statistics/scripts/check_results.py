#!/usr/bin/env python3
"""Check the result file of an analysis, the script that wrote it, and the text written from it.

  check_results.py                                          statistics/results.json and ledger.jsonl
  check_results.py --script statistics/analysis.py          also lint the analysis script
  check_results.py --text statistics/results.md methods.md  also look up every number in the text
  check_results.py --dir other-folder --strict

  complete   every result names its test, unit, n and estimate; a p-value has the interval of its
             estimate and an effect size with its interval, or the stated reason for having none
  families   a family of two or more tests names its correction and has adjusted p-values; the
             number corrected over equals the tests the ledger holds for the family, kept and
             dropped; Bonferroni, Holm, BH and BY values are recomputed
  ledger     the kept analyses of the last run are the results; a drop has its reason. Analyses of
             earlier runs that the last run no longer has are listed, to be explained
  hashes     the script and the data files still have the recorded SHA-256: ok, drift, or
             not_checked when a file is absent
  script     (--script) a seed is set through a generator and passed to every resampler; no data
             typed in as literals; no input file written to; results go through rz_results;
             ttest_ind states equal_var. not_checked without --script or when it does not parse
  text       (--text) every number is looked up at the rounding it is printed with: matched,
             mismatch or not_found. A labelled number (p, n, df, a test statistic, a package
             version) is compared with values of that kind; "p < 0.001" matches any smaller p;
             "p = 0.000" is a mismatch. A printed minus sign must match the recorded sign; a number
             without one may carry its direction in words ("shorter by 9.1 min"). An unlabelled
             number that matches nothing is a mismatch when it has decimals and either its
             sentence reports a result (two or more of its other numbers match one result) or the
             recorded value has the opposite sign, else not_found. Ignored by rule: years, dates,
             headings, list markers, code, links, citations, numbers after Figure, Table, Section
             and the like, numbers inside names (IL-6, CO2), table sizes. statistics/power*.json
             from power.py, when present, also supply values.

Writes check.md in --dir and prints a JSON summary. Exit code 1 on a mismatch, a failed check
(a missing field, a family without correction, a ledger or script finding) or drift; with
--strict also on a not_found number. Exit code 2 when results.json cannot be read.

A skill that records other kinds of results calls main(argv, extend). extend(content, args)
returns a dict with any of: "title" of check.md; "checks", rows of (name, status, problems,
detail) added before the text check; "numbers", (value, kind, owner, path) the text may print;
"labels", (kind, regex) pairs tried after the built-in ones. Numbers in a result's extra field
are looked up like its estimate.

Standard library only. Portions are derived from MIT-licensed code: see LICENSE-MIT.txt next to
this file and THIRD_PARTY_NOTICES.md in the plugin.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import numbers
import os
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rz_results import METHODS, ROLES, adjust  # noqa: E402

TYPED_DATA_MIN = 8            # numbers in one literal from which it is data, not a setting
GENERATORS = ("default_rng", "RandomState", "Random", "SeedSequence")
RESAMPLERS = ("bootstrap", "permutation_test", "monte_carlo_test")
GLOBAL_DRAW = re.compile(r"^(?:np|numpy)\.random\.(?!default_rng$|RandomState$|Generator$|SeedSequence$|seed$)\w+$"
                         r"|^random\.(?:random|randint|randrange|choices?|sample|shuffle|uniform|gauss|normalvariate)$")
READERS = frozenset("read_csv read_table read_excel read_parquet read_feather read_json read_stata loadtxt genfromtxt "
                    "read_text read_bytes".split())
WRITERS = frozenset("to_csv to_excel to_parquet to_feather to_json to_stata to_pickle savetxt write_text write_bytes "
                    "unlink remove".split())

NUMBER = re.compile(r"(?<![\w.^])(-)?((?:\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d+))?)"
                    r"(?:\s*[×x]\s*10\s*\^\s*\{?(-?\d+)\}?|[eE]([-+]?\d+))?(\s?%)?")
STAT = r"(?:\b[tFzZUWHQ]|χ\^?2|\bchi2|\bchi-squared?)"
LABELS = (("p", re.compile(r"(?:\b[pPq]|\b[pP][- ]?values?)\s*(?:[-_ ]?\(?(?:adj(?:usted)?|corr(?:ected)?|Holm|BH|BY|FDR|"
                           r"Bonferroni)\)?)?\s*([=<>≤≥])\s*$")),
          ("n", re.compile(r"\b[nN]\s*=\s*$")),
          ("df", re.compile(r"(?:\bdf\s*=\s*|" + STAT + r"\s*\(\s*(?:[\d.]+\s*,\s*)?)$")),
          ("statistic", re.compile(STAT + r"\s*(?:\([^()]*\))?\s*=\s*$")))
REFERENCE = re.compile(r"\b(?:sections?|sec\.|figures?|figs?\.|tables?|equations?|eqs?\.|appendix|chapter|steps?|aims?|"
                       r"hypothes[ie]s|models?|stud(?:y|ies)|experiments?|panels?|supplementary\s+\w+|refs?\.|"
                       r"references?|versions?|v\.?)\s*S?$", re.I)
BLANKED = (r"```.*?```", r"`[^`\n]*`", r"<!--.*?-->", r"https?://\S+", r"\b10\.\d{4,9}/\S+", r"\b\d{4}-\d{2}-\d{2}\b",
           r"(?m)^\s*#.*$", r"(?m)^\s*\d+[.)]\s", r"\[\s*\d+(?:\s*[,;–-]\s*\d+)*\s*\]", r"\[@[^\]]*\]")
SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z(\[])|\n\s*\n|\n(?=\s*[|*-])")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_number(value) -> bool:
    return isinstance(value, numbers.Real) and not isinstance(value, bool)


def has_text(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


def check_complete(results: list) -> list:
    problems = []
    for r in results:
        def need(ok, what):
            if not ok:
                problems.append(f"{r.get('id', '(no id)')}: {what}")
        for name in ("id", "question", "family", "test", "unit"):
            need(has_text(r.get(name)), f"{name} is missing")
        need(r.get("role") in ROLES, "role is not primary, secondary or exploratory")
        counts = list(r["n"].values()) if isinstance(r.get("n"), dict) else [r.get("n")]
        need(counts and all(isinstance(c, int) and not isinstance(c, bool) and c > 0 for c in counts), "n is missing")
        estimate, interval, effect = r.get("estimate") or {}, r.get("interval") or {}, r.get("effect_size")
        need(has_text(estimate.get("name")) and is_number(estimate.get("value")) and has_text(estimate.get("units")),
             "the estimate lacks its name, value or units")
        if r.get("p") is None:
            continue
        need(is_number(r["p"]) and 0 <= r["p"] <= 1, "p is not an exact value between 0 and 1")
        need(all(is_number(interval.get(k)) for k in ("low", "high", "level")), "a p-value without the interval of its estimate")
        if isinstance(effect, dict):
            need(has_text(effect.get("name")) and is_number(effect.get("value")), "the effect size lacks its name or value")
            need(all(is_number(effect.get(k)) for k in ("low", "high")) or has_text(effect.get("no_interval")),
                 "the effect size has no interval and no reason for that")
        else:
            need(effect == "estimate" or has_text(r.get("no_effect_size")), "a p-value without an effect size or the reason")
    return problems


def check_families(content: dict, run_lines: list) -> tuple:
    problems, details, families = [], [], content.get("families") or {}
    by_family: dict = {}
    for line in run_lines:
        if "id" in line and line.get("p") is not None:
            by_family.setdefault(line["family"], []).append(line)
    for name, lines in by_family.items():
        if len(lines) < 2:
            continue
        family = families.get(name)
        if not family:
            problems.append(f"family {name}: {len(lines)} tests and no correction")
            continue
        ids, stored = [line["id"] for line in lines], family.get("p_adjusted") or {}
        if family.get("m") != len(lines) or set(stored) != set(ids):
            problems.append(f"family {name}: corrected over {family.get('m')} tests, the ledger holds {len(lines)} "
                            f"({', '.join(ids)})")
            continue
        key = METHODS.get(str(family.get("method")).lower())
        if key and family.get("adjusted_by") != "the test procedure":
            for test_id, expected in zip(ids, adjust([line["p"] for line in lines], key)):
                if not is_number(stored[test_id]) or abs(stored[test_id] - expected) > 1e-9:
                    problems.append(f"family {name}: adjusted p of {test_id} is {stored[test_id]}, {key} gives {expected:.6g}")
            details.append(f"{name}: {key} over {len(lines)} tests, recomputed")
        else:
            details.append(f"{name}: {family.get('method')} over {len(lines)} tests, adjusted by the procedure, not recomputed")
        for r in content["results"]:
            if r.get("family") == name and r.get("p") is not None and r.get("p_adjusted") != stored.get(r["id"]):
                problems.append(f"{r['id']}: p_adjusted is missing or differs from the family's value")
    return problems, details


def check_ledger(content: dict, ledger: list) -> tuple:
    run = content.get("run")
    lines = [line for line in ledger if line.get("run") == run]
    tests = [line for line in lines if "id" in line]
    if not tests:
        return ["ledger.jsonl holds no analysis of this run: the tests run cannot be counted"], [], lines
    kept = [line["id"] for line in tests if line.get("status") == "kept"]
    results = [r.get("id") for r in content["results"]]
    problems = [f"{line['id']}: dropped without a reason" for line in tests
                if line.get("status") == "dropped" and not has_text(line.get("reason"))]
    if sorted(kept) != sorted(results):
        problems.append(f"the ledger's kept analyses ({', '.join(kept)}) are not the results ({', '.join(results)})")
    now = {line["id"] for line in tests}
    earlier = sorted({line["id"] for line in ledger if "id" in line and line.get("run") != run} - now)
    dropped = [line["id"] for line in tests if line.get("status") == "dropped"]
    details = [f"run {run}: {len(kept)} kept, {len(dropped)} dropped" + (f" ({', '.join(dropped)})" if dropped else "")]
    if earlier:
        details.append(f"in earlier runs only: {', '.join(earlier)}. Say why they were removed, or report them")
    return problems, details, lines


def check_hashes(record: dict, script) -> tuple:
    rows = []
    for role, entry in [("script", record.get("script") or {})] + [("data", e) for e in record.get("data") or []]:
        path = Path(str(entry.get("path", "")))
        state = "not_checked" if not path.is_file() else "ok" if sha256(path) == entry.get("sha256") else "drift"
        rows.append((role, str(path), state))
    if script and script.is_file() and sha256(script) != (record.get("script") or {}).get("sha256"):
        rows.append(("script", str(script), "drift"))
    states = {state for _, _, state in rows}
    return ("drift" if "drift" in states else "not_checked" if "not_checked" in states else "ok"), rows


def lint_script(path: Path, record: dict) -> tuple:
    """Findings about the analysis script; ("not_checked", [reason]) when it cannot be parsed."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, ValueError) as exc:
        return "not_checked", [f"{path} could not be read as Python ({type(exc).__name__}): nothing was linted"]
    findings, generators = [], 0

    def dotted(node) -> str:
        parts = []
        while isinstance(node, ast.Attribute):
            parts.append(node.attr)
            node = node.value
        return ".".join(reversed(parts + ([node.id] if isinstance(node, ast.Name) else [])))

    def is_none(node) -> bool:
        return isinstance(node, ast.Constant) and node.value is None

    def has(call, *names) -> bool:          # the keyword is given, or **kwargs may give it
        return any(k.arg is None or k.arg in names for k in call.keywords)

    strings = {t.id: n.value for n in ast.walk(tree) if isinstance(n, ast.Assign) for t in n.targets
               if isinstance(t, ast.Name)}

    def path_of(node, depth=0):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return os.path.normpath(node.value)
        if isinstance(node, ast.Name) and node.id in strings and depth < 3:
            return path_of(strings[node.id], depth + 1)
        if isinstance(node, ast.Call) and dotted(node.func).endswith("Path") and node.args:
            return path_of(node.args[0], depth + 1)
        return None

    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)]
    reads, writes, names = set(), {}, {dotted(c.func) for c in calls}
    for call in calls:
        name = dotted(call.func)
        last = name.rsplit(".", 1)[-1]
        if name in ("np.random.seed", "numpy.random.seed", "random.seed"):
            findings.append(f"line {call.lineno}: {name}() sets a global seed; create a generator "
                            "(rng = numpy.random.default_rng(SEED)) and pass it on")
        elif last in GENERATORS:
            generators += 1
            if not ((call.args and not is_none(call.args[0])) or
                    any(k.arg is None or (k.arg in ("seed", "x") and not is_none(k.value)) for k in call.keywords)):
                findings.append(f"line {call.lineno}: {name}() creates a generator without a seed")
        elif GLOBAL_DRAW.match(name):
            findings.append(f"line {call.lineno}: {name}() draws from the global random state; draw from a seeded generator")
        elif last in RESAMPLERS and not has(call, "random_state", "rng"):
            findings.append(f"line {call.lineno}: {last}() without rng= or random_state=: its resamples differ on every run")
        elif last == "ttest_ind" and not has(call, "equal_var"):
            findings.append(f"line {call.lineno}: ttest_ind() without equal_var runs Student's t test, the library "
                            "default; pass equal_var=False, or equal_var=True with the reason in notes")
        targets = [path_of(node) for node in ([call.func.value] if isinstance(call.func, ast.Attribute) else [])
                   + call.args[:1] + [k.value for k in call.keywords if k.arg in ("path_or_buf", "fname", "path", "file")]]
        if last == "open":
            builtin = isinstance(call.func, ast.Name)
            positional = call.args[1:2] if builtin else call.args[:1]
            mode = next((k.value for k in call.keywords if k.arg == "mode"), positional[0] if positional else None)
            writing = isinstance(mode, ast.Constant) and isinstance(mode.value, str) and any(c in mode.value for c in "wax+")
            target = path_of(call.args[0]) if builtin and call.args else None if builtin else path_of(call.func.value)
            if target and writing:
                writes.setdefault(target, call.lineno)
            elif target:
                reads.add(target)
        elif last in READERS:
            reads.update(t for t in targets if t)
        elif last in WRITERS:
            for target in targets:
                if target:
                    writes.setdefault(target, call.lineno)
    if generators and record and record.get("seed") is None:
        findings.append("the script creates a random generator but finish() recorded no seed: pass seed=SEED")
    inputs = reads | {os.path.normpath(str(e.get("path", ""))) for e in (record or {}).get("data") or []}
    for target, line in writes.items():
        if target in inputs:
            findings.append(f"line {line}: writes to {target}, a file the analysis reads; write results to a new file")
    docstrings = {id(n.body[0].value) for n in ast.walk(tree)
                  if isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n.body
                  and isinstance(n.body[0], ast.Expr)}
    for node in ast.walk(tree):
        if isinstance(node, (ast.List, ast.Tuple, ast.Set, ast.Dict)):
            inside = list(ast.walk(node))
            literal = all(isinstance(n, (ast.List, ast.Tuple, ast.Set, ast.Dict, ast.Constant, ast.UnaryOp, ast.USub,
                                         ast.UAdd, ast.Load)) for n in inside)
            count = sum(1 for n in inside if isinstance(n, ast.Constant) and is_number(n.value))
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings:
            literal = node.value.count("\n") >= 3
            count = len(re.findall(r"\d+(?:\.\d+)?", node.value))
        else:
            continue
        if literal and count >= TYPED_DATA_MIN:
            findings.append(f"line {node.lineno}: a literal with {count} numbers typed into the script; read data from a file")
            break
    module = next((a.asname or a.name for n in ast.walk(tree) if isinstance(n, ast.Import)
                   for a in n.names if a.name == "rz_results"), None)
    imported = {a.asname or a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module == "rz_results"
                for a in n.names}
    for function in ("record", "finish"):
        if f"{module}.{function}" not in names and not (function in imported and function in names):
            findings.append(f"the script never calls rz_results.{function}(): its numbers are not in results.json"
                            if function == "record" else "the script never calls rz_results.finish(): no hashes were stored")
    return ("fail" if findings else "ok"), findings


def candidates(content: dict, power) -> list:
    """Every recorded number as (value, kind, result id, path)."""
    found = []

    def leaves(node, owner, path, kind="value"):
        if isinstance(node, dict):
            for key, item in node.items():
                leaves(item, owner, f"{path}.{key}", "n" if key == "n" or str(key).startswith("n_") else kind)
        elif isinstance(node, list):
            for item in node:
                leaves(item, owner, path, kind)
        elif is_number(node):
            found.append((float(node), kind, owner, path))

    for r in content["results"]:
        for key, kind in (("n", "n"), ("df", "df"), ("p", "p"), ("p_adjusted", "p"), ("estimate", "value"),
                          ("interval", "value"), ("effect_size", "value"), ("descriptives", "value"), ("extra", "value")):
            leaves(r.get(key), r.get("id"), key, kind)
        leaves((r.get("statistic") or {}).get("value"), r.get("id"), "statistic", "statistic")
    for name, family in (content.get("families") or {}).items():
        leaves(family.get("m"), f"family {name}", "m")
        leaves(family.get("p_adjusted"), f"family {name}", "p_adjusted", "p")
    record = content.get("record") or {}
    leaves(record.get("seed"), "record", "seed")
    leaves(record.get("settings"), "record", "settings")
    leaves(power, "power", "power")
    return found


def scan_text(path: Path, found: list, versions: dict, labels=LABELS) -> tuple:
    """Rows (where, printed, status, recorded) for every number in the text, and the ignored counts."""
    text = path.read_text(encoding="utf-8").replace("−", "-")
    text = re.sub(r"[⁰¹²³⁴⁵⁶⁷⁸⁹⁻]+", lambda m: "^" + m.group(0).translate(str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹⁻", "0123456789-")), text)
    for pattern in BLANKED:
        text = re.sub(pattern, lambda m: re.sub(r"[^\n]", " ", m.group(0)), text, flags=re.S if pattern[0] in "`<" else 0)
    rows, ignored = [], Counter()

    def where(offset: int) -> str:
        return f"{path.name}:{text.count(chr(10), 0, offset) + 1}"

    for name, version in versions.items():
        for m in re.finditer(rf"(?i)\b{re.escape(name)}\b\s*\(?(?:version\s*|v\.?\s*)?(\d+(?:\.\d+)+)", text):
            same = version == m.group(1) or str(version).startswith(m.group(1) + ".")
            rows.append((where(m.start()), f"{name} {m.group(1)}", "matched" if same else "mismatch", f"record: {name} {version}"))
            text = text[:m.start(1)] + " " * len(m.group(1)) + text[m.end(1):]

    def show(c) -> str:
        return f"{c[2]}.{c[3]} = " + (str(int(c[0])) if c[0].is_integer() and abs(c[0]) < 1e15 else f"{c[0]:.6g}")

    def distance(c, token) -> float:
        # A printed minus sign must match the recorded sign; an unsigned number may carry its direction in words
        # ("shorter by 9.1 min" for an estimate of -9.1).
        value = c[0] if token["signed"] else abs(c[0])
        return min(abs(value * s - token["value"]) for s in ((1, 100) if token["percent"] else (1,)))

    start = 0
    for end in [m.start() for m in SENTENCE_END.finditer(text)] + [len(text)]:
        tokens = []
        for m in NUMBER.finditer(text, start, end):
            line_start = text.rfind("\n", 0, m.start()) + 1
            before, after = text[line_start:m.start()], text[m.end():m.end() + 8]
            digits = m.group(2).replace(",", "")
            label = next(((kind, rx.search(before)) for kind, rx in labels if rx.search(before)), (None, None))
            whole = m.group(3) is None and not m.group(4) and not m.group(5)
            if text[m.end():m.end() + 1] == "." and text[m.end() + 1:m.end() + 2].isdigit():
                ignored["version-like number"] += 1
            elif after[:1].isalpha() or (before[-1:] == "-" and before[-2:-1].isalpha()):
                ignored["part of a name"] += 1
            elif re.match(r"\s*[×x]\s*\d", after) or re.search(r"\d\s*[×x]\s*$", before):
                ignored["table size"] += 1
            elif label[0] is None and REFERENCE.search(before):
                ignored["figure, table or section number"] += 1
            elif label[0] is None and whole and not m.group(6) and len(digits) == 4 and 1900 <= int(digits) <= 2100:
                ignored["year"] += 1
            else:
                exponent = int(m.group(4) or m.group(5) or 0)
                tokens.append({"where": where(m.start()), "printed": m.group(0).strip(), "kind": label[0],
                               "op": label[1].group(1) if label[0] == "p" else "=", "signed": bool(m.group(1)),
                               "value": (-1 if m.group(1) else 1) * float(digits) * 10 ** exponent,
                               "tolerance": 0.5 * 10 ** (exponent - len(m.group(3) or "")) * (1 + 1e-9),
                               "percent": bool(m.group(6)), "decimal": not whole or bool(m.group(6))})
        for token in tokens:
            pool = [c for c in found if c[1] == token["kind"]] if token["kind"] else found
            x = token["value"]
            if token["op"] in "<≤":
                hits = [c for c in pool if c[0] < x or (token["op"] == "≤" and c[0] == x)]
            elif token["op"] in ">≥":
                hits = [c for c in pool if c[0] > x or (token["op"] == "≥" and c[0] == x)]
            else:
                hits = [c for c in pool if distance(c, token) <= token["tolerance"]]
                if token["signed"] and not hits:
                    unsigned = dict(token, signed=False, value=-x)
                    token["flipped"] = [c for c in pool if distance(c, unsigned) <= token["tolerance"]]
            if token["kind"] == "p" and x == 0:
                hits, token["note"] = [], "a p-value is never zero: print p < 0.001"
            elif token["op"] != "=" and hits and x > 0.001:
                token["note"] = "print the exact p-value"
            elif token.get("flipped"):
                token["note"] = "the recorded value has the opposite sign"
            token.update(hits=hits, pool=pool)
        owners = Counter(owner for token in tokens for owner in {c[2] for c in token["hits"]})
        anchor = owners.most_common(1)[0][0] if owners and owners.most_common(1)[0][1] >= 2 else None
        for token in tokens:
            note = f" ({token['note']})" if token.get("note") else ""
            def rank(c, token=token):          # the sentence's own result first, then the closest value
                return (c[2] != anchor, token["decimal"] and c[1] in ("df", "n"), distance(c, token))
            if token["hits"]:
                best = min(token["hits"], key=rank)
                rows.append((token["where"], token["printed"], "matched", show(best) + note))
                continue
            nearest = min(token.get("flipped") or token["pool"], key=rank, default=None)
            status = "mismatch" if token["kind"] or (token["decimal"] and (anchor or token.get("flipped"))) else "not_found"
            rows.append((token["where"], token["printed"], status,
                         (f"nearest: {show(nearest)}" if nearest else f"no recorded {token['kind'] or 'value'}") + note))
        start = end
    return sorted(rows, key=lambda row: int(row[0].rsplit(":", 1)[1])), ignored


def main(argv=None, extend=None) -> int:
    parser = argparse.ArgumentParser(description="Check results.json, the ledger, the analysis script and the text.")
    parser.add_argument("--dir", default="statistics", help="Folder with results.json and ledger.jsonl (default: statistics)")
    parser.add_argument("--script", type=Path, help="The analysis script, to lint it")
    parser.add_argument("--text", type=Path, nargs="+", default=[], help="Text files written from the results")
    parser.add_argument("--strict", action="store_true", help="Also exit 1 when a number in the text is not_found")
    args = parser.parse_args(argv)
    folder = Path(args.dir)
    try:
        content = json.loads((folder / "results.json").read_text(encoding="utf-8"))
        content["results"] = list(content["results"])
        ledger = [json.loads(line) for line in (folder / "ledger.jsonl").read_text(encoding="utf-8").splitlines()
                  if line.strip()] if (folder / "ledger.jsonl").is_file() else []
        power = [json.loads(path.read_text(encoding="utf-8")) for path in sorted(folder.glob("power*.json"))]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"check_results: could not read {folder / 'results.json'} or its ledger: {exc}", file=sys.stderr)
        return 2
    record = content.get("record")
    checks, problems = {}, []

    def add(name, status, found, detail=""):
        checks[name] = {"status": status, "detail": "; ".join(found[:3] + ([f"and {len(found) - 3} more"] if len(found) > 3 else []))
                        or detail}
        problems.extend(f"{name}: {item}" for item in found if status in ("fail", "drift"))

    found = check_complete(content["results"])
    add("complete", "fail" if found else "ok", found, f"{len(content['results'])} result(s) have every required field")
    ledger_problems, ledger_details, run_lines = check_ledger(content, ledger)
    family_problems, family_details = check_families(content, run_lines)
    add("families", "fail" if family_problems else "ok", family_problems,
        "; ".join(family_details) or "no family has two or more tests")
    add("ledger", "fail" if ledger_problems else "ok", ledger_problems, "; ".join(ledger_details))
    if not record:
        add("hashes", "fail", ["the run did not reach rz_results.finish(): no script or data hashes were stored"])
    else:
        state, rows = check_hashes(record, args.script)
        changed = [f"{role} {path}: {s}" for role, path, s in rows if s != "ok"]
        add("hashes", state, changed, f"{len(rows)} file(s) match their recorded SHA-256")
    if args.script:
        state, found = lint_script(args.script, record)
        add("script", state, found, f"{args.script}: seed, typed data, input overwrite, rz_results and equal_var")
    else:
        add("script", "not_checked", [], "no --script given")
    ext = extend(content, args) if extend else {}
    for name, status, found, detail in ext.get("checks", ()):
        add(name, status, list(found), detail)
    text_rows, ignored = [], Counter()
    for path in args.text:
        if not path.is_file():
            print(f"check_results: no such text file: {path}", file=sys.stderr)
            return 2
        rows, skipped = scan_text(path, candidates(content, power) + list(ext.get("numbers", ())),
                                  {"python": (record or {}).get("python", ""), **((record or {}).get("packages") or {})},
                                  LABELS + tuple(ext.get("labels", ())))
        text_rows += rows
        ignored += skipped
    counts = Counter(status for _, _, status, _ in text_rows)
    if args.text:
        checks["text"] = {"status": "fail" if counts["mismatch"] else "ok",
                          "detail": f"{counts['matched']} matched, {counts['mismatch']} mismatch, {counts['not_found']} "
                                    f"not_found, {sum(ignored.values())} ignored by rule"}
        problems += [f"text: {w} prints {p}: {s} ({r})" for w, p, s, r in text_rows if s != "matched"]
    else:
        checks["text"] = {"status": "not_checked", "detail": "no --text given"}

    lines = [f"# {ext.get('title', 'Statistics check')}", "", f"`{folder / 'results.json'}`: {len(content['results'])} result(s), run {content.get('run')}.",
             "", "| Check | Status | Detail |", "|---|---|---|"]
    lines += [f"| {name} | {c['status']} | {c['detail']} |" for name, c in checks.items()]
    if problems:
        lines += ["", "## To fix or explain", ""] + [f"- {item}" for item in problems]
    if text_rows:
        lines += ["", "## Numbers in the text", "", "| Where | Printed | Status | Recorded |", "|---|---|---|---|"]
        lines += [f"| {w} | {p} | {s} | {r} |" for w, p, s, r in text_rows]
        if ignored:
            lines += ["", "Ignored by rule: " + ", ".join(f"{count} {rule}" for rule, count in sorted(ignored.items())) + "."]
    lines += ["", "A status of not_checked means the check did not run; it is not a pass."]
    (folder / "check.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    failed = any(c["status"] in ("fail", "drift") for c in checks.values()) or (args.strict and counts["not_found"] > 0)
    print(json.dumps({"results": len(content["results"]), "checks": {name: c["status"] for name, c in checks.items()},
                      "text": dict(counts), "problems": problems, "report": str(folder / "check.md"),
                      "exit": int(failed)}, indent=2, ensure_ascii=False))
    return int(failed)


if __name__ == "__main__":
    sys.exit(main())
