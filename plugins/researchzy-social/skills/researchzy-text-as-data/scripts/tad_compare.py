#!/usr/bin/env python3
"""Interpretable comparisons for a text variable: counts from the user's dictionary, and topic models.

  tad_compare.py dictionary terms.csv [--window 4] [--negators FILE] [--kwic 20] [--seed 1]
  tad_compare.py topics --k 5[,6,...] [--seeds 1,2,3] [--method lda|nmf] [--top 10] [--docs 5]
                        [--stable-min 0.5] [--segmented COLUMN] [--reading-log FILE]

Both read the corpus that protocol.json names (--dir, default text-as-data) and write into <dir>/dictionary/
or <dir>/topics/.

dictionary: terms.csv has the columns category and term, from a source the user names. A term in Latin letters
matches whole words; a term in Chinese, Japanese or Korean script matches anywhere. A hit with a negator among
the --window tokens before it, in the same clause, is counted as negated, not as a hit. Writes scores.csv (hits
and negated hits per unit and category), kwic.csv (per category, a seeded sample of hits in context with an
empty valid column for the user's verdict) and dictionary.md: coverage overall and per group and, for a
category named like a class, how its hits agree with the user's labels in the scored rounds.

topics: LDA on counts or NMF on tf-idf, from scikit-learn, for each K and seed. Runs of Chinese characters
become character bigrams unless --segmented names a column of space-separated words; Latin words are
lower-cased and English stop words dropped. Each seed's topics are matched to the first seed's (scipy's
linear_sum_assignment when installed, else greedily) by the share of top words they have in common; a topic's
stability is its smallest share over the other seeds, and under --stable-min it is unstable. UMass coherence is
the mean over pairs of top words of log((D(wi, wj) + 1) / D(wj)), wj the higher ranked. The name column stays
empty unless --reading-log has a row for that K and topic listing every representative unit as read, with a
reader and a date.

Settings are conventions and are written into every output. Exit codes: 0 done, also when topics cannot run
for want of scikit-learn (status not_run); 2 when an input cannot be read. dictionary needs only the standard
library; topics needs scikit-learn and numpy, and uses scipy when it is installed.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import math
import random
import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tad_ledger as tl  # noqa: E402

NEGATORS = (r"不(?!仅|但|过|管|论|错|久|少|断|同)|没|未(?!来|免)|毫无|并非|绝非|\b(?:not|no|never|none|nothing|neither|nor|"
            r"without|hardly|barely)\b|n't\b")
CLAUSE = re.compile(r"[,.;:!?，。；：！？、\n]")
CJK_RUN = re.compile(f"[{tl.CJK}]+")
WORD = re.compile(rf"[^\W\d_{tl.CJK}][^\W_{tl.CJK}]+")
CONTEXT = 30


def fail(message: str):
    print(f"tad_compare: {message}", file=sys.stderr)
    raise SystemExit(2)


def fold(text: str) -> str:
    return unicodedata.normalize("NFKC", text or "").casefold()


def write_csv(path: Path, header: list, rows: list) -> None:
    with open(path, "w", newline="", encoding="utf-8-sig") as handle:
        out = csv.writer(handle)
        out.writerow(header)
        out.writerows(rows)


def corpus_of(args) -> tuple:
    d = Path(args.dir)
    ctx = tl.load(d)
    return d, ctx, tl.load_corpus(ctx)


def user_labels(d: Path, ctx: dict) -> dict:
    """{unit: the user's label} in the scored rounds."""
    out = {}
    for n in tl.rounds(d):
        f = tl.files(d, n)
        if f["score.json"].is_file():
            out.update(tl.read_round(f["user.csv"], tl.read_json(f["sample.json"]), ctx, "the user's file", tl.USER_HINT)[0])
    return out


# ---------------------------------------------------------------------------------------------
# dictionary


def load_terms(path: Path) -> dict:
    """{category: compiled pattern}, longest terms first; Latin terms whole words, CJK terms anywhere."""
    if not path.is_file():
        fail(f"no such dictionary: {path}")
    terms = {}
    for row in tl.read_table(path, ("category", "term"))[1]:
        if row["category"] and tl.norm(row["term"]):
            terms.setdefault(row["category"], set()).add(tl.norm(row["term"]))
    if not terms:
        fail(f"{path} holds no term: it needs the columns category and term")
    edge = rf"[^\W_{tl.CJK}]"
    return {c: re.compile("|".join(re.escape(t) if CJK_RUN.search(t) else rf"(?<!{edge}){re.escape(t)}(?!{edge})"
                                   for t in sorted(ts, key=len, reverse=True)), re.I) for c, ts in terms.items()}


def negated(text: str, start: int, window: int, negators) -> bool:
    """A negator among the last `window` tokens before the hit, inside its clause."""
    clause = CLAUSE.split(text[:start])[-1]
    toks = list(tl.TOKEN.finditer(clause))[-window:]
    return bool(toks) and bool(negators.search(clause[toks[0].start():]))


def cmd_dictionary(args) -> int:
    d, ctx, corpus = corpus_of(args)
    path, out = Path(args.terms), d / "dictionary"
    patterns = load_terms(path)
    if args.negators:
        words = [tl.norm(w) for w in tl.read_text(Path(args.negators)).splitlines() if w.strip()]
        negators, how = re.compile("|".join(map(re.escape, words)) or r"(?!)", re.I), f"{len(words)} negators from {args.negators}"
    else:
        negators, how = re.compile(NEGATORS, re.I), "the default negators (a convention)"
    hits, counts = {c: [] for c in patterns}, {}
    for u, x in corpus["units"].items():
        text = x["text"]
        for c, pattern in patterns.items():
            found = [(m.start(), m.end(), negated(text, m.start(), args.window, negators)) for m in pattern.finditer(text)]
            hits[c] += [(u, text, *h) for h in found]
            counts[(u, c)] = (sum(not n for *_, n in found), sum(n for *_, n in found))
    out.mkdir(parents=True, exist_ok=True)
    groups = ctx["groups"]
    write_csv(out / "scores.csv", ["unit", *groups, *(f"{c}{tail}" for c in patterns for tail in ("", "_negated"))],
              [[u, *x["groups"].values(), *(n for c in patterns for n in counts[(u, c)])] for u, x in corpus["units"].items()])
    rng, kwic = random.Random(args.seed), []
    for c, found in hits.items():
        for u, text, start, end, neg in sorted(rng.sample(found, min(args.kwic, len(found))), key=lambda h: (h[0], h[2])):
            kwic.append([c, u, text[max(0, start - CONTEXT):start], text[start:end], text[end:end + CONTEXT],
                         "yes" if neg else "", "", ""])
    write_csv(out / "kwic.csv", ["category", "unit", "left", "hit", "right", "negated", "valid", "note"], kwic)
    n = len(corpus["units"])
    covered = {c: {u for u in corpus["units"] if counts[(u, c)][0]} for c in patterns}
    lines = ["# Dictionary comparison", "", f"Dictionary: {path} (SHA-256 {hashlib.sha256(path.read_bytes()).hexdigest()[:12]}), "
             f"{len(patterns)} categories. Negation: {how}, within {args.window} tokens before a hit in its clause "
             f"(a convention). Context sample: up to {args.kwic} hits per category, seed {args.seed}, in kwic.csv.", "",
             "## Coverage", "", "Units with at least one hit that is not negated.", "",
             *tl.table(("Category", "Units", "Share", "Negated hits"), [
                 (c, len(covered[c]), f"{len(covered[c]) / n:.3f}" if n else "", sum(h[-1] for h in hits[c])) for c in patterns]),
             "", f"Any category: {len(set().union(*covered.values()))} of {n} units."]
    for g in groups:
        values = sorted({x["groups"][g] for x in corpus["units"].values()})
        size = {v: sum(x["groups"][g] == v for x in corpus["units"].values()) for v in values}
        share = lambda v, c: sum(corpus["units"][u]["groups"][g] == v for u in covered[c]) / size[v]  # noqa: E731
        lines += ["", *tl.table((g, "Units", *patterns), [(v, size[v], *(f"{share(v, c):.3f}" for c in patterns))
                                                          for v in values])]
    labels, rows = user_labels(d, ctx), []
    for c in patterns:
        cls = ctx["canon"].get(c.casefold())
        if cls and labels:
            has = {u: (cls in v if ctx["multi"] else v == cls) for u, v in labels.items()}
            both = sum(has[u] and u in covered[c] for u in has)
            hit, user = sum(u in covered[c] for u in has), sum(has.values())
            rows.append((c, len(has), f"{both} of {hit}", f"{both} of {user}"))
    head = ("Category = class", "Units labelled by the user", "Hits the user labelled with the class", "User's units with a hit")
    lines += ["", "## Against the user's labels", "", *(tl.table(head, rows) if rows else [
        "Not checked: no category is named like a class, or no round has been scored."]),
              "", "Read kwic.csv with the user and fill valid (yes or no) for each hit: the share of valid hits is the "
              "dictionary's precision in context. Counts are not a measure until that reading is done."]
    (out / "dictionary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    result = {"dictionary": str(path), "categories": list(patterns), "units": n, "window": args.window, "negators": how,
              "coverage": {c: len(covered[c]) for c in patterns}, "kwic": len(kwic), "against_labels": len(rows) > 0,
              "report": str(out / "dictionary.md")}
    tl.write_json(out / "dictionary.json", result)
    tl.show(result)
    return 0


# ---------------------------------------------------------------------------------------------
# topics


def load_sklearn():
    """The scikit-learn pieces, or None when scikit-learn or numpy is missing; scipy's assignment when present."""
    try:
        import numpy as np
        from sklearn.decomposition import NMF, LatentDirichletAllocation
        from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, CountVectorizer, TfidfTransformer
    except ImportError:
        return None
    try:
        from scipy.optimize import linear_sum_assignment
    except ImportError:
        linear_sum_assignment = None
    return {"np": np, "NMF": NMF, "LDA": LatentDirichletAllocation, "stop": ENGLISH_STOP_WORDS,
            "CountVectorizer": CountVectorizer, "Tfidf": TfidfTransformer, "assign": linear_sum_assignment}


def analyzer(stop, segmented: bool):
    """Tokens for the topic model: space-separated words of a segmented column, or Latin words and CJK character bigrams."""
    def tokens(text: str) -> list:
        text = fold(text)
        if segmented:
            return [t for t in text.split() if t not in stop]
        out = [w for w in WORD.findall(text) if w not in stop]
        for run in CJK_RUN.findall(text):
            out += [run] if len(run) == 1 else [run[i:i + 2] for i in range(len(run) - 1)]
        return out
    return tokens


def match(ref: list, other: list, assign) -> list:
    """For each reference topic, the share of its top words in the top words of the topic matched to it."""
    share = [[len(set(a) & set(b)) / len(a) for b in other] for a in ref]
    if assign:
        rows, cols = assign([[-s for s in row] for row in share])
        pairs = {int(i): int(j) for i, j in zip(rows, cols)}
    else:
        pairs = {}
        for _, i, j in sorted(((share[i][j], i, j) for i in range(len(ref)) for j in range(len(other))), reverse=True):
            if i not in pairs and j not in pairs.values():
                pairs[i] = j
    return [share[i][pairs[i]] for i in range(len(ref))]


def umass(idx: list, binary) -> float:
    """Mean over pairs of top words, in rank order, of log((D(wi, wj) + 1) / D(wj))."""
    sub = binary[:, idx]
    co = (sub.T @ sub).toarray()
    pairs = [(i, j) for i in range(1, len(idx)) for j in range(i)]
    return sum(math.log((co[i][j] + 1) / co[j][j]) for i, j in pairs) / len(pairs) if pairs else 0.0


def read_log(path) -> dict:
    """{(k, topic): row} from the reading log; {} without one."""
    if not path:
        return {}
    log = {}
    for row in tl.read_table(Path(path), ("k", "topic", "units_read", "name", "read_by", "date"))[1]:
        if row["k"].isdigit() and row["topic"].isdigit():
            log[(int(row["k"]), int(row["topic"]))] = row
    return log


def naming(log: dict, key: tuple, shown: list, given: bool) -> tuple:
    """(name, why): a name only from a reading-log row that lists every representative unit as read, with reader and date."""
    row = log.get(key)
    if not row or not row["name"]:
        return "", "not named: " + ("no name in the reading log" if given else "no reading log")
    unread = [u for u in shown if u not in {x.strip() for x in re.split("[;；,]", row["units_read"])}]
    if unread:
        return "", f"not named: the reading log does not list {tl.few(unread)} as read"
    if not row["read_by"] or not row["date"]:
        return "", "not named: the reading log row needs read_by and date"
    return row["name"], f"named by {row['read_by']} on {row['date']} after reading {len(shown)} units"


def cmd_topics(args) -> int:
    d, ctx, corpus = corpus_of(args)
    out, sk = d / "topics", load_sklearn()
    out.mkdir(parents=True, exist_ok=True)
    try:
        ks, seeds = [int(x) for x in args.k.split(",")], [int(x) for x in args.seeds.split(",")]
    except ValueError:
        fail("--k and --seeds take whole numbers separated by commas")
    if min(ks) < 2 or len(seeds) < 2:
        fail("give K of 2 or more, and two seeds or more: stability is measured across seeds")
    if sk is None:
        result = {"status": "not_run", "reason": "scikit-learn missing", "detail": "topics needs scikit-learn and numpy; "
                  "ask the user before installing them"}
        tl.write_json(out / "topics.json", result)
        tl.show(result)
        return 0
    np, column = sk["np"], args.segmented or ctx["text"]
    if column not in corpus["header"]:
        fail(f"--segmented {column!r} is not a column of {corpus['path'].name}")
    units = [u for u, row in zip(corpus["units"], corpus["rows"]) if row[column]]
    texts = [row[column] for row in corpus["rows"] if row[column]]
    vectorizer = sk["CountVectorizer"](analyzer=analyzer(sk["stop"], bool(args.segmented)), min_df=args.min_df, max_df=args.max_df)
    try:
        counts = vectorizer.fit_transform(texts)
    except ValueError as exc:
        fail(f"no vocabulary is left after --min-df {args.min_df} and --max-df {args.max_df}: {exc}")
    vocab, binary = vectorizer.get_feature_names_out(), (counts > 0).astype(int)
    data, filled = counts if args.method == "lda" else sk["Tfidf"]().fit_transform(counts), np.asarray(counts.sum(axis=1)).ravel() > 0
    log, summary = read_log(args.reading_log), []
    for k in ks:
        runs = []
        for seed in seeds:
            model = (sk["LDA"](n_components=k, random_state=seed, learning_method="batch", max_iter=args.iter) if args.method == "lda"
                     else sk["NMF"](n_components=k, init="random", random_state=seed, max_iter=max(args.iter, 200)))
            weights = model.fit_transform(data)
            runs.append(([list(np.argsort(-row, kind="stable")[:args.top]) for row in model.components_], weights))
        shares = [match(runs[0][0], top, sk["assign"]) for top, _ in runs[1:]]
        rows, reading = [], [f"# Topics, K = {k}: what to read before naming", "",
                             "Read every unit below in full before naming a topic; top words alone do not name it.", ""]
        for t in range(k):
            top = [str(vocab[i]) for i in runs[0][0][t]]
            order = [i for i in np.argsort(-runs[0][1][:, t], kind="stable") if filled[i]][:args.docs]
            shown = [units[i] for i in order]
            stable = [s[t] for s in shares]
            name, why = naming(log, (k, t + 1), shown, bool(args.reading_log))
            rows.append([t + 1, " ".join(top), f"{umass(runs[0][0][t], binary):.3f}", f"{min(stable):.2f}",
                         f"{sum(stable) / len(stable):.2f}", "yes" if min(stable) < args.stable_min else "", ";".join(shown),
                         name, why])
            reading += [f"## Topic {t + 1}", "", f"Top words: {' '.join(top)}", "",
                        *(f"- {u}: {' '.join(texts[i].split())}" for u, i in zip(shown, order)), ""]
        write_csv(out / f"k{k}-topics.csv", ["topic", "top_words", "coherence_umass", "stability_min", "stability_mean",
                                             "unstable", "representative_units", "name", "name_status"], rows)
        (out / f"k{k}-reading.md").write_text("\n".join(reading), encoding="utf-8")
        summary.append({"k": k, "coherence_mean": round(sum(float(r[2]) for r in rows) / k, 3),
                        "unstable": [r[0] for r in rows if r[5]], "named": [r[0] for r in rows if r[7]],
                        "not_named": {r[0]: r[8] for r in rows if not r[7]}, "topics": str(out / f"k{k}-topics.csv")})
    settings = {"method": args.method, "seeds": seeds, "top_words": args.top, "representative_units": args.docs,
                "stable_min": args.stable_min, "min_df": args.min_df, "max_df": args.max_df, "iterations": args.iter,
                "tokens": f"the words of column {args.segmented}" if args.segmented else "Latin words and CJK character bigrams",
                "alignment": "linear_sum_assignment (scipy)" if sk["assign"] else "greedy (scipy missing)",
                "vocabulary": len(vocab), "units": len(units)}
    lines = ["# Topic models", "", "Settings (conventions): " + "; ".join(f"{k} {v}" for k, v in settings.items()) + ".", "",
             *tl.table(("K", "Mean UMass coherence", "Unstable topics", "Named topics"), [
                 (s["k"], s["coherence_mean"], ", ".join(map(str, s["unstable"])) or "none", ", ".join(map(str, s["named"])) or "none")
                 for s in summary]), "",
             "A topic is unstable when fewer than the stable_min share of its top words recur in its matched topic under "
             "every other seed. Choose K by coherence and by reading, never by coherence alone. A topic is named only by "
             "someone who read its representative units (k<K>-reading.md), recorded in the reading log."]
    (out / "topics.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    result = {"status": "done", "settings": settings, "models": summary, "report": str(out / "topics.md")}
    tl.write_json(out / "topics.json", result)
    tl.show(result)
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Dictionary counts and topic models as comparisons for a text variable.")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--dir", default="text-as-data", help="The skill's folder (default: text-as-data)")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("dictionary", parents=[common], help="Count the user's dictionary terms, with negation and context")
    p.add_argument("terms", help="CSV with the columns category and term")
    p.add_argument("--window", type=int, default=4, help="Tokens before a hit searched for a negator (default 4)")
    p.add_argument("--negators", help="A file of negators, one per line, instead of the default list")
    p.add_argument("--kwic", type=int, default=20, help="Hits per category sampled in context (default 20)")
    p.add_argument("--seed", type=int, default=1, help="Seed of the context sample (default 1)")
    p = sub.add_parser("topics", parents=[common], help="LDA or NMF over K and seeds: stability, coherence, reading list")
    p.add_argument("--k", required=True, help="Numbers of topics, separated by commas")
    p.add_argument("--seeds", default="1,2,3", help="Seeds, separated by commas (default 1,2,3)")
    p.add_argument("--method", choices=("lda", "nmf"), default="lda")
    p.add_argument("--top", type=int, default=10, help="Top words per topic (default 10)")
    p.add_argument("--docs", type=int, default=5, help="Representative units per topic (default 5)")
    p.add_argument("--stable-min", type=float, default=0.5, help="Smallest share of top words that must recur (default 0.5)")
    p.add_argument("--min-df", type=int, default=2, help="Units a token must occur in (default 2)")
    p.add_argument("--max-df", type=float, default=0.5, help="Largest share of units a token may occur in (default 0.5)")
    p.add_argument("--iter", type=int, default=50, help="Iterations of the fit (default 50)")
    p.add_argument("--segmented", help="A column of space-separated words to use instead of character bigrams")
    p.add_argument("--reading-log", help="CSV: k, topic, units_read, name, read_by, date")
    args = parser.parse_args(argv)
    return {"dictionary": cmd_dictionary, "topics": cmd_topics}[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
