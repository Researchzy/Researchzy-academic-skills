#!/usr/bin/env python3
"""Describe a writing style with counts: the author's own earlier texts, or a journal's papers (titles and
abstracts of saved Researchzy search results, or papers the user supplies). A profile describes; it does not
prescribe.

  style_profile.py build A.md B.tex C.docx [--kind author|journal] [--out polish/profile-author.json]
  style_profile.py build --search-json polish/journal-hits.json --venue "Journal of Sleep Research" [--venue …]
  style_profile.py compare polish/polished.md polish/profile-author.json [--out polish]

build counts per text: sentence length, words per paragraph, connectors, hedges and boosters per 1,000 words,
"we", a passive-voice proxy, US and UK spellings, serial commas, dashes, abbreviations, and "significant(ly)"
with and without a test in the sentence; from search results also title length, colons in titles, structured
abstracts and abstract length, after dropping hits whose venue is not a --venue name. It keeps counts and
sources (file names and SHA-256, DOIs, corpus ids, query, filters, search date), never text. Below the
conventional minimum (3 texts by the author, 5 journal papers, 20 abstracts; --min changes it) the status is
"not enough texts". compare writes profile-compare.md and .json: where a draft lies outside the range of the
profile's texts, as notes for the author, not errors.

Exit codes: 0; 2 for a usage error or an input that cannot be read. Standard library only; files are read
with polish_check.py next to this file. Portions are derived from MIT-licensed code: see LICENSE-MIT.txt next
to this file and THIRD_PARTY_NOTICES.md in the plugin.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import statistics
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import polish_check as pc  # noqa: E402  (reading, sentences and claim words, shared with the checker)

MINIMUM = {"author": 3, "journal papers": 5, "journal abstracts": 20}      # conventions, not anyone's rules
CONNECTORS = ("however", "moreover", "furthermore", "in addition", "additionally", "therefore", "thus", "hence",
              "consequently", "in contrast", "nevertheless", "nonetheless", "notably", "importantly", "indeed",
              "overall", "similarly", "conversely", "specifically", "finally")
HEDGES, BOOSTERS = ("rung1", "rung2", "approximation"), ("rung6", "intensifier")
RATES = ("hedges", "boosters", "we", "connectors", "dashes", "abbreviations")
PASSIVE = re.compile(r"\b(?:is|are|was|were|be|been|being)\s+(?:\w+ly\s+)?(?:\w+ed|shown|known|found|seen|given|taken"
                     r"|made|done|written|chosen|drawn|held|kept|led|left|set|put|run|told|brought|built|felt|got|met"
                     r"|paid|said|sent|sold|spent|understood)\b", re.I)
SERIAL = re.compile(r"\b(?!(?i:however|moreover|furthermore|therefore|thus|hence|first|second|finally|also|then|here|"
                    r"there|yet|still|indeed|instead|overall)\b)[A-Za-z][\w-]*, (?:[a-z][\w-]* ){0,2}[a-z][\w-]*(,?) "
                    r"(?:and|or) [a-z]")                                       # a rough count of lists of three
DASH = re.compile(r"—|---|\s–\s|\s--\s")
ABBR = re.compile(r"\b[A-Z][A-Z0-9]*[A-Z][A-Z0-9]*s?\b")
SIGNIFICANT = re.compile(r"\bsignificant(?:ly)?\b", re.I)
STRUCTURED = re.compile(r"(?:^|[.\n]\s*)(?:background|objectives?|aims?|purpose|introduction|methods?|design|setting"
                        r"|participants|results|findings|conclusions?|interpretation|importance)\s*:", re.I)
# US and UK spellings; the suffixes are listed one by one, because "analyses" and "organism" are spelled alike
# everywhere and must not count as UK spelling.
_IZE = ("random standard character optim general normal minim maxim util summar organ recogn emphas hypothes "
        "categor visual real special local central priorit parameter regular stabil initial token penal synthes "
        "harmon hospital immun steril crystall polar").split()
_OR = "color behavior favor tumor labor neighbor honor vapor odor flavor".split()
_PAIRS = [p.split("/") for p in ("center/centre centers/centres centered/centred fiber/fibre fibers/fibres "
          "modeling/modelling modeled/modelled labeling/labelling labeled/labelled signaling/signalling fetal/foetal "
          "anemia/anaemia hemoglobin/haemoglobin pediatric/paediatric leukemia/leukaemia edema/oedema "
          "estrogen/oestrogen diarrhea/diarrhoea aging/ageing artifact/artefact artifacts/artefacts sulfur/sulphur").split()]
_END, _OR_END = "(?:e|ed|es|ing|ation|ations|er|ers)", "(?:s|ed|ing|al|able|ably|hood|ite|ites)?"
SPELLING = {"US": re.compile(rf"\b(?:(?:{'|'.join(_IZE)})iz{_END}|(?:analy|cataly|paraly)z(?:e|ed|es|ing|er|ers)"
                             rf"|(?:{'|'.join(_OR)}){_OR_END}|{'|'.join(us for us, _ in _PAIRS)})\b", re.I),
            "UK": re.compile(rf"\b(?:(?:{'|'.join(_IZE)})is{_END}|(?:analy|cataly|paraly)s(?:e|ed|ing|er|ers)"
                             rf"|(?:{'|'.join(w[:-2] + 'our' for w in _OR)}){_OR_END}|{'|'.join(uk for _, uk in _PAIRS)})\b",
                             re.I)}


def measure(paragraphs: list) -> dict:
    """Counts for one text, given as paragraphs of plain sentences. Lists of lengths are kept apart: they are
    pooled for the profile and never stored."""
    sentences = [s for p in paragraphs for s in p]
    text, lengths = " ".join(sentences), [len(pc.WORD.findall(s)) for s in sentences]
    low = text.lower()
    marks = Counter(label for s in sentences for label, _ in pc.markers_in(s))
    serial = [m.group(1) for m in SERIAL.finditer(text)]
    significant = [bool(pc.TEST.search(s)) for s in sentences if SIGNIFICANT.search(s)]
    connectors = {c: n for c in CONNECTORS if (n := len(re.findall(rf"\b{c}\b", low)))}
    counts = {"words": sum(lengths), "sentences": len(sentences), "paragraphs": len(paragraphs),
              "hedges": sum(marks[x] for x in HEDGES), "boosters": sum(marks[x] for x in BOOSTERS),
              "we": len(re.findall(r"\b(?:we|our|ours|us)\b", low)), "connectors": sum(connectors.values()),
              "dashes": len(DASH.findall(text)), "abbreviations": len(ABBR.findall(text)),
              "passive_sentences": sum(bool(PASSIVE.search(s)) for s in sentences),
              "us_spellings": len(SPELLING["US"].findall(text)), "uk_spellings": len(SPELLING["UK"].findall(text)),
              "serial_comma": serial.count(","), "no_serial_comma": serial.count(""),
              "significant_with_test": sum(significant), "significant_without_test": len(significant) - sum(significant),
              "connector_counts": connectors}
    counts["sentence_median"] = statistics.median(lengths) if lengths else 0
    return {"counts": counts, "lengths": lengths, "paragraph_words": [sum(len(pc.WORD.findall(s)) for s in p)
                                                                       for p in paragraphs]}


def features(counts: dict) -> dict:
    """The values a draft is compared on: rates per 1,000 words, the share of passive sentences, the median
    sentence length."""
    words = max(1, counts["words"])
    return {**{k: round(1000 * counts[k] / words, 2) for k in RATES},
            "passive_share": round(counts["passive_sentences"] / max(1, counts["sentences"]), 3),
            "sentence_median": counts["sentence_median"]}


def quartiles(values: list) -> dict:
    if len(values) < 2:
        return {"median": values[0] if values else None, "q1": None, "q3": None}
    q1, median, q3 = statistics.quantiles(values, n=4, method="inclusive")
    return {"median": round(median, 1), "q1": round(q1, 1), "q3": round(q3, 1)}


def usual(counts: dict) -> str:
    ranked = sorted(counts.items(), key=lambda kv: -kv[1])
    return "none" if not ranked[0][1] else "mixed" if ranked[0][1] == ranked[1][1] else ranked[0][0]


def paragraphs_of(path: Path) -> list:
    doc = pc.parse(path)
    paragraphs: dict = {}
    for u in doc["sentences"]:
        if u["kind"] == "text":
            paragraphs.setdefault(u["para"], []).append(u["plain"])
    return list(paragraphs.values())


def venue_key(name) -> str:
    return re.sub(r"^the ", "", pc.squash(re.sub(r"[^a-z0-9& ]", " ", str(name or "").lower()).replace("&", " and ")))


def from_search(path: Path, venues: list) -> tuple[list, dict]:
    """Texts from saved search_papers results: the hits of the target venue that have an abstract."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        pc.fail(f"{path}: not readable JSON ({exc})")
    searches = data.get("searches", [data]) if isinstance(data, dict) else [{"results": data}]
    wanted, seen, texts = {venue_key(v) for v in venues}, set(), []
    sample = {"searches": [], "hits": 0, "duplicates": 0, "other_venue": 0, "no_abstract": 0, "venues_dropped": Counter()}
    for search in (s for s in searches if isinstance(s, dict)):
        sample["searches"].append({k: search.get(k, "not given") for k in ("query", "filters", "sort", "date")})
        for hit in (h for h in search.get("results") or search.get("papers") or [] if isinstance(h, dict)):
            sample["hits"] += 1
            ident = str(hit.get("corpusId") or hit.get("doi") or hit.get("title", "")).lower()
            if ident in seen:
                sample["duplicates"] += 1
            elif venue_key(hit.get("venue")) not in wanted:
                sample["other_venue"] += 1
                sample["venues_dropped"][str(hit.get("venue") or "no venue")] += 1
            elif not (hit.get("abstract") or "").strip():
                sample["no_abstract"] += 1
            else:
                abstract, title = hit["abstract"], str(hit.get("title") or "")
                texts.append(({"corpusId": hit.get("corpusId"), "doi": hit.get("doi"), "year": hit.get("year")},
                              [pc.split_sentences(pc.squash(abstract))], {
                                  "title_words": len(pc.WORD.findall(title)), "title_colon": ":" in title,
                                  "structured": len(STRUCTURED.findall(abstract)) >= 2,
                                  "abstract_words": len(pc.WORD.findall(abstract))}))
            seen.add(ident)
    sample["venues_dropped"] = dict(sample["venues_dropped"].most_common(10))
    sample["kept"] = len(texts)
    return texts, sample


def cmd_build(args) -> int:
    if bool(args.files) == bool(args.search_json):
        pc.fail("give either the author's files or --search-json, not both and not neither")
    if args.search_json:
        if not args.venue:
            pc.fail("--search-json needs --venue: the name of the target journal as the index writes it")
        texts, sample = from_search(Path(args.search_json), args.venue)
        kind, basis = "journal", "journal abstracts"
    else:
        texts = []
        for name in args.files:
            paragraphs = paragraphs_of(Path(name))                      # stops on a missing or unreadable file
            texts.append(({"file": Path(name).name, "sha256": hashlib.sha256(Path(name).read_bytes()).hexdigest()},
                          paragraphs, {}))
        kind, basis, sample = args.kind, "author" if args.kind == "author" else "journal papers", {}
    minimum = args.min or MINIMUM[basis]
    sources, lengths, paragraph_words, extra, total = [], [], [], [], Counter()
    for source, paragraphs, more in texts:
        m = measure(paragraphs)
        sources.append({**source, **m["counts"], **more})
        total.update({k: v for k, v in m["counts"].items() if k not in ("connector_counts", "sentence_median")})
        lengths += m["lengths"]
        paragraph_words += m["paragraph_words"]
        extra.append(more)
    total["sentence_median"] = statistics.median(lengths) if lengths else 0
    each = [features(s) for s in sources]
    profile = {"sentence_length": quartiles(lengths), "words_per_paragraph": quartiles(paragraph_words),
               "values": features(total),
               "ranges": {k: [min(f[k] for f in each), max(f[k] for f in each)] for k in (each[0] if each else {})},
               "spelling": {"US": total["us_spellings"], "UK": total["uk_spellings"]},
               "serial_comma": {"with": total["serial_comma"], "without": total["no_serial_comma"]},
               "significant": {"with_test": total["significant_with_test"],
                               "without_test": total["significant_without_test"]},
               "connector_counts": dict(sum((Counter(s["connector_counts"]) for s in sources), Counter()).most_common(10))}
    if kind == "journal" and args.search_json and extra:
        profile.update({"title_words": quartiles([e["title_words"] for e in extra]),
                        "title_colon_share": round(sum(e["title_colon"] for e in extra) / len(extra), 3),
                        "structured_share": round(sum(e["structured"] for e in extra) / len(extra), 3),
                        "abstract_words": quartiles([e["abstract_words"] for e in extra])})
    result = {"tool": pc.TOOL, "command": "build", "schema_version": 1, "kind": kind, "basis": basis,
              "status": "ok" if len(sources) >= minimum else "not enough texts", "texts": len(sources),
              "minimum": minimum, "minimum_is": "a convention; --min changes it", "sample": sample,
              "note": ("Researchzy's index matches keywords in titles and abstracts: these are papers on the query's "
                       "topic in this venue, not a random sample of it." if args.search_json else ""),
              "sources": sources, "profile": profile if len(sources) >= minimum else {}}
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"profile": str(out), "kind": kind, "status": result["status"], "texts": len(sources),
                      "minimum": minimum, **({"hits": sample["hits"], "kept": sample["kept"]} if sample else {})}, indent=2))
    return 0


def cmd_compare(args) -> int:
    try:
        profile = json.loads(Path(args.profile).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        pc.fail(f"{args.profile}: not readable JSON ({exc})")
    if not isinstance(profile, dict) or profile.get("tool") != pc.TOOL or profile.get("command") != "build":
        pc.fail(f"{args.profile}: not a profile written by style_profile.py build")
    draft = measure(paragraphs_of(Path(args.draft)))
    values, rows = features(draft["counts"]), []
    p = profile["profile"]
    if profile["status"] == "ok":
        for key, (lo, hi) in p["ranges"].items():
            note = ("within the range of the profile's texts" if lo <= values[key] <= hi else
                    f"{'higher' if values[key] > hi else 'lower'} than in every text of the profile")
            rows.append({"feature": key.replace("_", " ") + (" per 1,000 words" if key in RATES else ""),
                         "draft": values[key], "profile": f"{lo}–{hi}", "note": note})
        c = draft["counts"]
        for name, mine, theirs in (("spelling", usual({"US": c["us_spellings"], "UK": c["uk_spellings"]}),
                                    usual(p["spelling"])),
                                   ("serial comma", usual({"with": c["serial_comma"], "without": c["no_serial_comma"]}),
                                    usual(p["serial_comma"]))):
            rows.append({"feature": name, "draft": mine, "profile": theirs, "note": "the same" if mine == theirs else
                         "nothing to compare" if "none" in (mine, theirs) else
                         "different: ask the author which to use; do not change it unasked"})
        if c["significant_without_test"]:
            rows.append({"feature": "'significant' without a test in the sentence", "draft": c["significant_without_test"],
                         "profile": p["significant"]["without_test"], "note": "query the author; do not swap the word"})
    result = {"tool": pc.TOOL, "command": "compare", "draft": args.draft, "profile": args.profile, "kind": profile["kind"],
              "status": profile["status"], "notes": rows}
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "profile-compare.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    lines = ["# Draft against the style profile", "", f"`{args.draft}` against `{args.profile}` ({profile['kind']} profile, "
             f"{profile['texts']} texts).", ""]
    if profile["status"] != "ok":
        lines.append(f"Not compared: the profile has {profile['texts']} texts and the convention is at least "
                     f"{profile['minimum']}. A profile of so few texts describes those texts, not a style.")
    else:
        lines += ["These notes describe how the draft differs from the profile's texts. They are not errors and not "
                  "instructions: the author decides what, if anything, to change.", ""]
        lines += pc.table(("Feature", "Draft", "Profile", "Note"), [(r["feature"], r["draft"], r["profile"], r["note"])
                                                                     for r in rows])
        if profile["kind"] == "journal" and profile.get("basis") == "journal abstracts":
            lines += ["", "The profile comes from abstracts: compare the draft's abstract with it, not the whole paper."]
    (out / "profile-compare.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"status": profile["status"], "notes": len(rows), "report": str(out / "profile-compare.md")}, indent=2))
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Describe a writing style with counts, and compare a draft with it.")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("build", help="Build a profile from the author's texts, journal papers or saved search results")
    p.add_argument("files", nargs="*", help="The author's earlier texts, or journal papers with --kind journal")
    p.add_argument("--kind", choices=("author", "journal"), default="author")
    p.add_argument("--search-json", help="Researchzy search_papers results saved as JSON, with query, filters, date")
    p.add_argument("--venue", action="append", help="The target journal as the index names it (repeatable)")
    p.add_argument("--min", type=int, help="Least number of texts (conventions: author 3, journal papers 5, abstracts 20)")
    p.add_argument("--out", default="polish/profile.json", help="Profile file (default: polish/profile.json)")
    p = sub.add_parser("compare", help="Notes on how a draft differs from a profile")
    p.add_argument("draft")
    p.add_argument("profile")
    p.add_argument("--out", default="polish", help="Output folder (default: polish)")
    args = parser.parse_args(argv)
    return cmd_build(args) if args.command == "build" else cmd_compare(args)


if __name__ == "__main__":
    sys.exit(main())
