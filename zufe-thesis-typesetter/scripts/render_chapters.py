#!/usr/bin/env python3
"""把已确认的流程 B 章节映射渲染为 TeX 文件。"""

from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path

from common import (
    latex_escape,
    now_iso,
    print_json,
    read_json,
    rel,
    safe_resolve_under,
    write_json,
)


def tex_heading(text: str, command: str) -> str:
    """渲染 LaTeX 标题命令。

    Args:
        text (str): 标题文本。
        command (str): LaTeX 标题命令名，例如 ``chapter``。

    Returns:
        str: 已转义的标题命令。
    """
    return f"\\{command}{{{latex_escape(text)}}}"


def formatted_run_to_latex(run: dict, quote_state: dict[str, bool] | None = None) -> str:
    """把单个 Word run 渲染为 LaTeX 片段。

    Args:
        run (dict): ``thesis.json`` 中的 run 级格式证据。
        quote_state (dict[str, bool] | None): 跨 run 共享的 ASCII 引号状态。

    Returns:
        str: 保留粗体、斜体、上下标后的 LaTeX 片段。
    """
    text = latex_escape(run.get("text") or "", quote_state=quote_state)
    if not text:
        return ""
    if run.get("bold"):
        text = f"\\textbf{{{text}}}"
    if run.get("italic"):
        text = f"\\textit{{{text}}}"
    if run.get("superscript"):
        text = f"\\textsuperscript{{{text}}}"
    if run.get("subscript"):
        text = f"\\textsubscript{{{text}}}"
    return text


def runs_to_latex(block: dict) -> str | None:
    """把源块中的 runs 合并渲染为 LaTeX。

    Args:
        block (dict): ``thesis.json`` 源块。

    Returns:
        str | None: 渲染后的 run 文本；没有可渲染 run 时返回 None。
    """
    runs = block.get("runs") or []
    if not runs:
        return None
    quote_state = {"next_quote_is_opening": True}
    rendered = "".join(formatted_run_to_latex(run, quote_state) for run in runs)
    return rendered if rendered else None


def table_needs_wrapping(rows: list[list[str]], col_count: int) -> bool:
    """判断表格是否需要使用固定宽度列换行。

    Args:
        rows (list[list[str]]): 表格行数据。
        col_count (int): 表格列数。

    Returns:
        bool: 列数多或单元格较长时返回 True。
    """
    if col_count > 4:
        return True
    for row in rows:
        for cell in row:
            text = str(cell or "")
            if "\n" in text or len(text) > 24:
                return True
    return False


def table_cell_to_latex(cell: str) -> str:
    """渲染单个表格单元格文本。

    Args:
        cell (str): 单元格原始文本。

    Returns:
        str: 已转义并保留换行语义的 LaTeX 单元格文本。
    """
    lines = [latex_escape(line.strip()) for line in str(cell or "").splitlines()]
    lines = [line for line in lines if line]
    return r"\newline ".join(lines)


def table_column_spec(rows: list[list[str]], col_count: int) -> str:
    """根据表格形状生成 tabular 列格式。

    Args:
        rows (list[list[str]]): 表格行数据。
        col_count (int): 表格列数。

    Returns:
        str: tabular 列格式字符串。
    """
    if col_count <= 0:
        return "l"
    if not table_needs_wrapping(rows, col_count):
        return "@{}" + ("l" * col_count) + "@{}"
    if col_count == 1:
        return r"@{}>{\raggedright\arraybackslash}p{0.90\textwidth}@{}"
    if col_count == 2:
        return (
            r"@{}>{\raggedright\arraybackslash}p{0.44\textwidth}"
            r">{\raggedright\arraybackslash}p{0.44\textwidth}@{}"
        )
    first_width = 0.30 if col_count <= 4 else 0.34
    other_width = max(0.08, (0.92 - first_width) / (col_count - 1))
    other = "".join(
        rf">{{\raggedright\arraybackslash}}p{{{other_width:.2f}\textwidth}}"
        for _ in range(col_count - 1)
    )
    return rf"@{{}}>{{\raggedright\arraybackslash}}p{{{first_width:.2f}\textwidth}}{other}@{{}}"


def table_to_latex(block: dict) -> str:
    """把 table 源块渲染为 LaTeX table 环境。

    Args:
        block (dict): ``source_type=table`` 的源块。

    Returns:
        str: LaTeX 表格环境。
    """
    rows = block.get("table", {}).get("rows", [])
    if not rows:
        return "% 空表格源块"
    col_count = max((len(row) for row in rows), default=1)
    body = []
    for index, row in enumerate(rows):
        padded = row + [""] * (col_count - len(row))
        body.append(
            "    " + " & ".join(table_cell_to_latex(cell) for cell in padded) + r" \\"
        )
        if index == 0 and len(rows) > 1:
            body.append(r"    \midrule")

    lines = [
        r"\begin{table}[htbp]",
        r"  \centering",
    ]
    if block.get("caption"):
        lines.append(f"  \\caption{{{latex_escape(block['caption'])}}}")
    lines.extend(
        [
            r"  \zihao{5}",
            r"  \songti",
            r"  \setlength{\tabcolsep}{3pt}",
            r"  \renewcommand{\arraystretch}{1.18}",
            f"  \\begin{{tabular}}{{{table_column_spec(rows, col_count)}}}",
            r"    \toprule",
            *body,
            r"    \bottomrule",
            r"  \end{tabular}",
            r"\end{table}",
        ]
    )
    return "\n".join(lines)


def block_to_latex(block: dict) -> str:
    """把单个已映射源块渲染为 LaTeX。

    Args:
        block (dict): ``thesis.json`` 源块。

    Returns:
        str: 源块对应的 LaTeX 文本。
    """
    if block.get("latex"):
        return str(block["latex"])
    text = block.get("text") or block.get("summary") or ""
    role = block.get("semantic_role") or block.get("candidate_type")
    level = int(block.get("level") or 0)
    if block.get("source_type") == "image":
        path = block.get("asset_output") or block.get("target_slot") or ""
        caption = block.get("caption") or block.get("summary") or ""
        return "\n".join(
            [
                "\\begin{figure}[htbp]",
                "  \\centering",
                "  \\includegraphics[width=0.8\\textwidth]{"
                f"{latex_escape(path, convert_quotes=False)}"
                "}",
                f"  \\caption{{{latex_escape(caption)}}}",
                "\\end{figure}",
            ]
        )
    if block.get("source_type") == "table":
        return table_to_latex(block)
    if level == 1:
        return tex_heading(text, "chapter")
    if level == 2:
        return tex_heading(text, "section")
    if level == 3:
        return tex_heading(text, "subsection")
    if role == "heading":
        return tex_heading(text, "chapter")
    return (runs_to_latex(block) or latex_escape(text)) + "\n"


def grouped_chapters(thesis: dict) -> list[dict]:
    """从结构信息或目标槽位推导章节渲染顺序。

    Args:
        thesis (dict): ``workspace/intermediate/thesis.json`` 数据。

    Returns:
        list[dict]: 章节条目列表，每项包含标题、文件和源块 ID。
    """
    chapters = thesis.get("structure", {}).get("chapters") or []
    if chapters:
        return chapters
    grouped = defaultdict(list)
    for block in thesis.get("source_blocks", []):
        target = block.get("target_slot") or ""
        if (
            target.startswith("chapters/")
            and target.endswith(".tex")
            and target != "chapters/basicinfo.tex"
        ):
            grouped[target].append(block["id"])
    return [
        {"title": Path(target).stem, "file": target, "block_ids": block_ids}
        for target, block_ids in sorted(grouped.items())
    ]


def render(root: Path, thesis_path: Path, allow_incomplete: bool) -> dict:
    """把已确认章节映射写入章节文件和 mainbody.tex。

    Args:
        root (Path): ZUFE-Thesis 模板根目录。
        thesis_path (Path): ``workspace/intermediate/thesis.json`` 路径。
        allow_incomplete (bool): 是否允许在仍有阻塞块时渲染。

    Returns:
        dict: 渲染结果；存在未确认源块时可返回 blocked。
    """
    thesis = read_json(thesis_path)
    blocks_by_id = {block["id"]: block for block in thesis.get("source_blocks", [])}
    blocking = [
        block["id"]
        for block in thesis.get("source_blocks", [])
        if block.get("status") in {"blocked", "needs_confirmation"}
    ]
    if blocking and not allow_incomplete:
        return {
            "flow": "B",
            "step": "render_chapters",
            "status": "blocked",
            "blocking_blocks": blocking,
            "next_steps": ["先解决或明确丢弃阻塞源块，再渲染章节。"],
        }

    rendered_files = []
    mainbody_lines = [
        "% Generated by zufe-thesis-typesetter.",
        "% 章节顺序来自 workspace/intermediate/thesis.json。",
        "",
    ]
    for chapter in grouped_chapters(thesis):
        try:
            target = safe_resolve_under(root, chapter["file"], "chapters")
        except ValueError as exc:
            return {
                "flow": "B",
                "step": "render_chapters",
                "status": "blocked",
                "error": str(exc),
            }
        target_rel = rel(target, root)
        lines = [f"% Generated chapter: {chapter.get('title', target.stem)}", ""]
        for block_id in chapter.get("block_ids", []):
            block = blocks_by_id.get(block_id)
            if not block:
                continue
            lines.append(f"% Source block: {block_id}")
            lines.append(block_to_latex(block))
            lines.append("")
            block["status"] = "rendered"
            block["render_result"] = {"path": target_rel, "kind": "chapter_tex"}
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("\n".join(lines), encoding="utf-8")
        rendered_files.append(target_rel)
        mainbody_lines.append(f"\\input{{{Path(target_rel).with_suffix('').as_posix()}}}")

    mainbody_lines.extend(
        [
            "",
            "% 参考文献由模板打印。",
            "\\input{misc/reference}",
            "",
        ]
    )
    mainbody = safe_resolve_under(root, "chapters/mainbody.tex", "chapters")
    mainbody.write_text("\n".join(mainbody_lines), encoding="utf-8")
    thesis.setdefault("render_log", []).append(
        {
            "step": "render_chapters",
            "status": "completed",
            "targets": rendered_files + [rel(mainbody, root)],
            "rendered_at": now_iso(),
        }
    )
    write_json(thesis_path, thesis)
    return {
        "flow": "B",
        "step": "render_chapters",
        "status": "passed",
        "targets": rendered_files + [rel(mainbody, root)],
    }


def main() -> int:
    """解析命令行参数并执行章节渲染。

    Returns:
        int: 渲染通过时返回 0，否则返回 2。
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--thesis-json", default="workspace/intermediate/thesis.json")
    parser.add_argument("--allow-incomplete", action="store_true")
    args = parser.parse_args()
    root = Path(args.root).expanduser().resolve()
    thesis_path = (
        (root / args.thesis_json).resolve()
        if not Path(args.thesis_json).is_absolute()
        else Path(args.thesis_json).resolve()
    )
    result = render(root, thesis_path, args.allow_incomplete)
    print_json(result)
    return 0 if result["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
