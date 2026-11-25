#!/usr/bin/env python3
"""Agreement between coders, written from the textbook formulas. A shared Researchzy module: every copy of
this file must stay byte for byte the same.

  rz_agreement.py table.csv [--boot 1000] [--seed 7]     first column the unit, then one column per coder

Import it from a script in the same folder:

  sys.path.insert(0, str(Path(__file__).resolve().parent))
  import rz_agreement as ra

  ra.cohen_kappa(a, b)                                     two coders, one label per unit
  ra.kappa_by_code(units, coder_a, coder_b, codes=None)    several codes per unit: kappa on present or absent
  ra.krippendorff_alpha_nominal(table, n_boot=0, seed=None, level=0.95)
  ra.classification_report(truth, pred, classes=None)      per class, macro-F1, accuracy, confusion matrix

Each function returns a dict that json.dumps can write when the labels are strings, numbers or booleans.
None marks a missing label. A coefficient the data cannot give is None with "reason": "not_estimable" and a
"detail" sentence, never 1.0 or 0: no unit to compare, chance agreement of 1 (every coder used one and the
same label), or a class that does not occur in the sample.

The command prints alpha, and kappa when there are two coders, as JSON. Exit code 2 when the CSV cannot be
read. Standard library only.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from collections import Counter

NOT_ESTIMABLE = "not_estimable"


def _order(values) -> list:
    """The distinct values, sorted so that the result does not depend on the order of the units."""
    return sorted(set(values), key=lambda v: (type(v).__name__, str(v)))


def _percentile(values: list, q: float):
    """The q-quantile of sorted values, interpolated between neighbours; None when there are none."""
    if not values:
        return None
    h = (len(values) - 1) * q
    i = int(h)
    return values[i] + (h - i) * (values[i + 1] - values[i]) if i + 1 < len(values) else values[i]


def cohen_kappa(a, b) -> dict:
    """Cohen's kappa for two coders who gave one label per unit (Cohen 1960).

    a, b: sequences of the same length, in the same unit order. A unit that either coder left as None drops
    out. Chance agreement comes from each coder's own marginal totals in the full contingency table, never
    from an assumed even split. Raises ValueError when the lengths differ.

    Returns {"kappa": float | None, "reason": None | "not_estimable", "detail": str, "n": units compared,
    "missing": units dropped, "observed": p_o | None, "expected": p_e | None, "categories": [labels],
    "table": [[count]]} with a row per label of coder a and a column per label of coder b, both in the
    order of "categories". kappa = (p_o - p_e) / (1 - p_e); it is None when no unit is left, or when p_e is 1
    because both coders gave every unit the same label.
    """
    if len(a) != len(b):
        raise ValueError("cohen_kappa: both coders must label the same units, in the same order")
    pairs = [(x, y) for x, y in zip(a, b) if x is not None and y is not None]
    n, cats = len(pairs), _order(v for pair in pairs for v in pair)
    where = {c: i for i, c in enumerate(cats)}
    table = [[0] * len(cats) for _ in cats]
    for x, y in pairs:
        table[where[x]][where[y]] += 1
    chance = sum(sum(row) * sum(col) for row, col in zip(table, zip(*table)))    # p_e * n * n, whole, so 1 is exact
    out = {"kappa": None, "reason": NOT_ESTIMABLE, "detail": "", "n": n, "missing": len(a) - n,
           "observed": None, "expected": None, "categories": cats, "table": table}
    if not n:
        return dict(out, detail="no unit was labelled by both coders")
    out["observed"] = sum(table[i][i] for i in range(len(cats))) / n
    if chance == n * n:
        return dict(out, expected=1.0, detail=f"both coders gave every unit the label {cats[0]!r}, so chance agreement is 1")
    out["expected"] = chance / (n * n)
    return dict(out, kappa=(out["observed"] - out["expected"]) / (1 - out["expected"]), reason=None)


def kappa_by_code(units, coder_a, coder_b, codes=None) -> dict:
    """Cohen's kappa for each code on present or absent, so that one unit may carry several codes.

    units: the unit ids to score. coder_a, coder_b: {unit id: iterable of codes}. A unit that a coder's dict
    lacks, or maps to None, was not coded by that coder and drops out of every code's table; an empty
    iterable means the coder applied no code. codes: the codes to report, by default every code either
    coder applied, sorted. A listed code that neither coder applied is not estimable.

    Returns {code: the dict of cohen_kappa on True or False per unit, plus "a_present", "b_present" and
    "both_present": the numbers of compared units where coder a, coder b, and both applied the code}.
    """
    units = list(units)
    coded = [{u: None if coder.get(u) is None else set(coder[u]) for u in units} for coder in (coder_a, coder_b)]
    if codes is None:
        codes = _order(code for sets in coded for s in sets.values() if s for code in s)
    out = {}
    for code in codes:
        a, b = ([None if s[u] is None else code in s[u] for u in units] for s in coded)
        result = cohen_kappa(a, b)
        both = [(x, y) for x, y in zip(a, b) if x is not None and y is not None]
        result.update(a_present=sum(x for x, _ in both), b_present=sum(y for _, y in both),
                      both_present=sum(x and y for x, y in both))
        if result["n"] and result["kappa"] is None:
            result["detail"] = (f"both coders applied {code!r} to every unit" if both[0][0]
                                else f"neither coder applied {code!r} to any unit")
        out[code] = result
    return out


def _parts(units: list) -> tuple:
    """(n, the sum of off-diagonal coincidences, {value: n_c}) over units that have two values or more."""
    totals, off = Counter(), 0.0
    for values in units:
        counts, m = Counter(values), len(values)
        totals.update(counts)
        off += (m * m - sum(k * k for k in counts.values())) / (m - 1)    # ordered pairs of unequal values / (m - 1)
    return sum(totals.values()), off, totals


def _alpha(n: int, off: float, totals: Counter):
    expected = n * n - sum(k * k for k in totals.values())                # the sum over c != k of n_c * n_k
    return None if not n or not expected else 1 - (n - 1) * off / expected


def krippendorff_alpha_nominal(table, n_boot=0, seed=None, level=0.95) -> dict:
    """Krippendorff's alpha for nominal labels, from the coincidence matrix; any number of coders, missing allowed.

    table: one row per unit with one value per coder, None for a missing value; rows may differ in length.
    A unit with fewer than two values cannot be paired and drops out. With n pairable values, coincidences
    o_ck and their totals n_c: alpha = 1 - D_o / D_e, D_o = (sum over c != k of o_ck) / n and
    D_e = (sum over c != k of n_c * n_k) / (n * (n - 1)). With n_boot > 0 the pairable units are resampled
    with replacement n_boot times from random.Random(seed), and the percentile interval at `level` is taken
    over the resamples whose alpha is estimable.

    Returns {"alpha": float | None, "reason": None | "not_estimable", "detail": str, "units": rows given,
    "pairable_units": int, "values": n, "categories": [values], "coincidence": [[float]] in the order of
    "categories", "observed_disagreement": D_o | None, "expected_disagreement": D_e | None, "bootstrap":
    None, or {"n_boot", "seed", "level", "low", "high", "not_estimable_draws", "method"} when n_boot > 0 and
    alpha is estimable}. alpha is None when no unit is pairable or every pairable value is the same.
    """
    units = [[v for v in row if v is not None] for row in table]
    pairable = [u for u in units if len(u) >= 2]
    n, off, totals = _parts(pairable)
    cats = _order(totals)
    where = {c: i for i, c in enumerate(cats)}
    coincidence = [[0.0] * len(cats) for _ in cats]
    for values in pairable:
        counts = Counter(values)
        for c, x in counts.items():
            for k, y in counts.items():
                coincidence[where[c]][where[k]] += x * (y - (c == k)) / (len(values) - 1)
    expected = n * n - sum(k * k for k in totals.values())
    out = {"alpha": _alpha(n, off, totals), "reason": None, "detail": "", "units": len(units),
           "pairable_units": len(pairable), "values": n, "categories": cats, "coincidence": coincidence,
           "observed_disagreement": off / n if n else None,
           "expected_disagreement": expected / (n * (n - 1)) if n else None, "bootstrap": None}
    if out["alpha"] is None:
        return dict(out, reason=NOT_ESTIMABLE, detail="no unit has two values to compare" if not pairable
                    else f"every value is {cats[0]!r}, so no disagreement is expected by chance")
    if n_boot:
        rng, each, draws = random.Random(seed), [_parts([u]) for u in pairable], []
        for _ in range(n_boot):
            drawn, counts = [each[rng.randrange(len(each))] for _ in each], Counter()
            for part in drawn:
                counts.update(part[2])
            draws.append(_alpha(sum(p[0] for p in drawn), sum(p[1] for p in drawn), counts))
        good, tail = sorted(d for d in draws if d is not None), (1 - level) / 2
        out["bootstrap"] = {"n_boot": n_boot, "seed": seed, "level": level, "low": _percentile(good, tail),
                            "high": _percentile(good, 1 - tail), "not_estimable_draws": n_boot - len(good),
                            "method": "percentile interval over units resampled with replacement"}
    return out


def classification_report(truth, pred, classes=None) -> dict:
    """Precision, recall, F1 and support per class, macro-F1, accuracy and the confusion matrix.

    truth, pred: sequences of the same length, one label per unit, in the same order; a unit with None on
    either side drops out. Raises ValueError when the lengths differ. classes: the classes to report, in
    order (default: every label seen, sorted). A label outside `classes` is listed in "unknown_labels" and
    gets its own row or column of the confusion matrix, so that nothing is dropped silently.

    Per class, with TP, FP, FN counted from the matrix: precision = TP / (TP + FP), None when the class was
    never predicted; recall = TP / (TP + FN) and F1 = 2TP / (2TP + FP + FN), both None with reason
    "not_estimable" when the class does not occur in `truth`: the sample says nothing about it, so it is
    never reported as 0 or 1. macro-F1 is the mean F1 over the classes that occur in `truth`.

    Returns {"n", "missing", "accuracy": float | None, "macro_f1": float | None, "macro_f1_classes": [...],
    "classes": {class: {"precision", "recall", "f1", "support", "predicted", "reason", "detail"}},
    "confusion": {"labels": [...], "matrix": [[count]]} with a row per true label and a column per predicted
    label, "unknown_labels": {"truth": [...], "pred": [...]}}.
    """
    if len(truth) != len(pred):
        raise ValueError("classification_report: truth and pred must cover the same units, in the same order")
    pairs = [(t, p) for t, p in zip(truth, pred) if t is not None and p is not None]
    classes = list(classes) if classes is not None else _order(v for pair in pairs for v in pair)
    unknown = {"truth": _order(t for t, _ in pairs if t not in classes), "pred": _order(p for _, p in pairs if p not in classes)}
    labels = classes + [x for x in _order(unknown["truth"] + unknown["pred"]) if x not in classes]
    where = {c: i for i, c in enumerate(labels)}
    matrix = [[0] * len(labels) for _ in labels]
    for t, p in pairs:
        matrix[where[t]][where[p]] += 1
    per = {}
    for c in classes:
        i = where[c]
        tp, support, predicted = matrix[i][i], sum(matrix[i]), sum(row[i] for row in matrix)
        per[c] = {"precision": tp / predicted if predicted else None, "recall": tp / support if support else None,
                  "f1": 2 * tp / (predicted + support) if support else None, "support": support,
                  "predicted": predicted, "reason": None if support else NOT_ESTIMABLE,
                  "detail": "" if support else f"{c!r} does not occur in the reference labels of this sample"}
        if support and not predicted:
            per[c]["detail"] = f"{c!r} was never predicted, so its precision is not estimable"
    scored, n = [c for c in classes if per[c]["f1"] is not None], len(pairs)
    return {"n": n, "missing": len(truth) - n,
            "accuracy": sum(matrix[i][i] for i in range(len(labels))) / n if n else None,
            "macro_f1": sum(per[c]["f1"] for c in scored) / len(scored) if scored else None, "macro_f1_classes": scored,
            "classes": per, "confusion": {"labels": labels, "matrix": matrix}, "unknown_labels": unknown}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Nominal alpha, and kappa for two coders, from a CSV of units by coders.")
    parser.add_argument("table", help="CSV with a header row: the unit, then one column per coder; a blank cell is missing")
    parser.add_argument("--boot", type=int, default=0, help="Bootstrap resamples for alpha's interval (default 0: none)")
    parser.add_argument("--seed", type=int, default=1, help="Seed of the bootstrap (default 1)")
    args = parser.parse_args(argv)
    try:
        with open(args.table, encoding="utf-8-sig", newline="") as handle:
            rows = [row for row in csv.reader(handle) if any(cell.strip() for cell in row)]
    except (OSError, UnicodeDecodeError) as exc:
        print(f"rz_agreement: cannot read {args.table}: {exc}", file=sys.stderr)
        return 2
    if len(rows) < 2 or len(rows[0]) < 3:
        print("rz_agreement: the CSV needs a header row, a unit column and two or more coder columns", file=sys.stderr)
        return 2
    width = len(rows[0])
    table = [[(row[i].strip() or None) if i < len(row) else None for i in range(1, width)] for row in rows[1:]]
    result = {"coders": rows[0][1:], "units": len(table), "alpha": krippendorff_alpha_nominal(table, args.boot, args.seed)}
    if width == 3:
        result["kappa"] = cohen_kappa([row[0] for row in table], [row[1] for row in table])
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
