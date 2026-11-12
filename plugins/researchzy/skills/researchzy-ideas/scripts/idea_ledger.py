#!/usr/bin/env python3
"""The ledger of a set of research ideas: the cards, the novelty searches, the checks, and what passed.

The agent searches, reads and judges; this script keeps the record in ideas/ideas.json, binds every
novelty search to the wording of the idea it was run for, and refuses a recommendation that the
record does not support. Ratings are kept per dimension; nothing is added up.

  idea_ledger.py brief --field "…" --question-type causal --data "…" --equipment "…" --months 18 --skills "…"
  idea_ledger.py add card.json                       one card or a list of cards; prints the new ids
  idea_ledger.py add --title "…" --question "…" --claim-type causal --hypothesis "…" --refuted-by "…"
  idea_ledger.py revise i1 --hypothesis "…"          a changed question or hypothesis is a new version
  idea_ledger.py search base --query "…" --total 240 --sort year             the evidence base
  idea_ledger.py search i1 --intent duplicate --query '"…" …' --total 37 --sort year --filter yearFrom=2023
  idea_ledger.py search i1 --intent skeptic --query "…" --failed "RATE_LIMITED: try again later"
  idea_ledger.py closest i1 closest.json             the closest works as returned, plus the comparison,
                                                     how far each was read, and "decisive": true on one
  idea_ledger.py novelty i1 --status differentiated  unsearched | inconclusive | overlap_found | differentiated
  idea_ledger.py gate i1 data=confirmed ethics=plausible equipment=confirmed skills=plausible time=unknown
  idea_ledger.py assume i1 --text "…" --risk 4 --months 2 --test "…"
  idea_ledger.py rate i1 value=2:"reason" difference=2:"reason" testability=3:"reason" …
  idea_ledger.py attack i1 --attack "…" --basis "…" --change "…" --residual "…"
  idea_ledger.py study i1 decision="…" support="…" refute="…" undetermined="…" null_value="…" budget="…" first_action="…"
  idea_ledger.py recommend i1                        succeeds only when the record supports it
  idea_ledger.py reject i2 --reason "…" --restart-if "…"
  idea_ledger.py status                              where every idea stands and what it lacks
  idea_ledger.py export                              ideas.md and novelty-log.md

All commands take --dir (default: ideas) and --date (default: today) before the command name.
Standard library only. Exit code 1: `recommend` or `novelty` was refused (the JSON lists what is
missing), or the input was bad (one line on standard error). A malformed command line exits 2.
"""

from __future__ import annotations

import argparse
import datetime
import json
import re
import sys
from pathlib import Path

CARD_FIELDS = ("title", "question", "claim_type", "hypothesis", "if_true", "if_rival", "refuted_by",
               "undetermined_if", "data", "first_test", "origin")
CARD_LABELS = (("question", "Question"), ("claim_type", "Claim type"), ("hypothesis", "Hypothesis"),
               ("if_true", "Expected if true"), ("if_rival", "Expected under the main rival explanation"),
               ("refuted_by", "Refuted by"), ("undetermined_if", "Undetermined if"),
               ("data", "Data and resources"), ("first_test", "First test"))
CLAIM_TYPES = ("descriptive", "associational", "predictive", "causal", "mechanistic")
INTENTS = ("duplicate", "mechanism", "adjacent", "skeptic")
NOT_AVAILABLE = {"citation": "the index has no cited-by search, so works citing the closest papers were not traced"}
SORTS = ("relevance", "citationCount", "year", "influency")
TOOLS = ("search_papers", "list_library_papers")
NOVELTY = {"unsearched": "not searched", "inconclusive": "inconclusive", "overlap_found": "overlap found",
           "differentiated": "differentiated within the searches logged"}
READ = ("metadata", "abstract", "full_text")
WORK_FIELDS = ("corpusId", "title", "authors", "authorCount", "year", "venue", "doi", "arxiv", "citationCount",
               "hasReadablePdf", "readerUrl")
COMPARISON = ("what_it_solved", "overlap", "difference", "why_it_matters")
GATES = ("data", "ethics", "equipment", "skills", "time")
GATE_STATUS = ("confirmed", "plausible", "unknown", "blocked")
DIMENSIONS = ("value", "difference", "testability", "feasibility", "information_gain")
ATTACK_FIELDS = ("attack", "basis", "change", "residual")
STUDY_FIELDS = (("decision", "Decision it informs"), ("support", "Supports the hypothesis if"),
                ("refute", "Refutes it if"), ("undetermined", "Undetermined if"),
                ("null_value", "What a null result is worth"), ("budget", "Budget cap"),
                ("first_action", "First action"))
BRIEF_FIELDS = ("field", "question_type", "data", "equipment", "months", "skills", "note")


def load(directory: Path) -> dict:
    path = directory / "ideas.json"
    if not path.exists():
        return {"tool": "researchzy-ideas", "schema_version": 1, "brief": {name: "" for name in BRIEF_FIELDS},
                "searches": [], "ideas": {}}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{path} is not valid JSON ({exc}). Restore it or move it aside.")


def save(directory: Path, ledger: dict) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "ideas.json").write_text(json.dumps(ledger, indent=2, ensure_ascii=False), encoding="utf-8")


def read_json(source: str):
    try:
        return json.loads(sys.stdin.read() if source == "-" else Path(source).read_text(encoding="utf-8"))
    except OSError as exc:
        raise SystemExit(f"Cannot read {source}: {exc.strerror}.")
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{source} is not valid JSON ({exc}).")


def tidy(text) -> str:
    return re.sub(r"\s+", " ", str(text)).strip()


def same(a: str, b: str) -> bool:
    return tidy(a).lower() == tidy(b).lower()


def pairs(items: list, names: tuple, what: str) -> dict:
    """name=value arguments, with the names checked."""
    out = {}
    for item in items:
        name, sep, value = item.partition("=")
        if not sep or name not in names:
            raise SystemExit(f"{what} takes name=value with a name from: {', '.join(names)}. Got {item!r}.")
        out[name] = value.strip()
    return out


def get_idea(ledger: dict, ref: str) -> dict:
    if ref not in ledger["ideas"]:
        raise SystemExit(f"No idea {ref!r} in the ledger ({', '.join(ledger['ideas']) or 'it is empty'}). Add it first.")
    return ledger["ideas"][ref]


def clean_card(card) -> dict:
    if not isinstance(card, dict):
        raise SystemExit("A card is a JSON object with the fields: " + ", ".join(CARD_FIELDS))
    unknown = [name for name in card if name not in CARD_FIELDS]
    if unknown:
        raise SystemExit(f"Unknown card field(s): {', '.join(unknown)}. The fields are: {', '.join(CARD_FIELDS)}")
    card = {name: tidy(value) for name, value in card.items() if value is not None and tidy(value)}
    if card.get("claim_type") and card["claim_type"] not in CLAIM_TYPES:
        raise SystemExit(f"claim_type is one of: {', '.join(CLAIM_TYPES)}. Got {card['claim_type']!r}.")
    return card


def flag_card(args) -> dict:
    return clean_card({name: getattr(args, name) for name in CARD_FIELDS if getattr(args, name) is not None})


# ---------------------------------------------------------------------------------------------
# What the record supports


def current_searches(ledger: dict, idea: dict) -> list:
    return [s for s in ledger["searches"] if s["idea"] == idea["id"] and s["version"] == idea["version"]]


def intents_done(ledger: dict, idea: dict) -> list:
    """Intents with a completed index search for the idea's current version. A failed search is not one."""
    done = {s["intent"] for s in current_searches(ledger, idea) if s["outcome"] == "ok" and s["tool"] == "search_papers"}
    return [intent for intent in INTENTS if intent in done]


def current_closest(idea: dict) -> list:
    return [w for w in idea["closest"] if w["version"] == idea["version"]]


def work_key(work: dict) -> str:
    if work.get("corpusId") not in (None, ""):
        return f"c{work['corpusId']}"
    return tidy(work.get("doi") or work.get("title") or "").lower()


def work_label(work: dict) -> str:
    names = [a.get("name", "") if isinstance(a, dict) else str(a) for a in work.get("authors") or []]
    names = [tidy(n) for n in names if tidy(n)]
    who = ""
    if names:
        who = names[0].split(",")[0].strip() if "," in names[0] else names[0].split()[-1]
        who += " et al." if (work.get("authorCount") or len(names)) > 1 else ""
    head = " ".join(str(part) for part in (who, work.get("year")) if part)
    return f"{head}: {work['title']}" if head else str(work["title"])


def novelty_gaps(ledger: dict, idea: dict, status: str) -> list:
    """What the record lacks for this novelty status, for the idea's current version."""
    version, works, done = idea["version"], current_closest(idea), intents_done(ledger, idea)
    gaps = []
    if status == "inconclusive" and not done:
        gaps.append(f"no completed search_papers search is logged for version {version}; without one the status is unsearched")
    if status == "overlap_found" and not any(w.get("overlap") for w in works):
        gaps.append(f"no closest work with a stated overlap is recorded for version {version}: an overlap needs a named paper")
    if status == "differentiated":
        if "duplicate" not in done:
            gaps.append(f"no completed search_papers search with intent duplicate for version {version}")
        if len(done) < 2:
            gaps.append(f"completed searches cover {len(done)} intent(s) for version {version}; two are needed")
        if not works:
            gaps.append(f"no closest work is recorded for version {version}")
        gaps += [f"closest work {work_label(w)!r} has no stated difference" for w in works if not w.get("difference")]
    return gaps


def recommendation_gaps(ledger: dict, idea: dict) -> list:
    """Exactly what stands between the idea and a recommendation. Empty when nothing does."""
    gaps = []
    if idea["novelty"]["status"] != "differentiated":
        gaps.append(f"novelty is {idea['novelty']['status']} for version {idea['version']}, not differentiated")
    decisive = next((w for w in current_closest(idea) if w.get("decisive")), None)
    if decisive is None:
        gaps.append("no closest work is marked decisive and read in full text")
    elif decisive["read"] != "full_text":
        gaps.append(f"the decisive closest work was read from the {decisive['read']} only: {work_label(decisive)}")
    gaps += [f"gate {g} is blocked" for g in GATES if idea["gates"].get(g, {}).get("status") == "blocked"]
    unrated = [d for d in DIMENSIONS if d not in idea["ratings"]]
    if unrated:
        gaps.append("not rated: " + ", ".join(unrated))
    if not idea["refuted_by"]:
        gaps.append("the card has no refuting result (refuted_by)")
    return gaps


def late_risk(ledger: dict, idea: dict) -> str:
    """Why the riskiest assumption cannot be shown to be testable early, or an empty string."""
    worst = max(idea["assumptions"], key=lambda a: (a["risk"], a["months"]), default=None)
    if worst is None or worst["risk"] < 3:
        return ""
    what = f"the riskiest assumption (risk {worst['risk']}: {worst['text']}) takes {worst['months']:g} months to test"
    available = ledger["brief"].get("months")
    if not available:
        return what + ", and the brief gives no months to judge whether that is early"
    return what + f", more than a quarter of the {available:g} months available" if worst["months"] > available / 4 else ""


def open_points(ledger: dict, idea: dict) -> list:
    """What a reader should know about an idea that does not block a recommendation."""
    points = [f"gate {g} is {idea['gates'].get(g, {}).get('status', 'not assessed')}" for g in GATES
              if idea["gates"].get(g, {}).get("status") not in ("confirmed", "plausible", "blocked")]
    empty = [name for name, _ in CARD_LABELS if not idea[name] and name != "refuted_by"]
    if empty:
        points.append("the card leaves empty: " + ", ".join(empty))
    done = intents_done(ledger, idea)
    failed = [i for i in INTENTS if i not in done and any(s["intent"] == i and s["outcome"] == "failed"
                                                          for s in current_searches(ledger, idea))]
    if failed:
        points.append(f"the searches for {', '.join(failed)} failed and were not repeated (a failed search is not zero results)")
    points.append(late_risk(ledger, idea) if idea["assumptions"] else "no assumption is recorded")
    if not idea["attacks"]:
        points.append("no attack is recorded")
    unset = [name for name, _ in STUDY_FIELDS if not idea["study"].get(name)]
    if unset:
        points.append("the first study lacks: " + ", ".join(unset))
    return [p for p in points if p]


def state(ledger: dict, idea: dict) -> str:
    """recommended | open | rejected. A recommendation the record no longer supports is open."""
    if idea["state"] == "recommended" and recommendation_gaps(ledger, idea):
        return "open"
    return idea["state"]


# ---------------------------------------------------------------------------------------------
# Commands


def cmd_brief(ledger: dict, args) -> dict:
    for name in BRIEF_FIELDS:
        if getattr(args, name) is not None:
            ledger["brief"][name] = getattr(args, name)
    return {"brief": ledger["brief"]}


def cmd_add(ledger: dict, args) -> dict:
    cards = [{}]
    if args.file:
        data = read_json(args.file)
        cards = data if isinstance(data, list) else [data]
    added = []
    for raw in cards:
        card = {**clean_card(raw), **flag_card(args)}
        missing = [name for name in ("question", "claim_type", "hypothesis") if not card.get(name)]
        if missing:
            raise SystemExit(f"A card needs: {', '.join(missing)}.")
        twin = next((i["id"] for i in ledger["ideas"].values()
                     if same(i["question"], card["question"]) and same(i["hypothesis"], card["hypothesis"])), None)
        if twin:
            raise SystemExit(f"{twin} already has this question and hypothesis. Use revise to change it.")
        words = card["question"].split()
        idea = {"id": f"i{len(ledger['ideas']) + 1}", "version": 1, "state": "open",
                **{name: card.get(name, "") for name in CARD_FIELDS},
                "history": [], "novelty": {"status": "unsearched", "date": "", "note": ""}, "closest": [],
                "gates": {}, "assumptions": [], "ratings": {}, "attacks": [], "study": {}, "rejection": {},
                "recommended_seq": None}
        idea["title"] = idea["title"] or " ".join(words[:8]) + ("…" if len(words) > 8 else "")
        ledger["ideas"][idea["id"]] = idea
        added.append(idea["id"])
    return {"added": added, "ideas": len(ledger["ideas"])}


def cmd_revise(ledger: dict, args) -> dict:
    idea = get_idea(ledger, args.idea)
    changes = {**(clean_card(read_json(args.file)) if args.file else {}), **flag_card(args)}
    changes = {name: value for name, value in changes.items() if value != idea[name]}
    if not changes:
        raise SystemExit("Nothing to change: give a card file or a field that differs from the card.")
    new_version = any(name in changes and not same(changes[name], idea[name]) for name in ("question", "hypothesis"))
    result = {"idea": idea["id"], "changed": sorted(changes), "new_version": new_version}
    if new_version:
        idea["history"].append({"version": idea["version"], "question": idea["question"], "hypothesis": idea["hypothesis"],
                                "novelty": idea["novelty"]["status"], "state": state(ledger, idea),
                                "replaced": args.date, "note": args.note or ""})
        idea["version"] += 1
        idea["novelty"] = {"status": "unsearched", "date": "", "note": ""}
        idea["ratings"].pop("difference", None)
        idea["state"], idea["rejection"], idea["recommended_seq"] = "open", {}, None
        result["search_again"] = (f"The novelty status, the closest works and the difference rating belonged to version "
                                  f"{idea['version'] - 1}. Run the novelty check again for version {idea['version']}.")
    idea.update(changes)
    return {**result, "version": idea["version"], "novelty": idea["novelty"]["status"]}


def cmd_search(ledger: dict, args) -> dict:
    idea = None if args.idea == "base" else get_idea(ledger, args.idea)
    if idea is None and args.intent:
        raise SystemExit("A search of the evidence base (base) takes no --intent.")
    if idea is not None and not args.intent:
        raise SystemExit("A novelty search needs --intent: " + ", ".join(INTENTS))
    if args.intent in NOT_AVAILABLE:
        raise SystemExit(f"Intent {args.intent} is not available: {NOT_AVAILABLE[args.intent]}. "
                         "The ledger records this for every idea; there is nothing to log.")
    if (args.total is None) == (args.failed is None) or (args.total or 0) < 0:
        raise SystemExit('Give --total N (0 or more) for a completed search, or --failed "code: message" '
                         "for one the tool did not answer. A failed search is not zero results.")
    filters = {}
    for item in args.filter or []:
        name, sep, value = item.partition("=")
        if not sep:
            raise SystemExit(f"--filter takes name=value, got {item!r}")
        filters[name.strip()] = value.strip()
    search = {"id": f"s{len(ledger['searches']) + 1}", "idea": idea["id"] if idea else None,
              "version": idea["version"] if idea else None, "date": args.date,
              "intent": args.intent or "evidence_base", "tool": args.tool, "query": args.query,
              "sort": args.sort or "", "filters": filters, "total": args.total,
              "outcome": "ok" if args.failed is None else "failed", "note": tidy(args.failed or args.note or "")}
    ledger["searches"].append(search)
    result = {"search": search["id"], "outcome": search["outcome"]}
    if idea:
        if idea["novelty"]["status"] == "unsearched" and intents_done(ledger, idea):   # searched, nothing concluded yet
            idea["novelty"] = {"status": "inconclusive", "date": args.date, "note": ""}
        result.update({"idea": idea["id"], "version": idea["version"], "novelty": idea["novelty"]["status"],
                       "intents_completed": intents_done(ledger, idea)})
    return result


def cmd_closest(ledger: dict, args) -> dict:
    idea = get_idea(ledger, args.idea)
    data = read_json(args.file)
    if isinstance(data, dict):
        data = data.get("works") or data.get("papers") or data.get("results") or [data]
    known = {work_key(w): w for w in current_closest(idea)}
    if not isinstance(data, list):
        raise SystemExit("closest takes a JSON list of works.")
    if sum(1 for raw in data if isinstance(raw, dict) and raw.get("decisive")) > 1:
        raise SystemExit("Only one closest work is decisive: the one with the largest overlap.")
    for raw in data:
        if not isinstance(raw, dict) or not tidy(raw.get("title") or ""):
            raise SystemExit("Every closest work needs its title, as the tool returned it.")
        if raw.get("read", "metadata") not in READ:
            raise SystemExit(f"read is one of: {', '.join(READ)}. Got {raw['read']!r}.")
        work = known.get(work_key(raw))
        if work is None:
            work = {"version": idea["version"], "read": "metadata", **{name: "" for name in COMPARISON}}
            idea["closest"].append(work)
            known[work_key(raw)] = work
        for name in WORK_FIELDS + ("read",):
            if raw.get(name) not in (None, "", []):
                work[name] = raw[name]
        work.update({name: tidy(raw[name]) for name in COMPARISON if tidy(raw.get(name) or "")})
        if raw.get("decisive"):
            for other in known.values():
                other["decisive"] = other is work
        elif "decisive" in raw:
            work["decisive"] = False
    works = current_closest(idea)
    return {"idea": idea["id"], "version": idea["version"], "closest_works": len(works),
            "read_in_full_text": sum(1 for w in works if w["read"] == "full_text"),
            "decisive": next((f"{work_label(w)} (read: {w['read']})" for w in works if w.get("decisive")), None),
            "incomplete": {work_label(w): [n for n in COMPARISON if not w[n]] for w in works
                           if any(not w[n] for n in COMPARISON)}}


def cmd_novelty(ledger: dict, args) -> dict:
    idea = get_idea(ledger, args.idea)
    gaps = novelty_gaps(ledger, idea, args.status)
    if gaps:
        return {"idea": idea["id"], "version": idea["version"], "novelty": idea["novelty"]["status"],
                "refused": args.status, "missing": gaps}
    idea["novelty"] = {"status": args.status, "date": args.date, "note": tidy(args.note or "")}
    return {"idea": idea["id"], "version": idea["version"], "novelty": args.status, "means": NOVELTY[args.status],
            "intents_completed": intents_done(ledger, idea), "not_available": NOT_AVAILABLE}


def cmd_gate(ledger: dict, args) -> dict:
    idea = get_idea(ledger, args.idea)
    for name, value in pairs(args.items, GATES, "gate").items():
        status, _, note = value.partition(":")
        if status not in GATE_STATUS:
            raise SystemExit(f"A gate is one of: {', '.join(GATE_STATUS)}. Got {name}={status!r}.")
        if status == "blocked" and not tidy(note):
            raise SystemExit(f'A blocked gate says what blocks it: {name}=blocked:"…"')
        idea["gates"][name] = {"status": status, "note": tidy(note)}
    return {"idea": idea["id"], "gates": {g: idea["gates"][g]["status"] for g in GATES if g in idea["gates"]},
            "not_assessed": [g for g in GATES if g not in idea["gates"]]}


def cmd_assume(ledger: dict, args) -> dict:
    idea = get_idea(ledger, args.idea)
    if not tidy(args.text) or args.months < 0:
        raise SystemExit("An assumption needs --text and --months of 0 or more.")
    entry = {"text": tidy(args.text), "risk": args.risk, "months": args.months, "test": tidy(args.test or "")}
    idea["assumptions"] = [a for a in idea["assumptions"] if not same(a["text"], entry["text"])] + [entry]
    return {"idea": idea["id"], "assumptions": len(idea["assumptions"]), "cannot_be_tested_early": late_risk(ledger, idea)}


def cmd_rate(ledger: dict, args) -> dict:
    idea = get_idea(ledger, args.idea)
    not_assessed = [g for g in GATES if g not in idea["gates"]]
    if not_assessed:
        raise SystemExit(f"Gates come before ratings. Not assessed yet: {', '.join(not_assessed)}.")
    blocked = [g for g in GATES if idea["gates"][g]["status"] == "blocked"]
    for name, value in pairs(args.items, DIMENSIONS, "rate").items():
        score, _, reason = value.partition(":")
        if score not in ("0", "1", "2", "3") or not tidy(reason):
            raise SystemExit(f'{name} takes a score from 0 to 3 and a reason: {name}=2:"…". Got {value!r}.')
        if name == "difference" and not current_closest(idea):
            raise SystemExit("difference is judged against the closest works, and none is recorded. Run the novelty "
                             f"check for version {idea['version']} first.")
        if name == "feasibility" and score != "0" and blocked:
            raise SystemExit(f"feasibility is 0 while a gate is blocked ({', '.join(blocked)}).")
        idea["ratings"][name] = {"score": int(score), "reason": tidy(reason)}
    return {"idea": idea["id"], "ratings": {d: idea["ratings"][d]["score"] for d in DIMENSIONS if d in idea["ratings"]},
            "not_rated": [d for d in DIMENSIONS if d not in idea["ratings"]]}


def cmd_attack(ledger: dict, args) -> dict:
    idea = get_idea(ledger, args.idea)
    entry = {name: tidy(getattr(args, name)) for name in ATTACK_FIELDS}
    empty = [name for name, value in entry.items() if not value]
    if empty:
        raise SystemExit(f'An attack needs: {", ".join(empty)}. Write "none" when nothing was changed or nothing remains.')
    idea["attacks"].append({"version": idea["version"], **entry})
    return {"idea": idea["id"], "attacks": len(idea["attacks"])}


def cmd_study(ledger: dict, args) -> dict:
    idea = get_idea(ledger, args.idea)
    names = tuple(name for name, _ in STUDY_FIELDS)
    if len(args.items) == 1 and "=" not in args.items[0]:
        fields = read_json(args.items[0])
        if not isinstance(fields, dict) or any(name not in names for name in fields):
            raise SystemExit("A first study is a JSON object with the fields: " + ", ".join(names))
    else:
        fields = pairs(args.items, names, "study")
    idea["study"].update({name: tidy(value) for name, value in fields.items() if tidy(value)})
    return {"idea": idea["id"], "study": idea["study"], "not_set": [n for n in names if not idea["study"].get(n)]}


def cmd_recommend(ledger: dict, args) -> dict:
    idea = get_idea(ledger, args.idea)
    gaps = recommendation_gaps(ledger, idea)
    if gaps:
        return {"idea": idea["id"], "version": idea["version"], "recommended": False, "missing": gaps}
    if idea["state"] != "recommended":
        idea["recommended_seq"] = 1 + max((i["recommended_seq"] or 0 for i in ledger["ideas"].values()), default=0)
    idea["state"], idea["rejection"] = "recommended", {}
    return {"idea": idea["id"], "version": idea["version"], "recommended": True, "open_points": open_points(ledger, idea)}


def cmd_reject(ledger: dict, args) -> dict:
    idea = get_idea(ledger, args.idea)
    if not tidy(args.reason) or not tidy(args.restart_if):
        raise SystemExit("A rejection needs --reason and --restart-if: what would make the idea worth reopening.")
    idea["state"], idea["recommended_seq"] = "rejected", None
    idea["rejection"] = {"reason": tidy(args.reason), "restart_if": tidy(args.restart_if), "version": idea["version"]}
    return {"idea": idea["id"], "state": "rejected", "restart_if": idea["rejection"]["restart_if"]}


def standing(ledger: dict, idea: dict) -> dict:
    works, done = current_closest(idea), intents_done(ledger, idea)
    out = {"id": idea["id"], "title": idea["title"], "version": idea["version"], "state": state(ledger, idea),
           "novelty": idea["novelty"]["status"], "intents_completed": done,
           "intents_not_completed": [i for i in INTENTS if i not in done], "intents_not_available": list(NOT_AVAILABLE),
           "closest_works": len(works), "read_in_full_text": sum(1 for w in works if w["read"] == "full_text"),
           "decisive_work_read": next((w["read"] for w in works if w.get("decisive")), "none marked"),
           "gates": {g: idea["gates"].get(g, {}).get("status", "not_assessed") for g in GATES},
           "ratings": {d: idea["ratings"][d]["score"] if d in idea["ratings"] else None for d in DIMENSIONS}}
    if out["state"] == "rejected":
        return {**out, "rejected_because": idea["rejection"]["reason"], "restart_if": idea["rejection"]["restart_if"]}
    return {**out, "missing_for_recommendation": recommendation_gaps(ledger, idea), "open_points": open_points(ledger, idea)}


def grouped(ledger: dict) -> dict:
    ideas = list(ledger["ideas"].values())
    groups = {name: [i for i in ideas if state(ledger, i) == name] for name in ("recommended", "open", "rejected")}
    groups["recommended"].sort(key=lambda i: i["recommended_seq"] or 0)
    return groups


def cmd_status(ledger: dict, args) -> dict:
    groups = grouped(ledger)
    return {"ideas": len(ledger["ideas"]), **{name: [i["id"] for i in ideas] for name, ideas in groups.items()},
            "no_candidate_qualifies": bool(ledger["ideas"]) and not groups["recommended"],
            "evidence_base_searches": sum(1 for s in ledger["searches"] if s["idea"] is None),
            "detail": [standing(ledger, idea) for ideas in groups.values() for idea in ideas]}


# ---------------------------------------------------------------------------------------------
# Export


def cell(value) -> str:
    return tidy("" if value is None else value).replace("|", "/") or "—"


def table(header: tuple, rows: list) -> list:
    return (["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
            + ["| " + " | ".join(cell(value) for value in row) + " |" for row in rows])


def work_link(work: dict) -> str:
    return f"[{work_label(work)}]({work['readerUrl']})" if work.get("readerUrl") else work_label(work)


def closest_table(works: list) -> list:
    return table(("Closest work", "What it solved", "Overlap", "Remaining difference", "Why the difference matters", "Read"),
                 [(work_link(w), *(w[name] for name in COMPARISON),
                   w["read"].replace("_", " ") + (", decisive" if w.get("decisive") else "")
                   + ("" if w.get("corpusId") not in (None, "") else ", not from the index"))
                  for w in works])


def search_table(searches: list, for_idea: bool = True) -> list:
    header = ("Search", "Date", "Version", "Intent", "Tool", "Query", "Sort", "Filters", "Results reported", "Outcome")
    rows = [(s["id"], s["date"], s["version"], s["intent"], s["tool"], f"`{s['query']}`",
             s["sort"] or ("relevance" if s["tool"] == "search_papers" else ""),
             ", ".join(f"{k}={v}" for k, v in s["filters"].items()), s["total"],
             ("completed" if s["outcome"] == "ok" else "failed, not zero results") + (f": {s['note']}" if s["note"] else ""))
            for s in searches]
    if not for_idea:   # a search of the evidence base has no idea version and no intent
        header, rows = header[:2] + header[4:], [row[:2] + row[4:] for row in rows]
    return table(header, rows)


def novelty_sentence(ledger: dict, idea: dict) -> str:
    novelty, done = idea["novelty"], intents_done(ledger, idea)
    return (f"Novelty of version {idea['version']}: **{NOVELTY[novelty['status']]}**"
            + (f" (set {novelty['date']})" if novelty["date"] else "") + ". "
            + f"Intents with a completed search: {', '.join(done) or 'none'}. "
            + f"No completed search: {', '.join(i for i in INTENTS if i not in done) or 'none'}. "
            + "Not available: " + "; ".join(f"{name} ({why})" for name, why in NOT_AVAILABLE.items()) + "."
            + (f" {novelty['note']}" if novelty["note"] else ""))


def render_idea(ledger: dict, idea: dict) -> list:
    lines = [f"### {idea['id']} · {idea['title']} (version {idea['version']})", ""]
    current, gaps, points = state(ledger, idea), recommendation_gaps(ledger, idea), open_points(ledger, idea)
    if current == "rejected":
        lines += [f"Rejected: {idea['rejection']['reason'].rstrip('.')}. "
                  f"Restart if: {idea['rejection']['restart_if'].rstrip('.')}.", ""]
    else:
        verdict = "Recommended."
        if current == "open":
            verdict = "The earlier recommendation no longer holds. " if idea["state"] == "recommended" else ""
            verdict += (f"Not recommended: {'; '.join(gaps)}." if gaps
                        else "Not recommended yet: the checks are met and no recommendation has been recorded.")
        lines += [verdict + (f" Still open: {'; '.join(points)}." if points else ""), ""]
    if idea["origin"]:
        lines += [f"Origin: {idea['origin']}", ""]
    lines += table(("Card", "Content"), [(label, idea[name]) for name, label in CARD_LABELS]) + [""]
    lines += [novelty_sentence(ledger, idea), ""]
    if current_closest(idea):
        lines += closest_table(current_closest(idea)) + [""]
    if idea["gates"]:
        lines += ["Gates: " + "; ".join(f"{g} {idea['gates'][g]['status']}" + (f" ({idea['gates'][g]['note']})" if idea["gates"][g]["note"] else "")
                                        for g in GATES if g in idea["gates"]) + ".", ""]
    if idea["assumptions"]:
        rows = sorted(idea["assumptions"], key=lambda a: (-a["risk"], -a["months"]))
        lines += table(("Assumption", "Risk (1–5)", "Months to test", "How it would be tested"),
                       [(a["text"], a["risk"], f"{a['months']:g}", a["test"]) for a in rows]) + [""]
    if idea["ratings"]:
        lines += table(("Dimension", "Rating (0–3)", "Reason"),
                       [(d.replace("_", " "), *((r["score"], r["reason"]) if (r := idea["ratings"].get(d)) else ("not rated", "")))
                        for d in DIMENSIONS]) + [""]
    if idea["attacks"]:
        lines += table(("Attack", "Basis", "Change made", "What remains"),
                       [tuple(a[name] for name in ATTACK_FIELDS) for a in idea["attacks"]]) + [""]
    if idea["study"]:
        lines += ["Minimum first study:", ""]
        lines += [f"- {label}: {idea['study'][name]}" for name, label in STUDY_FIELDS if idea["study"].get(name)] + [""]
    return lines


def cmd_export(ledger: dict, args) -> dict:
    directory = Path(args.dir)
    directory.mkdir(parents=True, exist_ok=True)
    groups, brief = grouped(ledger), ledger["brief"]
    months = f"{brief['months']:g} months" if brief.get("months") else ""
    about = [f"{label}: {value}" for label, value in (
        ("Field", brief["field"]), ("Question type", brief["question_type"]), ("Data", brief["data"]),
        ("Equipment", brief["equipment"]), ("Time", months), ("Skills", brief["skills"]), ("Note", brief["note"])) if value]
    lines = ["# Research ideas", ""] + (["; ".join(about) + ".", ""] if about else [])
    lines += [f"{len(ledger['ideas'])} idea{'' if len(ledger['ideas']) == 1 else 's'}: "
              f"{len(groups['recommended'])} recommended, {len(groups['open'])} open, "
              f"{len(groups['rejected'])} rejected. Each idea is rated 0–3 on five separate dimensions; the ratings are "
              "not added up, and the order below is not a ranking by score. Searches are in [novelty-log.md](novelty-log.md).", ""]
    if ledger["ideas"] and not groups["recommended"]:
        lines += ["**No candidate qualifies for a recommendation.** What each open idea lacks is listed under it.", ""]
    for name, ideas in groups.items():
        if ideas:
            lines += [f"## {name.capitalize()}", ""]
            for idea in ideas:
                lines += render_idea(ledger, idea)
    (directory / "ideas.md").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")

    log = ["# Novelty log", "",
           "Every search is bound to the version of the idea it was run for. \"Differentiated\" means only that the "
           "searches logged here found no work that already covers the idea. Not available for any idea: "
           + "; ".join(f"`{name}` ({why})" for name, why in NOT_AVAILABLE.items()) + ".", ""]
    base = [s for s in ledger["searches"] if s["idea"] is None]
    if base:
        log += ["## Evidence base", ""] + search_table(base, for_idea=False) + [""]
    for idea in ledger["ideas"].values():
        log += [f"## {idea['id']} · {idea['title']}", "", novelty_sentence(ledger, idea), ""]
        searches = [s for s in ledger["searches"] if s["idea"] == idea["id"]]
        log += (search_table(searches) if searches else ["No search is logged for this idea."]) + [""]
        if current_closest(idea):
            log += [f"Closest works for version {idea['version']}:", ""] + closest_table(current_closest(idea)) + [""]
        for old in idea["history"]:
            log += [f"- Version {old['version']}, replaced {old['replaced']} (novelty then: {NOVELTY[old['novelty']]}). "
                    f"Question: {old['question']} Hypothesis: {old['hypothesis']}"
                    + (f" Note: {old['note']}" if old["note"] else "")]
        log += [""] if idea["history"] else []
    (directory / "novelty-log.md").write_text("\n".join(log).rstrip() + "\n", encoding="utf-8")
    return {**{name: len(ideas) for name, ideas in groups.items()},
            "no_candidate_qualifies": bool(ledger["ideas"]) and not groups["recommended"],
            "files": [str(directory / "ideas.md"), str(directory / "novelty-log.md")]}


def iso_date(text: str) -> str:
    try:
        return datetime.date.fromisoformat(text).isoformat()
    except ValueError:
        raise argparse.ArgumentTypeError(f"{text!r} is not a date like 2026-01-31")


def card_flags(parser) -> None:
    for name in CARD_FIELDS:
        parser.add_argument("--" + name.replace("_", "-"), dest=name, choices=CLAIM_TYPES if name == "claim_type" else None)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="The ledger of a set of research ideas.")
    parser.add_argument("--dir", default="ideas", help="The ideas folder (default: ideas)")
    parser.add_argument("--date", type=iso_date, default=datetime.date.today().isoformat(),
                        help="The date to record, YYYY-MM-DD (default: today)")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("brief", help="Record the field, the kind of question and the researcher's constraints")
    p.add_argument("--field")
    p.add_argument("--question-type", dest="question_type")
    p.add_argument("--data", help="Data the researcher holds or can get")
    p.add_argument("--equipment", help="Instruments, compute, lab or field access")
    p.add_argument("--months", type=float, help="Months available for the project")
    p.add_argument("--skills")
    p.add_argument("--note")

    p = sub.add_parser("add", help="Add idea cards: a JSON file (one card or a list), or one card from flags")
    p.add_argument("file", nargs="?")
    card_flags(p)

    p = sub.add_parser("revise", help="Change a card; a changed question or hypothesis starts a new version")
    p.add_argument("idea")
    p.add_argument("file", nargs="?")
    card_flags(p)
    p.add_argument("--note", help="Why the idea was changed")

    p = sub.add_parser("search", help="Log one search: for an idea's current version, or for the evidence base")
    p.add_argument("idea", help="An idea id, or base for a search made before any idea")
    p.add_argument("--intent", choices=INTENTS + tuple(NOT_AVAILABLE))
    p.add_argument("--query", required=True)
    p.add_argument("--total", type=int, help="How many results the tool reported in all")
    p.add_argument("--failed", help="The tool's error (code and message) when the search did not complete")
    p.add_argument("--sort", choices=SORTS)
    p.add_argument("--filter", action="append", help="name=value, e.g. yearFrom=2023 (repeatable)")
    p.add_argument("--tool", choices=TOOLS, default="search_papers")
    p.add_argument("--note")

    p = sub.add_parser("closest", help="Record the closest works of an idea's current version (a JSON file, or -)")
    p.add_argument("idea")
    p.add_argument("file")

    p = sub.add_parser("novelty", help="Set the novelty status of an idea's current version")
    p.add_argument("idea")
    p.add_argument("--status", required=True, choices=tuple(NOVELTY))
    p.add_argument("--note")

    p = sub.add_parser("gate", help='Record gates: name=status or name=status:"note"')
    p.add_argument("idea")
    p.add_argument("items", nargs="+", help=f"{'|'.join(GATES)} = {'|'.join(GATE_STATUS)}")

    p = sub.add_parser("assume", help="Record one assumption with its risk and the months needed to test it")
    p.add_argument("idea")
    p.add_argument("--text", required=True)
    p.add_argument("--risk", required=True, type=int, choices=range(1, 6), help="1 (established) to 5 (a long shot)")
    p.add_argument("--months", required=True, type=float, help="Months until a result that tests it")
    p.add_argument("--test", help="How it would be tested")

    p = sub.add_parser("rate", help='Rate dimensions 0–3, each with a reason: name=2:"reason"')
    p.add_argument("idea")
    p.add_argument("items", nargs="+", help="|".join(DIMENSIONS))

    p = sub.add_parser("attack", help="Record one objection and what became of it")
    p.add_argument("idea")
    for name in ATTACK_FIELDS:
        p.add_argument("--" + name, required=True)

    p = sub.add_parser("study", help="Record the minimum first study: name=value …, or a JSON file")
    p.add_argument("idea")
    p.add_argument("items", nargs="+", help="|".join(name for name, _ in STUDY_FIELDS))

    p = sub.add_parser("recommend", help="Mark an idea recommended, if the record supports it")
    p.add_argument("idea")

    p = sub.add_parser("reject", help="Reject an idea and keep it, with what would reopen it")
    p.add_argument("idea")
    p.add_argument("--reason", required=True)
    p.add_argument("--restart-if", dest="restart_if", required=True)

    sub.add_parser("status", help="Where every idea stands and what it lacks")
    sub.add_parser("export", help="Write ideas.md and novelty-log.md")

    args = parser.parse_args(argv)
    directory = Path(args.dir)
    ledger = load(directory)
    result = globals()[f"cmd_{args.command}"](ledger, args)
    if args.command not in ("status", "export"):
        save(directory, ledger)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 1 if result.get("missing") else 0


if __name__ == "__main__":
    sys.exit(main())
