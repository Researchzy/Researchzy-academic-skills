"""Fictional trials for the tests, in the shape ClinicalTrials.gov API v2 returns. The NCT numbers are
outside the range the registry has issued, and no text comes from a real record or paper.

NCT99123456 is a knee osteoarthritis trial; NCT99123546 (two digits swapped) is a diabetes trial."""
from __future__ import annotations

import copy
import json
from pathlib import Path

NCT, SWAPPED = "NCT99123456", "NCT99123546"
SECONDARY = [
    {"measure": "WOMAC physical function subscale", "description": "WOMAC physical function subscale, 0 to 68",
     "timeFrame": "26 weeks"},
    {"measure": "Timed Up and Go test", "description": "Seconds to rise, walk 3 metres and sit down", "timeFrame": "12 weeks"},
    {"measure": "Adverse events", "description": "Number of participants with an adverse event", "timeFrame": "26 weeks"}]


def record(count=200, kind="ESTIMATED", last="2025-09-02", start="2020-02-03", secondary=None) -> dict:
    return {"protocolSection": {
        "identificationModule": {
            "nctId": NCT, "briefTitle": "Supervised Exercise for Knee Osteoarthritis",
            "officialTitle": "Supervised Exercise Versus Usual Care for Knee Osteoarthritis: a Randomised Controlled Trial (SEKO)",
            "acronym": "SEKO", "secondaryIdInfos": [{"id": "2019-004567-12", "type": "EUDRACT_NUMBER"}]},
        "statusModule": {
            "overallStatus": "COMPLETED", "startDateStruct": {"date": start, "type": "ACTUAL"},
            "primaryCompletionDateStruct": {"date": "2021-06-30", "type": "ACTUAL"}, "studyFirstSubmitDate": "2020-05-11",
            "studyFirstPostDateStruct": {"date": "2020-05-14", "type": "ACTUAL"},
            "lastUpdatePostDateStruct": {"date": last, "type": "ACTUAL"}},
        "sponsorCollaboratorsModule": {"leadSponsor": {"name": "Lakeside University Hospital", "class": "OTHER"}},
        "conditionsModule": {"conditions": ["Knee Osteoarthritis"], "keywords": ["exercise therapy"]},
        "designModule": {"studyType": "INTERVENTIONAL", "enrollmentInfo": {"count": count, "type": kind}},
        "armsInterventionsModule": {
            "armGroups": [{"label": "Supervised exercise", "type": "EXPERIMENTAL"}, {"label": "Usual care", "type": "OTHER"}],
            "interventions": [
                {"type": "BEHAVIORAL", "name": "Supervised exercise",
                 "description": "Physiotherapist-supervised strengthening exercise, two 45-minute sessions a week for 12 weeks"},
                {"type": "OTHER", "name": "Usual care", "description": "Advice and pain relief from the general practitioner"}]},
        "outcomesModule": {
            "primaryOutcomes": [{"measure": "WOMAC pain subscale", "timeFrame": "12 weeks",
                                 "description": "Western Ontario and McMaster Universities Osteoarthritis Index, pain subscale, 0 to 20"}],
            "secondaryOutcomes": copy.deepcopy(SECONDARY if secondary is None else secondary)}},
        "derivedSection": {}, "hasResults": False}


def other_trial() -> dict:
    """The record the swapped number leads to."""
    return {"protocolSection": {
        "identificationModule": {"nctId": SWAPPED, "briefTitle": "Once-Weekly Semaglutide in Adults With Type 2 Diabetes"},
        "statusModule": {"overallStatus": "COMPLETED", "startDateStruct": {"date": "2019-04-01", "type": "ACTUAL"},
                         "studyFirstSubmitDate": "2019-03-02", "lastUpdatePostDateStruct": {"date": "2023-01-10", "type": "ACTUAL"}},
        "sponsorCollaboratorsModule": {"leadSponsor": {"name": "Example Pharma"}},
        "conditionsModule": {"conditions": ["Type 2 Diabetes"]},
        "designModule": {"enrollmentInfo": {"count": 480, "type": "ACTUAL"}},
        "armsInterventionsModule": {"interventions": [{"type": "DRUG", "name": "Semaglutide"}, {"type": "DRUG", "name": "Placebo"}]},
        "outcomesModule": {"primaryOutcomes": [{"measure": "Change in HbA1c", "timeFrame": "26 weeks"}]}}, "hasResults": True}


PAPER = (
    "Supervised exercise versus usual care for knee osteoarthritis: a randomised controlled trial\n"
    "Published online 14 March 2025\n"
    "Trial registration: ClinicalTrials.gov NCT99123456; EudraCT 2019-004567-12. The trial was prospectively registered.\n"
    "Funding: Lakeside University Hospital research fund.\n"
    "\f"
    "Methods. Adults with knee osteoarthritis were recruited from general practices. Participants in the intervention\n"
    "group attended supervised exercise, two 45-minute sessions a week for 12 weeks.\n"
    "We planned to recruit 200 participants. Between 3 February 2020 and 30 June 2021, 150 participants were randomised.\n"
    "The primary outcome was knee function (WOMAC physical function subscale) at 26 weeks. Secondary outcomes were\n"
    "Pain (WOMAC) at week 12, quality of life (EQ-5D-5L) at 26 weeks and adverse events up to 26 weeks.\n"
    "\f"
    "Discussion. Before unblinding, the steering committee made knee function at 26 weeks the primary outcome.\n")

PAPER_ZH = (
    "监督下运动与常规治疗对膝骨关节炎疗效的随机对照试验\n"
    "2025年3月14日在线发表\n"
    "临床试验注册：ClinicalTrials.gov，NCT99123456。本试验为前瞻性注册。\n"
    "\f"
    "方法：纳入膝骨关节炎患者。干预组接受监督下运动，每周2次，每次45分钟，共12周。\n"
    "计划样本量为200例。2020年2月3日至2021年6月30日共随机分配１５０例患者（干预组７５例，对照组７５例）。\n"
    "主要结局指标为第12周WOMAC疼痛评分；次要结局指标为第26周WOMAC功能评分。\n")

SEARCHED = {"searched": "Methods, Discussion and the supplement"}
ITEMS = {
    "paper": {"text": "paper.txt", "published": {"date": "2025-03-14", "quote": "Published online 14 March 2025", "locator": "p. 1"}},
    "record": {"file": f"record-{NCT}.json", "read": "2026-11-18"},
    "registrations": [
        {"registry": "ClinicalTrials.gov", "id": NCT, "quote": f"ClinicalTrials.gov {NCT}", "locator": "p. 1"},
        {"registry": "EudraCT", "id": "2019-004567-12", "quote": "EudraCT 2019-004567-12", "locator": "p. 1"}],
    "identity": {
        "title": {"quote": "Supervised exercise versus usual care for knee osteoarthritis", "locator": "p. 1, title"},
        "condition": {"quote": "Adults with knee osteoarthritis were recruited", "locator": "p. 2, Methods"},
        "intervention": {"quote": "attended supervised exercise", "locator": "p. 2, Methods"},
        "sponsor": {"quote": "Lakeside University Hospital research fund", "locator": "p. 1, Funding"}},
    "items": [
        {"id": "O1", "kind": "outcome", "role": "primary", "locator": "p. 2, Methods", "disclosure": SEARCHED,
         "quote": "The primary outcome was knee function (WOMAC physical function subscale) at 26 weeks",
         "record": "protocolSection.outcomesModule.secondaryOutcomes[0]"},
        {"id": "O2", "kind": "outcome", "role": "secondary", "quote": "Pain (WOMAC) at week 12", "locator": "p. 2, Methods",
         "record": "protocolSection.outcomesModule.primaryOutcomes[0]", "disclosure": SEARCHED},
        {"id": "O3", "kind": "outcome", "role": "secondary", "quote": "quality of life (EQ-5D-5L) at 26 weeks",
         "locator": "p. 2, Methods", "record": None, "disclosure": SEARCHED},
        {"id": "O4", "kind": "outcome", "role": "secondary", "quote": "adverse events up to 26 weeks", "locator": "p. 2, Methods",
         "record": "protocolSection.outcomesModule.secondaryOutcomes[2]"},
        {"id": "N1", "kind": "enrollment", "basis": "planned", "value": 200, "quote": "We planned to recruit 200 participants",
         "locator": "p. 2, Methods"},
        {"id": "N2", "kind": "enrollment", "basis": "actual", "value": 150, "quote": "150 participants were randomised",
         "locator": "p. 2, Methods"},
        {"id": "D1", "kind": "date", "date": "2020-02-03", "record": "protocolSection.statusModule.startDateStruct", "quote": "Between 3 February 2020 and 30 June 2021",
         "locator": "p. 2, Methods"},
        {"id": "R1", "kind": "registration_claim", "claim": "prospective", "quote": "The trial was prospectively registered",
         "locator": "p. 1"},
        {"id": "I1", "kind": "intervention", "quote": "supervised exercise, two 45-minute sessions a week for 12 weeks",
         "locator": "p. 2, Methods", "record": "protocolSection.armsInterventionsModule.interventions[0]"}],
    "unreported": [{"record": "protocolSection.outcomesModule.secondaryOutcomes[1]",
                    "searched": "Results, Tables 2 and 3, the supplement"}]}

ITEMS_ZH = {
    "paper": {"text": "paper.txt", "published": {"date": "2025-03-14", "quote": "2025年3月14日在线发表", "locator": "第1页"}},
    "record": {"file": f"record-{NCT}.json", "read": "2026-11-18"},
    "registrations": [{"registry": "ClinicalTrials.gov", "id": NCT, "quote": f"ClinicalTrials.gov，{NCT}", "locator": "第1页"}],
    "identity": {
        "title": {"quote": "监督下运动与常规治疗对膝骨关节炎疗效", "locator": "第1页",
                  "translation": "Supervised exercise versus usual care for knee osteoarthritis"},
        "condition": {"quote": "纳入膝骨关节炎患者", "locator": "第2页", "translation": "knee osteoarthritis"},
        "intervention": {"quote": "干预组接受监督下运动", "locator": "第2页", "translation": "supervised exercise"}},
    "items": [
        {"id": "O1", "kind": "outcome", "role": "primary", "quote": "主要结局指标为第12周WOMAC疼痛评分", "locator": "第2页",
         "translation": "The primary outcome was the WOMAC pain score at week 12",
         "record": "protocolSection.outcomesModule.primaryOutcomes[0]"},
        {"id": "O2", "kind": "outcome", "role": "secondary", "quote": "次要结局指标为第26周WOMAC功能评分", "locator": "第2页",
         "translation": "A secondary outcome was the WOMAC function score at week 26",
         "record": "protocolSection.outcomesModule.secondaryOutcomes[0]"},
        {"id": "N1", "kind": "enrollment", "basis": "planned", "value": 200, "quote": "计划样本量为200例", "locator": "第2页"},
        {"id": "N2", "kind": "enrollment", "basis": "actual", "value": 150, "quote": "共随机分配１５０例患者", "locator": "第2页"},
        {"id": "D1", "kind": "date", "date": "2020-02-03", "record": "protocolSection.statusModule.startDateStruct", "quote": "2020年2月3日至2021年6月30日", "locator": "第2页"},
        {"id": "R1", "kind": "registration_claim", "claim": "prospective", "quote": "本试验为前瞻性注册", "locator": "第1页"}],
    "unreported": [{"record": f"protocolSection.outcomesModule.secondaryOutcomes[{i}]", "searched": "结果与表2"} for i in (1, 2)]}


def study(nct, title, status, start, results, enrolment, conditions, interventions) -> dict:
    return {"protocolSection": {
        "identificationModule": {"nctId": nct, "briefTitle": title},
        "statusModule": {"overallStatus": status, "startDateStruct": {"date": start[0], "type": start[1]},
                         "primaryCompletionDateStruct": {"date": "2027-12", "type": "ESTIMATED"}},
        "designModule": {"enrollmentInfo": {"count": enrolment[0], "type": enrolment[1]}},
        "conditionsModule": {"conditions": conditions},
        "armsInterventionsModule": {"interventions": [{"type": "BEHAVIORAL", "name": n} for n in interventions]}},
        "derivedSection": {}, "hasResults": results}


TRIALS = [study("NCT99000101", "Supervised Exercise in Knee Osteoarthritis", "COMPLETED", ("2015-03-01", "ACTUAL"), True,
                (120, "ACTUAL"), ["Knee Osteoarthritis"], ["Supervised exercise", "Usual care"]),
          study("NCT99000102", "Aquatic Exercise for Knee Pain", "WITHDRAWN", ("2021-01", "ESTIMATED"), False,
                (0, "ACTUAL"), ["Osteoarthritis, Knee"], ["Aquatic exercise"]),
          study("NCT99000103", "Group Exercise and Education for Knee Osteoarthritis", "RECRUITING", ("2025-09-01", "ACTUAL"),
                False, (240, "ESTIMATED"), ["Knee Osteoarthritis"], ["Group exercise", "Education"])]
URL = ("https://clinicaltrials.gov/api/v2/studies?format=json&countTotal=true&pageSize=100"
       "&query.cond=knee%20osteoarthritis&query.intr=exercise")
LOG = {"question": "Supervised exercise versus usual care for knee osteoarthritis pain",
       "searches": [{"id": "s1", "url": URL, "date": "2026-11-18", "pages": ["search/s1-p1.json"]},
                    {"id": "s2", "url": URL.replace("query.intr=exercise", "query.term=supervised%20exercise"),
                     "date": "2026-11-18", "pages": ["search/s2-p1.json"]}],
       "relevance": [{"nct": "NCT99000101", "call": "similar", "reason": "same comparison in the same population"},
                     {"nct": "NCT99000103", "call": "partial", "reason": "group exercise, not supervised one to one"}]}


def write(path: Path, data) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(data if isinstance(data, str) else json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def build(directory: Path, items=None, rec=None, paper=PAPER, version=True) -> Path:
    """Write a comparison into directory/registry-check and return that folder."""
    base = directory / "registry-check"
    items = copy.deepcopy(ITEMS if items is None else items)
    write(base / "paper.txt", paper)
    write(base / items["record"]["file"], record() if rec is None else rec)
    write(base / "items.json", items)
    if version:
        write(base / "api-version.json", {"apiVersion": "2.0.5", "dataTimestamp": "2026-11-18T10:00:05"})
    return base


def build_search(directory: Path, log=None, first=None, second=None) -> Path:
    base = directory / "registry-check"
    write(base / "search-log.json", copy.deepcopy(LOG if log is None else log))
    write(base / "search" / "s1-p1.json", {"totalCount": 3, "studies": copy.deepcopy(TRIALS)} if first is None else first)
    write(base / "search" / "s2-p1.json", {"totalCount": 1, "studies": copy.deepcopy(TRIALS[:1])} if second is None else second)
    return base
