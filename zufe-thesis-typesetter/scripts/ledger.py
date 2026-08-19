#!/usr/bin/env python3
"""按需读取 thesis.json，避免 Agent 为局部判断加载完整账本。"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from common import FINAL_BLOCK_STATES, block_summary, print_json, read_json, rel


def nonnegative_int(value: str) -> int:
    """解析非负分页偏移量。"""
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("必须是非负整数。")
    return parsed


def page_size(value: str) -> int:
    """解析有界分页大小。"""
    parsed = int(value)
    if not 1 <= parsed <= 100:
        raise argparse.ArgumentTypeError("必须在 1 到 100 之间。")
    return parsed


def blocks_from(thesis: dict[str, Any]) -> list[dict[str, Any]]:
    """返回账本源块；结构无效时拒绝静默降级为空列表。"""
    blocks = thesis.get("source_blocks", [])
    if not isinstance(blocks, list):
        raise ValueError("source_blocks 必须是列表。")
    invalid_indexes = [index for index, block in enumerate(blocks) if not isinstance(block, dict)]
    if invalid_indexes:
        raise ValueError(f"source_blocks 包含非对象条目，索引：{invalid_indexes[:10]}。")
    return blocks


def value_counts(items: list[dict[str, Any]], key: str) -> dict[str, int]:
    """按指定字段统计源块数量。"""
    counts = Counter(str(item.get(key) or "missing") for item in items)
    return dict(sorted(counts.items()))


def selected_evidence(block: dict[str, Any]) -> dict[str, Any]:
    """提取语义判断最常用的段落证据。"""
    evidence = block.get("evidence")
    if not isinstance(evidence, dict):
        return {}
    keys = (
        "style",
        "alignment",
        "bold_any",
        "italic_any",
        "font_sizes_pt",
        "container_path",
        "anchor_paragraph_id",
        "anchor_text",
    )
    return {key: evidence[key] for key in keys if key in evidence}


def compact_block(block: dict[str, Any]) -> dict[str, Any]:
    """生成适合分页列表的源块摘要。"""
    return {
        "id": block.get("id"),
        "order": block.get("order"),
        "source_type": block.get("source_type"),
        "candidate_type": block.get("candidate_type"),
        "semantic_role": block.get("semantic_role"),
        "level": block.get("level"),
        "render_title": block.get("render_title"),
        "status": block.get("status"),
        "confidence": block.get("confidence"),
        "target_slot": block.get("target_slot"),
        "text": block_summary(str(block.get("text") or block.get("summary") or ""), 180),
        "evidence": selected_evidence(block),
    }


def is_heading_candidate(block: dict[str, Any]) -> bool:
    """判断源块是否需要进入标题语义大纲。"""
    candidate_type = str(block.get("candidate_type") or "")
    semantic_role = str(block.get("semantic_role") or "")
    raw_level = block.get("level")
    has_explicit_level = (
        raw_level is not None and raw_level != "" and raw_level != 0 and raw_level != "0"
    )
    return (
        candidate_type == "heading"
        or candidate_type.endswith("_heading")
        or semantic_role in {"heading", "chapter_heading", "section_heading", "subsection_heading"}
        or has_explicit_level
    )


def paginate(items: list[dict[str, Any]], offset: int, limit: int) -> dict[str, Any]:
    """对源块摘要做稳定分页。"""
    page = items[offset : offset + limit]
    return {
        "total": len(items),
        "offset": offset,
        "limit": limit,
        "returned": len(page),
        "has_more": offset + len(page) < len(items),
        "items": page,
    }


def summary(thesis: dict[str, Any], thesis_path: str) -> dict[str, Any]:
    """汇总账本状态，不返回源块正文。"""
    blocks = blocks_from(thesis)
    unsupported = thesis.get("unsupported_features", [])
    unsupported = unsupported if isinstance(unsupported, list) else []
    unresolved_unsupported = [
        item
        for item in unsupported
        if isinstance(item, dict)
        and item.get("count")
        and item.get("status", "needs_confirmation")
        not in {"accepted_with_warning", "confirmed", "resolved"}
    ]
    structure = thesis.get("structure", {})
    chapters = structure.get("chapters", []) if isinstance(structure, dict) else []
    pending = [block for block in blocks if block.get("status") not in FINAL_BLOCK_STATES]
    return {
        "status": "passed",
        "command": "summary",
        "thesis_json": thesis_path,
        "schema_version": thesis.get("schema_version"),
        "source_block_count": len(blocks),
        "invalid_source_block_count": 0,
        "source_blocks_by_status": value_counts(blocks, "status"),
        "source_blocks_by_type": value_counts(blocks, "source_type"),
        "candidate_types": value_counts(blocks, "candidate_type"),
        "pending_count": len(pending),
        "heading_candidate_count": sum(1 for block in blocks if is_heading_candidate(block)),
        "chapter_count": len(chapters) if isinstance(chapters, list) else 0,
        "unsupported_feature_count": len(unsupported),
        "unresolved_unsupported_feature_count": len(unresolved_unsupported),
    }


def pending(thesis: dict[str, Any], offset: int, limit: int) -> dict[str, Any]:
    """分页返回尚未完成处理的源块摘要。"""
    items = [
        compact_block(block)
        for block in blocks_from(thesis)
        if block.get("status") not in FINAL_BLOCK_STATES
    ]
    return {"status": "passed", "command": "pending", **paginate(items, offset, limit)}


def get_block(thesis: dict[str, Any], block_id: str) -> dict[str, Any]:
    """按稳定 ID 返回单个完整源块。"""
    matches = [block for block in blocks_from(thesis) if block.get("id") == block_id]
    if not matches:
        return {
            "status": "blocked",
            "command": "get",
            "error_code": "source_block_not_found",
            "block_id": block_id,
        }
    if len(matches) > 1:
        return {
            "status": "blocked",
            "command": "get",
            "error_code": "duplicate_source_block_id",
            "block_id": block_id,
            "match_count": len(matches),
        }
    return {"status": "passed", "command": "get", "block": matches[0]}


def outline(thesis: dict[str, Any], offset: int, limit: int) -> dict[str, Any]:
    """分页返回标题候选及前后文，供 Agent 统一确认层级。"""
    blocks = blocks_from(thesis)
    items = []
    for index, block in enumerate(blocks):
        if not is_heading_candidate(block):
            continue
        item = compact_block(block)
        item["previous"] = compact_block(blocks[index - 1]) if index > 0 else None
        item["next"] = compact_block(blocks[index + 1]) if index + 1 < len(blocks) else None
        items.append(item)
    return {"status": "passed", "command": "outline", **paginate(items, offset, limit)}


def main() -> int:
    """解析只读账本查询命令并输出 JSON。"""
    parser = argparse.ArgumentParser(
        description="按摘要、分页或源块 ID 读取 thesis.json；此脚本不会修改账本。"
    )
    parser.add_argument("--root", default=".", help="ZUFE-Thesis 模板根目录。")
    parser.add_argument(
        "--thesis-json",
        default="workspace/intermediate/thesis.json",
        help="相对模板根目录的流程 B 账本路径。",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("summary", help="只返回账本计数和状态汇总。")
    pending_parser = commands.add_parser("pending", help="分页返回尚未完成的源块摘要。")
    pending_parser.add_argument(
        "--offset", type=nonnegative_int, default=0, help="从第几个待处理源块开始，默认 0。"
    )
    pending_parser.add_argument(
        "--limit", type=page_size, default=20, help="本页最多返回 1 到 100 个源块，默认 20。"
    )
    get_parser = commands.add_parser("get", help="按 ID 返回一个完整源块。")
    get_parser.add_argument("block_id", help="import_docx.py 生成的稳定源块 ID。")
    outline_parser = commands.add_parser(
        "outline", help="分页返回标题候选、Word 证据和相邻源块摘要。"
    )
    outline_parser.add_argument(
        "--offset", type=nonnegative_int, default=0, help="从第几个标题候选开始，默认 0。"
    )
    outline_parser.add_argument(
        "--limit", type=page_size, default=20, help="本页最多返回 1 到 100 个候选，默认 20。"
    )
    args = parser.parse_args()

    root = Path(args.root).expanduser().resolve()
    thesis_path = (
        (root / args.thesis_json).resolve()
        if not Path(args.thesis_json).is_absolute()
        else Path(args.thesis_json).resolve()
    )
    try:
        thesis = read_json(thesis_path)
    except (OSError, json.JSONDecodeError) as exc:
        print_json(
            {
                "status": "blocked",
                "error_code": "thesis_json_unreadable",
                "thesis_json": rel(thesis_path, root),
                "detail": str(exc),
            }
        )
        return 2
    if not isinstance(thesis, dict):
        print_json(
            {
                "status": "blocked",
                "error_code": "thesis_json_type",
                "detail": "thesis.json 顶层必须是 JSON 对象。",
            }
        )
        return 2

    try:
        if args.command == "summary":
            result = summary(thesis, rel(thesis_path, root))
        elif args.command == "pending":
            result = pending(thesis, args.offset, args.limit)
        elif args.command == "get":
            result = get_block(thesis, args.block_id)
        else:
            result = outline(thesis, args.offset, args.limit)
    except ValueError as exc:
        result = {
            "status": "blocked",
            "error_code": "source_blocks_invalid",
            "detail": str(exc),
        }
    print_json(result)
    return 0 if result["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
