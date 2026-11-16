#!/usr/bin/env python3
"""Check meta-analysis/results.json and the text written from it.

  check_meta.py                                                 results.json and ledger.jsonl
  check_meta.py --text meta-analysis/results.md meta-analysis/methods.md
  check_meta.py --dir other-folder --strict

Runs every check of check_results.py (the copy next to this file), with --dir defaulting to
meta-analysis, and adds:

  meta          every result carries extra["meta"] from meta_pool.py with k, Q and its df, I^2, the
                model and the interval method; random effects also tau^2 and its estimator; a main
                pool also a prediction interval or the reason for none, a small-study test only at
                k >= 10 and a test between subgroups only when every group has 4 or more studies;
                no negative I^2 or tau^2
  paragraphs    (--text) a paragraph that prints a pooled estimate (its value with decimals, beside a
                bound of its interval or a word such as "pooled") also prints both bounds of its
                interval, both bounds of its prediction interval (or the words "prediction interval"
                with the reason there is none) and a labelled tau^2, tau or I^2. Table rows are not
                paragraphs
  small-study   (--text) a sentence that cites a small-study test (Egger, Peters, an asymmetry test)
                without saying it was not run fails when no pool ran one
  methods       (--text) the texts name each pool's tau^2 estimator and interval method, or its
                inverse-variance, Mantel-Haenszel or Peto fixed-effect method
  wording       (--text) no sentence chooses the model because of I^2, Q or a heterogeneity test; no
                negative I^2 or tau^2

Labels added to the number check: k, I^2 (per cent), tau^2 and tau (also written I², τ², τ). Q with its
df and p, the small-study test and the test between subgroups use the built-in statistic, df and p
labels; their values come from extra["meta"].

Writes check.md and prints a JSON summary. Exit code 1 on a mismatch or a failed check (with --strict
also on a number not found); 2 when results.json cannot be read. Standard library only.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_results as cr  # noqa: E402

SMALL_K, SUBGROUP_K = 10, 4          # the conventions meta_pool.py applies
LABELS = (("k", re.compile(r"\bk\s*=\s*$")),
          ("i2", re.compile(r"(?:\bI\^?2|\bI-squared)\s*=\s*$")),
          ("tau2", re.compile(r"(?:τ\^?2|\btau\^?2|\btau-squared)\s*=\s*$", re.I)),
          ("tau", re.compile(r"(?:τ|\btau)\s*=\s*$", re.I)))
HETEROGENEITY = re.compile(r"(?:\bI\^?2|\bI-squared|τ\^?2|\btau\^?2|τ|\btau)\s*[=<>≤≥]", re.I)
NEGATIVE = re.compile(r"(?:\bI\^?2|\bI-squared|τ\^?2|\btau\^?2)\s*=\s*-\s*\d", re.I)
POOLED = re.compile(r"\b(?:pooled|overall|summary|combined|random[- ]effects?|fixed[- ]effects?|common[- ]effects?)\b", re.I)
TESTS = re.compile(r"\b(?:Egger|Peters|Begg|Harbord|small[- ]study(?:[- ]effects?)? tests?|(?:tests?|regression) (?:for|of) "
                   r"(?:funnel[- ]plot )?asymmetry|(?:funnel[- ]plot )?asymmetry tests?)", re.I)
NOT_RUN = re.compile(r"\b(?:not|never)\s+(?:be\s+|been\s+)?(?:run|performed|done|conducted|assessed|carried out|possible|"
                     r"feasible|applied|used|tested|undertaken|computed)\b|\bno (?:formal )?(?:\w+[- ])?(?:tests?|testing)\b|"
                     r"\bwithout (?:a |any )?(?:formal )?test|\b(?:fewer|too few|insufficient|only (?:if|when|with|for))\b|"
                     r"\bat least (?:10|ten)\b|\bk\s*<\s*10|(?:≥|>=)\s*10|\b(?:10|ten) or more", re.I)
STAT_HET = (r"(?:I\^?2|I-squared|Cochran'?s Q|\bQ\b|chi-?squared? test|statistical heterogeneity|heterogeneity tests?|tests? "
            r"(?:for|of) heterogeneity|(?:significant|substantial|considerable|high|low|moderate|little|no) heterogeneity|"
            r"heterogeneity was (?:high|low|substantial|significant|considerable|moderate|absent|not significant|negligible))")
CHOICE = re.compile(r"\b(?:because|since|given|due to|owing to|based on|according to|depending on|if|when|whenever)\b"
                    r"\W+(?:[\w^'-]+\W+){0,6}?" + STAT_HET, re.I)
MODEL = re.compile(r"\b(?:random|fixed|common)[- ]effects?\b", re.I)
NAMES = {"REML": r"\bREML\b|restricted maximum[- ]likelihood", "PM": r"Paule[- –](?:and |& ?)?Mandel",
         "DL": r"DerSimonian[- –](?:and |& ?)?Laird", "Hartung-Knapp": r"Hartung[- –](?:and |& ?)?Knapp|Knapp[- –]"
         r"(?:and |& ?)?Hartung|\bHKSJ\b", "Wald": r"\bWald\b|normal approximation|\bz[- ]distribution|standard normal",
         "inverse variance": r"inverse[- ]variance", "Mantel-Haenszel": r"Mantel[- –](?:and |& ?)?Haenszel", "Peto": r"\bPeto\b"}
SUPERSCRIPT = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹⁻", "0123456789-")


def clean(path: Path) -> str:
    """The text as check_results.py reads it: minus signs, superscripts, code, links and citations blanked."""
    text = path.read_text(encoding="utf-8").replace("−", "-")
    text = re.sub(r"[⁰¹²³⁴⁵⁶⁷⁸⁹⁻]+", lambda m: "^" + m.group(0).translate(SUPERSCRIPT), text)
    for pattern in cr.BLANKED:
        text = re.sub(pattern, lambda m: re.sub(r"[^\n]", " ", m.group(0)), text, flags=re.S if pattern[0] in "`<" else 0)
    return text


def tokens(text: str) -> list:
    """(value, tolerance, signed, percent, has decimals) for each number, skipping years, names and references."""
    out = []
    for m in cr.NUMBER.finditer(text):
        before, after = text[text.rfind("\n", 0, m.start()) + 1:m.start()], text[m.end():m.end() + 2]
        digits, exponent = m.group(2).replace(",", ""), int(m.group(4) or m.group(5) or 0)
        whole = m.group(3) is None
        if after[:1].isalpha() or cr.REFERENCE.search(before) or (whole and len(digits) == 4 and 1900 <= int(digits) <= 2100):
            continue
        value = float(digits) * 10 ** exponent
        out.append((-value if m.group(1) else value, 0.5 * 10 ** (exponent - len(m.group(3) or "")) * (1 + 1e-9),
                    bool(m.group(1)), bool(m.group(6)), not whole))
    return out


def shows(value, found: list, decimals_only: bool = False) -> bool:
    if not cr.is_number(value):
        return False
    return any(abs((value if signed else abs(value)) * f - v) <= tol for v, tol, signed, pct, dec in found
               for f in ((1, 100) if pct else (1,)) if dec or not decimals_only)


def blocks(text: str, pattern: str) -> list:
    """(line, block) for each paragraph (pattern blank lines) or sentence (cr.SENTENCE_END) of a text."""
    out, start = [], 0
    for end in [m.start() for m in re.finditer(pattern, text)] + [len(text)]:
        block = text[start:end]
        if block.strip():
            out.append((text.count("\n", 0, start + len(block) - len(block.lstrip())) + 1, block))
        start = end
    return out


def meta_of(result: dict):
    meta = (result.get("extra") or {}).get("meta")
    return meta if isinstance(meta, dict) else None


def check_fields(results: list) -> list:
    problems = []
    for r in results:
        meta, name = meta_of(r), r.get("id")
        if meta is None:
            problems.append(f"{name}: no extra['meta']: not a result of meta_pool.py")
            continue
        need = ["k", "Q", "Q_df", "I2", "model", "ci_method"] + (["tau2", "tau2_method"] if meta.get("model") == "random" else [])
        missing = [key for key in need if meta.get(key) is None]
        if missing:
            problems.append(f"{name}: extra['meta'] lacks {', '.join(missing)}")
        problems += [f"{name}: {key} is negative" for key in ("I2", "tau2") if cr.is_number(meta.get(key)) and meta[key] < 0]
        if meta.get("analysis") != "main":
            continue
        if not meta.get("pi") and not meta.get("pi_reason"):
            problems.append(f"{name}: no prediction interval and no reason for none")
        small = meta.get("small_study") or {}
        if small.get("status") == "run" and (meta.get("k") or 0) < SMALL_K:
            problems.append(f"{name}: a small-study test was run with k = {meta.get('k')}, fewer than {SMALL_K}")
        elif small.get("status") not in ("run", "not run"):
            problems.append(f"{name}: the small-study test is neither run nor marked not run with its reason")
        for group in meta.get("subgroups") or []:
            if (group.get("test") or {}).get("status") == "run" and \
                    any((g.get("k") or 0) < SUBGROUP_K for g in group.get("groups") or []):
                problems.append(f"{name}: subgroups by {group.get('column')} were tested with a group under {SUBGROUP_K} studies")
    return problems


def numbers(results: list) -> list:
    """The meta-analysis values the text may print with a label: (value, kind, owner, path)."""
    out = []
    for r in results:
        meta = meta_of(r) or {}
        def add(value, kind, path):
            if cr.is_number(value):
                out.append((float(value), kind, r.get("id"), f"extra.meta.{path}"))
        for key, kind in (("k", "k"), ("I2", "i2"), ("tau2", "tau2"), ("tau", "tau"), ("Q", "statistic"), ("Q_df", "df"),
                          ("Q_p", "p")):
            add(meta.get(key), kind, key)
        small = meta.get("small_study") or {}
        for key, kind in (("t", "statistic"), ("df", "df"), ("p", "p")):
            add(small.get(key), kind, f"small_study.{key}")
        for group in meta.get("subgroups") or []:
            test = group.get("test") or {}
            for key, kind in (("Q_between", "statistic"), ("df", "df"), ("p", "p")):
                add(test.get(key), kind, f"subgroups.{group.get('column')}.{key}")
    return out


def text_checks(results: list, paths: list) -> list:
    mains = [r for r in results if (meta_of(r) or {}).get("analysis") == "main"]
    texts = [(p, clean(p)) for p in paths if p.is_file()]
    if not texts:
        return [(name, "not_checked", [], "no --text given") for name in ("paragraphs", "small-study", "methods", "wording")]
    para, small, methods, wording, seen = [], [], [], [], 0
    ran = any((meta_of(r).get("small_study") or {}).get("status") == "run" for r in mains)
    for path, text in texts:
        for line, block in blocks(re.sub(r"(?m)^[ \t]*\|.*$", "", text), r"\n\s*\n"):
            found = tokens(block)
            for r in mains:
                meta, estimate, interval = meta_of(r), (r.get("estimate") or {}).get("value"), r.get("interval") or {}
                bounds = [shows(interval.get(k), found) for k in ("low", "high")]
                if not shows(estimate, found, decimals_only=True) or not (any(bounds) or POOLED.search(block)):
                    continue
                seen += 1
                missing = [] if all(bounds) else ["both bounds of its interval"]
                pi = meta.get("pi")
                if pi and not (shows(pi.get("low"), found) and shows(pi.get("high"), found)):
                    missing.append("both bounds of its prediction interval")
                elif not pi and not re.search(r"prediction interval", block, re.I):
                    missing.append('"prediction interval" with the reason there is none')
                if not HETEROGENEITY.search(block):
                    missing.append("a labelled τ², τ or I²")
                if missing:
                    para.append(f"{path.name}:{line}: {r['id']} is printed without {', '.join(missing)}")
        for line, sentence in blocks(text, cr.SENTENCE_END.pattern):
            if TESTS.search(sentence) and not NOT_RUN.search(sentence) and not ran:
                small.append(f"{path.name}:{line}: cites a small-study test, but no pool ran one (each has k < {SMALL_K} "
                             "or no matched test)")
            if MODEL.search(sentence) and CHOICE.search(sentence):
                wording.append(f"{path.name}:{line}: the model is chosen from a heterogeneity statistic: give the reason "
                               "from how the studies differ")
            if NEGATIVE.search(sentence):
                wording.append(f"{path.name}:{line}: a negative I² or τ²: print the truncated value, 0")
    allowed = "\n".join(p.read_text(encoding="utf-8") for p, _ in texts)
    for r in mains:
        meta = meta_of(r)
        wanted = [meta.get("tau2_method"), meta.get("ci_method")] if meta.get("model") == "random" else [meta.get("method")]
        for name in wanted:
            if name in NAMES and not re.search(NAMES[name], allowed, re.I):
                methods.append(f"{r['id']}: no text names its {'τ² estimator' if name in ('REML', 'PM', 'DL') else 'method'} "
                               f"{name}")
    rows = [("paragraphs", para, f"{seen} paragraph(s) with a pooled estimate carry its interval, prediction interval and "
             "heterogeneity"), ("small-study", small, "no small-study test cited without one being run"),
            ("methods", methods, f"the methods of {len(mains)} pool(s) are named"),
            ("wording", wording, "no model chosen from I² or a heterogeneity test; no negative I² or τ²")]
    return [(name, "fail" if found else "ok", found, detail) for name, found, detail in rows]


def extend(content: dict, args) -> dict:
    results = content["results"]
    fields = check_fields(results)
    pooled = sum(1 for r in results if (meta_of(r) or {}).get("analysis") == "main")
    checks = [("meta", "fail" if fields else "ok", fields, f"{len(results)} result(s), {pooled} main pool(s), with their "
               "meta-analysis fields")]
    return {"title": "Meta-analysis check", "checks": checks + text_checks(results, list(args.text)),
            "numbers": numbers(results), "labels": LABELS}


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "-h" in argv or "--help" in argv:
        print(__doc__)
        return 0
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--dir", default="meta-analysis")
    own, rest = parser.parse_known_args(argv)
    return cr.main(["--dir", own.dir, *rest], extend=extend)


if __name__ == "__main__":
    sys.exit(main())
