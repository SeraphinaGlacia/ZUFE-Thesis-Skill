#!/usr/bin/env python3
"""流程 A 的 DOCX 轻量预扫描，用于可读性检查和 metadata 候选提取。"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

from common import block_summary, classify_text, now_iso, print_json, write_json


def import_docx() -> Any:
    """导入 python-docx，并把缺依赖错误转换为用户可读异常。

    Returns:
        Any: ``docx`` 模块对象。

    Raises:
        RuntimeError: 当前 Python 环境无法导入 ``python-docx`` 时抛出。
    """
    try:
        import docx  # type: ignore
    except Exception as exc:
        raise RuntimeError(f"python-docx 不可用：{exc}") from exc
    return docx


def candidate(pattern: str, text: str) -> str:
    """按正则表达式提取第一个捕获组。

    Args:
        pattern (str): 包含一个捕获组的正则表达式。
        text (str): 待匹配文本。

    Returns:
        str: 捕获值；无匹配时返回空字符串。
    """
    match = re.search(pattern, text, flags=re.IGNORECASE)
    return match.group(1).strip() if match else ""


def clean_label(text: str) -> str:
    """清理表格字段标签，便于映射为 metadata key。

    Args:
        text (str): 原始标签文本。

    Returns:
        str: 去除空白和冒号后的标签。
    """
    return re.sub(r"[\s:：]+", "", text or "")


def clean_value(text: str) -> str:
    """清理表格单元格或段落值。

    Args:
        text (str): 原始文本。

    Returns:
        str: 压缩空白后的文本。
    """
    return re.sub(r"\s+", " ", text or "").strip()


def report_style_candidate(text: str) -> str:
    """从文本中识别模板 report_style 候选。

    Args:
        text (str): Word 封面或正文文本。

    Returns:
        str: 专业实践返回 ``1``，毕业论文返回 ``0``，无证据返回空字符串。
    """
    if re.search(r"专业实践|实践报告|专业实习", text):
        return "1"
    if re.search(r"毕业论文|学位论文|本科论文", text):
        return "0"
    return ""


def is_report_style_line(text: str) -> bool:
    """判断短行是否只是报告类型说明。

    Args:
        text (str): 待判断文本。

    Returns:
        bool: 文本像单独报告类型行时返回 True。
    """
    return bool(report_style_candidate(text)) and len(clean_value(text)) <= 20


def table_field_candidates(tables: list[Any]) -> dict:
    """从封面表格中提取 metadata 候选。

    Args:
        tables (list[Any]): python-docx 表格对象列表。

    Returns:
        dict: 从相邻标签/值单元格中提取的 metadata 候选。
    """
    label_to_key = {
        "报告类型": "report_style",
        "论文类型": "report_style",
        "指导教师": "mentor",
        "导师": "mentor",
        "专业名称": "major",
        "专业": "major",
        "学院": "college",
        "院系": "college",
        "学生姓名": "name",
        "姓名": "name",
        "学号": "student_id",
        "班级": "class_name",
        "日期": "date",
        "完成日期": "date",
    }
    data = {}
    for table in tables:
        for row in table.rows:
            cells = [clean_value(cell.text) for cell in row.cells]
            for index, cell in enumerate(cells[:-1]):
                key = label_to_key.get(clean_label(cell))
                value = cells[index + 1] if key else ""
                if not key or not value or data.get(key):
                    continue
                data[key] = report_style_candidate(value) if key == "report_style" else value
    return data


def metadata_candidates(lines: list[str], tables: list[Any] | None = None) -> dict:
    """根据轻量预扫描文本生成 metadata 候选。

    Args:
        lines (list[str]): 前若干段落和表格单元格文本。
        tables (list[Any] | None): python-docx 表格对象列表。

    Returns:
        dict: report_style、题目、姓名、学号等候选字段。
    """
    joined = "\n".join(lines[:80])
    first_long = next(
        (
            line
            for line in lines[:20]
            if len(line) >= 6
            and not is_report_style_line(line)
            and not re.search(r"姓名|学号|学院|专业|导师|班级", line)
        ),
        "",
    )
    table_candidates = table_field_candidates(tables or [])
    candidates = {
        "report_style": report_style_candidate(joined),
        "thesis_title_cn": first_long,
        "name": candidate(r"(?:姓名|学生姓名)\s*[:：]\s*([^\n]+)", joined),
        "student_id": candidate(r"(?:学号)\s*[:：]\s*([A-Za-z0-9-]+)", joined),
        "college": candidate(r"(?:学院|院系)\s*[:：]\s*([^\n]+)", joined),
        "major": candidate(r"(?:专业名称|专业)\s*[:：]\s*([^\n]+)", joined),
        "mentor": candidate(r"(?:导师|指导教师)\s*[:：]\s*([^\n]+)", joined),
        "class_name": candidate(r"(?:班级)\s*[:：]\s*([^\n]+)", joined),
        "date": candidate(
            r"((?:20\d{2}|二〇\d{2}|二零\d{2})年\s*\d{1,2}月?)",
            joined,
        ),
    }
    for key, value in table_candidates.items():
        if value and not candidates.get(key):
            candidates[key] = value
    return candidates


def table_text_lines(tables: list[Any]) -> list[str]:
    """把表格单元格文本展平为 metadata 预扫描行。

    Args:
        tables (list[Any]): python-docx 表格对象列表。

    Returns:
        list[str]: 非空单元格文本列表。
    """
    lines = []
    for table in tables:
        for row in table.rows:
            for cell in row.cells:
                text = clean_value(cell.text)
                if text:
                    lines.append(text)
    return lines


def prescan(root: Path, docx_path: Path) -> dict:
    """对 DOCX 做流程 A 轻量预扫描。

    Args:
        root (Path): ZUFE-Thesis 模板根目录；当前仅用于接口一致。
        docx_path (Path): 标准输入 DOCX 路径。

    Returns:
        dict: 可读性、结构预览和 metadata 候选结果。
    """
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
        candidate_type, confidence = classify_text(
            text,
            getattr(paragraph.style, "name", ""),
        )
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
        "metadata_candidates": metadata_candidates(
            non_empty_lines + table_text_lines(document.tables),
            document.tables,
        ),
        "structure_preview": paragraphs[:80],
        "next_steps": (
            []
            if non_empty_lines
            else ["DOCX 没有可读文本，请用户重新另存为 DOCX 或更换文件。"]
        ),
    }
    return result


def main() -> int:
    """解析命令行参数并执行 DOCX 轻量预扫描。

    Returns:
        int: DOCX 可读且有文本时返回 0，否则返回 2。
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--docx", default="workspace/input/thesis.docx")
    parser.add_argument("--output", help="可选 JSON 输出路径。流程 A 不要输出到 thesis.json。")
    args = parser.parse_args()
    root = Path(args.root).expanduser().resolve()
    docx_path = (
        (root / args.docx).resolve()
        if not Path(args.docx).is_absolute()
        else Path(args.docx).resolve()
    )
    result = prescan(root, docx_path)
    if args.output:
        output = (
            (root / args.output).resolve()
            if not Path(args.output).is_absolute()
            else Path(args.output).resolve()
        )
        write_json(output, result)
    print_json(result)
    return 0 if result["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
