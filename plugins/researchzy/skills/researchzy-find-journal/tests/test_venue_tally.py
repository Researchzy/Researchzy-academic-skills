"""venue_tally.py: names, tallies, registry lookups against canned answers, and every rule of check.

No test touches the network: the registries are replaced by a function that answers by URL.
"""
from __future__ import annotations

import importlib.util
import io
import json
import sys
import tempfile
import unittest
import urllib.parse
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts" / "venue_tally.py"
spec = importlib.util.spec_from_file_location("venue_tally", SCRIPT)
vt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vt)

ELIFE = {"title": "eLife", "publisher": "eLife Sciences Publications, Ltd", "ISSN": ["2050-084X"],
         "issn-type": [{"value": "2050-084X", "type": "electronic"}], "counts": {"current-dois": 9000},
         "breakdowns": {"dois-by-issued-year": [[2023, 1900], [2025, 2100], [2024, 2000]]}}
SOIL = {"title": "Soil Biology and Biochemistry", "publisher": "Elsevier BV", "ISSN": ["0038-0717", "1879-3428"],
        "issn-type": [{"value": "0038-0717", "type": "print"}, {"value": "1879-3428", "type": "electronic"}],
        "counts": {"current-dois": 3000}, "breakdowns": {"dois-by-issued-year": [[2025, 500]]}}
ELIFE_DOAJ = {"last_updated": "2026-03-01T10:00:00Z", "bibjson": {
    "title": "eLife", "eissn": "2050-084X", "publisher": {"name": "eLife Sciences"},
    "apc": {"has_apc": True, "max": [{"price": 3000, "currency": "USD"}], "url": "https://elifesciences.org/fees"},
    "license": [{"type": "CC BY"}], "publication_time_weeks": 12, "editorial": {"review_process": ["Open peer review"]},
    "ref": {"aims_scope": "https://elifesciences.org/about/aims-scope",
            "author_instructions": "https://elifesciences.org/authors"}}}


class Registries:
    """A stand-in for the network: answers by URL and counts the calls."""

    def __init__(self):
        self.crossref = {"elife": [ELIFE], "soil biology and biochemistry": [SOIL],
                         "journal of imaginary results": [{"title": "Journal of Imaginary Numbers", "ISSN": ["1111-2222"]},
                                                          {"title": "Imaginary Results Quarterly", "ISSN": []}],
                         "neurips": []}
        self.by_issn = {"2050-084X": ELIFE}
        self.doaj = {"2050-084X": [ELIFE_DOAJ]}
        self.down, self.status, self.calls = set(), {}, []

    def __call__(self, url, timeout):
        self.calls.append(url)
        parts = urllib.parse.urlsplit(url)
        if parts.netloc in self.down:
            return None, b"", {}
        if self.status.get(parts.netloc):           # a list of statuses to answer with, one per call
            return self.status[parts.netloc].pop(0), b"busy", {"Retry-After": "1"}

        def reply(data):
            return 200, json.dumps(data).encode(), {}

        if parts.netloc == "api.crossref.org" and parts.path == "/journals":
            query = urllib.parse.parse_qs(parts.query)["query"][0]
            return reply({"status": "ok", "message": {"items": self.crossref.get(query.lower(), [])}})
        if parts.netloc == "api.crossref.org":
            issn = parts.path.rsplit("/", 1)[1]
            return reply({"status": "ok", "message": self.by_issn[issn]}) if issn in self.by_issn else (404, b"", {})
        issn = urllib.parse.unquote(parts.path).rsplit(":", 1)[1]
        found = self.doaj.get(issn, [])
        return reply({"total": len(found), "results": found})


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.dir = self.root / "journal-shortlist"
        self.net = Registries()
        vt.open_url, vt.sleep = self.net, lambda seconds: None
        vt.STATE.update(cache={}, last={}, calls=0)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, data):
        path = self.root / name
        path.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")
        return str(path)

    def run_cli(self, *argv):
        old, out = sys.argv, io.StringIO()
        sys.argv = ["venue_tally.py", "--dir", str(self.dir), *argv]
        try:
            with redirect_stdout(out), redirect_stderr(io.StringIO()):
                code = vt.main()
        finally:
            sys.argv = old
        return code, json.loads(out.getvalue())


class NameTests(unittest.TestCase):
    def test_spellings_of_one_venue_are_one_venue(self):
        same = [("The Lancet", "Lancet", "LANCET (London, England)"),
                ("Science & Technology Review", "Science and Technology Review", "Science &amp; Technology Review"),
                ("Revista Española de Cardiología", "Revista Espanola de Cardiologia"),
                ("Proceedings of the 38th International Conference on Machine Learning",
                 "International Conference on Machine Learning (ICML 2021)", "International Conference on Machine Learning"),
                ("Proc. of the Thirty-Eighth AAAI Conference on Artificial Intelligence", "AAAI Conference on Artificial Intelligence"),
                ("Advances in Neural Information Processing Systems 34", "Advances in Neural Information Processing Systems"),
                ("Annual Meeting of the Association for Computational Linguistics, Vol. 1",
                 "Annual Meeting of the Association for Computational Linguistics 2023"),
                ("J. Mach. Learn. Res.", "J Mach Learn Res")]
        for names in same:
            self.assertEqual(len({vt.venue_key(n) for n in names}), 1, names)

    def test_abbreviations_and_other_names_stay_apart(self):
        self.assertNotEqual(vt.venue_key("J. Mach. Learn. Res."), vt.venue_key("Journal of Machine Learning Research"))
        self.assertNotEqual(vt.venue_key("Nature"), vt.venue_key("Nature Communications"))
        # "Proceedings" is part of a journal's name when the name is not a conference.
        self.assertEqual(vt.venue_key("Proceedings of the National Academy of Sciences"),
                         "proceedings of the national academy of sciences")
        self.assertEqual(vt.venue_key("Proceedings of the IEEE"), "proceedings of the ieee")

    def test_preprint_servers_and_repositories_have_their_own_bucket(self):
        cases = {"arXiv preprint arXiv:1706.03762": "arxiv", "ArXiv": "arxiv", "arXiv.org": "arxiv",
                 "bioRxiv": "biorxiv", "medRxiv : the preprint server for health sciences": "medrxiv",
                 "SSRN Electronic Journal": "ssrn", "Research Square": "research square", "Zenodo": "zenodo",
                 "OSF Preprints": "osf", "PsyArXiv": "psyarxiv"}
        for raw, key in cases.items():
            self.assertEqual(vt.classify(raw)[:2], ("preprint", key), raw)
        self.assertEqual(vt.classify("Halle Studies in Linguistics")[0], "venue")
        self.assertEqual(vt.classify("First Monday")[0], "venue")
        for empty in ("", None, "Unknown", "  "):
            self.assertEqual(vt.classify(empty), ("", "", ""))

    def test_field_labels_and_names(self):
        self.assertEqual(vt.field_name("Open-access model"), "open_access")
        self.assertEqual(vt.field_name("Scope statement"), "scope")
        self.assertEqual(vt.field_name("time to decision"), "time_to_decision")
        self.assertEqual(vt.field_name("Impact factor"), "impact_factor")


BIB = r"""
@string{jn = "Unused"}
@comment{ignored}
@article{smith2021,
  title = {Drought {Legacy} Effects on Soil Microbes},
  journal = {The {ISME} Journal},
  year = 2021, doi = {10.1000/ISME.1}
}
@inproceedings{lee2020, title = "Learning \& soils", booktitle = {Proceedings of the 37th International Conference on Machine Learning}, year = {2020}}
@incollection{chap2019, title = {A chapter}, booktitle = {Handbook of Soil Science}, year = {2019}}
@article{bl2022, title = {Biblatex entry}, journaltitle = {Soil Biology {\&} Biochemistry}, date = {2022-04-01}}
@misc{pre2023, title = {A preprint}, archivePrefix = {arXiv}, eprint = {2301.00001}, year = {2023}}
@book{book2010, title = {A book with no venue}, year = {2010}}
"""


class TallyTests(Base):
    def test_bib_fields(self):
        entries = dict(vt.read_bib(Path(self.write("refs.bib", BIB))))
        self.assertEqual(list(entries), ["smith2021", "lee2020", "chap2019", "bl2022", "pre2023", "book2010"])
        self.assertEqual(entries["smith2021"], {"title": "Drought Legacy Effects on Soil Microbes",
                                                "doi": "10.1000/ISME.1", "venue": "The ISME Journal", "year": "2021"})
        self.assertEqual(entries["lee2020"]["title"], "Learning & soils")
        self.assertEqual(entries["lee2020"]["venue"], "Proceedings of the 37th International Conference on Machine Learning")
        self.assertEqual(entries["chap2019"]["venue"], "")          # a book chapter's booktitle is not a venue
        self.assertEqual((entries["bl2022"]["venue"], entries["bl2022"]["year"]), ("Soil Biology & Biochemistry", "2022-04-01"))
        self.assertEqual(entries["pre2023"]["venue"], "arXiv")

    def test_two_streams_counted_with_duplicates_once(self):
        isme = {"title": "Drought legacy effects on soil microbes", "venue": "ISME Journal", "year": 2021,
                "doi": "10.1000/isme.1", "corpusId": 1}
        s1 = self.write("s1.json", {"query": "soil microbiome drought", "total": 120, "results": [
            isme,
            {"corpusId": 2, "title": "Rewetting pulses", "venue": "Soil Biology and Biochemistry", "year": 2022},
            {"corpusId": 3, "title": "Microbial drought memory", "venue": "bioRxiv", "year": 2023},
            {"corpusId": 4, "title": "No venue paper", "venue": "", "year": 2024}]})
        s2 = self.write("s2.json", [
            {"corpusId": 9, "title": "Drought legacy effects on soil microbes", "venue": "The ISME Journal",
             "doi": "https://doi.org/10.1000/ISME.1", "year": 2021},          # same DOI as in s1
            {"corpusId": 5, "title": "Microbial Drought Memory.", "venue": "Microbiome", "year": 2024},  # its published version
            {"corpusId": 6, "title": "Excluded work", "venue": "Global Change Biology", "year": 2020}])
        s3 = self.write("s3.json", {"papers": [{"corpusId": 7, "title": "Rhizosphere drought",
                                                "venue": "Soil Biol. Biochem.", "year": 2019}]})
        lookups = self.write("refs.json", {"results": {"smith2021": [isme, {"title": "another hit"}],
                                                       "ghost2020": [], "chap2019": []}})
        code, out = self.run_cli("tally", "--similar", s1, s2, s3, "--bib", self.write("refs.bib", BIB),
                                 "--references", lookups, "--exclude", "Global Change Biology", "--exclude", "Nowhere Letters")
        self.assertEqual(code, 0)
        self.assertEqual(out["similar"], {"papers": 6, "deduplicated": 2, "without_venue": 1})
        self.assertEqual(out["references"], {"papers": 7, "deduplicated": 1, "without_venue": 2, "not_found": 1})
        tally = json.loads((self.dir / "tally.json").read_text())
        self.assertEqual(sorted(v["key"] for v in tally["venues"]),
                         ["international conference on machine learning", "isme journal", "microbiome",
                          "soil biol biochem", "soil biology and biochemistry"])
        isme_row = next(v for v in tally["venues"] if v["key"] == "isme journal")
        self.assertEqual((isme_row["similar"], isme_row["references"], isme_row["years"]), (1, 1, [2021, 2021]))
        self.assertEqual(sorted(isme_row["variants"]), ["ISME Journal", "The ISME Journal"])
        soil = next(v for v in tally["venues"] if v["key"] == "soil biology and biochemistry")
        self.assertEqual((soil["similar"], soil["references"], soil["years"]), (1, 1, [2022, 2022]))
        self.assertIn("Rewetting pulses (2022)", soil["examples"]["similar"])
        self.assertIn("soil biol biochem", {v["key"] for v in tally["venues"]})   # an abbreviation stays apart
        # The preprint and its journal version are one paper, counted under the journal.
        self.assertEqual(next(v for v in tally["venues"] if v["key"] == "microbiome")["similar"], 1)
        self.assertEqual([(p["key"], p["similar"], p["references"]) for p in tally["preprints"]], [("arxiv", 0, 1)])
        self.assertEqual([(v["name"], v["similar"]) for v in tally["excluded"]],
                         [("Global Change Biology", 1), ("Nowhere Letters", 0)])
        self.assertNotIn("global change biology", {v["key"] for v in tally["venues"]})
        self.assertEqual(tally["references"]["not_found"], ["ghost2020"])
        self.assertEqual(sorted(tally["references"]["without_venue"]), ["book2010", "chap2019"])
        self.assertEqual(tally["inputs"][0], {"file": s1, "stream": "similar", "records": 4,
                                              "query": "soil microbiome drought", "total": 120})
        md = (self.dir / "tally.md").read_text()
        self.assertIn("Similar papers: 6 (2 found more than once and counted once, 1 without a venue)", md)
        self.assertIn("| ISME Journal (also written: The ISME Journal) | 1 | 1 | 2021 |", md)
        self.assertIn("## Preprint servers and repositories", md)
        self.assertIn("## Excluded", md)
        self.assertIn("- ghost2020", md)

    def test_bad_input_is_a_message_not_a_traceback(self):
        with self.assertRaises(SystemExit) as stop:
            self.run_cli("tally", "--similar", self.write("bad.json", "{not json"))
        self.assertEqual(stop.exception.code, 2)
        with self.assertRaises(SystemExit):
            self.run_cli("tally")
        with self.assertRaises(SystemExit):
            self.run_cli("tally", "--similar", self.write("num.json", "42"))


class LookupTests(Base):
    def facts(self):
        return json.loads((self.dir / "facts.json").read_text())["facts"]

    def fact(self, venue, field):
        return next((f for f in self.facts() if f["venue"] == venue and f["field"] == field), None)

    def test_a_match_gives_crossref_and_doaj_facts_with_source_and_date(self):
        code, out = self.run_cli("lookup", "eLife")
        self.assertEqual(code, 0)
        self.assertEqual(out["looked_up"][0]["crossref"], "found")
        self.assertEqual(out["looked_up"][0]["doaj"], "listed")
        self.assertEqual(out["registry_calls"], 2)
        publisher = self.fact("eLife", "publisher")
        self.assertEqual((publisher["value"], publisher["source"]), ("eLife Sciences Publications, Ltd", "crossref"))
        self.assertEqual(publisher["source_url"], "https://api.crossref.org/journals?query=eLife&rows=5")
        self.assertEqual(publisher["retrieved"], vt.today())
        self.assertEqual(self.fact("eLife", "dois_by_year")["value"], "2025: 2100; 2024: 2000; 2023: 1900")
        fee = self.fact("eLife", "fee")
        self.assertEqual((fee["value"], fee["source"], fee["source_url"]),
                         ("APC, highest charged: 3000 USD, as declared to DOAJ", "doaj",
                          "https://doaj.org/api/search/journals/issn:2050-084X"))
        self.assertEqual(self.fact("eLife", "open_access")["value"], "Open access; licence CC BY, as declared to DOAJ")
        self.assertEqual(self.fact("eLife", "peer_review")["value"], "Open peer review, as declared to DOAJ")
        self.assertIsNone(self.fact("eLife", "time_to_decision"))   # DOAJ's weeks are to publication
        self.assertIn("12 weeks from submission to publication", self.fact("eLife", "weeks_to_publication")["value"])
        self.assertEqual(self.fact("eLife", "aims_scope_url")["value"], "https://elifesciences.org/about/aims-scope")
        md = (self.dir / "facts.md").read_text()
        self.assertIn("| eLife | Fee | APC, highest charged: 3000 USD, as declared to DOAJ | "
                      "https://doaj.org/api/search/journals/issn:2050-084X |", md)
        self.assertIn("| eLife | Scope statement | confirm on site | | |", md)
        self.assertIn("a subscription or hybrid journal is expected to be `not found`", md)
        self.assertIn("a conference is expected to be `not found` or `not matched`", md)
        self.assertIn("Neither absence is a warning by itself", md)
        self.assertIn("what the journal declared to DOAJ: confirm them on its site", md)
        # Answers are cached: the same lookup again makes no call.
        self.assertEqual(self.run_cli("lookup", "eLife")[1]["registry_calls"], 0)

    def test_doaj_is_asked_once_with_the_electronic_issn(self):
        _, out = self.run_cli("lookup", "Soil Biology and Biochemistry")
        self.assertEqual((out["looked_up"][0]["crossref"], out["looked_up"][0]["doaj"]), ("found", "not_found"))
        self.assertEqual(out["looked_up"][0]["issn"], ["1879-3428", "0038-0717"])
        self.assertEqual([u for u in self.net.calls if "doaj" in u], ["https://doaj.org/api/search/journals/issn:1879-3428"])
        self.assertEqual(self.fact("Soil Biology and Biochemistry", "doaj_status")["value"], "not_found")
        self.assertIsNone(self.fact("Soil Biology and Biochemistry", "fee"))

    def test_near_titles_are_not_a_match(self):
        _, out = self.run_cli("lookup", "Journal of Imaginary Results")
        row = out["looked_up"][0]
        self.assertEqual((row["crossref"], row["doaj"]), ("not_matched", "not_looked_up"))
        self.assertEqual(row["did_you_mean"], ["Journal of Imaginary Numbers (1111-2222; publisher not given)",
                                               "Imaginary Results Quarterly (no ISSN; publisher not given)"])
        status = self.fact("Journal of Imaginary Results", "crossref_status")
        self.assertIn("did you mean: Journal of Imaginary Numbers", status["note"])
        self.assertIsNone(self.fact("Journal of Imaginary Results", "publisher"))

    def test_not_found_is_kept_apart_from_a_failed_lookup(self):
        _, out = self.run_cli("lookup", "NeurIPS")
        self.assertEqual(out["looked_up"][0]["crossref"], "not_found")
        _, out = self.run_cli("lookup", "Made Up Journal", "--issn", "1234-5678")
        self.assertEqual(out["looked_up"][0]["crossref"], "not_found")
        self.assertEqual(out["looked_up"][0]["doaj"], "not_found")

        self.net.down.add("api.crossref.org")
        self.net.status["doaj.org"] = [500]
        _, out = self.run_cli("lookup", "Another Journal", "--issn", "2222-3333")
        self.assertEqual((out["looked_up"][0]["crossref"], out["looked_up"][0]["doaj"]), ("lookup_failed", "lookup_failed"))
        md = (self.dir / "facts.md").read_text()
        self.assertIn("| Another Journal | lookup failed,", md)
        # A failure is not cached: the next run asks again.
        self.net.down.clear()
        _, out = self.run_cli("lookup", "Another Journal", "--issn", "2222-3333")
        self.assertEqual(out["looked_up"][0]["doaj"], "not_found")
        self.assertEqual(out["registry_calls"], 2)

    def test_one_retry_after_rate_limiting(self):
        self.net.status["api.crossref.org"] = [429]
        _, out = self.run_cli("lookup", "eLife")
        self.assertEqual(out["looked_up"][0]["crossref"], "found")
        self.assertEqual(out["registry_calls"], 3)

    def test_issn_must_be_well_formed_and_alone(self):
        for argv in (("lookup", "eLife", "--issn", "2050084X"), ("lookup", "A", "B", "--issn", "2050-084X")):
            with self.assertRaises(SystemExit):
                self.run_cli(*argv)

    def test_a_fact_read_on_the_venue_page(self):
        self.run_cli("lookup", "eLife")
        _, out = self.run_cli("fact", "eLife", "Article types accepted", "Research Article; Short Report",
                              "--url", "https://elifesciences.org/authors", "--date", "2026-11-12")
        self.assertEqual((out["field"], out["in_facts_table"]), ("article_types", True))
        self.run_cli("fact", "eLife", "fee", "2000 USD", "--url", "https://elifesciences.org/fees")
        self.run_cli("fact", "eLife", "fee", "2500 USD", "--url", "https://elifesciences.org/fees")
        page_fees = [f for f in self.facts() if f["field"] == "fee" and f["source"] == "page"]
        self.assertEqual([f["value"] for f in page_fees], ["2500 USD"])          # replaced, not added
        self.assertEqual(len([f for f in self.facts() if f["field"] == "fee"]), 2)  # DOAJ's stays
        md = (self.dir / "facts.md").read_text()
        self.assertIn("| eLife | Fee | 2500 USD | https://elifesciences.org/fees |", md)   # the page beats DOAJ
        self.assertIn("| eLife | Article types accepted | Research Article; Short Report | "
                      "https://elifesciences.org/authors | 2026-11-12 |", md)
        for bad in (("fact", "eLife", "fee", "1 USD", "--url", "elifesciences.org"),
                    ("fact", "eLife", "fee", "1 USD", "--url", "https://x.org", "--date", "12/11/2026"),
                    ("fact", "eLife", "fee", "confirm on site", "--url", "https://x.org"),
                    ("fact", "eLife", "crossref_status", "found", "--url", "https://x.org")):
            with self.assertRaises(SystemExit):
                self.run_cli(*bad)


SHORTLIST = """# Journal shortlist: Drought legacy in soil microbes

2026-11-12 · research article · evidence: tally.md, facts.md

## Brief

- Excluded by the user: Global Change Biology

## Evidence

Four searches gave 40 similar papers; 30 references were counted.

## Shortlist

### 1. eLife

- Band: strong fit
- Reason: Both streams name it, and the venue filter found three recent papers on drought legacy.
- Recent papers on the topic: "Drought in 30 days of soil" (2024)
- Fee: APC of 3000 USD as declared to DOAJ, see https://elifesciences.org/fees-2024 checked 2026-11-12.

### 2. Soil Biology and Biochemistry

- **Band:** plausible
- **Reason:** Similar papers appear there; DOAJ does not list it, which is expected for a subscription journal.

### 3. Microbiome

- Band: stretch
- Reason: Added by judgement; one recent paper on the topic.

## Added by judgement

| Venue | Why it was added | Evidence found for it |
|---|---|---|
| Microbiome | The user's field publishes there | One paper |

## Facts to confirm

| Venue | Field | Value | Source | Date read |
|---|---|---|---|---|
{rows}

## Cascade plan

| Step | Venue | When | Why |
|---|---|---|---|
| 1 | eLife | First submission | Strongest evidence |
| 2 | Soil Biology and Biochemistry | After a desk rejection | Narrower readership |

A same-publisher transfer depends on the publisher: confirm on site.

```text
Fenced text is not read: an APC of 9999 here is ignored.
```

## What was not checked

- The design bar (researchzy-paper-review).
"""


class CheckTests(Base):
    def setUp(self):
        super().setUp()
        similar = self.write("s.json", [
            {"title": "A", "venue": "eLife", "year": 2024}, {"title": "B", "venue": "Soil Biology and Biochemistry", "year": 2023},
            {"title": "C", "venue": "Global Change Biology", "year": 2022}, {"title": "D", "venue": "bioRxiv", "year": 2025}])
        self.run_cli("tally", "--similar", similar, "--exclude", "Global Change Biology")
        self.run_cli("lookup", "eLife", "Soil Biology and Biochemistry")
        self.run_cli("fact", "eLife", "scope", "Research in the life and biomedical sciences",
                     "--url", "https://elifesciences.org/about/aims-scope", "--date", "2026-11-12")
        doaj = "https://doaj.org/api/search/journals/issn:2050-084X"
        today = vt.today()
        rows = []
        for venue in ("eLife", "Soil Biology and Biochemistry", "Microbiome"):
            for field, label in vt.FIELDS.items():
                rows.append(f"| {venue} | {label} | confirm on site | | |")
        rows[0] = ("| eLife | Scope statement | Research in the life and biomedical sciences | "
                   "https://elifesciences.org/about/aims-scope | 2026-11-12 |")
        rows[4] = f"| eLife | Fee | APC, highest charged: 3000 USD, as declared to DOAJ | {doaj} | {today} |"
        self.good = SHORTLIST.replace("{rows}", "\n".join(rows))

    def check(self, text):
        path = self.write("shortlist.md", text)
        return self.run_cli("check", path)

    def rules(self, text):
        code, out = self.check(text)
        self.assertEqual(code, 1)
        return [p["rule"] for p in out["problems"]], out

    def test_a_good_shortlist_passes(self):
        code, out = self.check(self.good)
        self.assertEqual(out["problems"], [])
        self.assertEqual((code, out["ok"]), (0, True))
        self.assertEqual(out["from_tally"], ["eLife", "Soil Biology and Biochemistry"])
        self.assertEqual(out["added_by_judgement"], ["Microbiome"])
        self.assertEqual(out["facts_table"], {"sourced": 2, "confirm_on_site": 25})
        self.assertTrue(any("five to eight" in n for n in out["notes"]))
        self.assertTrue(any(n.startswith("Microbiome was not looked up") for n in out["notes"]))

    def test_origin_every_venue_comes_from_the_tally_or_the_judgement_list(self):
        text = self.good.replace("| Microbiome | The user's field publishes there | One paper |\n", "")
        rules, out = self.rules(text)
        self.assertEqual(rules, ["origin"])
        self.assertIn("Microbiome is neither in tally.json", out["problems"][0]["detail"])

    def test_excluded_venues_must_not_appear(self):
        text = self.good.replace("| 2 | Soil Biology and Biochemistry |", "| 2 | Global Change Biology |")
        rules, _ = self.rules(text)
        self.assertEqual(sorted(rules), ["cascade", "excluded"])
        text = self.good.replace("### 3. Microbiome", "### 3. Global Change Biology").replace(
            "| Microbiome |", "| Global Change Biology |")
        rules, _ = self.rules(text)
        self.assertIn("excluded", rules)
        # A preprint server or an excluded venue named in the Brief is not a shortlist entry.
        self.assertEqual(self.check(self.good)[0], 0)

    def test_facts_cells_are_recorded_values_or_confirm_on_site(self):
        for old, new in (("| eLife | Length limits | confirm on site | | |", "| eLife | Length limits | 5000 words | | |"),
                         ("| eLife | Length limits | confirm on site | | |", "| eLife | Length limits | | | |"),
                         ("| eLife | Length limits | confirm on site | | |", "| eLife | Length limits | Confirm on the site | | |"),
                         ("| 2026-11-12 |\n| eLife | Article", "| 2026-11-11 |\n| eLife | Article"),           # wrong date
                         ("https://elifesciences.org/about/aims-scope |", "https://example.org/scope |"),       # wrong source
                         ("| eLife | Preprint policy | confirm on site | | |\n", ""),                              # a missing row
                         ("| Microbiome | Fee | confirm on site | | |", "| Microbiome | Colour | confirm on site | | |"),
                         ("| Microbiome | Fee | confirm on site | | |", "| Nature | Fee | confirm on site | | |")):
            self.assertIn(old, self.good)
            rules, _ = self.rules(self.good.replace(old, new, 1))
            self.assertIn("facts_table", rules, new)

    def test_numbers_next_to_metric_words_need_a_recorded_fact(self):
        for sentence in ("Its impact factor is 4.2.", "Decisions take 30 days.", "The APC is 2,950 USD.",
                         "Expect about 6 weeks to a first decision.", "The fee: 150 EUR per page."):
            text = self.good.replace("## What was not checked", f"{sentence}\n\n## What was not checked")
            rules, _ = self.rules(text)
            self.assertEqual(rules, ["unsourced_number"], sentence)
        # A recorded number may be repeated; under a venue's heading it must be that venue's.
        ok = self.good.replace("## What was not checked", "DOAJ lists an APC of 3000 USD for eLife.\n\n## What was not checked")
        self.assertEqual(self.check(ok)[0], 0)
        wrong_venue = self.good.replace("- Band: stretch", "- Band: stretch\n- Fee: 3000 USD")
        rules, out = self.rules(wrong_venue)
        self.assertEqual(rules, ["unsourced_number"])
        self.assertIn("for this venue", out["problems"][0]["detail"])
        # Numbers in addresses, dates, quoted titles and fenced text are not read: the good shortlist has all four.

    def test_no_probability_of_acceptance(self):
        for sentence in ("The probability of acceptance is moderate.", "A good chance of acceptance.",
                         "About 30% of such papers are accepted.", "Odds of acceptance are fair.",
                         "Likelihood of being accepted: high."):
            text = self.good.replace("## What was not checked", f"{sentence}\n\n## What was not checked")
            rules, _ = self.rules(text)
            self.assertIn("prediction", rules, sentence)

    def test_bands_and_reasons(self):
        rules, out = self.rules(self.good.replace("- Band: strong fit", "- Band: excellent fit"))
        self.assertEqual(rules, ["band"])
        self.assertIn("strong fit, plausible, stretch", out["problems"][0]["detail"])
        rules, _ = self.rules(self.good.replace("- Reason: Added by judgement; one recent paper on the topic.\n", ""))
        self.assertEqual(rules, ["band"])

    def test_layout(self):
        rules, _ = self.rules(self.good.replace("## Shortlist", "## Candidates"))
        self.assertIn("layout", rules)
        twice = self.good.replace("### 3. Microbiome", "### 3. The eLife")
        rules, _ = self.rules(twice)
        self.assertIn("layout", rules)

    def test_check_needs_a_tally(self):
        (self.dir / "tally.json").unlink()
        with self.assertRaises(SystemExit) as stop:
            self.check(self.good)
        self.assertEqual(stop.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
