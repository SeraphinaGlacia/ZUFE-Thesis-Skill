#!/usr/bin/env python3
"""流程 B：正式抽取 DOCX，生成 thesis.json 和 extracted.md。"""

from __future__ import annotations

import argparse
import zipfile
from pathlib import Path

from common import block_summary, classify_text, now_iso, print_json, rel, write_json
from prescan_docx import metadata_candidates

REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def import_docx_libs():
    try:
        import docx  # type: ignore
        from docx.table import Table  # type: ignore
        from docx.text.paragraph import Paragraph  # type: ignore
    except Exception as exc:
        raise RuntimeError(f"python-docx 不可用：{exc}") from exc
    return docx, Paragraph, Table


def paragraph_evidence(paragraph) -> dict:
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


def run_payload(paragraph) -> list[dict]:
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
                "font_size_pt": round(run.font.size.pt, 2) if run.font.size is not None else None,
            }
        )
    return runs


def relationship_media_path(paragraph, relationship_id: str) -> str | None:
    part = getattr(paragraph, "part", None)
    related_parts = getattr(part, "related_parts", {}) if part is not None else {}
    related = related_parts.get(relationship_id)
    partname = getattr(related, "partname", None)
    if partname is None:
        return None
    return str(partname).lstrip("/")


def paragraph_image_refs(paragraph, paragraph_id: str, anchor_text: str) -> list[dict]:
    refs = []
    seen = set()
    for blip in paragraph._element.xpath(".//*[local-name()='blip']"):
        relationship_id = blip.get(f"{{{REL_NS}}}embed") or blip.get(f"{{{REL_NS}}}link")
        if not relationship_id:
            continue
        media_path = relationship_media_path(paragraph, relationship_id)
        if not media_path:
            continue
        key = (relationship_id, media_path)
        if key in seen:
            continue
        seen.add(key)
        refs.append(
            {
                "relationship_id": relationship_id,
                "docx_media_path": media_path,
                "anchor_paragraph_id": paragraph_id,
                "anchor_text": block_summary(anchor_text),
            }
        )
    return refs


def table_payload(table) -> dict:
    rows = []
    for row in table.rows:
        rows.append([cell.text.strip() for cell in row.cells])
    return {
        "rows": rows,
        "row_count": len(rows),
        "column_count": max((len(row) for row in rows), default=0),
    }


def media_entries(docx_path: Path) -> list[str]:
    entries = []
    with zipfile.ZipFile(docx_path) as archive:
        for name in archive.namelist():
            if name.startswith("word/media/") and not name.endswith("/"):
                entries.append(name)
    return sorted(entries)


def image_block(image_index: int, order: int, evidence: dict, *, anchored: bool) -> dict:
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
    docx, Paragraph, Table = import_docx_libs()
    document = docx.Document(str(docx_path))
    blocks = []
    markdown = ["# DOCX 抽取源块", ""]
    paragraph_count = table_count = 0
    non_empty_texts = []
    order = 0
    image_count = 0
    anchored_media_paths = set()

    for child in document.element.body.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            paragraph_count += 1
            paragraph_id = f"p{paragraph_count:04d}"
            paragraph = Paragraph(child, document)
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
                block = {
                    "id": paragraph_id,
                    "order": order,
                    "source_type": "paragraph",
                    "candidate_type": candidate_type,
                    "text": text,
                    "summary": block_summary(text),
                    "runs": run_payload(paragraph),
                    "evidence": paragraph_evidence(paragraph),
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
            table = Table(child, document)
            payload = table_payload(table)
            block = {
                "id": f"t{table_count:04d}",
                "order": order,
                "source_type": "table",
                "candidate_type": "table",
                "text": "",
                "summary": f"表格 {payload['row_count']}x{payload['column_count']}",
                "table": payload,
                "evidence": {"position": order},
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

    unanchored_images = [entry for entry in media_entries(docx_path) if entry not in anchored_media_paths]
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
        "created_at": now_iso(),
        "counts": {
            "total_source_blocks": len(blocks),
            "paragraphs": paragraph_count,
            "tables": table_count,
            "images": image_count,
        },
        "metadata_candidates": metadata_candidates(non_empty_texts),
        "metadata": {},
        "structure": {"chapters": []},
        "source_blocks": blocks,
        "render_log": [],
        "warnings": [
            "初始抽取会把非空内容标记为 needs_confirmation，Codex 确认目标槽位后才能渲染。",
        ],
    }
    intermediate = root / "workspace/intermediate"
    write_json(intermediate / "thesis.json", thesis)
    (intermediate / "extracted.md").write_text("\n".join(markdown) + "\n", encoding="utf-8")
    return {
        "flow": "B",
        "step": "import_docx",
        "status": "needs_confirmation",
        "thesis_json": rel(intermediate / "thesis.json", root),
        "extracted_md": rel(intermediate / "extracted.md", root),
        "counts": thesis["counts"],
        "next_steps": [
            "Codex 必须分配目标槽位并解决低置信度源块后再渲染。",
            "只有映射和渲染完成后，才能运行 check_flow_b_gate.py 判断是否进入流程 C。",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--docx", default="workspace/input/thesis.docx")
    args = parser.parse_args()
    root = Path(args.root).expanduser().resolve()
    docx_path = (root / args.docx).resolve() if not Path(args.docx).is_absolute() else Path(args.docx).resolve()
    result = extract(root, docx_path)
    print_json(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
