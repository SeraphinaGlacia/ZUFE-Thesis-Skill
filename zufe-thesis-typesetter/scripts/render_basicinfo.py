#!/usr/bin/env python3
"""把 metadata、摘要和关键词渲染到 chapters/basicinfo.tex。"""

from __future__ import annotations

import argparse
import re
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
        thesis_meta.get("abstract_en_generated") or thesis_meta.get("keywords_en_generated")
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


REQUIRED_METADATA_FIELDS = [
    ("thesis_title_cn", ("thesis_title_cn", "title_cn", "title")),
    ("thesis_title_en", ("thesis_title_en", "title_en")),
    ("college", ("college", "deptName")),
    ("major", ("major", "majorName")),
    ("name", ("name", "yourName")),
    ("student_id", ("student_id", "studentID")),
    ("mentor", ("mentor", "mentorName")),
    ("class_name", ("class_name", "className")),
    ("date", ("date", "today")),
]

BASICINFO_METADATA_FIELDS = {
    "report_style",
    "thesis_title_cn",
    "thesis_title_abs_cn",
    "thesis_title_en",
    "thesis_subtitle_cn",
    "thesis_subtitle_en",
    "college",
    "major",
    "name",
    "student_id",
    "mentor",
    "class_name",
    "date",
    "abstract_cn",
    "abstract_en",
    "keywords_cn",
    "keywords_en",
}
REPORT_STYLE_EVIDENCE = {
    "1": ["专业实践报告", "专业实践", "实践报告", "专业实习"],
    "0": ["本科毕业论文", "毕业论文", "学位论文", "本科论文"],
}
BASICINFO_FIELD_LABELS = {
    "report_style": ["报告类型", "论文类型"],
    "thesis_title_cn": ["题目", "论文题目", "报告题目", "中文题目"],
    "thesis_title_abs_cn": ["摘要页题目"],
    "thesis_title_en": ["英文题目", "English Title"],
    "thesis_subtitle_cn": ["副标题", "中文副标题"],
    "thesis_subtitle_en": ["英文副标题", "English Subtitle"],
    "college": ["学院", "学院名称"],
    "major": ["专业", "专业名称"],
    "name": ["姓名", "学生姓名", "作者"],
    "student_id": ["学号", "学生学号"],
    "mentor": ["导师", "指导教师", "指导老师"],
    "class_name": ["班级", "班级名称"],
    "date": ["日期", "完成日期"],
    "abstract_cn": ["摘要", "中文摘要"],
    "abstract_en": ["Abstract", "英文摘要"],
    "keywords_cn": ["关键词", "中文关键词"],
    "keywords_en": ["Keywords", "Key words", "英文关键词"],
}


def normalized_evidence(value: Any) -> str:
    """规范化源块证据，忽略 Word 中无意义的空白差异。

    Args:
        value (Any): 待规范化的文本值。

    Returns:
        str: 去除空白并统一大小写后的文本。
    """
    return re.sub(r"\s+", "", str(value or "")).casefold()


def source_block_evidence(block: dict) -> str:
    """汇总段落或表格源块中的可见文本证据。

    Args:
        block (dict): ``thesis.json`` 源块。

    Returns:
        str: 可用于字段值核对的规范化文本。
    """
    parts = [str(block.get("text") or "")]
    table = block.get("table")
    if isinstance(table, dict):
        for row in table.get("rows", []):
            if isinstance(row, list):
                parts.extend(str(cell or "") for cell in row)
    return normalized_evidence("\n".join(parts))


def metadata_field_fragments(field: str, value: Any) -> list[str]:
    """生成必须能在源块中找到的字段证据片段。

    Args:
        field (str): basicinfo 规范字段名。
        value (Any): 实际写入 LaTeX 的字段值。

    Returns:
        list[str]: 需要逐项匹配的非空文本片段。
    """
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    text = str(value or "").strip()
    return [text] if text else []


def block_metadata_fields(block: dict) -> list[str]:
    """读取源块声明的 basicinfo 字段绑定。

    Args:
        block (dict): ``thesis.json`` 源块。

    Returns:
        list[str]: 去重后的规范字段名列表。
    """
    raw_fields = block.get("metadata_fields")
    if raw_fields is None and block.get("metadata_field"):
        raw_fields = [block["metadata_field"]]
    if isinstance(raw_fields, str):
        raw_fields = [raw_fields]
    if not isinstance(raw_fields, list):
        return []
    return list(
        dict.fromkeys(
            str(field).strip() for field in raw_fields if field is not None and str(field).strip()
        )
    )


def block_text_list(block: dict, key: str) -> list[str]:
    """读取源块中显式声明的文本片段列表。

    Args:
        block (dict): ``thesis.json`` 源块。
        key (str): 字符串或字符串列表字段名。

    Returns:
        list[str]: 去除空项后的文本片段。
    """
    values = block.get(key, [])
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, list):
        return []
    return [str(value).strip() for value in values if str(value).strip()]


def verify_basicinfo_block(
    block: dict, field_values: dict[str, Any]
) -> tuple[list[str], list[str]]:
    """验证源块内容确实由声明的 metadata 字段承接。

    Args:
        block (dict): 待验证的源块。
        field_values (dict[str, Any]): 本轮实际渲染的规范字段值。

    Returns:
        tuple[list[str], list[str]]: 已验证字段和未通过原因。
    """
    fields = block_metadata_fields(block)
    if not fields:
        return [], ["missing_metadata_fields"]

    evidence = source_block_evidence(block)
    verified = []
    problems = []
    for field in fields:
        if field not in BASICINFO_METADATA_FIELDS:
            problems.append(f"unknown_field:{field}")
            continue
        if field == "report_style":
            report_style_options = REPORT_STYLE_EVIDENCE.get(str(field_values.get(field)), [])
            if any(normalized_evidence(option) in evidence for option in report_style_options):
                verified.append(field)
            else:
                problems.append("source_value_mismatch:report_style")
            continue
        fragments = metadata_field_fragments(field, field_values.get(field))
        if not fragments:
            problems.append(f"empty_rendered_value:{field}")
            continue
        missing = [
            fragment for fragment in fragments if normalized_evidence(fragment) not in evidence
        ]
        if missing:
            problems.append(f"source_value_mismatch:{field}")
            continue
        verified.append(field)

    covered_fragments = []
    for field in verified:
        covered_fragments.extend(BASICINFO_FIELD_LABELS.get(field, []))
        if field == "report_style":
            covered_fragments.extend(REPORT_STYLE_EVIDENCE.get(str(field_values.get(field)), []))
        else:
            covered_fragments.extend(metadata_field_fragments(field, field_values.get(field)))

    remaining = evidence
    for fragment in sorted(
        covered_fragments, key=lambda value: len(normalized_evidence(value)), reverse=True
    ):
        remaining = remaining.replace(normalized_evidence(fragment), "")

    excluded_fragments = block_text_list(block, "metadata_excluded_text")
    if excluded_fragments and not str(block.get("metadata_exclusion_reason") or "").strip():
        problems.append("missing_metadata_exclusion_reason")
    for fragment in excluded_fragments:
        normalized_fragment = normalized_evidence(fragment)
        if normalized_fragment not in remaining:
            problems.append("metadata_excluded_text_mismatch")
            continue
        remaining = remaining.replace(normalized_fragment, "")

    remaining = re.sub(r"[\s:：,，;；。.!！?？/|\\()（）\[\]【】{}<>《》_-]+", "", remaining)
    if remaining:
        problems.append(f"uncovered_source_text:{remaining[:40]}")
    return verified, problems


def required_metadata_missing(metadata: dict) -> list[str]:
    """检查封面和身份字段是否已由流程 A 确认。

    Args:
        metadata (dict): ``metadata.yaml`` 字段。

    Returns:
        list[str]: 缺失或无效的必填字段名。
    """
    missing = []
    report_style = metadata_value(metadata, "report_style", default="").strip()
    if report_style not in {"0", "1"}:
        missing.append("report_style")

    for field, aliases in REQUIRED_METADATA_FIELDS:
        if not metadata_value(metadata, *aliases, default="").strip():
            missing.append(field)

    if metadata_bool(metadata, "has_subtitle", default=False):
        subtitle_cn = metadata_value(
            metadata,
            "thesis_subtitle_cn",
            "subtitle_cn",
            default="",
        ).strip()
        subtitle_en = metadata_value(
            metadata,
            "thesis_subtitle_en",
            "subtitle_en",
            default="",
        ).strip()
        if not subtitle_cn:
            missing.append("thesis_subtitle_cn")
        if not subtitle_en:
            missing.append("thesis_subtitle_en")

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
                "询问用户：确认留空、手动提供英文摘要/关键词，或允许 Agent 生成。",
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
    thesis = read_json(thesis_path, default={}) if thesis_path and thesis_path.exists() else {}
    if not isinstance(thesis, dict):
        return {
            "flow": "B",
            "step": "render_basicinfo",
            "status": "blocked",
            "gate": "thesis_json_structure",
            "detail": "thesis.json 顶层必须是 JSON 对象。",
            "next_steps": ["修复或重新生成 thesis.json 后再渲染。"],
        }
    thesis_meta = thesis.get("metadata", {})
    source_blocks = thesis.get("source_blocks", [])
    if not isinstance(thesis_meta, dict) or not isinstance(source_blocks, list):
        return {
            "flow": "B",
            "step": "render_basicinfo",
            "status": "blocked",
            "gate": "thesis_json_structure",
            "detail": "thesis.json.metadata 必须是对象，source_blocks 必须是列表。",
            "next_steps": ["修复或重新生成 thesis.json 后再渲染。"],
        }
    abstracts = thesis_meta.get("abstracts", {})
    keywords = thesis_meta.get("keywords", {})
    abstracts = abstracts if isinstance(abstracts, dict) else {}
    keywords = keywords if isinstance(keywords, dict) else {}

    missing_metadata = required_metadata_missing(metadata)
    if missing_metadata:
        return {
            "flow": "B",
            "step": "render_basicinfo",
            "status": "blocked",
            "gate": "metadata_required",
            "missing_fields": missing_metadata,
            "detail": "封面和身份字段必须由 Word 证据或用户确认，不能写入空宏。",
            "next_steps": ["先回到流程 A 确认缺失 metadata，再渲染 basicinfo.tex。"],
        }
    report_style = metadata_value(metadata, "report_style", default="").strip()
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
    abstract_cn = thesis_meta.get("abstract_cn") or abstracts.get("cn") or abstracts.get("zh") or ""
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

    field_values = {
        "report_style": report_style,
        "thesis_title_cn": title_cn,
        "thesis_title_abs_cn": title_abs_cn,
        "thesis_title_en": title_en,
        "thesis_subtitle_cn": subtitle_cn,
        "thesis_subtitle_en": subtitle_en,
        "college": metadata_value(metadata, "college", "deptName", default=""),
        "major": metadata_value(metadata, "major", "majorName", default=""),
        "name": metadata_value(metadata, "name", "yourName", default=""),
        "student_id": metadata_value(metadata, "student_id", "studentID", default=""),
        "mentor": metadata_value(metadata, "mentor", "mentorName", default=""),
        "class_name": metadata_value(metadata, "class_name", "className", default=""),
        "date": metadata_value(metadata, "date", "today", default=""),
        "abstract_cn": abstract_cn,
        "abstract_en": abstract_en,
        "keywords_cn": keywords_cn,
        "keywords_en": keywords_en,
    }

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

    unverified_blocks = []
    if thesis_path and thesis_path.exists():
        for block in source_blocks:
            if not isinstance(block, dict):
                unverified_blocks.append({"block_id": None, "reasons": ["source_block_not_object"]})
                continue
            if block.get("target_slot") != "chapters/basicinfo.tex":
                continue
            if block.get("status") == "discarded_with_reason":
                continue
            if block.get("status") not in {"mapped", "rendered"}:
                unverified_blocks.append(
                    {
                        "block_id": block.get("id"),
                        "reasons": [f"source_block_state:{block.get('status')}"],
                    }
                )
                continue
            verified_fields, problems = verify_basicinfo_block(block, field_values)
            if not problems:
                block["status"] = "rendered"
                block["render_result"] = {
                    "path": "chapters/basicinfo.tex",
                    "kind": "latex_macro",
                    "metadata_fields": verified_fields,
                    "evidence": "all_bound_values_found_in_source_block",
                }
            else:
                block["status"] = "mapped"
                block["render_result"] = None
                unverified_blocks.append(
                    {
                        "block_id": block.get("id"),
                        "metadata_fields": block_metadata_fields(block),
                        "reasons": problems,
                    }
                )
        result_status = "needs_confirmation" if unverified_blocks else "passed"
        thesis.setdefault("render_log", []).append(
            {
                "step": "render_basicinfo",
                "status": result_status,
                "target": rel(target, root),
                "rendered_at": now_iso(),
                "unverified_blocks": unverified_blocks,
            }
        )
        write_json(thesis_path, thesis)
    else:
        result_status = "passed"

    return {
        "flow": "B",
        "step": "render_basicinfo",
        "status": result_status,
        "target": rel(target, root),
        "gate": "basicinfo_source_evidence" if unverified_blocks else None,
        "unverified_blocks": unverified_blocks,
        "next_steps": (
            [
                "为每个 basicinfo 源块声明 metadata_fields，并确认实际字段值能在源块中找到。",
                "不能由宏承接的同块文字必须改映射，或用 metadata_excluded_text 和 metadata_exclusion_reason 明确记录。",
            ]
            if unverified_blocks
            else []
        ),
    }


def main() -> int:
    """解析命令行参数并执行 basicinfo 渲染。

    Returns:
        int: 渲染通过时返回 0，否则返回 2。
    """
    parser = argparse.ArgumentParser(
        description="把已确认的 metadata、摘要和关键词渲染到 chapters/basicinfo.tex。"
    )
    parser.add_argument("--root", default=".", help="ZUFE-Thesis 模板根目录。")
    parser.add_argument(
        "--metadata",
        default="workspace/input/metadata.yaml",
        help="相对模板根目录的 metadata 路径。",
    )
    parser.add_argument(
        "--thesis-json",
        default="workspace/intermediate/thesis.json",
        help="相对模板根目录的流程 B 账本路径。",
    )
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
