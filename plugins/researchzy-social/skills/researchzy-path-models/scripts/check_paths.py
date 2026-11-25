#!/usr/bin/env python3
"""Register model.md before the first estimate; check paths/results.json, the ledger and the text.

  check_paths.py register paths/model.md [--reason "why the model changed"]
  check_paths.py --script paths/analysis.py [--text paths/results.md paths/methods.md] [--dir paths] [--strict]

register appends {"event": "register", "sha256", "time"} for model.md to <dir>/ledger.jsonl, the
ledger of rz_results.py. It refuses a model.md without a design line (cross-sectional,
longitudinal, experimental), a roles table with X and Y, or a ```model block; once estimates
exist, it refuses a changed model without --reason.

The checks of check_results.py (the copy next to this file) run on <dir>/results.json; added:

  registration  registered before the first estimate; model.md has the last registered SHA-256; a
                registration after the first estimate has its reason
  paths         per result with extra["paths"] (path_tools.py): the estimate is a recorded value;
                each defined parameter equals its expression on the recorded coefficients (the
                full-sample a*b, not the mean of the draws); the interval is percentile, bca,
                monte_carlo or quasi_bayesian (bc only on a dropped result) with draws, seed and
                failed draws; every equation has the same n; centring is recorded and b3 is the same
                centred and uncentred; probes lie inside the moderator's observed range;
                Johnson-Neyman bounds or a jn_reason; the index beside conditional indirect effects;
                a sensitivity record for mediation; a structural model converged, with df and fit
  model         a kept model equals a registered ```model block (an OLS result may leave equations
                out), or has its deviation and the run's ledger holds the registered model's fit and
                one fit per change. Writes <dir>/models.md: every model of the run and its changes
  wording       (--text) no full or partial mediation (完全中介, 部分中介), Sobel or Baron-Kenny test as
                evidence, or prove (证明, 证实); moderated mediation only with an index; with a
                cross-sectional design, no causal verb (causes, leads to, increases, drives; 导致, 引起,
                提高, 促进 ...) in a sentence that names two model variables
  probes        (--text) a probe written as k SD from the mean (+1 SD, 高于均值1个标准差) lies inside
                the observed range of a recorded moderator

Labels added to the number check: a (a1, a3), b and B (any unstandardized coefficient or slope), β
(standardized), c′, a·b, ab, indirect effect, 间接效应, index, 指数, CFI, TLI, RMSEA, SRMR.

Writes check.md and models.md and prints a JSON summary. Exit code 1 on a failed check, a mismatch in
the text (with --strict a number not found) or a refused registration; 2 when results.json, the
ledger or model.md cannot be read. Standard library only.
"""

from __future__ import annotations

import argparse
import ast
import json
import operator
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_results as cr  # noqa: E402

DESIGNS = {"cross-sectional": ("cross", "横截面", "截面"), "longitudinal": ("longitud", "纵向", "追踪"),
           "experimental": ("experiment", "实验")}
KINDS = ("equations", "mediation", "moderation", "moderated_mediation", "sem")
INTERVALS = ("percentile", "bca", "monte_carlo", "quasi_bayesian")
OPS = ("=~", "~~", ":=", "~")
BINARY = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}
S, EQ, SPAN = cr.START, r"\s*(?:=|:|为|是|等于)\s*$", r"[^.;=。；\n\d]{0,60}?\s*(?:=|:|为|是|等于|was|is|were|of)\s*$"
LABELS = tuple((kind, re.compile(pattern, flags)) for kind, pattern, flags in (
    ("cfi", rf"{S}CFI{EQ}", 0), ("tli", rf"{S}TLI{EQ}", 0), ("rmsea", rf"{S}RMSEA{EQ}", 0), ("srmr", rf"{S}SRMR{EQ}", 0),
    ("index", rf"(?:{S}index(?![A-Za-z])|指数){SPAN}", re.I),
    ("indirect", rf"(?:(?:{S}a\s*[·×*⋅]\s*b|{S}ab)(?![A-Za-z])|{S}indirect effects?|间接效应){SPAN}", re.I),
    ("c_prime", rf"(?:{S}c\s*['′’]|{S}direct effects?|直接效应){SPAN}", re.I),
    ("a", rf"{S}a[_\d₀-₉]*\s*(?:路径)?(?:系数)?{EQ}", 0), ("b", rf"{S}[bB][_\d₀-₉]*\s*(?:路径)?(?:系数)?{EQ}", 0),
    ("beta", rf"{S}β[_\d₀-₉]*{EQ}", 0)))
CAUSAL = re.compile(r"\b(?:caus(?:e|es|ed|ing)|lead(?:s|ing)?\s+to|led\s+to|result(?:s|ed|ing)?\s+in|driv(?:e|es|en|ing)|"
                    r"drove|increas(?:es|ed)|decreas(?:es|ed)|rais(?:es|ed)|reduc(?:es|ed)|improv(?:es|ed)|promot(?:es|ed)|"
                    r"enhanc(?:es|ed)|boost(?:s|ed)|induc(?:es|ed))\b|导致|引起|造成|引发|提高|提升|促进|增强|增加|降低|减少|驱动", re.I)
FULL_PARTIAL = re.compile(r"\b(?:full|fully|complete|completely|partial|partially|perfect|perfectly)\s+mediat\w*|"
                          r"\bmediat\w*\s+(?:fully|completely|partially)\b|完全中介|部分中介", re.I)
STEPS = re.compile(r"\bSobel\b|\bBaron\s*(?:and|&)\s*Kenny\b|\bBaron[-–]Kenny\b|\bcausal[- ]steps?\b|逐步检验|依次检验|因果步骤", re.I)
DISCLAIMED = re.compile(r"\b(?:instead of|rather than|in place of|(?:did|do|does|was|were|is|are)\s+not\s+(?:use|used|rely|"
                        r"relied|report|reported|run|label|labelled|labeled|classify|classified|call|called|interpret|"
                        r"interpreted))\b|不使用|未使用|没有使用|不采用|未采用|没有采用|不报告|未报告|而非|而不是|不再|取代|代替", re.I)
PROVE = re.compile(r"\bprov(?:e|es|ed|en|ing)\b|证明|证实", re.I)
NEGATED = re.compile(r"\b(?:not|cannot|can't|never|no|neither|nor)\b|不能|无法|并不|并未|不足以|未能|没有|不支持", re.I)
MODERATED = re.compile(r"moderated mediation|mediation\s+(?:was|is|were)\s+moderated|conditional indirect effects?\b[^.]{0,80}?"
                       r"\b(?:differ\w*|stronger|weaker|larger|smaller|depend\w*)|有调节的中介|中介(?:效应|作用)?[^。；]{0,10}?"
                       r"(?:受到?|被)[^。；]{0,10}?调节|条件间接效应[^。；]{0,30}?(?:更强|更弱|更大|更小|不同|差异)", re.I)
SD = re.compile(r"(?<![A-Za-z])(?:SDs?(?![A-Za-z])|S\.D\.|standard deviations?)|标准差", re.I)
K_BEFORE = re.compile(r"([+\-±]|plus|minus|加|减)?\s*(\d+(?:\.\d+)?|one|two|一|两|二)\s*个?\s*$", re.I)
UP, DOWN = re.compile(r"above|高于|以上", re.I), re.compile(r"below|低于|以下", re.I)
SIGNS = {"+": "+", "plus": "+", "加": "+", "-": "-", "minus": "-", "减": "-", "±": "+-"}
WORDS = {"one": 1.0, "two": 2.0, "一": 1.0, "两": 2.0, "二": 2.0}


def parse(text: str) -> list:
    """(lhs, op, [(label, term)]) for each =~ ~~ ~ statement, (name, ":=", expression) for a definition."""
    out = []
    for line in (raw.split("#", 1)[0].strip() for raw in re.split(r"[\n;]", text)):
        op = next((o for o in OPS if o in line), None)
        lhs, _, rhs = line.partition(op or "~")
        if line and (not op or not lhs.strip() or not rhs.strip()):
            raise ValueError(f"not a model statement: {line!r}")
        if line and op == ":=":
            out.append((lhs.strip(), op, rhs.strip()))
        elif line:
            terms = [(label.strip(), ":".join(p.strip() for p in term.split(":")))
                     for label, _, term in (part.strip().rpartition("*") for part in rhs.split("+"))]
            if any(not term for _, term in terms):
                raise ValueError(f"an empty term in {line!r}")
            out.append((lhs.strip(), op, terms))
    return out


def read_model(path) -> dict:
    """The design, the roles table and the ```model blocks of model.md; ValueError names what is missing."""
    text = Path(path).read_text(encoding="utf-8")
    line = re.search(r"(?im)^[\s>*_-]*(?:design|设计)\s*\**\s*[:：]\s*\**\s*(.+)$", text)
    design = next((name for name, words in DESIGNS.items() if line and any(w in line.group(1).lower() for w in words)), None)
    rows, inside = [], False
    for row in text.splitlines():
        cells = [c.strip() for c in row.strip().strip("|").split("|")] if row.lstrip().startswith("|") else None
        inside = bool(cells) and (inside or cells[0].lower() in ("role", "角色"))
        if inside and cells[0].lower() not in ("role", "角色") and not re.fullmatch(r"[\s|:-]*", row):
            rows.append(cells + ["", ""])
    roles = [{"role": c[0], "column": c[1], "names": [n.strip() for n in re.split(r"[;；]", c[2]) if n.strip()]} for c in rows]
    blocks = {m.group(1).strip() or f"model {i + 1}": m.group(2)
              for i, m in enumerate(re.finditer(r"(?ms)^```(?:model|lavaan)[ \t]*([^\n]*)\n(.*?)^```", text))}
    missing = [what for ok, what in ((design, "a design line (Design: cross-sectional, longitudinal or experimental)"),
                                     ({"X", "Y"} <= {r["role"].upper() for r in roles},
                                      "a roles table (| Role | Column | Names in the text |) with X and Y"),
                                     (blocks, "a ```model block with the lavaan-style specification")) if not ok]
    if missing:
        raise ValueError(f"{path} lacks " + "; ".join(missing))
    for block in blocks.values():
        parse(block)
    return {"design": design, "roles": roles, "models": blocks}


def evaluate(expression: str, values: dict):
    """A defined parameter from labelled values with + - * / ( ) and numbers; numbers or numpy arrays."""
    def walk(node):
        if isinstance(node, ast.BinOp) and type(node.op) in BINARY:
            return BINARY[type(node.op)](walk(node.left), walk(node.right))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
            return -walk(node.operand) if isinstance(node.op, ast.USub) else walk(node.operand)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return node.value
        if isinstance(node, ast.Name) and node.id in values:
            return values[node.id]
        raise ValueError(f"{expression!r}: {ast.unparse(node)} is not a recorded label, a number or + - * /")
    try:
        return walk(ast.parse(str(expression).strip(), mode="eval").body)
    except SyntaxError as exc:
        raise ValueError(f"{expression!r} is not an expression") from exc


def atoms(text: str) -> set:
    """One string per path, loading or covariance, without labels; products and covariance pairs sorted."""
    out = set()
    for lhs, op, terms in parse(text):
        for label, term in terms if op != ":=" else ():
            term, fixed = ":".join(sorted(term.split(":"))), f"{label}*" if re.fullmatch(r"[-+.\d]+", label) else ""
            left, right = sorted((lhs, term)) if op == "~~" else (lhs, term)
            out.add(f"{left} {op} {fixed}{right}")
    return out


def changes(fitted: str, blocks: dict, whole: bool) -> list:
    """The shortest list of changes ("+ m1 ~~ y1", "- eng ~ age") from a registered block to the fitted model."""
    mine, best = atoms(fitted), None
    heads = {" ".join(x.split(" ")[:2]) for x in mine}
    for theirs in map(atoms, blocks.values()):
        found = [f"+ {x}" for x in sorted(mine - theirs)] + \
            [f"- {x}" for x in sorted(theirs - mine) if whole or " ".join(x.split(" ")[:2]) in heads]
        best = found if best is None or len(found) < len(best) else best
    return best or []


def paths_of(entry: dict):
    found = (entry.get("extra") or {}).get("paths")
    return found if isinstance(found, dict) else None


def close(x, y) -> bool:
    return cr.is_number(x) and cr.is_number(y) and abs(x - y) <= 1e-6 * max(1.0, abs(x), abs(y))


def row(name, problems, detail, unchecked=()):
    status = "fail" if problems else "not_checked" if unchecked else "ok"
    return name, status, problems, "; ".join(unchecked) if unchecked and not problems else detail


def read_ledger(folder: Path) -> list:
    path = folder / "ledger.jsonl"
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()] if path.is_file() else []


def register(argv) -> int:
    parser = argparse.ArgumentParser(prog="check_paths.py register", description="Register model.md before estimating.")
    parser.add_argument("model", type=Path, nargs="?", help="model.md (default: <dir>/model.md)")
    parser.add_argument("--dir", default="paths", help="Folder of the ledger (default: paths)")
    parser.add_argument("--reason", default="", help="Why the model changed; required once estimates exist")
    args = parser.parse_args(argv)
    folder = Path(args.dir)
    path = args.model or folder / "model.md"
    try:
        model, ledger = read_model(path), read_ledger(folder)
    except (OSError, ValueError) as exc:
        print(f"check_paths register: {exc}", file=sys.stderr)
        return 2
    digest, estimated = cr.sha256(path), any("id" in x for x in ledger)
    earlier = [x for x in ledger if x.get("event") == "register"]
    if earlier and earlier[-1].get("sha256") == digest:
        print(json.dumps({"registered": False, "why": "unchanged since its registration", **earlier[-1]}, ensure_ascii=False))
        return 0
    if estimated and not args.reason.strip():
        print("check_paths register: estimates exist already, so a new model is a deviation: give --reason", file=sys.stderr)
        return 1
    entry = {"time": datetime.now(timezone.utc).isoformat(timespec="seconds"), "event": "register", "path": path.as_posix(),
             "sha256": digest, "design": model["design"], "models": list(model["models"]),
             "reason": args.reason.strip() or None, "after_estimates": estimated}
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / "ledger.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print(json.dumps({"registered": True, **entry}, indent=2, ensure_ascii=False))
    return 0


def check_registration(folder: Path, ledger: list):
    marks = [(i, x) for i, x in enumerate(ledger) if x.get("event") == "register"]
    first = next((i for i, x in enumerate(ledger) if "id" in x), len(ledger))
    if not marks:
        return row("registration", [f"{folder / 'model.md'} was never registered: run check_paths.py register before the "
                                    "first estimate"], "")
    problems = [f"registered at {x.get('time')}, after the first estimate, without a reason" for i, x in marks
                if i > first and not cr.has_text(x.get("reason"))]
    last = marks[-1][1]
    path = Path(str(last.get("path") or folder / "model.md"))
    if not path.is_file() or cr.sha256(path) != last.get("sha256"):
        problems.append(f"{path} is missing or changed after its registration at {last.get('time')}: register the new "
                        "version with --reason, or restore the registered one")
    late = [f"{x.get('time')} ({x.get('reason')})" for i, x in marks if i > first]
    return row("registration", problems, f"first registered at {marks[0][1].get('time')}, " + (
        "before" if marks[0][0] < first else "after") + " the first estimate" + (f"; later: {'; '.join(late)}" if late else ""))


def check_fields(results: list):
    problems, seen = [], 0
    for r in (r for r in results if paths_of(r)):
        p, seen = paths_of(r), seen + 1

        def need(ok, message, rid=r.get("id")):
            if not ok:
                problems.append(f"{rid}: {message}")
        kind, defined = p.get("kind"), {k: d for k, d in (p.get("defined") or {}).items() if isinstance(d, dict)}
        need(kind in KINDS, f"kind {kind!r} is not one of {', '.join(KINDS)}")
        need(kind not in ("mediation", "moderated_mediation") or defined, "no defined parameter (ind := a*b)")
        if p.get("status") == "not_checked":
            need(False, f"kept although not run ({p.get('reason')}): record it with kept=False and the reason")
            continue
        coefficients = {k: c.get("value") for k, c in (p.get("coefficients") or {}).items() if isinstance(c, dict)}
        estimate = (r.get("estimate") or {}).get("value")
        need(any(close(estimate, v) for v in [*coefficients.values(), *(d.get("estimate") for d in defined.values())]),
             f"the estimate {estimate} is no recorded coefficient or defined parameter")
        ns = {name: e.get("n") for name, e in (p.get("equations") or {}).items() if isinstance(e, dict)}
        need(len(set(ns.values())) <= 1, "equations on different rows (n " + ", ".join(f"{k} {v}" for k, v in ns.items()) +
             "): fit them together with path_tools, so that every equation uses the same rows")
        for name, d in defined.items():
            try:
                value = evaluate(d.get("expression"), coefficients)
            except (ValueError, TypeError, ZeroDivisionError) as exc:
                need(False, f"{name}: {exc}")
                continue
            need(close(d.get("estimate"), value), f"{name} = {d.get('estimate')}, but {d.get('expression')} on the recorded "
                 f"coefficients is {value:.6g}: report the full-sample value, not the mean of the bootstrap draws")
            need(cr.is_number(d.get("low")) and cr.is_number(d.get("high")) or cr.has_text(d.get("note")),
                 f"{name} has no interval and no note on why")
        interval = p.get("interval") or {}
        need(not defined or interval.get("method") in INTERVALS, f"interval method {interval.get('method')!r}: use percentile "
             "or bca, or monte_carlo or quasi_bayesian for what a package ran; a plain bc interval goes on a dropped result")
        need(not defined or all(isinstance(interval.get(k), int) for k in ("draws", "seed", "failed")),
             "the interval lacks its number of draws, seed or failed draws")
        w, probe = p.get("moderator") or {}, p.get("probe") or {}
        if kind in ("moderation", "moderated_mediation"):
            need(isinstance((p.get("centring") or {}).get("columns"), dict) and cr.has_text((p.get("centring") or {}).get(
                "around")), "centring is not recorded: the columns centred and around which mean, or 'not centred'")
            ranged = cr.is_number(w.get("min")) and cr.is_number(w.get("max"))
            need(ranged, "the moderator's observed min and max are not recorded")
            for label, at in [(s.get("label"), s.get("w")) for s in probe.get("slopes") or []] + \
                    [(name, d.get("at")) for name, d in defined.items() if "at" in d]:
                need(not ranged or (cr.is_number(at) and w["min"] - 1e-9 <= at <= w["max"] + 1e-9), f"probe {label} = {at} "
                     f"lies outside the observed range {w.get('min')} to {w.get('max')} of {w.get('column')}: probe inside it")
        if kind == "moderation":
            need(isinstance(probe.get("jn"), dict) or cr.has_text(p.get("jn_reason")), "no Johnson-Neyman bounds, no jn_reason")
            need(p.get("b3_uncentred") is None or close(probe.get("b3"), p.get("b3_uncentred")),
                 f"b3 is {probe.get('b3')} centred and {p.get('b3_uncentred')} uncentred: centring subtracts a constant "
                 "and leaves b3 and its test unchanged; check the centring (a mean taken within each case gives zeros)")
        if kind == "moderated_mediation" or any("at" in d for d in defined.values()):
            index = defined.get(p.get("index")) if isinstance(p.get("index"), str) else None
            need(isinstance(index, dict) and cr.is_number(index.get("low")) and cr.is_number(index.get("high")),
                 "conditional indirect effects without the index of moderated mediation and its interval")
        if kind in ("mediation", "moderated_mediation"):
            s = p.get("sensitivity") or {}
            need(s.get("status") == "done" or (s.get("status") == "not_done" and cr.has_text(s.get("reason"))),
                 "no sensitivity record: run it, or record sensitivity={'status': 'not_done', 'reason': ...}")
        if kind == "sem":
            need(p.get("converged") is True, "the structural model did not converge: report no estimate from it")
            need(isinstance(p.get("df"), int) and p["df"] >= 0 and isinstance(p.get("fit"), dict), "df or fit is missing")
    return row("paths", problems, f"{seen} path result(s) checked", [] if seen else ["no result has extra['paths']"])


def check_models(content: dict, ledger: list, folder: Path, model, error):
    if model is None:
        return row("model", [], "", [f"model.md could not be read: {error}"])
    fits = [x for x in ledger if x.get("run") == content.get("run") and isinstance((paths_of(x) or {}).get("model"), str)]
    for x in fits:
        try:
            x["changes"] = changes(paths_of(x)["model"], model["models"], "=~" in paths_of(x)["model"] or
                                   paths_of(x).get("kind") == "sem")
        except ValueError as exc:
            x["changes"] = [f"unreadable model: {exc}"]
    problems, lines = [], ["# Models", "", "Written by check_paths.py from the last run in ledger.jsonl: every model fitted, "
                           "kept or dropped, and its changes from the registered model.", "", "| Result | Kind | Status | n "
                           "| Estimate | Fit | Changes from the registered model |", "|---|---|---|---|---|---|---|"]
    for x in fits:
        p, n, found = paths_of(x), x.get("n"), x["changes"]
        if x.get("status") == "kept" and found and not cr.has_text(p.get("deviation")):
            problems.append(f"{x['id']}: differs from the registered model ({'; '.join(found[:4])}): give the reason in "
                            "extra['paths']['deviation']")
        earlier = [y for y in fits if y is not x and len(y["changes"]) < len(found)]
        if x.get("status") == "kept" and found and (len(earlier) < len(found) or all(y["changes"] for y in fits)):
            problems.append(f"{x['id']}: {len(found)} change(s) from the registered model, but this run's ledger holds "
                            f"{len(earlier)} earlier fit(s): record the registered model's fit and each re-specification "
                            "(kept=False with the reason)")
        lines.append(table_row(x, p, n, found))
    if fits:
        (folder / "models.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    kept = sum(1 for x in fits if x.get("status") == "kept" and x["changes"])
    return row("model", problems, f"{len(fits)} fit(s) in this run, listed in models.md; {kept} kept model(s) deviate",
               [] if fits else ["no fitted model in this run"])


def table_row(x: dict, p: dict, n, found: list) -> str:
    fit = p.get("fit") or {}
    fit = ", ".join(f"{k.upper()} {fit[k]:.3g}" for k in ("cfi", "rmsea", "srmr") if cr.is_number(fit.get(k)))
    cells = [x["id"], p.get("kind"), "kept" if x.get("status") == "kept" else f"dropped: {x.get('reason')}",
             ", ".join(f"{k} {v}" for k, v in n.items()) if isinstance(n, dict) else n,
             f"{x['estimate']:.4g}" if cr.is_number(x.get("estimate")) else "—", f"{fit}, df {p.get('df')}" if fit else "—",
             ("; ".join(found) or "none") + (f" (reason: {p['deviation']})" if p.get("deviation") else "")]
    return "| " + " | ".join(map(str, cells)) + " |"


def sentences(path: Path):
    """(where, sentence) for a text read as check_results.py reads it: full-width forms as ASCII, code blanked."""
    text = path.read_text(encoding="utf-8").replace("−", "-").translate(cr.FULL_WIDTH)
    for pattern in cr.BLANKED:
        text = re.sub(pattern, lambda m: re.sub(r"[^\n]", " ", m.group(0)), text, flags=re.S if pattern[0] in "`<" else 0)
    start = 0
    for end in [m.start() for m in cr.SENTENCE_END.finditer(text)] + [len(text)]:
        lead = len(text[start:end]) - len(text[start:end].lstrip())
        yield f"{path.name}:{text.count(chr(10), 0, start + lead) + 1}", text[start:end]
        start = end


def first(rx, sentence: str, reach: int):
    """The first match of rx that no negation precedes within reach characters."""
    return next((m for m in rx.finditer(sentence) if not NEGATED.search(sentence[:m.start()][-reach:])), None)


def check_wording(texts: list, results: list, model, error):
    roles = [re.compile(r"(?<![A-Za-z])(?:" + "|".join(map(re.escape, sorted(r["names"], key=len, reverse=True))) +
                        r")(?![A-Za-z])", re.I) for r in (model or {}).get("roles", []) if r["names"]]
    cross, problems = (model or {}).get("design") == "cross-sectional", []
    indexed = any(isinstance((paths_of(r) or {}).get("index"), str) for r in results)
    for where, sentence in (s for path in texts for s in sentences(path)):
        verb = first(CAUSAL, sentence, 40)
        if cross and verb and sum(1 for rx in roles if rx.search(sentence)) >= 2:
            problems.append(f"{where}: '{verb.group(0)}' joins two model variables in a cross-sectional design: write 'was "
                            "associated with' or 'is consistent with'")
        for rx, what in ((FULL_PARTIAL, "report the indirect and direct effects with their intervals, not a label that "
                          "depends on sample size"), (STEPS, "report the bootstrap interval of the indirect effect")):
            found = rx.search(sentence)
            if found and not DISCLAIMED.search(sentence):
                problems.append(f"{where}: '{found.group(0)}' given as evidence: {what}")
        if first(PROVE, sentence, 30):
            problems.append(f"{where}: '{first(PROVE, sentence, 30).group(0)}': estimates can be consistent with a model, "
                            "never prove it")
        found = MODERATED.search(sentence)
        if found and not indexed and not NEGATED.search(sentence):
            problems.append(f"{where}: '{found.group(0)}' without a recorded index of moderated mediation and its interval")
    return row("wording", problems, "no full or partial mediation, Sobel, Baron-Kenny or prove; no claim of moderated "
               "mediation without the index" + ("; no causal verb between model variables" if cross else ""),
               ["no --text given"] if not texts else [] if model else [f"causal verbs not checked: {error}"])


def check_probes(texts: list, results: list):
    moderators = {m.get("column"): m for m in ((paths_of(r) or {}).get("moderator") or {} for r in results)
                  if all(cr.is_number(m.get(k)) for k in ("min", "max", "mean", "sd"))}
    problems, mentions = [], 0
    for where, sentence in (s for path in texts for s in sentences(path)):
        for m in SD.finditer(sentence):
            k = K_BEFORE.search(sentence[max(0, m.start() - 30):m.start()])
            near = sentence[max(0, m.start() - 30):m.end() + 20]
            signs = SIGNS.get((k.group(1) or "").lower()) if k else None
            signs = signs or ("+" if UP.search(near) else "") + ("-" if DOWN.search(near) else "")
            if not k or not signs:
                continue
            mentions += 1
            size = WORDS.get(k.group(2).lower()) or float(k.group(2))
            for column, w in moderators.items():
                for value, sign in ((w["mean"] + size * w["sd"] * (1 if s == "+" else -1), s) for s in signs):
                    if not w["min"] - 1e-9 <= value <= w["max"] + 1e-9:
                        problems.append(f"{where}: {sign}{size:g} SD of {column} is {value:.4g}, outside its observed range "
                                        f"{w['min']:g} to {w['max']:g}: probe inside the range")
    unchecked = ["no --text given"] if not texts else ["the text probes at k SD, but no moderator range is recorded"] \
        if mentions and not moderators else []
    return row("probes", problems, f"{mentions} probe(s) written as k SD lie inside the observed range", unchecked)


def numbers(results: list) -> list:
    """Labelled values the text may print: (value, kind, owner, path)."""
    out = []
    for r in results:
        p = paths_of(r) or {}

        def add(value, kind, where, r=r):
            if cr.is_number(value):
                out.append((float(value), kind, r.get("id"), f"extra.paths.{where}"))
        for key, c in ((k, c) for k, c in (p.get("coefficients") or {}).items() if isinstance(c, dict)):
            for kind in ["b"] + (["a"] if key.startswith("a") else []) + (["c_prime"] if key.startswith("c") else []):
                add(c.get("value"), kind, f"coefficients.{key}.value")
            for field, kind in (("std", "beta"), ("p", "p"), ("t", "statistic"), ("z", "statistic")):
                add(c.get(field), kind, f"coefficients.{key}.{field}")
        for name, d in ((k, d) for k, d in (p.get("defined") or {}).items() if isinstance(d, dict)):
            add(d.get("estimate"), "index" if name == p.get("index") else "indirect", f"defined.{name}.estimate")
        for name, e in ((k, e) for k, e in (p.get("equations") or {}).items() if isinstance(e, dict)):
            add(e.get("df_resid"), "df", f"equations.{name}.df_resid")
        for s in (p.get("probe") or {}).get("slopes") or []:
            for field, kind in (("slope", "b"), ("t", "statistic"), ("p", "p")):
                add(s.get(field), kind, f"probe.{s.get('label')}.{field}")
        for key in ("cfi", "tli", "rmsea", "srmr", "chi2", "chi2_p"):
            add((p.get("fit") or {}).get(key), {"chi2": "statistic", "chi2_p": "p"}.get(key, key), f"fit.{key}")
        add((p.get("probe") or {}).get("df"), "df", "probe.df")
        add(p.get("df"), "df", "df")
    return out


def extend(content: dict, args) -> dict:
    folder, results, texts = Path(args.dir), content["results"], [p for p in args.text if p.is_file()]
    ledger = read_ledger(folder)
    try:
        model, error = read_model(folder / "model.md"), None
    except (OSError, ValueError) as exc:
        model, error = None, str(exc)
    rows = [check_registration(folder, ledger), check_fields(results), check_models(content, ledger, folder, model, error),
            check_wording(texts, results, model, error), check_probes(texts, results)]
    return {"title": "Path model check", "checks": rows, "numbers": numbers(results), "labels": LABELS}


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["register"]:
        return register(argv[1:])
    if "-h" in argv or "--help" in argv:
        print(__doc__)
        return 0
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--dir", default="paths")
    own, rest = parser.parse_known_args(argv)
    return cr.main(["--dir", own.dir, *rest], extend=extend)


if __name__ == "__main__":
    sys.exit(main())
