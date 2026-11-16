"""A small, wholly fictional review for the tests: an invented three-domain tool and three invented
trials. No sentence comes from a real paper and no item from a real tool."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

FILLER = " ".join(f"Paragraph {i} of the methods describes the schedule of the study visits in detail." for i in range(45))

TEXTS = {
    "alder2021": (
        "[[page 1]]\nEvening meal timing and body weight: a fictional randomised trial.\n" + FILLER + "\n"
        "[[page 2]]\nParticipants were allocated by a computer-generated list held by an independent statistician "
        "who had no contact with participants. The allocation sequence was concealed in sequentially numbered "
        "opaque envelopes opened after consent.\nOutcome assessors who weighed participants were not told the "
        "group assign-\nment at any visit. Of 120 randomised participants, 9 did not attend the final visit.\n"),
    "birch2022": (
        "[[page 1]]\nA fictional pilot trial of an early eating window.\n" + FILLER + "\n"
        "[[page 2]]\nAssignment followed a random number table prepared before recruitment began.\nBody weight "
        "was measured on a calibrated scale by research nurses who did not know the allocation.\nAll 60 "
        "participants completed the twelve week follow up and were analysed.\n"),
    "cedar2023": (
        "[[page 1]]\nTime-restricted eating in shift workers: a fictional trial.\n" + FILLER + "\n"
        "[[page 4]]\nA web-based system generated the allocation sequence and revealed each assignment only after "
        "enrolment was complete.\nParticipants reported their own body weight at home with 17\nscales of "
        "their own choosing, and knew which group they were in.\n"),
}

TOOL = {
    "id": "demo", "name": "Demo appraisal tool (fictional)", "version": "0.1",
    "designs": ["parallel randomised trials"],
    "source": {"file": "tool-source/demo-tool.txt", "read": "2026-11-13"},
    "transcribed_by": "model",
    "answers": ["Y", "PY", "PN", "N", "NI", "NA"],
    "judgements": [{"id": "low", "label": "Low"}, {"id": "some", "label": "Some concerns"},
                   {"id": "high", "label": "High"}, {"id": "ni", "label": "No information", "no_information": True}],
    "domains": [{"id": "D1", "name": "Assignment", "questions": ["1a", "1b"]},
                {"id": "D2", "name": "Missing outcome data", "questions": ["2a"]},
                {"id": "D3", "name": "Outcome measurement", "questions": [{"id": "3a"}]}],
    "overall": {"rule": "worst_or_higher", "locator": "guide p. 2"},
    "mapping": {"D1": {"locator": "guide p. 3", "rules": [
        {"if": {"1b": ["N", "PN"]}, "then": "high"},
        {"if": {"1a": ["Y", "PY"], "1b": ["Y", "PY"]}, "then": "low"},
        {"if": {}, "then": "some"}]}},
}


def quote(text, locator, **more):
    return {"quote": text, "locator": locator, **more}


def result(domains, overall, **more):
    return {"outcome": "weight", "result": "body weight at 12 weeks, kg",
            "target": "effect of assignment to the intervention (intention to treat)",
            "assessor": "model", "checked_by": "", "domains": domains, "overall": overall, **more}


ASSESSMENTS = {"assessments": [
    {"study": "alder2021", "texts": [{"path": "texts/alder2021.txt", "kind": "full_text"}], "results": [result({
        "D1": {"answers": {"1a": "Y", "1b": "Y"}, "judgement": "low", "support": [
            quote("allocated by a computer-generated list held by an independent statistician", "p. 2, Methods"),
            quote("concealed in sequentially numbered opaque envelopes opened after consent", "p. 2, Methods")]},
        "D2": {"answers": {"2a": "Y"}, "judgement": "low", "support": [
            quote("Of 120 randomised participants, 9 did not attend the final visit", "p. 2, Results")]},
        "D3": {"answers": {"3a": "Y"}, "judgement": "low", "support": [
            quote("Outcome assessors who weighed participants were not told the group assignment", "p. 2")]},
    }, {"judgement": "low"}, weight=40.0)]},
    {"study": "birch2022", "texts": [{"path": "texts/birch2022.txt", "kind": "full_text"}], "results": [result({
        "D1": {"answers": {"1a": "Y", "1b": "NI"}, "judgement": "some",
               "support": [quote("Assignment followed a random number table prepared before recruitment", "p. 2")],
               "no_information": {"searched": "Methods, supplementary appendix and the trial registration"}},
        "D2": {"answers": {"2a": "Y"}, "judgement": "low", "support": [
            quote("All 60 participants completed the twelve week follow up", "p. 2")]},
        "D3": {"answers": {"3a": "Y"}, "judgement": "low", "support": [
            quote("research nurses who did not know the allocation", "p. 2")]},
    }, {"judgement": "some"}, weight=25.0)]},
    {"study": "cedar2023", "texts": [{"path": "texts/cedar2023.txt", "kind": "full_text"}], "results": [result({
        "D1": {"answers": {"1a": "Y", "1b": "Y"}, "judgement": "low", "support": [
            quote("revealed each assignment only after enrolment was complete", "p. 4")]},
        "D2": {"answers": {"2a": "NI"}, "judgement": "ni",
               "no_information": {"searched": "Results, flow diagram, tables 1-3 and the supplement"}},
        "D3": {"answers": {"3a": "N"}, "judgement": "high", "support": [
            quote("Participants reported their own body weight at home with scales of their own choosing", "p. 4")]},
    }, {"judgement": "high"}, weight=35.0)]},
]}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(directory: Path, tool=None, assessments=None, hashes: bool = True) -> Path:
    """Write the review into directory/risk-of-bias and return that folder. Hashes are recorded
    from the files as written, unless hashes is False."""
    base = directory / "risk-of-bias"
    (base / "texts").mkdir(parents=True, exist_ok=True)
    (base / "tool-source").mkdir(exist_ok=True)
    (base / "tool-source" / "demo-tool.txt").write_text("Demo appraisal tool, version 0.1 (fictional).\n",
                                                        encoding="utf-8")
    for study, text in TEXTS.items():
        (base / "texts" / f"{study}.txt").write_text(text, encoding="utf-8")
    tool = copy.deepcopy(TOOL if tool is None else tool)
    assessments = copy.deepcopy(ASSESSMENTS if assessments is None else assessments)
    if hashes:
        if tool.get("source", {}).get("file"):
            tool["source"].setdefault("sha256", sha(base / tool["source"]["file"]))
        for study in assessments["assessments"]:
            for text in study.get("texts", []):
                if (base / text["path"]).is_file():
                    text.setdefault("sha256", sha(base / text["path"]))
    (base / "tool.json").write_text(json.dumps(tool, indent=2), encoding="utf-8")
    (base / "assessments.json").write_text(json.dumps(assessments, indent=2), encoding="utf-8")
    return base
