#!/usr/bin/env python3
"""渲染已确认 BibTeX 条目，不编造参考文献。"""

from __future__ import annotations

import argparse
from pathlib import Path

from common import now_iso, print_json, read_json, rel, write_json


def render(root: Path, thesis_path: Path, input_bib: Path | None) -> dict:
    """渲染已确认参考文献到 Reference.bib。

    Args:
        root (Path): ZUFE-Thesis 模板根目录。
        thesis_path (Path): ``workspace/intermediate/thesis.json`` 路径。
        input_bib (Path | None): 用户额外提供的 BibTeX 文件路径。

    Returns:
        dict: 渲染结果；存在未确认参考文献时返回 needs_confirmation。
    """
    thesis = read_json(thesis_path, default={}) if thesis_path.exists() else {}
    if not isinstance(thesis, dict):
        return {
            "flow": "B",
            "step": "render_bib",
            "status": "blocked",
            "gate": "thesis_json_structure",
            "detail": "thesis.json 顶层必须是 JSON 对象。",
            "next_steps": ["修复或重新生成 thesis.json 后再渲染参考文献。"],
        }
    references = thesis.get("references", [])
    source_blocks = thesis.get("source_blocks", [])
    if not isinstance(references, list) or not isinstance(source_blocks, list):
        return {
            "flow": "B",
            "step": "render_bib",
            "status": "blocked",
            "gate": "thesis_json_structure",
            "detail": "thesis.json.references 和 source_blocks 必须是列表。",
            "next_steps": ["修复或重新生成 thesis.json 后再渲染参考文献。"],
        }
    entries = []
    warnings = []
    blocks_to_render = []
    blocks_needing_confirmation = []

    if input_bib and input_bib.exists():
        input_text = input_bib.read_text(encoding="utf-8").strip()
        if input_text:
            entries.append(input_text)
        else:
            warnings.append(f"外部 BibTeX 文件为空：{input_bib}")

    for reference in references:
        if not isinstance(reference, dict):
            warnings.append("references 中存在非对象条目，未写入 Reference.bib。")
            continue
        bibtex = str(reference.get("bibtex") or "").strip()
        if bibtex:
            entries.append(bibtex)
        elif reference.get("raw"):
            warnings.append(f"原始参考文献未转换为 BibTeX：{reference.get('raw')}")

    for block in source_blocks:
        if not isinstance(block, dict):
            warnings.append("source_blocks 中存在非对象条目，未写入 Reference.bib。")
            continue
        if block.get("target_slot") != "Reference.bib":
            continue
        if block.get("status") == "discarded_with_reason":
            continue
        bibtex = str(block.get("bibtex") or "").strip()
        if bibtex and block.get("status") in {"mapped", "rendered"}:
            entries.append(bibtex)
            blocks_to_render.append(block)
        elif bibtex:
            warnings.append(f"{block.get('id')} 有 BibTeX，但源块状态尚未确认映射。")
            blocks_needing_confirmation.append(block)
        else:
            warnings.append(f"{block.get('id')} 像参考文献，但没有已确认 BibTeX。")
            blocks_needing_confirmation.append(block)

    target = root / "Reference.bib"
    target_written = False
    if not entries:
        warnings.append("没有已确认 BibTeX 条目；为避免破坏现有数据，本轮未改写 Reference.bib。")
    if entries and not warnings:
        temporary = target.with_name(f".{target.name}.tmp")
        try:
            temporary.write_text("\n\n".join(entries).strip() + "\n", encoding="utf-8")
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
        target_written = True
        for block in blocks_to_render:
            block["status"] = "rendered"
            block["render_result"] = {"path": "Reference.bib", "kind": "bibtex"}
    else:
        for block in blocks_needing_confirmation:
            block["status"] = "needs_confirmation"

    if thesis_path.exists():
        thesis.setdefault("warnings", []).extend(warnings)
        thesis.setdefault("render_log", []).append(
            {
                "step": "render_bib",
                "status": "completed_with_warnings" if warnings else "completed",
                "target": rel(target, root),
                "rendered_at": now_iso(),
                "warnings": warnings,
            }
        )
        write_json(thesis_path, thesis)

    return {
        "flow": "B",
        "step": "render_bib",
        "status": "needs_confirmation" if warnings else "passed",
        "target": rel(target, root),
        "target_written": target_written,
        "warnings": warnings,
    }


def main() -> int:
    """解析命令行参数并执行 BibTeX 渲染。

    Returns:
        int: 无参考文献确认风险时返回 0，否则返回 2。
    """
    parser = argparse.ArgumentParser(
        description="在全部参考文献确认后，原子写入模板 Reference.bib。"
    )
    parser.add_argument("--root", default=".", help="ZUFE-Thesis 模板根目录。")
    parser.add_argument(
        "--thesis-json",
        default="workspace/intermediate/thesis.json",
        help="相对模板根目录的流程 B 账本路径。",
    )
    parser.add_argument(
        "--input-bib",
        default="workspace/input/references.bib",
        help="相对模板根目录的用户提供 BibTeX 输入路径。",
    )
    args = parser.parse_args()
    root = Path(args.root).expanduser().resolve()
    thesis_path = (
        (root / args.thesis_json).resolve()
        if not Path(args.thesis_json).is_absolute()
        else Path(args.thesis_json).resolve()
    )
    input_bib = (
        (root / args.input_bib).resolve()
        if not Path(args.input_bib).is_absolute()
        else Path(args.input_bib).resolve()
    )
    result = render(root, thesis_path, input_bib)
    print_json(result)
    return 0 if result["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
