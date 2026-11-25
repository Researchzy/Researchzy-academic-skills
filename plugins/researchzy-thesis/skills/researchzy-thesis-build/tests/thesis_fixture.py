"""Invented Word files and rules for the tests, built from XML strings with zipfile (no python-docx).

Nothing here comes from a real thesis, a real paper or a real school's rules. The thesis plants the
problems of the real task TB-1 that a script can catch: 11 pt body text set by direct formatting
against a 12 pt rule, arabic page numbers in the front matter, numbering that restarts in chapter 2,
a typed "2.1" on an automatically numbered heading that also skips a level, and a section whose
binding margin is narrower than the rule.
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/"
NS = f'xmlns:w="{W_NS}" xmlns:r="{R_NS}"'

STYLES = f"""<w:styles {NS}>
<w:docDefaults>
 <w:rPrDefault><w:rPr><w:rFonts w:asciiTheme="minorHAnsi" w:hAnsiTheme="minorHAnsi" w:eastAsiaTheme="minorEastAsia"/>
  <w:sz w:val="21"/></w:rPr></w:rPrDefault>
 <w:pPrDefault><w:pPr><w:spacing w:line="240" w:lineRule="auto"/></w:pPr></w:pPrDefault>
</w:docDefaults>
<w:style w:type="paragraph" w:default="1" w:styleId="a"><w:name w:val="Normal"/>
 <w:pPr><w:spacing w:line="360" w:lineRule="auto"/><w:ind w:firstLineChars="200" w:firstLine="480"/></w:pPr>
 <w:rPr><w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" w:eastAsia="宋体"/><w:sz w:val="24"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="BodyText"><w:name w:val="Body Text"/><w:basedOn w:val="a"/></w:style>
<w:style w:type="paragraph" w:styleId="1"><w:name w:val="heading 1"/><w:basedOn w:val="a"/>
 <w:pPr><w:numPr><w:numId w:val="1"/></w:numPr><w:outlineLvl w:val="0"/><w:ind w:firstLineChars="0" w:firstLine="0"/></w:pPr>
 <w:rPr><w:rFonts w:eastAsia="黑体"/><w:sz w:val="32"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="2"><w:name w:val="heading 2"/><w:basedOn w:val="1"/>
 <w:pPr><w:numPr><w:ilvl w:val="1"/><w:numId w:val="1"/></w:numPr><w:outlineLvl w:val="1"/></w:pPr><w:rPr><w:sz w:val="28"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="3"><w:name w:val="heading 3"/><w:basedOn w:val="1"/>
 <w:pPr><w:numPr><w:ilvl w:val="2"/><w:numId w:val="1"/></w:numPr><w:outlineLvl w:val="2"/></w:pPr><w:rPr><w:sz w:val="24"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Plain"><w:name w:val="Plain"/></w:style>
<w:style w:type="paragraph" w:styleId="TOC1"><w:name w:val="toc 1"/><w:basedOn w:val="a"/></w:style>
<w:style w:type="paragraph" w:styleId="Caption"><w:name w:val="caption"/><w:basedOn w:val="a"/><w:rPr><w:sz w:val="21"/></w:rPr></w:style>
</w:styles>"""

THEME = """<a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" name="Office"><a:themeElements>
<a:fontScheme name="Office">
 <a:majorFont><a:latin typeface="Calibri Light"/><a:ea typeface=""/><a:cs typeface=""/><a:font script="Hans" typeface="等线 Light"/></a:majorFont>
 <a:minorFont><a:latin typeface="Calibri"/><a:ea typeface=""/><a:cs typeface=""/><a:font script="Hans" typeface="等线"/></a:minorFont>
</a:fontScheme></a:themeElements></a:theme>"""

NUMBERING = f"""<w:numbering {NS}><w:abstractNum w:abstractNumId="0">
<w:lvl w:ilvl="0"><w:numFmt w:val="decimal"/><w:lvlText w:val="第%1章"/></w:lvl>
<w:lvl w:ilvl="1"><w:numFmt w:val="decimal"/><w:lvlText w:val="%1.%2"/></w:lvl>
<w:lvl w:ilvl="2"><w:numFmt w:val="decimal"/><w:lvlText w:val="%1.%2.%3"/></w:lvl>
</w:abstractNum><w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num></w:numbering>"""

PAGE_FOOTER = ('<w:p><w:pPr><w:jc w:val="center"/></w:pPr><w:r><w:fldChar w:fldCharType="begin"/></w:r>'
               '<w:r><w:instrText xml:space="preserve"> PAGE \\* MERGEFORMAT </w:instrText></w:r>'
               '<w:r><w:fldChar w:fldCharType="separate"/></w:r><w:r><w:t>1</w:t></w:r><w:r><w:fldChar w:fldCharType="end"/></w:r></w:p>')


def run(text: str, rpr: str = "") -> str:
    return "<w:r>" + (f"<w:rPr>{rpr}</w:rPr>" if rpr else "") + f'<w:t xml:space="preserve">{text}</w:t></w:r>'


def para(text: str = "", style: str = "", ppr: str = "", rpr: str = "", runs: str = "") -> str:
    props = (f'<w:pStyle w:val="{style}"/>' if style else "") + ppr
    return "<w:p>" + (f"<w:pPr>{props}</w:pPr>" if props else "") + (runs or (run(text, rpr) if text else "")) + "</w:p>"


def field(code: str, shown: str, end: bool = True) -> str:
    """A complex field: begin, code, separate, shown result, and (unless end is False) end."""
    return ('<w:r><w:fldChar w:fldCharType="begin"/></w:r>' + f'<w:r><w:instrText xml:space="preserve">{code}</w:instrText></w:r>'
            + '<w:r><w:fldChar w:fldCharType="separate"/></w:r>' + run(shown)
            + ('<w:r><w:fldChar w:fldCharType="end"/></w:r>' if end else ""))


def sect(left: int = 1701, start=None, fmt: str = "", footer: str = "", w: int = 11906, h: int = 16838) -> str:
    """Section properties: A4 by default, 2.5 cm margins with a 3 cm binding (left) margin."""
    attrs = (f' w:fmt="{fmt}"' if fmt else "") + (f' w:start="{start}"' if start is not None else "")
    return ("<w:sectPr>" + (f'<w:footerReference w:type="default" r:id="{footer}"/>' if footer else "")
            + f'<w:pgSz w:w="{w}" w:h="{h}"/><w:pgMar w:top="1417" w:right="1417" w:bottom="1417" w:left="{left}" '
            'w:header="851" w:footer="992" w:gutter="0"/>' + (f"<w:pgNumType{attrs}/>" if attrs else "") + "</w:sectPr>")


def body_para(text: str, rpr: str = "", end_section: str = "") -> str:
    return para(text, "a", ppr=end_section, rpr=rpr)


THESIS_BODY = "".join([
    para("某某大学博士学位论文（虚构）", "Plain"),                                                     # ¶ 1
    para("作者：张三", "Plain", ppr=sect()),                                                           # ¶ 2, section 1: cover, no page number
    para("摘要", "1", ppr='<w:numPr><w:numId w:val="0"/></w:numPr>'),                                 # ¶ 3
    body_para("本研究采用技术接受模型（TAM）考察教师对学习平台的接受，样本量为312人。"),             # ¶ 4
    para(style="TOC1", runs=field(' TOC \\o "1-3" \\h ', "第1章 绪论 1")),                              # ¶ 5
    body_para("目录之后的说明文字。", end_section=sect(footer="rIdFooter1")),                          # ¶ 6, section 2: arabic (planted)
    para("绪论", "1"),                                                                                 # ¶ 7, chapter 1, numbered
    body_para("第一段正文用宋体小四号字，Latin words use Times New Roman as the rule asks."),           # ¶ 8
    body_para("第二段正文同样按照规定排版，没有直接格式。"),                                           # ¶ 9
    body_para("第一章的最后一段正文。", end_section=sect(start=1)),                                     # ¶ 10, section 3 starts at 1
    para("第2章 研究方法", "1", ppr='<w:numPr><w:numId w:val="0"/></w:numPr>'),                       # ¶ 11, typed, no automatic number
    para("2.1 研究设计", "3"),                                                                         # ¶ 12, typed on automatic, skips level 2
    body_para("这一段来自已发表的论文，保留了十一磅的直接格式。", rpr='<w:sz w:val="22"/>'),          # ¶ 13
    body_para("第二段也是十一磅，In the published paper it was 11 pt.", rpr='<w:sz w:val="22"/>'),    # ¶ 14
    para("图2-1 研究框架", "Caption"),                                                                 # ¶ 15
    body_para("这一段的中文用了楷体，but the Latin text keeps its font.", rpr='<w:rFonts w:eastAsia="楷体"/>'),  # ¶ 16
    body_para("第二章的最后一段。", end_section=sect(left=1418, start=1)),                              # ¶ 17, section 4: restart, narrow left
    para("参考文献", "1", ppr='<w:numPr><w:numId w:val="0"/></w:numPr>'),                             # ¶ 18
    body_para("[1] 王伟. 教师技术接受研究[J]. 教育研究, 2020.", rpr='<w:sz w:val="21"/>'),            # ¶ 19, reference list
    sect(),                                                                                            # section 5
])


def make_docx(path: Path, body: str, styles: str = STYLES, numbering: str = NUMBERING, theme: str = THEME,
              footers: dict | None = None, settings: str = "") -> Path:
    footers = {"rIdFooter1": PAGE_FOOTER} if footers is None else footers
    rels = [f'<Relationship Id="rIdStyles" Type="{REL}styles" Target="styles.xml"/>']
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/'
                         'package/2006/content-types"><Default Extension="xml" ContentType="application/xml"/></Types>')
        archive.writestr("word/document.xml", f"<w:document {NS}><w:body>{body}</w:body></w:document>")
        archive.writestr("word/styles.xml", styles)
        if numbering:
            archive.writestr("word/numbering.xml", numbering)
            rels.append(f'<Relationship Id="rIdNumbering" Type="{REL}numbering" Target="numbering.xml"/>')
        if theme:
            archive.writestr("word/theme/theme1.xml", theme)
            rels.append(f'<Relationship Id="rIdTheme" Type="{REL}theme" Target="theme/theme1.xml"/>')
        for rid, xml in footers.items():
            archive.writestr(f"word/{rid}.xml", f"<w:ftr {NS}>{xml}</w:ftr>")
            rels.append(f'<Relationship Id="{rid}" Type="{REL}footer" Target="{rid}.xml"/>')
        if settings:
            archive.writestr("word/settings.xml", f"<w:settings {NS}>{settings}</w:settings>")
        archive.writestr("word/_rels/document.xml.rels", '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/'
                         'relationships">' + "".join(rels) + "</Relationships>")
    return path


# The school's rules as pdftotext would give them: spaces and breaks inside Chinese text, ASCII brackets
# where the record quotes full-width ones, and a third page that is a scanned image (no text but its number).
RULES_TEXT = ("示例大学研究生学位论文撰写规定（为测试编写）\n"
              "第三条  论文用 A4 纸 (210×297 毫米)。上下边距 2.5 厘米，左边\n距 3 厘米（装订侧），右边距 2.5 厘米。\n"
              "第四条  正文中文用宋体，西文用 Times New Roman，正文字号为小四号。\n"
              "\f第五条 章标题按“第1章”编号，节标题按“1.1”“1.1.1”编号。\n"
              "第六条 前置部分用罗马数字编页码，正文从第1章起用阿拉伯数字\n连续编页码，页码居中置于页脚。\n"
              "第七条 参考文献著录按 GB/T 7714-2015 执行。正文引用采用著者-出版年制。\n"
              "\f\n                                   3\n\f")


def rules_record() -> dict:
    stated = lambda topic, value, quote, where: {"topic": topic, "value": value, "source": "stated", "quote": quote,  # noqa: E731
                                                 "locator": where}
    return {
        "record": {"school": "示例大学（虚构）", "rules_source": "thesis-build/rules.txt", "template_source": "template.docx",
                   "date_read": "2026-11-18"},
        "rules": [
            stated("page_size", "210 x 297 mm", "论文用A4纸（210×297毫米）", "p. 1, 第三条"),
            stated("margins", {"top": "2.5 cm", "bottom": "2.5 cm", "left": "3 cm", "right": "2.5 cm"},
                   "上下边距2.5厘米，左边距3厘米（装订侧），右边距2.5厘米", "p. 1, 第三条"),
            stated("body_font", {"east_asian": "宋体", "latin": "Times New Roman"}, "正文中文用宋体，西文用Times New Roman",
                   "p. 1, 第四条"),
            stated("body_size", "小四", "正文字号为小四号", "p. 1, 第四条"),
            {"topic": "line_spacing", "source": "not_checked", "locator": "p. 3 (scanned image)",
             "note": "Page 3 has no text layer; the user was asked for a text version."},
            {"topic": "first_line_indent", "value": "2 characters", "source": "observed_in_template",
             "locator": "template.docx, style Normal"},
            stated("heading_numbering", "第1章, 1.1, 1.1.1", "章标题按“第1章”编号，节标题按“1.1”“1.1.1”编号", "p. 2, 第五条"),
            stated("page_numbers", {"front_matter": "roman", "main_matter": "arabic", "main_starts_at": 1,
                                    "position": "bottom center"},
                   "前置部分用罗马数字编页码，正文从第1章起用阿拉伯数字连续编页码，页码居中置于页脚", "p. 2, 第六条"),
            stated("reference_standard", "GB/T 7714-2015", "参考文献著录按GB/T 7714-2015执行", "p. 2, 第七条"),
            stated("citation_style", "author-year", "正文引用采用著者-出版年制", "p. 2, 第七条"),
        ],
        "conflicts": [
            {"topic": "citation_style", "detail": "The template's sample chapter uses numbered citations.", "decision": "pending"},
            {"topic": "reference_standard", "detail": "The student asked for the newest edition; the rules name GB/T 7714-2015.",
             "decision": "pending"},
        ],
    }


def write_rules(directory: Path, record: dict | None = None) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "rules.txt").write_text(RULES_TEXT, encoding="utf-8")
    path = directory / "rules.json"
    path.write_text(json.dumps(rules_record() if record is None else record, ensure_ascii=False, indent=1), encoding="utf-8")
    return path
