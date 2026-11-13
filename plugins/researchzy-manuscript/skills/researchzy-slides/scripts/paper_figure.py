#!/usr/bin/env python3
"""Take a figure out of a paper's PDF unchanged, and record where it came from.

  paper_figure.py page paper.pdf --page 4                       slides/preview/page-04.png
  paper_figure.py crop paper.pdf --page 4 --box 0.08,0.12,0.92,0.55 --id fig2a \\
                  --label "Fig. 2a of Zhen et al. (2026)" [--dpi 300] [--replace]

page   renders a whole page for looking at, with a grid every tenth of the page when Pillow is
       installed, and lists the captions and embedded pictures on it with their boxes (with
       PyMuPDF). Use it to choose --box.
crop   renders the box of the page at --dpi (default 300) to slides/figures/<id>.png and appends a
       row to slides/figures/manifest.json: id, file, source and its SHA-256, page, box, dpi,
       pixel size, the PNG's SHA-256, label and renderer.

The box is x0,y0,x1,y1 in fractions of the page, from its top left corner. Nothing is redrawn,
recoloured or edited: the PNG is the rendered page region, as rendered. An id already in the
manifest is refused unless --replace is given, and --replace still refuses a file that is not the
crop the manifest records. All commands take --dir (default: slides). Prints JSON.

Needs PyMuPDF, or the pdftoppm program with Pillow; it says which is missing. Exit code 1: a
refused id, a page or box out of range, or no renderer; 2: a file that cannot be read.

Portions are derived from MIT-licensed code: see LICENSE-MIT.txt next to this file and
THIRD_PARTY_NOTICES.md in the plugin.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

MIN_WIDTH_PX = 900      # narrower than this looks soft when it fills half a projected slide
CAPTION_RE = re.compile(r"^\s*(fig\.?|figure|table|extended data fig\.?)\s*[A-Z]?\d+[a-z]?\s*[:.|]", re.I)


class Refused(Exception):
    pass


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def backends() -> dict:
    found = {}
    try:
        import pymupdf as fitz
    except ImportError:
        try:
            import fitz
        except ImportError:
            fitz = None
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        Image = ImageDraw = None
    found["fitz"], found["Image"], found["ImageDraw"] = fitz, Image, ImageDraw
    found["pdftoppm"] = shutil.which("pdftoppm")
    if not fitz and not (found["pdftoppm"] and Image):
        missing = ["PyMuPDF (pip install pymupdf)"]
        missing.append("or Pillow (pip install pillow)" if found["pdftoppm"] else
                       "or the pdftoppm program (poppler-utils)" + ("" if Image else " with Pillow"))
        raise Refused("Rendering a PDF page needs " + " ".join(missing) + ".")
    return found


def parse_box(text: str) -> tuple:
    try:
        box = tuple(float(v) for v in text.split(","))
    except ValueError:
        box = ()
    if len(box) != 4 or not all(0 <= v <= 1 for v in box) or not (box[0] < box[2] and box[1] < box[3]):
        raise Refused(f"--box takes x0,y0,x1,y1 as fractions of the page (0 to 1, x0 < x1, y0 < y1), "
                      f"not {text!r}")
    return box


def page_count(pdf: Path, b: dict) -> int:
    if b["fitz"]:
        with b["fitz"].open(pdf) as doc:
            return doc.page_count
    out = subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True)
    found = re.search(r"^Pages:\s+(\d+)", out.stdout, re.M)
    return int(found[1]) if found else 0


def render(pdf: Path, page: int, dpi: int, box, out: Path, b: dict) -> str:
    """Render a page, or the box of it, to a PNG. Returns the renderer used."""
    if b["fitz"]:
        with b["fitz"].open(pdf) as doc:
            p = doc[page - 1]
            r = p.rect
            clip = None if box is None else b["fitz"].Rect(
                r.x0 + box[0] * r.width, r.y0 + box[1] * r.height, r.x0 + box[2] * r.width, r.y0 + box[3] * r.height)
            p.get_pixmap(dpi=dpi, clip=clip, alpha=False).save(out)
        return "pymupdf"
    with tempfile.TemporaryDirectory() as tmp:
        prefix = Path(tmp) / "page"
        done = subprocess.run([b["pdftoppm"], "-png", "-r", str(dpi), "-f", str(page), "-l", str(page),
                               str(pdf), str(prefix)], capture_output=True, text=True)
        rendered = sorted(Path(tmp).glob("page*.png"))
        if done.returncode or not rendered:
            raise Refused(f"pdftoppm could not render page {page}: {done.stderr.strip()}")
        with b["Image"].open(rendered[0]) as image:
            if box is not None:
                w, h = image.size
                image = image.crop((round(box[0] * w), round(box[1] * h), round(box[2] * w), round(box[3] * h)))
            image.save(out, "PNG")
    return "pdftoppm"


def png_size(path: Path) -> list:
    head = path.read_bytes()[:24]
    return [int.from_bytes(head[16:20], "big"), int.from_bytes(head[20:24], "big")]


def blank(path: Path, b: dict) -> bool | None:
    if b["Image"]:
        with b["Image"].open(path) as image:
            return all(low == high for low, high in image.convert("RGB").getextrema())
    if b["fitz"]:
        return bool(b["fitz"].Pixmap(str(path)).is_unicolor)
    return None


def page_items(pdf: Path, page: int, b: dict) -> list:
    """Captions, embedded pictures and clusters of vector drawing on a page, with their boxes in
    fractions of the page: starting points for --box, not the box itself."""
    if not b["fitz"]:
        return []
    items = []
    with b["fitz"].open(pdf) as doc:
        p = doc[page - 1]
        w, h = p.rect.width, p.rect.height

        def frac(r) -> list:
            return [round(max(0, min(1, v)), 3) for v in (r[0] / w, r[1] / h, r[2] / w, r[3] / h)]

        for block in p.get_text("blocks"):
            if CAPTION_RE.match(block[4]):
                items.append({"caption": " ".join(block[4].split())[:120], "box": frac(block[:4])})
        for info in p.get_image_info():
            items.append({"picture": f"{info.get('width')}x{info.get('height')} px", "box": frac(info["bbox"])})
        for rect in getattr(p, "cluster_drawings", lambda: [])():
            if rect.width * rect.height > 0.02 * w * h:     # rules and underlines are not figures
                items.append({"drawing": "vector graphics", "box": frac(rect)})
    return items


def draw_grid(path: Path, b: dict) -> bool:
    if not b["Image"]:
        return False
    with b["Image"].open(path) as image:
        image = image.convert("RGB")
        draw, (w, h) = b["ImageDraw"].Draw(image), image.size
        for i in range(1, 10):
            x, y = round(i * w / 10), round(i * h / 10)
            draw.line([(x, 0), (x, h)], fill=(230, 60, 60), width=1)
            draw.line([(0, y), (w, y)], fill=(230, 60, 60), width=1)
            draw.text((x + 3, 3), f".{i}", fill=(200, 0, 0))
            draw.text((3, y + 3), f".{i}", fill=(200, 0, 0))
        image.save(path, "PNG")
    return True


def check_source(pdf: Path, page: int, b: dict) -> None:
    if not pdf.is_file():
        raise FileNotFoundError(f"No such PDF: {pdf}")
    pages = page_count(pdf, b)
    if not 1 <= page <= pages:
        raise Refused(f"--page {page} is outside the PDF's {pages} page(s)")


def cmd_page(args) -> dict:
    pdf, b = Path(args.pdf), backends()
    check_source(pdf, args.page, b)
    folder = Path(args.dir) / "preview"
    folder.mkdir(parents=True, exist_ok=True)
    out = folder / f"page-{args.page:02d}.png"
    renderer = render(pdf, args.page, args.dpi, None, out, b)
    grid = draw_grid(out, b)
    return {"preview": str(out), "page": args.page, "renderer": renderer,
            "grid": "every 0.1 of the page, labelled" if grid else "not drawn: needs Pillow",
            "on_this_page": page_items(pdf, args.page, b) if b["fitz"] else "listed only with PyMuPDF",
            "next": "open the preview, choose the box around the whole figure (axes, legend, panel "
                    "letters, scale bar), then run crop"}


def cmd_crop(args) -> dict:
    pdf, b, box = Path(args.pdf), backends(), parse_box(args.box)
    if not re.fullmatch(r"[A-Za-z0-9][\w-]*", args.id):
        raise Refused(f"--id takes letters, digits, - and _ (it names the file), not {args.id!r}")
    check_source(pdf, args.page, b)
    folder = Path(args.dir) / "figures"
    folder.mkdir(parents=True, exist_ok=True)
    manifest_path = folder / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else {
        "tool": "researchzy-slides", "figures": []}
    out = folder / f"{args.id}.png"
    old = next((row for row in manifest["figures"] if row["id"] == args.id), None)
    if old and not args.replace:
        raise Refused(f"Figure {args.id!r} is already in the manifest. Choose another id, or give "
                      "--replace to crop it again.")
    if out.exists() and (old is None or sha256(out) != old.get("sha256")):
        raise Refused(f"{out} exists and is not the crop the manifest records for {args.id!r}; it is "
                      "not overwritten. Choose another id.")
    part = out.with_name(out.stem + ".part.png")
    renderer = render(pdf, args.page, args.dpi, box, part, b)
    if blank(part, b):
        part.unlink()
        raise Refused("The crop is a single colour: the box misses the figure. Look at the page preview again.")
    part.replace(out)
    row = {"id": args.id, "file": out.name, "source": str(pdf), "source_sha256": sha256(pdf),
           "page": args.page, "box": list(box), "dpi": args.dpi, "pixels": png_size(out),
           "sha256": sha256(out), "label": args.label or "", "renderer": renderer}
    manifest["figures"] = [r for r in manifest["figures"] if r["id"] != args.id] + [row]
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    notes = []
    if row["pixels"][0] < MIN_WIDTH_PX:
        notes.append(f"{row['pixels'][0]} px wide: raise --dpi so it stays sharp on a projector")
    if not args.label:
        notes.append("no --label: give the slide a Source: line naming the figure and the paper")
    return {"figure": str(out), "manifest": str(manifest_path), **row,
            "replaced": bool(old), "notes": notes,
            "next": "open the PNG and confirm the whole figure is there and nothing else"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Take a figure out of a paper's PDF unchanged.")
    parser.add_argument("--dir", default="slides", help="The deck's folder (default: slides)")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("page", help="Render a whole page to look at")
    p.add_argument("pdf")
    p.add_argument("--page", type=int, required=True, help="1 for the first page")
    p.add_argument("--dpi", type=int, default=110)
    p = sub.add_parser("crop", help="Crop a box of a page to slides/figures/<id>.png")
    p.add_argument("pdf")
    p.add_argument("--page", type=int, required=True, help="1 for the first page")
    p.add_argument("--box", required=True, help="x0,y0,x1,y1 in fractions of the page, from the top left")
    p.add_argument("--id", required=True, help="The id the plan's Figure: line uses, e.g. fig2a")
    p.add_argument("--dpi", type=int, default=300)
    p.add_argument("--label", help='The source label, e.g. "Fig. 2a of Zhen et al. (2026)"')
    p.add_argument("--replace", action="store_true", help="Crop an id of the manifest again")
    args = parser.parse_args()
    if not 50 <= args.dpi <= 1200:
        parser.error("--dpi is between 50 and 1200")
    try:
        result = cmd_page(args) if args.command == "page" else cmd_crop(args)
    except Refused as exc:
        print(json.dumps({"refused": str(exc)}, indent=2))
        return 1
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"Cannot read the PDF: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
