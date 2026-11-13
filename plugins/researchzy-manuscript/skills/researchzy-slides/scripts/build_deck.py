#!/usr/bin/env python3
"""Build the deck from the slide plan: Beamer always, PowerPoint when python-pptx is installed.

  build_deck.py build slides/plan.md            slides/deck.tex, slides/notes.md, slides/build.json
  build_deck.py build slides/plan.md --pptx     also slides/deck.pptx (needs python-pptx)
  then:  latexmk -pdf -cd -interaction=nonstopmode -halt-on-error -file-line-error slides/deck.tex

deck.tex  Beamer's default theme with a few colour and font settings; 16:9 unless the plan says
          4:3. A title frame from the front block, one frame per slide with its title, bullets
          and figure (scaled to the space, its source label under it in small type), the notes
          in \\note{} (not printed in the PDF), and \\appendix before the backup slides so the
          frame total counts the talk only. The plan's text is escaped; a figure whose file is
          missing becomes a framed "missing figure" box, never an \\includegraphics.
notes.md  the notes of every slide with its seconds and its start time in the talk.
deck.pptx the same slides on a 13.33 x 7.5 inch page (10 x 7.5 for 4:3): titles at 30 pt, body
          text at 22 pt and never below the 20 pt floor; a slide whose text does not fit is
          reported as over-full, not shrunk. Notes go in the notes pane. Its layout is not
          rendered here: open it and look.

The build refuses when the plan has lines it cannot read, when plan-check.json is missing, is
for another version of the plan or failed (--unchecked builds anyway and records it), and when a
file it would write was edited after the last build (--force keeps the edited file as
deck.edited.tex, notes.edited.md or deck.edited.pptx and writes a new one). build.json records
the plan's and every written file's SHA-256.

Exit code 1: a refusal, a missing figure, or an over-full PPTX slide; 2: a plan that cannot be
read. Standard library only for Beamer.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import re
import shutil
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("slide_plan", SCRIPTS / "slide_plan.py")
sp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sp)

TITLE_PT, BODY_PT, SOURCE_PT, BODY_FLOOR_PT = 30, 22, 14, 20
WIDE = 1.8          # a figure at least this many times wider than tall goes under the bullets
SPECIALS = {"\\": r"\textbackslash{}", "{": r"\{", "}": r"\}", "$": r"\$", "&": r"\&", "#": r"\#",
            "^": r"\textasciicircum{}", "_": r"\_", "%": r"\%", "~": r"\textasciitilde{}",
            "\u2212": r"\textminus{}", "\u00b5": r"\textmu{}", "\u2264": r"$\leq$", "\u2265": r"$\geq$",
            "\u2248": r"$\approx$", "\u2192": r"$\rightarrow$", "\u2190": r"$\leftarrow$",
            "\u2194": r"$\leftrightarrow$", "\u223c": r"$\sim$", "\u2260": r"$\neq$", "\u221e": r"$\infty$",
            "\u2026": r"\ldots{}", "\u2032": r"$'$", "\u00a0": "~", "\u2009": r"\,", "\u202f": r"\,"}
GREEK = ("alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu xi omicron pi rho "
         "varsigma sigma tau upsilon phi chi psi omega").split()
SPECIALS.update({chr(0x3B1 + i): f"$\\{name}$" for i, name in enumerate(GREEK) if name not in ("omicron", "varsigma")})
SPECIALS.update({chr(0x391 + i): f"$\\{name.capitalize()}$" for i, name in enumerate(GREEK)
                 if name in ("gamma", "delta", "theta", "lambda", "xi", "pi", "sigma", "upsilon", "phi", "psi", "omega")})

PREAMBLE = r"""\documentclass[aspectratio=<<ASPECT>>,11pt]{beamer}
\usepackage{iftex}
\ifPDFTeX
  \usepackage[T1]{fontenc}
  \usepackage{lmodern}
\else
  \usepackage{fontspec}
\fi
\usepackage{graphicx}
% Beamer's default theme, with our colours and fonts. Pages are 16 x 9 cm (12.8 x 9.6 for 4:3):
% projected at 13.33 inches wide, 11 pt type reads like about 23 pt in PowerPoint.
\definecolor{rzaccent}{HTML}{2F4F8F}
\definecolor{rzmuted}{HTML}{5F6670}
\setbeamercolor{structure}{fg=rzaccent}
\setbeamercolor{frametitle}{fg=rzaccent}
\setbeamercolor{title}{fg=rzaccent}
\setbeamercolor{footline}{fg=rzmuted}
\setbeamerfont{frametitle}{size=\large,series=\bfseries}
\setbeamerfont{title}{size=\Large,series=\bfseries}
\setbeamerfont{footline}{size=\scriptsize}
\setbeamertemplate{navigation symbols}{}
\setbeamertemplate{itemize items}[circle]
\setbeamertemplate{footline}[frame number]
\setbeamertemplate{page number in head/foot}[appendixframenumber]  % backup slides count apart
\pdfstringdefDisableCommands{\def\translate#1{#1}}  % the appendix's PDF bookmark
\setlength{\parskip}{0pt}
\newcommand{\rzsource}[1]{\par\vspace{2pt}{\scriptsize\color{rzmuted}#1\par}}
\newcommand{\rzmissing}[1]{\fbox{\parbox[c][3cm][c]{0.8\linewidth}{\centering\color{red}Missing figure: #1}}}
"""


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path: Path, text: str) -> None:
    """Write only a changed file, so that an unchanged deck.tex keeps the log beside it current."""
    if not path.is_file() or path.read_text(encoding="utf-8") != text:
        path.write_text(text, encoding="utf-8")


def tex(text: str) -> str:
    """Plain text from the plan, safe in LaTeX: specials escaped, common symbols in math."""
    out = "".join(SPECIALS.get(ch, ch) for ch in text)
    return re.sub(r'"([^"]*)"', r"``\1''", out)


def unsupported(text: str) -> list:
    """Characters pdflatex's fonts lack (beyond Latin and the symbols escaped above)."""
    return sorted({ch for ch in text if ord(ch) >= 0x250 and ch not in SPECIALS})


def figure_tex(slide: dict, row, width: str, height_cm: float, missing: list) -> list:
    label = slide["source"] or (row or {}).get("label", "")
    if row is None or not row["path"].is_file():
        missing.append({"slide": slide["n"], "figure": slide["figure"],
                        "why": "not in figures/manifest.json" if row is None else f"file missing: {row['path']}"})
        body = [rf"\rzmissing{{{tex(slide['figure'])}}}"]
    else:
        body = [rf"\includegraphics[width={width},height={height_cm:.1f}cm,keepaspectratio]{{figures/{row['file']}}}"]
    return [r"\centering", *body] + ([rf"\rzsource{{{tex(label)}}}"] if label else [])


def frame_tex(slide: dict, manifest: dict, missing: list) -> list:
    notes = [rf"\note{{{tex(p)}\par}}" for p in slide["notes"].split("\n\n") if p]
    if slide["kind"] == "title":
        return [r"\begin{frame}", r"\titlepage", *notes, r"\end{frame}", ""]
    if slide["kind"] == "section":
        head = [r"\begin{frame}", r"\vfill", r"\centering",
                rf"{{\usebeamerfont{{title}}\usebeamercolor[fg]{{title}}{tex(slide['title'])}\par}}", r"\vfill"]
        return head + notes + [r"\end{frame}", ""]
    lines = [rf"\begin{{frame}}[t]{{{tex(slide['title'])}}}"]
    # "{}" keeps a bullet that starts with "[" from being read as the item's label
    items = [r"\begin{itemize}"] + [rf"  \item{'{}' if b.startswith('[') else ''} {tex(b)}" for b in slide["bullets"]]
    items.append(r"\end{itemize}")
    row = manifest.get(slide["figure"]) if slide["figure"] else None
    pixels = (row or {}).get("pixels") or [4, 3]
    aspect = pixels[0] / max(pixels[1], 1)
    if not slide["figure"]:     # text alone gets the room a figure would take: larger type, more air
        lines += ([items[0], r"\large", r"\setlength{\itemsep}{0.7em}", *items[1:]] if slide["bullets"] else [])
    elif not slide["bullets"]:
        lines += figure_tex(slide, row, r"\textwidth", 5.9, missing)
    elif aspect >= WIDE:
        lines += items + [r"\vspace{2pt}"]
        lines += figure_tex(slide, row, r"\textwidth", max(2.6, 6.0 - 0.65 * len(slide["bullets"])), missing)
    else:
        lines += [r"\begin{columns}[T,onlytextwidth]", r"\begin{column}{0.42\textwidth}", *items,
                  r"\end{column}", r"\begin{column}{0.55\textwidth}"]
        lines += figure_tex(slide, row, r"\linewidth", 5.6, missing) + [r"\end{column}", r"\end{columns}"]
    return lines + notes + [r"\end{frame}", ""]


def deck_tex(plan: dict, manifest: dict, missing: list) -> str:
    front = plan["front"]
    when = tex(front.get("event", "")) + (rf"\\[2pt]{{\scriptsize doi:{tex(front['doi'])}}}" if front.get("doi") else "")
    head = [f"% Generated by researchzy-slides build_deck.py from {Path(plan['path']).name} "
            f"(SHA-256 {plan['sha256'][:12]}). Change the plan and build again; edits here are",
            "% kept only if you rename this file.",
            PREAMBLE.replace("<<ASPECT>>", "169" if front["aspect"] == "16:9" else "43"),
            rf"\title{{{tex(front['title'])}}}", rf"\subtitle{{{tex(front.get('subtitle', ''))}}}",
            rf"\author{{{tex(front.get('presenter', ''))}}}", rf"\institute{{{tex(front.get('affiliation', ''))}}}",
            rf"\date{{{when}}}", "", r"\begin{document}", ""]
    body, in_appendix = [], False
    for slide in plan["slides"]:
        if slide["backup"] and not in_appendix:
            body += ["% Backup slides: off the clock, and outside the frame total.", r"\appendix", ""]
            in_appendix = True
        body += frame_tex(slide, manifest, missing)
    return "\n".join(head + body + [r"\end{document}", ""])


def clock(seconds: int) -> str:
    return f"{seconds // 60}:{seconds % 60:02d}"


def notes_md(plan: dict) -> str:
    on_clock = [s for s in plan["slides"] if not s["backup"]]
    total = sum(s["seconds"] or 0 for s in on_clock)
    lines = [f"# Speaker notes: {plan['front']['title']}", "",
             f"{len(on_clock)} slides in {clock(total)} planned, for a slot of {plan['front']['minutes']:g} "
             "minutes. Times are the plan's Seconds: lines.", ""]
    start, in_backup = 0, False
    for s in plan["slides"]:
        if s["backup"] and not in_backup:
            lines += ["# Backup (off the clock)", ""]
            in_backup = True
        timing = "" if s["backup"] else (
            f" ({clock(s['seconds'])}, from {clock(start)})" if s["seconds"] is not None else " (no time planned)")
        lines += [f"## {s['n']}. {s['title']}{timing}", "", s["notes"] or "_No notes._", ""]
        start += 0 if s["backup"] else s["seconds"] or 0
    return "\n".join(lines)


def height_needed(paragraphs: list, width_in: float, pt: float, gap: float = 0.0) -> float:
    """Inches of text box these paragraphs need: about 0.5 em per character, lines at 1.2 em,
    `gap` em after each paragraph but the last, and the box's 0.1 inch inner margins."""
    per_line = max(8, int((width_in - 0.2) * 72 / (pt * 0.5)))
    lines = sum(max(1, math.ceil(len(p) / per_line)) for p in paragraphs)
    return (lines * 1.2 + gap * (len(paragraphs) - 1)) * pt / 72 + 0.1


def write_pptx(plan: dict, manifest: dict, path: Path) -> list:
    """Write the PowerPoint deck; returns the slides whose text does not fit."""
    from pptx import Presentation
    from pptx.dml.color import RGBColor
    from pptx.enum.text import MSO_AUTO_SIZE, PP_ALIGN
    from pptx.oxml.ns import qn
    from pptx.util import Inches, Pt

    wide = plan["front"]["aspect"] == "16:9"
    W, H, M = (13.333 if wide else 10.0), 7.5, 0.5
    deck = Presentation()
    deck.slide_width, deck.slide_height = Inches(W), Inches(H)
    accent, muted, overfull = RGBColor(0x2F, 0x4F, 0x8F), RGBColor(0x5F, 0x66, 0x70), []

    def box(slide, name, left, top, width, height, paragraphs, pt, colour=None, bold=False, align=None, bullets=False):
        shape = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height))
        shape.name = name
        frame = shape.text_frame
        frame.word_wrap, frame.auto_size = True, MSO_AUTO_SIZE.NONE
        for i, text in enumerate(paragraphs):
            para = frame.paragraphs[0] if i == 0 else frame.add_paragraph()
            run = para.add_run()
            run.text = text
            run.font.size, run.font.bold = Pt(pt), bold
            if colour is not None:
                run.font.color.rgb = colour
            if align is not None:
                para.alignment = align
            para.space_after = Pt(pt * 0.4 if bullets else 0)
            if bullets:     # a real bullet with a hanging indent, so wrapped lines line up
                ppr = para._p.get_or_add_pPr()
                ppr.set("marL", str(Pt(pt)))
                ppr.set("indent", str(-Pt(pt)))
                ppr.append(ppr.makeelement(qn("a:buChar"), {"char": "\u2022"}))
        return shape

    def fits(n, label, paragraphs, width, height, pt, gap=0.0):
        need = height_needed(paragraphs, width, pt, gap)
        if need > height + 0.05:
            overfull.append({"slide": n, "where": label, "needs_in": round(need, 2), "has_in": round(height, 2)})

    main = sum(1 for s in plan["slides"] if not s["backup"])
    for s in plan["slides"]:
        slide = deck.slides.add_slide(deck.slide_layouts[6])
        n, front = s["n"], plan["front"]
        number = f"Backup {n - main}" if s["backup"] else f"{n} / {main}"
        box(slide, "Slide number", W - 2.0, H - 0.45, 1.6, 0.35, [number], 12, muted, align=PP_ALIGN.RIGHT)
        if s["notes"]:
            slide.notes_slide.notes_text_frame.text = s["notes"]
        if s["kind"] in ("title", "section"):
            fits(n, "title", [s["title"]], W - 2 * M, 1.9, 36)
            box(slide, "Title", M, 1.6 if s["kind"] == "title" else 2.6, W - 2 * M, 1.9, [s["title"]], 36,
                accent, True, PP_ALIGN.CENTER)
            info = [v for v in (front.get("subtitle"), front.get("presenter"), front.get("affiliation"),
                                front.get("event"), front.get("doi") and "doi:" + front["doi"]) if v]
            if s["kind"] == "title" and info:
                box(slide, "Subtitle", M, 3.7, W - 2 * M, 2.6, info, 22, muted, align=PP_ALIGN.CENTER)
            continue
        fits(n, "title", [s["title"]], W - 2 * M, 1.05, TITLE_PT)
        box(slide, "Title", M, 0.3, W - 2 * M, 1.05, [s["title"]], TITLE_PT, accent, True)
        top, bottom = 1.5, H - 0.55
        row = manifest.get(s["figure"]) if s["figure"] else None
        has_figure = row is not None and row["path"].is_file()
        pixels = (row or {}).get("pixels") or [4, 3]
        aspect = pixels[0] / max(pixels[1], 1)
        side = has_figure and s["bullets"] and aspect < WIDE
        text_w = (W - 2 * M) * 0.42 if side else W - 2 * M
        shown = ["\u2022 " + b for b in s["bullets"]]
        text_h = bottom - top if (side or not has_figure) else min(bottom - top - 2.5, height_needed(shown, text_w, BODY_PT, 0.4))
        if s["bullets"]:
            fits(n, "bullets", shown, text_w, text_h, BODY_PT, 0.4)
            box(slide, "Body", M, top, text_w, text_h, s["bullets"], BODY_PT, bullets=True)
        if has_figure:
            label = s["source"] or row.get("label", "")
            left, area_top = (M + text_w + 0.3, top) if side else (M, top + (text_h + 0.15 if s["bullets"] else 0))
            area_w, area_h = (W - M - left, bottom - area_top - (0.45 if label else 0))
            pic_w = min(area_w, area_h * aspect)
            pic_h = pic_w / aspect
            pic_left = left + (area_w - pic_w) / 2
            slide.shapes.add_picture(str(row["path"]), Inches(pic_left), Inches(area_top), Inches(pic_w), Inches(pic_h))
            if label:
                box(slide, "Source label", left, area_top + pic_h + 0.05, area_w, 0.4, [label], SOURCE_PT, muted,
                    align=PP_ALIGN.CENTER)
    deck.save(str(path))
    return overfull


def guard(path: Path, record: dict, force: bool) -> str | None:
    """None when the file may be written; else why not. With --force the edited file is kept."""
    if not path.exists() or record.get("files", {}).get(path.name) == sha256(path):
        return None
    if not force:
        return (f"{path} was changed after the last build (or not written by it). Give --force to keep "
                f"it as {path.stem}.edited{path.suffix} and write a new one.")
    keep, i = path.with_name(f"{path.stem}.edited{path.suffix}"), 1
    while keep.exists():
        i += 1
        keep = path.with_name(f"{path.stem}.edited{i}{path.suffix}")
    shutil.copy2(path, keep)
    return None


def cmd_build(args) -> tuple:
    plan = sp.parse_plan(args.plan)
    folder = Path(args.plan).parent
    if plan["problems"]:
        return 1, {"refused": "the plan has lines the scripts cannot read: run slide_plan.py check and fix them",
                   "problems": plan["problems"]}
    check_path, check = folder / "plan-check.json", "not run"
    if check_path.is_file():
        result = json.loads(check_path.read_text(encoding="utf-8"))
        check = ("for another version of the plan" if result.get("plan_sha256") != plan["sha256"]
                 else "passed" if result.get("ok") else "failed")
    if check != "passed" and not args.unchecked:
        return 1, {"refused": f"slide_plan.py check has {check if check != 'not run' else 'not been run'} "
                              "on this plan. Run it, fix the errors, show the plan to the user, then build. "
                              "--unchecked builds anyway and records that."}
    record_path = folder / "build.json"
    record = json.loads(record_path.read_text(encoding="utf-8")) if record_path.is_file() else {}
    targets = [folder / "deck.tex", folder / "notes.md"] + ([folder / "deck.pptx"] if args.pptx else [])
    refusals = [why for why in (guard(p, record, args.force) for p in targets) if why]
    if refusals:
        return 1, {"refused": refusals}

    manifest, missing = sp.load_manifest(plan["path"]), []
    text = deck_tex(plan, manifest, missing)
    write(folder / "deck.tex", text)
    write(folder / "notes.md", notes_md(plan))
    odd = unsupported("".join(f"{s['title']} {' '.join(s['bullets'])} {s['notes']} {s['source']}"
                              for s in plan["slides"]) + " ".join(str(v) for v in plan["front"].values()))
    engine = "-xelatex" if odd else "-pdf"
    out = {"deck_tex": str(folder / "deck.tex"), "notes": str(folder / "notes.md"),
           "slides": len(plan["slides"]), "backup": sum(1 for s in plan["slides"] if s["backup"]),
           "plan_check": check, "missing_figures": missing,
           "compile": f"latexmk {engine} -cd -interaction=nonstopmode -halt-on-error -file-line-error {folder / 'deck.tex'}"}
    if odd:
        out["characters_for_xelatex"] = "".join(odd)
        out["engine_note"] = ("pdflatex's fonts lack these characters, so compile with xelatex; a script such "
                              "as Chinese also needs a font that has it (xeCJK and a CJK font)")
    files = {p.name: sha256(p) for p in targets[:2]}
    if args.pptx:
        try:
            import pptx  # noqa: F401
        except ImportError:
            out["pptx"] = "not written: python-pptx is not installed (pip install python-pptx)"
        else:
            out["overfull_pptx_slides"] = write_pptx(plan, manifest, folder / "deck.pptx")
            files["deck.pptx"] = sha256(folder / "deck.pptx")
            out["pptx"] = str(folder / "deck.pptx")
            out["pptx_layout"] = sp.NOT_RENDERED
    record = {"tool": sp.TOOL, "plan": str(args.plan), "plan_sha256": plan["sha256"], "plan_check": check,
              "files": {**record.get("files", {}), **files}}
    record_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    failed = missing or out.get("overfull_pptx_slides")
    return (1 if failed else 0), out


def main() -> int:
    parser = argparse.ArgumentParser(description="Build deck.tex (and deck.pptx) from the slide plan.")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("build", help="Write deck.tex, notes.md and build.json beside the plan")
    p.add_argument("plan")
    p.add_argument("--pptx", action="store_true", help="Also write deck.pptx (needs python-pptx)")
    p.add_argument("--force", action="store_true", help="Keep edited outputs as *.edited.* and write new ones")
    p.add_argument("--unchecked", action="store_true", help="Build although the plan check did not pass")
    args = parser.parse_args()
    try:
        code, out = cmd_build(args)
    except sp.PlanError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return code


if __name__ == "__main__":
    sys.exit(main())
