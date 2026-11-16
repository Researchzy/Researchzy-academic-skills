#!/usr/bin/env python3
"""Check the GRADE summary of findings in sof.json and write sof.md.

  sof_check.py [--dir risk-of-bias] [--results meta-analysis/results.json]

Per outcome: randomised evidence starts high and observational evidence low (high only with
start_reason); each of the five domains has a decision (none, not_assessable, serious,
very_serious), all but none with a reason and each downgrade with its studies; only observational
evidence is rated up, by a named person; the certainty label equals the level the decisions give,
and an outcome with no studies is no_evidence, not very low; every study listed has a
risk-of-bias assessment of the outcome in assessments.json; a risk ratio or odds ratio needs
comparator risks with their sources, from which the absolute effects per 1,000 are computed.
--results compares the estimate, its interval and the numbers of studies and participants, at the
precision written in sof.json, with the record named by results_id (the results.json of
researchzy-meta-analysis).

The format is in references/certainty.md. Writes sof.md in --dir and prints a JSON summary. Exit
code 1 when a check fails; 2 when an input file is missing or is not valid JSON. Standard library
only; the shared helpers come from rob_check.py next to this file.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rob_check import dicts, die, load, obj, row, strs, studies_in, txt  # noqa: E402

LEVELS = ("very_low", "low", "moderate", "high")
STARTS = {"randomised": "high", "randomized": "high", "observational": "low"}
DOWNGRADES = ("risk_of_bias", "inconsistency", "indirectness", "imprecision", "publication_bias")
DECISIONS = {"none": 0, "not_assessable": 0, "serious": 1, "very_serious": 2}
SHOWN = {"none": "not serious", "not_assessable": "not assessable", "serious": "serious (−1)",
         "very_serious": "very serious (−2)"}
UPGRADES = ("large_effect", "dose_response", "plausible_confounding")


def num(value):
    return float(value) if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool) else None


def places(value) -> int:
    """Decimal places as written in sof.json (read with Decimal, so 0.80 keeps two)."""
    return max(0, -value.as_tuple().exponent) if isinstance(value, Decimal) else 0


def per_1000(measure: str, ratio: float, risk: float) -> float:
    """Risk with the intervention per 1,000, from a risk ratio or odds ratio and the comparator risk."""
    return 1000 * min(ratio * risk if measure == "RR" else ratio * risk / (1 - risk + ratio * risk), 1.0)


def whole(x: float) -> int:
    return int(math.floor(abs(x) + 0.5)) * (1 if x >= 0 else -1)


def level_problems(o: dict, studies: list) -> tuple:
    """(problems, the certainty the decisions give) for one outcome."""
    design, start, downs = txt(o.get("design")).lower(), txt(o.get("start")).lower(), obj(o.get("downgrades"))
    label = txt(o.get("certainty")).lower().replace(" ", "_").replace("-", "_")
    if not studies:         # nothing to rate: "no evidence" is not "very low"
        return ([] if label == "no_evidence" else ["no studies: the certainty is no_evidence, not a level"]), "no_evidence"
    problems = []
    if design not in STARTS or start not in ("high", "low"):
        problems.append("design must be randomised or observational, and start high or low")
    elif start != STARTS[design] and STARTS[design] == "high":
        problems.append("randomised evidence starts high")
    elif start != STARTS[design] and not txt(o.get("start_reason")):
        problems.append("observational evidence starting high needs start_reason, confirmed by the user")
    level = 3 if start == "high" else 1
    problems += [f"{k} is not one of the five domains" for k in downs if k not in DOWNGRADES]
    for dom in DOWNGRADES:
        entry = obj(downs.get(dom))
        decision = txt(entry.get("decision"))
        named = studies if entry.get("studies") == "all" else strs(entry.get("studies")) or []
        if decision not in DECISIONS:
            problems.append(f"{dom}: no decision (none, not_assessable, serious, very_serious)")
            continue
        if decision != "none" and not txt(entry.get("reason")):
            problems.append(f"{dom}: {decision} needs a reason")
        if DECISIONS[decision] and not named:
            problems.append(f"{dom}: name the studies behind the downgrade")
        problems += [f"{dom}: {s} is not among the outcome's studies" for s in named if s not in studies]
        level -= DECISIONS[decision]
    for dom, entry in obj(o.get("upgrades")).items():
        levels, by = obj(entry).get("levels"), txt(obj(entry).get("decided_by")).lower()
        if dom not in UPGRADES or design != "observational":
            problems.append(f"{dom}: only observational evidence is rated up, for {', '.join(UPGRADES)}")
        elif levels not in (1, 2) or isinstance(levels, bool) or not txt(obj(entry).get("reason")):
            problems.append(f"{dom}: an upgrade needs levels (1 or 2) and a reason")
        elif by in ("", "model"):
            problems.append(f"{dom}: rating up is the user's decision: decided_by names the person")
        else:
            level += levels
    computed = LEVELS[max(0, min(3, level))]
    if label != computed:
        problems.append(f"certainty says {label or 'nothing'}; the decisions give {computed}")
    return problems, computed


def effect_problems(o: dict) -> tuple:
    """(problems, [(comparator label, comparator risk, per 1,000 with the intervention: value, low, high)])."""
    effect, risks = obj(o.get("effect")), dicts(o.get("comparator_risks"))
    measure, (value, low, high) = txt(effect.get("measure")).upper(), (num(effect.get(k)) for k in ("value", "low", "high"))
    checks = (
        (None in (value, low, high) or not low <= value <= high, "effect needs value, low and high with low <= value <= high"),
        (measure in ("RR", "OR", "HR") and (low or 0) <= 0, "a ratio and its interval must be above 0"),
        (not txt(effect.get("source")), "effect.source: the results.json record or the user's file it comes from"),
        (type(o.get("participants")) is not int or o["participants"] < 1, "participants: the number in the studies"),
        (measure in ("RR", "OR") and not risks, "a risk ratio or odds ratio needs comparator_risks with their sources"),
        (any(not 0 < (num(r.get("value")) or 0) < 1 or not txt(r.get("source")) for r in risks),
         "each comparator risk needs a value between 0 and 1 and its source"))
    problems = [message for failed, message in checks if failed]
    if problems or measure not in ("RR", "OR"):
        return problems, []
    return problems, [(txt(r.get("label")) or "comparator", num(r.get("value")),
                       [per_1000(measure, x, num(r.get("value"))) for x in (value, low, high)]) for r in risks]


def compare(o: dict, record: dict, rid: str) -> tuple:
    """(status, detail) of the effect in sof.json against a results.json record."""
    effect, n = obj(o.get("effect")), obj(record.get("n"))
    pairs = (("estimate", effect.get("value"), obj(record.get("estimate")).get("value")),
             ("interval low", effect.get("low"), obj(record.get("interval")).get("low")),
             ("interval high", effect.get("high"), obj(record.get("interval")).get("high")),
             ("studies", len(strs(o.get("studies")) or []), n.get("studies")),
             ("participants", o.get("participants"), n.get("participants")))
    wrong = [f"{name} {mine} against {theirs} in {rid}" for name, mine, theirs in pairs if num(theirs) is not None
             and (num(mine) is None or abs(num(mine) - num(theirs)) > 0.5 * 10 ** -places(mine) + 1e-9)]
    absent = [f"{name} is not in record {rid}" for name, _, theirs in pairs if num(theirs) is None]
    return "fail" if wrong else "not_checked" if absent else "ok", "; ".join(wrong + absent) or f"matches {rid}"


def check_outcome(o: dict, records: dict, results, assessed) -> tuple:
    """(rows, absolute effects, the certainty the decisions give) for one outcome of sof.json."""
    studies, oid = strs(o.get("studies")) or [], txt(o.get("id"))
    problems, computed = level_problems(o, studies)
    rows = [("certainty", "fail" if problems else "ok", "; ".join(problems))]
    if not studies:
        return rows, [], computed
    missing = [s for s in studies if (s, oid) not in (assessed or set())]
    if assessed is None:
        rows.append(("risk_of_bias", "not_checked", "no assessments.json beside sof.json"))
    else:
        rows.append(("risk_of_bias", "fail" if missing else "ok",
                     f"assessments.json has no result {oid!r} for {', '.join(missing)}" if missing else ""))
    problems, absolute = effect_problems(o)
    rows.append(("effect", "fail" if problems else "ok", "; ".join(problems)))
    rid = txt(o.get("results_id"))
    if not results:
        rows.append(("results", "not_checked", "the effect was not compared with a results file: pass --results"))
    elif not rid:
        rows.append(("results", "not_checked", "no results_id names the record to compare with"))
    elif rid not in records:
        rows.append(("results", "fail", f"no record {rid} in {results}"))
    else:
        rows.append(("results", *compare(o, records[rid], rid)))
    return rows, absolute, computed


def check_sof(base: Path, results) -> dict:
    data = obj(load(base / "sof.json", parse_float=Decimal))
    outcomes = dicts(data.get("outcomes")) or die(f"{base / 'sof.json'} holds no outcomes: see references/certainty.md.")
    records = {txt(r.get("id")): r for r in dicts(obj(load(Path(results))).get("results"))} if results else {}
    assessed = None
    if (base / "assessments.json").is_file():
        assessed = {(txt(s.get("study")), txt(r.get("outcome"))) for s in studies_in(base) for r in dicts(s.get("results"))}
    checks, notes = [], []
    sof = ["# Summary of findings", "", txt(data.get("question")), "",
           row("Outcome", "Participants (studies)", "Effect (95% CI)", "Risk with comparator",
               "Risk with intervention (95% CI)", "Difference (95% CI)", "Certainty"), "|---" * 7 + "|"]
    profile = ["## Evidence profile", "", row("Outcome", "Studies", "Design", *(d.replace("_", " ").capitalize() for d in DOWNGRADES),
                                              "Rated up", "Certainty", "Rated by", "Checked by"), "|---" * 12 + "|"]
    for o in outcomes:
        name, studies, effect = txt(o.get("name")) or txt(o.get("id")) or "?", strs(o.get("studies")) or [], obj(o.get("effect"))
        rows, absolute, computed = check_outcome(o, records, results, assessed)
        checks += [(name, *r) for r in rows]
        marks = []
        for dom in DOWNGRADES if studies else ():
            entry = obj(obj(o.get("downgrades")).get(dom))
            named = studies if entry.get("studies") == "all" else strs(entry.get("studies")) or []
            if txt(entry.get("reason")):
                notes.append(f"{name}, {dom.replace('_', ' ')}" + (f" ({', '.join(named)})" if named else "")
                             + f": {txt(entry.get('reason'))}")
            marks.append(SHOWN.get(txt(entry.get("decision")), "?") + (f" [{len(notes)}]" if txt(entry.get("reason")) else ""))
        ups = "; ".join(f"{k.replace('_', ' ')} +{obj(v).get('levels')} ({txt(obj(v).get('decided_by'))})"
                        for k, v in obj(o.get("upgrades")).items()) or "none"
        level = LEVELS.index(computed) if computed in LEVELS else -1
        shown = f"{'⊕' * (level + 1)}{'◯' * (3 - level)} {computed.replace('_', ' ').capitalize()}" if level >= 0 else "No studies"
        profile.append(row(name, len(studies), txt(o.get("design")), *(marks or ["-"] * 5), ups, shown, txt(o.get("decided_by")),
                           txt(o.get("checked_by")) or "not yet"))
        told = " ".join(filter(None, (txt(effect.get("measure")), str(effect.get("value")),
                                      f"({effect.get('low')} to {effect.get('high')})", txt(effect.get("units"))))) \
            if studies else "-"
        for label, risk, (point, low, high) in absolute or [("", 0, (0, 0, 0))]:
            diff = [f"{abs(whole(x - risk * 1000))} {'fewer' if whole(x - risk * 1000) < 0 else 'more'}" for x in (point, low, high)]
            sof.append(row(name, f"{o.get('participants') or '-'} ({len(studies)})", told,
                           f"{whole(risk * 1000)} per 1,000 ({label})" if risk else "-",
                           f"{whole(point)} per 1,000 ({whole(low)} to {whole(high)})" if risk else "-",
                           f"{diff[0]} per 1,000 ({diff[1]} to {diff[2]})" if risk else "-", shown))
    sources = [f"{txt(o.get('name'))}, {txt(r.get('label')) or 'comparator'} {r.get('value')}: {txt(r.get('source'))}"
               for o in outcomes for r in dicts(o.get("comparator_risks"))]
    sof += ["", "Comparator risks: " + ("; ".join(sources) or "none") + ".", "", *profile, "", "Reasons:", ""]
    sof += [f"{i}. {n}" for i, n in enumerate(notes, 1)] or ["None given."]
    trouble = [c for c in checks if c[2] != "ok"]
    sof += ["", "## Checks", ""] + ([f"- {c[0]}, {c[1]}: {c[2]}: {c[3]}" for c in trouble] or ["Every check passed."])
    (base / "sof.md").write_text("\n".join(sof) + "\n", encoding="utf-8")
    return {"outcomes": len(outcomes), **{s: sum(c[2] == s for c in checks) for s in ("ok", "fail", "not_checked")},
            "problems": [dict(zip(("outcome", "check", "status", "detail"), c)) for c in trouble],
            "report": str(base / "sof.md")}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Check the GRADE summary of findings in sof.json and write sof.md.")
    parser.add_argument("--dir", default="risk-of-bias", help="The output folder (default: risk-of-bias)")
    parser.add_argument("--results", help="results.json of researchzy-meta-analysis, to compare the effects with")
    args = parser.parse_args(argv)
    result = check_sof(Path(args.dir), args.results)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 1 if result["fail"] else 0


if __name__ == "__main__":
    sys.exit(main())
