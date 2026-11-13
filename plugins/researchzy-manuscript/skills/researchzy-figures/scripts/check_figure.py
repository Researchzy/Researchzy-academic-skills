#!/usr/bin/env python3
"""Check an exported figure file: size, smallest text, fonts, resolution, colours and axis record.

  check_figure.py figures/fig1.pdf figures/fig1.png --width-mm 89
  check_figure.py plot.pdf --width-mm 183 --min-pt 6          a stricter font floor
  check_figure.py scan.tiff --width-mm 89 --min-dpi 600       line art as a raster

The checker reads the exported file, not the plotting code, so it works for a figure made with
any tool (matplotlib, R, a drawing program). --width-mm is the width the figure will have in
print; without it sizes are judged as drawn.

  PDF        width        page width against --width-mm (within --tolerance-mm, default 1)
             min_font_size  smallest glyph at print width against --min-pt (default 5), read from
                          the text operators of the content streams; includes sub- and superscripts
             fonts        every font is embedded and none is Type 3
             images       whether raster images are inside (their resolution is not measured)
  PNG, TIFF  width        pixels / dpi metadata against --width-mm
             resolution   pixels across the print width against --min-dpi (default 300)
             colour_vision, grayscale   needs Pillow: the colours drawn, pair by pair, under
                          simulated protanopia, deuteranopia and tritanopia, and by lightness.
                          A PDF given without its PNG gets `colours` NOT_CHECKED instead
  both       axes         the axis findings of <name>.figure.json, when rz_figure.save wrote one
                          for exactly this file

Every check is PASS, FAIL or NOT_CHECKED with the reason. A check that could not run is
NOT_CHECKED, never PASS. Prints JSON. Exit code 1 when any check is FAIL, 2 for a file that
cannot be read as PDF, PNG or TIFF.

Standard library only; Pillow is optional. Portions are derived from Apache-2.0-licensed code:
see LICENSE-APACHE-2.0.txt next to this file and THIRD_PARTY_NOTICES.md in the plugin.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import re
import struct
import sys
import zlib
from pathlib import Path

MM_PER_INCH = 25.4
PT_PER_INCH = 72.0
# Working values of this skill, not a standard. Okabe and Ito's closest pair is 16 apart under
# simulation; the red and green of common default palettes fall to 5-8.
MIN_DELTA_E = 15.0      # CIE 1976 colour difference below which two plotted colours are confusable
MIN_DELTA_L = 10.0      # CIE L* difference below which two colours are one grey in a grayscale print
MIN_SHARE = 0.0002      # a plotted colour covers at least this share of the pixels...
MIN_PIXELS = 40         # ...and at least this many
MAX_COLOURS = 12        # more colours than this is a continuous scale or a photograph
MAX_STRAY = 0.10        # share of the drawn pixels that may belong to no listed colour
MIX_TOLERANCE = 4.0     # distance (0-255 scale) from the line between two colours that still counts as a mix

# Machado, Oliveira and Fernandes (2009), "A physiologically-based model for simulation of color
# vision deficiency", IEEE Transactions on Visualization and Computer Graphics 15(6), 1291-1298:
# the matrices for severity 1.0 (dichromacy), applied to linear RGB.
CVD_MATRICES = {
    "protanopia": ((0.152286, 1.052583, -0.204868), (0.114503, 0.786281, 0.099216), (-0.003882, -0.048116, 1.051998)),
    "deuteranopia": ((0.367322, 0.860646, -0.227968), (0.280085, 0.672501, 0.047413), (-0.011820, 0.042940, 0.968881)),
    "tritanopia": ((1.255528, -0.076749, -0.178779), (-0.078411, 0.930809, 0.147602), (0.004733, 0.691367, 0.303900)),
}


class Unreadable(Exception):
    """The file is not something this script can read."""


def check(name: str, status: str, detail: str, **extra) -> dict:
    return {"check": name, "status": status, "detail": detail, **extra}


# ---------------------------------------------------------------------------------------------
# PDF

OBJECT_RE = re.compile(rb"(?<![\d.])(\d+)\s+\d+\s+obj\b")
STREAM_RE = re.compile(rb"stream\r?\n")
NUMBER = rb"[-+]?(?:\d+(?:\.\d*)?|\.\d+)"
BOX_RE = re.compile(rb"/MediaBox\s*\[\s*(" + NUMBER + rb")\s+(" + NUMBER + rb")\s+(" + NUMBER + rb")\s+(" + NUMBER + rb")\s*\]")
TOKEN_RE = re.compile(
    rb"%[^\r\n]*"                                   # comment
    rb"|\((?:\\.|[^\\()])*\)"                       # literal string
    rb"|<<|>>|<[0-9A-Fa-f\s]*>"                     # dictionary delimiters, hex string
    rb"|[\[\]]"
    rb"|/[^\s/<>\[\]()%]*"                          # name
    rb"|[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][-+]?\d+)?"  # number
    rb"|[^\s/<>\[\]()%]+",                          # operator
    re.S,
)
NUMBER_RE = re.compile(rb"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][-+]?\d+)?$")
SHOW_OPERATORS = {b"Tj", b"TJ", b"'", b'"'}
IDENTITY = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
STRING_ESCAPES = {b"n": b"\n", b"r": b"\r", b"t": b"\t", b"b": b"\b", b"f": b"\f"}


def multiply(first: tuple, second: tuple) -> tuple:
    """first x second for PDF row-vector matrices [a b c d e f]."""
    a1, b1, c1, d1, e1, f1 = first
    a2, b2, c2, d2, e2, f2 = second
    return (a1 * a2 + b1 * c2, a1 * b2 + b1 * d2, c1 * a2 + d1 * c2, c1 * b2 + d1 * d2,
            e1 * a2 + f1 * c2 + e2, e1 * b2 + f1 * d2 + f2)


def matrix_scale(matrix: tuple) -> float:
    """The isotropic scale of the linear part: the square root of |det|."""
    return abs(matrix[0] * matrix[3] - matrix[1] * matrix[2]) ** 0.5


def string_bytes(tokens: list) -> bytes:
    """The bytes of the literal strings among the operands of one text-showing operator.

    Hex strings are left out: they hold glyph numbers, which mean nothing without the font.
    """
    def unescape(match):
        code = match.group(1)
        return bytes([int(code, 8) & 255]) if code[:1] in b"01234567" else STRING_ESCAPES.get(code, code)

    return b"".join(re.sub(rb"\\([0-7]{1,3}|.)", unescape, token[1:-1], flags=re.S)
                    for token in tokens if token.startswith(b"("))


def readable(runs: list) -> list:
    """Runs with their bytes turned into text, best effort, for naming the text that is too small.

    A font whose strings all have two bytes per character, mostly with a zero high byte, is a
    composite font written as UTF-16 (what matplotlib does); everything else is read as Latin-1.
    """
    by_font: dict = {}
    for _, font, raw in runs:
        by_font.setdefault(font, []).append(raw)
    wide = {font: all(len(raw) % 2 == 0 for raw in raws)
            and 2 * sum(raw[0::2].count(0) for raw in raws) > sum(len(raw) // 2 for raw in raws)
            for font, raws in by_font.items()}
    decoded = []
    for size, font, raw in runs:
        text = raw.decode("utf-16-be", "replace") if wide[font] else raw.decode("latin-1")
        decoded.append((size, font, "".join(ch for ch in text if ch.isprintable())[:40]))
    return decoded


def text_runs(stream: bytes) -> list:
    """(effective size in points, font resource name, string bytes) of every piece of text shown.

    The effective size is the Tf size scaled by the text matrix (Tm) and the current
    transformation matrix (cm, saved and restored by q and Q). Text is counted only inside
    BT ... ET, so operator-like bytes elsewhere are ignored.
    """
    runs = []
    operands: list = []
    ctm, stack = IDENTITY, []
    text_matrix, font, font_size, in_text = IDENTITY, "", 0.0, False
    for match in TOKEN_RE.finditer(stream):
        token = match.group(0)
        if token.startswith(b"%"):
            continue
        if token[:1] in (b"(", b"/", b"[", b"]", b"<") or NUMBER_RE.match(token):
            operands.append(token)
            continue
        try:
            if token == b"q":
                stack.append(ctm)
            elif token == b"Q":
                ctm = stack.pop() if stack else ctm
            elif token == b"cm" and len(operands) >= 6:
                ctm = multiply(tuple(float(v) for v in operands[-6:]), ctm)
            elif token == b"BT":
                text_matrix, in_text = IDENTITY, True
            elif token == b"ET":
                in_text = False
            elif token == b"Tm" and len(operands) >= 6:
                text_matrix = tuple(float(v) for v in operands[-6:])
            elif token == b"Tf" and len(operands) >= 2:
                font, font_size = operands[-2].lstrip(b"/").decode("ascii", "replace"), float(operands[-1])
            elif token in SHOW_OPERATORS and in_text:
                size = abs(font_size) * matrix_scale(multiply(text_matrix, ctm))
                if size > 0:
                    runs.append((size, font, string_bytes(operands)))
        except ValueError:
            pass
        operands.clear()
    return runs


def stream_bytes(head: bytes, payload: bytes):
    """The decoded bytes of a stream, or None when its filter is not plain or FlateDecode."""
    found = re.search(rb"/Filter\s*(\[[^\]]*\]|/\w+)", head)
    filters = re.findall(rb"/(\w+)", found.group(1)) if found else []
    if not filters:
        return payload
    if filters != [b"FlateDecode"]:
        return None
    try:
        return zlib.decompressobj().decompress(payload)
    except zlib.error:
        return None


def pdf_objects(data: bytes) -> dict:
    """Object number -> (dictionary part, stream payload or None), including compressed objects."""
    objects: dict = {}
    cursor = 0
    while True:
        match = OBJECT_RE.search(data, cursor)
        if not match:
            break
        end = data.find(b"endobj", match.end())
        end = len(data) if end < 0 else end
        stream = STREAM_RE.search(data, match.end(), end)
        if stream:
            stop = data.find(b"endstream", stream.end())
            stop = len(data) if stop < 0 else stop
            objects[int(match.group(1))] = (data[match.end():stream.start()], data[stream.end():stop])
            cursor = stop
        else:
            objects[int(match.group(1))] = (data[match.end():end], None)
            cursor = end
    for head, payload in list(objects.values()):        # objects packed into object streams
        if payload is None or not re.search(rb"/Type\s*/ObjStm\b", head):
            continue
        body = stream_bytes(head, payload)
        count, first = re.search(rb"/N\s+(\d+)", head), re.search(rb"/First\s+(\d+)", head)
        if body is None or not count or not first:
            continue
        index = [int(v) for v in body[:int(first.group(1))].split()]
        for i in range(min(int(count.group(1)), len(index) // 2)):
            start = int(first.group(1)) + index[2 * i + 1]
            stop = int(first.group(1)) + index[2 * i + 3] if 2 * i + 3 < len(index) else len(body)
            objects.setdefault(index[2 * i], (body[start:stop], None))
    return objects


def follow(objects: dict, head: bytes, key: bytes):
    """The dictionary that /key of `head` leads to; `head` itself when the value is written in
    place or the key is absent; None when the object it points to cannot be found."""
    found = re.search(rb"/" + key + rb"\s*\[?\s*(\d+)\s+\d+\s+R", head)
    if not found:
        return head
    target = objects.get(int(found.group(1)), (None, None))[0]
    if target is not None and b"<<" not in target:      # an array kept as its own object: take its first entry
        inner = re.search(rb"(\d+)\s+\d+\s+R", target)
        target = objects.get(int(inner.group(1)), (None, None))[0] if inner else None
    return target


def pdf_fonts(objects: dict) -> list:
    """The fonts of a PDF: name, type, and whether the font program is in the file (None: unknown)."""
    fonts = []
    for head, _ in objects.values():
        kind = re.search(rb"/Subtype\s*/(Type0|Type1|MMType1|TrueType|Type3)\b", head)
        if not kind or not re.search(rb"/Type\s*/Font(?![A-Za-z])", head):
            continue
        name = re.search(rb"/(?:BaseFont|Name)\s*/([^\s/<>\[\]()]+)", head)
        name = re.sub(r"^[A-Z]{6}\+", "", name.group(1).decode("latin-1")) if name else "(unnamed)"
        kind = kind.group(1).decode()
        # A composite font keeps its descriptor in the descendant font.
        holder = follow(objects, head, b"DescendantFonts") if kind == "Type0" else head
        descriptor = follow(objects, holder, b"FontDescriptor") if holder is not None else None
        embedded = True if kind == "Type3" else None if descriptor is None \
            else bool(re.search(rb"/FontFile[23]?\b", descriptor))
        fonts.append({"name": name, "type": kind, "embedded": embedded})
    return sorted(fonts, key=lambda f: (f["name"], f["type"]))


def check_pdf(data: bytes, args) -> tuple:
    objects = pdf_objects(data)
    pages = [head for head, _ in objects.values() if re.search(rb"/Type\s*/Page(?![A-Za-z])", head)]
    info: dict = {"pages": len(pages)}
    checks = []

    box = next((BOX_RE.search(head) for head in pages if BOX_RE.search(head)), None) \
        or next((BOX_RE.search(head) for head, _ in objects.values() if BOX_RE.search(head)), None)
    scale = 1.0
    if box is None:
        checks.append(check("width", "NOT_CHECKED", "the page size (MediaBox) could not be read from this PDF"))
    else:
        x0, y0, x1, y1 = (float(v) for v in box.groups())
        width, height = abs(x1 - x0) / PT_PER_INCH * MM_PER_INCH, abs(y1 - y0) / PT_PER_INCH * MM_PER_INCH
        turned = re.search(rb"/Rotate\s+(-?\d+)", pages[0]) if pages else None
        if turned and int(turned.group(1)) % 180 == 90:
            width, height = height, width
        info.update(width_mm=round(width, 2), height_mm=round(height, 2))
        size = f"the page is {width:.1f} x {height:.1f} mm"
        if len(pages) > 1:
            size += f" ({len(pages)} pages; the size is that of the first)"
        if args.width_mm is None:
            checks.append(check("width", "NOT_CHECKED", f"{size}; no --width-mm was given to compare it with"))
        elif abs(width - args.width_mm) <= args.tolerance_mm:
            checks.append(check("width", "PASS", f"{size}; asked for {args.width_mm:g} mm"))
        else:
            scale = args.width_mm / width
            checks.append(check("width", "FAIL", f"{size}; asked for {args.width_mm:g} mm wide. Placed at that "
                                                 f"width, everything in it is scaled by {scale:.2f}"))

    # Text lives in the content streams of the pages and in form XObjects, nowhere else.
    wanted = {number for number, (head, payload) in objects.items()
              if payload is not None and re.search(rb"/Subtype\s*/Form\b", head)}
    for head in pages:
        contents = re.search(rb"/Contents\s*(\[[^\]]*\]|\d+\s+\d+\s+R)", head)
        if contents:
            wanted |= {int(number) for number in re.findall(rb"(\d+)\s+\d+\s+R", contents.group(1))}
    runs, unread = [], 0
    for number in sorted(wanted):
        head, payload = objects.get(number, (b"", None))
        body = stream_bytes(head, payload) if payload is not None else None
        if body is None:
            unread += 1
        else:
            runs += text_runs(body)
    sizes: dict = {}
    for size, _, text in readable(runs):
        entry = sizes.setdefault(round(size * scale, 2), {"count": 0, "text": []})
        entry["count"] += 1
        if text and text not in entry["text"] and len(entry["text"]) < 4:
            entry["text"].append(text)
    table = [{"size_pt": size, "count": entry["count"], "text": entry["text"]} for size, entry in sorted(sizes.items())]
    below = [row for row in table if row["size_pt"] < args.min_pt - 0.005]
    counts = {f"{row['size_pt']:g}": row["count"] for row in table}
    at = "at print width" if args.width_mm is not None else "as drawn (no --width-mm)"
    if below:
        # matplotlib draws sub- and superscripts at 0.7 of their text: say so when that is the cause.
        parent = next((row["size_pt"] for row in table if abs(below[0]["size_pt"] - 0.7 * row["size_pt"]) < 0.02), None)
        checks.append(check("min_font_size", "FAIL",
                            f"smallest text is {below[0]['size_pt']:g} pt {at}; the floor is {args.min_pt:g} pt"
                            + (f". It is 0.7 of the {parent:g} pt text: a sub- or superscript" if parent else ""),
                            smallest_pt=below[0]["size_pt"], below=below, sizes_pt=counts))
    elif not table:
        checks.append(check("min_font_size", "NOT_CHECKED",
                            "no text was found in the page content: the text is drawn as outlines or is part of an "
                            "image" + (f", or sits in the {unread} content streams that could not be decoded" if unread else "")
                            + ". Judge it by eye at print size"))
    elif unread:
        checks.append(check("min_font_size", "NOT_CHECKED",
                            f"{unread} content streams could not be decoded; the text that was read is "
                            f"{table[0]['size_pt']:g} pt or larger", smallest_pt=table[0]["size_pt"]))
    else:
        checks.append(check("min_font_size", "PASS",
                            f"smallest text is {table[0]['size_pt']:g} pt {at}; the floor is {args.min_pt:g} pt",
                            smallest_pt=table[0]["size_pt"], sizes_pt=counts))

    fonts = pdf_fonts(objects)
    type3 = [f["name"] for f in fonts if f["type"] == "Type3"]
    loose = [f["name"] for f in fonts if f["embedded"] is False]
    unknown = [f["name"] for f in fonts if f["embedded"] is None]
    if not fonts:
        checks.append(check("fonts", "NOT_CHECKED", "no font was found in this PDF: there is no text, or it is drawn as outlines"))
    elif type3 or loose:
        problems = ([f"Type 3 fonts ({', '.join(type3)}): many submission systems reject them; "
                     "in matplotlib set pdf.fonttype to 42"] if type3 else []) \
            + ([f"not embedded ({', '.join(loose)}): the text will be drawn with whatever font the reader has"] if loose else [])
        checks.append(check("fonts", "FAIL", "; ".join(problems), fonts=fonts))
    elif unknown:
        checks.append(check("fonts", "NOT_CHECKED", f"could not tell whether these fonts are embedded: {', '.join(unknown)}",
                            fonts=fonts))
    else:
        checks.append(check("fonts", "PASS", "all fonts are embedded and none is Type 3: "
                            + ", ".join(sorted({f["name"] for f in fonts})), fonts=fonts))

    images = [head for head, payload in objects.values() if payload is not None and re.search(rb"/Subtype\s*/Image\b", head)]
    if images:
        sizes_px = [(int(w.group(1)), int(h.group(1))) for w, h in
                    ((re.search(rb"/Width\s+(\d+)", head), re.search(rb"/Height\s+(\d+)", head)) for head in images) if w and h]
        largest = max(sizes_px, key=lambda size: size[0] * size[1], default=None)
        checks.append(check("images", "NOT_CHECKED",
                            f"{len(images)} raster image(s) inside this PDF"
                            + (f" (largest {largest[0]} x {largest[1]} px)" if largest else "")
                            + "; their resolution on the page is not measured. Look at them at print size"))
    else:
        checks.append(check("images", "PASS", "no raster image inside: the figure is all vector"))
    return info, checks


# ---------------------------------------------------------------------------------------------
# PNG and TIFF


def png_info(data: bytes) -> dict:
    """Pixel size and resolution from the IHDR and pHYs chunks."""
    if len(data) < 33 or data[12:16] != b"IHDR":
        raise Unreadable("the PNG header is damaged")
    width, height = struct.unpack(">II", data[16:24])
    info = {"width_px": width, "height_px": height, "dpi": None}
    cursor = 8
    while cursor + 8 <= len(data):
        length, kind = struct.unpack(">I4s", data[cursor:cursor + 8])
        if kind == b"pHYs" and length == 9:
            per_unit, _, unit = struct.unpack(">IIB", data[cursor + 8:cursor + 17])
            if unit == 1 and per_unit:                  # pixels per metre
                info["dpi"] = per_unit * 0.0254
        if kind in (b"IDAT", b"IEND"):
            break
        cursor += 12 + length
    return info


def tiff_info(data: bytes) -> dict:
    """Pixel size and resolution from the first image directory of a TIFF."""
    order = {b"II": "<", b"MM": ">"}.get(data[:2])
    if order is None or len(data) < 8 or struct.unpack(order + "H", data[2:4])[0] != 42:
        raise Unreadable("this TIFF variant is not supported (BigTIFF?)")
    offset = struct.unpack(order + "I", data[4:8])[0]
    try:
        count = struct.unpack(order + "H", data[offset:offset + 2])[0]
        tags = {}
        for i in range(count):
            tag, kind, _, raw = struct.unpack(order + "HHI4s", data[offset + 2 + 12 * i:offset + 14 + 12 * i])
            if kind == 3:                               # SHORT
                tags[tag] = struct.unpack(order + "H", raw[:2])[0]
            elif kind == 4:                             # LONG
                tags[tag] = struct.unpack(order + "I", raw)[0]
            elif kind == 5:                             # RATIONAL, stored elsewhere
                where = struct.unpack(order + "I", raw)[0]
                top, bottom = struct.unpack(order + "II", data[where:where + 8])
                tags[tag] = top / bottom if bottom else None
    except struct.error:
        raise Unreadable("the TIFF directory is damaged") from None
    if 256 not in tags or 257 not in tags:
        raise Unreadable("the TIFF has no image size")
    per_unit, unit = tags.get(282), tags.get(296, 2)        # XResolution; ResolutionUnit 2 = inch, 3 = centimetre
    dpi = per_unit * {2: 1.0, 3: 2.54}[unit] if per_unit and unit in (2, 3) else None
    return {"width_px": tags[256], "height_px": tags[257], "dpi": dpi}


def linear(channel: int) -> float:
    c = channel / 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def lab(rgb: tuple) -> tuple:
    """CIELAB (D65) of a linear-RGB colour with sRGB primaries."""
    r, g, b = rgb
    xyz = (0.4124564 * r + 0.3575761 * g + 0.1804375 * b,
           0.2126729 * r + 0.7151522 * g + 0.0721750 * b,
           0.0193339 * r + 0.1191920 * g + 0.9503041 * b)
    fx, fy, fz = ((t ** (1 / 3) if t > 216 / 24389 else (24389 / 27 * t + 16) / 116)
                  for t in (xyz[0] / 0.95047, xyz[1], xyz[2] / 1.08883))
    return (116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz))


def simulate(rgb: tuple, deficiency: str) -> tuple:
    """A linear-RGB colour as seen with a colour-vision deficiency (clipped to the display range)."""
    return tuple(min(1.0, max(0.0, sum(m * c for m, c in zip(row, rgb)))) for row in CVD_MATRICES[deficiency])


def delta_e(first: tuple, second: tuple) -> float:
    """CIE 1976 colour difference between two CIELAB colours."""
    return sum((a - b) ** 2 for a, b in zip(first, second)) ** 0.5


def to_hex(colour: tuple) -> str:
    return "#%02X%02X%02X" % tuple(colour)


def compare_colours(colours: list) -> tuple:
    """Pairs of sRGB colours that normal colour vision separates but a deficiency or a grayscale
    print does not: (confusable under a simulated deficiency, same grey).

    Pairs that already look alike (two greys of the axes and grid, a colour and its tint) are left
    out: every reader sees those the same way, and the author sees them too.
    """
    rgb = {colour: tuple(linear(c) for c in colour) for colour in colours}
    confusable, same_grey = [], []
    for first, second in itertools.combinations(colours, 2):
        if delta_e(lab(rgb[first]), lab(rgb[second])) < MIN_DELTA_E:
            continue
        for deficiency in CVD_MATRICES:
            distance = delta_e(lab(simulate(rgb[first], deficiency)), lab(simulate(rgb[second], deficiency)))
            if distance < MIN_DELTA_E:
                confusable.append({"pair": [to_hex(first), to_hex(second)], "under": deficiency, "delta_e": round(distance, 1)})
        lightness = abs(lab(rgb[first])[0] - lab(rgb[second])[0])
        if lightness < MIN_DELTA_L:
            same_grey.append({"pair": [to_hex(first), to_hex(second)], "delta_l": round(lightness, 1)})
    return confusable, same_grey


def is_mix(colour: tuple, first: tuple, second: tuple) -> bool:
    """Whether an sRGB colour lies between two others: what anti-aliasing and transparency produce."""
    step = [b - a for a, b in zip(first, second)]
    length = sum(v * v for v in step)
    if not length:
        return False
    t = sum((c - a) * v for c, a, v in zip(colour, first, step)) / length
    return 0.0 <= t <= 1.0 and sum((c - a - t * v) ** 2 for c, a, v in zip(colour, first, step)) <= MIX_TOLERANCE ** 2


def plotted_colours(path: Path):
    """The colours drawn on the background: (colours, background, stray share), or a reason string.

    First the colours with a flat area: enough pixels that have the same colour to their right and
    below. Then the colours of thin lines and small marks: frequent colours that are not a mix of
    the background and a colour already found, which is what anti-aliasing leaves along every edge.
    The background is the colour of the top-left pixel. Text, axes and grid lines count as drawn.
    The stray share is the part of the drawn pixels that belongs to none of the colours.
    """
    try:
        from PIL import Image, ImageChops
    except ImportError:
        return "Pillow is not installed (python3 -m pip install pillow)"
    try:
        with Image.open(path) as image:
            image = image.convert("RGBA" if image.mode in ("RGBA", "LA", "P", "PA") else "RGB").convert("RGBA")
    except Exception as exc:
        return f"Pillow could not read the image: {exc}"
    flat = Image.alpha_composite(Image.new("RGBA", image.size, (255, 255, 255, 255)), image).convert("RGB")
    total = flat.width * flat.height
    background = flat.getpixel((0, 0))
    floor = max(MIN_PIXELS, MIN_SHARE * total)

    inside = Image.new("L", flat.size, 255)
    for dx, dy in ((-1, 0), (0, -1)):                   # compare with the pixel to the right, then below
        r, g, b = ImageChops.difference(flat, ImageChops.offset(flat, dx, dy)).split()
        same = ImageChops.lighter(ImageChops.lighter(r, g), b).point(lambda v: 0 if v else 255)
        inside = ImageChops.multiply(inside, same)
    areas = Image.composite(flat.convert("RGBA"), Image.new("RGBA", flat.size, (0, 0, 0, 0)), inside)
    colours = [c[:3] for n, c in sorted(areas.getcolors(total), reverse=True)
               if c[3] and n >= floor and c[:3] != background]
    solid = set(colours)

    def explained(colour: tuple) -> bool:
        return colour in solid or any(is_mix(colour, background, known) for known in colours) \
            or any(is_mix(colour, a, b) for a, b in itertools.combinations(colours, 2))

    exact = sorted(((n, c) for n, c in flat.getcolors(total) if c != background), reverse=True)
    ink = sum(n for n, _ in exact)
    stray = 0
    for n, colour in exact:
        if len(colours) > MAX_COLOURS or stray > MAX_STRAY * ink:
            break
        if explained(colour):
            continue
        if n >= floor:                                  # a purer colour replaces the tints of it found before
            colours = [c for c in colours if c in solid or not is_mix(c, background, colour)] + [colour]
        else:
            stray += n
    return colours, background, (stray / ink if ink else 0.0)


def check_colours(path: Path) -> list:
    found = plotted_colours(path)
    reason = found if isinstance(found, str) else None
    if reason is None:
        colours, background, stray = found
        names = [to_hex(c) for c in colours]
        listed = f"colours drawn on {to_hex(background)}: {', '.join(names) or 'none'}"
        if len(colours) > MAX_COLOURS:
            reason = (f"more than {MAX_COLOURS} colours were found, which is a continuous colour scale or a "
                      "photograph: pairs are compared for categorical colours only")
        elif not colours and not stray:
            reason = f"nothing is drawn on the background {to_hex(background)}"
        elif stray > MAX_STRAY or not colours:
            reason = (f"{stray:.0%} of the drawn pixels belong to no colour that could be listed (marks too fine for "
                      "this resolution, shading or a photograph). Export at 300 dpi, or judge the colours by eye")
    if reason:
        return [check(name, "NOT_CHECKED", reason) for name in ("colour_vision", "grayscale")]
    if len(colours) < 2:
        return [check(name, "PASS", f"{listed}; one colour, so there is no pair to confuse", colours=names)
                for name in ("colour_vision", "grayscale")]
    confusable, same_grey = compare_colours(colours)
    return [
        check("colour_vision", "FAIL" if confusable else "PASS",
              (f"{len({tuple(p['pair']) for p in confusable})} pair(s) that normal vision separates fall below a colour "
               f"difference of {MIN_DELTA_E:g} under a simulated colour-vision deficiency" if confusable else
               f"every pair keeps a colour difference of {MIN_DELTA_E:g} or more under simulated protanopia, "
               "deuteranopia and tritanopia") + f"; {listed}", colours=names, **({"confusable": confusable} if confusable else {})),
        check("grayscale", "FAIL" if same_grey else "PASS",
              (f"{len(same_grey)} pair(s) differ by less than {MIN_DELTA_L:g} in lightness: in a grayscale print "
               "they are told apart only by a second cue (marker, line style, hatching, label)" if same_grey else
               f"every pair differs by {MIN_DELTA_L:g} or more in lightness") + f"; {listed}",
              colours=names, **({"same_grey": same_grey} if same_grey else {})),
    ]


def check_raster(path: Path, data: bytes, kind: str, args) -> tuple:
    info = png_info(data) if kind == "png" else tiff_info(data)
    pixels, dpi = info["width_px"], info["dpi"]
    checks = []
    if dpi:
        width = pixels / dpi * MM_PER_INCH
        info.update(dpi=round(dpi, 1), width_mm=round(width, 2), height_mm=round(info["height_px"] / dpi * MM_PER_INCH, 2))
        size = f"{pixels} px at {dpi:.0f} dpi is {width:.1f} mm wide"
        if args.width_mm is None:
            checks.append(check("width", "NOT_CHECKED", f"{size}; no --width-mm was given to compare it with"))
        else:
            good = abs(width - args.width_mm) <= args.tolerance_mm
            checks.append(check("width", "PASS" if good else "FAIL", f"{size}; asked for {args.width_mm:g} mm"))
    else:
        checks.append(check("width", "NOT_CHECKED", "the file states no resolution, so it has no physical size"))
    effective = pixels / (args.width_mm / MM_PER_INCH) if args.width_mm else dpi
    if not effective:
        checks.append(check("resolution", "NOT_CHECKED",
                            f"{pixels} x {info['height_px']} px with no stated resolution and no --width-mm"))
    else:
        basis = f"{pixels} px across {args.width_mm:g} mm" if args.width_mm else "the resolution stated in the file"
        checks.append(check("resolution", "PASS" if round(effective) >= args.min_dpi else "FAIL",
                            f"{effective:.0f} dpi ({basis}); the floor is {args.min_dpi:g} dpi", dpi=round(effective, 1)))
    return info, checks + check_colours(path)


# ---------------------------------------------------------------------------------------------


def check_record(path: Path, data: bytes, record_path) -> dict:
    """The axis findings rz_figure.save recorded, if the record is about exactly this file."""
    record_path = Path(record_path) if record_path else path.with_name(path.stem + ".figure.json")
    unseen = ("bars and filled areas from zero, twin axes and log axes were not checked: these are read from "
              "the figure object when rz_figure.save exports it. Check them in the plotting code")
    if not record_path.is_file():
        return check("axes", "NOT_CHECKED", f"no record {record_path.name} next to the file; {unseen}")
    try:
        record = json.loads(record_path.read_text(encoding="utf-8"))
        hashes = {entry["sha256"] for entry in record["outputs"]}
        findings = record["axis_findings"]
    except (ValueError, KeyError, TypeError):
        return check("axes", "NOT_CHECKED", f"{record_path.name} is not a record written by rz_figure.save; {unseen}")
    if hashlib.sha256(data).hexdigest() not in hashes:
        return check("axes", "NOT_CHECKED", f"{record_path.name} was written for other files or an older export of "
                                            "this one. Run the plotting script again, or check the files it lists")
    if findings:
        return check("axes", "FAIL", "; ".join(f"{f['rule']}: {f['detail']}" for f in findings), findings=findings)
    return check("axes", "PASS", "the record lists no bar or area cut off from zero, no twin axes and no "
                                 "zero or negative value on a log axis")


def check_file(path: Path, args, stems_with_raster: set) -> dict:
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise Unreadable(str(exc)) from None
    if data.startswith(b"%PDF-"):
        kind = "pdf"
        info, checks = check_pdf(data, args)
        if path.stem not in stems_with_raster:
            checks.append(check("colours", "NOT_CHECKED", "colours are read from pixels: run the checker on the PNG export too"))
    elif data.startswith(b"\x89PNG\r\n\x1a\n"):
        kind = "png"
        info, checks = check_raster(path, data, kind, args)
    elif data[:4] in (b"II*\x00", b"MM\x00*"):
        kind = "tiff"
        info, checks = check_raster(path, data, kind, args)
    else:
        raise Unreadable("not a PDF, PNG or TIFF file")
    checks.append(check_record(path, data, args.record))
    return {"file": str(path), "type": kind, **info, "checks": checks}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Check an exported figure file (PDF, PNG or TIFF).")
    parser.add_argument("files", nargs="+", type=Path, help="Exported figure files")
    parser.add_argument("--width-mm", type=float, help="The width the figure will have in print")
    parser.add_argument("--tolerance-mm", type=float, default=1.0, help="Allowed difference in width (default 1)")
    parser.add_argument("--min-pt", type=float, default=5.0, help="Smallest allowed text at print width, in points (default 5)")
    parser.add_argument("--min-dpi", type=float, default=300.0, help="Lowest allowed raster resolution at print width (default 300)")
    parser.add_argument("--record", help="The <name>.figure.json to read axis findings from (default: next to the file)")
    args = parser.parse_args(argv)
    if (args.width_mm is not None and args.width_mm <= 0) or args.min_pt <= 0 or args.min_dpi <= 0:
        print("check_figure: --width-mm, --min-pt and --min-dpi must be positive.", file=sys.stderr)
        return 2
    rasters = {path.stem for path in args.files if path.suffix.lower() in (".png", ".tif", ".tiff")}
    results = []
    for path in args.files:
        try:
            results.append(check_file(path, args, rasters))
        except Unreadable as exc:
            print(f"check_figure: cannot read {path}: {exc}", file=sys.stderr)
            return 2
    counts = {status: sum(1 for r in results for c in r["checks"] if c["status"] == status)
              for status in ("PASS", "FAIL", "NOT_CHECKED")}
    print(json.dumps({"tool": "researchzy-figures",
                      "settings": {"width_mm": args.width_mm, "tolerance_mm": args.tolerance_mm,
                                   "min_pt": args.min_pt, "min_dpi": args.min_dpi},
                      "files": results, "counts": counts, "ok": counts["FAIL"] == 0}, indent=2, ensure_ascii=False))
    return 1 if counts["FAIL"] else 0


if __name__ == "__main__":
    sys.exit(main())
