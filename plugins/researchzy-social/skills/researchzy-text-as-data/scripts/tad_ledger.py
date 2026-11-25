#!/usr/bin/env python3
"""The ledger of a text variable: blind validation rounds, the instructions frozen by the round that passed, the
full run with provenance on every row, and class shares corrected for the errors that round measured.

  tad_ledger.py sample [--seed S] [--size N] [--stratify COLUMN]   draw a round: the model's and the user's files
  tad_ledger.py seal --host H --model M [--batch-size B]            seal the model's labels before the user's exist
  tad_ledger.py score [--round N] [--boot 1000]                     agreement and per-class figures, once per round
  tad_ledger.py hash FILE                                           the SHA-256 to write on every row of a batch
  tad_ledger.py check-run [run.csv]                                 the full run against the round that passed
  tad_ledger.py correct [run.csv] [--boot 1000]                     corrected class shares, error rates per group

Every command takes --dir (default text-as-data), the folder with protocol.json, codebook.csv,
codebook-changes.csv, the instruction file and rounds/, in the formats of references/.

sample refuses a corpus with a column of labels (its units go to exposed.txt and are never drawn), and
instructions or a codebook that quote a drawn unit; it draws units never drawn, exposed or quoted, in proportion
to a group column on request. seal needs a class for every unit of the model's file and empty user files; it
records the SHA-256 of that file, the instructions and the codebook, the model as the host reports it, the
sampling settings (not controllable, by default) and the batch size. seal and score refuse when the
instructions or the codebook changed after the draw; score refuses an unsealed round, a model's file changed
after the seal, a label that is not a class and a round scored before. score gives kappa and nominal alpha (per
class in multi-label mode), per-class precision, recall and F1, macro-F1, the confusion matrix and seeded
bootstrap intervals; a class the user never gave is not estimable, never 0 or 1. check-run compares every row
of the run with the latest passed round (rows numbered from 1 without the header); correct inverts that round's
misclassification matrix and refuses while check-run fails. Units whose text speaks to the coder are leads,
labelled as data. Thresholds come from protocol.json; defaults are conventions and are labelled so.

Exit codes: 0 done; 1 when a round is below its thresholds or not assessable, or check-run finds a failure; 2
when an input cannot be read or is not in the documented format, or a step is refused. Standard library only.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import random
import re
import sys
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rz_agreement as ra  # noqa: E402

CHANGES = ("added", "renamed", "merged", "retired", "redefined")
DEFAULTS = {"kappa_min": 0.6, "alpha_min": 0.667, "macro_f1_min": 0.7, "class_f1_min": 0.5, "sample_size": 50}
LIMITS = ("kappa_min", "alpha_min", "macro_f1_min", "class_f1_min")
ROUND_COLUMNS = ("unit", "text", "label", "note")
RUN_COLUMNS = ("unit", "label", "instructions_sha256", "codebook_version", "model")
NONE, LEVEL = "none", 0.95
RUN, SHORT = 12, 8      # a unit is quoted when a text holds RUN of its tokens in a row, or all of a shorter unit;
                        # under SHORT tokens it is too short to tell (a CJK character is one token)
CJK = "぀-ヿ㐀-䶿一-鿿豈-﫿가-힯"
TOKEN = re.compile(rf"[{CJK}]|[^\W_{CJK}]+")
LABEL_NAME = re.compile(r"^(?:codes?|coding|class(?:es)?|categor(?:y|ies)|tags?|gold)$|(?:^|_)(?:labels?|annotations?)$"
                        r"|标签|类别|编码|分类|标注")
ADDRESSED = re.compile(
    r"(?:忽略|无视|不要理会|别管|不用管|不必遵守|不要遵守)掉?(?:你的|上面的|前面的|之前的|以上的?|所有的?|全部的?)*"
    r"(?:编码本|编码规则|规则|说明|指令|提示词?|要求|标准)"
    r"|(?:把|将)(?:这条|此条|本条|这段|所有|全部|以下)?(?:评论|内容|文本|回答)?(?:都|全部|一律)?"
    r"(?:标为|标成|标注为|编码为|编为|归为|归类为|分类为|判为|算作)"
    r"|(?:编码员|编码者|标注员|标注者|模型|人工智能)们?[，,：:\s]*(?:请|你|注意)"
    r"|\b(?:ignore|disregard|forget|override)\b[^.!?\n]{0,40}\b(?:codebook|instructions?|rules?|guidelines?|prompt)\b"
    r"|\b(?:label|code|classify|tag)\s+(?:this|it|everything|all)\b[^.!?\n]{0,30}\bas\b"
    r"|\b(?:note to|attention|dear)\s+(?:the\s+)?(?:coder|annotator|labell?er|model|ai|assistant)\b"
    r"|\byou are an? (?:ai|model|language model|assistant)\b", re.I)
USER_HINT = "Ask the user which class they meant; a new class is a codebook change, which ends this round."
MODEL_HINT = "Use a class of the codebook and put any doubt in the note column."


def fail(message: str):
    print(f"tad_ledger: {message}", file=sys.stderr)
    raise SystemExit(2)


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def at(base: Path, name: str) -> Path:
    """A path written in protocol.json: absolute, or relative to the folder, else to the working directory."""
    path = Path(name)
    return path if path.is_absolute() or (not (base / path).exists() and path.exists()) else base / path


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        fail(f"cannot read {path} as UTF-8 text: {exc}")


def read_table(path: Path, required: tuple = ()) -> tuple:
    """(header, rows) of a CSV or TSV; rows are dicts of stripped cells, blank rows left out."""
    text = read_text(path)
    delimiter = "\t" if path.suffix.lower() in (".tsv", ".tab") else max(",;\t", key=text.split("\n", 1)[0].count)
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    header = [name.strip() for name in reader.fieldnames or []]
    missing = [column for column in required if column not in header]
    if missing:
        fail(f"{path} lacks the column(s) {', '.join(missing)}; it needs {', '.join(required)}")
    rows = [{(k or "").strip(): v.strip() if isinstance(v, str) else "" for k, v in row.items()} for row in reader]
    return header, [row for row in rows if any(row.values())]


def read_json(path: Path, optional: bool = False) -> dict:
    if not path.is_file():
        return {} if optional else fail(f"{path} does not exist")
    try:
        data = json.loads(read_text(path))
    except json.JSONDecodeError as exc:
        fail(f"{path} is not valid JSON: {exc}")
    return data if isinstance(data, dict) else fail(f"{path} must hold a JSON object")


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def show(data: dict) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False))


def table(header: tuple, rows: list) -> list:
    cell = lambda value: re.sub(r"\s+", " ", str(value)).replace("|", "/").strip()  # noqa: E731
    return ["| " + " | ".join(header) + " |", "|" + "---|" * len(header),
            *("| " + " | ".join(cell(v) for v in row) + " |" for row in rows)]


def norm(text: str) -> str:
    return unicodedata.normalize("NFKC", text or "").strip()


def tokens(text: str) -> list:
    return TOKEN.findall(unicodedata.normalize("NFKC", text).casefold())


def spans(numbers) -> str:
    """[1, 2, 3, 7] as "1–3, 7"."""
    runs = []
    for n in sorted(numbers):
        if runs and n == runs[-1][1] + 1:
            runs[-1][1] = n
        else:
            runs.append([n, n])
    return ", ".join(str(a) if a == b else f"{a}–{b}" for a, b in runs)


def few(items: list, size: int = 5) -> str:
    return ", ".join(map(str, items[:size])) + (f" and {len(items) - size} more" if len(items) > size else "")


def fmt(value) -> str:
    return "not estimable" if value is None else f"{value:.2f}"


def percentile(values: list, q: float):
    if not values:
        return None
    h = (len(values) - 1) * q
    i = int(h)
    return values[i] + (h - i) * (values[i + 1] - values[i]) if i + 1 < len(values) else values[i]


def interval(box) -> str:
    if not box or box["low"] is None:
        return "not estimable"
    lost = f"; {box['not_estimable_draws']} resamples not estimable" if box["not_estimable_draws"] else ""
    return f"{box['low']:.2f} to {box['high']:.2f}{lost}"


def setting(protocol: dict, name: str) -> tuple:
    """(value, how it was set): the protocol's setting, or the default convention."""
    entry = (protocol.get("settings") or {}).get(name)
    if isinstance(entry, dict) and type(entry.get("value")) in (int, float):
        how = "default convention" if entry.get("default") else entry.get("source") or "no source given"
        return entry["value"], f"{entry['value']} ({how}, set {entry.get('date') or 'undated'})"
    return DEFAULTS[name], f"{DEFAULTS[name]} (default convention, not set in protocol.json)"


def load_codebook(d: Path) -> dict:
    """{"active": classes in use, "version": the current version, "sha256": of both files, "text": both files}."""
    path, changes = d / "codebook.csv", d / "codebook-changes.csv"
    if not path.is_file():
        fail(f"{path} does not exist: write the codebook first (references/protocol-and-codebook.md)")
    book, versions, raw = {}, [1], path.read_bytes()
    for number, row in enumerate(read_table(path, ("code", "definition", "version"))[1], 2):
        if not row["code"] or row["code"] in book or not row["version"].isdigit():
            fail(f"codebook.csv row {number}: every class needs its own row and a whole-number version")
        book[norm(row["code"])], versions = row, versions + [int(row["version"])]
    if changes.is_file():
        for number, ch in enumerate(read_table(changes, ("version", "date", "change", "code", "new_code", "reason",
                                                         "decided_by"))[1], 2):
            if not ch["version"].isdigit() or ch["change"] not in CHANGES or not ch["code"]:
                fail(f"codebook-changes.csv row {number}: needs a whole-number version, a change ({', '.join(CHANGES)}) and the code")
            versions.append(int(ch["version"]))
        raw += b"\0" + changes.read_bytes()
    return {"active": sorted(c for c, row in book.items() if row.get("status", "").lower() != "retired"),
            "version": max(versions), "sha256": hashlib.sha256(raw).hexdigest(), "text": raw.decode("utf-8", "replace")}


def load(d: Path) -> dict:
    if not d.is_dir():
        fail(f"no folder {d}: run from the working directory that holds it, or pass --dir")
    p = read_json(d / "protocol.json")
    corpus, classes = p.get("corpus") if isinstance(p.get("corpus"), dict) else {}, p.get("classes")
    named = isinstance(classes, list) and len(classes) >= 2 and len({norm(str(c)).casefold() for c in classes}) == len(classes)
    wrong = [name for name, ok in (("corpus.file", corpus.get("file")), ("corpus.id", corpus.get("id")),
                                   ("corpus.text", corpus.get("text")), ("classes: two or more distinct names", named),
                                   ("labels: single or multi", p.get("labels") in ("single", "multi")),
                                   ("seed: a whole number", type(p.get("seed")) is int)) if not ok]
    if wrong:
        fail(f"protocol.json lacks or misstates {'; '.join(wrong)} (references/protocol-and-codebook.md)")
    classes = [norm(str(c)) for c in classes]
    if p["labels"] == "multi" and NONE in {c.casefold() for c in classes}:
        fail(f'in multi-label mode "{NONE}" marks a unit without a class; it cannot be a class itself')
    cb, groups = load_codebook(d), corpus.get("groups") or []
    if sorted(classes) != cb["active"]:
        fail(f"protocol.json lists the classes {', '.join(classes)} but codebook.csv has {', '.join(cb['active'])}: "
             "make them the same")
    return {"dir": d, "protocol": p, "classes": classes, "canon": {c.casefold(): c for c in classes},
            "multi": p["labels"] == "multi", "id": corpus["id"], "text": corpus["text"],
            "groups": groups if isinstance(groups, list) else [groups], "corpus_path": at(d, corpus["file"]),
            "instructions": at(d, p.get("instructions") or "instructions.md"), "second": bool(p.get("second_coder")), "cb": cb}


def load_corpus(ctx: dict) -> dict:
    path = ctx["corpus_path"]
    if not path.is_file():
        fail(f"the corpus file {path} that protocol.json names does not exist")
    if path.suffix.lower() not in (".csv", ".tsv", ".tab", ".txt"):
        fail(f"{path.name}: the scripts read CSV or TSV. Write a CSV copy into text-as-data/ and record both files' SHA-256 "
             "in protocol.json (references/protocol-and-codebook.md)")
    header, rows = read_table(path, (ctx["id"], ctx["text"], *ctx["groups"]))
    units = {}
    for number, row in enumerate(rows, 1):
        if not row[ctx["id"]] or row[ctx["id"]] in units:
            fail(f"{path} row {number}: every unit needs its own id in the column {ctx['id']}")
        units[row[ctx["id"]]] = {"text": row[ctx["text"]], "groups": {g: row[g] for g in ctx["groups"]}}
    return {"path": path, "sha256": sha256(path), "header": header, "rows": rows, "units": units}


def rounds(d: Path) -> list:
    return sorted(int(m.group(1)) for m in (re.fullmatch(r"round(\d+)-sample\.json", p.name)
                                            for p in (d / "rounds").glob("round*-sample.json")) if m)


def files(d: Path, number: int) -> dict:
    return {kind: d / "rounds" / f"round{number}-{kind}" for kind in
            ("sample.json", "model.csv", "user.csv", "second.csv", "seal.json", "score.json", "score.md")}


def pick_round(d: Path, wanted) -> tuple:
    number = wanted or (rounds(d) or [None])[-1]
    if number is None or not files(d, number)["sample.json"].is_file():
        fail("no such round: run sample first")
    return number, files(d, number), read_json(files(d, number)["sample.json"])


def drawn(d: Path) -> dict:
    """{unit: the round that drew it}."""
    return {u["unit"]: n for n in rounds(d) for u in read_json(files(d, n)["sample.json"]).get("units", [])}


def scored(d: Path) -> list:
    """[(round, status)] of the rounds scored so far."""
    return [(n, read_json(files(d, n)["score.json"]).get("status")) for n in rounds(d) if files(d, n)["score.json"].is_file()]


def same_codebook(ctx: dict, sample: dict, number: int) -> None:
    if (sample.get("codebook_version"), sample.get("codebook_sha256")) != (ctx["cb"]["version"], ctx["cb"]["sha256"]):
        quiet = sample.get("codebook_version") == ctx["cb"]["version"]
        fail(f"the codebook changed after round {number} was drawn" + (" but its version did not: record the change in "
             "codebook-changes.csv with a new version and" if quiet else ":") + " draw a new round")


def same_instructions(ctx: dict, sample: dict, number: int, texts: dict) -> None:
    instr = ctx["instructions"]
    if not instr.is_file() or sha256(instr) != sample["instructions"]["sha256"]:
        grams = quote_grams(ctx)
        mine = [u for u, text in texts.items() if quoted(text, grams)]
        fail(f"the instructions changed after round {number} was drawn" + (
            f" and now quote units of this round ({few(mine)}): a few-shot example taken from the scoring sample" if mine
            else "") + ". A round measures instructions written before its units were read: draw a new round")


def quote_grams(ctx: dict) -> set:
    """Every run of SHORT to RUN tokens in the instruction file and the codebook."""
    grams = set()
    for text in (read_text(ctx["instructions"]) if ctx["instructions"].is_file() else "", ctx["cb"]["text"]):
        t = tokens(text)
        for n in range(SHORT, RUN + 1):
            grams.update(tuple(t[i:i + n]) for i in range(len(t) - n + 1))
    return grams


def quoted(text: str, grams: set) -> bool:
    t = tokens(text)
    need = min(RUN, len(t))
    return len(t) >= SHORT and any(tuple(t[i:i + need]) in grams for i in range(len(t) - need + 1))


def parse(cell: str, ctx: dict) -> tuple:
    """(label, ok): one class in single-label mode; a frozenset of classes in multi-label mode, empty for none."""
    keys = [part.strip().casefold() for part in re.split("[;；]", norm(cell)) if part.strip()]
    if ctx["multi"]:
        if keys == [NONE]:
            return frozenset(), True
        return frozenset(ctx["canon"].get(k) for k in keys), bool(keys) and all(k in ctx["canon"] for k in keys)
    return (ctx["canon"][keys[0]], True) if len(keys) == 1 and keys[0] in ctx["canon"] else (None, False)


def write_round(path: Path, rows: list) -> None:
    with open(path, "w", newline="", encoding="utf-8-sig") as handle:
        out = csv.writer(handle)
        out.writerow(ROUND_COLUMNS)
        out.writerows((unit, text, "", "") for unit, text in rows)


def read_round(path: Path, sample: dict, ctx: dict, who: str, hint: str, strict: bool = False) -> tuple:
    """({unit: label}, {unit: text}) of a filled round file."""
    if not path.is_file():
        fail(f"{path} does not exist: sample writes it")
    header, rows = read_table(path, ("unit", "text", "label"))
    units, got = [u["unit"] for u in sample["units"]], {row["unit"]: row for row in rows}
    extra = [column for column in header if column not in ROUND_COLUMNS]
    if strict and extra:
        fail(f"{path.name} has columns that sample did not write ({', '.join(extra)}): the model's file holds unit, text, "
             "label and note only, so that no other labels travel with it")
    if set(got) != set(units) or len(rows) != len(units):
        fail(f"{path.name} must hold exactly the {len(units)} units of the round, once each")
    if strict and any(hashlib.sha256(got[u["unit"]]["text"].encode()).hexdigest() != u["sha256"] for u in sample["units"]):
        fail(f"a text in {path.name} differs from the corpus as drawn: label the texts as sample wrote them")
    empty = [u for u in units if not got[u]["label"]]
    if empty:
        fail(f"{who} has no label for {few(empty)}")
    labels, bad = {}, {}
    for u in units:
        labels[u], ok = parse(got[u]["label"], ctx)
        if not ok:
            bad.setdefault(got[u]["label"], []).append(u)
    if bad:
        rule = "classes of the codebook separated by ;, or none" if ctx["multi"] else "one class of the codebook"
        fail(f"{who} uses labels that are not {rule}: " + "; ".join(f"{label!r} ({few(us)})" for label, us in bad.items())
             + f". Classes: {', '.join(ctx['classes'])}. {hint}")
    return labels, {u: got[u]["text"] for u in units}


def exposed(d: Path, add=()) -> set:
    """The units of exposed.txt, after writing `add` into it: their labels were where the agent could read them."""
    path = d / "exposed.txt"
    units = set(read_text(path).split()) if path.is_file() else set()
    if add:
        path.write_text("\n".join(sorted(units | set(add))) + "\n", encoding="utf-8")
    return units | set(add)


def label_columns(corpus: dict, ctx: dict) -> list:
    """[(column, ids with a filled cell, cells that are classes)] for columns other than the id and the text that
    hold labels: a label-like name, or cells that are mostly classes, with two classes or more among them."""
    keys, found = set(ctx["canon"]) | {NONE}, []
    for column in corpus["header"]:
        filled = [row for row in corpus["rows"] if row.get(column)] if column not in (ctx["id"], ctx["text"]) else []
        values = [{p.strip().casefold() for p in re.split("[;；]", norm(row[column])) if p.strip()} for row in filled]
        hits = [v for v in values if v and v <= keys]
        named = LABEL_NAME.search(re.sub(r"[\s-]+", "_", column.strip().casefold()))
        if filled and (named or (2 * len(hits) >= len(filled) and len(set().union(*hits) - {NONE}) >= 2)):
            found.append((column, [row[ctx["id"]] for row in filled], len(hits)))
    return found


def allocate(size: int, counts: dict) -> dict:
    """Units per group in proportion to its size, by largest remainder."""
    exact = {g: size * n / sum(counts.values()) for g, n in counts.items()}
    quota = {g: int(x) for g, x in exact.items()}
    for g in sorted(counts, key=lambda g: (quota[g] - exact[g], g))[:size - sum(quota.values())]:
        quota[g] += 1
    return quota


def cmd_sample(args) -> int:
    d = Path(args.dir)
    ctx = load(d)
    corpus = load_corpus(ctx)
    leaked = label_columns(corpus, ctx)
    if leaked:
        ids = exposed(d, {uid for _, filled, _ in leaked for uid in filled})
        fail(f"{corpus['path'].name} holds labels the agent must not see: " + "; ".join(
            f"column {c!r} ({len(f)} cells filled, {n} of them classes)" for c, f, n in leaked) + ". Ask the user for a "
            "copy without that column, kept apart from any file of their labels, and point corpus.file in protocol.json "
            f"at it. The units with a filled cell are listed in {d / 'exposed.txt'} and will never be drawn.")
    if not ctx["instructions"].is_file():
        fail(f"{ctx['instructions']} does not exist: write the instructions before the draw, so that they cannot be "
             "fitted to the units of the round")
    taken, grams = drawn(d), quote_grams(ctx)
    quotes = {u for u, x in corpus["units"].items() if quoted(x["text"], grams)}
    if quotes & set(taken):
        fail("the instructions or the codebook quote units drawn for a round: " + few(sorted(
            f"{u} (round {taken[u]})" for u in quotes & set(taken))) + ". Examples must come from units never drawn: "
            "replace them, then draw")
    hidden = exposed(d)
    left = {"drawn before": len(taken), "exposed": len(hidden & set(corpus["units"])),
            "quoted in the instructions or codebook": len(quotes), "empty text": 0}
    pool = []
    for u, x in corpus["units"].items():
        if u not in taken and u not in hidden and u not in quotes:
            left["empty text"] += not x["text"]
            pool += [u] if x["text"] else []
    number = (rounds(d) or [0])[-1] + 1
    seed = ctx["protocol"]["seed"] + number - 1 if args.seed is None else args.seed
    size, how = (args.size, "--size") if args.size else setting(ctx["protocol"], "sample_size")
    size, rng = min(int(size), len(pool)), random.Random(seed)
    if not size:
        fail("no unit is left to draw")
    if args.stratify:
        if args.stratify not in ctx["groups"]:
            fail(f"--stratify must name a group column of protocol.json: {', '.join(ctx['groups']) or 'none declared'}")
        strata = {}
        for u in pool:
            strata.setdefault(corpus["units"][u]["groups"][args.stratify], []).append(u)
        quota = allocate(size, {g: len(us) for g, us in strata.items()})
        picked = [u for g in sorted(strata) for u in rng.sample(strata[g], quota[g])]
    else:
        picked = rng.sample(pool, size)
    order = {u: i for i, u in enumerate(corpus["units"])}
    picked.sort(key=order.get)
    f, who = files(d, number), ("model", "user", "second") if ctx["second"] else ("model", "user")
    f["sample.json"].parent.mkdir(parents=True, exist_ok=True)
    write_json(f["sample.json"], {
        "round": number, "seed": seed, "population": len(pool), "size": size, "stratify": args.stratify, "left_out": left,
        "corpus": {"file": str(corpus["path"]), "sha256": corpus["sha256"]}, "codebook_version": ctx["cb"]["version"],
        "codebook_sha256": ctx["cb"]["sha256"], "instructions": {"file": str(ctx["instructions"]),
                                                                 "sha256": sha256(ctx["instructions"])},
        "created": now(), "units": [{"unit": u, "groups": corpus["units"][u]["groups"],
                                     "sha256": hashlib.sha256(corpus["units"][u]["text"].encode()).hexdigest()} for u in picked]})
    for name in who:
        write_round(f[f"{name}.csv"], [(u, corpus["units"][u]["text"]) for u in picked])
    show({"round": number, "seed": seed, "population": len(pool), "size": size, "size_setting": how,
          "stratify": args.stratify, "left_out": left, "files": [str(f[f"{name}.csv"]) for name in who],
          "addressed_to_the_coder": [u for u in picked if ADDRESSED.search(corpus["units"][u]["text"])],
          "next": "label every unit of the model's file from the instructions and the codebook alone, then run seal; "
                  "the user's labels stay out of the folder and the chat until the seal is recorded"})
    return 0


def cmd_seal(args) -> int:
    d = Path(args.dir)
    ctx = load(d)
    number, f, sample = pick_round(d, args.round)
    if f["seal.json"].exists():
        fail(f"round {number} is sealed already")
    same_codebook(ctx, sample, number)
    labels, texts = read_round(f["model.csv"], sample, ctx, "the model's file", MODEL_HINT, strict=True)
    same_instructions(ctx, sample, number, texts)
    if exposed(d) & set(texts):
        fail(f"units of round {number} are in exposed.txt: their labels were where the agent could read them. Draw a new round")
    for name in ("user", "second") if ctx["second"] else ("user",):
        path = f[f"{name}.csv"]
        if not path.is_file():
            write_round(path, list(texts.items()))
        elif any(row.get("label") for row in read_table(path)[1]):
            exposed(d, texts)
            fail(f"{path.name} holds labels before the seal, so the order of labelling cannot be shown; the round's units "
                 "are now in exposed.txt. Draw a new round; the user keeps their labels out of the folder until the seal "
                 "is recorded")
    batch = args.batch_size or len(labels)
    write_json(f["seal.json"], {
        "round": number, "sealed": now(), "model_file": f["model.csv"].name, "model_sha256": sha256(f["model.csv"]),
        "instructions": sample["instructions"], "codebook_version": sample["codebook_version"],
        "codebook_sha256": sample["codebook_sha256"], "host": args.host, "model": args.model, "sampling": args.sampling,
        "batch_size": batch, "format": args.format, "user_files_empty_at_seal": True})
    show({"round": number, "seal": str(f["seal.json"]), "model": args.model, "host": args.host, "sampling": args.sampling,
          "batch_size": batch, "next": "the user labels their file without seeing the model's labels; then run score"})
    return 0


def cmd_hash(args) -> int:
    path = Path(args.file)
    if not path.is_file():
        fail(f"no such file: {path}")
    show({"file": str(path), "sha256": sha256(path)})
    return 0


def figures(units: list, a: dict, b: dict, ctx: dict) -> dict:
    """Agreement of coder a with the reference b on a list of units (resampled units may repeat)."""
    if not ctx["multi"]:
        rep = ra.classification_report([b[u] for u in units], [a[u] for u in units], ctx["classes"])
        return {"kappa": ra.cohen_kappa([a[u] for u in units], [b[u] for u in units]), "per": rep["classes"],
                "macro_f1": rep["macro_f1"], "accuracy": rep["accuracy"], "confusion": rep["confusion"]}
    per = {c: ra.classification_report([c in b[u] for u in units], [c in a[u] for u in units], [True, False])["classes"][True]
           for c in ctx["classes"]}
    f1 = [p["f1"] for p in per.values() if p["f1"] is not None]
    return {"kappa": ra.kappa_by_code(units, a, b, ctx["classes"]), "per": per, "macro_f1": sum(f1) / len(f1) if f1 else None,
            "accuracy": sum(a[u] == b[u] for u in units) / len(units) if units else None}


def alphas(units: list, a: dict, b: dict, ctx: dict, n_boot: int, seed) -> dict:
    """Nominal alpha with its bootstrap interval: {"all": ...}, or one per class on present or absent."""
    if not ctx["multi"]:
        return {"all": ra.krippendorff_alpha_nominal([[a[u], b[u]] for u in units], n_boot, seed)}
    return {c: ra.krippendorff_alpha_nominal([[c in a[u], c in b[u]] for u in units], n_boot, seed) for c in ctx["classes"]}


def kappas(fig: dict, ctx: dict) -> dict:
    return {c: k["kappa"] for c, k in fig["kappa"].items()} if ctx["multi"] else {"all": fig["kappa"]["kappa"]}


def bootstrap(units: list, model: dict, user: dict, ctx: dict, n_boot: int, seed) -> dict:
    """Percentile intervals of kappa, macro-F1 and each class's F1 over units resampled with replacement."""
    rng, draws = random.Random(seed), {}
    for _ in range(n_boot):
        fig = figures([units[rng.randrange(len(units))] for _ in units], model, user, ctx)
        for name, value in [*((f"kappa {c}", k) for c, k in kappas(fig, ctx).items()), ("macro_f1", fig["macro_f1"]),
                            *((f"f1 {c}", p["f1"]) for c, p in fig["per"].items())]:
            draws.setdefault(name, []).append(value)
    tail, out = (1 - LEVEL) / 2, {}
    for name, values in draws.items():
        good = sorted(v for v in values if v is not None)
        out[name] = {"low": percentile(good, tail), "high": percentile(good, 1 - tail), "not_estimable_draws": len(values) - len(good)}
    return out


def judge(fig: dict, alpha: dict, limits: dict, ctx: dict) -> tuple:
    """(status, the figures below their thresholds or not estimable)."""
    (kmin, _), (amin, _), (fmin, _), (cmin, _) = (limits[name] for name in LIMITS)
    k = kappas(fig, ctx)
    keep = [c for c in k if k[c] is not None and alpha[c]["alpha"] is not None] if ctx["multi"] else ["all"]
    checks = [(f"kappa{'' if c == 'all' else ' of ' + c}", k[c], kmin) for c in keep]
    checks += [(f"alpha{'' if c == 'all' else ' of ' + c}", alpha[c]["alpha"], amin) for c in keep]
    checks += [("macro-F1", fig["macro_f1"], fmin)] + [(f"F1 of {c}", p["f1"], cmin) for c, p in fig["per"].items()
                                                       if p["f1"] is not None]
    missing = [name for name, value, _ in checks if value is None] or ([] if keep else ["every class"])
    if missing:
        return "not_assessable", [f"{name} not estimable" for name in missing]
    below = [f"{name} {value:.2f} below {limit}" for name, value, limit in checks if value < limit]
    return ("below_threshold" if below else "passed"), below


def where_errors_go(fig: dict, ctx: dict) -> list:
    """For each class the model missed, where its units went."""
    lines = []
    if ctx["multi"]:
        for c, k in fig["kappa"].items():
            missed, added = k["b_present"] - k["both_present"], k["a_present"] - k["both_present"]
            if missed or added:
                lines.append(f"- {c}: the model missed {missed} of the {k['b_present']} units the user gave it, "
                             f"and gave it to {added} unit(s) the user did not.")
        return lines
    labels, matrix = fig["confusion"]["labels"], fig["confusion"]["matrix"]
    for i, c in enumerate(labels):
        off = sorted(((n, labels[j]) for j, n in enumerate(matrix[i]) if j != i and n), reverse=True)
        if off:
            lines.append(f"- {c}: " + ", ".join(f"{n} of {sum(matrix[i])} labelled {other}" for n, other in off) + " by the model.")
    return lines


def cmd_score(args) -> int:
    d = Path(args.dir)
    ctx = load(d)
    number, f, sample = pick_round(d, args.round)
    if f["score.json"].exists():
        fail(f"round {number} has been scored, and a scored round is final: revise the codebook or the instructions "
             "if needed and draw a new round")
    seal = read_json(f["seal.json"], optional=True)
    if not seal:
        fail(f"round {number} is not sealed: label the model's file and run seal before the user's labels come in")
    if sha256(f["model.csv"]) != seal["model_sha256"]:
        fail(f"the model's file of round {number} changed after the seal, so the round cannot be scored: draw a new round")
    same_codebook(ctx, sample, number)
    units, seed = [u["unit"] for u in sample["units"]], sample["seed"]
    model, texts = read_round(f["model.csv"], sample, ctx, "the model's file", MODEL_HINT)
    same_instructions(ctx, sample, number, texts)
    user, _ = read_round(f["user.csv"], sample, ctx, "the user's file", USER_HINT)
    limits = {name: setting(ctx["protocol"], name) for name in LIMITS}
    fig, alpha = figures(units, model, user, ctx), alphas(units, model, user, ctx, args.boot, seed)
    boot = bootstrap(units, model, user, ctx, args.boot, seed)
    status, reasons = judge(fig, alpha, limits, ctx)
    before, groups = scored(d), {u["unit"]: u.get("groups") or {} for u in sample["units"]}
    people = None
    if ctx["second"]:
        second, _ = read_round(f["second.csv"], sample, ctx, "the second coder's file", USER_HINT)
        both = figures(units, second, user, ctx)
        people = {"kappa": kappas(both, ctx), "alpha": {c: a["alpha"] for c, a in alphas(units, second, user, ctx, 0, seed).items()}}
    differ = [u for u in units if model[u] != user[u]]
    say = lambda v: "; ".join(sorted(v)) or NONE if ctx["multi"] else v  # noqa: E731
    addressed = [u for u in units if ADDRESSED.search(texts[u])]
    write_json(f["score.json"], {
        "round": number, "status": status, "reasons": reasons, "thresholds": {n: how for n, (_, how) in limits.items()},
        "units": units, "seed": seed, "n_boot": args.boot, "level": LEVEL, "kappa": fig["kappa"], "alpha": alpha,
        "accuracy": fig["accuracy"], "macro_f1": fig["macro_f1"], "per_class": fig["per"], "confusion": fig.get("confusion"),
        "intervals": boot, "people": people, "addressed_to_the_coder": addressed, "rounds_drawn": len(rounds(d)),
        "scored_before": before, "disagreements": [{"unit": u, "model": say(model[u]), "user": say(user[u])} for u in differ],
        "scored": now()})
    k = kappas(fig, ctx)
    lines = [f"# Validation round {number}", "",
             f"Status: {status.replace('_', ' ')}" + (f": {'; '.join(reasons)}." if reasons else "."),
             f"{len(units)} units drawn with seed {seed} from {sample['population']}" + (f", in proportion to {sample['stratify']}"
             if sample.get("stratify") else "") + f"; codebook version {sample['codebook_version']}; instructions "
             f"SHA-256 {sample['instructions']['sha256'][:12]}. The model's file was sealed at {seal['sealed']}, while the user's "
             f"file was empty. Model: {seal['model']}, as {seal['host']} reports it; sampling settings: {seal['sampling']}; "
             f"batch size {seal['batch_size']}.",
             f"Rounds drawn: {len(rounds(d))}; scored before this one: " + (", ".join(f"round {n} ({s.replace('_', ' ')})"
                                                                              for n, s in before) or "none") + ".",
             "Thresholds: " + "; ".join(f"{n} {how}" for n, (_, how) in limits.items()) + ".",
             "These figures measure agreement between the model and this user on these units, under these instructions, "
             "this codebook and this model; they do not carry over to another version of any of them.", ""]
    if people:
        lines += ["## Between the two people", "", "; ".join(f"kappa{'' if c == 'all' else ' of ' + c} {fmt(v)}" for c, v in
                                                            people["kappa"].items()) + ". " + "; ".join(
            f"alpha{'' if c == 'all' else ' of ' + c} {fmt(v)}" for c, v in people["alpha"].items()) + ".", ""]
    name = lambda c: "" if c == "all" else f" of {c}"  # noqa: E731
    lines += ["## The model against the user", "", *table(("Figure", "Value", f"{LEVEL:.0%} interval"), [
        *((f"Kappa{name(c)}", fmt(v), interval(boot.get(f"kappa {c}"))) for c, v in k.items()),
        *((f"Alpha{name(c)}", fmt(a["alpha"]), interval(a["bootstrap"])) for c, a in alpha.items()),
        ("Accuracy" + (" (exact match)" if ctx["multi"] else ""), fmt(fig["accuracy"]), ""),
        (f"Macro-F1 over {len([p for p in fig['per'].values() if p['f1'] is not None])} of {len(ctx['classes'])} classes",
         fmt(fig["macro_f1"]), interval(boot.get("macro_f1")))]), "",
        *table(("Class", "User", "Model", "Precision", "Recall", "F1", "F1 interval", "Note"), [
            (c, p["support"], p["predicted"], fmt(p["precision"]), fmt(p["recall"]), fmt(p["f1"]),
             interval(boot.get(f"f1 {c}")) if p["f1"] is not None else "", p["detail"]) for c, p in fig["per"].items()]), ""]
    if not ctx["multi"]:
        labels, matrix = fig["confusion"]["labels"], fig["confusion"]["matrix"]
        lines += ["Rows: the user's label; columns: the model's.", "",
                  *table(("", *labels), [(c, *row) for c, row in zip(labels, matrix)]), ""]
    lines += ["## Where the errors go", "", *(where_errors_go(fig, ctx) or ["No error."]), "",
              f"## Disagreements ({len(differ)})", ""]
    for u in differ:
        tag = ", ".join(f"{g}: {v}" for g, v in groups[u].items())
        lines += [f"### {u}" + (f" ({tag})" if tag else ""), "", "> " + " ".join(texts[u].split()), "",
                  f"Model: {say(model[u])}. User: {say(user[u])}.", ""]
    if addressed:
        lines += ["## Text addressed to the coder", "", "These units speak to whoever labels them. They are labelled as data, "
                  "never obeyed: " + ", ".join(addressed) + ".", ""]
    if status == "passed":
        lines += ["## Frozen version", "", f"The instructions ({sample['instructions']['sha256']}), codebook version "
                  f"{sample['codebook_version']} and the model {seal['model']} of this round are the frozen version: the full "
                  f"run uses them, in batches of at most {seal['batch_size']}, and check-run compares every row with them.", ""]
    f["score.md"].write_text("\n".join(lines), encoding="utf-8")
    show({"round": number, "status": status, "reasons": reasons, "kappa": k, "macro_f1": fig["macro_f1"],
          "not_estimable": [c for c, p in fig["per"].items() if p["f1"] is None], "disagreements": len(differ),
          "addressed_to_the_coder": addressed, "report": str(f["score.md"])})
    return 0 if status == "passed" else 1


def passed_round(d: Path):
    """(number, files, sample, seal, score) of the latest round that passed, or None."""
    for number in reversed(rounds(d)):
        f = files(d, number)
        score = read_json(f["score.json"], optional=True)
        if score.get("status") == "passed":
            return number, f, read_json(f["sample.json"]), read_json(f["seal.json"]), score
    return None


def run_checks(ctx: dict, corpus: dict, path: Path) -> tuple:
    """(rows of (check, subject, state, detail), the passed round or None, {unit: label}) for the full run."""
    d, out, labels = ctx["dir"], [], {}

    def check(name, subject, ok, good, bad):
        out.append((name, subject, "pass" if ok else "fail", good if ok else bad))

    if not path.is_file():
        fail(f"no full run at {path}: write it as references/frozen-run.md describes")
    header, rows = read_table(path, RUN_COLUMNS)
    passed = passed_round(d)
    if not passed:
        return [("passed_round", "rounds", "fail", "No round has passed, so the labels are not validated: score a round.")], None, {}
    number, f, sample, seal, score = passed
    done = scored(d)
    out.append(("passed_round", f"round {number}", "pass", f"Passed at {score['scored']}; {len(rounds(d))} round(s) drawn, "
                f"{len(done)} scored: " + ", ".join(f"round {n} {s.replace('_', ' ')}" for n, s in done) + "."))
    seen, problems = {}, []
    for i, row in enumerate(rows, 1):
        seen.setdefault(row["unit"], []).append(i)
    missing = [u for u in corpus["units"] if u not in seen]
    twice = [i for u, at_rows in seen.items() for i in at_rows[1:]]
    stray = [i for u, at_rows in seen.items() if u not in corpus["units"] for i in at_rows]
    problems += [f"{len(missing)} unit(s) of the corpus have no row ({few(missing)})"] if missing else []
    problems += [f"rows {spans(twice)} repeat a unit"] if twice else []
    problems += [f"rows {spans(stray)} name units that are not in the corpus"] if stray else []
    check("coverage", path.name, not problems, f"One row for each of the {len(corpus['units'])} units of the corpus.",
          "; ".join(problems) + ".")
    bad = {}
    for i, row in enumerate(rows, 1):
        value, ok = parse(row["label"], ctx)
        if ok:
            labels.setdefault(row["unit"], value)
        else:
            bad.setdefault(row["label"] or "(empty)", []).append(i)
    check("labels", path.name, not bad, "Every label is a class.",
          "Not a class: " + "; ".join(f"{label!r} in rows {spans(at_rows)}" for label, at_rows in bad.items()) + ".")
    key = lambda text: " ".join(norm(text).casefold().split())  # noqa: E731
    for name, column, expected, what in (
            ("instructions", "instructions_sha256", seal["instructions"]["sha256"], "the SHA-256 of the sealed instructions"),
            ("codebook_version", "codebook_version", str(seal["codebook_version"]), "the codebook version of the round"),
            ("model", "model", seal["model"], "the model of the round")):
        wrong = [i for i, row in enumerate(rows, 1) if key(row[column]) != key(expected)]
        seen_values = sorted({row[column] for row in rows if key(row[column]) != key(expected)})
        check(name, column, not wrong, f"All {len(rows)} rows carry {what}.",
              f"Rows {spans(wrong)} carry {few(seen_values, 2)} instead of {what} ({expected}).")
    if "batch" in header:
        sizes = Counter(row.get("batch", "") for row in rows)
        over = sorted(b for b, n in sizes.items() if n > seal["batch_size"])
        check("batch_size", "batch", not over, f"No batch holds more than the round's {seal['batch_size']} units.",
              f"Batches {few(over)} hold more than the round's {seal['batch_size']} units.")
    else:
        out.append(("batch_size", "batch", "not_checked", "The run has no batch column."))
    instr = ctx["instructions"]
    check("instructions_file", instr.name, instr.is_file() and sha256(instr) == seal["instructions"]["sha256"],
          f"As sealed in round {number}.", f"Not the version sealed in round {number}: the run must use the frozen instructions.")
    check("codebook_file", "codebook.csv", ctx["cb"]["sha256"] == seal["codebook_sha256"], f"Version "
          f"{seal['codebook_version']}, as sealed.",
          f"The codebook changed after round {number} (now version {ctx['cb']['version']}).")
    taken, grams = drawn(d), quote_grams(ctx)
    quotes = [f"{u} (round {n})" for u, n in taken.items() if u in corpus["units"] and quoted(corpus["units"][u]["text"], grams)]
    check("examples", "instructions and codebook", not quotes, "No drawn unit is quoted in them.",
          f"They quote units drawn for a round: {few(quotes)}. Examples must come from units never drawn.")
    out.append(("corpus", corpus["path"].name, "pass" if corpus["sha256"] == sample["corpus"]["sha256"] else "not_checked",
                f"As when round {number} was drawn." if corpus["sha256"] == sample["corpus"]["sha256"] else
                f"The corpus file changed after round {number} was drawn: the round says nothing about units added since."))
    out += [("class_validated", c, "not_checked", f"No unit of round {number} has {c} in the user's labels: its labels "
             "in the run are not validated.") for c, p in score["per_class"].items() if p["f1"] is None]
    return out, passed, labels


def cmd_check_run(args) -> int:
    d = Path(args.dir)
    ctx = load(d)
    corpus, path = load_corpus(ctx), Path(args.run) if args.run else d / "run.csv"
    rows, passed, _ = run_checks(ctx, corpus, path)
    leads = [u for u, x in corpus["units"].items() if ADDRESSED.search(x["text"])]
    counts = {state: sum(row[2] == state for row in rows) for state in ("pass", "fail", "not_checked")}
    lines = ["# Full run check", "", f"Run: {path}. Validated by: {'round ' + str(passed[0]) if passed else 'no round'}. "
             "Row numbers count the rows of the run from 1, without the header.", "",
             f"{len(rows)} checks: {counts['pass']} pass, {counts['fail']} fail, {counts['not_checked']} not checked.", "",
             *table(("Check", "Subject", "State", "Detail"), rows)]
    if leads:
        lines += ["", "## Leads", "", f"Units whose text speaks to the coder, labelled as data: {few(leads, 20)}. Read their labels."]
    (d / "check-run.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    result = {"ok": not counts["fail"], "counts": counts, "validated_by": passed[0] if passed else None,
              "failed": [f"{r[0]}: {r[3]}" for r in rows if r[2] == "fail"],
              "not_checked": [f"{r[0]}: {r[1]}" for r in rows if r[2] == "not_checked"],
              "addressed_to_the_coder": leads, "report": str(d / "check-run.md")}
    write_json(d / "check-run.json", result)
    show(result)
    return 0 if result["ok"] else 1


def solve(m: list, q: list):
    """p with sum_i p[i] * m[i][j] = q[j] for every j, that is (M^T)^-1 q, by Gauss-Jordan elimination with partial
    pivoting; None when the matrix is singular."""
    k = len(q)
    a = [[m[i][j] for i in range(k)] + [q[j]] for j in range(k)]
    for col in range(k):
        pivot = max(range(col, k), key=lambda r: abs(a[r][col]))
        if abs(a[pivot][col]) < 1e-12:
            return None
        a[col], a[pivot] = a[pivot], a[col]
        for r in range(k):
            if r != col and a[r][col]:
                factor = a[r][col] / a[col][col]
                a[r] = [x - factor * y for x, y in zip(a[r], a[col])]
    return [a[i][k] / a[i][i] for i in range(k)]


def corrected(pairs: list, raw: list, classes: list) -> tuple:
    """(shares, None), or (None, why): the raw shares corrected with the misclassification rates of the (user, model)
    pairs, M[i][j] = share of the units the user put in class i that the model put in class j."""
    count = {c: Counter() for c in classes}
    for truth, pred in pairs:
        count[truth][pred] += 1
    absent = [c for c in classes if not sum(count[c].values())]
    if absent:      # in multi-label mode the classes are False and True: the class absent or present
        return None, "no unit of the round " + ("; ".join(("has the class" if c else "lacks the class") if isinstance(c, bool)
                                                         else f"has {c}" for c in absent)) + " in the user's labels"
    shares = solve([[count[i][j] / sum(count[i].values()) for j in classes] for i in classes], raw)
    return (shares, None) if shares else (None, "the misclassification matrix cannot be inverted")


def estimate(pairs: list, run: list, classes: list, n_boot: int, seed) -> dict:
    """Raw and corrected shares with percentile intervals from resampling the validation pairs; the run is held fixed."""
    raw = [sum(x == c for x in run) / len(run) if run else 0 for c in classes]
    point, why = corrected(pairs, raw, classes) if pairs and run else (None, "no validation unit or no row of the run")
    rng, draws = random.Random(seed), []
    for _ in range(n_boot if point else 0):
        draws.append(corrected([pairs[rng.randrange(len(pairs))] for _ in pairs], raw, classes)[0])
    good, tail = [x for x in draws if x], (1 - LEVEL) / 2
    shares = {}
    for i, c in enumerate(classes):
        values = sorted(x[i] for x in good)
        shares[c] = {"raw": raw[i], "corrected": point[i] if point else None, "low": percentile(values, tail),
                     "high": percentile(values, 1 - tail)}
    return {"validation_units": len(pairs), "run_units": len(run), "shares": shares, "not_estimable": why,
            "not_estimable_draws": len(draws) - len(good)}


def error_rates(pairs: list, classes: list) -> dict:
    """Per class: [found, of the units the user gave it] and [wrong, of the units the model gave it]."""
    return {c: {"recall": [sum(p == c for t, p in pairs if t == c), sum(t == c for t, _ in pairs)],
                "wrong": [sum(t != c for t, p in pairs if p == c), sum(p == c for _, p in pairs)]} for c in classes}


def gaps(by_group: dict, names: dict, column: str) -> list:
    """[(size, sentence)] for the differences in error rates between the groups of a column; names maps each
    class of the rates to the name shown."""
    found = []
    for c, shown in names.items():
        for key in ("wrong", "recall"):
            seen = sorted((k / n, str(g), k, n) for g, rates in by_group.items() for k, n in [rates[c][key]] if n)
            if len(seen) > 1 and seen[-1][0] > seen[0][0]:
                (_, g1, k1, n1), (_, g2, k2, n2) = seen[-1], seen[0]
                found.append((seen[-1][0] - seen[0][0], f"the model's {shown} labels were wrong in {k1} of {n1} units of "
                              f"{column} {g1}, and in {k2} of {n2} of {g2}" if key == "wrong" else f"of the units the user "
                              f"labelled {shown}, the model found {k1} of {n1} in {column} {g1}, and {k2} of {n2} in {g2}"))
    return found


NOTE = """## What these errors mean for an analysis

- **The class as the outcome**, compared across groups or regressed on a predictor such as {groups}. If the error
  rates were the same in every group, errors would blur the differences: with two classes they shrink toward zero;
  with more, a difference in one class also leaks into the classes it is confused with. When the rates differ
  between groups, as the leads above suggest, part of each group difference is a difference in errors: the
  estimate can be too large, too small or of the wrong sign.
- **The class as a predictor.** With two classes and errors that depend neither on the outcome nor on other
  predictors, its coefficient is pulled toward zero. With more classes, other predictors, or errors that differ by
  group or outcome, the bias can go either way and reaches the coefficients of correlated predictors.
- **What to report.** The raw and the corrected shares side by side, the error rates per class and group, and the
  round they come from. A regression corrected for misclassification, which uses the validation round as a
  gold-standard subsample, is not computed here: name it in the limitations as a step the user can take.
"""


def cmd_correct(args) -> int:
    d = Path(args.dir)
    ctx = load(d)
    corpus, path = load_corpus(ctx), Path(args.run) if args.run else d / "run.csv"
    rows, passed, labels = run_checks(ctx, corpus, path)
    failed = [f"{r[0]} ({r[3]})" for r in rows if r[2] == "fail"]
    if failed:
        fail("correct needs a full run that passes check-run; fix first: " + "; ".join(failed[:3]))
    number, f, sample, seal, _ = passed
    model, _ = read_round(f["model.csv"], sample, ctx, "the model's file", MODEL_HINT)
    user, _ = read_round(f["user.csv"], sample, ctx, "the user's file", USER_HINT)
    group_of = {u["unit"]: u.get("groups") or {} for u in sample["units"]}
    if ctx["multi"]:    # one present-or-absent variable per class
        variables = [(c, [False, True], lambda u, c=c: c in user[u], lambda u, c=c: c in model[u],
                      lambda u, c=c: c in labels[u]) for c in ctx["classes"]]
    else:
        variables = [("", ctx["classes"], user.get, model.get, labels.get)]

    def run_for(units_v, units_r) -> dict:
        out = {}
        for name, cls, truth, pred, ran in variables:
            pairs = [(truth(u), pred(u)) for u in units_v]
            out[name] = {"estimate": estimate(pairs, [ran(u) for u in units_r], cls, args.boot, sample["seed"]),
                         "rates": error_rates(pairs, cls)}
        return out

    show_class = lambda name, c: name if ctx["multi"] else c  # noqa: E731
    shown = lambda cls: cls[1:] if ctx["multi"] else cls  # noqa: E731
    every = run_for(list(group_of), list(corpus["units"]))
    by_group, found = {}, []
    for g in ctx["groups"]:
        values = sorted({x["groups"][g] for x in corpus["units"].values()})
        by_group[g] = {v: run_for([u for u in group_of if group_of[u].get(g) == v],
                                  [u for u, x in corpus["units"].items() if x["groups"][g] == v]) for v in values}
        for name, cls, *_ in variables:
            found += gaps({v: r[name]["rates"] for v, r in by_group[g].items()}, {c: show_class(name, c) for c in shown(cls)}, g)
    leads = [text for _, text in sorted(found, key=lambda item: -item[0])[:5]]

    def rows_of(result: dict, prefix=()) -> list:
        out = []
        for name, cls, *_ in variables:
            est, rates = result[name]["estimate"], result[name]["rates"]
            for c in shown(cls):
                s, x = est["shares"][c], est["shares"][c]["corrected"]
                odd = x is not None and not 0 <= x <= 1
                out.append((*prefix, show_class(name, c), "{}/{}".format(*rates[c]["recall"]), "{}/{}".format(*rates[c]["wrong"]),
                            f"{s['raw']:.3f}", fmt(x) if x is None else f"{x:.3f}", "" if s["low"] is None else
                            f"{s['low']:.3f} to {s['high']:.3f}",
                            est["not_estimable"] or ("outside 0 to 1: too few units" if odd else "")))
        return out

    head = ("Class", "Found", "Wrong", "Raw share", "Corrected", "Interval", "Note")
    lost = sum(r["estimate"]["not_estimable_draws"] for r in every.values())
    lines = ["# Measurement-error note", "", f"Run: {path} ({len(labels)} units), labelled with the frozen version of round "
             f"{number}: instructions {seal['instructions']['sha256'][:12]}, codebook version {seal['codebook_version']}, model "
             f"{seal['model']} as {seal['host']} reports it. Validation: round {number}, {len(group_of)} units drawn with seed "
             f"{sample['seed']} from {sample['population']}" + (f" in proportion to {sample['stratify']}" if sample.get("stratify")
                                                                 else "") + ".", "",
             "Found: units the model gave the class, of those the user gave it. Wrong: units the user gave another class, of "
             "those the model gave it. The corrected shares solve raw = M^T x corrected, M holding the round's "
             "misclassification rates (row: the user's class; column: the model's)" + (", one present-or-absent matrix per "
             "class" if ctx["multi"] else "") + f". Intervals: {LEVEL:.0%} percentile, {args.boot} resamples of the round's "
             f"units, seed {sample['seed']}; the run's counts are held fixed, so they show the uncertainty of the round only. "
             f"Resamples that could not be corrected: {lost}.", "", "## All units", "", *table(head, rows_of(every)), ""]
    for g, results in by_group.items():
        lines += [f"## By {g}", "", *table((g, *head), [r for v, res in results.items() for r in rows_of(res, (v,))]), ""]
    lines += ["## Leads", "", *([f"- {lead[0].upper()}{lead[1:]}." for lead in leads]
                                 or ["- No difference in error rates between groups."]), "",
              NOTE.format(groups=", ".join(ctx["groups"]) or "a group")]
    (d / "error-note.md").write_text("\n".join(lines), encoding="utf-8")
    result = {"round": number, "seed": sample["seed"], "n_boot": args.boot, "level": LEVEL, "overall": every,
              "groups": by_group, "leads": leads, "report": str(d / "error-note.md")}
    write_json(d / "correct.json", result)
    show({"round": number, "overall": {show_class(n, c): every[n]["estimate"]["shares"][c] for n, cls, *_ in variables
                                       for c in shown(cls)}, "leads": leads, "report": str(d / "error-note.md")})
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Validation rounds, the frozen run and corrected shares of a text variable.")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--dir", default="text-as-data", help="The skill's folder (default: text-as-data)")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("sample", parents=[common], help="Draw a round and write the model's and the user's files")
    p.add_argument("--seed", type=int, help="Seed of the draw (default: the protocol's seed plus the round number less one)")
    p.add_argument("--size", type=int, help="Units to draw (default: the sample_size setting)")
    p.add_argument("--stratify", help="A group column: draw from each group in proportion to its size")
    p = sub.add_parser("seal", parents=[common], help="Seal the model's filled file before the user's labels exist")
    p.add_argument("--round", type=int, help="The round (default: the latest)")
    p.add_argument("--host", required=True, help="The product that runs the model, as it names itself")
    p.add_argument("--model", required=True, help="The model's name, as the host reports it")
    p.add_argument("--batch-size", type=int, help="Units labelled per batch (default: the whole round)")
    p.add_argument("--format", default="CSV rows of unit and text, as in the round file", help="How the units were shown")
    p.add_argument("--sampling", default="not controllable", help="The sampling settings, only when the host shows them")
    p = sub.add_parser("score", parents=[common], help="Score a sealed round, once")
    p.add_argument("--round", type=int, help="The round (default: the latest)")
    p.add_argument("--boot", type=int, default=1000, help="Bootstrap resamples (default 1000)")
    p = sub.add_parser("hash", parents=[common], help="Print the SHA-256 of a file, to write on each row of a batch")
    p.add_argument("file")
    p = sub.add_parser("check-run", parents=[common], help="Check the full run against the round that passed")
    p.add_argument("run", nargs="?", help="The full run (default: <dir>/run.csv)")
    p = sub.add_parser("correct", parents=[common], help="Corrected class shares and error rates per group")
    p.add_argument("run", nargs="?", help="The full run (default: <dir>/run.csv)")
    p.add_argument("--boot", type=int, default=1000, help="Bootstrap resamples (default 1000)")
    args = parser.parse_args(argv)
    if any(getattr(args, name, None) is not None and getattr(args, name) < 1 for name in ("size", "batch_size")):
        fail("--size and --batch-size must be at least 1")
    if getattr(args, "boot", 1) < 0:
        fail("--boot must be 0 or more")
    return {"sample": cmd_sample, "seal": cmd_seal, "score": cmd_score, "hash": cmd_hash, "check-run": cmd_check_run,
            "correct": cmd_correct}[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
