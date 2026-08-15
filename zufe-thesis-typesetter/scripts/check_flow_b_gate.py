#!/usr/bin/env python3
"""检查流程 B 是否可以把工程交给流程 C。"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path, PurePosixPath

from common import (
    FINAL_BLOCK_STATES,
    active_chapter_files,
    file_fingerprint,
    latex_label_reference_issues,
    manual_cross_reference_hits,
    print_json,
    read_json,
    safe_resolve_under,
)

ACCEPTED_UNSUPPORTED_FEATURE_STATUSES = {"accepted_with_warning", "confirmed", "resolved"}
ALLOWED_BLOCK_STATES = FINAL_BLOCK_STATES | {"blocked", "mapped", "needs_confirmation"}
RESERVED_CHAPTER_FILES = {"chapters/basicinfo.tex", "chapters/mainbody.tex"}


def valid_chapter_file(value: str) -> bool:
    """判断章节文件是否是 chapters 下的安全 TeX 相对路径。

    Args:
        value (str): 账本中的章节文件路径。

    Returns:
        bool: 路径安全且不是模板保留文件时返回 True。
    """
    if "\\" in value:
        return False
    path = PurePosixPath(value)
    return (
        not path.is_absolute()
        and len(path.parts) >= 2
        and path.parts[0] == "chapters"
        and ".." not in path.parts
        and path.suffix == ".tex"
        and value not in RESERVED_CHAPTER_FILES
    )


def ledger_schema_issues(thesis: dict) -> list[dict]:
    """校验动态 thesis.json 中最关键的运行时契约。

    Args:
        thesis (dict): ``thesis.json`` 顶层对象。

    Returns:
        list[dict]: 会阻止流程 B 完成的契约问题。
    """
    issues = []
    blocks = thesis.get("source_blocks", [])
    if not isinstance(blocks, list):
        return [{"check": "source_blocks_type", "detail": "source_blocks 必须是列表。"}]

    block_by_id = {}
    source_type_counts = {"paragraph": 0, "table": 0, "image": 0}
    for index, block in enumerate(blocks):
        if not isinstance(block, dict):
            issues.append(
                {
                    "check": "source_block_type",
                    "block_index": index,
                    "detail": "源块必须是 JSON 对象。",
                }
            )
            continue
        block_id = block.get("id")
        if not isinstance(block_id, str) or not block_id.strip():
            issues.append(
                {
                    "check": "source_block_id",
                    "block_index": index,
                    "detail": "源块缺少非空字符串 ID。",
                }
            )
        elif block_id in block_by_id:
            issues.append(
                {
                    "check": "duplicate_source_block_id",
                    "block_id": block_id,
                    "detail": "源块 ID 重复。",
                }
            )
        else:
            block_by_id[block_id] = block

        status = block.get("status")
        if not isinstance(status, str) or status not in ALLOWED_BLOCK_STATES:
            issues.append(
                {
                    "check": "source_block_status_value",
                    "block_id": block_id,
                    "detail": f"未知源块状态：{status}。",
                }
            )
        source_type = block.get("source_type")
        if isinstance(source_type, str) and source_type in source_type_counts:
            source_type_counts[source_type] += 1

    counts = thesis.get("counts", {})
    if not isinstance(counts, dict):
        issues.append({"check": "counts_type", "detail": "counts 必须是 JSON 对象。"})
    else:
        expected_by_type = counts.get("source_blocks_by_type")
        if expected_by_type is not None and not isinstance(expected_by_type, dict):
            issues.append(
                {
                    "check": "source_blocks_by_type",
                    "detail": "counts.source_blocks_by_type 必须是 JSON 对象。",
                }
            )
        elif isinstance(expected_by_type, dict):
            for source_type, actual_count in source_type_counts.items():
                if expected_by_type.get(source_type) == actual_count:
                    continue
                issues.append(
                    {
                        "check": "source_type_count",
                        "source_type": source_type,
                        "detail": (
                            f"counts.source_blocks_by_type.{source_type}="
                            f"{expected_by_type.get(source_type)}，实际为 {actual_count}。"
                        ),
                    }
                )

    unsupported = thesis.get("unsupported_features", [])
    if not isinstance(unsupported, list):
        issues.append(
            {"check": "unsupported_features_type", "detail": "unsupported_features 必须是列表。"}
        )

    structure = thesis.get("structure", {})
    if not isinstance(structure, dict):
        issues.append({"check": "structure_type", "detail": "structure 必须是 JSON 对象。"})
        return issues
    chapters = structure.get("chapters", [])
    if not isinstance(chapters, list):
        issues.append({"check": "chapters_type", "detail": "structure.chapters 必须是列表。"})
        return issues

    referenced_by = {}
    chapter_files = {}
    for index, chapter in enumerate(chapters):
        if not isinstance(chapter, dict):
            issues.append(
                {
                    "check": "chapter_type",
                    "chapter_index": index,
                    "detail": "章节条目必须是 JSON 对象。",
                }
            )
            continue
        chapter_file = chapter.get("file")
        if not isinstance(chapter_file, str) or not valid_chapter_file(chapter_file):
            issues.append(
                {
                    "check": "chapter_file",
                    "chapter_index": index,
                    "target": chapter_file,
                    "detail": "章节文件必须是 chapters 下的安全 .tex 路径，且不能使用模板保留文件。",
                }
            )
        else:
            normalized_file = PurePosixPath(chapter_file).as_posix()
            chapter_file_key = normalized_file.casefold()
            if chapter_file_key in chapter_files:
                issues.append(
                    {
                        "check": "duplicate_chapter_file",
                        "chapter_index": index,
                        "target": normalized_file,
                        "detail": (
                            f"章节文件与第 {chapter_files[chapter_file_key]} 个章节重复，"
                            "渲染时会覆盖先前正文。"
                        ),
                    }
                )
            else:
                chapter_files[chapter_file_key] = index + 1
        block_ids = chapter.get("block_ids", [])
        if not isinstance(block_ids, list):
            issues.append(
                {
                    "check": "chapter_block_ids_type",
                    "chapter_index": index,
                    "detail": "chapter.block_ids 必须是列表。",
                }
            )
            continue
        for block_id in block_ids:
            if not isinstance(block_id, str) or block_id not in block_by_id:
                issues.append(
                    {
                        "check": "chapter_unknown_block",
                        "chapter_index": index,
                        "block_id": block_id,
                        "detail": "章节引用了不存在的源块。",
                    }
                )
                continue
            if block_id in referenced_by:
                issues.append(
                    {
                        "check": "chapter_duplicate_block_reference",
                        "block_id": block_id,
                        "detail": (
                            f"同一源块同时出现在 {referenced_by[block_id]} 和 {chapter_file}。"
                        ),
                    }
                )
            else:
                referenced_by[block_id] = chapter_file
            target_slot = block_by_id[block_id].get("target_slot")
            if isinstance(chapter_file, str) and target_slot != chapter_file:
                issues.append(
                    {
                        "check": "chapter_target_mismatch",
                        "block_id": block_id,
                        "detail": f"源块 target_slot={target_slot}，章节文件={chapter_file}。",
                    }
                )
    return issues


def source_docx_integrity_issues(root: Path, thesis: dict) -> tuple[list[dict], dict | None]:
    """核对当前源 DOCX 与正式抽取时记录的指纹。

    Args:
        root (Path): ZUFE-Thesis 模板根目录。
        thesis (dict): ``thesis.json`` 顶层对象。

    Returns:
        tuple[list[dict], dict | None]: 完整性问题和当前文件指纹。
    """
    issues = []
    source_docx = thesis.get("source_docx")
    expected = thesis.get("source_docx_fingerprint")
    if not isinstance(source_docx, str) or not source_docx.strip():
        issues.append(
            {"check": "source_docx_path", "detail": "source_docx 必须是标准输入目录下的相对路径。"}
        )
        return issues, None
    try:
        source_path = safe_resolve_under(root, source_docx, "workspace/input")
    except ValueError:
        issues.append(
            {
                "check": "source_docx_path",
                "target": source_docx,
                "detail": "source_docx 必须位于 workspace/input 下。",
            }
        )
        return issues, None
    if not source_path.exists() or not source_path.is_file():
        issues.append(
            {
                "check": "source_docx_exists",
                "target": source_docx,
                "detail": "生成 thesis.json 的源 DOCX 不存在。",
            }
        )
        return issues, None
    actual = file_fingerprint(source_path)
    if not isinstance(expected, dict):
        issues.append(
            {
                "check": "source_docx_fingerprint",
                "detail": "source_docx_fingerprint 缺失或结构无效，必须重新正式抽取。",
            }
        )
    elif expected != actual:
        issues.append(
            {
                "check": "source_docx_changed",
                "expected_fingerprint": expected,
                "actual_fingerprint": actual,
                "detail": "源 DOCX 已在正式抽取后发生变化，当前账本不能继续使用。",
            }
        )
    return issues, actual


def rendered_source_text(root: Path, thesis: dict) -> str:
    """读取所有章节源码用于流程 B 完成门禁反查。

    Args:
        root (Path): ZUFE-Thesis 模板根目录。
        thesis (dict): 当前 ``thesis.json`` 对象。

    Returns:
        str: 拼接后的本轮章节 TeX 源码文本。
    """
    return "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for path in active_chapter_files(root, thesis)
    )


def count_runs_with_flag(blocks: list[dict], flag: str) -> int:
    """统计已渲染源块中带指定 run 标记的数量。

    Args:
        blocks (list[dict]): ``thesis.json`` 中的源块列表。
        flag (str): run 级布尔标记，例如 ``superscript``。

    Returns:
        int: 带该标记的 run 数量。
    """
    count = 0
    for block in blocks:
        if not isinstance(block, dict) or block.get("status") != "rendered":
            continue
        runs = block.get("runs", [])
        if not isinstance(runs, list):
            continue
        count += sum(1 for run in runs if isinstance(run, dict) and run.get(flag))
    return count


def count_latex_command(source_text: str, command: str) -> int:
    """统计章节源码中某个 LaTeX 命令的出现次数。

    Args:
        source_text (str): 章节源码文本。
        command (str): 不含反斜杠的 LaTeX 命令名。

    Returns:
        int: 命令出现次数。
    """
    return len(re.findall(rf"\\{command}\s*\{{", source_text))


def check(root: Path, thesis_path: Path) -> dict:
    """检查流程 B 是否满足进入流程 C 的完成门禁。

    Args:
        root (Path): ZUFE-Thesis 模板根目录。
        thesis_path (Path): ``workspace/intermediate/thesis.json`` 路径。

    Returns:
        dict: 流程 B 完成门禁结果和阻塞问题列表。
    """
    if not thesis_path.exists():
        return {
            "flow": "B",
            "gate": "completion",
            "status": "blocked",
            "issues": [{"check": "thesis_json_missing", "detail": "thesis.json 不存在。"}],
            "next_steps": ["先运行 import_docx.py 生成正式清点账本。"],
        }
    try:
        thesis = read_json(thesis_path)
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "flow": "B",
            "gate": "completion",
            "status": "blocked",
            "issues": [{"check": "thesis_json_invalid", "detail": str(exc)}],
            "next_steps": ["修复或重新生成 thesis.json 后再运行流程 B 门禁。"],
        }
    thesis_fingerprint = file_fingerprint(thesis_path)
    if not isinstance(thesis, dict):
        return {
            "flow": "B",
            "gate": "completion",
            "status": "blocked",
            "issues": [
                {"check": "thesis_json_type", "detail": "thesis.json 顶层必须是 JSON 对象。"}
            ],
            "next_steps": ["修复 thesis.json 结构后重新运行流程 B 门禁。"],
        }
    raw_blocks = thesis.get("source_blocks", [])
    blocks = raw_blocks if isinstance(raw_blocks, list) else []
    issues = ledger_schema_issues(thesis)
    source_integrity_issues, source_docx_fingerprint = source_docx_integrity_issues(root, thesis)
    issues.extend(source_integrity_issues)

    counts = thesis.get("counts", {})
    expected = counts.get("total_source_blocks") if isinstance(counts, dict) else None
    if expected != len(blocks):
        issues.append(
            {
                "check": "source_block_count",
                "detail": f"账本记录 {expected} 个源块，实际找到 {len(blocks)} 个。",
            }
        )

    unsupported_features = thesis.get("unsupported_features", [])
    for feature in unsupported_features if isinstance(unsupported_features, list) else []:
        if not isinstance(feature, dict):
            issues.append(
                {
                    "check": "unsupported_feature_type",
                    "detail": "unsupported feature 条目必须是 JSON 对象。",
                }
            )
            continue
        if not feature.get("count"):
            continue
        status = feature.get("status", "needs_confirmation")
        if not isinstance(status, str) or status not in ACCEPTED_UNSUPPORTED_FEATURE_STATUSES:
            issues.append(
                {
                    "check": "unsupported_feature_confirmation",
                    "feature_type": feature.get("type"),
                    "detail": f"{feature.get('type')} 检测到 {feature.get('count')} 处，状态仍是 {status}。",
                }
            )

    for block in blocks:
        if not isinstance(block, dict):
            continue
        block_id = block.get("id")
        status = block.get("status")
        text = str(block.get("text") or "").strip()
        source_type = block.get("source_type")
        is_noise = status == "discarded_with_reason"
        if not isinstance(status, str) or status not in FINAL_BLOCK_STATES:
            issues.append(
                {
                    "check": "source_block_state",
                    "block_id": block_id,
                    "detail": f"状态仍是 {status}。",
                }
            )
        if status == "discarded_with_reason" and not block.get("discard_reason"):
            issues.append(
                {
                    "check": "discard_reason",
                    "block_id": block_id,
                    "detail": "丢弃源块没有记录原因。",
                }
            )
        render_result = block.get("render_result")
        if status == "rendered" and not isinstance(render_result, dict):
            issues.append(
                {
                    "check": "render_result",
                    "block_id": block_id,
                    "detail": "已渲染源块的 render_result 必须是 JSON 对象。",
                }
            )
        if status == "rendered" and isinstance(render_result, dict):
            rendered_path = render_result.get("path")
            if not isinstance(rendered_path, str) or not rendered_path:
                issues.append(
                    {
                        "check": "render_result_path",
                        "block_id": block_id,
                        "detail": "已渲染源块的 render_result.path 无效。",
                    }
                )
            else:
                candidate = (root / rendered_path).resolve()
                try:
                    candidate.relative_to(root.resolve())
                except ValueError:
                    issues.append(
                        {
                            "check": "render_result_path_escape",
                            "block_id": block_id,
                            "detail": "render_result.path 逃逸出模板根目录。",
                        }
                    )
                else:
                    if not candidate.exists():
                        issues.append(
                            {
                                "check": "rendered_target_exists",
                                "block_id": block_id,
                                "target": rendered_path,
                                "detail": "render_result 指向的实际文件不存在。",
                            }
                        )
                    target_slot = block.get("target_slot")
                    if target_slot and target_slot != rendered_path:
                        issues.append(
                            {
                                "check": "render_result_target_mismatch",
                                "block_id": block_id,
                                "detail": (
                                    f"target_slot={target_slot}，"
                                    f"render_result.path={rendered_path}。"
                                ),
                            }
                        )
        if (
            not is_noise
            and (text or (isinstance(source_type, str) and source_type in {"table", "image"}))
            and not (block.get("target_slot") or block.get("discard_reason"))
        ):
            issues.append(
                {
                    "check": "target_slot",
                    "block_id": block_id,
                    "detail": "非噪声源块没有目标槽位或丢弃原因。",
                }
            )

    required_targets = [
        "chapters/basicinfo.tex",
        "chapters/mainbody.tex",
        "Reference.bib",
    ]
    for target in required_targets:
        if not (root / target).exists():
            issues.append(
                {
                    "check": "target_exists",
                    "target": target,
                    "detail": "必需目标文件不存在。",
                }
            )

    mainbody = root / "chapters/mainbody.tex"
    if mainbody.exists() and "\\input{chapters/" not in mainbody.read_text(
        encoding="utf-8",
        errors="ignore",
    ):
        issues.append(
            {
                "check": "chapter_order",
                "target": "chapters/mainbody.tex",
                "detail": "没有检测到章节 input。",
            }
        )

    source_text = rendered_source_text(root, thesis)
    superscript_runs = count_runs_with_flag(blocks, "superscript")
    rendered_superscripts = count_latex_command(source_text, "textsuperscript")
    if rendered_superscripts < superscript_runs:
        issues.append(
            {
                "check": "superscript_rendering",
                "detail": (
                    f"{superscript_runs} 个已渲染 Word 上标 run，"
                    f"但章节源码只检测到 {rendered_superscripts} 个 \\textsuperscript。"
                ),
            }
        )
    subscript_runs = count_runs_with_flag(blocks, "subscript")
    rendered_subscripts = count_latex_command(source_text, "textsubscript")
    if rendered_subscripts < subscript_runs:
        issues.append(
            {
                "check": "subscript_rendering",
                "detail": (
                    f"{subscript_runs} 个已渲染 Word 下标 run，"
                    f"但章节源码只检测到 {rendered_subscripts} 个 \\textsubscript。"
                ),
            }
        )
    if re.search(r"\\resizebox\s*\{\s*\\textwidth\s*\}\s*\{\s*!\s*\}", source_text):
        issues.append(
            {
                "check": "table_resizebox_textwidth",
                "detail": "章节源码包含无条件 \\resizebox{\\textwidth}{!}，可能放大窄表并破坏字号。",
            }
        )
    manual_reference_hits = manual_cross_reference_hits(source_text)
    if manual_reference_hits:
        issues.append(
            {
                "check": "manual_cross_reference_numbers",
                "detail": ("章节源码仍包含手写图表编号；应由 Agent 确认映射后改写为 \\ref 引用。"),
                "examples": manual_reference_hits,
            }
        )
    label_reference_issues = latex_label_reference_issues(source_text)
    if label_reference_issues["duplicate_labels"]:
        issues.append(
            {
                "check": "duplicate_latex_labels",
                "detail": "章节源码包含重复 label，会导致引用跳转不稳定。",
                "labels": label_reference_issues["duplicate_labels"],
            }
        )
    if label_reference_issues["undefined_refs"]:
        issues.append(
            {
                "check": "undefined_latex_refs",
                "detail": "章节源码包含没有对应 label 的 \\ref。",
                "labels": label_reference_issues["undefined_refs"],
            }
        )

    status = "passed" if not issues else "blocked"
    return {
        "flow": "B",
        "gate": "completion",
        "status": status,
        "thesis_json_fingerprint": thesis_fingerprint,
        "source_docx_fingerprint": source_docx_fingerprint,
        "issues": issues,
        "next_steps": []
        if status == "passed"
        else [
            "解决所有问题后才能启动流程 C。",
            "需要用户确认的映射或丢弃决定必须先在对话中完成。",
        ],
    }


def main() -> int:
    """解析命令行参数并输出流程 B 完成门禁结果。

    Returns:
        int: 门禁通过时返回 0，否则返回 2。
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--thesis-json", default="workspace/intermediate/thesis.json")
    args = parser.parse_args()
    root = Path(args.root).expanduser().resolve()
    thesis_path = (
        (root / args.thesis_json).resolve()
        if not Path(args.thesis_json).is_absolute()
        else Path(args.thesis_json).resolve()
    )
    result = check(root, thesis_path)
    print_json(result)
    return 0 if result["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
