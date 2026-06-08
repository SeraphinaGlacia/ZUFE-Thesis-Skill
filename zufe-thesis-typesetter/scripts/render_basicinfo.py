#!/usr/bin/env python3
"""把 metadata、摘要和关键词渲染到 chapters/basicinfo.tex。"""

from __future__ import annotations

import argparse
from pathlib import Path

from typing import Any

from common import (
    latex_escape,
    load_metadata_yaml,
    metadata_bool,
    metadata_value,
    now_iso,
    print_json,
    read_json,
    rel,
    safe_resolve_under,
    write_json,
)


def list_or_text(value: Any) -> str:
    """把 metadata 中的列表或标量统一转为模板字符串。

    Args:
        value (Any): 关键词列表、标量或空值。

    Returns:
        str: 使用中文分号连接后的文本。
    """
    if isinstance(value, list):
        return "；".join(str(item) for item in value)
    return "" if value is None else str(value)


def metadata_true(metadata: dict, key: str) -> bool:
    """读取 metadata 中的真值字段。

    Args:
        metadata (dict): metadata 字典。
        key (str): 字段名。

    Returns:
        bool: 字段按 metadata 布尔规则解析后的结果。
    """
    return metadata_bool(metadata, key, default=False)


def generated_english_requires_confirmation(thesis_meta: dict) -> bool:
    """判断英文摘要或关键词是否属于需授权的生成内容。

    Args:
        thesis_meta (dict): ``thesis.json`` 中的 metadata 字段。

    Returns:
        bool: 英文内容被标记为生成时返回 True。
    """
    source = str(thesis_meta.get("english_content_source") or "").strip().lower()
    if source == "generated":
        return True
    generated = thesis_meta.get("generated_content") or []
    if isinstance(generated, list) and any(
        str(item).startswith(("abstract_en", "keywords_en")) for item in generated
    ):
        return True
    return bool(
        thesis_meta.get("abstract_en_generated")
        or thesis_meta.get("keywords_en_generated")
    )


def has_content(value: Any) -> bool:
    """判断摘要或关键词字段是否包含实质内容。

    Args:
        value (Any): 字符串、列表或空值。

    Returns:
        bool: 存在非空文本时返回 True。
    """
    if isinstance(value, list):
        return any(str(item).strip() for item in value)
    return bool(str(value or "").strip())


def english_content_decision(metadata: dict, thesis_meta: dict) -> str:
    """读取用户对缺失英文摘要/关键词的处理选择。

    Args:
        metadata (dict): ``metadata.yaml`` 字段。
        thesis_meta (dict): ``thesis.json.metadata`` 字段。

    Returns:
        str: 小写后的选择值，例如 ``omit``、``manual`` 或 ``generate``。
    """
    value = metadata_value(metadata, "english_content_decision", default="")
    if not value:
        value = str(thesis_meta.get("english_content_decision") or "")
    return value.strip().lower()


def missing_english_fields(abstract_en: Any, keywords_en: Any) -> list[str]:
    """检查英文摘要和英文关键词是否缺失。

    Args:
        abstract_en (Any): 英文摘要字段。
        keywords_en (Any): 英文关键词字段。

    Returns:
        list[str]: 缺失字段名列表。
    """
    missing = []
    if not has_content(abstract_en):
        missing.append("abstract_en")
    if not has_content(keywords_en):
        missing.append("keywords_en")
    return missing


def validate_english_content_choice(
    metadata: dict,
    thesis_meta: dict,
    abstract_en: Any,
    keywords_en: Any,
) -> dict | None:
    """校验缺失英文摘要/关键词时是否已有明确用户选择。

    Args:
        metadata (dict): ``metadata.yaml`` 字段。
        thesis_meta (dict): ``thesis.json.metadata`` 字段。
        abstract_en (Any): 英文摘要字段。
        keywords_en (Any): 英文关键词字段。

    Returns:
        dict | None: 需要阻止渲染时返回门禁结果；通过时返回 None。
    """
    missing = missing_english_fields(abstract_en, keywords_en)
    if not missing:
        return None

    decision = english_content_decision(metadata, thesis_meta)
    allowed = {"omit", "manual", "generate"}
    if not decision:
        return {
            "flow": "B",
            "step": "render_basicinfo",
            "status": "blocked",
            "gate": "english_content_decision_required",
            "missing_fields": missing + ["english_content_decision"],
            "detail": "英文摘要或英文关键词缺失，必须先让用户选择留空、手动提供或允许生成。",
            "next_steps": [
                "询问用户：确认留空、手动提供英文摘要/关键词，或允许 Codex 生成。",
                "将选择记录为 english_content_decision=omit/manual/generate。",
            ],
        }
    if decision not in allowed:
        return {
            "flow": "B",
            "step": "render_basicinfo",
            "status": "blocked",
            "gate": "english_content_decision_invalid",
            "missing_fields": missing,
            "detail": "english_content_decision 只能是 omit、manual 或 generate。",
            "next_steps": ["重新确认英文摘要/关键词处理方式。"],
        }
    if decision == "omit":
        return None
    return {
        "flow": "B",
        "step": "render_basicinfo",
        "status": "blocked",
        "gate": "english_content_missing_after_decision",
        "missing_fields": missing,
        "detail": "用户选择了提供或生成英文内容，但渲染前仍缺少英文摘要或英文关键词。",
        "next_steps": [
            "先把确认后的英文摘要和英文关键词写入 thesis.json metadata。",
            "如果选择生成，还必须记录 allow_generated_english: true。",
        ],
    }


def render(root: Path, metadata_path: Path, thesis_path: Path | None) -> dict:
    """把已确认 metadata 和摘要关键词渲染到 basicinfo.tex。

    Args:
        root (Path): ZUFE-Thesis 模板根目录。
        metadata_path (Path): ``workspace/input/metadata.yaml`` 路径。
        thesis_path (Path | None): ``workspace/intermediate/thesis.json`` 路径。

    Returns:
        dict: 渲染结果；缺关键确认信息时返回 blocked。
    """
    metadata = load_metadata_yaml(metadata_path)
    thesis = (
        read_json(thesis_path, default={})
        if thesis_path and thesis_path.exists()
        else {}
    )
    thesis_meta = thesis.get("metadata", {})
    abstracts = thesis_meta.get("abstracts", {})
    keywords = thesis_meta.get("keywords", {})

    report_style = metadata_value(metadata, "report_style", default="").strip()
    if report_style not in {"0", "1"}:
        return {
            "flow": "B",
            "step": "render_basicinfo",
            "status": "blocked",
            "gate": "metadata_required",
            "missing_fields": ["report_style"],
            "detail": "报告类型不能默认推断；必须由 Word 证据或用户确认 report_style=0/1。",
            "next_steps": ["先回到流程 A 确认报告类型，再渲染 basicinfo.tex。"],
        }
    if generated_english_requires_confirmation(thesis_meta) and not metadata_true(
        metadata,
        "allow_generated_english",
    ):
        return {
            "flow": "B",
            "step": "render_basicinfo",
            "status": "blocked",
            "gate": "generated_english_requires_confirmation",
            "detail": "英文摘要或英文关键词被标记为生成内容，但 metadata.yaml 未允许自动生成。",
            "next_steps": ["向用户说明英文摘要/关键词属于内容性补写，并确认是否允许自动生成。"],
        }
    has_subtitle = metadata_bool(metadata, "has_subtitle", default=False)
    title_cn = metadata_value(metadata, "thesis_title_cn", "title_cn", "title", default="")
    title_abs_cn = metadata_value(
        metadata,
        "thesis_title_abs_cn",
        "title_abs_cn",
        "thesisTitleAbs",
        default="",
    )
    title_en = metadata_value(metadata, "thesis_title_en", "title_en", default="")
    subtitle_cn = metadata_value(metadata, "thesis_subtitle_cn", "subtitle_cn", default="")
    subtitle_en = metadata_value(metadata, "thesis_subtitle_en", "subtitle_en", default="")
    abstract_cn = (
        thesis_meta.get("abstract_cn") or abstracts.get("cn") or abstracts.get("zh") or ""
    )
    abstract_en = thesis_meta.get("abstract_en") or abstracts.get("en") or ""
    keywords_cn = thesis_meta.get("keywords_cn") or keywords.get("cn") or keywords.get("zh") or ""
    keywords_en = thesis_meta.get("keywords_en") or keywords.get("en") or ""
    english_choice_result = validate_english_content_choice(
        metadata,
        thesis_meta,
        abstract_en,
        keywords_en,
    )
    if english_choice_result:
        return english_choice_result

    lines = [
        "% Generated by zufe-thesis-typesetter. Edit metadata.yaml/thesis.json, then rerender.",
        "% 基本信息",
        r"\hypersetup{hidelinks,pdfborder={0 0 0},pdfborderstyle={/S/U/W 0}}",
        "",
        f"\\newcommand{{\\reportStyle}}{{{latex_escape(report_style)}}}",
        "",
        f"\\newcommand{{\\thesisTitle}}{{{latex_escape(title_cn)}}}",
        *(
            [f"\\newcommand{{\\thesisTitleAbs}}{{{latex_escape(title_abs_cn)}}}"]
            if title_abs_cn
            else []
        ),
        f"\\newcommand{{\\thesisTitleEN}}{{{latex_escape(title_en)}}}",
        "",
        "\\haveSub{}" if has_subtitle else "% \\haveSub{}",
        f"\\newcommand{{\\thesisSubTitle}}{{{latex_escape(subtitle_cn)}}}",
        f"\\newcommand{{\\thesisSubTitleEN}}{{{latex_escape(subtitle_en)}}}",
        "",
        "\\newcommand{\\deptName}{"
        f"{latex_escape(metadata_value(metadata, 'college', 'deptName', default=''))}"
        "}",
        "\\newcommand{\\majorName}{"
        f"{latex_escape(metadata_value(metadata, 'major', 'majorName', default=''))}"
        "}",
        "\\newcommand{\\yourName}{"
        f"{latex_escape(metadata_value(metadata, 'name', 'yourName', default=''))}"
        "}",
        "\\newcommand{\\yourStudentID}{"
        f"{latex_escape(metadata_value(metadata, 'student_id', 'studentID', default=''))}"
        "}",
        "\\newcommand{\\mentorName}{"
        f"{latex_escape(metadata_value(metadata, 'mentor', 'mentorName', default=''))}"
        "}",
        "\\newcommand{\\className}{"
        f"{latex_escape(metadata_value(metadata, 'class_name', 'className', default=''))}"
        "}",
        "\\newcommand{\\Today}{"
        f"{latex_escape(metadata_value(metadata, 'date', 'today', default=''))}"
        "}",
        "",
        "% 中英文摘要与关键词",
        f"\\newcommand{{\\abstractCN}}{{{latex_escape(abstract_cn)}}}",
        "",
        f"\\newcommand{{\\keywordsCN}}{{{latex_escape(list_or_text(keywords_cn))}}}",
        "",
        f"\\newcommand{{\\abstractEN}}{{{latex_escape(abstract_en)}}}",
        "",
        f"\\newcommand{{\\keywordsEN}}{{{latex_escape(list_or_text(keywords_en))}}}",
        "",
    ]
    target = safe_resolve_under(root, "chapters/basicinfo.tex", "chapters")
    target.write_text("\n".join(lines), encoding="utf-8")

    if thesis_path and thesis_path.exists():
        thesis.setdefault("render_log", []).append(
            {
                "step": "render_basicinfo",
                "status": "completed",
                "target": rel(target, root),
                "rendered_at": now_iso(),
            }
        )
        for block in thesis.get("source_blocks", []):
            if (
                block.get("target_slot") == "chapters/basicinfo.tex"
                and block.get("status") == "mapped"
            ):
                block["status"] = "rendered"
                block["render_result"] = {
                    "path": "chapters/basicinfo.tex",
                    "kind": "latex_macro",
                }
        write_json(thesis_path, thesis)

    return {
        "flow": "B",
        "step": "render_basicinfo",
        "status": "passed",
        "target": rel(target, root),
    }


def main() -> int:
    """解析命令行参数并执行 basicinfo 渲染。

    Returns:
        int: 渲染通过时返回 0，否则返回 2。
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--metadata", default="workspace/input/metadata.yaml")
    parser.add_argument("--thesis-json", default="workspace/intermediate/thesis.json")
    args = parser.parse_args()
    root = Path(args.root).expanduser().resolve()
    metadata_path = (
        (root / args.metadata).resolve()
        if not Path(args.metadata).is_absolute()
        else Path(args.metadata).resolve()
    )
    thesis_path = (
        (root / args.thesis_json).resolve()
        if not Path(args.thesis_json).is_absolute()
        else Path(args.thesis_json).resolve()
    )
    result = render(root, metadata_path, thesis_path)
    print_json(result)
    return 0 if result["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
