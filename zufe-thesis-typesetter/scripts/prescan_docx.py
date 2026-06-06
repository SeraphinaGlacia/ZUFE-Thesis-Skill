#!/usr/bin/env python3
"""流程 A 的 DOCX 轻量预扫描，用于可读性检查和 metadata 候选提取。"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from common import block_summary, classify_text, now_iso, print_json, write_json


def import_docx():
    try:
        import docx  # type: ignore
    except Exception as exc:
        raise RuntimeError(f"python-docx 不可用：{exc}") from exc
    return docx


def candidate(pattern: str, text: str) -> str:
    match = re.search(pattern, text, flags=re.IGNORECASE)
    return match.group(1).strip() if match else ""


def metadata_candidates(lines: list[str]) -> dict:
    joined = "\n".join(lines[:80])
    first_long = next((line for line in lines[:20] if len(line) >= 6 and not re.search(r"姓名|学号|学院|专业|导师|班级", line)), "")
    return {
        "thesis_title_cn": first_long,
        "name": candidate(r"(?:姓名|学生姓名)\s*[:：]\s*([^\n]+)", joined),
        "student_id": candidate(r"(?:学号)\s*[:：]\s*([A-Za-z0-9-]+)", joined),
        "college": candidate(r"(?:学院|院系)\s*[:：]\s*([^\n]+)", joined),
        "major": candidate(r"(?:专业)\s*[:：]\s*([^\n]+)", joined),
        "mentor": candidate(r"(?:导师|指导教师)\s*[:：]\s*([^\n]+)", joined),
        "class_name": candidate(r"(?:班级)\s*[:：]\s*([^\n]+)", joined),
        "date": candidate(r"((?:20\d{2}|二〇\d{2}|二零\d{2})年\s*\d{1,2}月?)", joined),
    }


def prescan(root: Path, docx_path: Path) -> dict:
    docx = import_docx()
    try:
        document = docx.Document(str(docx_path))
    except Exception as exc:
        return {
            "flow": "A",
            "gate": "word_prescan",
            "status": "blocked",
            "docx": str(docx_path),
            "error": str(exc),
            "next_steps": ["请用户提供未加密、未损坏、可打开的 .docx 文件。"],
        }

    paragraphs = []
    non_empty_lines = []
    for index, paragraph in enumerate(document.paragraphs, start=1):
        text = paragraph.text.strip()
        candidate_type, confidence = classify_text(text, getattr(paragraph.style, "name", ""))
        if text:
            non_empty_lines.append(text)
        paragraphs.append(
            {
                "index": index,
                "text": block_summary(text, 120),
                "style": getattr(paragraph.style, "name", ""),
                "candidate_type": candidate_type,
                "confidence": confidence,
            }
        )
    result = {
        "flow": "A",
        "gate": "word_prescan",
        "status": "passed" if non_empty_lines else "blocked",
        "docx": str(docx_path),
        "created_at": now_iso(),
        "counts": {
            "paragraphs": len(document.paragraphs),
            "non_empty_paragraphs": len(non_empty_lines),
            "tables": len(document.tables),
        },
        "metadata_candidates": metadata_candidates(non_empty_lines),
        "structure_preview": paragraphs[:80],
        "next_steps": [] if non_empty_lines else ["DOCX 没有可读文本，请用户重新另存为 DOCX 或更换文件。"],
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--docx", default="workspace/input/thesis.docx")
    parser.add_argument("--output", help="可选 JSON 输出路径。流程 A 不要输出到 thesis.json。")
    args = parser.parse_args()
    root = Path(args.root).expanduser().resolve()
    docx_path = (root / args.docx).resolve() if not Path(args.docx).is_absolute() else Path(args.docx).resolve()
    result = prescan(root, docx_path)
    if args.output:
        output = (root / args.output).resolve() if not Path(args.output).is_absolute() else Path(args.output).resolve()
        write_json(output, result)
    print_json(result)
    return 0 if result["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
