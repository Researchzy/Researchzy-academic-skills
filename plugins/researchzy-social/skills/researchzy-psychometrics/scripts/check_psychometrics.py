#!/usr/bin/env python3
"""Check psychometrics/results.json and the text written from it.

  check_psychometrics.py --script psychometrics/analysis.py
  check_psychometrics.py --text psychometrics/results.md psychometrics/methods.md --strict

Runs the checks of check_results.py (the copy next to this file; --dir defaults to psychometrics) on
results recorded with rz_results.record(..., extra={"psy": {"kind": ...}}) and adds, per kind:

  reliability  alpha names its interval method; a bootstrap has its seed and resamples
  factors      EFA settings and parallel-analysis settings recorded; the counts of parallel analysis and
               Kaiser's rule recomputed; the factors retained equal parallel analysis or carry a reason
  cfa          converged: true, df > 0, identification, estimator, ordinal decision; three indicators
               per factor or a constraint; no |loading| >= 1, negative variance or |r| >= 1 between
               factors; SRMR with its formula (recomputed from the saved matrices) or a reason for none
  validity     omega, CR, AVE recomputed from the loadings; HTMT from its saved correlations; AVEs below
               a squared factor correlation listed
  invariance   configural, metric, scalar, strict in order, a failed level followed only by its partial
               version; delta CFI and RMSEA recomputed against the last level that held; decisions follow
               the rule, which has a name, source and date; metric and above only from lavaan
  cmv          each test is harman, marker or method_factor; the limits are stated
  conventions  each recorded cut-off has its name, rule, source and date
  (--text)     wording: a judgement against a cut-off ("good fit", 拟合良好, 超过阈值) names a recorded
               convention; group_means: only under scalar invariance in lavaan, freed parameters named;
               cmv_claims: no absence of common-method bias on Harman's test alone, never as a fact;
               invariance_claims: only levels whose lavaan model held; loadings_claims: "all loadings > .70"

Labels added to the number check, also in Chinese typography: α, ω, CR, AVE, HTMT, CFI, TLI, RMSEA,
SRMR, λ and loadings (载荷); χ² and its df use the built-in labels. Writes check.md, prints a JSON
summary. Exit code 1 on a mismatch or a failed check (with --strict also on a number not found); 2
when results.json cannot be read. Standard library only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from itertools import combinations
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_results as cr  # noqa: E402

LEVELS = ("configural", "metric", "scalar", "strict")
KINDS = {"alpha": "alpha", "omega": "omega", "cr": "cr", "ave": "ave", "htmt": "htmt", "loadings": "loading", "cfi": "cfi",
         "tli": "tli", "rmsea": "rmsea", "srmr": "srmr", "chi2": "statistic", "df": "df"}
SKIP = {"item_stats", "parallel", "kaiser", "errors", "factor_corr", "matrices", "tests", "rule"}
CMV_TESTS = ("harman", "marker", "method_factor")
TEXT_ROWS = ("wording", "group_means", "cmv_claims", "invariance_claims", "loadings_claims")
TOL = 5e-4                    # a recorded value may be rounded to three decimals
S = cr.START


LABELS = tuple((kind, re.compile(rf"(?:{names})(?:\s*系数|\s*值)?\s*(?:\([^()]*\))?\s*{cr.EQUALS}\s*$")) for kind, names in (
    ("alpha", rf"α|{S}alpha"), ("omega", rf"ω|{S}omega"), ("cr", rf"{S}CR|组合信度"), ("ave", rf"{S}AVE"), ("htmt", rf"{S}HTMT"),
    ("cfi", rf"{S}CFI"), ("tli", rf"{S}TLI"), ("rmsea", rf"{S}RMSEA"), ("srmr", rf"{S}SRMR"), ("loading", rf"λ|{S}loadings?|载荷")))
JUDGE = re.compile(
    r"\b(?:(?:good|acceptable|adequate|excellent|satisfactory|reasonable|poor|unacceptable|inadequate)\s+(?:model\s+)?fit"
    r"|fit(?:ted)?\s+(?:the\s+data\s+)?(?:well|poorly|acceptably|adequately)\b|fit\s+(?:was|is|were)\s+(?:\w+\s+)?"
    r"(?:good|acceptable|adequate|excellent|satisfactory|poor)|(?:good|acceptable|adequate|excellent|satisfactory|poor|"
    r"questionable)\s+(?:reliability|internal\s+consistency|(?:convergent\s+|discriminant\s+)?validity)|(?:reliability|"
    r"consistency|validity)\s+(?:was|is|were)\s+(?:\w+\s+)?(?:good|acceptable|adequate|excellent|satisfactory|poor)|"
    r"(?:exceed\w*|above|below|surpass\w*|met|meets?|satisf(?:y|ies|ied)|within)\s+(?:the\s+)?(?:recommended\s+|"
    r"conventional\s+|accepted\s+|suggested\s+)?(?:threshold|cut-?off|criteri(?:on|a)|benchmark|standard|guideline)s?|"
    r"which\s+(?:is|was)\s+(?:considered\s+)?(?:good|acceptable|adequate|excellent|satisfactory|poor))"
    r"|拟合(?:良好|较好|很好|理想|可以接受|可接受|尚可|不佳|较差|欠佳)|(?:良好|可以接受|可接受|理想)的拟合|可以接受|可接受"
    r"|(?:超过|高于|低于|达到|满足|符合)了?(?:推荐|建议|公认|常用|一般)?的?(?:阈值|临界值|标准|要求)"
    r"|(?:信度|效度|一致性)(?:良好|较好|很好|理想|较差)", re.I)
COMPARE = re.compile(r"\b(?:higher|lower|greater|smaller|differ\w*|compar\w*|than|versus|vs\.?)\b|高于|低于|差异|不同|比较|相比",
                     re.I)
MEANS = re.compile(r"\b(?:means?|averages?|scor\w*|levels?)\b|均值|平均|得分|分数|水平", re.I)
REFUSED = re.compile(r"\b(?:not|never|cannot|no)\s+(?:be\s+|been\s+)?compar\w*|\bno\s+comparison|(?:未|没有|不能|无法|不宜|拒绝)"
                     r"(?:进行)?(?:比较|对比)", re.I)
CMV = re.compile(r"common[- ]method\s+(?:bias|variance)|\bCM[VB]\b|共同方法(?:偏差|变异)|同源(?:偏差|方差)", re.I)
ABSENT = re.compile(r"\bnot\s+(?:an?\s+)?(?:concern|problem|issue|threat|serious|substantial|present|likely|significant)|"
                    r"\bno\s+(?:serious\s+|substantial\s+|evidence\s+of\s+)?(?:concern|problem|issue|threat|bias)|\bunlikely\b|"
                    r"\bruled\s+out|\bnegligible|\babsent\b|\bminimal\b|不(?:是|构成|存在|严重|明显)|没有|并不|无明显|可以忽略|排除", re.I)
CAVEAT = re.compile(r"\b(?:cannot|can\s*not|does\s+not|do\s+not)\s+(?:show|rule\s+out|establish|prove|exclude)|"
                    r"(?:不能|无法|并不能|不足以)(?:说明|排除|证明|表明)", re.I)
HARMAN = re.compile(r"Harman|single[- ]factor|单因[子素]", re.I)
OTHER_TEST = re.compile(r"marker|method\s+factor|标记变量|方法因子", re.I)
FACT = re.compile(r"\bno\s+common[- ]method\s+(?:bias|variance)|\bruled\s+out|\b(?:was|is)\s+absent|\bdoes\s+not\s+exist|"
                  r"不存在(?:明显的?|严重的?)?共同方法|共同方法(?:偏差|变异)不存在|排除了?共同方法", re.I)
INVARIANCE = re.compile(r"\b(metric|scalar|strict|weak|strong)\s+(?:measurement\s+)?invarian(?:ce|t)\b|"
                        r"(度量|标量|尺度|严格|弱|强)(?:测量)?(?:等值|不变)性?", re.I)
HOLDS = re.compile(r"\b(?:held|holds?|supported|established|achieved|confirmed|demonstrated|met|found)\b|成立|得到了?(?:支持|验证)"
                   r"|满足|具有|具备|达到", re.I)
NEGATED = re.compile(r"\bnot\b|n't\b|\bfail\w*|\bno\b|\brejected|\black\w*|不(?![同断仅少过论管良适久])|未|没有|无法|拒绝", re.I)
LEVEL_WORDS = {"weak": "metric", "strong": "scalar", "度量": "metric", "弱": "metric", "标量": "scalar", "尺度": "scalar",
               "强": "scalar", "严格": "strict"}
ALL_LOADINGS = re.compile(r"\b(?:all|every|each)\b[^.;。；]{0,40}?\bloadings?\b[^.;。；]{0,30}?(>=|≥|>|at\s+least|above|exceed\w*|"
                          r"greater\s+than|over)\s*(\d*\.\d+|\d+)|(?:所有|全部|各|每个)[^。；]{0,20}?载荷[^。；]{0,15}?"
                          r"(≥|>=|>|不低于|大于|高于|超过|在)\s*(\d*\.\d+|\d+)", re.I)


def num(value) -> bool:
    return cr.is_number(value) and math.isfinite(value)


def psy(result: dict):
    p = (result.get("extra") or {}).get("psy")
    return p if isinstance(p, dict) else None


def of_kind(results: list, kind: str) -> list:
    return [(r.get("id"), p) for r in results for p in [psy(r)] if p and p.get("kind") == kind]


def row(name, problems, detail, unchecked=None):
    return name, "fail" if problems else "not_checked" if unchecked else "ok", problems, unchecked or detail


def matrices(ref, keys):
    """(the saved matrices, "") or (None, why not); ("drift", why) when the file changed after the run."""
    path = Path(str((ref or {}).get("path") or ""))
    if not (ref or {}).get("path") or not path.is_file():
        return None, f"{path} is not there" if (ref or {}).get("path") else "no matrices file recorded"
    if hashlib.sha256(path.read_bytes()).hexdigest() != ref.get("sha256"):
        return "drift", f"{path} changed after the run: run the analysis again"
    saved = json.loads(path.read_text(encoding="utf-8"))
    return (saved, "") if all(saved.get(k) for k in keys) else (None, f"{path} lacks {' or '.join(keys)}")


def srmr(s, sig) -> float:
    k = len(s)
    return math.sqrt(sum(((s[i][j] - sig[i][j]) / math.sqrt(s[i][i] * s[j][j])) ** 2 for i in range(k)
                         for j in range(i + 1)) / (k * (k + 1) / 2))


def check_reliability(results):
    found, problems = of_kind(results, "reliability"), []
    for rid, p in found:
        problems += [] if cr.has_text(p.get("construct")) and len(p.get("items") or []) > 1 else \
            [f"{rid}: name the construct and its items (two or more)"]
        if p.get("ci") not in ("feldt", "bootstrap"):
            problems.append(f"{rid}: the interval method of alpha (ci) is not feldt or bootstrap")
        elif p["ci"] == "bootstrap" and not all(isinstance(p.get(k), int) for k in ("seed", "n_boot")):
            problems.append(f"{rid}: a bootstrap interval needs its seed and number of resamples (seed, n_boot)")
    return row("reliability", problems, f"{len(found)} alpha(s) with their interval method",
               None if found else "no reliability result recorded")


def check_factors(results):
    found, problems, details = of_kind(results, "efa"), [], []
    for rid, p in found:
        pa, kaiser = p.get("parallel") or {}, p.get("kaiser") or {}
        missing = [k for k in ("correlation", "method", "rotation") if not cr.has_text(p.get(k))] + \
            [f"parallel.{k}" for k in ("eigen", "criterion", "n_sets", "seed", "observed", "suggested") if pa.get(k) is None]
        if missing:
            problems.append(f"{rid}: not recorded: {', '.join(missing)}")
            continue
        reference = pa.get("random_percentile" if pa["criterion"] == "percentile" else "random_mean") or []
        count = next((i for i, (o, r) in enumerate(zip(pa["observed"], reference)) if o <= r), len(reference))
        if not reference or count != pa["suggested"]:
            problems.append(f"{rid}: parallel analysis suggests {pa['suggested']}, its eigenvalues give {count}")
        k = sum(1 for v in kaiser.get("eigenvalues") or [] if v > 1)
        if kaiser.get("count") != k or not kaiser.get("eigenvalues"):
            problems.append(f"{rid}: Kaiser's rule gives {k} from the recorded eigenvalues, recorded {kaiser.get('count')}")
        if p.get("n_factors") != pa["suggested"] and not cr.has_text(p.get("reason")):
            problems.append(f"{rid}: {p.get('n_factors')} factors retained, parallel analysis suggests {pa['suggested']}: "
                            "record the reason, or retain that number")
        details.append(f"{rid}: parallel analysis {pa['suggested']}, Kaiser {kaiser.get('count')}, retained "
                       f"{p.get('n_factors')}" + (" (reason recorded)" if cr.has_text(p.get("reason")) else ""))
    return row("factors", problems, "; ".join(details), None if found else "no EFA recorded")


def check_cfa(results):
    found, problems, details = of_kind(results, "cfa"), [], []
    for rid, p in found:
        fit, own = p.get("fit") or {}, []
        own += [] if p.get("converged") is True else ["no record that the model converged (converged: true): report no fit index"]
        own += [] if isinstance(p.get("df"), int) and p["df"] > 0 else [f"df must be a whole number above 0, not {p.get('df')}"]
        own += [f"{k} is not recorded" for k in ("identification", "estimator", "ordinal") if not cr.has_text(p.get(k))]
        own += [] if p.get("loadings") else ["no standardized loadings recorded"]
        for factor, items in (p.get("loadings") or {}).items():
            own += [f"{factor} has {len(items)} indicator(s): use three or more, or record the constraint that identifies "
                    "it (constraints)"] if len(items) < 3 and not cr.has_text(p.get("constraints")) else []
            own += [f"Heywood case: the standardized loading of {i} on {factor} is {v:.3f}" for i, v in items.items()
                    if num(v) and abs(v) >= 1]
        own += [f"Heywood case: negative error variance of {i} ({v:.3f})" for i, v in (p.get("errors") or {}).items()
                if num(v) and v < 0] + list(p.get("heywood") or [])
        own += [f"factor correlation {a}-{b} is {v:.3f}" for a, rw in (p.get("factor_corr") or {}).items()
                for b, v in rw.items() if a != b and num(v) and abs(v) >= 1]
        own += [f"fit lacks {k}" for k in ("chi2", "cfi", "tli", "rmsea") if not num(fit.get(k))]
        if not num(fit.get("srmr")):
            own += [] if cr.has_text(fit.get("srmr_reason")) else ["no SRMR and no reason for none (fit.srmr_reason)"]
        else:
            own += [] if cr.has_text(fit.get("srmr_formula")) else ["SRMR without its formula (fit.srmr_formula)"]
            saved, why = matrices(p.get("matrices"), ("sample_cov", "implied_cov"))
            value = srmr(saved["sample_cov"], saved["implied_cov"]) if isinstance(saved, dict) else None
            own += [why] if saved == "drift" else [] if value is None or abs(value - fit["srmr"]) <= TOL else \
                [f"SRMR is {fit['srmr']:.4f}, the saved matrices give {value:.4f}"]
            details.append(f"{rid}: SRMR {'recomputed' if value is not None else f'not recomputed ({why})'}")
        problems += [f"{rid}: {m}" for m in own]
    return row("cfa", problems, "; ".join(details) or f"{len(found)} CFA(s) recorded", None if found else "no CFA recorded")


def check_validity(results):
    found, problems, notes = [(rid, p) for rid, p in of_kind(results, "cfa") if p.get("validity")], [], []
    for rid, p in found:
        v, errors = p["validity"], p.get("errors") or {}
        for factor, items in (p.get("loadings") or {}).items():
            lam, theta = list(items.values()), [errors.get(i) for i in items]
            if not all(num(x) for x in lam + theta) or not all(0 <= x < 1 for x in lam):
                continue                     # check_cfa reports what leaves these values undefined
            s = sum(lam)
            for key, value in (("omega", s * s / (s * s + sum(theta))), ("cr", s * s / (s * s + sum(1 - x * x for x in lam))),
                               ("ave", sum(x * x for x in lam) / len(lam))):
                got = (v.get(key) or {}).get(factor)
                if num(got) and abs(got - value) > TOL:
                    problems.append(f"{rid}: {key} of {factor} is {got:.4f}, its loadings give {value:.4f}")
        ave = v.get("ave") or {}
        notes += [f"AVE of {f} ({ave[f]:.2f}) is below the squared {a}-{b} correlation ({r * r:.2f})"
                  for a, rw in (p.get("factor_corr") or {}).items() for b, r in rw.items() for f in (a, b)
                  if a != b and num(r) and num(ave.get(f)) and ave[f] < r * r]
        h = v.get("htmt") or {}
        saved, why = matrices(h.get("matrices"), ("items", "corr")) if h else (None, "")
        problems += [f"{rid}: {why}"] if saved == "drift" else []
        if isinstance(saved, dict):
            at, corr = {name: k for k, name in enumerate(saved["items"])}, saved["corr"]

            def mean(pairs):
                return sum(corr[at[x]][at[y]] for x, y in pairs) / len(pairs)
            for a, rw in (h.get("matrix") or {}).items():
                for b, got in rw.items():
                    ia, ib = ((h.get("items") or {}).get(c) or [] for c in (a, b))
                    if len(ia) > 1 and len(ib) > 1 and set(ia + ib) <= set(at) and num(got):
                        value = mean([(x, y) for x in ia for y in ib]) / math.sqrt(mean(list(combinations(ia, 2))) *
                                                                                   mean(list(combinations(ib, 2))))
                        if abs(got - value) > TOL:
                            problems.append(f"{rid}: HTMT {a}-{b} is {got:.4f}, the saved correlations give {value:.4f}")
            notes.append("HTMT recomputed")
    detail = "; ".join(dict.fromkeys(notes)) or "omega, CR and AVE agree with the loadings"
    return row("validity", problems, detail, None if found else "no CFA with a validity record")


def check_invariance(results):
    found, problems, details = of_kind(results, "invariance"), [], []
    for rid, p in found:
        rule, held, last, steps = p.get("rule") or {}, None, None, []
        if not all(cr.has_text(rule.get(k)) for k in ("name", "source", "date")):
            problems.append(f"{rid}: the invariance rule needs its name, source and date")
        for lv in p.get("levels") or []:
            name, decision = lv.get("level"), lv.get("decision")
            if name not in LEVELS or decision not in ("holds", "fails", "not_checked"):
                problems.append(f"{rid}: each level is one of {', '.join(LEVELS)}, decided holds, fails or not_checked")
                continue
            steps.append(f"{name}{' (partial)' if lv.get('freed') else ''} {decision}")
            if decision == "not_checked":
                problems += [] if cr.has_text(lv.get("reason")) else [f"{rid}: {name} is not_checked without its reason"]
                continue
            if name != "configural" and (lv.get("engine") or p.get("engine")) != "lavaan":
                problems.append(f"{rid}: {name} invariance needs lavaan's constrained model; semopy fits each group on its "
                                "own: record the level as not_checked with that reason")
            if last and (LEVELS.index(name) < LEVELS.index(last["level"]) or (name == last["level"] and not lv.get("freed"))):
                problems.append(f"{rid}: {name} comes after {last['level']}: test the levels in order")
            elif last and last["decision"] == "fails" and name != last["level"]:
                problems.append(f"{rid}: {name} was tested after {last['level']} failed: stop there, or free parameters of "
                                "the failed level (partial invariance)")
            if name != "configural" and held:
                delta = {k: lv[k] - held[k] for k in ("cfi", "rmsea") if num(lv.get(k)) and num(held.get(k))}
                problems += [f"{rid}: {name}: delta_{k} is {lv.get(f'delta_{k}')}, against {held['level']} it is "
                             + (f"{delta[k]:+.4f}" if k in delta else "not computable") for k in ("cfi", "rmsea")
                             if k not in delta or not num(lv.get(f"delta_{k}")) or abs(lv[f"delta_{k}"] - delta[k]) > TOL]
                drop, rise = rule.get("max_cfi_drop"), rule.get("max_rmsea_rise")
                ok = len(delta) == 2 and (not num(drop) or -delta["cfi"] <= drop + 1e-9) and \
                    (not num(rise) or delta["rmsea"] <= rise + 1e-9)
                if len(delta) == 2 and (num(drop) or num(rise)) and decision != ("holds" if ok else "fails"):
                    problems.append(f"{rid}: {name} is recorded as {decision}; the rule {rule.get('name')} gives "
                                    f"{'holds' if ok else 'fails'}")
            held, last = (lv if decision == "holds" else held), lv
        details.append(f"{rid}: " + ", ".join(steps))
    return row("invariance", problems, "; ".join(details), None if found else "no invariance result recorded")


def check_cmv(results):
    found, problems = of_kind(results, "cmv"), []
    for rid, p in found:
        problems += [f"{rid}: a test must be one of {', '.join(CMV_TESTS)}, and Harman's share lie between 0 and 1"
                     for t in p.get("tests") or [{}] if t.get("test") not in CMV_TESTS or
                     (t["test"] == "harman" and not (num(t.get("share")) and 0 <= t["share"] <= 1))]
        problems += [] if cr.has_text(p.get("limits")) else [f"{rid}: say what the tests cannot show (limits)"]
    detail = "; ".join(f"{rid}: " + ", ".join(str(t.get("test")) for t in p.get("tests") or []) for rid, p in found)
    return row("cmv", problems, detail, None if found else "no common-method test recorded")


def conventions(results):
    found = [(r.get("id"), c) for r in results for c in ((psy(r) or {}).get("conventions") or [])]
    keys = ("name", "rule", "source", "date")
    problems = [f"{rid}: convention {c.get('name')!r} lacks {', '.join(k for k in keys if not c.get(k))}" for rid, c in found
                if not all(c.get(k) for k in keys)]
    names = [n for _, c in found for n in ([c["name"]] if isinstance(c.get("name"), str) else c.get("name") or [])]
    return row("conventions", problems, f"{len(found)} convention(s): " + "; ".join(names) if found else "", None
               if found else "no convention recorded: the text may not judge any value against a cut-off"), names


def fold(text: str) -> str:
    return " ".join(text.translate(cr.FULL_WIDTH).casefold().split())


def sentences(paths):
    """(where, sentence) with code, links, headings and citations blanked as the number check does."""
    for path in paths:
        text = path.read_text(encoding="utf-8").replace("−", "-").translate(cr.FULL_WIDTH)
        for pattern in cr.BLANKED:
            text = re.sub(pattern, lambda m: re.sub(r"[^\n]", " ", m.group(0)), text, flags=re.S if pattern[0] in "`<" else 0)
        start = 0
        for end in [m.start() for m in cr.SENTENCE_END.finditer(text)] + [len(text)]:
            chunk = text[start:end]
            if chunk.strip():
                yield f"{path.name}:{text.count(chr(10), 0, start + len(chunk) - len(chunk.lstrip())) + 1}", chunk
            start = end


def text_checks(results, paths, names):
    paths = [p for p in paths if p.is_file()]
    if not paths:
        return [(n, "not_checked", [], "no --text given") for n in TEXT_ROWS]
    joined, found = fold("\n".join(p.read_text(encoding="utf-8") for p in paths)), {n: [] for n in TEXT_ROWS}
    inv, cmv = of_kind(results, "invariance"), of_kind(results, "cmv")
    held = {lv["level"]: lv for _, p in inv for lv in p.get("levels") or []
            if lv.get("decision") == "holds" and (lv.get("engine") or p.get("engine")) == "lavaan"}
    terms = [fold(t) for _, p in inv for t in [p.get("group"), *(p.get("group_terms") or [])] if t]
    other = any(t.get("test") in ("marker", "method_factor") for _, p in cmv for t in p.get("tests") or [])
    loads = sorted((v, i, f) for _, p in of_kind(results, "cfa") for f, items in (p.get("loadings") or {}).items()
                   for i, v in items.items() if num(v))
    for where, sentence in sentences(paths):
        folded, judge = fold(sentence), JUDGE.search(sentence)
        if judge and not any(fold(n) in folded for n in names):
            found["wording"].append(f"{where}: '{judge.group(0)}' names no recorded convention: name the one the user "
                                    "chose, or give the value without the judgement")
        if any(t in folded for t in terms) and COMPARE.search(sentence) and MEANS.search(sentence) and \
                not REFUSED.search(sentence):
            freed = [str(x) for x in (held.get("scalar") or {}).get("freed") or []]
            found["group_means"] += [f"{where}: compares groups, but scalar invariance did not hold in lavaan: do not "
                                     "compare the means"] if "scalar" not in held else \
                [f"{where}: compares groups under partial scalar invariance: name the freed parameters "
                 f"({', '.join(freed)}) in the text"] if any(fold(x) not in joined for x in freed) else []
        if CMV.search(sentence) and not CAVEAT.search(sentence):
            alone = not other or (HARMAN.search(sentence) and not OTHER_TEST.search(sentence))
            found["cmv_claims"] += [f"{where}: states that there is no common-method bias: say what the tests show and "
                                    "cannot show"] if FACT.search(sentence) else \
                [f"{where}: claims common-method bias is absent on Harman's test alone: it cannot show that"] \
                if ABSENT.search(sentence) and alone else []
        for m in INVARIANCE.finditer(sentence) if HOLDS.search(sentence) and not NEGATED.search(sentence) else ():
            level = LEVEL_WORDS.get((m.group(1) or m.group(2)).lower(), (m.group(1) or m.group(2)).lower())
            found["invariance_claims"] += [f"{where}: claims {level} invariance; no lavaan model of that level held"] \
                if level not in held else [f"{where}: {level} invariance held only partially: say partial"] \
                if held[level].get("freed") and not re.search(r"\bpartial|部分", sentence, re.I) else []
        for m in ALL_LOADINGS.finditer(sentence) if loads else ():
            op, bound, (low, item, factor) = (m.group(1) or m.group(3)).lower(), float(m.group(2) or m.group(4)), loads[0]
            if low < bound or (low == bound and op not in (">=", "≥", "at least", "不低于")):
                found["loadings_claims"].append(f"{where}: '{m.group(0).strip()}', but the loading of {item} on {factor} "
                                                f"is {low:.2f}")
    unchecked = {"group_means": None if terms else "no invariance record names the groups (group, group_terms)",
                 "loadings_claims": None if loads else "no CFA loadings recorded"}
    return [row(n, found[n], "no finding", None if found[n] else unchecked.get(n)) for n in TEXT_ROWS]


def numbers(results, settings):
    """(value, kind, owner, path) for the labels above; the key decides the kind: fit.cfi is a "cfi"."""
    out = [(float(settings["alpha"]), "alpha", "record", "settings.alpha")] if num(settings.get("alpha")) else []

    def walk(node, owner, path, kind):
        if isinstance(node, dict):
            for key, item in node.items():
                walk(item, owner, f"{path}.{key}", KINDS.get(key, kind) if key not in SKIP else None)
        elif isinstance(node, list):
            for item in node:
                walk(item, owner, path, kind)
        elif kind and num(node):
            out.append((float(node), kind, owner, path))
    for r in results:
        walk(psy(r) or {}, r.get("id"), "extra.psy", None)
    return out


def extend(content: dict, args) -> dict:
    results, (named, names) = content["results"], conventions(content["results"])
    rows = [check(results) for check in (check_reliability, check_factors, check_cfa, check_validity, check_invariance,
                                         check_cmv)] + [named]
    return {"title": "Psychometrics check", "checks": rows + text_checks(results, list(args.text), names),
            "numbers": numbers(results, (content.get("record") or {}).get("settings") or {}), "labels": LABELS}


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "-h" in argv or "--help" in argv:
        print(__doc__)
        return 0
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--dir", default="psychometrics")
    own, rest = parser.parse_known_args(argv)
    return cr.main(["--dir", own.dir, *rest], extend=extend)


if __name__ == "__main__":
    sys.exit(main())
