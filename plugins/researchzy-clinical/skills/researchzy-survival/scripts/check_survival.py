#!/usr/bin/env python3
"""Check survival/results.json and the text written from it.

  check_survival.py                                          results.json and ledger.jsonl
  check_survival.py --script survival/analysis.py
  check_survival.py --text survival/results.md survival/methods.md --strict

Runs every check of check_results.py (the copy next to this file; --dir defaults to survival) on results recorded
with rz_results.record(..., **rz_survival.fields(result)), that is with extra["survival"], and adds:

  survival      every result carries extra["survival"] with its kind (km, logrank, cox, ph_test, rmst, cif), the
                time unit, time zero, the event mapping and the excluded rows with their reasons, and the fields of
                its kind: counts, the median with its interval and method or not_reached, the number at risk and the
                reverse-KM follow-up; the log-rank statistic, df = groups - 1, p and weights; Efron ties, n, events
                and each parameter's HR, interval and p with its reference level; the PH test's statistic, df, p,
                time transform and plot; RMST's tau; the cumulative incidence's cause and times
  ph            every Cox result has a proportional-hazards result whose model is its id
  rmst          tau is at most the longest follow-up of the group whose follow-up is shortest
  (--text)      not_reached: a median printed for a group whose median was not reached; hr_interval: an HR printed
                without its interval; methods: with a Cox result, the texts name the tie method and the test of
                proportional hazards; reference: an HR printed as the reciprocal of a recorded one (the text's
                reference group is the other level)

Labels added to the number check, in English and Chinese: HR (风险比), median (中位), events (事件数), at risk
(在险人数) and RMST (限制性平均生存时间); the p-values, statistics and df of the log-rank and PH tests are looked up
with the built-in labels. Writes check.md and prints a JSON summary. Exit code 1 on a mismatch or a failed check
(with --strict also on a number not found); 2 when results.json cannot be read. Standard library only.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_results as cr  # noqa: E402

S = cr.START
COMMON = ("time_unit", "time_zero", "event_mapping", "excluded")
REQUIRED = {"km": ("group", "n", "events", "censored", "median", "at_risk", "followup", "band"),
            "logrank": ("group_column", "groups", "statistic", "df", "p", "weights"),
            "cox": ("ties", "n", "events", "parameters", "events_per_parameter"),
            "ph_test": ("model", "transform", "global", "parameters", "plot"),
            "rmst": ("tau", "groups", "method"), "cif": ("cause", "group", "at", "method")}
TRANSFORMS = ("km", "rank", "identity", "log")
HR = (rf"(?:{S}a?HRs?|{S}hazard\s+ratios?|风险比|危险比)(?:\s*\([^()]*\))?(?:\s+(?:for|of)\s+[A-Za-z-]+(?:\s+[A-Za-z-]+)?)?"
      rf"\s*(?:[=:,]|\bwas\b|\bof\b|\bis\b|为|是|等于)?\s*")
LABELS = (("hr", re.compile(HR + "$", re.I)),
          ("median", re.compile(rf"(?:{S}median|中位)(?:(?!not\s+reached|未达)[^\d;。；]){{0,40}}?(?:[=:,]|\bwas\b|\bwere\b|"
                                rf"\bof\b|\bis\b|为|是|达)?\s*$", re.I)),
          ("events", re.compile(rf"(?:{S}(?:number\s+of\s+)?events?|{S}deaths?|事件数|死亡(?:人数|例数)?)\s*(?:[=:]|\bwas\b|"
                                rf"\bwere\b|为|是|共)?\s*$", re.I)),
          ("at_risk", re.compile(r"(?:at\s+risk|在险人数|风险人数)\s*(?:[=:,]|\bwas\b|\bwere\b|为|是)?\s*$", re.I)),
          ("rmst", re.compile(rf"(?:{S}RMSTs?|restricted\s+mean\s+survival(?:\s+times?)?|限制性平均生存时间)(?:\s+difference|"
                              rf"差值|差)?(?:\s*\([^()]*\))?\s*(?:[=:,]|\bwas\b|\bof\b|\bis\b|为|是)?\s*$", re.I)))
HR_VALUE = re.compile(HR + r"(-?\d+(?:\.\d+)?)", re.I)
INTERVAL = re.compile(r"\bCI\b|confidence\s+interval|置信区间|\d\s*(?:–|—|-|−|to|至|~|～|,|，)\s*-?\d", re.I)
MEDIAN = re.compile(r"\bmedian(?!\s+(?:[A-Za-z-]+\s+){0,2}follow)|中位(?!随访)", re.I)
FOLLOW = re.compile(r"follow[- ]?up|随访", re.I)
NOT_REACHED = re.compile(r"not\s+(?:been\s+|yet\s+)?reached|(?<![A-Za-z])NR(?![A-Za-z])|not\s+estimable|未达到|未达|"
                         r"不可估计", re.I)
UNIT = re.compile(r"\d\s*(?:days?|weeks?|months?|years?|d\b|wks?\b|mo\b|yrs?\b|天|日|周|个?月|年)", re.I)
CLAUSE = re.compile(r"[;；，]|\b(?:and|whereas|while|but|compared\s+with|versus|vs\.?)\b|而|相比")
BRACKETS = re.compile(r"\([^()]*\)|\[[^\[\]]*\]")
TIES = {"efron": r"(?<![A-Za-z])Efron", "breslow": r"(?<![A-Za-z])Breslow"}     # Han text has no \b before Latin
PH_NAMED = re.compile(r"Schoenfeld|Grambsch|proportional[- ]hazards?\s+(?:assumption|test)|\bPH\s+(?:assumption|test)|"
                      r"比例风险(?:假定|假设|检验)", re.I)


def survival(result: dict):
    found = (result.get("extra") or {}).get("survival")
    return found if isinstance(found, dict) else None


def of_kind(results: list, kind: str) -> list:
    return [(r.get("id"), s) for r in results for s in [survival(r)] if s and s.get("kind") == kind]


def check_fields(results: list) -> list:
    problems = []
    for r in results:
        rid, s = r.get("id"), survival(r)
        if s is None or s.get("kind") not in REQUIRED:
            problems.append(f"{rid}: no extra['survival'] with a kind of {', '.join(REQUIRED)}: record it with "
                            "rz_survival.fields()")
            continue
        own = [f"lacks {k}" for k in COMMON + REQUIRED[s["kind"]] if s.get(k) in (None, "", [], {})
               and not (k == "excluded" and s.get(k) == [])]
        mapping = s.get("event_mapping")
        own += [] if isinstance(mapping, dict) and 1 in mapping.values() else ["the event mapping gives no code 1"]
        own += [f"excluded row {e.get('row')} has no reason" for e in s.get("excluded") or []
                if not cr.has_text(e.get("reason"))]
        kind = s["kind"]
        if kind == "km":
            m = s.get("median") or {}
            if not cr.has_text(m.get("method")):
                own.append("the median has no interval method")
            if m.get("estimate") == "not_reached" and m.get("high") != "not_reached":
                own.append("the median is not reached but its upper bound is a number")
            own += [] if (s.get("followup") or {}).get("median") is not None else ["no reverse-KM median follow-up"]
        elif kind == "logrank" and isinstance(s.get("groups"), dict) and s.get("df") != len(s["groups"]) - 1:
            own.append(f"df is {s.get('df')}, but {len(s['groups'])} groups give {len(s['groups']) - 1}")
        elif kind == "cox":
            own += [] if s.get("ties") == "efron" else [f"ties is {s.get('ties')!r}: fit with Efron's method"]
            own += [f"parameter {p.get('name')} lacks {k}" for p in s.get("parameters") or [] for k in
                    ("name", "hr", "low", "high", "p") if p.get(k) is None]
            own += [f"parameter {p.get('name')} is a level without its reference" for p in s.get("parameters") or []
                    if p.get("level") is not None and not p.get("reference")]
        elif kind == "ph_test":
            own += [] if s.get("transform") in TRANSFORMS else [f"transform {s.get('transform')!r} is not one of "
                                                                 f"{', '.join(TRANSFORMS)}"]
            own += [f"global lacks {k}" for k in ("statistic", "df", "p") if (s.get("global") or {}).get(k) is None]
        problems += [f"{rid}: {m}" for m in own]
    return problems


def check_ph(results: list) -> tuple:
    models = {s.get("model") for _, s in of_kind(results, "ph_test")}
    cox = [rid for rid, _ in of_kind(results, "cox")]
    missing = [f"{rid}: no proportional-hazards result names it as its model" for rid in cox if rid not in models]
    detail = f"{len(cox)} Cox result(s), each with its test of proportional hazards"
    return "ph", "fail" if missing else "ok" if cox else "not_checked", missing, detail if cox else "no Cox result"


def check_rmst(results: list) -> tuple:
    found, problems = of_kind(results, "rmst"), []
    for rid, s in found:
        longest = {g: v.get("longest") for g, v in (s.get("groups") or {}).items()}
        shortest = min((v for v in longest.values() if cr.is_number(v)), default=None)
        if shortest is None or not cr.is_number(s.get("tau")):
            problems.append(f"{rid}: tau or the longest follow-up per group is not recorded")
        elif s["tau"] > shortest:
            problems.append(f"{rid}: tau {s['tau']:g} lies beyond the follow-up of a group (longest {shortest:g}): "
                            "the curve is not estimated there")
    return ("rmst", "fail" if problems else "ok" if found else "not_checked", problems,
            f"{len(found)} RMST result(s) within follow-up" if found else "no RMST result")


def sentences(paths: list):
    """(where, chunk): sentences and table rows, with code, links, headings and citations blanked."""
    for path in paths:
        text = path.read_text(encoding="utf-8").replace("−", "-").translate(cr.FULL_WIDTH)
        for pattern in cr.BLANKED:
            flags = re.S if pattern[0] in "`<" else 0
            text = re.sub(pattern, lambda m: re.sub(r"[^\n]", " ", m.group(0)), text, flags=flags)
        start = 0
        for end in [m.start() for m in cr.SENTENCE_END.finditer(text)] + [len(text)]:
            chunk = text[start:end]
            if chunk.strip():
                yield f"{path.name}:{text.count(chr(10), 0, start + len(chunk) - len(chunk.lstrip())) + 1}", chunk
            start = end


def names(label: str) -> re.Pattern:
    """A group's name in text: as a word in Latin script, anywhere in Chinese."""
    word = re.escape(label.strip())
    return re.compile(word if re.search(r"[^\x00-\x7f]", label) else rf"(?<![A-Za-z]){word}(?![A-Za-z])", re.I)


def clauses(chunk: str) -> list:
    """The clauses of a sentence, brackets (intervals) blanked; a clause without a number joins the next one."""
    out, carry = [], ""
    for part in CLAUSE.split(BRACKETS.sub(" ", chunk)):
        carry += " " + part
        if re.search(r"\d", part):
            out, carry = out + [carry], ""
    return out + [carry] if carry.strip() else out


def close(printed: str, value: float) -> bool:
    decimals = len(printed.split(".", 1)[1]) if "." in printed else 0
    return abs(float(printed) - value) <= 0.5 * 10 ** -decimals * (1 + 1e-9)


def text_checks(results: list, paths: list) -> list:
    rows = ("not_reached", "hr_interval", "methods", "reference")
    paths = [p for p in paths if p.is_file()]
    if not paths:
        return [(name, "not_checked", [], "no --text given") for name in rows]
    found = {name: [] for name in rows}
    unreached = [(s["group"]["value"], [names(str(x)) for x in s.get("labels") or [s["group"]["value"]]])
                 for _, s in of_kind(results, "km") if (s.get("median") or {}).get("estimate") == "not_reached"
                 and isinstance(s.get("group"), dict)]
    ratios = [(p.get("hr"), p.get("name"), p.get("reference")) for _, s in of_kind(results, "cox")
              for p in s.get("parameters") or [] if cr.is_number(p.get("hr")) and p["hr"] > 0]
    for where, chunk in sentences(paths):
        for clause in clauses(chunk) if MEDIAN.search(chunk) else []:
            for group, patterns in unreached if UNIT.search(clause) and not (NOT_REACHED.search(clause) or
                                                                              FOLLOW.search(clause)) else []:
                if any(p.search(clause) for p in patterns):
                    found["not_reached"].append(f"{where}: prints a median for {group}, whose median was not reached: "
                                                "write that it was not reached")
        if chunk.lstrip().startswith("|"):
            continue
        for m in HR_VALUE.finditer(chunk):
            if not INTERVAL.search(chunk[m.end():m.end() + 80]):
                found["hr_interval"].append(f"{where}: HR {m.group(1)} is printed without its interval")
            if ratios and not any(close(m.group(1), hr) for hr, _, _ in ratios):
                flipped = [(hr, n, ref) for hr, n, ref in ratios if close(m.group(1), 1 / hr)]
                found["reference"] += [f"{where}: HR {m.group(1)} is the reciprocal of the recorded {hr:.2f} ({n}, "
                                       f"reference {ref}): the text compares the other way round"
                                       for hr, n, ref in flipped[:1]]
    cox = of_kind(results, "cox")
    if cox:
        joined = "\n".join(p.read_text(encoding="utf-8") for p in paths)
        for rid, s in cox:
            if not re.search(TIES.get(s.get("ties"), r"(?!)"), joined, re.I):
                found["methods"].append(f"{rid}: no text names the tie method ({s.get('ties')}); say that ties were "
                                        "handled by Efron's method")
        if not PH_NAMED.search(joined):
            found["methods"].append("no text names the test of proportional hazards (for example the Grambsch-"
                                    "Therneau test on scaled Schoenfeld residuals)")
    details = {"not_reached": f"{len(unreached)} group(s) recorded as not reached",
               "hr_interval": "every printed HR has its interval", "reference": "no HR printed the other way round",
               "methods": "the tie method and the PH test are named" if cox else "no Cox result"}
    return [(n, "fail" if found[n] else "not_checked" if n == "methods" and not cox else "ok", found[n], details[n])
            for n in rows]


def numbers(results: list) -> list:
    """(value, kind, owner, path) for the labels above and for the p, statistic and df of the tests in extra."""
    out = []

    def walk(node, owner, path):
        if isinstance(node, dict):
            for key, item in node.items():
                walk(item, owner, f"{path}.{key}")
        elif isinstance(node, list):
            for item in node:
                walk(item, owner, path)
        elif cr.is_number(node):
            last = path.rsplit(".", 2)
            kind = {"hr": "hr", "p": "p", "statistic": "statistic", "df": "df", "events": "events", "rmst": "rmst",
                    "counts": "at_risk" if last[-2] == "at_risk" else None,
                    "estimate": "median" if last[-2] == "median" else None,
                    "median": "median" if last[-2] == "followup" else None,
                    "value": "rmst" if ".differences." in path else None}.get(last[-1])
            if kind:
                out.append((float(node), kind, owner, path))
    for r in results:
        walk(survival(r) or {}, r.get("id"), "extra.survival")
    return out


def extend(content: dict, args) -> dict:
    results, fields = content["results"], check_fields(content["results"])
    rows = [("survival", "fail" if fields else "ok", fields, f"{len(results)} result(s) with their survival fields"),
            check_ph(results), check_rmst(results)]
    return {"title": "Survival check", "checks": rows + text_checks(results, list(args.text)),
            "numbers": numbers(results), "labels": LABELS}


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "-h" in argv or "--help" in argv:
        print(__doc__)
        return 0
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--dir", default="survival")
    own, rest = parser.parse_known_args(argv)
    return cr.main(["--dir", own.dir, *rest], extend=extend)


if __name__ == "__main__":
    sys.exit(main())
