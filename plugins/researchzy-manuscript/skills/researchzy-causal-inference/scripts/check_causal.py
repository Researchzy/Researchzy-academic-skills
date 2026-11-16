#!/usr/bin/env python3
"""Check a causal analysis against its design probe, then the numbers and verbs of the text.

  check_causal.py --probe causal/counties.design.json
  check_causal.py --probe causal/counties.design.json --script causal/analysis.py
  check_causal.py --probe causal/counties.design.json --text causal/results.md causal/methods.md

It runs the checks of check_results.py on causal/results.json (complete, families, ledger, hashes,
text) and adds:

  route           known designs, one headline per question (family); headlines only on a matched
                  route, with its design and headline estimator (a TWFE headline on staggered data fails)
  diagnostics     each required diagnostic of a headline is pass, fail, or not_checked with a reason;
                  a not_checked one makes this check not_checked, never ok
  clustering      level, basis, G and treated G recorded; the level is not finer than the assignment
                  level of the probe, and G is not larger than the probe counts
  iv_strength     first-stage F below --f-low (default 10): the Anderson-Rubin set is recorded and is
                  the headline interval; below 3.84 the AR set is unbounded and no 2SLS headline stands
  permutation     a permutation p is at least 1/(B + 1); a synthetic-control p at least 1/(J + 1)
  rules           what a failed diagnostic forbids; "fragile" in the text when the breakdown M is below
                  1; cohorts with a failed pre-trend named; randomization inference for few treated clusters
  specifications  per question, the specifications run (record lines of the last run in ledger.jsonl);
                  a headline that is the only one whose interval excludes the null needs the count in the
                  text; a dropped record without the causal fields of causal_tools.spec() is reported
  verbs           (--text) causal verbs about results that the route or the diagnostics do not support
  script          (--script) the lint of check_results.py, where causal_tools.spec() counts as recording

Writes check.md and robustness.md (every specification, headline first, changes in n flagged) in
--dir (default causal) and prints a JSON summary. Exit code 1 on a failed check or a mismatch in the
text (with --strict also a number not found); 2 when results.json or the probe cannot be read.
Standard library only.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_results as cr  # noqa: E402

REQUIRED = {"did_2x2": ("pretrend_plot", "pretrend_test"),
            "staggered_did": ("cohorts", "untreated_each_period", "event_study", "sensitivity"),
            "event_study": ("pretrend_test", "sensitivity"),
            "iv": ("first_stage", "reduced_form", "first_stage_f", "ar_set", "ols"),
            "rd": ("density", "covariate_balance", "bandwidths", "placebo_cutoffs"),
            "panel_fe": ("within_variation",), "sc": ("pre_fit", "placebos"),
            "weighting": ("overlap", "balance", "max_weight", "trimming")}
NO_ESTIMATE = {("rd", "density"): "the density test rejected: report no RD point estimate (manipulation-robust "
                                  "bounds are outside this skill)",
               ("rd", "covariate_balance"): "covariates jump at the cutoff: report no RD estimate",
               ("sc", "pre_fit"): "the pre-period fit failed: report no synthetic-control estimate"}
EVENT = {"did_2x2": {"twfe_event_study", "callaway_santanna"}, "staggered_did": {"callaway_santanna"}}
TREATED_G = {"did_2x2", "staggered_did", "event_study", "panel_fe"}
AR_UNBOUNDED = 3.84        # chi-square(1) at 5%: below it the first stage is not distinguishable from zero
STRONG = re.compile(r"\b(?:caus(?:e|es|ed|ing)|led to|leads? to|result(?:s|ed)? in|drove|driven by|"
                    r"induc(?:e|es|ed))\b", re.I)
DIRECTIONAL = re.compile(r"\b(?:(?:in|de)creas(?:e|es|ed)|rais(?:e|es|ed)|reduc(?:e|es|ed)|lower(?:s|ed)|"
                         r"improv(?:e|es|ed)|boost(?:s|ed)?)\b", re.I)
WORDS = "zero one two three four five six seven eight nine ten eleven twelve".split()


def number(*values):
    return next((float(v) for v in values if isinstance(v, (int, float)) and not isinstance(v, bool)), None)


def value_of(entry) -> dict:
    return entry.get("value") if isinstance(entry, dict) and isinstance(entry.get("value"), dict) else {}


def status_of(c, key):
    return ((c.get("diagnostics") or {}).get(key) or {}).get("status")


def row(name, problems, detail, unchecked=()):
    status = "fail" if problems else "not_checked" if unchecked else "ok"
    return name, status, problems, "; ".join(unchecked) if unchecked and not problems else detail


def check_route(causal, heads, route, probe):
    problems = [f"{r['id']}: unknown design {c.get('design')!r}; use one of {', '.join(REQUIRED)}"
                for r, c in causal if c.get("design") not in REQUIRED]
    count = defaultdict(int)
    for r, c in causal:
        count[r.get("family")] += bool(c.get("headline"))
    problems += [f"question {family}: {n} headline specifications; mark exactly one with headline=True"
                 for family, n in count.items() if n != 1]
    design = route.get("design")
    for r, c in heads if probe else ():
        if route.get("outcome") != "matched":
            problems.append(f"{r['id']}: the probe's route is {route.get('outcome')} ({'; '.join(route.get('why', []))}): "
                            "report no headline estimate")
        elif c["design"] == "event_study" and design in EVENT:
            if c["estimator"] not in EVENT[design]:
                problems.append(f"{r['id']}: an event study on {design} data comes from "
                                f"{' or '.join(sorted(EVENT[design]))}, not {c['estimator']}")
        elif c["design"] != design:
            problems.append(f"{r['id']}: design {c['design']}, but the probe matched {design}")
        elif c["estimator"] not in route.get("headline", []):
            problems.append(f"{r['id']}: {c['estimator']} is not a headline for {design} (the route allows "
                            f"{', '.join(route.get('headline', []))}); record it with headline=False"
                            + ("; under staggered adoption TWFE weighs some comparisons negatively"
                               if c["estimator"].startswith("twfe") else ""))
    unchecked = ["no result was recorded with causal_tools.spec()"] if not causal else \
        ["no --probe given: the route is not compared"] if not probe else []
    return row("route", problems, f"{len(causal)} causal result(s); route {route.get('outcome')}: {design}", unchecked)


def check_diagnostics(heads):
    problems, unchecked, failed = [], [], []
    for r, c in heads:
        for key in REQUIRED.get(c["design"], ()):
            entry = (c.get("diagnostics") or {}).get(key)
            if not isinstance(entry, dict) or entry.get("status") not in ("pass", "fail", "not_checked"):
                problems.append(f"{r['id']}: the required diagnostic {key} is not recorded as pass, fail or not_checked")
            elif entry["status"] == "not_checked":
                reason = str(entry.get("reason") or "").strip()
                (unchecked if reason else problems).append(f"{r['id']}: {key} not_checked ({reason or 'no reason given'})")
            elif entry["status"] == "fail":
                failed.append(f"{key} of {r['id']}")
    detail = f"recorded for {len(heads)} headline(s)" + (f"; failed: {', '.join(failed)}" if failed else "")
    return row("diagnostics", problems, detail, unchecked if heads else ["no headline"])


def check_clustering(heads, probe):
    facts, problems, unchecked, notes = (probe or {}).get("clustering") or {}, [], [], []
    for r, c in heads:
        cl = c.get("cluster") or {}
        if c["design"] == "sc":
            continue
        if not cl.get("level") or not isinstance(cl.get("G"), int):
            problems.append(f"{r['id']}: no cluster: record cluster={{'level', 'basis', 'G', 'G_treated'}}")
            continue
        if cl.get("basis") not in ("assignment", "sampling"):
            problems.append(f"{r['id']}: the cluster basis must be 'assignment' or 'sampling'")
        if c["design"] in TREATED_G and not isinstance(cl.get("G_treated"), int):
            problems.append(f"{r['id']}: the number of treated clusters (G_treated) is missing")
        level = (facts.get("levels") or {}).get(cl["level"])
        if level is None:
            unchecked.append(f"{r['id']}: " + ("no --probe given" if not probe else
                             f"the probe did not see {cl['level']}: run it with --cluster {cl['level']}"))
            continue
        if not level.get("at_or_above_assignment"):
            problems.append(f"{r['id']}: clustered by {cl['level']}, finer than the assignment level {facts.get('assignment')}")
        for key in ("G", "G_treated"):
            mine, theirs = cl.get(key), level.get(key)
            if isinstance(mine, int) and isinstance(theirs, int) and mine != theirs:
                (problems if mine > theirs else notes).append(f"{r['id']}: {key} = {mine}, the probe counts {theirs} for "
                                                              f"{cl['level']}" + ("" if mine > theirs else
                                                                                  ": say in the text which clusters dropped out"))
    return row("clustering", problems, "; ".join(notes) or "not finer than the assignment level", unchecked)


def check_iv(heads, f_low):
    problems, unchecked, details = [], [], []
    for r, c in ((r, c) for r, c in heads if c["design"] == "iv"):
        diagnostics = c.get("diagnostics") or {}
        f, ar = diagnostics.get("first_stage_f") or {}, diagnostics.get("ar_set") or {}
        F, segments = number(f.get("value"), (f.get("statistic") or {}).get("value")), value_of(ar).get("set")
        if F is None:
            unchecked.append(f"{r['id']}: no first-stage F value")
            continue
        details.append(f"{r['id']}: F = {F:.4g}")
        interval = r.get("interval") or {}
        if F < AR_UNBOUNDED and c["estimator"] == "2sls":
            problems.append(f"{r['id']}: first-stage F = {F:.3g} < {AR_UNBOUNDED}: the first stage is not distinguishable "
                            "from zero and the AR set is unbounded; report no IV estimate")
        elif F < f_low and (ar.get("status") not in ("pass", "fail") or not isinstance(segments, list)):
            problems.append(f"{r['id']}: first-stage F = {F:.3g} < {f_low:g}: record the Anderson-Rubin set (ar_set "
                            "with value {'set': [[low, high]], 'bounded': true}) and lead with it")
        elif F < f_low and len(segments) == 1 and value_of(ar).get("bounded", True) and any(
                number(interval.get(k)) is None or abs(interval[k] - v) > 1e-6 * max(1.0, abs(v))
                for k, v in zip(("low", "high"), segments[0])):
            problems.append(f"{r['id']}: first-stage F = {F:.3g} < {f_low:g}: the headline interval must be the "
                            f"Anderson-Rubin set {segments[0]}")
    return row("iv_strength", problems, "; ".join(details) + f" (AR set leads below F = {f_low:g})", unchecked)


def check_permutation(causal):
    problems, seen = [], 0
    for r, c in causal:
        for name, entry in [("permutation", c.get("permutation"))] + list((c.get("diagnostics") or {}).items()):
            for holder in (entry, value_of(entry)) if isinstance(entry, dict) else ():
                for key in ("B", "J"):
                    draws, p = holder.get(key), number(holder.get("p"))
                    if isinstance(draws, int) and p is not None:
                        seen += 1
                        if p < 1 / (draws + 1) - 1e-12:
                            problems.append(f"{r['id']}: {name} p = {p:.4g} is below 1/({key} + 1) = {1 / (draws + 1):.4g}"
                                            ": count the observed assignment, (1 + hits) / (B + 1)")
    return row("permutation", problems, f"{seen} permutation p-value(s) at or above their floor") if seen else None


def check_rules(heads, texts, few_treated, probe):
    problems, unchecked, joined = [], [], "\n".join(texts.values())
    gaps = ((probe or {}).get("facts") or {}).get("periods_without_untreated")
    for r, c in heads:
        d, design = c.get("diagnostics") or {}, c["design"]
        problems += [f"{r['id']}: {message}" for (where, key), message in NO_ESTIMATE.items()
                     if design == where and status_of(c, key) == "fail"]
        trim = value_of(d.get("trimming"))
        if design == "weighting" and trim.get("method") != "drop":
            problems.append(f"{r['id']}: trimming must drop units (trimming value 'method': 'drop'), never clip scores")
        share = number(trim.get("trimmed_share"))
        if design == "weighting" and share is not None and share > 0.5 and str(c.get("estimand") or "").upper() == "ATE":
            problems.append(f"{r['id']}: {share:.0%} of the units were trimmed: report the effect in the overlap "
                            "population, not the ATE")
        g1 = (c.get("cluster") or {}).get("G_treated")
        if design == "panel_fe" and isinstance(g1, int) and g1 <= few_treated and \
                status_of(c, "randomization_inference") not in ("pass", "fail"):
            problems.append(f"{r['id']}: {g1} treated clusters (at most {few_treated}): add the diagnostic "
                            "randomization_inference (causal_tools.ri_pvalue)")
        if design == "staggered_did" and gaps and status_of(c, "untreated_each_period") == "pass":
            problems.append(f"{r['id']}: untreated_each_period is pass, but the probe found periods without an "
                            f"untreated unit: {gaps}")
        if design not in ("did_2x2", "staggered_did", "event_study"):
            continue
        m = number(value_of(d.get("sensitivity")).get("breakdown_M"))
        words = r"\bfragile\b" + (r"|\bdirectional\b" if design == "did_2x2" else "")
        if m is not None and m < 1 and not re.search(words, joined, re.I):
            (problems if texts else unchecked).append(f"{r['id']}: breakdown M = {m:.3g} < 1: say in the text that the "
                                                      "result is fragile")
        for key, entry in ((k, e) for k, e in d.items() if isinstance(e, dict) and e.get("status") == "fail"):
            for g in entry.get("cohorts") or value_of(entry).get("cohorts") or []:
                label = str(int(g)) if isinstance(g, float) and g.is_integer() else str(g)
                if not re.search(rf"(?<![\d.]){re.escape(label)}(?![\d.])", joined):
                    (problems if texts else unchecked).append(f"{r['id']}: {key} failed for cohort {label}: name it in the "
                                                              "text and say whether it is reported separately or dropped")
    return row("rules", problems, "what the failed diagnostics forbid is respected" if heads else "no headline",
               [u + " (no --text given)" for u in unchecked])


def causal_of(line) -> dict:
    return (line.get("extra") or {}).get("causal") or {}


def check_specifications(content, folder, texts):
    """The record lines of the latest run in ledger.jsonl: every specification, kept or dropped."""
    path = folder / "ledger.jsonl"
    lines = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()] if path.is_file() else []
    records = [x for x in lines if x.get("run") == content.get("run") and "event" not in x]
    specs, joined = [x for x in records if causal_of(x)], "\n".join(texts.values())
    problems = [f"{x['id']}: dropped without the causal fields: record every specification with causal_tools.spec(), "
                "so that robustness.md shows it" for x in records if x.get("status") == "dropped" and not causal_of(x)]
    families, numbers, details = defaultdict(list), [], []
    for x in specs:
        iv, null = x.get("interval") or {}, number(causal_of(x).get("null")) or 0.0
        x["excludes_null"] = number(iv.get("low")) is not None and number(iv.get("high")) is not None and \
            not iv["low"] <= null <= iv["high"]
        families[x.get("family")].append(x)
    for family, items in families.items():
        excluding = [x for x in items if x["excludes_null"]]
        head = next((x for x in items if causal_of(x).get("headline")), None)
        details.append(f"{family}: {len(items)} specification(s), {len(excluding)} excluding the null")
        numbers.append((float(len(items)), "value", "specifications", f"{family}.count"))
        word = WORDS[len(items)] if len(items) < len(WORDS) else str(len(items))
        if len(items) > 1 and head and head["excludes_null"] and len(excluding) == 1 and not re.search(
                rf"\b(?:{len(items)}|{word})\b[^.;]{{0,60}}?\bspecifications?\b", joined, re.I):
            problems.append(f"question {family}: the headline is the only one of {len(items)} specifications whose interval "
                            f"excludes {causal_of(head).get('null', 0)}: say so in the text with the count (for example "
                            f"'one of {len(items)} specifications'); robustness.md lists them all")
    if not specs:
        return ("specifications", "fail" if problems else "not_checked", problems, "no specification in this run"), [], []
    return row("specifications", problems, "; ".join(details)), numbers, specs


def write_robustness(folder, specs, questions):
    def fmt(v):
        return f"{v:.4g}" if number(v) is not None else "—"
    lines, families = ["# Robustness", "", "Written by check_causal.py from the last run in ledger.jsonl: every specification, "
                       "the headline first. An n that differs from the headline's is flagged.", ""], defaultdict(list)
    for x in specs:
        families[x.get("family")].append(x)
    for family, items in families.items():
        items.sort(key=lambda x: not causal_of(x).get("headline"))
        head = items[0] if causal_of(items[0]).get("headline") else None
        lines += [f"## {family}: {questions.get(family) or ''}", "",
                  "| Specification | Estimator | Estimate | Interval | n | Status |", "|---|---|---|---|---|---|"]
        for x in items:
            c, iv, n = causal_of(x), x.get("interval") or {}, x.get("n")
            interval = f"{fmt(iv.get('low'))} to {fmt(iv.get('high'))} ({iv['level']:.0%})" if number(iv.get("level")) else "—"
            shown = (", ".join(f"{k} {v}" for k, v in n.items()) if isinstance(n, dict) else fmt(n)) + \
                (" (differs from the headline)" if head and x is not head and n != head.get("n") else "")
            status = "headline" if c.get("headline") else "kept" if x.get("status") == "kept" else f"dropped: {x.get('reason')}"
            lines.append(f"| {c.get('label') or x.get('id')} | {c.get('estimator')} | {fmt(x.get('estimate'))} | {interval} "
                         f"| {shown} | {status} |")
        lines.append("")
    (folder / "robustness.md").write_text("\n".join(lines), encoding="utf-8")


def sentences(text):
    """(line, sentence) pairs, with code, links, headings and citations blanked as the number check does."""
    text = text.replace("−", "-")
    for pattern in cr.BLANKED:
        text = re.sub(pattern, lambda m: re.sub(r"[^\n]", " ", m.group(0)), text, flags=re.S if pattern[0] in "`<" else 0)
    start = 0
    for end in [m.start() for m in cr.SENTENCE_END.finditer(text)] + [len(text)]:
        lead = len(text[start:end]) - len(text[start:end].lstrip())
        yield text.count("\n", 0, start + lead) + 1, text[start:end]
        start = end


def prints(sentence, result):
    """Whether the sentence prints the result's estimate or an interval bound, at its rounding."""
    values = [v for v in ((result.get("estimate") or {}).get("value"), (result.get("interval") or {}).get("low"),
                          (result.get("interval") or {}).get("high")) if number(v) is not None]
    return any(abs((v if m.group(1) else abs(v)) - float(m.group(2).replace(",", "")) * (-1 if m.group(1) else 1))
               <= 0.5 * 10 ** -len(m.group(3)) * (1 + 1e-9) for m in cr.NUMBER.finditer(sentence) if m.group(3)
               for v in values)


def check_verbs(texts, causal, heads, route, probe):
    if not texts:
        return "verbs", "not_checked", [], "no --text given"
    allowed = set(route.get("headline", [])) | EVENT.get(route.get("design"), set())

    def reason(r, c):
        if probe and route.get("outcome") != "matched":
            return f"the probe's route is {route.get('outcome')}"
        if probe and not c.get("headline") and c.get("estimator") not in allowed:
            return f"{c.get('estimator')} is not a headline estimator for {route.get('design')}"
        source = c if c.get("headline") else next((h for x, h in heads if x.get("family") == r.get("family")), c)
        bad = [k for k in REQUIRED.get(source.get("design"), ()) if status_of(source, k) != "pass"]
        return f"required diagnostics not passed: {', '.join(bad)}" if bad else None

    general = next((why for why in (reason(r, c) for r, c in heads) if why), None) or \
        (f"the probe's route is {route.get('outcome')}" if probe and route.get("outcome") != "matched" else None)
    problems = []
    for path, text in texts.items():
        for line, sentence in sentences(text):
            verb = STRONG.search(sentence) or DIRECTIONAL.search(sentence)
            owners = [(r, c) for r, c in causal if prints(sentence, r)] if verb else []
            reasons = [reason(r, c) for r, c in owners]
            why = (reasons[0] if all(reasons) else None) if owners else general if verb and STRONG.search(sentence) else None
            if why:
                problems.append(f"{path.name}:{line}: '{verb.group(0)}' where {why}: describe the estimate instead")
    return row("verbs", problems, "no causal verb without the design behind it")


def check_script(script, record):
    if not script:
        return "script", "not_checked", [], "no --script given"
    state, findings = cr.lint_script(script, record)
    if state == "not_checked":
        return "script", "not_checked", [], findings[0]
    tree = ast.parse(script.read_text(encoding="utf-8"))
    modules = {a.asname or a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names
               if a.name == "causal_tools"}
    names = {a.asname or a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module == "causal_tools"
             for a in n.names if a.name == "spec"}
    if any(isinstance(n, ast.Call) and ((isinstance(n.func, ast.Attribute) and n.func.attr == "spec" and
                                         isinstance(n.func.value, ast.Name) and n.func.value.id in modules) or
                                        (isinstance(n.func, ast.Name) and n.func.id in names)) for n in ast.walk(tree)):
        findings = [f for f in findings if "never calls rz_results.record()" not in f]
    if record and cr.sha256(script) != (record.get("script") or {}).get("sha256"):
        findings.append(f"{script} changed after the run that wrote results.json: run it again")
    return row("script", findings, f"{script}: seed, typed data, input overwrite, recording")


def diagnostic_numbers(causal):
    """Labelled numbers the text may print from the diagnostics: statistics, their df, p-values."""
    found = []
    for r, c in causal:
        for key, entry in list((c.get("diagnostics") or {}).items()) + [("permutation", c.get("permutation"))]:
            if not isinstance(entry, dict):
                continue
            stat = entry.get("statistic") if isinstance(entry.get("statistic"), dict) else {}
            value = number(stat.get("value"), entry.get("value") if key == "first_stage_f" else None)
            found += [(value, "statistic", r["id"], f"diagnostics.{key}.statistic")] if value is not None else []
            found += [(float(d), "df", r["id"], f"diagnostics.{key}.df") for d in stat.get("df") or [] if number(d) is not None]
            found += [(float(h["p"]), "p", r["id"], f"diagnostics.{key}.p") for h in (entry, value_of(entry))
                      if number(h.get("p")) is not None]
    return found


def extend(content, cargs, args, probe):
    folder, route = Path(args.dir), (probe or {}).get("route") or {}
    causal = [(r, r["extra"]["causal"]) for r in content["results"] if isinstance((r.get("extra") or {}).get("causal"), dict)]
    heads = [(r, c) for r, c in causal if c.get("headline")]
    texts = {p: p.read_text(encoding="utf-8") for p in cargs.text if p.is_file()}
    specs_row, spec_numbers, specs = check_specifications(content, folder, texts)
    rows = [check_route(causal, heads, route, probe), check_diagnostics(heads), check_clustering(heads, probe),
            check_iv(heads, args.f_low) if any(c["design"] == "iv" for _, c in heads) else None,
            check_permutation(causal), check_rules(heads, texts, args.few_treated, probe), specs_row,
            check_verbs(texts, causal, heads, route, probe), check_script(args.script, content.get("record"))]
    if specs:
        write_robustness(folder, specs, {r.get("family"): r.get("question") for r in content["results"]})
    rows.append(("robustness", "ok" if specs else "not_checked", [],
                 f"{folder / 'robustness.md'}: {len(specs)} specification(s)" if specs else "no specification to tabulate"))
    return {"title": "Causal inference check", "checks": [r for r in rows if r],
            "numbers": diagnostic_numbers(causal) + spec_numbers}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Check a causal analysis against its design. Other options "
                                                 "(--text, --strict) go to check_results.py.")
    parser.add_argument("--probe", type=Path, help="causal/<data>.design.json written by probe_causal.py")
    parser.add_argument("--dir", default="causal", help="Folder with results.json (default: causal)")
    parser.add_argument("--script", type=Path, help="The analysis script, to lint it")
    parser.add_argument("--f-low", type=float, default=10.0, help="First-stage F below which the AR set leads "
                        "(default 10, the Staiger-Stock convention)")
    parser.add_argument("--few-treated", type=int, default=6, help="Treated clusters at or below which panel FE needs "
                        "randomization inference (default 6, after MacKinnon, Nielsen and Webb 2023)")
    args, rest = parser.parse_known_args(argv)
    probe = None
    if args.probe:
        try:
            probe = json.loads(args.probe.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            print(f"check_causal: could not read the probe {args.probe}: {exc}", file=sys.stderr)
            return 2
    return cr.main(["--dir", args.dir] + rest, extend=lambda content, cargs: extend(content, cargs, args, probe))


if __name__ == "__main__":
    sys.exit(main())
