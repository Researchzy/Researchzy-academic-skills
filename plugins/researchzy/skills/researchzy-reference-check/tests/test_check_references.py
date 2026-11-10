"""check_references.py against recorded registry answers; no test touches the network."""
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

SCRIPT = Path(__file__).parents[1] / "scripts" / "check_references.py"
spec = importlib.util.spec_from_file_location("check_references", SCRIPT)
cr = importlib.util.module_from_spec(spec)
sys.modules["check_references"] = cr
spec.loader.exec_module(cr)


def crossref_work(doi, title, authors, year, **extra):
    msg = {"DOI": doi, "title": [title], "type": "journal-article",
           "author": [{"family": f, "given": g} for f, g in authors],
           "issued": {"date-parts": [[year]]}, "container-title": ["Journal of Tests"]}
    msg.update(extra)
    return msg


RESNET = crossref_work("10.1109/cvpr.2016.90", "Deep Residual Learning for Image Recognition",
                       [("He", "Kaiming"), ("Zhang", "Xiangyu"), ("Ren", "Shaoqing"), ("Sun", "Jian")], 2016)
ALEXNET = crossref_work("10.1145/3065386", "ImageNet classification with deep convolutional neural networks",
                        [("Krizhevsky", "Alex"), ("Sutskever", "Ilya"), ("Hinton", "Geoffrey E.")], 2017)
DEEP_LEARNING = crossref_work("10.1038/nature14539", "Deep learning",
                              [("LeCun", "Yann"), ("Bengio", "Yoshua"), ("Hinton", "Geoffrey")], 2015)
RETRACTED = crossref_work(
    "10.1016/s0140-6736(97)11096-0", "RETRACTED: Ileal-lymphoid-nodular hyperplasia in children",
    [("Wakefield", "AJ"), ("Murch", "SH")], 1998,
    **{"updated-by": [{"DOI": "10.1016/s0140-6736(10)60175-4", "type": "retraction", "label": "Retraction",
                       "updated": {"date-parts": [[2010, 2, 6]]}}]})
NOTICE = crossref_work("10.1016/s0140-6736(10)60175-4", "Retraction—Ileal-lymphoid-nodular hyperplasia in children",
                       [], 2010, **{"update-to": [{"DOI": "10.1016/s0140-6736(97)11096-0", "type": "retraction"}]})

ARXIV_FEED = """<?xml version='1.0' encoding='UTF-8'?><feed xmlns="http://www.w3.org/2005/Atom">
<opensearch:totalResults>{n}</opensearch:totalResults>{entry}</feed>"""
ATTENTION = """<entry><id>http://arxiv.org/abs/1706.03762v5</id><title>Attention Is All
 You Need</title><published>2017-06-12T17:57:34Z</published>
<author><name>Ashish Vaswani</name></author><author><name>Noam Shazeer</name></author></entry>"""
HIGGS = """<entry><id>http://arxiv.org/abs/1207.7214v2</id><title>Observation of a new particle</title>
<published>2012-07-31T11:59:59Z</published><author><name>The ATLAS Collaboration</name></author>
<arxiv:doi xmlns:arxiv="http://arxiv.org/schemas/atom">10.1016/j.physletb.2012.08.020</arxiv:doi>
<arxiv:journal_ref xmlns:arxiv="http://arxiv.org/schemas/atom">Phys.Lett. B716 (2012) 1-29</arxiv:journal_ref></entry>"""


class Registries:
    """A stand-in for the network: answers by URL, counts the calls."""

    def __init__(self):
        self.crossref = {m["DOI"]: m for m in (RESNET, ALEXNET, DEEP_LEARNING, RETRACTED, NOTICE)}
        self.handles: set = set()           # DOIs registered with an agency other than Crossref
        self.datacite: dict = {}
        self.arxiv = {"1706.03762": ATTENTION, "1207.7214": HIGGS}
        self.pubmed: dict = {}
        self.search: list = []              # items a Crossref title search returns
        self.down: tuple = ()               # hosts that do not answer
        self.status: dict = {}              # host -> HTTP status to answer with
        self.calls: list = []

    def __call__(self, url, timeout):
        self.calls.append(url)
        parts = urllib.parse.urlsplit(url)
        host, path, query = parts.netloc, urllib.parse.unquote(parts.path), urllib.parse.parse_qs(parts.query)
        if host in self.down:
            return None, b"", {}
        if host in self.status:
            return self.status[host], b"busy", {}

        def reply(status, data):
            return status, (json.dumps(data) if not isinstance(data, str) else data).encode(), {}

        if host == "api.crossref.org" and "query.bibliographic" in query:
            return reply(200, {"status": "ok", "message": {"items": self.search}})
        if host == "api.crossref.org":
            doi = path[len("/works/"):].lower()
            if doi in self.crossref:
                return reply(200, {"status": "ok", "message": self.crossref[doi]})
            return reply(404, "Resource not found.")
        if host == "doi.org":
            doi = path[len("/api/handles/"):].lower()
            known = doi in self.handles or doi in self.crossref
            return reply(200 if known else 404, {"responseCode": 1 if known else 100, "handle": doi})
        if host == "api.datacite.org":
            doi = path[len("/dois/"):].lower()
            if doi in self.datacite:
                return reply(200, {"data": {"attributes": self.datacite[doi]}})
            return reply(404, {"errors": [{"status": "404"}]})
        if host == "export.arxiv.org":
            entry = self.arxiv.get(query["id_list"][0], "")
            return reply(200, ARXIV_FEED.format(n=1 if entry else 0, entry=entry))
        if host == "eutils.ncbi.nlm.nih.gov":
            pmid = query["id"][0]
            if path.endswith("esummary.fcgi"):
                item = self.pubmed.get(pmid, {}).get("summary") or {"uid": pmid, "error": "cannot get document summary"}
                return reply(200, {"result": {"uids": [pmid], pmid: item}})
            return reply(200, self.pubmed.get(pmid, {}).get("xml", "<PubmedArticleSet></PubmedArticleSet>"))
        raise AssertionError(f"unexpected request: {url}")


def bib(key, title, authors, year, **fields):
    extra = "".join(f",\n  {k} = {{{v}}}" for k, v in fields.items())
    return f"@article{{{key},\n  title = {{{title}}},\n  author = {{{authors}}},\n  year = {{{year}}}{extra}\n}}\n"


RESNET_AUTHORS = "He, Kaiming and Zhang, Xiangyu and Ren, Shaoqing and Sun, Jian"


class Base(unittest.TestCase):
    def setUp(self):
        self.net = Registries()
        cr.CLIENT.opener = self.net
        cr.CLIENT.sleep = lambda seconds: None
        cr.CLIENT.cache = {}
        cr.CLIENT.calls = 0
        cr.CLIENT._last = {}

    def check(self, text, researchzy=None, parse=cr.parse_bib):
        record = parse(text)[0]
        return cr.verify_record(record, offline=False, researchzy=researchzy)


class DoiTests(Base):
    def test_a_matching_record_confirms(self):
        rec = self.check(bib("he2016", "Deep Residual Learning for Image Recognition", RESNET_AUTHORS, 2016,
                             doi="10.1109/CVPR.2016.90"))
        self.assertEqual(rec.status, cr.CONFIRMED)
        self.assertEqual(rec.found["source"], "crossref")
        self.assertEqual(rec.differences, [])

    def test_brace_protected_capitals_do_not_split_title_words(self):
        rec = self.check(bib("he2016", "{D}eep {R}esidual {L}earning for {I}mage {R}ecognition",
                             RESNET_AUTHORS, 2016, doi="10.1109/CVPR.2016.90"))
        self.assertEqual(rec.title_guess, "Deep Residual Learning for Image Recognition")
        self.assertEqual(rec.status, cr.CONFIRMED)

    def test_an_invented_co_author_is_a_mismatch(self):
        rec = self.check(bib("he2016", "Deep Residual Learning for Image Recognition",
                             "He, Kaiming and LeCun, Yann and Ren, Shaoqing and Sun, Jian", 2016,
                             doi="10.1109/CVPR.2016.90"))
        self.assertEqual(rec.status, cr.MISMATCH)
        self.assertEqual([d["field"] for d in rec.differences], ["author"])
        self.assertIn("after the first", rec.differences[0]["summary"])
        self.assertEqual(cr.bib_fixes(rec)[0][:2], ("author", RESNET_AUTHORS))

    def test_a_wrong_first_author_is_named_as_such(self):
        rec = self.check(bib("he2016", "Deep Residual Learning for Image Recognition",
                             "Hinton, Geoffrey and Zhang, Xiangyu and Ren, Shaoqing and Sun, Jian", 2016,
                             doi="10.1109/CVPR.2016.90"))
        self.assertIn("first author differs", rec.differences[0]["summary"])

    def test_and_others_is_a_declared_short_list(self):
        rec = self.check(bib("he2016", "Deep Residual Learning for Image Recognition",
                             "He, Kaiming and others", 2016, doi="10.1109/CVPR.2016.90"))
        self.assertEqual(rec.status, cr.CONFIRMED)
        self.assertIn("1 of 4 cited", rec.note)

    def test_a_short_list_without_and_others_is_a_mismatch(self):
        rec = self.check(bib("he2016", "Deep Residual Learning for Image Recognition",
                             "He, Kaiming and Zhang, Xiangyu", 2016, doi="10.1109/CVPR.2016.90"))
        self.assertEqual(rec.status, cr.MISMATCH)
        self.assertIn("AUTHOR COUNT", rec.differences[0]["detail"])

    def test_a_year_two_off_is_a_minor_difference_and_one_off_a_note(self):
        rec = self.check(bib("he2016", "Deep Residual Learning for Image Recognition", RESNET_AUTHORS, 2018,
                             doi="10.1109/CVPR.2016.90"))
        self.assertEqual(rec.status, cr.MISMATCH)
        self.assertEqual((rec.differences[0]["field"], rec.differences[0]["severity"]), ("year", "minor"))
        self.assertEqual(cr.bib_fixes(rec)[0][:2], ("year", "2016"))
        rec = self.check(bib("he2016", "Deep Residual Learning for Image Recognition", RESNET_AUTHORS, 2017,
                             doi="10.1109/CVPR.2016.90"))
        self.assertEqual(rec.status, cr.CONFIRMED)
        self.assertIn("year: cited 2017", rec.note)

    def test_a_real_doi_of_another_paper_is_caught_and_the_cited_work_is_found(self):
        self.net.search = [ALEXNET]
        rec = self.check(bib("krizhevsky2012", "ImageNet Classification with Deep Convolutional Neural Networks",
                             "Krizhevsky, Alex and Sutskever, Ilya and Hinton, Geoffrey E.", 2017,
                             doi="10.1038/nature14539"))
        self.assertEqual(rec.status, cr.MISMATCH)
        self.assertEqual([d["field"] for d in rec.differences], ["identifier_points_elsewhere"])
        self.assertIn("Deep learning", rec.differences[0]["found"])
        self.assertEqual(rec.found["doi"], "10.1145/3065386")  # the cited work, not the DOI's
        self.assertEqual(cr.bib_fixes(rec)[0][:2], ("doi", "10.1145/3065386"))

    def test_a_real_doi_of_another_paper_when_the_cited_work_is_not_found(self):
        rec = self.check(bib("krizhevsky2012", "ImageNet Classification with Deep Convolutional Neural Networks",
                             "Krizhevsky, Alex", 2017, doi="10.1038/nature14539"))
        self.assertEqual(rec.status, cr.MISMATCH)
        self.assertEqual(rec.found, {})
        self.assertIn("the cited work itself was not found", rec.note)
        self.assertEqual(rec.flags, [])
        needed = cr.researchzy_lookups([rec], None)["needed"]
        self.assertEqual([c["arguments"] for c in needed[0]["calls"]],
                         [{"query": '"ImageNet Classification with Deep Convolutional Neural Networks"'},
                          {"query": "ImageNet Classification with Deep Convolutional Neural Networks"}])

    def test_a_doi_in_no_registry_is_not_registered(self):
        rec = self.check(bib("x2023", "Quantum gravitational effects on avian migration", "Marlowe, Tessa", 2023,
                             doi="10.1234/jir.2023.99999"))
        self.assertEqual(rec.status, cr.NOT_REGISTERED)
        self.assertIn("does not exist in any registry", rec.evidence)

    def test_an_unregistered_doi_on_a_real_paper_is_a_mismatch_with_the_right_doi(self):
        self.net.search = [RESNET]
        rec = self.check(bib("he2016", "Deep Residual Learning for Image Recognition", RESNET_AUTHORS, 2016,
                             doi="10.1109/CVPR.2016.99999"))
        self.assertEqual(rec.status, cr.MISMATCH)
        self.assertEqual(rec.differences[0]["field"], "identifier_not_registered")
        self.assertEqual(cr.bib_fixes(rec)[0][:2], ("doi", "10.1109/cvpr.2016.90"))

    def test_a_registry_that_does_not_answer_refutes_nothing(self):
        for failure in ({"down": ("api.crossref.org",)}, {"status": {"api.crossref.org": 500}}):
            self.setUp()
            for key, value in failure.items():
                setattr(self.net, key, value)
            rec = self.check(bib("he2016", "Deep Residual Learning for Image Recognition", RESNET_AUTHORS, 2016,
                                 doi="10.1109/CVPR.2016.90"))
            self.assertEqual(rec.status, cr.UNCONFIRMED, failure)
            self.assertIn("lookup failed", rec.evidence)

    def test_a_failed_handle_lookup_leaves_the_doi_unconfirmed(self):
        self.net.down = ("doi.org",)
        rec = self.check(bib("x2023", "Some dataset", "Doe, Jane", 2023, doi="10.5281/zenodo.1"))
        self.assertEqual(rec.status, cr.UNCONFIRMED)

    def test_a_malformed_doi_is_not_sent_to_the_handle_registry(self):
        rec = self.check(bib("x2023", "Some paper title of many words", "Doe, Jane", 2023, doi="n/a"))
        self.assertEqual(rec.status, cr.UNCONFIRMED)
        self.assertFalse(any("doi.org" in url for url in self.net.calls))

    def test_a_datacite_doi_is_confirmed_from_datacite(self):
        self.net.handles.add("10.5281/zenodo.42")
        self.net.datacite["10.5281/zenodo.42"] = {
            "titles": [{"title": "A dataset of test references"}], "publicationYear": 2023,
            "creators": [{"familyName": "Doe", "givenName": "Jane", "name": "Doe, Jane"},
                         {"name": "Sebastian Schwindt", "familyName": "Sebastian Schwindt"}],
            "types": {"resourceTypeGeneral": "Dataset"}}
        rec = self.check(bib("doe2023", "A dataset of test references", "Doe, Jane and Schwindt, Sebastian", 2023,
                             doi="10.5281/zenodo.42"))
        self.assertEqual((rec.status, rec.found["source"]), (cr.CONFIRMED, "datacite"))

    def test_a_doi_of_another_agency_without_a_record_is_unconfirmed(self):
        self.net.handles.add("10.5281/zenodo.43")
        rec = self.check(bib("doe2023", "A dataset of test references", "Doe, Jane", 2023, doi="10.5281/zenodo.43"))
        self.assertEqual(rec.status, cr.UNCONFIRMED)
        self.assertIn("registered with another agency", rec.evidence)

    def test_a_retraction_is_flagged_with_its_notice(self):
        rec = self.check(bib("w1998", "Ileal-lymphoid-nodular hyperplasia in children",
                             "Wakefield, AJ and Murch, SH", 1998, doi="10.1016/S0140-6736(97)11096-0"))
        self.assertEqual(rec.status, cr.CONFIRMED)
        self.assertEqual([f["flag"] for f in rec.flags], ["retracted"])
        self.assertIn("10.1016/s0140-6736(10)60175-4 (2010-02-06)", rec.flags[0]["detail"])

    def test_a_cited_retraction_notice_is_flagged_as_a_notice(self):
        rec = self.check(bib("n2010", "Retraction: Ileal-lymphoid-nodular hyperplasia in children", "{The Editors}",
                             2010, doi="10.1016/S0140-6736(10)60175-4"))
        self.assertEqual([f["flag"] for f in rec.flags], ["update_notice"])


class ArxivAndPubmedTests(Base):
    def test_an_eprint_number_is_confirmed_by_arxiv(self):
        rec = self.check(bib("v2017", "Attention Is All You Need", "Vaswani, Ashish and Shazeer, Noam", 2017,
                             eprint="1706.03762", archivePrefix="arXiv"))
        self.assertEqual((rec.status, rec.found["source"]), (cr.CONFIRMED, "arxiv"))

    def test_an_arxiv_doi_is_looked_up_at_arxiv_not_crossref(self):
        rec = self.check(bib("v2017", "Attention Is All You Need", "Vaswani, Ashish", 2017,
                             doi="10.48550/arXiv.1706.03762"))
        self.assertEqual(rec.status, cr.CONFIRMED)
        self.assertFalse(any("crossref" in url for url in self.net.calls))

    def test_a_wrong_first_author_on_an_arxiv_paper_is_a_mismatch(self):
        rec = self.check(bib("v2017", "Attention Is All You Need", "Hinton, Geoffrey", 2017, eprint="1706.03762"))
        self.assertEqual(rec.status, cr.MISMATCH)
        self.assertIn("first author differs", rec.note)

    def test_a_published_preprint_and_a_collective_author(self):
        rec = self.check(bib("atlas2012", "Observation of a new particle", "{ATLAS Collaboration}", 2012,
                             eprint="1207.7214"))
        self.assertEqual(rec.status, cr.CONFIRMED)
        self.assertEqual([f["flag"] for f in rec.flags], ["preprint_published"])
        self.assertIn("collective author", rec.note)
        self.assertIn("DOI of the record: 10.1016/j.physletb.2012.08.020", rec.note)

    def test_an_arxiv_number_arxiv_does_not_have(self):
        rec = self.check(bib("x2024", "A paper that is not there at all", "Doe, Jane", 2024, eprint="2401.99999"))
        self.assertEqual(rec.status, cr.NOT_REGISTERED)

    def test_a_pmid_with_its_structured_authors_and_retraction(self):
        self.net.pubmed["9500320"] = {
            "summary": {"uid": "9500320", "title": "Ileal-lymphoid-nodular hyperplasia in children.",
                        "pubdate": "1998 Feb 28", "pubtype": ["Journal Article", "Retracted Publication"],
                        "authors": [{"name": "Wakefield AJ", "authtype": "Author"}],
                        "articleids": [{"idtype": "doi", "value": "10.1016/S0140-6736(97)11096-0"}]},
            "xml": '<Author ValidYN="Y"><LastName>Wakefield</LastName><ForeName>A J</ForeName></Author>'
                   '<Author ValidYN="Y"><LastName>Murch</LastName><ForeName>S H</ForeName></Author>'
                   '<CommentsCorrections RefType="RetractionIn"></CommentsCorrections>'}
        rec = self.check(bib("w1998", "Ileal-lymphoid-nodular hyperplasia in children",
                             "Wakefield, A. J. and Murch, S. H.", 1998, pmid="9500320"))
        self.assertEqual((rec.status, rec.found["source"]), (cr.CONFIRMED, "pubmed"))
        self.assertEqual(rec.actual_authors, ["Wakefield", "Murch"])
        self.assertEqual([f["flag"] for f in rec.flags], ["retracted"])

    def test_a_pmid_pubmed_does_not_have(self):
        rec = self.check(bib("x1998", "A paper that is not there at all", "Doe, Jane", 1998, pmid="99999999"))
        self.assertEqual(rec.status, cr.NOT_REGISTERED)


class TitleSearchTests(Base):
    def test_a_title_match_with_agreeing_authors_confirms_and_offers_the_doi(self):
        self.net.search = [RESNET]
        rec = self.check(bib("he2016", "Deep Residual Learning for Image Recognition", RESNET_AUTHORS, 2016))
        self.assertEqual((rec.status, rec.found["source"]), (cr.CONFIRMED, "crossref_title"))
        self.assertIn("DOI of the record: 10.1109/cvpr.2016.90", rec.note)

    def test_a_title_match_with_other_authors_is_only_a_candidate(self):
        self.net.search = [RESNET]
        rec = self.check(bib("x2016", "Deep Residual Learning for Image Recognition", "Marlowe, Tessa", 2016))
        self.assertEqual(rec.status, cr.UNCONFIRMED)
        self.assertEqual(rec.candidates[0]["why_not"], "its authors differ from the cited ones")

    def test_a_title_match_from_another_year_is_only_a_candidate(self):
        self.net.search = [RESNET]
        rec = self.check(bib("he2009", "Deep Residual Learning for Image Recognition", RESNET_AUTHORS, 2009))
        self.assertEqual(rec.status, cr.UNCONFIRMED)
        self.assertEqual(rec.candidates[0]["why_not"], "its year is not the cited one")

    def test_a_similar_title_is_not_the_same_title(self):
        self.net.search = [crossref_work("10.1/b", "Deep Residual Learning for Image Recognition: A Critical Survey",
                                         [("He", "Kaiming")], 2016)]
        rec = self.check(bib("he2016", "Deep Residual Learning for Image Recognition", "He, Kaiming", 2016))
        self.assertEqual(rec.status, cr.UNCONFIRMED)
        self.assertEqual((rec.candidates[0]["similarity"], rec.candidates[0]["doi"]), (0.71, "10.1/b"))
        self.assertIn("No confident Crossref title match", rec.evidence)

    def test_a_plain_text_reference_is_matched_by_the_title_inside_it(self):
        self.net.search = [RESNET]
        line = "[1] He K, Zhang X, Ren S, Sun J. Deep residual learning for image recognition. CVPR. 2016."
        rec = self.check(line + "\n[2] Other A. Another reference that is long enough. 2015.", parse=cr.parse_reference_lines)
        self.assertEqual((rec.ref_id, rec.status), ("ref_1", cr.CONFIRMED))

    def test_a_short_title_whose_words_merely_occur_in_the_line_is_not_a_match(self):
        self.net.search = [crossref_work("10.1/s", "Stochastic Optimization Methods", [("Marti", "Kurt")], 2015)]
        line = "[4] Kingma DP, Ba J. Adam: A method for stochastic optimization. ICLR; 2015."
        rec = self.check(line + "\n[5] Other A. Another reference that is long enough. 2015.", parse=cr.parse_reference_lines)
        self.assertEqual((rec.status, rec.candidates), (cr.UNCONFIRMED, []))

    def test_plain_text_author_styles_are_not_mismatches(self):
        for authors in ("He K, Zhang X, Ren S, Sun J.", "K. He, X. Zhang, S. Ren, and J. Sun.",
                        "Kaiming He, Xiangyu Zhang, Shaoqing Ren, and Jian Sun.", "He, K., Zhang, X., et al."):
            line = f"[1] {authors} Deep residual learning for image recognition. CVPR 2016. doi:10.1109/CVPR.2016.90"
            rec = self.check(line + "\n[2] Other A. Another reference that is long enough. 2015.", parse=cr.parse_reference_lines)
            self.assertEqual(rec.status, cr.CONFIRMED, authors)

    def test_a_plain_text_reference_that_does_not_name_the_first_author_is_a_mismatch(self):
        line = "[1] Hinton G, LeCun Y. Deep residual learning for image recognition. CVPR 2016. doi:10.1109/CVPR.2016.90"
        rec = self.check(line + "\n[2] Other A. Another reference that is long enough. 2015.", parse=cr.parse_reference_lines)
        self.assertEqual(rec.status, cr.MISMATCH)
        self.assertIn("first author differs", rec.note)

    def test_an_arxiv_record_names_its_first_author_in_a_plain_line(self):
        line = "[2] Vaswani A, Shazeer N, et al. Attention is all you need. arXiv:1706.03762; 2017."
        rec = self.check(line + "\n[3] Other A. Another reference that is long enough. 2015.", parse=cr.parse_reference_lines)
        self.assertEqual(rec.status, cr.CONFIRMED)


RZ_RESNET = {"corpusId": 206594692, "title": "Deep Residual Learning for Image Recognition",
             "authors": ["Kaiming He", "X. Zhang", "Shaoqing Ren"], "authorCount": 4, "year": 2015,
             "venue": "CVPR", "doi": "10.1109/CVPR.2016.90", "arxiv": "1512.03385",
             "hasReadablePdf": True, "readerUrl": "https://app.researchzy.com/read/c/206594692"}


class ResearchzyTests(Base):
    def test_a_researchzy_title_match_settles_what_the_registries_left_open(self):
        rec = self.check(bib("he2016", "Deep Residual Learning for Image Recognition", RESNET_AUTHORS, 2016),
                         researchzy=[cr._researchzy_paper(RZ_RESNET)])
        self.assertEqual((rec.status, rec.found["source"]), (cr.CONFIRMED, "researchzy"))
        self.assertEqual(rec.researchzy["corpusId"], 206594692)
        self.assertTrue(rec.researchzy["hasReadablePdf"])

    def test_a_researchzy_record_with_the_cited_doi_confirms_when_crossref_is_down(self):
        self.net.down = ("api.crossref.org",)
        rec = self.check(bib("he2016", "Deep Residual Learning for Image Recognition", RESNET_AUTHORS, 2016,
                             doi="10.1109/CVPR.2016.90"), researchzy=[cr._researchzy_paper(RZ_RESNET)])
        self.assertEqual(rec.status, cr.CONFIRMED)

    def test_no_papers_from_researchzy_is_not_a_refutation(self):
        rec = self.check(bib("he2016", "Deep Residual Learning for Image Recognition", RESNET_AUTHORS, 2016),
                         researchzy=[])
        self.assertEqual(rec.status, cr.UNCONFIRMED)
        self.assertIn("Researchzy search returned no papers", rec.evidence)

    def test_a_researchzy_paper_by_other_authors_is_only_a_candidate(self):
        rec = self.check(bib("x2016", "Deep Residual Learning for Image Recognition", "Marlowe, Tessa", 2016),
                         researchzy=[cr._researchzy_paper(RZ_RESNET)])
        self.assertEqual(rec.status, cr.UNCONFIRMED)
        self.assertEqual(rec.candidates[0]["corpusId"], 206594692)

    def test_full_names_match_in_either_order(self):
        self.assertTrue(cr.soft_first_author_agrees("Zhang", ["Wei Zhang"]))
        self.assertTrue(cr.soft_first_author_agrees("Zhang", ["Zhang Wei"]))
        self.assertTrue(cr.soft_first_author_agrees("van der Berg", ["Anna van der Berg"]))
        self.assertFalse(cr.soft_first_author_agrees("Li", ["Hannah Williams", "K. Lin"]))
        self.assertIsNone(cr.soft_first_author_agrees("", ["Wei Zhang"]))

    def test_saved_results_are_read_in_both_layouts(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "r.json"
            path.write_text(json.dumps({"results": {"he2016": [RZ_RESNET], "x": []}}))
            self.assertEqual(sorted(cr.load_researchzy(path)), ["he2016", "x"])
            path.write_text(json.dumps([{"ref_id": "he2016", "results": [dict(RZ_RESNET, authors=[{"name": "Kaiming He"}])]}]))
            self.assertEqual(cr.load_researchzy(path)["he2016"][0]["authors"], ["Kaiming He"])

    def test_references_already_looked_up_are_not_asked_for_again(self):
        rec = self.check(bib("he2016", "Deep Residual Learning for Image Recognition", RESNET_AUTHORS, 2016),
                         researchzy=[])
        self.assertEqual(cr.researchzy_lookups([rec], {"he2016": []})["needed"], [])
        self.assertEqual(len(cr.researchzy_lookups([rec], {})["needed"]), 1)


class ParsingTests(unittest.TestCase):
    def test_bibtex_forms(self):
        text = """@string{cvpr = "CVPR"}
@comment{ignored}
@article(paren2020,
  title = "A quoted title",
  author = "Doe, Jane",
  date = {2020-05-01},
  doi = "10.1000/XYZ"
)
  @inproceedings {last2019,
  author = {{von Deimling}, Andreas and Garc{\\'i}a-L{\\'o}pez, Mar{\\'\\i}a},
  title = {A {B}ayesian {T}itle with \\emph{emphasis}},
  year = 2019,
  url = {https://arxiv.org/abs/1901.00001v2}
}"""
        first, second = cr.parse_bib(text)
        self.assertEqual((first.ref_id, first.title_guess, first.year_guess, first.doi),
                         ("paren2020", "A quoted title", "2020", "10.1000/xyz"))
        self.assertEqual((second.ref_id, second.title_guess, second.year_guess, second.arxiv),
                         ("last2019", "A Bayesian Title with emphasis", "2019", "1901.00001v2"))
        self.assertEqual(second.cited_authors, ["von Deimling", "Garcia-Lopez"])

    def test_latex_is_read_as_text(self):
        self.assertEqual(cr.delatex("Schr{\\\"o}dinger and Erd\\H{o}s at Stra\\ss e \\& M{\\o}ller"),
                         "Schrodinger and Erdos at Strasse & Moller")
        self.assertEqual(cr.strip_latex("J.~Doe. \\newblock A title. \\emph{Journal}, 2020. % note\n\\url{https://x.org/a_b}"),
                         "J. Doe. A title. Journal, 2020. https://x.org/a_b")

    def test_a_numbered_list_keeps_its_numbers_and_an_unnumbered_one_is_counted(self):
        text = "Intro text.\n\n## References\n\n[3] Doe J. A first reference of some length. J Test. 2020. doi:10.1000/a\n" \
               "[7] Roe R. A second reference of some length. arXiv:2101.00001. 2021.\n\n## Appendix\nNot a reference."
        records = cr.parse_reference_lines(text)
        self.assertEqual([(r.ref_id, r.doi, r.arxiv) for r in records],
                         [("ref_3", "10.1000/a", ""), ("ref_7", "", "2101.00001")])
        records = cr.parse_reference_lines("- Doe J. A first reference of some length. 2020.\n- Roe R. A second one, long too. 2021.")
        self.assertEqual([r.ref_id for r in records], ["ref_1", "ref_2"])

    def test_bibitems(self):
        tex = "\\begin{thebibliography}{9}\n\\bibitem[Doe(2020)]{doe2020} J.~Doe. \\newblock A title of some words here. " \
              "\\emph{J. Test}, 2020. \\doi{10.1000/a}\n\\bibitem{roe2021} R. Roe. Another title. 2021.\n\\end{thebibliography}"
        records = cr.parse_bibitems(tex)
        self.assertEqual([(r.ref_id, r.doi, r.year_guess) for r in records],
                         [("doe2020", "10.1000/a", "2020"), ("roe2021", "", "2021")])

    def test_the_bib_files_a_latex_source_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "refs.bib").write_text("")
            found = cr.tex_bib_files("% \\bibliography{old}\n\\bibliography{refs,missing}", Path(tmp))
            self.assertEqual([p.name for p in found], ["refs.bib"])

    def test_a_field_is_replaced_or_added(self):
        entry = '@article{k,\n  title = {A {B} c},\n  year = 2019,\n  note = "x"\n}'
        self.assertIn("title = {New}", cr.set_bib_field(entry, "title", "New"))
        self.assertIn("year = {2020},", cr.set_bib_field(entry, "year", "2020"))
        self.assertIn('note = {y}\n}', cr.set_bib_field(entry, "note", "y"))
        added = cr.set_bib_field(entry, "doi", "10.1/x")
        self.assertTrue(added.endswith('note = "x",\n  doi = {10.1/x}\n}'), added)

    def test_duplicates_and_placeholders(self):
        records = cr.parse_bib(
            bib("a", "The same title of a paper", "Doe, Jane", 2020, doi="10.1000/ABC")
            + bib("b", "Another title of a paper", "Doe, Jane", 2020, doi="https://doi.org/10.1000/abc/")
            + bib("c", "The Same Title of a Paper", "Doe, Jane", 2020)
            + bib("d", "Wave propagation in pressure vessels", "Roe, R.", 2021, note="in press")
            + bib("e", "A study conducted in pressure chambers", "Roe, R.", 2021))
        self.assertEqual([d["ref_ids"] for d in cr.detect_duplicates(records)], [["a", "b"]])
        self.assertEqual([d["ref_ids"] for d in cr.detect_title_duplicates(records)], [["a", "c"]])
        for record in records:
            cr.flag_placeholder(record)
        self.assertEqual([r.ref_id for r in records if r.flags], ["d"])


class CitationTests(unittest.TestCase):
    def find(self, name, text, ref_ids):
        return cr.find_citations(Path(name), text, set(ref_ids))

    def test_latex_citations(self):
        tex = "\\documentclass{article} % \\cite{preamble}\n\\begin{document}\n" \
              "Error fell to 3.57\\%~\\cite{he2016}. % \\cite{commented}\n" \
              "As Smith et al. (2020) argue, attention suffices \\citep[see][p. 3]{vaswani2017, he2016}.\n\n" \
              "Later text. \\nocite{quiet}\n\\bibliography{refs}\n\\cite{after}\n\\end{document}"
        citations, cited = self.find("main.tex", tex, ["he2016", "vaswani2017", "quiet"])
        self.assertEqual(cited, {"he2016", "vaswani2017", "quiet"})
        self.assertEqual([(c["ref_id"], c["line"], c["check"]) for c in citations],
                         [("he2016", 3, True), ("vaswani2017", 4, False), ("he2016", 4, False)])
        self.assertEqual(citations[0]["sentence"], "Error fell to 3.57\\%~\\cite{he2016}.")
        self.assertTrue(citations[1]["sentence"].startswith("As Smith et al. (2020) argue"))

    def test_pandoc_citations(self):
        md = "The model is the first of its kind [@doe2020; @roe2021, p. 4]. See @fig:setup and mail a@b.org.\n\n" \
             "# References\n\n[@late2000]"
        citations, cited = self.find("paper.md", md, ["doe2020", "roe2021"])
        self.assertEqual(cited, {"doe2020", "roe2021"})
        self.assertEqual(citations[0]["why"], ["priority"])

    def test_numeric_citations_of_a_numbered_list(self):
        text = "Accuracy improved by 12% [3, 5-7]. Nothing here.\n\nReferences\n[3] Doe J. A reference."
        citations, cited = self.find("paper.txt", text, [f"ref_{n}" for n in (3, 5, 6, 7)])
        self.assertEqual(cited, {"ref_3", "ref_5", "ref_6", "ref_7"})
        self.assertEqual({c["sentence"] for c in citations}, {"Accuracy improved by 12% [3, 5-7]."})


class ClientTests(Base):
    def test_definite_answers_are_cached_and_failures_are_not(self):
        url = "https://api.crossref.org/works/10.1109/cvpr.2016.90"
        self.assertEqual(cr.CLIENT.get(url)[0], 200)
        self.assertEqual(cr.CLIENT.get(url)[0], 200)
        self.assertEqual(len(self.net.calls), 1)
        self.net.down = ("doi.org",)
        cr.CLIENT.get("https://doi.org/api/handles/10.1/x")
        cr.CLIENT.get("https://doi.org/api/handles/10.1/x")
        self.assertEqual(len(self.net.calls), 3)

    def test_a_busy_registry_is_asked_once_more(self):
        self.net.status = {"api.crossref.org": 429}
        self.assertEqual(cr.CLIENT.get("https://api.crossref.org/works/10.1/x")[0], 429)
        self.assertEqual(len(self.net.calls), 2)

    def test_the_contact_address_is_only_sent_when_given(self):
        cr.CLIENT.contact = ""
        self.assertNotIn("mailto", cr.CLIENT.user_agent())
        cr.CLIENT.contact = "me@example.org"
        self.assertIn("mailto:me@example.org", cr.CLIENT.user_agent())
        cr.CLIENT.contact = ""


class EndToEndTests(Base):
    def run_main(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        old = sys.argv
        sys.argv = ["check_references.py", *argv]
        try:
            with redirect_stdout(out), redirect_stderr(err):
                code = cr.main()
        finally:
            sys.argv = old
        return code, out.getvalue()

    def test_a_latex_project(self):
        self.net.search = [ALEXNET]
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "refs.bib").write_text(
                bib("he2016", "Deep Residual Learning for Image Recognition", RESNET_AUTHORS, 2016, doi="10.1109/CVPR.2016.90")
                + bib("krizhevsky2012", "ImageNet Classification with Deep Convolutional Neural Networks",
                      "Krizhevsky, Alex and Sutskever, Ilya and Hinton, Geoffrey E.", 2017, doi="10.1038/nature14539")
                + bib("x2023", "Quantum gravitational effects on avian migration", "Marlowe, Tessa", 2023,
                      doi="10.1234/jir.2023.99999"))
            (tmp / "main.tex").write_text("\\begin{document}\nError fell to 3.57\\% \\cite{he2016}. "
                                          "Earlier work \\cite{krizhevsky2012,nokey}.\n\\bibliography{refs}\n\\end{document}")
            code, printed = self.run_main(str(tmp / "main.tex"), "--out", str(tmp / "out"))
            self.assertEqual(code, 0)
            summary = json.loads(printed)
            self.assertEqual(summary["counts"], {cr.CONFIRMED: 1, cr.MISMATCH: 1, cr.NOT_REGISTERED: 1})
            audit = json.loads((tmp / "out" / "references.json").read_text())
            self.assertEqual(audit["citation_keys"], {"missing": ["nokey"], "uncited": ["x2023"]})
            self.assertEqual(sorted(audit["source_sha256"]), ["main.tex", "refs.bib"])
            self.assertNotIn("entry", audit["records"][0])
            report = (tmp / "out" / "report.md").read_text()
            self.assertIn("### `x2023` — identifier not registered", report)
            self.assertIn("the DOI belongs to a different work. It resolves to: Deep learning", report)
            self.assertIn("doi = {10.1145/3065386}", (tmp / "out" / "fixes.bib").read_text())
            self.assertEqual([i["ref_id"] for i in json.loads((tmp / "out" / "lookups.json").read_text())["needed"]],
                             ["x2023"])
            # A second run answers from the cache, and --strict reports what is left.
            calls = len(self.net.calls)
            code, _ = self.run_main(str(tmp / "main.tex"), "--out", str(tmp / "out"), "--strict")
            self.assertEqual((code, len(self.net.calls)), (1, calls))

    def test_offline_looks_nothing_up(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "refs.bib").write_text(bib("he2016", "Deep Residual Learning", RESNET_AUTHORS, 2016, doi="10.1109/CVPR.2016.90"))
            code, printed = self.run_main(str(tmp / "refs.bib"), "--out", str(tmp / "out"), "--offline")
            self.assertEqual((code, self.net.calls), (0, []))
            self.assertEqual(json.loads(printed)["counts"], {cr.UNCONFIRMED: 1})


if __name__ == "__main__":
    unittest.main()
