#!/usr/bin/env python3
"""流程 B：正式抽取 DOCX，生成 thesis.json 和 extracted.md。"""

from __future__ import annotations

import argparse
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Any

from common import (
    block_summary,
    classify_text,
    file_fingerprint,
    now_iso,
    print_json,
    rel,
    write_json,
)
from prescan_docx import metadata_candidates

REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

UNSUPPORTED_FEATURES = {
    "footnote_or_endnote": {
        "severity": "high",
        "summary": "检测到脚注或尾注，第一版不会自动转换脚注/尾注内容。",
    },
    "equation_omml": {
        "severity": "high",
        "summary": "检测到 Word OMML 公式，第一版不会自动转换公式。",
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
    "hyperlink": {
        "severity": "medium",
        "summary": "检测到超链接，第一版只保留可抽取文本，链接目标需要确认。",
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


def run_payload(paragraph: Any) -> list[dict]:
    """提取段落中非空 run 的文本和格式证据。

    Args:
        paragraph (Any): python-docx Paragraph 对象。

    Returns:
        list[dict]: 保留粗体、斜体、上下标和字号的 run 列表。
    """
    runs = []
    for index, run in enumerate(paragraph.runs, start=1):
        text = run.text
        if not text:
            continue
        runs.append(
            {
                "index": index,
                "text": text,
                "bold": bool(run.bold),
                "italic": bool(run.italic),
                "superscript": bool(run.font.superscript),
                "subscript": bool(run.font.subscript),
                "font_size_pt": (round(run.font.size.pt, 2) if run.font.size is not None else None),
            }
        )
    return runs


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
            ("hyperlink", document_parts, {"hyperlink"}, None),
            ("equation_omml", parts, {"oMath", "oMathPara"}, None),
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
                "footnote_or_endnote",
                [name for name in parts if name in {"word/footnotes.xml", "word/endnotes.xml"}],
                {"footnote", "endnote"},
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
        if tag in {"p", "tbl"}:
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


def table_payload(table: Any) -> dict:
    """把 python-docx 表格转换为账本表格结构。

    Args:
        table (Any): python-docx Table 对象。

    Returns:
        dict: 表格行、行数和列数。
    """
    rows = []
    for row in table.rows:
        rows.append([cell.text.strip() for cell in row.cells])
    return {
        "rows": rows,
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
    unsupported_features = detect_unsupported_features(docx_path)

    for child, containers in iter_body_blocks(document.element.body):
        tag = local_name(child.tag)
        if tag == "p":
            paragraph_count += 1
            paragraph_id = f"p{paragraph_count:04d}"
            paragraph = paragraph_class(child, document)
            text = paragraph.text.strip()
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
                    "runs": run_payload(paragraph),
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
        elif tag == "tbl":
            table_count += 1
            order += 1
            table = table_class(child, document)
            metadata_tables.append(table)
            payload = table_payload(table)
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
