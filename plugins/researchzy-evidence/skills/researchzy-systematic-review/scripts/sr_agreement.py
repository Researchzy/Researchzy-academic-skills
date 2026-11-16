#!/usr/bin/env python3
"""Calibrate the model's title-abstract screening against the user's, and audit the model's exclusions.

  sr_agreement.py sample --seed 20261113 [--size N]     records still to screen, drawn at random:
                                                        calibration/round<N>-user.csv and -model.csv
  sr_agreement.py score [--round N]                     Cohen's kappa, agreement, include recall
  sr_agreement.py sample --audit --size 59 --seed 7     the model's exclusions, drawn at random
  sr_agreement.py score --audit [--round N]             wrong exclusions, or an exact upper bound

The user fills the decision column of round<N>-user.csv and the model fills round<N>-model.csv with
include, exclude or unsure, each without seeing the other's. Unsure counts as include: an unsure record
goes on to full text. Kappa comes from the full 2x2 table, so chance agreement uses each reviewer's own
include rate, never an assumed 50/50. The thresholds are the protocol's calibration.kappa_min and
recall_min. Default size: 50, or 10% of the records still to screen if that is more, at most 100. A
scored round is final: a new attempt is a new round with a new seed.

An audit shows the user records the model excluded, without the model's reasons. With no wrong
exclusion among n of N it gives the largest number of wrong exclusions still consistent with that at
95% confidence (exact, hypergeometric). A spot check can find problems; it cannot prove there are none.

All commands take --dir (default systematic-review). Standard library only. Exit codes: 0 done; 1 the
round is below the thresholds or cannot be assessed, or the audit found a wrong exclusion; 2 an input
cannot be read or is incomplete.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
import sys
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sr_ledger as sl  # noqa: E402

COLUMNS = ("record", "title", "abstract", "year", "decision", "code", "note")
LABELS = {"include": True, "unsure": True, "exclude": False}
DEFAULTS = {"kappa_min": 0.60, "recall_min": 1.0}      # conventions, used only when no protocol is recorded
CONFIDENCE = Fraction(95, 100)                         # a fraction, so that the audit bound is exact
NOTE = "A spot check can find problems; it cannot prove there are none."


def fail(message: str):
    print(f"sr_agreement: {message}", file=sys.stderr)
    raise SystemExit(2)


def rounds(folder: Path, kind: str) -> list:
    names = (p.name[len(kind):-len("-sample.json")] for p in folder.glob(f"{kind}*-sample.json"))
    return sorted(int(n) for n in names if n.isdigit())


def cmd_sample(args, directory: Path, ledger: dict):
    grp, folder, kind = sl.groups(ledger), directory / "calibration", "audit" if args.audit else "round"
    fin, taken = sl.finals(ledger, grp), {r for p in folder.glob("*-sample.json") for r in sl.read_json(p)["records"]}
    if args.audit and not args.size:
        fail("an audit needs --size: how many of the model's exclusions the user will check")
    pool = [c for c in sorted(set(grp.values()), key=sl.num) if c not in taken and (
        (fin.get((c, "ta")) or {}).get("decision") == "exclude" and fin[(c, "ta")].get("reviewer") == "model" if args.audit
        else (c, "ta") not in fin and (c, "pre") not in fin)]
    size = min(len(pool), args.size or min(100, max(50, math.ceil(0.1 * len(pool)))))
    stem = f"{kind}{args.round or (rounds(folder, kind) or [0])[-1] + 1}"
    if not size or (folder / f"{stem}-sample.json").exists():
        fail("no records left to sample" if not size else f"{stem} exists already: choose another --round")
    picked = sorted(random.Random(args.seed).sample(pool, size), key=sl.num)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{stem}-sample.json").write_text(json.dumps({"kind": kind, "round": int(stem[len(kind):]), "seed": args.seed,
                                                            "population": len(pool), "size": size, "created": sl.now(),
                                                            "records": picked}, indent=2) + "\n", encoding="utf-8")
    members: dict = {}
    for rid, c in grp.items():
        members.setdefault(c, []).append(ledger["records"][rid])
    files = [folder / f"{stem}-{who}.csv" for who in (("user",) if args.audit else ("user", "model"))]
    for path in files:
        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(COLUMNS)
            for c in picked:
                rec = max(members[c], key=lambda r: len(r.get("abstract", "")))   # the fullest copy of the record
                writer.writerow([c, rec["title"], rec.get("abstract", ""), rec.get("year", ""), "", "", ""])
    return {"sample": stem, "population": len(pool), "size": size, "seed": args.seed, "files": [str(p) for p in files]}, 0


def read_decisions(path: Path, expected: list) -> dict:
    try:
        with open(path, newline="", encoding="utf-8-sig") as fh:
            rows = {(r.get("record") or "").strip(): r for r in csv.DictReader(fh)}
    except OSError as exc:
        fail(f"cannot read {path}: {exc.strerror or exc}")
    if set(rows) != set(expected):
        fail(f"{path.name} must hold exactly the {len(expected)} sampled records, as written by sample")
    blank = [rid for rid, r in rows.items() if (r.get("decision") or "").strip().lower() not in LABELS]
    if blank:
        fail(f"{path.name}: write include, exclude or unsure for {', '.join(blank[:5])}" + (" and more" if len(blank) > 5 else ""))
    return {rid: dict(r, decision=r["decision"].strip().lower()) for rid, r in rows.items()}


def agreement(pairs: list) -> dict:
    """Agreement statistics from (user includes, model includes) pairs."""
    n = len(pairs)
    a = sum(1 for u, m in pairs if u and m)
    b = sum(1 for u, m in pairs if u and not m)
    c = sum(1 for u, m in pairs if m and not u)
    d = n - a - b - c
    observed, chance = (a + d) / n, ((a + b) * (a + c) + (c + d) * (b + d)) / n ** 2
    return {"table": {"both_include": a, "user_include_model_exclude": b, "user_exclude_model_include": c, "both_exclude": d},
            "agreement": observed, "kappa": None if chance >= 1 else (observed - chance) / (1 - chance),
            "include_recall": a / (a + b) if a + b else None, "user_includes": a + b}


def upper_bound(population: int, audited: int) -> int:
    """The largest number of wrong exclusions among `population` for which a random sample of `audited`
    of them still finds none with probability of at least 1 - CONFIDENCE: hypergeometric, in whole numbers."""
    wrong, samples = 0, math.comb(population, audited)
    while wrong < population - audited and math.comb(population - wrong - 1, audited) >= (1 - CONFIDENCE) * samples:
        wrong += 1
    return wrong


def cmd_score(args, directory: Path, ledger: dict):
    folder, kind = directory / "calibration", "audit" if args.audit else "round"
    number = args.round or (rounds(folder, kind) or [None])[-1]
    stem = f"{kind}{number}"
    if number is None or not (folder / f"{stem}-sample.json").exists():
        fail(f"no {kind} sample to score: run sample first")
    if (folder / f"{stem}-score.json").exists():
        fail(f"{stem} has been scored, and a scored round is final: draw a new one")
    ids = sl.read_json(folder / f"{stem}-sample.json")["records"]
    population = sl.read_json(folder / f"{stem}-sample.json")["population"]
    user, title = read_decisions(folder / f"{stem}-user.csv", ids), lambda r: ledger["records"].get(r, {}).get("title", "")
    if args.audit:
        wrong = [r for r in ids if LABELS[user[r]["decision"]]]
        result = {"kind": "audit", "round": number, "audited": len(ids), "population": population, "wrong_exclusions": wrong,
                  "status": "wrong_exclusions_found" if wrong else "none_found", "note": NOTE}
        lines = [f"# Audit {number} of the model's exclusions", "", f"The user checked {len(ids)} of {population} exclusions "
                 f"made by the model, without its reasons, and found {len(wrong)} wrong" + (": " + ", ".join(wrong) if wrong else ".")]
        if not wrong:
            bound = upper_bound(population, len(ids))
            result.update(upper_bound=bound, upper_bound_share=bound / population)
            lines.append(f"At most {result['upper_bound']} of the {population} exclusions ({result['upper_bound_share']:.1%}) "
                         f"could still be wrong ({float(CONFIDENCE):.0%} confidence, exact hypergeometric bound).")
        lines += ["", NOTE]
    else:
        model = read_decisions(folder / f"{stem}-model.csv", ids)
        stats = agreement([(LABELS[user[r]["decision"]], LABELS[model[r]["decision"]]) for r in ids])
        cal = sl.protocol(ledger).get("calibration") or {}
        limits = {k: cal.get(k, v) for k, v in DEFAULTS.items()}
        status = "not_assessable" if None in (stats["kappa"], stats["include_recall"]) else "passed" if (
            stats["kappa"] >= limits["kappa_min"] and stats["include_recall"] >= limits["recall_min"]) else "below_threshold"
        result = {"kind": "calibration", "round": number, "size": len(ids), **stats, "thresholds": limits,
                  "thresholds_from": "protocol" if cal else "defaults: no protocol recorded", "status": status,
                  "disagreements": [{"record": r, "title": title(r), "user": user[r]["decision"], "model": model[r]["decision"],
                                     "model_code": model[r].get("code") or ""} for r in ids
                                    if LABELS[user[r]["decision"]] != LABELS[model[r]["decision"]]]}
        if (folder / f"{stem}-model.csv").stat().st_mtime > (folder / f"{stem}-user.csv").stat().st_mtime:
            result["warning"] = "the model's file changed after the user's: the model must decide before seeing the user's decisions"
        t, show = stats["table"], lambda v: "cannot be computed" if v is None else f"{v:.2f}"
        why = {"not_assessable": " Kappa needs both decisions in the sample and recall needs a record the user included: "
                                 "draw a new round."}.get(status, "")
        lines = [f"# Calibration round {number}", "", f"Status: {status.replace('_', ' ')}. Kappa {show(stats['kappa'])} (threshold "
                 f"{limits['kappa_min']}), include recall {show(stats['include_recall'])} (threshold {limits['recall_min']}); "
                 f"thresholds from the {result['thresholds_from']}.{why}", "",
                 "| | Model: include or unsure | Model: exclude |", "|---|---|---|",
                 f"| User: include or unsure | {t['both_include']} | {t['user_include_model_exclude']} |",
                 f"| User: exclude | {t['user_exclude_model_include']} | {t['both_exclude']} |", "",
                 f"Agreement: {t['both_include'] + t['both_exclude']} of {len(ids)}. The recall rests on the {stats['user_includes']} "
                 "records the user included or was unsure about.", *([f"Warning: {result['warning']}."] if "warning" in result else []),
                 "", "## Disagreements", "", "| Record | Title | User | Model | Model's code |", "|---|---|---|---|---|",
                 *[f"| {d['record']} | {sl.cell(d['title'])} | {d['user']} | {d['model']} | {sl.cell(d['model_code'])} |"
                   for d in result["disagreements"]]]
    result.update(scored=sl.now(), records=ids)
    (folder / f"{stem}-score.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (folder / f"{stem}-score.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    summary = {k: v for k, v in result.items() if k not in ("records", "disagreements")}
    return dict(summary, report=str(folder / f"{stem}-score.md")), 0 if result["status"] in ("passed", "none_found") else 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Calibrate and audit the model's title-abstract screening.")
    parser.add_argument("--dir", default="systematic-review", help="The review's folder (default: systematic-review)")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("sample", help="Draw a calibration sample, or with --audit a sample of the model's exclusions")
    p.add_argument("--seed", type=int, required=True)
    p.add_argument("--size", type=int, help="How many records (default for calibration: 50 or 10%%, at most 100)")
    p.add_argument("--round", type=int, help="The round number (default: the next one)")
    p.add_argument("--audit", action="store_true")
    p = sub.add_parser("score", help="Score a calibration round, or with --audit an audit")
    p.add_argument("--round", type=int, help="The round number (default: the latest sample)")
    p.add_argument("--audit", action="store_true")
    args = parser.parse_args(argv)
    directory = Path(args.dir)
    if not (directory / "ledger.json").exists():
        fail(f"no ledger in {directory}: run sr_ledger.py first")
    if args.command == "sample" and args.size is not None and args.size < 1:
        fail("--size must be at least 1")
    result, code = (cmd_sample if args.command == "sample" else cmd_score)(args, directory, sl.load(directory))
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return code


if __name__ == "__main__":
    sys.exit(main())
