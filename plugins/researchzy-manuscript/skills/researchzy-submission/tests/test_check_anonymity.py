"""check_anonymity.py: what could identify the authors, with file and line; nothing is changed."""
from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import shutil
import sys
import tempfile
import unittest
import zipfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).parents[1] / "scripts" / "check_anonymity.py"
spec = importlib.util.spec_from_file_location("check_anonymity", SCRIPT)
ca = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ca)

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
AUTHORS = {
    "authors": [
        {"name": "Mira Okafor", "name_native": "米拉", "initials": "M.O.", "email": "m.okafor@invented.example",
         "orcid": "0000-0002-1825-0097", "affiliations": ["Department of Ecology, Invented University, Northtown"],
         "handles": ["mokafor"]},
        {"name": "Tomas Lindqvist", "email": "tl1987@gmail.com", "affiliations": ["Example Institute, Southport"]},
    ],
    "funding": [{"funder": "Invented Science Foundation", "grant_number": "ISF-2024-0117"}],
    "ethics": [{"approval_id": "IEB-2023-044"}],
    "registrations": [{"registry": "OSF", "id": "OSF-REG-7781"}],
    "anonymity": {"repositories": ["soil-memory"], "earlier_venues": ["Invented Workshop on Soils 2025"]},
}


def docx(paragraphs, core="", extra=None) -> bytes:
    body = "".join(f"<w:p><w:r><w:t>{p}</w:t></w:r></w:p>" for p in paragraphs)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", f'<w:document xmlns:w="{W_NS}"><w:body>{body}</w:body></w:document>')
        if core:
            archive.writestr("docProps/core.xml", core)
        for name, data in (extra or {}).items():
            archive.writestr(name, data)
    return buffer.getvalue()


def core(creator: str, modified: str = "") -> str:
    return ('<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
            f'xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:creator>{creator}</dc:creator>'
            f"<cp:lastModifiedBy>{modified}</cp:lastModifiedBy></cp:coreProperties>")


def pdf(author: str) -> bytes:
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
               b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] >>",
               b"<< /Author (" + author.encode() + b") /Producer (pdfTeX) >>"]
    out, offsets = b"%PDF-1.4\n", []
    for i, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n%s\nendobj\n" % (i, body)
    xref = len(out)
    out += b"xref\n0 5\n0000000000 65535 f \n" + b"".join(b"%010d 00000 n \n" % o for o in offsets)
    return out + b"trailer\n<< /Size 5 /Root 1 0 R /Info 4 0 R >>\nstartxref\n%d\n%%%%EOF\n" % xref


class AnonymityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name) / "submission" / "invented"
        self.folder.mkdir(parents=True)
        self.write("authors.json", json.dumps(AUTHORS))

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, content):
        path = self.folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content) if isinstance(content, bytes) else path.write_text(content, encoding="utf-8")
        return path

    def run_check(self, *extra):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = ca.main([str(self.folder), *extra])
        return code, (json.loads(out.getvalue()) if out.getvalue() else None)

    def found(self, result, kind=None, file=None):
        return [(h["where"], h["found"]) for h in result["hits"]
                if (kind is None or h["kind"] == kind) and (file is None or h["file"] == file)]

    def test_identifiers_from_the_authors_file(self):
        ids = {(kind, value) for kind, value, _ in ca.identifiers(AUTHORS, ["okafor-lab"])}
        for expected in (("name", "Mira Okafor"), ("name", "米拉"), ("family name", "Okafor"), ("initials", "M.O."),
                         ("initials", "MO"), ("email", "m.okafor@invented.example"), ("email domain", "invented.example"),
                         ("ORCID", "0000-0002-1825-0097"), ("institution", "Invented University"),
                         ("institution", "Department of Ecology"), ("handle", "mokafor"), ("grant number", "ISF-2024-0117"),
                         ("ethics approval id", "IEB-2023-044"), ("registration id", "OSF-REG-7781"),
                         ("repository", "soil-memory"), ("earlier venue", "Invented Workshop on Soils 2025"),
                         ("extra", "okafor-lab")):
            self.assertIn(expected, ids)
        self.assertNotIn(("email domain", "gmail.com"), ids)       # a webmail domain identifies nobody
        self.assertNotIn(("institution", "Northtown"), ids)        # one word: a city, too common to count

    def test_identifiers_in_text_with_context(self):
        self.write("paper.tex", "\\section{Introduction}\n"
                                "Soil memory matters. % ask Mira Okafor for plot 7\n"
                                "Funded by grant ISF-2024-0117 and approved under IEB-2023-044.\n"
                                "Previously presented at the Invented Workshop on Soils 2025.\n"
                                "M. O. and T.L. designed it; MO wrote it; contact m.okafor@invented.example.\n"
                                "米拉的研究\n"
                                "\\begin{thebibliography}{9}\n\\bibitem{a} Okafor M. Soil. 2021.\n")
        code, result = self.run_check()
        self.assertEqual(code, 1)
        hits = [(h["where"], h["found"], h["context"]) for h in result["hits"] if h["kind"] == "identifier"]
        self.assertIn((2, "name: Mira Okafor", "LaTeX comment"), hits)
        self.assertNotIn((2, "family name: Okafor", "LaTeX comment"), hits)          # one hit for the full name
        self.assertIn((3, "grant number: ISF-2024-0117", "text"), hits)
        self.assertIn((3, "ethics approval id: IEB-2023-044", "text"), hits)
        self.assertIn((4, "earlier venue: Invented Workshop on Soils 2025", "text"), hits)
        self.assertIn((5, "initials: M.O.", "text"), hits)
        self.assertIn((5, "initials: MO", "text"), hits)
        self.assertIn((5, "email: m.okafor@invented.example", "text"), hits)
        self.assertNotIn((5, "family name: Okafor", "text"), hits)                    # inside the email address
        self.assertIn((6, "name: 米拉", "text"), hits)
        self.assertIn((8, "family name: Okafor", "reference list"), hits)

    def test_self_citation_phrasing(self):
        self.write("paper.md", "As we showed in our earlier study [12], memory varies.\n"
                               "We previously reported a related effect.\n"
                               "Our previous work on soils (Okafor et al., 2021) found this.\n"
                               "Previous work found no effect (Smith, 2020).\n")
        _, result = self.run_check()
        hits = {h["where"]: h["cited"] for h in result["hits"] if h["kind"] == "self_citation"}
        self.assertEqual(hits, {1: True, 2: False, 3: True})

    def test_acknowledgement_and_funding_sections(self):
        self.write("paper.md", "## Acknowledgements\n\nWe thank the field crew.\n\n**Funding:** none.\n\n"
                               "Funding agencies had no role in the design.\n")
        self.write("paper.tex", "\\section*{Acknowledgments}\n\\begin{acks}\nThanks.\n\\end{acks}\n")
        _, result = self.run_check()
        self.assertEqual([(h["file"], h["where"]) for h in result["hits"] if h["kind"] == "section"],
                         [("paper.md", 1), ("paper.md", 5), ("paper.tex", 1), ("paper.tex", 2)])

    def test_links(self):
        self.write("paper.md", "Code: https://github.com/someone/tool and https://anonymous.4open.science/r/x-1.\n"
                               "See https://www.invented.example/~mokafor/ and https://doi.org/10.1000/xyz.\n"
                               "Data at https://zenodo.org/records/123.\n")
        _, result = self.run_check()
        self.assertEqual(self.found(result, "url"),
                         [(1, "repository link: https://github.com/someone/tool"),
                          (2, "personal or institutional link: https://www.invented.example/~mokafor/"),
                          (3, "repository link: https://zenodo.org/records/123")])

    def test_latex_author_commands(self):
        self.write("paper.tex", "\\author{Anonymous}\n\\author{Mira Okafor}\n\\affiliation{Invented University}\n"
                                "\\title{Soil\\thanks{Supported by the foundation.}}\n\\author{}\n")
        _, result = self.run_check()
        self.assertEqual([where for where, _ in self.found(result, "latex")], [2, 3, 4])

    def test_office_metadata_tracked_changes_and_paths(self):
        document = docx(["Soil memory and seedlings.", "We thank Tomas Lindqvist."], core=core("Mira Okafor", "Microsoft Office User"),
                        extra={"word/comments.xml": f'<w:comments xmlns:w="{W_NS}"><w:comment w:author="mokafor">'
                                                    "<w:p><w:r><w:t>Check with Mira Okafor</w:t></w:r></w:p></w:comment></w:comments>",
                               "word/_rels/document.xml.rels": '<Relationships><Relationship Target="file:///home/mokafor/fig1.png"/>'
                                                               '<Relationship Target="https://github.com/okafor/soil-memory"/></Relationships>',
                               "docProps/app.xml": "<Properties><Company>Invented University</Company></Properties>"})
        self.write("blinded.docx", document)
        self.write("clean.docx", docx(["Nothing here."], core=core("", "python-docx")))
        _, result = self.run_check()
        hits = self.found(result, file="blinded.docx")
        self.assertIn(("docProps/core.xml", "creator: Mira Okafor"), hits)
        self.assertNotIn(("docProps/core.xml", "lastModifiedBy: Microsoft Office User"), hits)
        self.assertIn(("docProps/app.xml", "Company: Invented University"), hits)
        self.assertIn(("word/comments.xml", "tracked-change or comment author: mokafor"), hits)
        self.assertIn(("word/comments.xml", "name: Mira Okafor"), hits)
        self.assertIn(("paragraph 2", "name: Tomas Lindqvist"), hits)
        self.assertTrue(any(kind == "path" for kind in (h["kind"] for h in result["hits"] if h["where"].endswith(".rels"))))
        self.assertIn(("word/_rels/document.xml.rels", "repository link: https://github.com/okafor/soil-memory"), hits)
        self.assertEqual(self.found(result, file="clean.docx"), [])

    def test_pdf_properties(self):
        self.write("paper.pdf", pdf("Mira Okafor"))
        with mock.patch.object(ca.shutil, "which", return_value=None):
            _, result = self.run_check()
        self.assertEqual(result["hits"], [])
        self.assertTrue(any("pdfinfo (Poppler) is not installed" in x for x in result["not_checked"]))
        self.assertTrue(any("PDF text not checked" in x for x in result["not_checked"]))
        if not shutil.which("pdfinfo"):
            self.skipTest("pdfinfo is not installed")
        _, result = self.run_check()
        self.assertIn(("PDF properties", "Author: Mira Okafor (name: Mira Okafor)"), self.found(result, "metadata"))

    def test_file_names_images_and_unreadable_files(self):
        self.write("figures/Okafor_fig1.png", b"\x89PNG\r\n\x1a\n" + b"tEXtAuthor\x00Mira Okafor" + b"\x00" * 50)
        self.write("data.sav", b"\x00\x01")
        self.write(".DS_Store", b"Mira Okafor")
        _, result = self.run_check()
        self.assertIn(("file name", "family name: Okafor"), self.found(result, "file_name"))
        self.assertIn(("image metadata", "name: Mira Okafor"), self.found(result, "metadata"))
        self.assertTrue(any(x.startswith("figures/Okafor_fig1.png: the picture itself") for x in result["not_checked"]))
        self.assertTrue(any(x.startswith("data.sav: a .sav file is not read") for x in result["not_checked"]))
        self.assertNotIn(".DS_Store", result["files_read"])

    def test_identified_and_working_files_are_left_out_and_nothing_is_changed(self):
        title = self.write("title-page.md", "Mira Okafor, Invented University\n")
        self.write("report.md", "Mira Okafor")
        paper = self.write("paper.md", "Soil memory predicts survival.\n")
        before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in self.folder.rglob("*") if p.is_file()}
        code, result = self.run_check("--identified", str(title))
        self.assertEqual((code, result["hits"]), (0, []))
        self.assertIn("title-page.md", result["skipped"])
        self.assertIn("report.md", result["skipped"])
        after = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in before}
        self.assertEqual(before, after)
        self.assertTrue((self.folder / "anonymity.md").is_file())
        code, result = self.run_check()
        self.assertEqual(code, 1)
        self.assertEqual(paper.read_text(encoding="utf-8"), "Soil memory predicts survival.\n")

    def test_extra_identifiers_and_bad_input(self):
        self.write("paper.md", "The Northtown Soil Survey and okafor-lab.\n")
        extra = self.write("ids.txt", "# one per line\nNorthtown Soil Survey\n")
        _, result = self.run_check("--extra", "okafor-lab", "--extra-file", str(extra))
        self.assertEqual({found for _, found in self.found(result, "identifier")},
                         {"extra: okafor-lab", "extra: Northtown Soil Survey"})
        self.assertEqual(self.run_check("--identified", "nope.md")[0], 2)
        self.write("authors.json", "[]")
        self.assertEqual(self.run_check()[0], 2)


if __name__ == "__main__":
    unittest.main()
