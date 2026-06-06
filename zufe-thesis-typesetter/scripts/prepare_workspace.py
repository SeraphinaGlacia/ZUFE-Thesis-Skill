#!/usr/bin/env python3
"""创建标准工作区，并在用户批准后整理 Word 输入。"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from common import archive_path, ensure_workspace, item, overall_status, print_json, rel


def directory_has_payload(path: Path) -> bool:
    if not path.exists():
        return False
    return any(child.name != ".DS_Store" for child in path.iterdir())


def archive_outputs(root: Path) -> list[str]:
    moved = []
    archive_root = archive_path(root, "flow-a-old-outputs")
    for relative in ("workspace/intermediate", "workspace/output"):
        source = root / relative
        if not directory_has_payload(source):
            continue
        target = archive_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(target))
        source.mkdir(parents=True, exist_ok=True)
        moved.append(rel(target, root))
    return moved


def prepare(root: Path, word: Path | None, move_word: bool, copy_word: bool, archive_existing: bool) -> dict:
    checks = []
    ensure_workspace(root)
    checks.append(item("workspace", "passed", "标准 workspace 目录已存在。"))

    archived = []
    old_payload = [
        relative
        for relative in ("workspace/intermediate", "workspace/output")
        if directory_has_payload(root / relative)
    ]
    if old_payload and archive_existing:
        archived = archive_outputs(root)
        checks.append(item("old_outputs", "passed", "旧 intermediate/output 产物已归档。", archived=archived))
    elif old_payload:
        checks.append(
            item(
                "old_outputs",
                "blocked",
                "检测到旧 intermediate 或 output 产物，不能静默覆盖。",
                paths=old_payload,
            )
        )
    else:
        checks.append(item("old_outputs", "passed", "未检测到旧 intermediate/output 产物。"))

    target = root / "workspace/input/thesis.docx"
    if word is None:
        status = "passed" if target.exists() else "needs_confirmation"
        checks.append(
            item(
                "word_input",
                status,
                "标准 thesis.docx 已存在。" if target.exists() else "没有提供 Word 文件，标准路径也不存在 thesis.docx。",
                target=rel(target, root),
            )
        )
    else:
        source = word.expanduser().resolve()
        if not source.exists():
            checks.append(item("word_input", "blocked", "提供的 Word 文件不存在。", source=str(source)))
        elif source.suffix.lower() == ".doc":
            checks.append(
                item(
                    "word_input",
                    "blocked",
                    ".doc 输入需要单独获得转换批准后才能继续。",
                    source=str(source),
                )
            )
        elif source.suffix.lower() != ".docx":
            checks.append(item("word_input", "blocked", "第一版只接受 .docx 输入。", source=str(source)))
        elif target.exists() and source != target.resolve():
            checks.append(
                item(
                    "word_input",
                    "blocked",
                    "workspace/input/thesis.docx 已存在，不能默认覆盖。",
                    source=str(source),
                    target=rel(target, root),
                )
            )
        elif move_word and copy_word:
            checks.append(item("word_input", "blocked", "只能选择 --move-word 或 --copy-word 其中一个。"))
        elif move_word:
            target.parent.mkdir(parents=True, exist_ok=True)
            if source != target.resolve():
                shutil.move(str(source), str(target))
            checks.append(item("word_input", "passed", "Word 文件已移动到标准路径。", target=rel(target, root)))
        elif copy_word:
            target.parent.mkdir(parents=True, exist_ok=True)
            if source != target.resolve():
                shutil.copy2(source, target)
            checks.append(item("word_input", "passed", "Word 文件已复制到标准路径。", target=rel(target, root)))
        elif source == target.resolve():
            checks.append(item("word_input", "passed", "Word 文件已经在标准路径。", target=rel(target, root)))
        else:
            checks.append(
                item(
                    "word_input",
                    "needs_confirmation",
                    "已提供 Word 文件，但移动或复制需要用户明确批准。",
                    source=str(source),
                    target=rel(target, root),
                )
            )

    status = overall_status(checks)
    return {
        "flow": "A",
        "gate": "workspace_and_word",
        "status": status,
        "checks": checks,
        "canonical_docx": rel(target, root),
        "next_steps": [] if status == "passed" else [
            "向用户确认如何处理 Word 文件或旧输出。",
            "只有说明原文件会离开原位置并获得批准后，才使用 --move-word。",
            "只有获得用户批准后，才使用 --archive-existing-output。",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--word", type=Path)
    parser.add_argument("--move-word", action="store_true")
    parser.add_argument("--copy-word", action="store_true")
    parser.add_argument("--archive-existing-output", action="store_true")
    args = parser.parse_args()
    result = prepare(
        Path(args.root).expanduser().resolve(),
        args.word,
        args.move_word,
        args.copy_word,
        args.archive_existing_output,
    )
    print_json(result)
    return 0 if result["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
