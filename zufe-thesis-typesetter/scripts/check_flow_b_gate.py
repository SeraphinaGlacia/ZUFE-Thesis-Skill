#!/usr/bin/env python3
"""检查流程 B 是否可以把工程交给流程 C。"""

from __future__ import annotations

import argparse
from pathlib import Path

from common import FINAL_BLOCK_STATES, print_json, read_json


def check(root: Path, thesis_path: Path) -> dict:
    thesis = read_json(thesis_path)
    blocks = thesis.get("source_blocks", [])
    issues = []

    expected = thesis.get("counts", {}).get("total_source_blocks")
    if expected != len(blocks):
        issues.append({"check": "source_block_count", "detail": f"账本记录 {expected} 个源块，实际找到 {len(blocks)} 个。"})

    for block in blocks:
        block_id = block.get("id")
        status = block.get("status")
        text = (block.get("text") or "").strip()
        source_type = block.get("source_type")
        is_noise = status == "discarded_with_reason"
        if status not in FINAL_BLOCK_STATES:
            issues.append({"check": "source_block_state", "block_id": block_id, "detail": f"状态仍是 {status}。"})
        if status == "discarded_with_reason" and not block.get("discard_reason"):
            issues.append({"check": "discard_reason", "block_id": block_id, "detail": "丢弃源块没有记录原因。"})
        if status == "rendered" and not block.get("render_result"):
            issues.append({"check": "render_result", "block_id": block_id, "detail": "已渲染源块没有 render_result。"})
        if not is_noise and (text or source_type in {"table", "image"}) and not (block.get("target_slot") or block.get("discard_reason")):
            issues.append({"check": "target_slot", "block_id": block_id, "detail": "非噪声源块没有目标槽位或丢弃原因。"})

    required_targets = [
        "chapters/basicinfo.tex",
        "chapters/mainbody.tex",
        "Reference.bib",
    ]
    for target in required_targets:
        if not (root / target).exists():
            issues.append({"check": "target_exists", "target": target, "detail": "必需目标文件不存在。"})

    mainbody = root / "chapters/mainbody.tex"
    if mainbody.exists() and "\\input{chapters/" not in mainbody.read_text(encoding="utf-8", errors="ignore"):
        issues.append({"check": "chapter_order", "target": "chapters/mainbody.tex", "detail": "没有检测到章节 input。"})

    status = "passed" if not issues else "blocked"
    return {
        "flow": "B",
        "gate": "completion",
        "status": status,
        "issues": issues,
        "next_steps": [] if status == "passed" else [
            "解决所有问题后才能启动流程 C。",
            "需要用户确认的映射或丢弃决定必须先在对话中完成。",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--thesis-json", default="workspace/intermediate/thesis.json")
    args = parser.parse_args()
    root = Path(args.root).expanduser().resolve()
    thesis_path = (root / args.thesis_json).resolve() if not Path(args.thesis_json).is_absolute() else Path(args.thesis_json).resolve()
    result = check(root, thesis_path)
    print_json(result)
    return 0 if result["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
