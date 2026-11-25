"""An invented hospital ethics-application form, built from XML strings, and filled copies of it.

The form has what real forms have and fillers break: a label with a trailing space and full-width brackets, a
vertically merged label cell, cells whose own formatting (宋体 and Times New Roman, 12 pt) differs from the
style (theme fonts, 10.5 pt), numbered section headings, a signature line after the last section, and a
header with a logo and a page number.
"""
from __future__ import annotations

import struct
import zipfile
import zlib
from pathlib import Path

NS = ('xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
      'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
      'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
      'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
      'xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture"')
REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
FONT = '<w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" w:eastAsia="宋体"/><w:sz w:val="24"/>'
KOREAN = '<w:rFonts w:ascii="맑은 고딕" w:hAnsi="맑은 고딕" w:eastAsia="맑은 고딕" w:cs="맑은 고딕"/>'

FIELDS = [
    {"label": "项目名称", "place": "right", "value": "监督下运动与常规治疗膝骨关节炎的随机对照试验"},
    {"label": "联系电话(手机)", "place": "right", "value": "012345"},
    {"label": "姓名", "place": "right", "value": "王某"},
    {"label": "职称", "place": "right", "value": "主治医师"},
    {"label": "是否涉及基因检测", "place": "right", "value": "No"},
    {"label": "研究摘要", "place": "below", "value": "两臂随机试验。\nPrimary outcome: WOMAC pain at 12 weeks."},
    {"label": "研究背景", "place": "after", "until": "风险与受益", "value": "膝骨关节炎常见。\n第二段：现有证据有限。"},
    {"label": "风险与受益", "place": "after", "until": "申请人签字： 日期：", "value": "不良事件按方案第8节记录和报告。"},
]


def png() -> bytes:
    """A 1 x 1 PNG: the logo."""
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"\x00\x20\x40\x80")) + chunk(b"IEND", b""))


def run(text: str, rpr: str = FONT, raw: bool = False) -> str:
    """A run holding text; a line break becomes w:br unless raw, when it is typed into w:t as Word never does."""
    parts = [text] if raw else text.split("\n")
    body = "<w:br/>".join(f'<w:t xml:space="preserve">{part}</w:t>' for part in parts)
    return f"<w:r>{f'<w:rPr>{rpr}</w:rPr>' if rpr else ''}{body}</w:r>"


def para(content: str = "", ppr: str = "") -> str:
    return f"<w:p><w:pPr>{ppr}<w:rPr>{FONT}</w:rPr></w:pPr>{content}</w:p>"


def cell(content: str, width: int, extra: str = "") -> str:
    return f'<w:tc><w:tcPr><w:tcW w:w="{width}" w:type="dxa"/>{extra}</w:tcPr>{content}</w:tc>'


def document(values=None, rpr: str = FONT, raw: bool = False) -> str:
    """The form's document.xml; with values (field number -> text) the filled copy, written as a careful filler would."""
    values = values or {}

    def value(number: int) -> str:
        return para(run(values[number], rpr, raw)) if number in values else para()

    def region(number: int, empty: int) -> str:
        if number not in values:
            return para() * empty
        return "".join(para(run(line, rpr, raw)) for line in ([values[number]] if raw else values[number].split("\n")))

    span = lambda n: f'<w:gridSpan w:val="{n}"/>'  # noqa: E731
    label = lambda text, n=1, extra="": cell(para(run(text)), 1500 * n, (span(n) if n > 1 else "") + extra)  # noqa: E731
    rows = [label("项目名称", 2) + cell(value(1), 5000),
            label("联系电话（手机） ", 2) + cell(value(2), 5000),
            label("研究者", 1, '<w:vMerge w:val="restart"/>') + label("姓名") + cell(value(3), 5000),
            cell(para(), 1500, "<w:vMerge/>") + label("职称") + cell(value(4), 5000),
            label("是否涉及基因检测", 2) + cell(value(5), 5000),
            label("研究摘要", 3),
            cell(value(6), 8000, span(3))]
    numbered = '<w:pStyle w:val="Heading1"/><w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr>'
    body = (para(run("伦理审查申请表"), '<w:pStyle w:val="Title"/>')
            + '<w:tbl><w:tblPr><w:tblW w:w="8000" w:type="dxa"/></w:tblPr><w:tblGrid><w:gridCol w:w="1500"/>'
              '<w:gridCol w:w="1500"/><w:gridCol w:w="5000"/></w:tblGrid>'
            + "".join(f"<w:tr>{r}</w:tr>" for r in rows) + "</w:tbl>"
            + para(run("研究背景"), numbered) + region(7, 2)
            + para(run("风险与受益"), numbered) + region(8, 1)
            + para(run("申请人签字：") + "<w:r><w:tab/></w:r>" + run("日期："))
            + '<w:sectPr><w:headerReference w:type="default" r:id="rId4"/><w:footerReference w:type="default" r:id="rId5"/>'
              '<w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1440" w:right="1800" w:bottom="1440" w:left="1800" '
              'w:header="851" w:footer="992" w:gutter="0"/></w:sectPr>')
    return f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<w:document {NS}><w:body>{body}</w:body></w:document>'


STYLES = (f'<w:styles {NS}><w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:asciiTheme="minorHAnsi" w:hAnsiTheme="minorHAnsi" '
          'w:eastAsiaTheme="minorEastAsia"/><w:sz w:val="21"/></w:rPr></w:rPrDefault></w:docDefaults>'
          '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style>'
          '<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:basedOn w:val="Normal"/>'
          '<w:rPr><w:b/><w:sz w:val="32"/></w:rPr></w:style>'
          '<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/>'
          '<w:pPr><w:outlineLvl w:val="0"/></w:pPr><w:rPr><w:b/></w:rPr></w:style></w:styles>')
NUMBERING = (f'<w:numbering {NS}><w:abstractNum w:abstractNumId="0"><w:lvl w:ilvl="0"><w:start w:val="1"/>'
             '<w:numFmt w:val="chineseCounting"/><w:lvlText w:val="%1、"/></w:lvl></w:abstractNum>'
             '<w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num></w:numbering>')
THEME = ('<a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" name="t"><a:themeElements>'
         '<a:fontScheme name="f"><a:majorFont><a:latin typeface="Calibri Light"/><a:ea typeface=""/><a:cs typeface=""/>'
         '</a:majorFont><a:minorFont><a:latin typeface="Calibri"/><a:ea typeface=""/><a:cs typeface=""/>'
         '<a:font script="Hans" typeface="等线"/></a:minorFont></a:fontScheme></a:themeElements></a:theme>')
LOGO = ('<w:drawing><wp:inline><wp:extent cx="360000" cy="360000"/><wp:docPr id="1" name="logo"/><a:graphic>'
        '<a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture"><pic:pic><pic:nvPicPr>'
        '<pic:cNvPr id="0" name="logo.png"/><pic:cNvPicPr/></pic:nvPicPr><pic:blipFill><a:blip r:embed="rId1"/>'
        '<a:stretch><a:fillRect/></a:stretch></pic:blipFill><pic:spPr><a:xfrm><a:off x="0" y="0"/>'
        '<a:ext cx="360000" cy="360000"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr></pic:pic>'
        '</a:graphicData></a:graphic></wp:inline></w:drawing>')
HEADER = (f'<w:hdr {NS}><w:p><w:r>{LOGO}</w:r><w:r><w:t xml:space="preserve">第 </w:t></w:r>'
          '<w:fldSimple w:instr=" PAGE "><w:r><w:t>1</w:t></w:r></w:fldSimple><w:r><w:t xml:space="preserve"> 页</w:t></w:r></w:p></w:hdr>')
FOOTER = f'<w:ftr {NS}><w:p><w:r><w:t>表格版本 2.1</w:t></w:r></w:p></w:ftr>'


def parts(document_xml: str) -> dict:
    ct = "application/vnd.openxmlformats-officedocument"
    rels = [("rId1", "styles", "styles.xml"), ("rId2", "numbering", "numbering.xml"), ("rId3", "theme", "theme/theme1.xml"),
            ("rId4", "header", "header1.xml"), ("rId5", "footer", "footer1.xml")]
    return {
        "[Content_Types].xml": '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/><Default Extension="png" ContentType="image/png"/>'
        f'<Override PartName="/word/document.xml" ContentType="{ct}.wordprocessingml.document.main+xml"/>'
        f'<Override PartName="/word/styles.xml" ContentType="{ct}.wordprocessingml.styles+xml"/>'
        f'<Override PartName="/word/numbering.xml" ContentType="{ct}.wordprocessingml.numbering+xml"/>'
        f'<Override PartName="/word/theme/theme1.xml" ContentType="{ct}.theme+xml"/>'
        f'<Override PartName="/word/header1.xml" ContentType="{ct}.wordprocessingml.header+xml"/>'
        f'<Override PartName="/word/footer1.xml" ContentType="{ct}.wordprocessingml.footer+xml"/></Types>',
        "_rels/.rels": '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        f'<Relationship Id="rId1" Type="{REL}/officeDocument" Target="word/document.xml"/></Relationships>',
        "word/_rels/document.xml.rels": '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        + "".join(f'<Relationship Id="{i}" Type="{REL}/{kind}" Target="{target}"/>' for i, kind, target in rels) + "</Relationships>",
        "word/_rels/header1.xml.rels": '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        f'<Relationship Id="rId1" Type="{REL}/image" Target="media/image1.png"/></Relationships>',
        "word/document.xml": document_xml, "word/styles.xml": STYLES, "word/numbering.xml": NUMBERING,
        "word/theme/theme1.xml": THEME, "word/header1.xml": HEADER, "word/footer1.xml": FOOTER, "word/media/image1.png": png(),
    }


def write_docx(path: Path, document_xml: str, **changes) -> Path:
    """A .docx of the form's parts with document_xml, and any part replaced: changes={"word/styles.xml": "…"}."""
    files = {**parts(document_xml), **{name.replace("__", "/"): body for name, body in changes.items()}}
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, body in files.items():
            archive.writestr(name, body.encode("utf-8") if isinstance(body, str) else body)
    return path


def filled_values() -> dict:
    return {number: field["value"] for number, field in enumerate(FIELDS, 1)}
