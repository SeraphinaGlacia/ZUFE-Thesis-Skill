#!/usr/bin/env python3
"""流程 B：正式抽取 DOCX，生成 thesis.json 和 extracted.md。"""

from __future__ import annotations

import argparse
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlsplit

from common import (
    block_summary,
    classify_text,
    file_fingerprint,
    now_iso,
    print_json,
    rel,
    write_json,
)
from omml_to_latex import convert_omml
from prescan_docx import metadata_candidates

PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

UNSUPPORTED_FEATURES = {
    "endnote": {
        "severity": "high",
        "summary": "检测到尾注；当前版本不会自动把尾注改写为 LaTeX 注释结构。",
    },
    "unconverted_footnote": {
        "severity": "high",
        "summary": "检测到无法完整转换的脚注，必须人工确认或补写。",
    },
    "unconverted_equation": {
        "severity": "high",
        "summary": "检测到无法完整转换的 Word 原生 OMML 公式，必须人工确认。",
    },
    "unconverted_hyperlink": {
        "severity": "medium",
        "summary": "检测到目标缺失、内部跳转或协议不受支持的超链接，必须确认。",
    },
    "textbox": {
        "severity": "high",
        "summary": "检测到文本框，第一版不会自动转换文本框内容。",
    },
    "tracked_changes": {
        "severity": "high",
        "summary": "检测到修订痕迹，必须先确认是否接受或拒绝修订。",
    },
    "comment": {
        "severity": "medium",
        "summary": "检测到批注，第一版不会把批注写入论文正文。",
    },
    "header_footer": {
        "severity": "medium",
        "summary": "检测到页眉或页脚，第一版不把页眉页脚当作正文自动转换。",
    },
    "content_control": {
        "severity": "high",
        "summary": "检测到 Word 内容控件；已展开可见块，但仍需确认没有隐藏、重复或条件内容。",
    },
    "alt_chunk": {
        "severity": "high",
        "summary": "检测到外部导入内容（altChunk），第一版无法可靠抽取其正文。",
    },
    "linked_image": {
        "severity": "high",
        "summary": "检测到外部链接图片；DOCX 中没有可独立导出的内嵌媒体内容。",
    },
    "chart_or_smartart": {
        "severity": "high",
        "summary": "检测到 Word 图表或 SmartArt，第一版无法可靠转换其数据和可编辑结构。",
    },
    "ole_object": {
        "severity": "high",
        "summary": "检测到 OLE 嵌入对象，第一版不会执行或转换其中内容。",
    },
    "field_code": {
        "severity": "medium",
        "summary": "检测到 Word 域代码；可见结果可能被抽取，但域语义和自动更新不会保留。",
    },
    "automatic_numbering": {
        "severity": "medium",
        "summary": "检测到 Word 自动编号；段落文本可能不包含界面中显示的编号。",
    },
}

TRANSPARENT_BODY_CONTAINERS = {"sdt", "sdtContent", "customXml", "smartTag"}
TRANSPARENT_INLINE_CONTAINERS = {
    "bdo",
    "customXml",
    "dir",
    "fldSimple",
    "sdt",
    "sdtContent",
    "smartTag",
}
SUPPORTED_HYPERLINK_SCHEMES = {"http", "https", "mailto"}


class InlineFeatureTracker:
    """记录已转换内联语义和无法自动完成的条目。"""

    def __init__(self) -> None:
        self.converted: Counter[str] = Counter()
        self.issues: list[dict] = []

    def record_converted(self, feature_type: str) -> None:
        """记录一处确定性转换成功的特性。"""
        self.converted[feature_type] += 1

    def record_issue(self, feature_type: str, location: dict, detail: str) -> None:
        """记录一处需要确认的转换问题。"""
        self.issues.append(
            {
                "type": feature_type,
                "location": {**location, "detail": detail},
            }
        )

    def unsupported_entries(self) -> list[dict]:
        """把逐项问题压缩为现有 ``unsupported_features`` 契约。"""
        grouped: dict[str, list[dict]] = defaultdict(list)
        for issue in self.issues:
            grouped[issue["type"]].append(issue["location"])
        return [
            feature_entry(feature_type, len(locations), locations)
            for feature_type, locations in sorted(grouped.items())
        ]


class DocxInlineContext:
    """DOCX 主文档和脚注内联抽取所需的只读包信息。"""

    def __init__(
        self,
        main_relationships: dict[str, dict],
        footnote_relationships: dict[str, dict],
        footnotes: dict[str, ET.Element],
    ) -> None:
        self.main_relationships = main_relationships
        self.footnote_relationships = footnote_relationships
        self.footnotes = footnotes
        self.tracker = InlineFeatureTracker()
        self.referenced_footnotes: set[str] = set()


def import_docx_libs() -> tuple[Any, Any, Any]:
    """导入 python-docx 及运行时构造段落/表格所需类型。

    Returns:
        tuple[Any, Any, Any]: ``docx`` 模块、Paragraph 类和 Table 类。

    Raises:
        RuntimeError: 当前 Python 环境无法导入 ``python-docx`` 时抛出。
    """
    try:
        import docx
        from docx.table import Table
        from docx.text.paragraph import Paragraph
    except Exception as exc:
        raise RuntimeError(f"python-docx 不可用：{exc}") from exc
    return docx, Paragraph, Table


def paragraph_evidence(paragraph: Any) -> dict:
    """提取段落级格式证据。

    Args:
        paragraph (Any): python-docx Paragraph 对象。

    Returns:
        dict: 段落样式、对齐方式、run 级格式汇总和字号证据。
    """
    sizes = []
    bold_any = False
    italic_any = False
    superscript_any = False
    subscript_any = False
    for run in paragraph.runs:
        if run.bold:
            bold_any = True
        if run.italic:
            italic_any = True
        if run.font.superscript:
            superscript_any = True
        if run.font.subscript:
            subscript_any = True
        if run.font.size is not None:
            sizes.append(round(run.font.size.pt, 2))
    return {
        "style": getattr(paragraph.style, "name", ""),
        "alignment": str(paragraph.alignment),
        "bold_any": bold_any,
        "italic_any": italic_any,
        "superscript_any": superscript_any,
        "subscript_any": subscript_any,
        "font_sizes_pt": sorted(set(sizes)),
        "run_count": len(paragraph.runs),
    }


def word_attribute(element: ET.Element, name: str) -> str:
    """读取 WordprocessingML 的 ``w:*`` 属性。"""
    return str(element.get(f"{{{WORD_NS}}}{name}", ""))


def run_property_enabled(properties: ET.Element | None, name: str) -> bool:
    """读取显式 run on/off 属性，不把样式继承误报为显式格式。"""
    if properties is None:
        return False
    element = properties.find(f"{{{WORD_NS}}}{name}")
    if element is None:
        return False
    return word_attribute(element, "val").strip().lower() not in {"0", "false", "off", "no"}


def run_format(element: ET.Element) -> dict:
    """从底层 ``w:r`` 提取与现有账本兼容的格式字段。"""
    properties = element.find(f"{{{WORD_NS}}}rPr")
    vertical = ""
    size = None
    if properties is not None:
        vertical_element = properties.find(f"{{{WORD_NS}}}vertAlign")
        if vertical_element is not None:
            vertical = word_attribute(vertical_element, "val")
        size_element = properties.find(f"{{{WORD_NS}}}sz")
        if size_element is not None:
            try:
                size = round(float(word_attribute(size_element, "val")) / 2, 2)
            except ValueError:
                size = None
    return {
        "bold": run_property_enabled(properties, "b"),
        "italic": run_property_enabled(properties, "i"),
        "superscript": vertical == "superscript",
        "subscript": vertical == "subscript",
        "font_size_pt": size,
    }


def text_item(text: str, formatting: dict) -> dict | None:
    """构造普通文本 run；空文本不进入账本。"""
    if not text:
        return None
    return {"text": text, **formatting}


def items_complete(items: list[dict]) -> bool:
    """判断内联条目及其嵌套内容是否都可确定性渲染。"""
    for item in items:
        kind = item.get("kind", "text")
        if kind == "text":
            continue
        if item.get("conversion_status") not in {"converted", "resolved"}:
            return False
        if kind == "hyperlink" and not items_complete(item.get("runs") or []):
            return False
        if kind == "footnote":
            for paragraph_items in item.get("content") or []:
                if not items_complete(paragraph_items):
                    return False
    return True


def inline_plain_text(items: list[dict]) -> str:
    """生成供语义判断和检索使用的有界可读文本。"""
    parts = []
    for item in items:
        kind = item.get("kind", "text")
        if kind in {"text", "hyperlink"}:
            parts.append(str(item.get("text") or ""))
        elif kind == "equation":
            latex = item.get("latex") or item.get("candidate_latex") or "未转换公式"
            parts.append(f"[公式: {latex}]")
        elif kind == "footnote":
            parts.append(f"[脚注: {item.get('text') or '未转换'}]")
        elif kind == "endnote":
            parts.append(f"[尾注 {item.get('note_id') or '?'}]")
    return "".join(parts)


def equation_item(
    element: ET.Element,
    *,
    display: bool,
    context: DocxInlineContext,
    location: dict,
) -> dict:
    """转换一个 Word 原生 OMML 公式，并记录未知结构。"""
    conversion = convert_omml(element)
    item = {
        "kind": "equation",
        "display": display,
        "source_format": "omml",
    }
    if conversion.complete:
        item.update({"latex": conversion.latex, "conversion_status": "converted"})
        context.tracker.record_converted("equations")
    else:
        item.update(
            {
                "candidate_latex": conversion.latex,
                "unsupported_omml_tags": list(conversion.unsupported_tags),
                "conversion_status": "needs_confirmation",
            }
        )
        detail = (
            "OMML 转换结果为空。"
            if not conversion.latex
            else "OMML 含未支持节点：" + ", ".join(conversion.unsupported_tags)
        )
        context.tracker.record_issue("unconverted_equation", location, detail)
    return item


def note_content(
    note_id: str,
    *,
    context: DocxInlineContext,
    location: dict,
) -> tuple[list[list[dict]], str, list[str]]:
    """提取脚注中的段落级内联内容，并返回无法承接的对象类型。"""
    footnote = context.footnotes.get(note_id)
    if footnote is None:
        return [], "", ["missing_footnote_body"]
    unsupported = sorted(
        {
            local_name(element.tag)
            for element in footnote.iter()
            if local_name(element.tag)
            in {
                "altChunk",
                "drawing",
                "fldChar",
                "fldSimple",
                "instrText",
                "numPr",
                "object",
                "oMathPara",
                "pict",
                "sdt",
                "tbl",
                "txbxContent",
            }
        }
    )
    paragraphs = []
    for paragraph_index, paragraph in enumerate(
        footnote.findall(f"{{{WORD_NS}}}p"),
        start=1,
    ):
        paragraph_location = {
            **location,
            "part": "word/footnotes.xml",
            "note_id": note_id,
            "note_paragraph": paragraph_index,
        }
        paragraphs.append(
            inline_items_from_parent(
                paragraph,
                context=context,
                relationships=context.footnote_relationships,
                location=paragraph_location,
                allow_footnotes=False,
            )
        )
    text = "\n".join(inline_plain_text(items).strip() for items in paragraphs).strip()
    return paragraphs, text, unsupported


def footnote_item(
    note_id: str,
    *,
    context: DocxInlineContext,
    location: dict,
    in_table: bool,
    allow_footnotes: bool,
) -> dict:
    """把脚注引用和脚注正文合并为一个可渲染内联条目。"""
    if not allow_footnotes:
        detail = "脚注或尾注中嵌套了脚注引用，OOXML 结构不符合可安全转换边界。"
        context.tracker.record_issue("unconverted_footnote", location, detail)
        return {
            "kind": "footnote",
            "note_id": note_id,
            "text": "",
            "content": [],
            "conversion_status": "needs_confirmation",
        }
    context.referenced_footnotes.add(note_id)
    content, text, unsupported = note_content(note_id, context=context, location=location)
    problems = []
    if not content or not text:
        problems.append("脚注正文缺失或为空。")
    if unsupported:
        problems.append("脚注含暂不支持对象：" + ", ".join(unsupported))
    if not all(items_complete(paragraph_items) for paragraph_items in content):
        problems.append("脚注正文仍有未完成的内联转换。")
    if in_table:
        problems.append("脚注位于表格单元格；当前表格渲染器不能可靠放置脚注正文。")
    status = "needs_confirmation" if problems else "converted"
    if problems:
        context.tracker.record_issue("unconverted_footnote", location, " ".join(problems))
    else:
        context.tracker.record_converted("footnotes")
    return {
        "kind": "footnote",
        "note_id": note_id,
        "text": text,
        "content": content,
        "conversion_status": status,
    }


def run_inline_items(
    element: ET.Element,
    *,
    context: DocxInlineContext,
    location: dict,
    allow_footnotes: bool,
    in_table: bool,
) -> list[dict]:
    """按 ``w:r`` 子节点顺序拆出文本、脚注和公式。"""
    formatting = run_format(element)
    items = []
    buffer = []

    def flush_text() -> None:
        item = text_item("".join(buffer), formatting)
        buffer.clear()
        if item is not None:
            items.append(item)

    for child in element:
        tag = local_name(child.tag)
        if tag == "rPr":
            continue
        if tag in {"t", "delText"}:
            buffer.append(child.text or "")
        elif tag == "tab":
            buffer.append("\t")
        elif tag in {"br", "cr"}:
            buffer.append("\n")
        elif tag == "noBreakHyphen":
            buffer.append("‑")
        elif tag == "softHyphen":
            buffer.append("\u00ad")
        elif tag == "footnoteReference":
            flush_text()
            note_id = word_attribute(child, "id")
            items.append(
                footnote_item(
                    note_id,
                    context=context,
                    location=location,
                    in_table=in_table,
                    allow_footnotes=allow_footnotes,
                )
            )
        elif tag == "endnoteReference":
            flush_text()
            items.append(
                {
                    "kind": "endnote",
                    "note_id": word_attribute(child, "id"),
                    "conversion_status": "needs_confirmation",
                }
            )
        elif tag in {"oMath", "oMathPara"}:
            flush_text()
            items.append(
                equation_item(
                    child,
                    display=tag == "oMathPara",
                    context=context,
                    location=location,
                )
            )
    flush_text()
    return items


def hyperlink_item(
    element: ET.Element,
    *,
    context: DocxInlineContext,
    relationships: dict[str, dict],
    location: dict,
    allow_footnotes: bool,
    in_table: bool,
) -> dict:
    """抽取外部超链接目标和带格式显示文本。"""
    nested = inline_items_from_parent(
        element,
        context=context,
        relationships=relationships,
        location=location,
        allow_footnotes=allow_footnotes,
        in_table=in_table,
    )
    relationship_id = element.get(f"{{{REL_NS}}}id", "")
    anchor = word_attribute(element, "anchor")
    relationship = relationships.get(relationship_id)
    target = str(relationship.get("target") or "") if relationship else ""
    target_mode = str(relationship.get("target_mode") or "") if relationship else ""
    url = target
    if url and anchor and "#" not in url:
        url = f"{url}#{anchor}"
    scheme = urlsplit(url).scheme.lower()
    problems = []
    if not nested or not inline_plain_text(nested):
        problems.append("超链接没有可见显示文本。")
    if not relationship_id and anchor:
        problems.append("内部书签跳转尚未映射为 LaTeX label。")
    elif not relationship or target_mode.lower() != "external":
        problems.append("超链接关系目标缺失或不是外部关系。")
    elif scheme not in SUPPORTED_HYPERLINK_SCHEMES:
        problems.append(f"超链接协议 {scheme or 'unknown'} 不在自动转换范围。")
    elif any(character in url for character in "{}\\\r\n"):
        problems.append("超链接目标含不能安全写入 LaTeX 参数的控制字符。")
    if not items_complete(nested):
        problems.append("超链接显示内容仍有未完成的内联转换。")
    status = "needs_confirmation" if problems else "converted"
    if problems:
        context.tracker.record_issue("unconverted_hyperlink", location, " ".join(problems))
    else:
        context.tracker.record_converted("hyperlinks")
    return {
        "kind": "hyperlink",
        "text": inline_plain_text(nested),
        "url": url or None,
        "relationship_id": relationship_id or None,
        "anchor": anchor or None,
        "runs": nested,
        "conversion_status": status,
    }


def inline_items_from_parent(
    parent: ET.Element,
    *,
    context: DocxInlineContext,
    relationships: dict[str, dict],
    location: dict,
    allow_footnotes: bool = True,
    in_table: bool = False,
) -> list[dict]:
    """按 OOXML 顺序抽取段落或透明容器中的内联语义。"""
    items = []
    for child in parent:
        tag = local_name(child.tag)
        if tag == "r":
            items.extend(
                run_inline_items(
                    child,
                    context=context,
                    location=location,
                    allow_footnotes=allow_footnotes,
                    in_table=in_table,
                )
            )
        elif tag == "hyperlink":
            items.append(
                hyperlink_item(
                    child,
                    context=context,
                    relationships=relationships,
                    location=location,
                    allow_footnotes=allow_footnotes,
                    in_table=in_table,
                )
            )
        elif tag in {"oMath", "oMathPara"}:
            items.append(
                equation_item(
                    child,
                    display=tag == "oMathPara",
                    context=context,
                    location=location,
                )
            )
        elif tag in TRANSPARENT_INLINE_CONTAINERS or tag == "ins":
            items.extend(
                inline_items_from_parent(
                    child,
                    context=context,
                    relationships=relationships,
                    location=location,
                    allow_footnotes=allow_footnotes,
                    in_table=in_table,
                )
            )
    return items


def run_payload(
    paragraph: Any,
    *,
    context: DocxInlineContext | None = None,
    location: dict | None = None,
    in_table: bool = False,
) -> list[dict]:
    """按原始顺序提取文本 run、超链接、脚注和 Word 原生公式。"""
    active_context = context or DocxInlineContext({}, {}, {})
    items = inline_items_from_parent(
        paragraph._element,
        context=active_context,
        relationships=active_context.main_relationships,
        location=location or {"part": "word/document.xml"},
        in_table=in_table,
    )
    for index, item in enumerate(items, start=1):
        item["index"] = index
    return items


def local_name(tag: str) -> str:
    """从 XML QName 中取本地标签名。

    Args:
        tag (str): XML 标签名，可能包含命名空间。

    Returns:
        str: 不含命名空间的标签名。
    """
    return tag.rsplit("}", 1)[-1]


def xml_parts(names: list[str]) -> list[str]:
    """筛选 DOCX 中需要检查的 Word XML 部件。

    Args:
        names (list[str]): ZIP 包内全部文件名。

    Returns:
        list[str]: 需要参与 unsupported feature 扫描的 XML 部件。
    """
    return [
        name
        for name in names
        if name.startswith("word/")
        and name.endswith(".xml")
        and not name.startswith("word/_rels/")
        and name not in {"word/styles.xml", "word/settings.xml", "word/fontTable.xml"}
    ]


def xml_root(archive: zipfile.ZipFile, name: str) -> ET.Element | None:
    """读取并解析 DOCX 内部 XML 部件。

    Args:
        archive (zipfile.ZipFile): 已打开的 DOCX ZIP 包。
        name (str): XML 部件路径。

    Returns:
        ET.Element | None: XML 根节点；缺失或解析失败时返回 None。
    """
    try:
        return ET.fromstring(archive.read(name))
    except (KeyError, ET.ParseError):
        return None


def relationship_targets(archive: zipfile.ZipFile, part_name: str) -> dict[str, dict]:
    """读取 OOXML 部件的关系目标。"""
    part = PurePosixPath(part_name)
    relationship_name = (part.parent / "_rels" / f"{part.name}.rels").as_posix()
    root = xml_root(archive, relationship_name)
    if root is None:
        return {}
    relationships = {}
    for relationship in root.findall(f"{{{PACKAGE_REL_NS}}}Relationship"):
        relationship_id = relationship.get("Id")
        target = relationship.get("Target")
        if not relationship_id or not target:
            continue
        relationships[relationship_id] = {
            "target": target,
            "target_mode": relationship.get("TargetMode", "Internal"),
            "type": relationship.get("Type", ""),
        }
    return relationships


def footnote_elements(archive: zipfile.ZipFile) -> dict[str, ET.Element]:
    """读取非内置脚注节点，并按 Word 脚注 ID 建立索引。"""
    root = xml_root(archive, "word/footnotes.xml")
    if root is None:
        return {}
    notes = {}
    for footnote in root.findall(f"{{{WORD_NS}}}footnote"):
        note_id = footnote.get(f"{{{WORD_NS}}}id")
        if note_id and note_id not in {"-1", "0"}:
            notes[note_id] = footnote
    return notes


def load_inline_context(docx_path: Path) -> DocxInlineContext:
    """加载主文档关系、脚注关系和脚注正文。"""
    with zipfile.ZipFile(docx_path) as archive:
        return DocxInlineContext(
            main_relationships=relationship_targets(archive, "word/document.xml"),
            footnote_relationships=relationship_targets(archive, "word/footnotes.xml"),
            footnotes=footnote_elements(archive),
        )


def count_elements(
    archive: zipfile.ZipFile,
    part_names: list[str],
    element_names: set[str],
    *,
    exclude_ids: set[str] | None = None,
) -> tuple[int, list[dict]]:
    """统计指定 XML 标签在多个部件中的出现次数。

    Args:
        archive (zipfile.ZipFile): 已打开的 DOCX ZIP 包。
        part_names (list[str]): 待扫描 XML 部件路径。
        element_names (set[str]): 待统计的本地标签名集合。
        exclude_ids (set[str] | None): 需要排除的 Word 内置 ID。

    Returns:
        tuple[int, list[dict]]: 总数和每个部件的位置计数。
    """
    total = 0
    locations = []
    for name in part_names:
        root = xml_root(archive, name)
        if root is None:
            continue
        count = 0
        for element in root.iter():
            if local_name(element.tag) not in element_names:
                continue
            element_id = element.attrib.get(f"{{{WORD_NS}}}id")
            if exclude_ids and element_id in exclude_ids:
                continue
            count += 1
        if count:
            total += count
            locations.append({"part": name, "count": count})
    return total, locations


def feature_entry(feature_type: str, count: int, locations: list[dict]) -> dict:
    """构造 unsupported feature 账本条目。

    Args:
        feature_type (str): 暂不支持特性类型。
        count (int): 检测到的数量。
        locations (list[dict]): 位置证据列表。

    Returns:
        dict: ``thesis.json.unsupported_features`` 条目。
    """
    config = UNSUPPORTED_FEATURES[feature_type]
    return {
        "type": feature_type,
        "count": count,
        "severity": config["severity"],
        "status": "needs_confirmation",
        "summary": config["summary"],
        "locations": locations[:20],
    }


def count_linked_images(
    archive: zipfile.ZipFile,
    part_names: list[str],
) -> tuple[int, list[dict]]:
    """统计使用外部关系而非内嵌媒体的图片。

    Args:
        archive (zipfile.ZipFile): 已打开的 DOCX ZIP 包。
        part_names (list[str]): 待扫描的 Word XML 部件。

    Returns:
        tuple[int, list[dict]]: 外部链接图片总数和部件位置。
    """
    total = 0
    locations = []
    for name in part_names:
        root = xml_root(archive, name)
        if root is None:
            continue
        count = sum(
            1
            for element in root.iter()
            if local_name(element.tag) == "blip" and bool(element.attrib.get(f"{{{REL_NS}}}link"))
        )
        if count:
            total += count
            locations.append({"part": name, "count": count})
    return total, locations


def detect_unsupported_features(docx_path: Path) -> list[dict]:
    """检测第一版暂不自动转换的 DOCX 特性。

    Args:
        docx_path (Path): 标准输入 DOCX 路径。

    Returns:
        list[dict]: 需要用户或 Agent 确认的 unsupported feature 列表。
    """
    features = []
    with zipfile.ZipFile(docx_path) as archive:
        names = archive.namelist()
        parts = xml_parts(names)
        document_parts = [
            name
            for name in parts
            if name.startswith(("word/document", "word/header", "word/footer"))
        ]

        checks = [
            ("textbox", parts, {"txbxContent"}, None),
            ("tracked_changes", parts, {"ins", "del", "moveFrom", "moveTo"}, None),
            ("content_control", document_parts, {"sdt"}, None),
            ("alt_chunk", document_parts, {"altChunk"}, None),
            ("chart_or_smartart", document_parts, {"chart", "relIds"}, None),
            ("ole_object", document_parts, {"OLEObject", "object"}, None),
            ("field_code", document_parts, {"fldSimple", "fldChar", "instrText"}, None),
            ("automatic_numbering", document_parts, {"numPr"}, None),
            ("comment", [name for name in parts if name == "word/comments.xml"], {"comment"}, None),
            (
                "endnote",
                [name for name in parts if name == "word/endnotes.xml"],
                {"endnote"},
                {"-1", "0"},
            ),
        ]
        for feature_type, part_names, element_names, exclude_ids in checks:
            count, locations = count_elements(
                archive,
                part_names,
                element_names,
                exclude_ids=exclude_ids,
            )
            if count:
                features.append(feature_entry(feature_type, count, locations))

        linked_image_count, linked_image_locations = count_linked_images(archive, document_parts)
        if linked_image_count:
            features.append(
                feature_entry("linked_image", linked_image_count, linked_image_locations)
            )

        header_footer_parts = [
            name
            for name in names
            if (name.startswith("word/header") or name.startswith("word/footer"))
            and name.endswith(".xml")
        ]
        if header_footer_parts:
            features.append(
                feature_entry(
                    "header_footer",
                    len(header_footer_parts),
                    [{"part": name, "count": 1} for name in sorted(header_footer_parts)],
                )
            )
    return features


def iter_body_blocks(parent: Any, containers: tuple[str, ...] = ()):
    """按正文顺序枚举段落和表格，并展开透明 XML 容器。

    Args:
        parent (Any): Word XML 正文或容器节点。
        containers (tuple[str, ...]): 当前节点外层容器路径。

    Yields:
        tuple[Any, tuple[str, ...]]: 正文块 XML 节点及其容器路径。
    """
    for child in parent.iterchildren():
        tag = local_name(child.tag)
        if tag in {"p", "tbl", "oMathPara"}:
            yield child, containers
        elif tag in TRANSPARENT_BODY_CONTAINERS:
            yield from iter_body_blocks(child, (*containers, tag))


def relationship_media_path(paragraph: Any, relationship_id: str) -> str | None:
    """根据段落关系 ID 找到 DOCX 媒体路径。

    Args:
        paragraph (Any): python-docx Paragraph 对象。
        relationship_id (str): 图片 blip 的关系 ID。

    Returns:
        str | None: ``word/media/...`` 路径；无法解析时返回 None。
    """
    part = getattr(paragraph, "part", None)
    related_parts = getattr(part, "related_parts", {}) if part is not None else {}
    related = related_parts.get(relationship_id)
    partname = getattr(related, "partname", None)
    if partname is None:
        return None
    return str(partname).lstrip("/")


def paragraph_image_refs(
    paragraph: Any,
    paragraph_id: str,
    anchor_text: str,
) -> list[dict]:
    """从段落 XML 中提取图片锚点证据。

    python-docx 的高层 API 不会把内嵌图片作为正文块暴露，因此这里读取
    段落底层 XML 的 blip 节点，以保留图片在 Word 正文中的相对位置。

    Args:
        paragraph (Any): python-docx Paragraph 对象。
        paragraph_id (str): 段落源块 ID。
        anchor_text (str): 图片所在段落的文本摘要来源。

    Returns:
        list[dict]: 图片关系、媒体路径和锚点段落证据列表。
    """
    refs = []
    for occurrence, blip in enumerate(
        paragraph._element.xpath(".//*[local-name()='blip']"),
        start=1,
    ):
        relationship_id = blip.get(f"{{{REL_NS}}}embed") or blip.get(f"{{{REL_NS}}}link")
        if not relationship_id:
            continue
        media_path = relationship_media_path(paragraph, relationship_id)
        if not media_path:
            continue
        refs.append(
            {
                "relationship_id": relationship_id,
                "docx_media_path": media_path,
                "anchor_paragraph_id": paragraph_id,
                "anchor_image_occurrence": occurrence,
                "anchor_text": block_summary(anchor_text),
            }
        )
    return refs


def table_payload(
    table: Any,
    *,
    context: DocxInlineContext | None = None,
    table_id: str = "table",
) -> dict:
    """把 python-docx 表格转换为账本表格结构。

    Args:
        table (Any): python-docx Table 对象。

    Returns:
        dict: 表格行、行数和列数。
    """
    rows = []
    inline_rows = []
    for row_index, row in enumerate(table.rows, start=1):
        text_row = []
        inline_row = []
        for column_index, cell in enumerate(row.cells, start=1):
            cell_paragraphs = []
            cell_texts = []
            for paragraph_index, paragraph in enumerate(cell.paragraphs, start=1):
                items = run_payload(
                    paragraph,
                    context=context,
                    location={
                        "part": "word/document.xml",
                        "table_id": table_id,
                        "row": row_index,
                        "column": column_index,
                        "cell_paragraph": paragraph_index,
                    },
                    in_table=True,
                )
                cell_paragraphs.append(items)
                cell_texts.append(inline_plain_text(items).strip())
            text_row.append("\n".join(text for text in cell_texts if text))
            inline_row.append(cell_paragraphs)
        rows.append(text_row)
        inline_rows.append(inline_row)
    return {
        "rows": rows,
        "inline_rows": inline_rows,
        "row_count": len(rows),
        "column_count": max((len(row) for row in rows), default=0),
    }


def media_entries(docx_path: Path) -> list[str]:
    """列出 DOCX ZIP 中的媒体文件。

    Args:
        docx_path (Path): 标准输入 DOCX 路径。

    Returns:
        list[str]: 排序后的 ``word/media/...`` 文件路径列表。
    """
    entries = []
    with zipfile.ZipFile(docx_path) as archive:
        for name in archive.namelist():
            if name.startswith("word/media/") and not name.endswith("/"):
                entries.append(name)
    return sorted(entries)


def image_block(image_index: int, order: int, evidence: dict, *, anchored: bool) -> dict:
    """构造图片源块。

    Args:
        image_index (int): 图片源块序号。
        order (int): 原始内容顺序。
        evidence (dict): 图片媒体路径和锚点证据。
        anchored (bool): 图片是否已定位到正文段落。

    Returns:
        dict: 需要确认目标槽位的 image 源块。
    """
    details = dict(evidence)
    details["position"] = order
    details["anchor_status"] = "anchored_in_body" if anchored else "unanchored_media_entry"
    return {
        "id": f"img{image_index:04d}",
        "order": order,
        "source_type": "image",
        "candidate_type": "image",
        "text": "",
        "summary": details.get("docx_media_path", ""),
        "evidence": details,
        "target_slot": None,
        "asset_status": "pending_export",
        "asset_output": None,
        "status": "needs_confirmation",
        "confidence": 0.5 if anchored else 0.3,
        "requires_confirmation": True,
        "confirmation": None,
        "discard_reason": None,
        "render_result": None,
    }


def extract(root: Path, docx_path: Path) -> dict:
    """正式抽取 DOCX 为 thesis.json 和 extracted.md。

    Args:
        root (Path): ZUFE-Thesis 模板根目录。
        docx_path (Path): 标准输入 DOCX 路径。

    Returns:
        dict: 流程 B 抽取结果和下一步提示。
    """
    docx, paragraph_class, table_class = import_docx_libs()
    document = docx.Document(str(docx_path))
    blocks = []
    markdown = ["# DOCX 抽取源块", ""]
    paragraph_count = table_count = 0
    non_empty_texts = []
    metadata_tables = []
    order = 0
    image_count = 0
    anchored_media_paths = set()
    inline_context = load_inline_context(docx_path)
    unsupported_features = detect_unsupported_features(docx_path)

    for child, containers in iter_body_blocks(document.element.body):
        tag = local_name(child.tag)
        if tag == "p":
            paragraph_count += 1
            paragraph_id = f"p{paragraph_count:04d}"
            paragraph = paragraph_class(child, document)
            runs = run_payload(
                paragraph,
                context=inline_context,
                location={"part": "word/document.xml", "paragraph_id": paragraph_id},
            )
            text = inline_plain_text(runs).strip()
            style = getattr(paragraph.style, "name", "")
            image_refs = paragraph_image_refs(paragraph, paragraph_id, text)
            candidate_type, confidence = classify_text(text, style)
            if text:
                non_empty_texts.append(text)
            if candidate_type == "empty":
                status = "discarded_with_reason"
                requires_confirmation = False
                discard_reason = "空段落"
            else:
                status = "needs_confirmation"
                requires_confirmation = True
                discard_reason = None
            anchor_block_order = None
            if text or not image_refs:
                order += 1
                anchor_block_order = order
                evidence = paragraph_evidence(paragraph)
                evidence["inline_item_count"] = len(runs)
                evidence["inline_kinds"] = dict(
                    sorted(Counter(item.get("kind", "text") for item in runs).items())
                )
                if containers:
                    evidence["container_path"] = list(containers)
                    evidence["inside_content_control"] = "sdt" in containers
                block = {
                    "id": paragraph_id,
                    "order": order,
                    "source_type": "paragraph",
                    "candidate_type": candidate_type,
                    "text": text,
                    "summary": block_summary(text),
                    "runs": runs,
                    "evidence": evidence,
                    "target_slot": None,
                    "status": status,
                    "confidence": confidence,
                    "requires_confirmation": requires_confirmation,
                    "confirmation": None,
                    "discard_reason": discard_reason,
                    "render_result": None,
                }
                blocks.append(block)
                markdown.append(f"## {block['id']} [{candidate_type}] {status}")
                markdown.append(block["summary"] or "(空)")
                markdown.append("")
            for image_ref in image_refs:
                order += 1
                image_count += 1
                if anchor_block_order is not None:
                    image_ref["anchor_block_order"] = anchor_block_order
                anchored_media_paths.add(image_ref["docx_media_path"])
                block = image_block(image_count, order, image_ref, anchored=True)
                blocks.append(block)
                markdown.append(f"## {block['id']} [image] needs_confirmation")
                markdown.append(f"{block['summary']} (anchor: {paragraph_id})")
                markdown.append("")
        elif tag == "oMathPara":
            paragraph_count += 1
            order += 1
            paragraph_id = f"p{paragraph_count:04d}"
            equation = equation_item(
                child,
                display=True,
                context=inline_context,
                location={"part": "word/document.xml", "paragraph_id": paragraph_id},
            )
            equation["index"] = 1
            text = inline_plain_text([equation])
            block = {
                "id": paragraph_id,
                "order": order,
                "source_type": "paragraph",
                "candidate_type": "body",
                "text": text,
                "summary": block_summary(text),
                "runs": [equation],
                "evidence": {
                    "style": "Office Math",
                    "display_equation": True,
                    **({"container_path": list(containers)} if containers else {}),
                },
                "target_slot": None,
                "status": "needs_confirmation",
                "confidence": 0.8,
                "requires_confirmation": True,
                "confirmation": None,
                "discard_reason": None,
                "render_result": None,
            }
            blocks.append(block)
            non_empty_texts.append(text)
            markdown.append(f"## {block['id']} [body] needs_confirmation")
            markdown.append(block["summary"])
            markdown.append("")
        elif tag == "tbl":
            table_count += 1
            order += 1
            table = table_class(child, document)
            metadata_tables.append(table)
            payload = table_payload(
                table,
                context=inline_context,
                table_id=f"t{table_count:04d}",
            )
            evidence = {"position": order}
            if containers:
                evidence["container_path"] = list(containers)
                evidence["inside_content_control"] = "sdt" in containers
            block = {
                "id": f"t{table_count:04d}",
                "order": order,
                "source_type": "table",
                "candidate_type": "table",
                "text": "",
                "summary": f"表格 {payload['row_count']}x{payload['column_count']}",
                "table": payload,
                "evidence": evidence,
                "target_slot": None,
                "status": "needs_confirmation",
                "confidence": 0.4,
                "requires_confirmation": True,
                "confirmation": None,
                "discard_reason": None,
                "render_result": None,
            }
            blocks.append(block)
            markdown.append(f"## {block['id']} [table] needs_confirmation")
            markdown.append(block["summary"])
            markdown.append("")

    for orphan_note_id in sorted(
        set(inline_context.footnotes) - inline_context.referenced_footnotes
    ):
        inline_context.tracker.record_issue(
            "unconverted_footnote",
            {"part": "word/footnotes.xml", "note_id": orphan_note_id},
            "脚注正文没有在主文档中找到对应引用。",
        )
    unsupported_features.extend(inline_context.tracker.unsupported_entries())

    unanchored_images = [
        entry for entry in media_entries(docx_path) if entry not in anchored_media_paths
    ]
    for entry in unanchored_images:
        order += 1
        image_count += 1
        block = image_block(image_count, order, {"docx_media_path": entry}, anchored=False)
        blocks.append(block)
        markdown.append(f"## {block['id']} [image] needs_confirmation")
        markdown.append(entry)
        markdown.append("")

    thesis = {
        "schema_version": "1.0",
        "source_docx": rel(docx_path, root),
        "source_docx_fingerprint": file_fingerprint(docx_path),
        "created_at": now_iso(),
        "counts": {
            "total_source_blocks": len(blocks),
            "paragraphs": paragraph_count,
            "tables": table_count,
            "images": image_count,
            "source_blocks_by_type": {
                source_type: sum(1 for block in blocks if block.get("source_type") == source_type)
                for source_type in ("paragraph", "table", "image")
            },
            "converted_inline_features": {
                feature_type: inline_context.tracker.converted.get(feature_type, 0)
                for feature_type in ("equations", "footnotes", "hyperlinks")
            },
            "unsupported_features": sum(feature["count"] for feature in unsupported_features),
        },
        "metadata_candidates": metadata_candidates(non_empty_texts, metadata_tables),
        "metadata": {},
        "structure": {"chapters": []},
        "unsupported_features": unsupported_features,
        "source_blocks": blocks,
        "render_log": [],
        "warnings": [
            "初始抽取会把非空内容标记为 needs_confirmation，Agent 确认目标槽位后才能渲染。",
            *(
                ["检测到暂不自动转换的 Word 特性，必须确认或处理后才能通过流程 B。"]
                if unsupported_features
                else []
            ),
        ],
    }
    intermediate = root / "workspace/intermediate"
    write_json(intermediate / "thesis.json", thesis)
    (intermediate / "extracted.md").write_text(
        "\n".join(markdown) + "\n",
        encoding="utf-8",
    )
    return {
        "flow": "B",
        "step": "import_docx",
        "status": "needs_confirmation",
        "thesis_json": rel(intermediate / "thesis.json", root),
        "extracted_md": rel(intermediate / "extracted.md", root),
        "counts": thesis["counts"],
        "next_steps": [
            "Agent 必须分配目标槽位并解决低置信度源块后再渲染。",
            "只有映射和渲染完成后，才能运行 check_flow_b_gate.py 判断是否进入流程 C。",
        ],
    }


def main() -> int:
    """解析命令行参数并执行 DOCX 正式抽取。

    Returns:
        int: 抽取脚本固定返回 0；后续确认由流程 B 门禁判断。
    """
    parser = argparse.ArgumentParser(
        description="正式抽取 DOCX，生成流程 B thesis.json 和 extracted.md。"
    )
    parser.add_argument("--root", default=".", help="ZUFE-Thesis 模板根目录。")
    parser.add_argument(
        "--docx",
        default="workspace/input/thesis.docx",
        help="相对模板根目录的 DOCX 输入路径。",
    )
    args = parser.parse_args()
    root = Path(args.root).expanduser().resolve()
    docx_path = (
        (root / args.docx).resolve()
        if not Path(args.docx).is_absolute()
        else Path(args.docx).resolve()
    )
    result = extract(root, docx_path)
    print_json(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
