#!/usr/bin/env python3
"""流程 C：归档旧产物并运行固定 XeLaTeX/Biber 编译链。"""

from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path

from check_flow_b_gate import check as check_flow_b_gate
from common import BUILD_TEMP_FILES, archive_path, now_iso, print_json, rel, write_json

COMPILE_CHAIN = [
    ["xelatex", "-interaction=nonstopmode", "-halt-on-error", "-file-line-error", "main.tex"],
    ["biber", "main"],
    ["xelatex", "-interaction=nonstopmode", "-halt-on-error", "-file-line-error", "main.tex"],
    ["xelatex", "-interaction=nonstopmode", "-halt-on-error", "-file-line-error", "main.tex"],
]


def subprocess_output_text(output: str | bytes | None) -> str:
    """把 subprocess 的超时输出规范为可写入日志的文本。

    ``TimeoutExpired`` 在部分 Python 版本中即使启用 ``text=True`` 也可能携带
    bytes，因此不能直接与字符串拼接。

    Args:
        output (str | bytes | None): subprocess 捕获的 stdout。

    Returns:
        str: UTF-8 解码后的日志文本。
    """
    if isinstance(output, bytes):
        return output.decode("utf-8", errors="replace")
    return output or ""


def move_if_exists(source: Path, target: Path) -> str | None:
    """如果源文件存在，则移动到归档位置。

    Args:
        source (Path): 待移动的源文件。
        target (Path): 目标归档路径。

    Returns:
        str | None: 已移动文件的目标路径；源文件不存在时返回 None。
    """
    if not source.exists():
        return None
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(target))
    return str(target)


def prepare_build(root: Path) -> list[dict]:
    """归档旧 PDF 和临时编译文件，避免误判旧产物。

    Args:
        root (Path): ZUFE-Thesis 模板根目录。

    Returns:
        list[dict]: 已归档文件的来源和目标路径。
    """
    archived = []
    pdf_target = archive_path(root, "flow-c-before-build") / "main.pdf"
    moved_pdf = move_if_exists(root / "main.pdf", pdf_target)
    if moved_pdf:
        archived.append({"source": "main.pdf", "target": rel(Path(moved_pdf), root)})
    temp_archive = archive_path(root, "flow-c-before-build/temp")
    for filename in BUILD_TEMP_FILES:
        moved = move_if_exists(root / filename, temp_archive / filename)
        if moved:
            archived.append({"source": filename, "target": rel(Path(moved), root)})
    return archived


def run_chain(root: Path, timeout: int) -> list[dict]:
    """按固定顺序运行 XeLaTeX/Biber 编译链。

    Args:
        root (Path): ZUFE-Thesis 模板根目录。
        timeout (int): 单个编译命令的超时时间，单位为秒。

    Returns:
        list[dict]: 每一步命令的退出码、时间和日志路径。
    """
    output_dir = root / "workspace/output"
    output_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for index, command in enumerate(COMPILE_CHAIN, start=1):
        started = now_iso()
        output = ""
        exit_code = 0
        try:
            process = subprocess.run(
                command,
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=timeout,
            )
            output = process.stdout or ""
            exit_code = process.returncode
        except FileNotFoundError as exc:
            output = f"command not found: {command[0]}\n{exc}\n"
            exit_code = 127
        except subprocess.TimeoutExpired as exc:
            output = subprocess_output_text(exc.stdout) + (
                f"\ncommand timed out after {timeout} seconds: {' '.join(command)}\n"
            )
            exit_code = 124
        ended = now_iso()
        log_path = output_dir / f"build-step-{index}-{'-'.join(command)}.log"
        log_path.write_text(output, encoding="utf-8", errors="ignore")
        results.append(
            {
                "index": index,
                "command": command,
                "exit_code": exit_code,
                "started_at": started,
                "ended_at": ended,
                "log": rel(log_path, root),
            }
        )
        if exit_code != 0:
            break
    return results


def write_build_reports(root: Path, result: dict) -> None:
    """写入机器可读和人类可读构建报告。

    Args:
        root (Path): ZUFE-Thesis 模板根目录。
        result (dict): 本轮构建结果。
    """
    output_dir = root / "workspace/output"
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / "build_result.json", result)
    report = [
        "# Build Report",
        "",
        f"- Status: `{result['status']}`",
        f"- New PDF: `{result['new_pdf']}`",
        f"- PDF: `{result['pdf']}`",
        f"- Flow B gate: `{result['flow_b_gate']['status']}`",
        "",
        "## Steps",
        "",
    ]
    for step in result["steps"]:
        report.append(f"- `{' '.join(step['command'])}` -> `{step['exit_code']}` ({step['log']})")
    (output_dir / "report.md").write_text("\n".join(report) + "\n", encoding="utf-8")


def build(root: Path, timeout: int) -> dict:
    """执行流程 C 编译并写入构建报告。

    Args:
        root (Path): ZUFE-Thesis 模板根目录。
        timeout (int): 单个编译命令的超时时间，单位为秒。

    Returns:
        dict: 构建结果，同时写入 ``build_result.json`` 和 ``report.md``。
    """
    started_at = now_iso()
    thesis_path = root / "workspace/intermediate/thesis.json"
    gate_result = check_flow_b_gate(root, thesis_path)
    gate_evidence = {
        "status": gate_result.get("status"),
        "thesis_json_fingerprint": gate_result.get("thesis_json_fingerprint"),
        "source_docx_fingerprint": gate_result.get("source_docx_fingerprint"),
    }
    if gate_result.get("status") != "passed":
        result = {
            "flow": "C",
            "step": "build",
            "status": "blocked",
            "started_at": started_at,
            "archived": [],
            "steps": [],
            "new_pdf": False,
            "pdf": None,
            "flow_b_gate": {**gate_evidence, "issues": gate_result.get("issues", [])},
            "next_steps": ["返回流程 B，解决门禁问题后再编译。"],
        }
        write_build_reports(root, result)
        return result

    archived = prepare_build(root)
    steps = run_chain(root, timeout)
    pdf = root / "main.pdf"
    new_pdf = pdf.exists()
    failed_steps = [step for step in steps if step["exit_code"] != 0]
    status = (
        "passed" if new_pdf and not failed_steps and len(steps) == len(COMPILE_CHAIN) else "failed"
    )
    result = {
        "flow": "C",
        "step": "build",
        "status": status,
        "started_at": started_at,
        "archived": archived,
        "steps": steps,
        "new_pdf": new_pdf,
        "pdf": "main.pdf" if pdf.exists() else None,
        "flow_b_gate": gate_evidence,
        "next_steps": []
        if status == "passed"
        else [
            "运行 diagnose_build.py 对编译失败分类。",
            "不能把已归档的旧 PDF 当成本轮输出。",
        ],
    }
    write_build_reports(root, result)
    return result


def main() -> int:
    """解析命令行参数并执行流程 C 构建。

    Returns:
        int: 构建通过时返回 0，否则返回 2。
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--timeout", type=int, default=600)
    args = parser.parse_args()
    result = build(Path(args.root).expanduser().resolve(), args.timeout)
    print_json(result)
    return 0 if result["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
