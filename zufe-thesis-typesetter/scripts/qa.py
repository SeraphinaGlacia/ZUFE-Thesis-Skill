#!/usr/bin/env python3
"""流程 C 的 PDF 文本级和源码级 QA。"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
from pathlib import Path

from check_flow_b_gate import check as check_flow_b_gate
from common import (
    active_chapter_files,
    latex_label_reference_issues,
    load_metadata_yaml,
    manual_cross_reference_hits,
    metadata_value,
    print_json,
    read_json,
    write_json,
)

PLACEHOLDER_PATTERNS = [
    r"xxxxxxxxxxxx",
    r"\b20xx\b",
    r"本文……",
    r"摘要的内容要包括",
    r"\bxxx\b",
]

KEY_SIGNALS = {
    "table_of_contents": r"目\s*录|Contents",
    "abstract_cn": r"摘\s*要",
    "abstract_en": r"Abstract",
    "references": r"参考文献|References",
}

SERIOUS_LOG_RE = re.compile(
    r"^!\s|Emergency stop|Fatal error occurred|No pages of output|"
    r"There were undefined references",
    flags=re.IGNORECASE | re.MULTILINE,
)

BIB_ENTRY_RE = re.compile(r"@\w+\s*[\{(]\s*([^,\s]+)", flags=re.IGNORECASE)
CITE_RE = re.compile(
    r"\\(?:cite|supercite|parencite|textcite|autocite|citep|citet)"
    r"(?:\s*\[[^\]]*\]){0,2}\s*\{([^}]+)\}",
    flags=re.IGNORECASE,
)
QA_TOOL_TIMEOUT_SECONDS = 30


def extract_text_with_pdftotext(pdf: Path) -> str:
    """使用 pdftotext 抽取 PDF 文本。

    Args:
        pdf (Path): PDF 文件路径。

    Returns:
        str: 抽取出的文本；pdftotext 不可用时返回空字符串。
    """
    if shutil.which("pdftotext") is None:
        return ""
    try:
        process = subprocess.run(
            ["pdftotext", str(pdf), "-"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=QA_TOOL_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return process.stdout or ""


def count_pdf_pages_with_pdfinfo(pdf: Path) -> int:
    """优先使用 pdfinfo 读取 PDF 页数。

    Args:
        pdf (Path): PDF 文件路径。

    Returns:
        int: ``pdfinfo`` 成功读取到的页数；不可用或解析失败时返回 0。
    """
    if shutil.which("pdfinfo") is None:
        return 0
    try:
        process = subprocess.run(
            ["pdfinfo", str(pdf)],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=QA_TOOL_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired):
        return 0
    if process.returncode != 0:
        return 0
    match = re.search(r"^Pages:\s*(\d+)\s*$", process.stdout or "", re.MULTILINE)
    return int(match.group(1)) if match else 0


def count_pdf_pages(pdf: Path) -> int:
    """统计 PDF 页数。

    Args:
        pdf (Path): PDF 文件路径。

    Returns:
        int: 检测到的页面数量。
    """
    page_count = count_pdf_pages_with_pdfinfo(pdf)
    if page_count:
        return page_count

    # 有些 PDF 会压缩页对象，原始字节扫描只能作为缺少 pdfinfo 时的兜底。
    data = pdf.read_bytes()
    return len(re.findall(rb"/Type\s*/Page\b", data))


def read_text(path: Path) -> str:
    """读取 UTF-8 文本文件，缺失时返回空字符串。

    Args:
        path (Path): 文本文件路径。

    Returns:
        str: 文件文本；文件不存在时为空字符串。
    """
    return path.read_text(encoding="utf-8", errors="ignore") if path.exists() else ""


def read_json_object(path: Path) -> dict:
    """读取 JSON 对象，缺失或损坏时返回空对象供 QA 生成失败项。

    Args:
        path (Path): JSON 文件路径。

    Returns:
        dict: JSON 顶层对象；无法读取或类型不符时为空对象。
    """
    try:
        data = read_json(path, default={})
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def rendered_source_text(root: Path, thesis: dict | None = None) -> str:
    """读取生成章节源码用于源码级 QA。

    Args:
        root (Path): ZUFE-Thesis 模板根目录。

    Returns:
        str: 拼接后的章节源码文本。
    """
    return "\n".join(read_text(path) for path in active_chapter_files(root, thesis))


def build_log_text(root: Path) -> str:
    """读取主日志和固定编译链日志。

    Args:
        root (Path): ZUFE-Thesis 模板根目录。
        thesis (dict | None): 当前账本；未提供时读取标准路径。

    Returns:
        str: 合并后的构建日志。
    """
    paths = [root / "main.log", root / "main.blg"]
    output_dir = root / "workspace/output"
    if output_dir.exists():
        step_logs = sorted(output_dir.glob("build-step-*.log"))
        paths.extend(step_logs[-1:])
    return "\n".join(read_text(path) for path in paths if path.exists())


def body_signal(thesis: dict, pdf_text: str) -> tuple[bool, str]:
    """从已确认章节标题或正文源块验证 PDF 正文信号。

    Args:
        thesis (dict): ``thesis.json`` 数据。
        pdf_text (str): 从本轮 PDF 抽取的文本。

    Returns:
        tuple[bool, str]: 是否命中以及采用的证据说明。
    """
    normalized_pdf = re.sub(r"\s+", "", pdf_text).casefold()
    candidates = []
    structure = thesis.get("structure", {})
    chapters = structure.get("chapters", []) if isinstance(structure, dict) else []
    chapters = chapters if isinstance(chapters, list) else []
    for chapter in chapters:
        if not isinstance(chapter, dict):
            continue
        title = str(chapter.get("title") or "").strip()
        if title:
            candidates.append(("chapter_title", title))
    if not candidates:
        source_blocks = thesis.get("source_blocks", [])
        source_blocks = source_blocks if isinstance(source_blocks, list) else []
        for block in source_blocks:
            if not isinstance(block, dict):
                continue
            target = str(block.get("target_slot") or "")
            text = str(block.get("text") or "").strip()
            if (
                block.get("status") == "rendered"
                and target.startswith("chapters/")
                and target not in {"chapters/basicinfo.tex", "chapters/mainbody.tex"}
                and len(re.sub(r"\s+", "", text)) >= 6
            ):
                candidates.append(("rendered_source_block", text[:80]))
                break
    for source, candidate in candidates:
        normalized_candidate = re.sub(r"\s+", "", candidate).casefold()
        if normalized_candidate and normalized_candidate in normalized_pdf:
            return True, f"matched {source}: {candidate[:80]}"
    if candidates:
        return False, f"none of {len(candidates)} audited body candidate(s) found"
    return False, "thesis.json contains no audited chapter title or rendered body block"


def count_runs_with_flag(thesis: dict, flag: str) -> int:
    """统计 thesis.json 中带指定 run 标记的数量。

    Args:
        thesis (dict): ``workspace/intermediate/thesis.json`` 数据。
        flag (str): run 级布尔标记名称。

    Returns:
        int: 带该标记的 run 数量。
    """
    count = 0
    source_blocks = thesis.get("source_blocks", [])
    source_blocks = source_blocks if isinstance(source_blocks, list) else []
    for block in source_blocks:
        if not isinstance(block, dict):
            continue
        runs = block.get("runs", [])
        if not isinstance(runs, list):
            continue
        count += sum(1 for run in runs if isinstance(run, dict) and run.get(flag))
    return count


def bibtex_keys(bib_text: str) -> list[str]:
    """提取 BibTeX 条目 key。

    Args:
        bib_text (str): Reference.bib 文本。

    Returns:
        list[str]: BibTeX key 列表。
    """
    return [match.strip() for match in BIB_ENTRY_RE.findall(bib_text) if match.strip()]


def duplicate_values(values: list[str]) -> list[str]:
    """找出列表中的重复值。

    Args:
        values (list[str]): 待检查值列表。

    Returns:
        list[str]: 排序后的重复值列表。
    """
    seen = set()
    duplicates = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return sorted(duplicates)


def braces_balanced(text: str) -> bool:
    """检查文本中的大括号是否平衡。

    Args:
        text (str): 待检查文本。

    Returns:
        bool: 大括号平衡时返回 True。
    """
    depth = 0
    escaped = False
    for char in text:
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth < 0:
                return False
    return depth == 0


def cited_keys(source_text: str) -> list[str]:
    """提取章节源码中的引用 key。

    Args:
        source_text (str): 章节源码文本。

    Returns:
        list[str]: 去重排序后的引用 key 列表。
    """
    keys = []
    for group in CITE_RE.findall(source_text):
        keys.extend(key.strip() for key in group.split(",") if key.strip())
    return sorted(set(keys))


def bibtex_quality_checks(root: Path, source_text: str) -> list[dict]:
    """执行 BibTeX 和 citation 闭环 QA。

    Args:
        root (Path): ZUFE-Thesis 模板根目录。
        source_text (str): 章节源码文本。

    Returns:
        list[dict]: BibTeX QA 检查项列表。
    """
    checks = []
    bib_text = read_text(root / "Reference.bib")
    keys = bibtex_keys(bib_text)
    duplicates = duplicate_values(keys)
    checks.append(
        {
            "name": "bibtex_duplicate_keys",
            "status": "failed" if duplicates else "passed",
            "detail": ", ".join(duplicates) if duplicates else "none",
        }
    )

    balanced = braces_balanced(bib_text)
    checks.append(
        {
            "name": "bibtex_braces_balanced",
            "status": "failed" if bib_text.strip() and not balanced else "passed",
            "detail": "balanced" if balanced else "unbalanced braces",
        }
    )

    cited = cited_keys(source_text)
    missing = sorted(set(cited) - set(keys))
    checks.append(
        {
            "name": "citation_keys_defined",
            "status": "failed" if missing else "passed",
            "detail": ", ".join(missing) if missing else "none",
        }
    )
    return checks


def source_quality_checks(root: Path, thesis: dict | None = None) -> list[dict]:
    """执行章节源码级 QA。

    Args:
        root (Path): ZUFE-Thesis 模板根目录。
        thesis (dict | None): 当前账本；未提供时读取标准路径。

    Returns:
        list[dict]: 源码级 QA 检查项列表。
    """
    checks = []
    source_text = rendered_source_text(root, thesis)
    if thesis is None:
        thesis = read_json_object(root / "workspace/intermediate/thesis.json")

    resize_hits = re.findall(
        r"\\resizebox\s*\{\s*\\textwidth\s*\}\s*\{\s*!\s*\}",
        source_text,
    )
    checks.append(
        {
            "name": "source_table_resizebox_textwidth",
            "status": "warning" if resize_hits else "passed",
            "detail": f"{len(resize_hits)} unguarded textwidth resizebox occurrence(s).",
        }
    )

    manual_reference_hits = manual_cross_reference_hits(source_text)
    checks.append(
        {
            "name": "source_manual_cross_reference_numbers",
            "status": "failed" if manual_reference_hits else "passed",
            "detail": "; ".join(manual_reference_hits) if manual_reference_hits else "none",
        }
    )
    label_reference_issues = latex_label_reference_issues(source_text)
    checks.append(
        {
            "name": "source_duplicate_latex_labels",
            "status": "failed" if label_reference_issues["duplicate_labels"] else "passed",
            "detail": ", ".join(label_reference_issues["duplicate_labels"])
            if label_reference_issues["duplicate_labels"]
            else "none",
        }
    )
    checks.append(
        {
            "name": "source_undefined_latex_refs",
            "status": "failed" if label_reference_issues["undefined_refs"] else "passed",
            "detail": ", ".join(label_reference_issues["undefined_refs"])
            if label_reference_issues["undefined_refs"]
            else "none",
        }
    )

    superscript_runs = count_runs_with_flag(thesis, "superscript")
    rendered_superscripts = len(re.findall(r"\\textsuperscript\s*\{", source_text))
    checks.append(
        {
            "name": "source_superscript_runs_rendered",
            "status": "warning" if rendered_superscripts < superscript_runs else "passed",
            "detail": (
                f"{superscript_runs} superscript run(s); "
                f"{rendered_superscripts} rendered marker(s)."
            ),
        }
    )

    subscript_runs = count_runs_with_flag(thesis, "subscript")
    rendered_subscripts = len(re.findall(r"\\textsubscript\s*\{", source_text))
    checks.append(
        {
            "name": "source_subscript_runs_rendered",
            "status": "warning" if rendered_subscripts < subscript_runs else "passed",
            "detail": (
                f"{subscript_runs} subscript run(s); {rendered_subscripts} rendered marker(s)."
            ),
        }
    )
    checks.extend(bibtex_quality_checks(root, source_text))
    return checks


def qa(root: Path) -> dict:
    """执行流程 C 产物 QA 并写入报告。

    Args:
        root (Path): ZUFE-Thesis 模板根目录。

    Returns:
        dict: QA 结果，同时写入 ``qa_result.json`` 和 ``qa_report.md``。
    """
    output_dir = root / "workspace/output"
    output_dir.mkdir(parents=True, exist_ok=True)
    build_result_path = output_dir / "build_result.json"
    thesis_path = root / "workspace/intermediate/thesis.json"
    build_result = read_json_object(build_result_path)
    thesis = read_json_object(thesis_path)
    metadata = load_metadata_yaml(root / "workspace/input/metadata.yaml")
    thesis_metadata = thesis.get("metadata", {})
    thesis_metadata = thesis_metadata if isinstance(thesis_metadata, dict) else {}
    english_content_decision = metadata_value(
        metadata,
        "english_content_decision",
        default=str(thesis_metadata.get("english_content_decision") or ""),
    ).lower()
    pdf = root / "main.pdf"
    checks = []

    flow_b_result = check_flow_b_gate(root, thesis_path)
    flow_b_passed = flow_b_result.get("status") == "passed"
    checks.append(
        {
            "name": "flow_b_gate_current",
            "status": "passed" if flow_b_passed else "failed",
            "detail": (
                "当前 thesis.json 通过流程 B 门禁。"
                if flow_b_passed
                else "当前 thesis.json 未通过流程 B 门禁。"
            ),
        }
    )
    recorded_gate = build_result.get("flow_b_gate", {})
    recorded_gate = recorded_gate if isinstance(recorded_gate, dict) else {}
    gate_binding_passed = (
        flow_b_passed
        and recorded_gate.get("status") == "passed"
        and recorded_gate.get("thesis_json_fingerprint")
        == flow_b_result.get("thesis_json_fingerprint")
        and recorded_gate.get("source_docx_fingerprint")
        == flow_b_result.get("source_docx_fingerprint")
    )
    checks.append(
        {
            "name": "build_flow_b_binding",
            "status": "passed" if gate_binding_passed else "failed",
            "detail": (
                "构建结果与当前 thesis.json 和源 DOCX 指纹一致。"
                if gate_binding_passed
                else "构建结果未记录通过的流程 B 门禁，或输入已在构建后变化。"
            ),
        }
    )

    build_report = output_dir / "report.md"
    checks.append(
        {
            "name": "build_report_exists",
            "status": "passed" if build_report.exists() else "failed",
            "detail": "workspace/output/report.md 存在。"
            if build_report.exists()
            else "workspace/output/report.md 缺失；必须先运行 build.py。",
        }
    )
    build_passed = build_result.get("status") == "passed"
    build_steps = build_result.get("steps")
    steps_passed = (
        isinstance(build_steps, list)
        and len(build_steps) == 4
        and all(step.get("exit_code") == 0 for step in build_steps if isinstance(step, dict))
        and all(isinstance(step, dict) for step in build_steps)
    )
    checks.append(
        {
            "name": "build_chain_passed",
            "status": "passed" if build_passed and steps_passed else "failed",
            "detail": (
                "build_result.json 记录固定四步编译链全部通过。"
                if build_passed and steps_passed
                else "build_result.json 缺失、状态未通过或四步编译记录不完整。"
            ),
        }
    )
    if pdf.exists():
        checks.append({"name": "pdf_exists", "status": "passed", "detail": "main.pdf 存在。"})
    else:
        checks.append({"name": "pdf_exists", "status": "failed", "detail": "main.pdf 缺失。"})

    new_pdf = bool(build_result.get("new_pdf")) if build_result else False
    freshness_detail = (
        f"new_pdf={new_pdf}"
        if build_result
        else "missing workspace/output/build_result.json; run build.py before QA."
    )
    checks.append(
        {
            "name": "pdf_freshness",
            "status": "passed" if new_pdf else "failed",
            "detail": freshness_detail,
        }
    )

    page_count = count_pdf_pages(pdf) if pdf.exists() else 0
    checks.append(
        {
            "name": "page_count",
            "status": "passed" if page_count > 0 else "warning" if pdf.exists() else "failed",
            "detail": (
                str(page_count)
                if page_count > 0
                else "PDF 存在，但当前工具无法可靠确认页数。"
                if pdf.exists()
                else "PDF 不存在，无法读取页数。"
            ),
        }
    )

    text = extract_text_with_pdftotext(pdf) if pdf.exists() else ""
    checks.append(
        {
            "name": "pdf_text",
            "status": "passed" if text.strip() else "warning",
            "detail": "已抽取 PDF 文本。" if text.strip() else "pdftotext 未能抽取 PDF 文本。",
        }
    )

    for name, pattern in KEY_SIGNALS.items():
        found = re.search(pattern, text, flags=re.IGNORECASE) is not None
        explicitly_omitted = name == "abstract_en" and english_content_decision == "omit"
        checks.append(
            {
                "name": f"signal_{name}",
                "status": (
                    "passed"
                    if found or explicitly_omitted
                    else "failed"
                    if text.strip()
                    else "warning"
                ),
                "detail": (
                    "用户已明确选择省略英文摘要。"
                    if explicitly_omitted and not found
                    else f"PDF 文本中{'找到' if found else '未找到'} {pattern!r}。"
                ),
            }
        )

    body_found, body_detail = body_signal(thesis, text)
    checks.append(
        {
            "name": "signal_body",
            "status": "passed" if body_found else "failed" if text.strip() else "warning",
            "detail": body_detail,
        }
    )

    source_text = rendered_source_text(root, thesis)
    combined = text + "\n" + source_text
    for pattern in PLACEHOLDER_PATTERNS:
        found = re.search(pattern, combined, flags=re.IGNORECASE) is not None
        checks.append(
            {
                "name": f"placeholder_{pattern}",
                "status": "warning" if found else "passed",
                "detail": "found" if found else "not found",
            }
        )

    logs = build_log_text(root)
    serious_error = SERIOUS_LOG_RE.search(logs)
    checks.append(
        {
            "name": "serious_build_errors",
            "status": "failed" if serious_error else "passed",
            "detail": serious_error.group(0) if serious_error else "none",
        }
    )
    unresolved = re.search(
        r"undefined references|Citation .* undefined|"
        r"LaTeX Warning: Reference .* undefined|\?\?",
        logs + "\n" + text,
        flags=re.IGNORECASE,
    )
    checks.append(
        {
            "name": "unresolved_references",
            "status": "failed" if unresolved else "passed",
            "detail": unresolved.group(0) if unresolved else "none",
        }
    )
    checks.extend(source_quality_checks(root, thesis))

    failed = [check for check in checks if check["status"] == "failed"]
    warnings = [check for check in checks if check["status"] == "warning"]
    final_status = "failed" if failed else "needs_review" if warnings else "ready_for_manual_review"
    result = {
        "flow": "C",
        "step": "qa",
        "status": final_status,
        "pdf": "main.pdf" if pdf.exists() else None,
        "page_count": page_count,
        "checks": checks,
        "manual_review_required": True,
        "automated_scope": "source_and_pdf_text",
        "reports": {
            "build": "workspace/output/report.md",
            "qa": "workspace/output/qa_report.md",
        },
        "next_steps": (
            ["修复 failed 检查后重新编译并运行 QA。"]
            if final_status == "failed"
            else ["人工打开 PDF，检查封面、分页、图表、公式和整体版式后再提交。"]
        ),
    }
    write_json(output_dir / "qa_result.json", result)
    report = [
        "# QA Report",
        "",
        f"- Final status: `{final_status}`",
        f"- PDF: `{result['pdf']}`",
        f"- Page count: `{page_count}`",
        "",
        "## Checks",
        "",
    ]
    for check in checks:
        report.append(f"- `{check['name']}`: `{check['status']}` - {check['detail']}")
    (output_dir / "qa_report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    return result


def main() -> int:
    """解析命令行参数并执行流程 C QA。

    Returns:
        int: QA 非 failed 时返回 0，否则返回 2。
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    args = parser.parse_args()
    result = qa(Path(args.root).expanduser().resolve())
    print_json(result)
    return 0 if result["status"] != "failed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
