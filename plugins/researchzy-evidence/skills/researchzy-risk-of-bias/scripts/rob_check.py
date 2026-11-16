#!/usr/bin/env python3
"""Check risk-of-bias assessments against the tool registered for the review and the saved texts,
and export the tables.

  rob_check.py hash FILE...                       SHA-256 of files, to record in the JSON files
  rob_check.py check [--dir risk-of-bias]         tool.json, assessments.json and the texts
  rob_check.py export [--dir risk-of-bias]        robvis-<tool>-<outcome>.csv, table.md, quotes.md

check: the tool is registered (name, version, date read, a source file whose SHA-256 still
matches or a web address, vocabularies, the overall rule with its locator); each text keeps its
SHA-256 and a full text has 400 words; every study x outcome x domain has a judgement, and every
signalling question an answer, from the vocabularies; every quote has a locator and five words
or more and is graded EXACT or INTERLEAVED in the study's texts by quote_match (PARTIAL and
ABSENT fail); every domain has such a quote or no_information.searched; the overall judgement
follows the rule (worst; worst_or_higher, a worse one with a reason; none); where a mapping is
registered the judgement is one its first matching rule allows (or departs_from_mapping says
why), elsewhere that check is not_checked, never ok.

The formats are in references/tools.md and references/assessing.md. A relative path inside them
is read from --dir, then from the working directory. Writes check.md, or the robvis CSVs,
table.md and quotes.md, in --dir and prints a JSON summary. Exit code 1 when a check fails
(export then writes nothing); 2 when an input file is missing or is not valid JSON. rob_plot.py
and sof_check.py import their shared helpers from this file. Standard library only.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from quote_match import match_quality, tokens  # noqa: E402

RULES = ("worst", "worst_or_higher", "none")
TEXT_KINDS = ("full_text", "abstract", "protocol", "registration", "supplement", "other")
GRADES = ("ABSENT", "PARTIAL", "INTERLEAVED", "EXACT")
PASSING = ("INTERLEAVED", "EXACT")
MIN_QUOTE_TOKENS = 5            # a shorter quote matches somewhere in most papers
MIN_FULL_TEXT_TOKENS = 400      # below this a "full text" is an abstract or a failed extraction
PAGE_MARK = re.compile(r"^[ \t]*(?:\[\[page (\d+)\]\]|=+ PAGE (\d+) =+)[ \t]*$", re.M | re.I)


def die(message: str):
    print(message, file=sys.stderr)
    raise SystemExit(2)


def load(path: Path, parse_float=None):
    if not path.is_file():
        die(f"{path} does not exist.")
    try:
        return json.loads(path.read_text(encoding="utf-8"), parse_float=parse_float)
    except (ValueError, UnicodeDecodeError) as exc:
        die(f"{path} is not valid JSON: {exc}")


def txt(value) -> str:
    return value.strip() if isinstance(value, str) else ""


def obj(value) -> dict:
    return value if isinstance(value, dict) else {}


def dicts(value) -> list:
    return [v for v in value if isinstance(v, dict)] if isinstance(value, list) else []


def strs(value):
    """A string or a non-empty list of strings, as a list; None for anything else."""
    value = [value] if isinstance(value, str) else value
    return value if isinstance(value, list) and value and all(isinstance(v, str) for v in value) else None


def at(base: Path, name: str) -> Path:
    path = Path(name)
    return path if path.is_absolute() or (not (base / path).exists() and path.exists()) else base / path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def row(*values) -> str:
    """A Markdown table row."""
    return "| " + " | ".join(re.sub(r"\s+", " ", str(v if v is not None else "")).replace("|", "/") for v in values) + " |"


# ---------------------------------------------------------------------------------------------
# The tool


def prepare(raw: dict) -> dict:
    judgements = [(txt(j.get("id")), txt(j.get("label")), bool(j.get("no_information")))
                  for j in dicts(raw.get("judgements")) if txt(j.get("id"))]
    overall = obj(raw.get("overall"))
    domains = [{"id": txt(d.get("id")), "name": txt(d.get("name")),
                "questions": [i for i in (txt(q) or txt(obj(q).get("id")) for q in d.get("questions") or []) if i]}
               for d in dicts(raw.get("domains"))]
    ranked = [j for j, _, ni in judgements if not ni]                     # best first
    return {"raw": raw, "id": txt(raw.get("id")), "domains": domains, "n_judgements": len(judgements),
            "answers": {a for a in raw.get("answers") or [] if isinstance(a, str)},
            "rank": {j: i for i, j in enumerate(ranked)},
            "ni": {j for j, _, ni in judgements if ni},
            "labels": {j: label or j for j, label, _ in judgements},
            "rule": txt(overall.get("rule")), "rule_locator": txt(overall.get("locator")),
            "mapping": obj(raw.get("mapping"))}


def read_tools(base: Path) -> list:
    data = load(base / "tool.json")
    data = data.get("tools", data) if isinstance(data, dict) else data
    tools = [prepare(t) for t in ([data] if isinstance(data, dict) else dicts(data))]
    return tools or die(f"{base / 'tool.json'} holds no tool: see references/tools.md.")


def tool_problems(t: dict) -> list:
    raw, source = t["raw"], obj(t["raw"].get("source"))
    ids, questions = [d["id"] for d in t["domains"]], [q for d in t["domains"] for q in d["questions"]]
    checks = (
        (not re.fullmatch(r"\d{4}-\d{2}-\d{2}", txt(source.get("read"))), "source.read must be the date read (YYYY-MM-DD)"),
        (not (txt(source.get("file")) or txt(source.get("url"))), "source needs the file or web address it was read from"),
        (not ids or not all(ids) or len(set(ids)) < len(ids) or not all(d["name"] for d in t["domains"]),
         "domains need unique ids and names"),
        (len(set(questions)) < len(questions), "signalling question ids repeat"),
        (bool(questions) and not t["answers"], "the answer vocabulary is empty"),
        (len(t["rank"]) < 2 or len(t["labels"]) < t["n_judgements"], "judgements need unique ids and two ranked levels"),
        (t["rule"] not in RULES or not t["rule_locator"], "overall needs a rule (worst, worst_or_higher, none) and its locator"))
    problems = [f"{k} is missing" for k in ("id", "name", "version") if not txt(raw.get(k))]
    problems += [message for failed, message in checks if failed]
    for did, entry in t["mapping"].items():
        asked = next((d["questions"] for d in t["domains"] if d["id"] == did), None)
        rules = dicts(obj(entry).get("rules"))
        if asked is None or not txt(obj(entry).get("locator")) or not rules:
            problems.append(f"mapping {did}: needs a domain of the tool, the locator it was read at, and rules")
        for rule in rules:
            condition, then = rule.get("if"), strs(rule.get("then"))
            if not isinstance(condition, dict) or not then or not set(then) <= set(t["labels"]) or any(
                    q not in (asked or []) or not set(strs(v) or [""]) <= t["answers"] for q, v in condition.items()):
                problems.append(f"mapping {did}: {json.dumps(rule)} uses a question, answer or judgement the tool lacks")
    return problems


def check_tool(t: dict, base: Path, add) -> None:
    where, source, problems = f"tool {t['id'] or '?'}", obj(t["raw"].get("source")), tool_problems(t)
    add("tool", "fail" if problems else "ok", where, "; ".join(problems))
    file, recorded = txt(source.get("file")), txt(source.get("sha256"))
    if not file:
        add("tool_file", "not_checked", where, "read from a web page with no saved copy: not comparable with its source")
    elif not at(base, file).is_file():
        add("tool_file", "fail", where, f"{file} is missing")
    elif not recorded:
        add("tool_file", "fail", where, f"no SHA-256 recorded for {file}: run hash and record it")
    elif recorded != sha256(at(base, file)):
        add("tool_file", "fail", where, f"{file} changed after it was registered: register the tool again")
    else:
        add("tool_file", "ok", where, file)


# ---------------------------------------------------------------------------------------------
# The assessments


def read_texts(study: dict, base: Path, add, where: str) -> dict:
    """{path: (text, [(page, text of the page)])} for the texts of one study."""
    texts = {}
    for entry in dicts(study.get("texts")):
        name, kind, recorded = txt(entry.get("path")), txt(entry.get("kind")) or "full_text", txt(entry.get("sha256"))
        if not name or not at(base, name).is_file():
            add("text", "fail", where, f"text {name or '(no path)'} is missing")
            continue
        data = at(base, name).read_bytes()
        content = data.decode("utf-8", errors="replace")
        words = len(tokens(content))
        problems = [] if kind in TEXT_KINDS else [f"kind must be one of {', '.join(TEXT_KINDS)}"]
        if not recorded:
            problems.append("no SHA-256 recorded: run hash and record it")
        elif recorded != hashlib.sha256(data).hexdigest():
            problems.append("changed after its SHA-256 was recorded: if re-extracted on purpose, record the new hash "
                            "and reread the judgements that rest on it")
        if kind == "full_text" and words < MIN_FULL_TEXT_TOKENS:
            problems.append(f"{words} words is an abstract or a failed extraction (kind abstract if that is all there is)")
        add("text", "fail" if problems else "ok", f"{where} / {name}", "; ".join(problems) or f"{words} words")
        marks = list(PAGE_MARK.finditer(content))
        ends = [m.start() for m in marks[1:]] + [len(content)]
        texts[name] = (content, [(int(m.group(1) or m.group(2)), content[m.end():end]) for m, end in zip(marks, ends)])
    if not texts:
        add("text", "fail", where, "no text of this study could be read: save its full text first")
    return texts


def grade(quote: str, texts: dict, wanted: str) -> tuple:
    """(grade, text, page) of the best match of a quote among a study's texts, or in the one it names."""
    best = ("ABSENT", "", None)
    for name, (content, pages) in texts.items():
        found = match_quality(quote, content)["grade"] if name == (wanted or name) else "ABSENT"
        if GRADES.index(found) > GRADES.index(best[0]):
            best = (found, name, next((n for n, part in pages if match_quality(quote, part)["grade"] in PASSING), None)
                    if found in PASSING else None)
    return best


def quote_problem(item: dict, texts: dict, found: str) -> str:
    quote, wanted = txt(item.get("quote")), txt(item.get("text"))
    if not txt(item.get("locator")):
        return "no locator: give the page, section, table or figure"
    if wanted and wanted not in texts:
        return f"names {wanted}, which is not a text of this study"
    if len(tokens(quote)) < MIN_QUOTE_TOKENS:
        return f"{len(tokens(quote))} words: quote at least {MIN_QUOTE_TOKENS}"
    return {"PARTIAL": "only partly found (PARTIAL): reread the passage and copy it again",
            "ABSENT": "not in the study's texts (ABSENT)"}.get(found, "")


def allowed_by(rules: list, answers: dict):
    """The judgements the first matching rule allows; None when no rule matches."""
    for rule in rules:
        if all(answers.get(q) in (strs(v) or []) for q, v in obj(rule.get("if")).items()):
            return strs(rule.get("then")) or []
    return None


def check_domain(t: dict, d: dict, entry: dict, texts: dict, add, w: str, key: tuple, grades: dict) -> None:
    judgement, answers, label = txt(entry.get("judgement")), obj(entry.get("answers")), t["labels"].get
    if not entry:
        add("complete", "fail", w, "no judgement for this domain")
        return
    problems = [] if judgement in t["labels"] else [f"judgement {judgement!r} is not in the vocabulary"]
    problems += [f"{q} is not answered" for q in d["questions"] if q not in answers]
    problems += [f"{q} is not a question of {d['id']}" for q in answers if q not in d["questions"]]
    problems += [f"{q}: {a!r} is not in the answer vocabulary" for q, a in answers.items() if a not in t["answers"]]
    add("complete", "fail" if problems else "ok", w, "; ".join(problems))

    passed = 0
    for i, item in enumerate(dicts(entry.get("support"))):
        found, name, page = grades[(*key, i)] = grade(txt(item.get("quote")), texts, txt(item.get("text")))
        problem = quote_problem(item, texts, found)
        passed += not problem
        add("quote", "fail" if problem else "ok", w, problem or f"{found} in {name}" + (f", page {page}" if page else ""))
    searched = txt(obj(entry.get("no_information")).get("searched"))
    if judgement in t["ni"] and not searched:
        add("support", "fail", w, "a judgement of no information needs no_information.searched")
    elif not passed and not searched:
        add("support", "fail", w, "no quote passed the quote check and no no_information.searched was given")
    else:
        add("support", "ok", w)

    rules, reason = dicts(obj(t["mapping"].get(d["id"])).get("rules")), txt(entry.get("departs_from_mapping"))
    allowed = allowed_by(rules, answers)
    names = " or ".join(label(j, j) for j in allowed or [])
    if not rules:
        add("mapping", "not_checked", w, "no mapping registered for this domain")
    elif allowed is None:
        add("mapping", "fail", w, "no rule of the registered mapping matches these answers")
    elif judgement in allowed:
        add("mapping", "ok", w)
    elif reason:
        add("departure", "ok", w, f"the mapping gives {names}; departs because: {reason}")
    else:
        add("mapping", "fail", w, f"the registered mapping gives {names} for these answers, not "
                                  f"{label(judgement, repr(judgement))}")


def overall_problem(t: dict, given: list, judgement: str, reason: str):
    """Why the overall judgement breaks the rule: "" when it does not, None when there is none to check."""
    ranks = [t["rank"][j] for j in given if j in t["rank"]]
    worst, rank = max(ranks, default=None), t["rank"].get(judgement)
    worst_name = next((t["labels"][j] for j, r in t["rank"].items() if r == worst), "")
    if t["rule"] == "none":
        return "the tool defines no overall judgement" if judgement else None
    if judgement in t["ni"]:
        return "" if reason and set(given) & t["ni"] else "an overall of no information needs such a domain and a reason"
    if rank is None:
        return f"overall {judgement!r} is not a ranked judgement of the tool" if judgement else "no overall judgement"
    if worst is None:
        return "no domain has a ranked judgement to derive the overall judgement from"
    if rank < worst:
        return f"better than the worst domain ({worst_name})"
    if rank > worst and t["rule"] == "worst":
        return f"worse than the worst domain ({worst_name}), which the rule worst does not allow"
    return f"worse than the worst domain ({worst_name}): give the reason" if rank > worst and not reason else ""


def check_result(t: dict, sid: str, result: dict, texts: dict, add, grades: dict) -> None:
    outcome, domains = txt(result.get("outcome")), obj(result.get("domains"))
    where = f"{sid} / {outcome or '?'}"
    problems = [f"{k} is missing" for k in ("outcome", "target", "assessor") if not txt(result.get(k))]
    problems += [f"{d} is not a domain of the tool" for d in domains if d not in {x["id"] for x in t["domains"]}]
    add("complete", "fail" if problems else "ok", where, "; ".join(problems))
    for d in t["domains"]:
        check_domain(t, d, obj(domains.get(d["id"])), texts, add, f"{where} / {d['id']}", (sid, outcome, d["id"]), grades)
    overall = obj(result.get("overall"))
    given = [txt(obj(domains.get(d["id"])).get("judgement")) for d in t["domains"]]
    problem = overall_problem(t, given, txt(overall.get("judgement")), txt(overall.get("reason")))
    if problem is not None:
        add("overall", "fail" if problem else "ok", where, problem)


def tool_for(study: dict, tools: list):
    wanted = txt(study.get("tool")) or (tools[0]["id"] if len(tools) == 1 else "")
    return next((t for t in tools if t["id"] == wanted), None)


def studies_in(base: Path) -> list:
    data = load(base / "assessments.json")
    studies = dicts(data.get("assessments") if isinstance(data, dict) else data)
    return studies or die(f"{base / 'assessments.json'} holds no assessments: see references/assessing.md.")


def run_checks(base: Path) -> tuple:
    rows, grades = [], {}

    def add(check, status, where, detail=""):
        rows.append({"check": check, "status": status, "where": where, "detail": detail})

    tools = read_tools(base)
    for t in tools:
        check_tool(t, base, add)
    studies = studies_in(base)
    ids = Counter(txt(s.get("study")) for s in studies)
    for s in studies:
        sid, t, results = txt(s.get("study")) or "?", tool_for(s, tools), dicts(s.get("results"))
        outcomes = Counter(txt(r.get("outcome")) for r in results)
        if sid == "?" or ids[sid] > 1:
            add("complete", "fail", sid, "every study needs its own id, used once")
        if not results or max(outcomes.values()) > 1:
            add("complete", "fail", sid, "results need one entry per outcome")
        if t is None:
            add("complete", "fail", sid, f"tool {txt(s.get('tool'))!r} is not registered in tool.json")
            continue
        texts = read_texts(s, base, add, sid)
        for r in results:
            check_result(t, sid, r, texts, add, grades)
    return rows, {"tools": tools, "studies": studies, "grades": grades}


def write_check(base: Path, rows: list, studies: list) -> dict:
    counts, failed, unchecked = Counter((r["check"], r["status"]) for r in rows), [r for r in rows if r["status"] == "fail"], {}
    for r in rows:
        if r["status"] == "not_checked":
            unchecked.setdefault(f"{r['check']}: {r['detail']}", []).append(r["where"].rsplit(" / ", 1)[-1])
    unreviewed = [f"{txt(s.get('study'))} / {txt(r.get('outcome'))}" for s in studies for r in dicts(s.get("results"))
                  if not txt(r.get("checked_by"))]
    lines = ["# Risk-of-bias check", "", row("Check", "ok", "fail", "not checked"), "|---" * 4 + "|"]
    lines += [row(n, counts[n, "ok"], counts[n, "fail"], counts[n, "not_checked"]) for n in dict.fromkeys(r["check"] for r in rows)]
    lines += ["", f"## Failures ({len(failed)})", ""]
    lines += [row("Check", "Where", "Problem"), "|---" * 3 + "|"] + [row(r["check"], r["where"], r["detail"]) for r in failed] \
        if failed else ["None."]
    sections = (("Not checked (never a pass)", [f"{k}: {len(w)} ({', '.join(sorted(set(w)))})" for k, w in unchecked.items()]),
                ("Departures from the registered mapping", [f"{r['where']}: {r['detail']}" for r in rows if r["check"] == "departure"]),
                ("Not yet reviewed by a person (checked_by is empty)", unreviewed))
    for title, found in sections:
        lines += ["", f"## {title}", ""] + ([f"- {item}" for item in found] or ["None."])
    (base / "check.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"ok": sum(r["status"] == "ok" for r in rows), "fail": len(failed),
            "not_checked": sum(len(w) for w in unchecked.values()), "departures": counts["departure", "ok"],
            "not_reviewed_by_a_person": len(unreviewed), "report": str(base / "check.md"),
            "failures": [{k: r[k] for k in ("check", "where", "detail")} for r in failed[:40]]}


# ---------------------------------------------------------------------------------------------
# Tables (rob_plot.py uses the first three functions too)


def by_outcome(ctx: dict) -> list:
    """[(tool, outcome, [(study id, result)])] in the order of assessments.json."""
    groups: dict = {}
    for s in ctx["studies"]:
        t = tool_for(s, ctx["tools"])
        for r in dicts(s.get("results")) if t else []:
            outcome = txt(r.get("outcome"))
            groups.setdefault((t["id"], outcome), (t, outcome, []))[2].append((txt(s.get("study")), r))
    return list(groups.values())


def columns(t: dict) -> tuple:
    """(the domain ids, then None for the overall judgement; their headings D1 ... Dn, Overall)."""
    overall = [None] if t["rule"] != "none" else []
    return ([d["id"] for d in t["domains"]] + overall,
            [f"D{i}" for i in range(1, len(t["domains"]) + 1)] + ["Overall"] * len(overall))


def judgement(result: dict, column) -> str:
    """The judgement of one domain of a result, or of the overall judgement when column is None."""
    return txt(obj(obj(result.get("domains")).get(column) if column else result.get("overall")).get("judgement"))


def cmd_export(base: Path) -> dict:
    rows, ctx = run_checks(base)
    failures = sum(r["status"] == "fail" for r in rows)
    if failures:
        return {"exported": False, "failures": failures, "message": "rob_check.py check fails: fix the assessments first"}
    files, table = [], ["# Risk-of-bias judgements", ""]
    quotes = ["# Quotes behind the judgements", "", "Every quote was found in the study's saved text by rob_check.py. Match is "
              "the grade of quote_match: EXACT, or INTERLEAVED when extraction noise sits inside the quote.", ""]
    for t, outcome, entries in by_outcome(ctx):
        cols, heads = columns(t)
        labels = {sid: [t["labels"][judgement(r, c)] for c in cols] for sid, r in entries}
        weighted = all(type(r.get("weight")) in (int, float) for _, r in entries)
        out = io.StringIO()
        csv.writer(out, lineterminator="\n").writerows(
            [["Study", *heads] + (["Weight"] if weighted else [])]
            + [[sid, *labels[sid]] + ([r["weight"]] if weighted else []) for sid, r in entries])
        files.append(re.sub(r"[^A-Za-z0-9._-]+", "-", f"robvis-{t['id']}-{outcome}") + ".csv")
        (base / files[-1]).write_text(out.getvalue(), encoding="utf-8")

        title, source = f"## {t['raw'].get('name')} {t['raw'].get('version')}: {outcome}", obj(t["raw"].get("source"))
        table += [title, "", row("Study", *heads, "Assessed by", "Checked by"), "|---" * (len(heads) + 3) + "|"]
        table += [row(sid, *labels[sid], r.get("assessor"), txt(r.get("checked_by")) or "not yet") for sid, r in entries]
        table += ["", "; ".join(f"D{i}: {d['name']}" for i, d in enumerate(t["domains"], 1)) + ".",
                  f"Tool read on {source.get('read')} from {source.get('file') or source.get('url')}.", ""]

        quotes += [title, "", row("Study", "Domain", "Answers", "Judgement", "Support", "Where", "Match"), "|---" * 7 + "|"]
        for sid, r in entries:
            for d in t["domains"]:
                entry = obj(obj(r.get("domains")).get(d["id"]))
                lead = [sid, d["id"], "; ".join(f"{q} {a}" for q, a in obj(entry.get("answers")).items()),
                        t["labels"][txt(entry.get("judgement"))]]
                for i, item in enumerate(dicts(entry.get("support"))):
                    found, name, page = ctx["grades"][(sid, txt(r.get("outcome")), d["id"], i)]
                    where = f"{txt(item.get('locator'))} ({f'page {page} of ' if page else ''}{name})"
                    quotes.append(row(*lead, f"\"{txt(item.get('quote'))}\"", where, found))
                    lead = ["", "", "", ""]
                searched = txt(obj(entry.get("no_information")).get("searched"))
                if searched:
                    quotes.append(row(*lead, "No information", f"Searched: {searched}", ""))
        quotes.append("")
    (base / "table.md").write_text("\n".join(table), encoding="utf-8")
    (base / "quotes.md").write_text("\n".join(quotes), encoding="utf-8")
    return {"exported": True, "files": [str(base / f) for f in files + ["table.md", "quotes.md"]]}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Check risk-of-bias assessments and export the tables.")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("hash", help="Print the SHA-256 of files").add_argument("files", nargs="+")
    for name, about in (("check", "Check tool.json, assessments.json and the texts; write check.md"),
                        ("export", "Write the robvis CSVs, table.md and quotes.md, when check passes")):
        sub.add_parser(name, help=about).add_argument("--dir", default="risk-of-bias",
                                                      help="The output folder (default: risk-of-bias)")
    args = parser.parse_args(argv)
    if args.command == "hash":
        missing = [f for f in args.files if not Path(f).is_file()]
        if missing:
            die("No such file: " + ", ".join(missing))
        result = {"sha256": {f: sha256(Path(f)) for f in args.files}}
    elif args.command == "check":
        rows, ctx = run_checks(Path(args.dir))
        result = write_check(Path(args.dir), rows, ctx["studies"])
    else:
        result = cmd_export(Path(args.dir))
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 1 if result.get("fail") or result.get("exported") is False else 0


if __name__ == "__main__":
    sys.exit(main())
