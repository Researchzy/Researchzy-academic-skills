"""check_figure.py: size, smallest text, fonts, resolution and colours of an exported file.

The files are built by hand here, so these tests need neither matplotlib nor a PDF library; the
colour tests need Pillow and skip without it.
"""
from __future__ import annotations

import hashlib
import importlib.util
import io
import itertools
import json
import struct
import sys
import tempfile
import unittest
import zlib
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).parents[1] / "scripts" / "check_figure.py"
spec = importlib.util.spec_from_file_location("check_figure", SCRIPT)
cf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cf)

try:
    import PIL  # noqa: F401
    HAVE_PILLOW = True
except ImportError:
    HAVE_PILLOW = False

MM = 72 / 25.4      # points per millimetre
EMBEDDED = [b"<< /Type /Font /Subtype /TrueType /BaseFont /ABCDEF+Arial /FontDescriptor 6 0 R >>",
            b"<< /Type /FontDescriptor /FontName /ABCDEF+Arial /FontFile2 7 0 R >>",
            b"<< /Length1 4 /Length 4 >>\nstream\nABCD\nendstream"]
COMPOSITE = [b"<< /Type /Font /Subtype /Type0 /BaseFont /LiberationSans /DescendantFonts [6 0 R] >>",
             b"<< /Type /Font /Subtype /CIDFontType2 /BaseFont /LiberationSans /FontDescriptor 7 0 R >>",
             b"<< /Type /FontDescriptor /FontFile2 8 0 R >>"]
TYPE3 = [b"<< /Type /Font /Subtype /Type3 /BaseFont /DejaVuSans /CharProcs << >> >>"]
NOT_EMBEDDED = [b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
LABELS = b"BT /F1 8 Tf 20 20 Td (Time \\(weeks\\)) Tj ET BT /F1 7.5 Tf 20 40 Td [(1) -20 (0)] TJ ET"


def pdf(content: bytes = LABELS, width_mm: float = 89, height_mm: float = 60, fonts=EMBEDDED,
        stream_filter: bytes = b"", extra=()) -> bytes:
    """A one-page PDF with one content stream and the given font objects (numbered from 5)."""
    payload = zlib.compress(content) if stream_filter == b"FlateDecode" else content
    name = b"/Filter /" + stream_filter + b" " if stream_filter else b""
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
               b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %.2f %.2f] /Contents 4 0 R "
               b"/Resources << /Font << /F1 5 0 R >> >> >>" % (width_mm * MM, height_mm * MM),
               b"<< " + name + b"/Length %d >>\nstream\n" % len(payload) + payload + b"\nendstream",
               *fonts, *extra]
    return b"%PDF-1.4\n" + b"".join(b"%d 0 obj\n%s\nendobj\n" % (i, body) for i, body in enumerate(objects, 1)) + b"%%EOF\n"


def png(pixels: list, dpi=300) -> bytes:
    """A PNG from rows of (r, g, b) tuples, with a pHYs chunk when dpi is given."""
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    raw = b"".join(b"\x00" + bytes(v for pixel in row for v in pixel) for row in pixels)
    out = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", len(pixels[0]), len(pixels), 8, 2, 0, 0, 0))
    if dpi:
        out += chunk(b"pHYs", struct.pack(">IIB", round(dpi / 0.0254), round(dpi / 0.0254), 1))
    return out + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


def canvas(width: int = 240, height: int = 120, colour=(255, 255, 255)) -> list:
    return [[colour] * width for _ in range(height)]


def block(pixels: list, colour: tuple, left: int, top: int, width: int = 40, height: int = 40) -> list:
    for y in range(top, top + height):
        pixels[y][left:left + width] = [colour] * width
    return pixels


def rgb(code: str) -> tuple:
    return tuple(int(code[i:i + 2], 16) for i in (1, 3, 5))


def tiff(width: int, height: int, resolution: int, unit: int = 2, order: str = "<") -> bytes:
    """The header and first directory of a TIFF: enough for its size and resolution."""
    short = (lambda v: struct.pack(order + "HH", v, 0))
    entries = [(256, 4, struct.pack(order + "I", width)), (257, 4, struct.pack(order + "I", height)),
               (282, 5, struct.pack(order + "I", 8 + 2 + 4 * 12 + 4)), (296, 3, short(unit))]
    body = struct.pack(order + "H", len(entries)) + b"".join(
        struct.pack(order + "HHI", tag, kind, 1) + value for tag, kind, value in entries) + struct.pack(order + "I", 0)
    head = (b"II*\x00" if order == "<" else b"MM\x00*") + struct.pack(order + "I", 8)
    return head + body + struct.pack(order + "II", resolution, 1)


OKABE_ITO = ["#000000", "#E69F00", "#56B4E9", "#009E73", "#F0E442", "#0072B2", "#D55E00", "#CC79A7"]


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name: str, data: bytes) -> Path:
        path = self.dir / name
        path.write_bytes(data)
        return path

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cf.main([str(a) for a in argv])
        return code, (json.loads(out.getvalue()) if out.getvalue() else err.getvalue())

    def checks(self, *argv, file: int = 0) -> dict:
        code, result = self.run_cli(*argv)
        found = {c["check"]: c for c in result["files"][file]["checks"]}
        found["_code"], found["_result"] = code, result
        return found


class PdfTests(Base):
    def test_width_is_compared_with_the_print_width(self):
        path = self.write("fig.pdf", pdf())
        good = self.checks(path, "--width-mm", "89")
        self.assertEqual((good["width"]["status"], good["_result"]["files"][0]["width_mm"]), ("PASS", 89.0))
        self.assertEqual(self.checks(path, "--width-mm", "89.8")["width"]["status"], "PASS")       # within 1 mm
        self.assertEqual(self.checks(path, "--width-mm", "183")["width"]["status"], "FAIL")
        # Nothing to compare with is not a pass.
        self.assertEqual(self.checks(path)["width"]["status"], "NOT_CHECKED")

    def test_smallest_text_is_read_from_the_text_operators(self):
        good = self.checks(self.write("fig.pdf", pdf()), "--width-mm", "89")["min_font_size"]
        self.assertEqual((good["status"], good["smallest_pt"], good["sizes_pt"]), ("PASS", 7.5, {"7.5": 1, "8": 1}))
        content = (LABELS + b" BT /F1 4 Tf 5 5 Td (tiny note) Tj ET"                        # a 4 pt label
                   b" q 0.5 0 0 0.5 0 0 cm BT /F1 9 Tf (halved) Tj ET Q"                     # 9 pt drawn at half scale
                   b" BT /F1 1 Tf 12 0 0 12 50 50 Tm (matrix) Tj ET"                         # size carried by the text matrix
                   b" BT /F1 8 Tf (after Q) Tj ET")
        bad = self.checks(self.write("bad.pdf", pdf(content)), "--width-mm", "89")
        self.assertEqual((bad["_code"], bad["min_font_size"]["status"], bad["min_font_size"]["smallest_pt"]), (1, "FAIL", 4.0))
        self.assertEqual([(row["size_pt"], row["text"]) for row in bad["min_font_size"]["below"]],
                         [(4.0, ["tiny note"]), (4.5, ["halved"])])
        self.assertEqual(bad["min_font_size"]["sizes_pt"], {"4": 1, "4.5": 1, "7.5": 1, "8": 2, "12": 1})
        # A stricter venue.
        self.assertEqual(self.checks(self.dir / "fig.pdf", "--width-mm", "89", "--min-pt", "8")["min_font_size"]["status"], "FAIL")

    def test_text_is_judged_at_the_print_width(self):
        # 8 pt text on a page twice as wide as the column is 4 pt once it is placed in the column.
        wide = self.checks(self.write("wide.pdf", pdf(width_mm=178)), "--width-mm", "89")
        self.assertEqual((wide["width"]["status"], wide["min_font_size"]["status"]), ("FAIL", "FAIL"))
        self.assertEqual(wide["min_font_size"]["smallest_pt"], 3.75)
        self.assertEqual(self.checks(self.dir / "wide.pdf")["min_font_size"]["status"], "PASS")     # as drawn

    def test_compressed_streams_are_read_and_unreadable_ones_are_not_a_pass(self):
        packed = self.checks(self.write("flate.pdf", pdf(stream_filter=b"FlateDecode")), "--width-mm", "89")
        self.assertEqual((packed["min_font_size"]["status"], packed["min_font_size"]["smallest_pt"]), ("PASS", 7.5))
        other = self.checks(self.write("lzw.pdf", pdf(stream_filter=b"LZWDecode")), "--width-mm", "89")
        self.assertEqual(other["min_font_size"]["status"], "NOT_CHECKED")
        self.assertIn("could not be decoded", other["min_font_size"]["detail"])
        self.assertEqual(other["_code"], 0)

    def test_text_drawn_as_outlines_cannot_be_measured(self):
        outlines = self.checks(self.write("paths.pdf", pdf(b"0 0 m 10 10 l S", fonts=[])), "--width-mm", "89")
        self.assertEqual((outlines["min_font_size"]["status"], outlines["fonts"]["status"]), ("NOT_CHECKED", "NOT_CHECKED"))
        # Operators outside BT ... ET, as in binary data, are not text.
        stray = self.checks(self.write("stray.pdf", pdf(b"/F1 2 Tf (x) Tj", fonts=[])), "--width-mm", "89")
        self.assertEqual(stray["min_font_size"]["status"], "NOT_CHECKED")

    def test_two_byte_strings_are_named_in_the_report(self):
        minus_one = "−1".encode("utf-16-be").replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")
        content = (b"BT /F1 8 Tf (" + "Dose (mg)".encode("utf-16-be").replace(b"(", b"\\(").replace(b")", b"\\)")
                   + b") Tj ET BT /F1 3.5 Tf (" + minus_one + b") Tj ET")
        found = self.checks(self.write("wide.pdf", pdf(content, fonts=COMPOSITE)), "--width-mm", "89")
        self.assertEqual(found["min_font_size"]["below"], [{"size_pt": 3.5, "count": 1, "text": ["−1"]}])

    def test_fonts_must_be_embedded_and_not_type_3(self):
        def fonts(objects):
            return self.checks(self.write("f.pdf", pdf(fonts=objects)), "--width-mm", "89")["fonts"]

        self.assertEqual((fonts(EMBEDDED)["status"], fonts(EMBEDDED)["fonts"]),
                         ("PASS", [{"name": "Arial", "type": "TrueType", "embedded": True}]))
        self.assertEqual(fonts(COMPOSITE)["status"], "PASS")
        self.assertEqual(fonts(TYPE3)["status"], "FAIL")
        self.assertIn("Type 3", fonts(TYPE3)["detail"])
        self.assertEqual(fonts(NOT_EMBEDDED)["status"], "FAIL")
        self.assertIn("not embedded (Helvetica)", fonts(NOT_EMBEDDED)["detail"])
        # A descriptor that cannot be found is unknown, not embedded and not missing.
        self.assertEqual(fonts(EMBEDDED[:1])["status"], "NOT_CHECKED")

    def test_objects_inside_an_object_stream_are_found(self):
        page = b"<< /Type /Page /MediaBox [0 0 %.2f 170] /Contents 4 0 R >>" % (89 * MM)
        font = NOT_EMBEDDED[0]
        index = b"3 0 5 %d " % (len(page) + 1)
        packed = zlib.compress(index + page + b" " + font)
        objects = {1: b"<< /Type /Catalog >>", 4: b"<< /Length %d >>\nstream\n%s\nendstream" % (len(LABELS), LABELS),
                   9: b"<< /Type /ObjStm /N 2 /First %d /Filter /FlateDecode /Length %d >>\nstream\n%s\nendstream"
                      % (len(index), len(packed), packed)}
        data = b"%PDF-1.5\n" + b"".join(b"%d 0 obj\n%s\nendobj\n" % item for item in objects.items())
        found = self.checks(self.write("objstm.pdf", data), "--width-mm", "89")
        self.assertEqual((found["width"]["status"], found["min_font_size"]["status"], found["fonts"]["status"]),
                         ("PASS", "PASS", "FAIL"))

    def test_raster_images_inside_a_pdf_are_reported_not_passed(self):
        self.assertEqual(self.checks(self.write("v.pdf", pdf()))["images"]["status"], "PASS")
        image = b"<< /Type /XObject /Subtype /Image /Width 600 /Height 400 /Length 3 >>\nstream\nabc\nendstream"
        inside = self.checks(self.write("r.pdf", pdf(extra=[image])))["images"]
        self.assertEqual(inside["status"], "NOT_CHECKED")
        self.assertIn("600 x 400 px", inside["detail"])

    def test_a_pdf_alone_says_that_colours_were_not_checked(self):
        pdf_path, png_path = self.write("fig.pdf", pdf()), self.write("fig.png", png(canvas()))
        alone = self.checks(pdf_path)
        self.assertEqual(alone["colours"]["status"], "NOT_CHECKED")
        self.assertNotIn("colours", self.checks(pdf_path, png_path))       # the PNG of the same figure covers it


class RasterTests(Base):
    def test_png_width_and_resolution(self):
        path = self.write("fig.png", png(canvas(1051, 30)))            # 89 mm at 300 dpi
        good = self.checks(path, "--width-mm", "89")
        self.assertEqual((good["width"]["status"], good["resolution"]["status"]), ("PASS", "PASS"))
        self.assertEqual(good["_result"]["files"][0]["width_px"], 1051)
        wide = self.checks(path, "--width-mm", "183")                      # too few pixels for a double column
        self.assertEqual((wide["width"]["status"], wide["resolution"]["status"], wide["_code"]), ("FAIL", "FAIL", 1))
        self.assertIn("146 dpi", wide["resolution"]["detail"])
        self.assertEqual(self.checks(path, "--width-mm", "89", "--min-dpi", "600")["resolution"]["status"], "FAIL")
        self.assertEqual(self.checks(path)["width"]["status"], "NOT_CHECKED")
        self.assertEqual(self.checks(path)["resolution"]["status"], "PASS")    # the stated 300 dpi

    def test_png_without_resolution_metadata(self):
        path = self.write("bare.png", png(canvas(1051, 30), dpi=None))
        bare = self.checks(path)
        self.assertEqual((bare["width"]["status"], bare["resolution"]["status"]), ("NOT_CHECKED", "NOT_CHECKED"))
        placed = self.checks(path, "--width-mm", "89")
        self.assertEqual((placed["width"]["status"], placed["resolution"]["status"]), ("NOT_CHECKED", "PASS"))

    def test_tiff_size_and_resolution(self):
        for order in "<>":
            inch = self.checks(self.write("a.tiff", tiff(2102, 900, 600, 2, order)), "--width-mm", "89", "--min-dpi", "600")
            self.assertEqual((inch["width"]["status"], inch["resolution"]["status"]), ("PASS", "PASS"), order)
        per_cm = self.checks(self.write("b.tif", tiff(1051, 400, 118, 3)), "--width-mm", "89")      # 118 px/cm is 300 dpi
        self.assertEqual((per_cm["width"]["status"], per_cm["resolution"]["status"]), ("PASS", "PASS"))
        self.assertEqual(per_cm["colour_vision"]["status"], "NOT_CHECKED")     # no pixel data in this stub

    def test_unreadable_files_stop_with_exit_code_2(self):
        self.assertEqual(self.run_cli(self.write("notes.txt", b"not a figure"))[0], 2)
        self.assertEqual(self.run_cli(self.dir / "missing.pdf")[0], 2)
        self.assertEqual(self.run_cli(self.write("fig.pdf", pdf()), "--width-mm", "0")[0], 2)


class ColourMathTests(unittest.TestCase):
    def test_simulation_matrices_keep_greys_and_white(self):
        for name, matrix in cf.CVD_MATRICES.items():
            for row in matrix:
                self.assertAlmostEqual(sum(row), 1.0, places=5, msg=name)
            self.assertEqual([round(v, 4) for v in cf.simulate((0.5, 0.5, 0.5), name)], [0.5, 0.5, 0.5])
        white = cf.lab((1.0, 1.0, 1.0))
        self.assertAlmostEqual(white[0], 100.0, places=2)
        self.assertAlmostEqual(abs(white[1]) + abs(white[2]), 0.0, places=2)
        self.assertAlmostEqual(cf.lab(tuple(cf.linear(c) for c in (255, 0, 0)))[0], 53.24, places=1)   # sRGB red

    def test_red_and_green_merge_for_a_dichromat(self):
        confusable, same_grey = cf.compare_colours([rgb("#D62728"), rgb("#2CA02C")])
        self.assertEqual([(c["under"], c["delta_e"]) for c in confusable], [("deuteranopia", 7.3)])
        self.assertEqual(same_grey, [])

    def test_the_palette_survives_simulation_and_its_first_four_survive_grayscale(self):
        colours = [rgb(code) for code in OKABE_ITO]
        confusable, same_grey = cf.compare_colours(colours)
        self.assertEqual(confusable, [])
        self.assertIn(["#E69F00", "#56B4E9"], [pair["pair"] for pair in same_grey])     # orange and sky blue: one grey
        first_four = [rgb(code) for code in ("#0072B2", "#E69F00", "#009E73", "#000000")]
        self.assertEqual(cf.compare_colours(first_four), ([], []))

    def test_colours_that_already_look_alike_are_not_reported(self):
        self.assertEqual(cf.compare_colours([rgb("#CCCCCC"), rgb("#D6D6D6"), rgb("#000000")]), ([], []))

    def test_a_mix_lies_between_its_two_colours(self):
        self.assertTrue(cf.is_mix((128, 185, 217), (255, 255, 255), (0, 114, 178)))     # half-covered blue edge
        self.assertFalse(cf.is_mix((86, 180, 233), (255, 255, 255), (0, 114, 178)))     # sky blue is its own colour
        self.assertFalse(cf.is_mix((0, 60, 100), (255, 255, 255), (0, 114, 178)))       # beyond the end


@unittest.skipUnless(HAVE_PILLOW, "Pillow is not installed")
class ColourTests(Base):
    def colours(self, pixels: list) -> dict:
        return self.checks(self.write("fig.png", png(pixels)))

    def test_safe_colours_pass_both_checks(self):
        pixels = canvas()
        for i, code in enumerate(("#0072B2", "#E69F00", "#009E73", "#000000")):
            block(pixels, rgb(code), 10 + 50 * i, 20)
        found = self.colours(pixels)
        self.assertEqual((found["colour_vision"]["status"], found["grayscale"]["status"]), ("PASS", "PASS"))
        self.assertEqual(sorted(found["colour_vision"]["colours"]), ["#000000", "#0072B2", "#009E73", "#E69F00"])

    def test_red_and_green_fail_and_the_pair_is_named(self):
        found = self.colours(block(block(canvas(), rgb("#D62728"), 10, 20), rgb("#2CA02C"), 80, 20))
        self.assertEqual((found["colour_vision"]["status"], found["_code"]), ("FAIL", 1))
        self.assertEqual(found["colour_vision"]["confusable"],
                         [{"pair": ["#D62728", "#2CA02C"], "under": "deuteranopia", "delta_e": 7.3}])
        self.assertEqual(found["grayscale"]["status"], "PASS")

    def test_equal_lightness_fails_in_grayscale_only(self):
        found = self.colours(block(block(canvas(), rgb("#E69F00"), 10, 20), rgb("#56B4E9"), 80, 20))
        self.assertEqual((found["colour_vision"]["status"], found["grayscale"]["status"]), ("PASS", "FAIL"))
        self.assertEqual(found["grayscale"]["same_grey"], [{"pair": ["#E69F00", "#56B4E9"], "delta_l": 0.8}])

    def test_thin_lines_and_anti_aliased_edges(self):
        pixels = canvas()
        for y in range(10, 110):                       # two one-pixel lines: no flat area at all
            pixels[y][30], pixels[y][31] = rgb("#D62728"), (235, 147, 148)       # the line and its half-covered edge
            pixels[y][90], pixels[y][91] = rgb("#2CA02C"), (150, 208, 150)
        found = self.colours(pixels)
        self.assertEqual(sorted(found["colour_vision"]["colours"]), ["#2CA02C", "#D62728"])
        self.assertEqual(found["colour_vision"]["status"], "FAIL")

    def test_one_colour_has_no_pair(self):
        found = self.colours(block(canvas(), (0, 0, 0), 10, 20))
        self.assertEqual((found["colour_vision"]["status"], found["colour_vision"]["colours"]), ("PASS", ["#000000"]))

    def test_what_cannot_be_listed_is_not_checked(self):
        blank = self.colours(canvas())
        self.assertEqual(blank["colour_vision"]["status"], "NOT_CHECKED")
        ramp = canvas()                                 # a continuous colour scale
        for step in range(60):
            block(ramp, (255 - 4 * step, 4 * step, (37 * step) % 256), 2 * step, 0, 2, 120)
        self.assertEqual(self.colours(ramp)["grayscale"]["status"], "NOT_CHECKED")
        speckle = canvas(120, 60)                       # no colour covers enough pixels
        for i, (x, y) in enumerate(itertools.product(range(0, 120, 2), range(0, 60, 2))):
            speckle[y][x] = (i * 7 % 256, i * 13 % 256, i * 29 % 256)
        self.assertEqual(self.colours(speckle)["colour_vision"]["status"], "NOT_CHECKED")

    def test_without_pillow_colours_are_not_checked(self):
        path = self.write("fig.png", png(block(canvas(), (0, 0, 0), 10, 20)))
        with mock.patch.dict(sys.modules, {"PIL": None}):
            found = self.checks(path)
        self.assertEqual((found["colour_vision"]["status"], found["grayscale"]["status"]), ("NOT_CHECKED", "NOT_CHECKED"))
        self.assertIn("Pillow is not installed", found["colour_vision"]["detail"])


class RecordTests(Base):
    def record(self, data: bytes, findings: list) -> None:
        (self.dir / "fig.figure.json").write_text(json.dumps({
            "tool": "researchzy-figures", "outputs": [{"path": "fig.pdf", "sha256": hashlib.sha256(data).hexdigest()}],
            "axis_findings": findings}), encoding="utf-8")

    def test_axis_findings_come_from_the_record_of_exactly_this_file(self):
        data = pdf()
        path = self.write("fig.pdf", data)
        self.assertEqual(self.checks(path)["axes"]["status"], "NOT_CHECKED")             # no record
        self.record(data, [])
        self.assertEqual(self.checks(path)["axes"]["status"], "PASS")
        self.record(data, [{"rule": "bar_not_from_zero", "axes": 0, "detail": "the y axis runs from 50 to 60"}])
        failed = self.checks(path)
        self.assertEqual((failed["axes"]["status"], failed["_code"]), ("FAIL", 1))
        self.assertIn("bar_not_from_zero", failed["axes"]["detail"])
        self.record(data + b" ", [])                                                    # a record of another export
        self.assertEqual(self.checks(path)["axes"]["status"], "NOT_CHECKED")
        (self.dir / "fig.figure.json").write_text("{}", encoding="utf-8")
        self.assertEqual(self.checks(path)["axes"]["status"], "NOT_CHECKED")

    def test_the_summary_counts_every_status(self):
        code, result = self.run_cli(self.write("fig.pdf", pdf()), "--width-mm", "89")
        self.assertEqual((code, result["ok"]), (0, True))
        self.assertEqual(result["counts"], {"PASS": 4, "FAIL": 0, "NOT_CHECKED": 2})    # colours and axes not checked
        self.assertEqual(result["settings"], {"width_mm": 89.0, "tolerance_mm": 1.0, "min_pt": 5.0, "min_dpi": 300.0})


if __name__ == "__main__":
    unittest.main()
