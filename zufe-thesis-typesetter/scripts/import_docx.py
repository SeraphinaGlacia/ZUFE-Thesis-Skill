#!/usr/bin/env python3
"""流程 B：正式抽取 DOCX，生成 thesis.json 和 extracted.md。"""

from __future__ import annotations

import argparse
import zipfile
from pathlib import Path

from common import block_summary, classify_text, now_iso, print_json, rel, write_json
from prescan_docx import metadata_candidates


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


def extract(root: Path, docx_path: Path) -> dict:
    docx, Paragraph, Table = import_docx_libs()
    document = docx.Document(str(docx_path))
    blocks = []
    markdown = ["# DOCX 抽取源块", ""]
    paragraph_count = table_count = 0
    non_empty_texts = []
    order = 0

    for child in document.element.body.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            paragraph_count += 1
            order += 1
            paragraph = Paragraph(child, document)
            text = paragraph.text.strip()
            style = getattr(paragraph.style, "name", "")
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
            block = {
                "id": f"p{paragraph_count:04d}",
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

    image_entries = media_entries(docx_path)
    for index, entry in enumerate(image_entries, start=1):
        order += 1
        block = {
            "id": f"img{index:04d}",
            "order": order,
            "source_type": "image",
            "candidate_type": "image",
            "text": "",
            "summary": entry,
            "evidence": {"docx_media_path": entry},
            "target_slot": None,
            "status": "needs_confirmation",
            "confidence": 0.3,
            "requires_confirmation": True,
            "confirmation": None,
            "discard_reason": None,
            "render_result": None,
        }
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
            "images": len(image_entries),
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
