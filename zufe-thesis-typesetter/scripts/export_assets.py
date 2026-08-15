#!/usr/bin/env python3
"""抽取 DOCX 媒体到 Images/word_media，并把资源证据写回 thesis.json。"""

from __future__ import annotations

import argparse
import shutil
import zipfile
from pathlib import Path

from common import file_fingerprint, print_json, read_json, rel, safe_resolve_under, write_json


def export_assets(root: Path, docx_path: Path, thesis_path: Path) -> dict:
    """从 DOCX 复制媒体资源并回写 thesis.json 资源证据。

    Args:
        root (Path): ZUFE-Thesis 模板根目录。
        docx_path (Path): 标准输入 DOCX 路径。
        thesis_path (Path): ``workspace/intermediate/thesis.json`` 路径。

    Returns:
        dict: 资源导出结果，包含已复制媒体文件列表。
    """
    thesis = read_json(thesis_path)
    if not isinstance(thesis, dict):
        return {
            "flow": "B",
            "step": "export_assets",
            "status": "blocked",
            "gate": "thesis_json_structure",
            "detail": "thesis.json 顶层必须是 JSON 对象。",
            "next_steps": ["修复或重新生成 thesis.json 后再导出资源。"],
        }
    expected_fingerprint = thesis.get("source_docx_fingerprint")
    if not isinstance(expected_fingerprint, dict):
        return {
            "flow": "B",
            "step": "export_assets",
            "status": "blocked",
            "gate": "source_docx_fingerprint_missing",
            "detail": "thesis.json 没有源 DOCX 指纹，无法证明资源与抽取正文来自同一文件。",
            "next_steps": ["重新运行 import_docx.py 生成带指纹的 thesis.json。"],
        }
    actual_fingerprint = file_fingerprint(docx_path)
    if actual_fingerprint != expected_fingerprint:
        return {
            "flow": "B",
            "step": "export_assets",
            "status": "blocked",
            "gate": "source_docx_changed",
            "expected_fingerprint": expected_fingerprint,
            "actual_fingerprint": actual_fingerprint,
            "detail": "当前 DOCX 与生成 thesis.json 时的文件不一致，已停止资源导出。",
            "next_steps": ["确认正确的 DOCX 后，重新运行 import_docx.py 和 export_assets.py。"],
        }
    source_blocks = thesis.get("source_blocks", [])
    if not isinstance(source_blocks, list):
        return {
            "flow": "B",
            "step": "export_assets",
            "status": "blocked",
            "gate": "thesis_json_structure",
            "detail": "thesis.json.source_blocks 必须是列表。",
            "next_steps": ["修复或重新生成 thesis.json 后再导出资源。"],
        }

    output_dir = safe_resolve_under(root, "Images/word_media", "Images")
    output_dir.mkdir(parents=True, exist_ok=True)
    extracted = []
    with zipfile.ZipFile(docx_path) as archive:
        for name in archive.namelist():
            if not name.startswith("word/media/") or name.endswith("/"):
                continue
            target = safe_resolve_under(root, output_dir / Path(name).name, "Images")
            with archive.open(name) as source, target.open("wb") as destination:
                shutil.copyfileobj(source, destination)
            extracted.append({"docx_media_path": name, "output": rel(target, root)})

    by_media = {entry["docx_media_path"]: entry["output"] for entry in extracted}
    for block in source_blocks:
        if not isinstance(block, dict):
            continue
        evidence = block.get("evidence")
        media_path = evidence.get("docx_media_path") if isinstance(evidence, dict) else None
        if media_path in by_media:
            block["asset_output"] = by_media[media_path]
            block["asset_status"] = "exported"
            block["render_result"] = {"path": by_media[media_path], "kind": "asset_extracted"}
    thesis.setdefault("render_log", []).append(
        {
            "step": "export_assets",
            "status": "completed",
            "outputs": extracted,
        }
    )
    write_json(thesis_path, thesis)
    return {
        "flow": "B",
        "step": "export_assets",
        "status": "passed",
        "outputs": extracted,
        "note": "图片在章节 TeX 中的位置仍需要确认目标槽位。",
    }


def main() -> int:
    """解析命令行参数并执行 DOCX 媒体导出。

    Returns:
        int: 导出成功时返回 0，源文件或账本门禁阻塞时返回 2。
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--docx", default="workspace/input/thesis.docx")
    parser.add_argument("--thesis-json", default="workspace/intermediate/thesis.json")
    args = parser.parse_args()
    root = Path(args.root).expanduser().resolve()
    docx_path = (
        (root / args.docx).resolve()
        if not Path(args.docx).is_absolute()
        else Path(args.docx).resolve()
    )
    thesis_path = (
        (root / args.thesis_json).resolve()
        if not Path(args.thesis_json).is_absolute()
        else Path(args.thesis_json).resolve()
    )
    result = export_assets(root, docx_path, thesis_path)
    print_json(result)
    return 0 if result["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
