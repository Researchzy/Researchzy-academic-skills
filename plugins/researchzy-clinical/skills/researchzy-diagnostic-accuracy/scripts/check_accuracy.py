#!/usr/bin/env python3
"""Check diagnostic-accuracy/results.json, the scripts behind it and the text written from it.

  check_accuracy.py --probe diagnostic-accuracy/nodules.probe.json --script diagnostic-accuracy/analysis.py
  check_accuracy.py --probe diagnostic-accuracy/nodules.probe.json --lint model.py \\
      --text diagnostic-accuracy/results.md diagnostic-accuracy/methods.md

Runs the checks of check_results.py (the copy next to this file; --dir defaults to diagnostic-accuracy)
on the results rz_accuracy.record() wrote, with their fields in extra["accuracy"], and adds:

  fields       kind, model, dataset, design, units, patients, positives; a measure's method, and its
               numerator and denominator unless it rests on a stated prevalence
  intervals    an AUC or AUC difference has an interval and its method; units that share a patient
               take a bootstrap by patient, with resamples and seed
  calibration  a model with an AUC on a dataset has a calibration result there, or no_calibration
  predictive   PPV, NPV and net benefit from a consecutive or cross-sectional sample, or a stated
               prevalence with its source
  thresholds   a cut-off comes from the plan, the development data or a cited publication, never the
               test data; a 2x2 of a model that has an AUC names its cut-off
  internal     an AUC on development data has an optimism result: apparent, optimism, corrected, B, seed
  leakage      a test-set result carries a probe whose leakage status was ok, of a file this run read;
               a --probe given is ok now; no null-label check found a problem
  lint         (--lint, --script) leads, never failures: a scaler, imputer, selector or univariate test
               run outside a function before the split; a split that ignores patients with several rows

With --text: paragraphs (an AUC or measure printed with its name has both bounds printed with it at
least once), apparent (a paragraph with an apparent AUC also prints the corrected one), comparison (two
models' AUCs on one dataset are compared by their paired difference, never by overlapping intervals),
cutoff_text (no cut-off chosen as optimal or by Youden's index on test data), verification (rows a probe
found without the reference standard are mentioned), methods (each recorded interval method is named). Labels added to the number check, also in
Chinese: AUC, C statistic (曲线下面积), sensitivity (灵敏度), specificity (特异度), PPV, NPV, LR+, LR-
(阳性/阴性似然比), slope (斜率), intercept (截距), net benefit (净获益), cut-off (截断值, 截点, 阈值),
Brier; a proportion may be printed as a per cent, with or without the % sign.

Writes check.md and prints a JSON summary. Exit code 1 on a failed check or a mismatch in the text
(with --strict also a number not found); 2 when results.json or a probe cannot be read. Standard
library only.
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

DESIGNS = ("consecutive", "cross_sectional", "case_control", "enriched")     # the vocabularies of rz_accuracy.py
COHORT, SOURCES = DESIGNS[:2], ("plan", "development", "published")
DATASETS = ("development", "internal_validation", "test", "external", "study")
KINDS = ("two_by_two", "auc", "auc_difference", "paired_difference", "calibration", "net_benefit", "optimism",
         "null_label")
MEASURES = {"sensitivity": "sensitivity", "specificity": "specificity", "ppv": "ppv", "npv": "npv",
            "lr_positive": "lr_pos", "lr_negative": "lr_neg"}
PROPORTIONS = ("sensitivity", "specificity", "ppv", "npv")
S, TAIL = cr.START, r"\s*(?:\([^()]*\))?\s*(?:=|:|：|为|是|达|of|was|is)?\s*$"
NAMES = {"auc": rf"{S}AUC|{S}AUROC|{S}c[- ]?(?:statistic|index)|C\s*统计量|C\s*指数|曲线下面积",
         "sensitivity": rf"{S}sensitivity|灵敏度|敏感度|敏感性", "specificity": rf"{S}specificity|特异度|特异性",
         "ppv": rf"{S}PPV|{S}positive predictive value|阳性预测值", "npv": rf"{S}NPV|{S}negative predictive value|阴性预测值",
         "lr_pos": rf"{S}LR\s*\+|{S}positive likelihood ratio|阳性似然比", "lr_neg": rf"{S}LR\s*-|{S}negative likelihood "
         r"ratio|阴性似然比", "slope": rf"{S}(?:calibration\s+)?slope|斜率", "intercept": rf"{S}(?:calibration\s+)?intercept|"
         rf"{S}calibration-in-the-large|截距", "net_benefit": rf"{S}net benefit|净获益|净收益",
         "threshold": rf"{S}cut-?off(?:\s+(?:value|point))?|{S}cut[- ]?point|{S}threshold(?:\s+probability)?|截断值|截点|"
         r"临界值|阈值|切点", "brier": rf"{S}Brier(?:\s+score)?|Brier\s*评分"}
LABELS = tuple((kind, re.compile(rf"(?:{names}){TAIL}", re.I)) for kind, names in NAMES.items())
WORD = {kind: re.compile(names, re.I) for kind, names in NAMES.items()}
COMPARE = re.compile(r"\b(?:higher|lower|greater|smaller|better|worse|outperform\w*|superior|inferior|exceed\w*|than|"
                     r"versus|vs\.?|compar\w*|differ\w*)\b|高于|低于|优于|劣于|大于|小于|差异|相比|比较", re.I)
OVERLAP = re.compile(r"\b(?:intervals?|CIs?)\b[^.;]{0,40}\boverlap|\boverlapping\s+(?:confidence\s+)?intervals|"
                     r"区间[^。；]{0,10}重叠", re.I)
CHOSEN = re.compile(r"youden|\b(?:optimal|optimum|best)\s+(?:cut-?off|cut[- ]?point|threshold)|maximi[sz]\w*\s+(?:the\s+)?"
                    r"(?:sum|youden|sensitivity)|约登|最佳(?:截断值|截点|临界值|阈值|切点)|最优(?:截断值|截点|临界值|阈值)", re.I)
TEST_DATA = re.compile(r"\b(?:test(?:ing)?|validation|hold-?out)\s+(?:set|data|cohort|sample|split|group)|测试集|验证集|"
                       r"检验集|测试组|验证组", re.I)
DEV_DATA = re.compile(r"\b(?:development|training|derivation|plan|pre-?specified)\b|开发|训练|建模|计划|预先", re.I)
PARTIAL = re.compile(r"partial(?:ly)?\s+verif|\bnot\s+verified|\bunverified|\bwithout\s+(?:a\s+|the\s+)?(?:reference\s+"
                     r"standard|biops\w+|histolog\w*|verification)|\b(?:no|did\s+not\s+(?:undergo|have|receive)|missing)\s+"
                     r"(?:a\s+|the\s+)?(?:reference\s+standard|biops\w+|verification)|部分验证|未(?:接受|进行|行|做)?(?:活检|"
                     r"金标准|病理)|(?:金标准|活检|病理)(?:结果)?缺失|没有(?:活检|金标准)", re.I)
PREP = {"StandardScaler", "MinMaxScaler", "RobustScaler", "MaxAbsScaler", "Normalizer", "QuantileTransformer",
        "PowerTransformer", "SimpleImputer", "KNNImputer", "IterativeImputer", "SelectKBest", "SelectPercentile",
        "SelectFpr", "SelectFdr", "SelectFwe", "GenericUnivariateSelect", "VarianceThreshold", "SelectFromModel", "RFE",
        "RFECV", "SequentialFeatureSelector", "PCA", "Pipeline", "make_pipeline"}
FILTERS = {"f_classif", "chi2", "mutual_info_classif", "ttest_ind", "mannwhitneyu", "ranksums", "pointbiserialr"}
PLAIN = {"train_test_split", "ShuffleSplit", "StratifiedShuffleSplit", "KFold", "StratifiedKFold", "RepeatedKFold",
         "RepeatedStratifiedKFold", "LeaveOneOut", "cross_val_score", "cross_validate", "cross_val_predict"}
SPLITTERS = PLAIN - {"cross_val_score", "cross_validate", "cross_val_predict"} | {
    "GroupShuffleSplit", "GroupKFold", "StratifiedGroupKFold", "LeaveOneGroupOut", "PredefinedSplit"}
BOUND = re.compile(r"(?:\bCI\b|置信区间)[\s:：,，]*$|(?:\bto\b|[-–—~～至])\s*$")      # a number that ends an interval
METHOD_WORDS = {"DeLong": r"DeLong", "bootstrap": r"bootstrap|自助|重抽样", "Clopper-Pearson": r"Clopper[- –]Pearson|\bexact\b|精确",
                "Wilson": r"Wilson", "Newcombe": r"Newcombe"}
SPLIT_WORD = re.compile(r"^(?:train(?:ing)?|dev(?:elopment)?|derivation|test(?:ing)?|valid(?:ation)?|hold-?out|开发|训练|"
                        r"测试|验证)|\b(?:train|dev|development|test|valid|validation)\b", re.I)


def row(name, problems, detail, unchecked=()):
    status = "fail" if problems else "not_checked" if unchecked else "ok"
    return name, status, problems, "; ".join(unchecked) if unchecked and not problems else detail


def check_records(items, record, probes):
    by, fields, intervals = defaultdict(list), [], []
    for r, a in items:
        by[a.get("kind")].append((r, a))
        lacks = [k for k in ("kind", "model", "dataset", "design") if not cr.has_text(a.get(k))] + \
            [k for k in ("units", "patients", "positives") if not isinstance(a.get(k), int)]
        fields += [f"{r['id']}: extra['accuracy'] lacks {', '.join(lacks)}"] * bool(lacks)
        fields += [f"{r['id']}: {k} {a[k]!r} is not one of {', '.join(v)}" for k, v in
                   (("kind", KINDS), ("dataset", DATASETS), ("design", DESIGNS)) if a.get(k) is not None and a[k] not in v]
        if a.get("kind") == "two_by_two":
            m = a.get("measure")
            if m not in MEASURES or not cr.has_text(a.get("method")):
                fields.append(f"{r['id']}: a measure needs its name and interval method")
            elif m in PROPORTIONS and not a.get("prevalence") and not (cr.is_number(a.get("numerator")) and cr.is_number(a.get("denominator"))):
                fields.append(f"{r['id']}: {m} without its numerator and denominator")
            if not r.get("interval") and not cr.has_text(a.get("no_interval")):
                fields.append(f"{r['id']}: no interval and no reason for none")
    for r, a in by["auc"] + by["auc_difference"]:
        method = str(a.get("method") or "")
        if not r.get("interval") and not cr.has_text(a.get("no_interval")):
            intervals.append(f"{r['id']}: an AUC without an interval: record rz_accuracy.auc(), which gives one")
        if not method:
            intervals.append(f"{r['id']}: the interval method is not named")
        elif cr.is_number(a.get("patients")) and cr.is_number(a.get("units")) and a["patients"] < a["units"] and "bootstrap" not in method:
            intervals.append(f"{r['id']}: {a['units']} units from {a['patients']} patients are not independent: the "
                             f"interval comes from a bootstrap by patient (groups= and seed=), not from {method}")
        if "bootstrap" in method and not (isinstance(a.get("B"), int) and isinstance(a.get("seed"), int)):
            intervals.append(f"{r['id']}: a bootstrap interval without its resamples (B) and seed")
    calibrated = {(a.get("model"), a.get("dataset")) for _, a in by["calibration"]}
    calibration = [f"{r['id']}: no calibration result for {a.get('model')} on {a.get('dataset')}: record "
                   "rz_accuracy.calibration() on the same data, or no_calibration='why the output is not a risk'"
                   for r, a in by["auc"] if (a.get("model"), a.get("dataset")) not in calibrated
                   and not cr.has_text(a.get("no_calibration"))]
    predictive = []
    for r, a in items:
        stated = a.get("prevalence") if isinstance(a.get("prevalence"), dict) else {}
        sourced = cr.is_number(stated.get("value")) and cr.has_text(stated.get("source")) and stated.get("source") != "the sample"
        if (a.get("measure") in ("ppv", "npv") or a.get("kind") == "net_benefit") and a.get("design") not in COHORT \
                and not sourced:
            predictive.append(f"{r['id']}: a {a.get('design')} sample fixes the share of positives: "
                              f"{a.get('measure') or 'net benefit'} needs the target population's prevalence and its source")
    scored, cutoffs = {a.get("model") for _, a in by["auc"]}, []
    for r, a in items:
        t = a.get("threshold")
        if isinstance(t, dict) and t.get("source") not in SOURCES:
            cutoffs.append(f"{r['id']}: the cut-off's source is {t.get('source')!r}: it comes from the plan, the "
                           "development data or a published source, never the test data")
        elif isinstance(t, dict) and t["source"] == "published" and not cr.has_text(t.get("citation")):
            cutoffs.append(f"{r['id']}: a published cut-off without its citation")
        elif t is None and a.get("kind") == "two_by_two" and a.get("model") in scored:
            cutoffs.append(f"{r['id']}: {a.get('model')} is a score (it has an AUC): name the cut-off and its source "
                           "with threshold=")
    internal = [f"{r['id']}: optimism needs the apparent, optimism and corrected AUC, B and the seed" for r, a in
                by["optimism"] if not all(cr.is_number(((a.get("metrics") or {}).get("auc") or {}).get(k)) for k in
                                          ("apparent", "optimism", "corrected"))
                or not isinstance(a.get("B"), int) or not isinstance(a.get("seed"), int)]
    optimistic = {a.get("model") for _, a in by["optimism"]}
    internal += [f"{r['id']}: an apparent AUC of {a.get('model')} on its development data: record rz_accuracy.optimism() "
                 "for this model and report the corrected value beside it" for r, a in by["auc"]
                 if a.get("dataset") == "development" and a.get("model") not in optimistic]
    leakage, run_data = [], {e.get("sha256") for e in (record or {}).get("data") or []}
    tests = [(r, a) for r, a in items if a.get("dataset") == "test"]
    for r, a in tests:
        lk = a.get("leakage") or {}
        if lk.get("status") != "ok":
            leakage.append(f"{r['id']}: a test-set result without a probe whose leakage status is ok")
        elif record and lk.get("data_sha256") not in run_data:
            leakage.append(f"{r['id']}: its probe read a file this run did not read, or the data changed: probe again")
    nulls = [r["id"] for r, a in by["null_label"] if a.get("status") == "problem"]
    if tests and nulls:
        leakage.append(f"the null-label check {', '.join(nulls)} found a problem: no test-set result stands until it is solved")
    for path, probe in probes.items():
        if record and probe["file"].get("sha256") not in run_data:
            leakage.append(f"{path}: the probe is of a file this run did not read, or the data changed: probe again")
        if tests and (probe.get("leakage") or {}).get("status") != "ok":
            leakage.append(f"{path}: the probe's leakage status is {(probe.get('leakage') or {}).get('status')}, and "
                           f"{len(tests)} test-set result(s) are recorded")
    return [row("fields", fields, f"{len(items)} accuracy result(s) with their fields"),
            row("intervals", intervals, f"{len(by['auc']) + len(by['auc_difference'])} AUC result(s) with an interval "
                "and its method"),
            row("calibration", calibration, f"{len(by['auc'])} AUC result(s) have calibration or a reason"),
            row("predictive", predictive, "predictive values and net benefit only where the prevalence is known"),
            row("thresholds", cutoffs, "every cut-off has an allowed source"),
            row("internal", internal, f"{len(by['optimism'])} optimism result(s)"),
            row("leakage", leakage, f"{len(tests)} test-set result(s); probes: {', '.join(probes) or 'none'}",
                ["no --probe given: the probe's current status was not read"] if tests and not probes else [])]


def tokens(text: str) -> list:
    """(value, tolerance, per cent, has decimals, is an interval bound) of each number, skipping years, names and
    references."""
    out = []
    for m in cr.NUMBER.finditer(text):
        before, after = text[text.rfind("\n", 0, m.start()) + 1:m.start()], text[m.end():m.end() + 2]
        digits, whole = m.group(2).replace(",", ""), m.group(3) is None
        if (after[:1].isalpha() and not re.match(f"[{cr.HAN}]", after)) or cr.REFERENCE.search(before) or \
                (whole and len(digits) == 4 and 1900 <= int(digits) <= 2100 and not m.group(6)):
            continue
        out.append(((-1 if m.group(1) else 1) * float(digits), 0.5 * 10 ** -len(m.group(3) or "") * (1 + 1e-9),
                    bool(m.group(6)), not whole or bool(m.group(6)), bool(BOUND.search(text[max(0, m.start() - 12):m.start()]))))
    return out


def shows(value, found, scales=(1,), decimals_only=False) -> bool:
    """Whether a number of the text prints value; decimals_only also skips interval bounds (an estimate, not a bound)."""
    return cr.is_number(value) and any(abs(value * f - v) <= tol for v, tol, pct, dec, bound in found
                                       for f in set(scales) | ({1, 100} if pct else set())
                                       if not decimals_only or (dec and not bound))


def blocks(text, pattern):
    """(line, block) for each paragraph (blank lines) or sentence (cr.SENTENCE_END) of a text."""
    out, start = [], 0
    for end in [m.start() for m in re.finditer(pattern, text)] + [len(text)]:
        block = text[start:end]
        if block.strip():
            out.append((text.count("\n", 0, start + len(block) - len(block.lstrip())) + 1, block))
        start = end
    return out


def check_text(items, texts, probes):
    if not texts:
        return [(n, "not_checked", [], "no --text given") for n in
                ("methods", "paragraphs", "apparent", "comparison", "cutoff_text", "verification")]
    apparent, comparison, cutoff, bare = [], [], [], {}
    diffs = {(a.get("dataset"), frozenset(a.get("models") or ())): r for r, a in items if a.get("kind") == "auc_difference"}
    for path, text in texts.items():
        for line, block in blocks(re.sub(r"(?m)^[ \t]*\|.*$", "", text), r"\n\s*\n"):   # table rows are not paragraphs
            found, where, printed = tokens(block), f"{path.name}:{line}", defaultdict(set)
            for r, a in items:
                kind, iv, value = a.get("kind"), r.get("interval") or {}, (r.get("estimate") or {}).get("value")
                word = WORD["auc"] if kind in ("auc", "auc_difference") else WORD.get(MEASURES.get(a.get("measure"), ""))
                scales = (1, 100) if a.get("measure") in PROPORTIONS else (1,)
                if word is not None and word.search(block) and shows(value, found, scales, True):
                    if kind == "auc":
                        printed[a.get("dataset")].add(a.get("model"))
                    if iv:                      # one printing with both bounds lets later mentions leave them out
                        bare[r["id"]] = None if all(shows(iv.get(k), found, scales) for k in ("low", "high")) else \
                            bare.get(r["id"], where)
                metric = (a.get("metrics") or {}).get("auc") or {}
                if metric and WORD["auc"].search(block) and shows(metric.get("apparent"), found, decimals_only=True) \
                        and not shows(metric.get("corrected"), found, decimals_only=True):
                    apparent.append(f"{where}: the apparent AUC of {a.get('model')} is printed without its "
                                    f"optimism-corrected value {metric['corrected']:.3f}")
            for dataset, models in printed.items():
                if len(models) > 1 and (COMPARE.search(block) or OVERLAP.search(block)):
                    pair = next((d for (ds, ms), d in diffs.items() if ds == dataset and len(ms) == 2 and ms <= models), None)
                    if pair is None or not shows(pair["estimate"]["value"], found, decimals_only=True):
                        comparison.append(f"{where}: compares the AUCs of {' and '.join(sorted(models))} on {dataset} "
                                          "without their paired difference: " + (
                                              "record rz_accuracy.compare_auc() and print it" if pair is None else
                                              f"print {pair['id']} with its interval"))
        for line, sentence in blocks(text, cr.SENTENCE_END.pattern):
            if OVERLAP.search(sentence):
                comparison.append(f"{path.name}:{line}: overlapping intervals are no test of a difference: print the "
                                  "paired difference and its interval")
            if CHOSEN.search(sentence) and TEST_DATA.search(sentence) and not DEV_DATA.search(sentence):
                cutoff.append(f"{path.name}:{line}: a cut-off chosen on the test data: use the planned cut-off or one "
                              "chosen on the development data")
    joined, verification = "\n".join(texts.values()), []
    for name, probe in probes.items():
        check = (probe.get("checks") or {}).get("verification") or {}
        if check.get("status") == "problem" and not PARTIAL.search(joined):
            verification.append(f"{name}: {check.get('count')} row(s) have no reference standard: say so in the text, "
                                "with the counts by index result")
    unnamed = defaultdict(list)
    for r, a in items:
        for label, pattern in METHOD_WORDS.items():
            if label.lower() in str(a.get("method") or "").lower() and not re.search(pattern, joined, re.I):
                unnamed[label].append(r["id"])
    methods = [f"{label}, the interval method of {ids[0]}" + (f" and {len(ids) - 1} more" if len(ids) > 1 else "")
               + ", is named in no text" for label, ids in unnamed.items()]
    return [row("methods", methods, "every recorded interval method is named"),
            row("paragraphs", [f"{w}: {rid} is printed without both bounds of its interval" for rid, w in bare.items()
                               if w], "every printed AUC and measure carries both bounds"),
            row("apparent", apparent, "apparent AUCs come with their corrected values"),
            row("comparison", sorted(set(comparison)), "AUCs are compared through their paired difference"),
            row("cutoff_text", cutoff, "no cut-off chosen on the test data"),
            row("verification", verification, "partial verification is reported", [] if probes else ["no --probe given"])]


def dotted(node) -> str:
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    return ".".join(reversed(parts + ([node.id] if isinstance(node, ast.Name) else [])))


def lint(paths, repeated):
    """Leads from reading the scripts (heuristics: each is for a person to look at)."""
    leads, unread = [], []
    for path in paths:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, ValueError) as exc:
            unread.append(f"{path} could not be read as Python ({type(exc).__name__})")
            continue
        top, stack = [], list(tree.body)                 # what runs at module level, outside functions and classes
        while stack:
            node = stack.pop()
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
                top.append(node)
                stack.extend(ast.iter_child_nodes(node))
        made = {t.id: dotted(n.value.func).rsplit(".", 1)[-1] for n in top if isinstance(n, ast.Assign)
                and isinstance(n.value, ast.Call) for t in n.targets if isinstance(t, ast.Name)}

        def is_split(n):
            name = dotted(n.func).rsplit(".", 1)[-1] if isinstance(n, ast.Call) else ""
            words = [c.value for c in ([n.left, *n.comparators] if isinstance(n, ast.Compare) else n.args if name == "query"
                                       else []) if isinstance(c, ast.Constant) and isinstance(c.value, str)]
            return name in SPLITTERS or any(SPLIT_WORD.search(w.strip()) for w in words)

        first = min((n.lineno for n in top if is_split(n)), default=None)
        for n in sorted((n for n in top if isinstance(n, ast.Call)), key=lambda n: n.lineno):
            last, what = dotted(n.func).rsplit(".", 1)[-1], None
            if last in ("fit", "fit_transform") and isinstance(n.func, ast.Attribute):
                owner = n.func.value
                what = dotted(owner.func).rsplit(".", 1)[-1] if isinstance(owner, ast.Call) else \
                    made.get(owner.id) if isinstance(owner, ast.Name) else None
                what = what if what in PREP else None
            elif last in FILTERS:
                what = f"{last}()"
            if what and (first is None or n.lineno < first):
                leads.append(f"{path.name}:{n.lineno}: {what} is fitted on all rows "
                             + (f"before the split (line {first})" if first else "and no split was found")
                             + ": fit it inside the pipeline function, so each resample and each split refits it")
        leads += [f"{path.name}:{n.lineno}: {dotted(n.func).rsplit('.', 1)[-1]}() splits rows, not patients, and patients "
                  "have several rows: use a grouped split (GroupKFold, GroupShuffleSplit) or the user's split column"
                  for n in ast.walk(tree) if isinstance(n, ast.Call) and repeated and dotted(n.func).rsplit(".", 1)[-1] in PLAIN
                  and not any(k.arg == "groups" for k in n.keywords)]
    return leads, unread


def numbers(items, probes):
    """Labelled values the text may print, with per-cent versions of proportions."""
    out = []

    def add(value, kind, owner, path, percent=False):
        if cr.is_number(value):
            out.extend([(float(value), kind, owner, path)] + [(float(value) * 100, kind, owner, f"{path} x 100")] * percent)

    for r, a in items:
        rid, est, iv = r.get("id"), r.get("estimate") or {}, r.get("interval") or {}
        label = "auc" if a.get("kind") in ("auc", "auc_difference", "null_label") else MEASURES.get(a.get("measure"))
        if label:
            for key, value in (("estimate", est.get("value")), ("interval.low", iv.get("low")), ("interval.high", iv.get("high"))):
                add(value, label, rid, key, a.get("measure") in PROPORTIONS)
            for key in ("numerator", "denominator"):
                add(a.get(key), label, rid, key)
        for model, value in (a.get("auc") or {}).items():
            add(value, "auc", rid, f"auc.{model}")
        add(a.get("against_true_labels"), "auc", rid, "against_true_labels")
        for name, values in [(k, a.get(k)) for k in ("slope", "intercept")] + list((a.get("metrics") or {}).items()):
            for key, value in (values if isinstance(values, dict) else {}).items():
                add(value, name, rid, f"{name}.{key}")
        add(a.get("brier"), "brier", rid, "brier")
        for i, at in enumerate(a.get("at") or []):
            for key, kind in (("threshold", "threshold"), ("model", "net_benefit"), ("treat_all", "net_benefit")):
                add(at.get(key), kind, rid, f"at.{i}.{key}", True)
        for key in ("from", "to"):
            add((a.get("thresholds") or {}).get(key), "threshold", rid, f"thresholds.{key}", True)
        add((a.get("threshold") or {}).get("value") if isinstance(a.get("threshold"), dict) else None, "threshold", rid,
            "threshold")
    for name, probe in probes.items():
        check, owner = (probe.get("checks") or {}).get("verification") or {}, f"probe {name}"
        add(probe["file"].get("rows"), "value", owner, "file.rows")
        add(check.get("count"), "value", owner, "verification.count")
        for split, groups in (check.get("by") or {}).items():
            for cls, c in groups.items():
                for key in ("rows", "missing", "share"):
                    add(c.get(key), "value", owner, f"verification.{split}.{cls}.{key}", key == "share")
    return out


def check_script(script, record):
    if not script:
        return "script", "not_checked", [], "no --script given"
    state, findings = cr.lint_script(script, record)
    if state == "not_checked":
        return "script", "not_checked", [], findings[0]
    tree = ast.parse(script.read_text(encoding="utf-8"))
    names = {a.asname or a.name for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom)) for a in n.names
             if a.name == "rz_accuracy" or (isinstance(n, ast.ImportFrom) and n.module == "rz_accuracy" and a.name == "record")}
    if any(isinstance(n, ast.Call) and (dotted(n.func) in {f"{m}.record" for m in names} or dotted(n.func) in names)
           for n in ast.walk(tree)):
        findings = [f for f in findings if "never calls rz_results.record()" not in f]
    if record and cr.sha256(script) != (record.get("script") or {}).get("sha256"):
        findings.append(f"{script} changed after the run that wrote results.json: run it again")
    return row("script", findings, f"{script}: seed, typed data, input overwrite, recording")


def extend(content, cargs, args, probes):
    items = [(r, r["extra"]["accuracy"]) for r in content["results"] if isinstance((r.get("extra") or {}).get("accuracy"), dict)]
    strays = [f"{r.get('id')}: no extra['accuracy']: not recorded through rz_accuracy.record()" for r in content["results"]
              if not isinstance((r.get("extra") or {}).get("accuracy"), dict)]
    texts = {}
    for path in (p for p in cargs.text if p.is_file()):           # as check_results.py reads it, code and links blanked
        texts[path] = path.read_text(encoding="utf-8").replace("−", "-").translate(cr.FULL_WIDTH)
        for pattern in cr.BLANKED:
            texts[path] = re.sub(pattern, lambda m: re.sub(r"[^\n]", " ", m.group(0)), texts[path],
                                 flags=re.S if pattern[0] in "`<" else 0)
    record = content.get("record")
    rows = check_records(items, record, probes)
    if strays:
        rows[0] = ("fields", "fail", strays + list(rows[0][2]), rows[0][3])
    paths = list(args.lint) + ([args.script] if args.script else [])
    leads, unread = lint(paths, any(((p.get("checks") or {}).get("repeated_ids") or {}).get("status") == "problem"
                                    for p in probes.values()))
    rows += check_text(items, texts, probes) + [check_script(args.script, record), (
        "lint", "lead" if leads else "not_checked" if len(unread) == len(paths) else "ok", leads,
        "; ".join(unread) or (f"no lead in {', '.join(map(str, paths))}" if paths else "no --lint or --script given"))]
    return {"title": "Diagnostic accuracy check", "checks": rows, "numbers": numbers(items, probes), "labels": LABELS}


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "-h" in argv or "--help" in argv:
        print(__doc__)
        return 0
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--dir", default="diagnostic-accuracy")
    parser.add_argument("--probe", type=Path, action="append", default=[])
    parser.add_argument("--script", type=Path)
    parser.add_argument("--lint", type=Path, nargs="+", default=[])
    args, rest = parser.parse_known_args(argv)
    try:
        probes = {str(path): json.loads(path.read_text(encoding="utf-8")) for path in args.probe}
        _ = [probe["file"]["sha256"] for probe in probes.values()]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"check_accuracy: could not read a probe: {exc}", file=sys.stderr)
        return 2
    return cr.main(["--dir", args.dir, *rest], extend=lambda content, cargs: extend(content, cargs, args, probes))


if __name__ == "__main__":
    sys.exit(main())
