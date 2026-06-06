#!/usr/bin/env python3
"""流程 C：归档旧产物并运行固定 XeLaTeX/Biber 编译链。"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import time
from pathlib import Path

from common import BUILD_TEMP_FILES, archive_path, now_iso, print_json, rel, write_json


COMPILE_CHAIN = [
    ["xelatex", "main.tex"],
    ["biber", "main"],
    ["xelatex", "main.tex"],
    ["xelatex", "main.tex"],
]


def move_if_exists(source: Path, target: Path) -> str | None:
    if not source.exists():
        return None
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(target))
    return str(target)


def prepare_build(root: Path) -> list[dict]:
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
            output = (exc.stdout or "") + f"\ncommand timed out after {timeout} seconds: {' '.join(command)}\n"
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


def build(root: Path, timeout: int) -> dict:
    start_time = time.time()
    archived = prepare_build(root)
    steps = run_chain(root, timeout)
    pdf = root / "main.pdf"
    new_pdf = pdf.exists() and pdf.stat().st_mtime >= start_time
    failed_steps = [step for step in steps if step["exit_code"] != 0]
    status = "passed" if new_pdf and not failed_steps and len(steps) == len(COMPILE_CHAIN) else "failed"
    result = {
        "flow": "C",
        "step": "build",
        "status": status,
        "started_at": now_iso(),
        "archived": archived,
        "steps": steps,
        "new_pdf": new_pdf,
        "pdf": "main.pdf" if pdf.exists() else None,
        "next_steps": [] if status == "passed" else [
            "运行 diagnose_build.py 对编译失败分类。",
            "不能把已归档的旧 PDF 当成本轮输出。",
        ],
    }
    output_dir = root / "workspace/output"
    write_json(output_dir / "build_result.json", result)
    report = [
        "# Build Report",
        "",
        f"- Status: `{status}`",
        f"- New PDF: `{new_pdf}`",
        f"- PDF: `{result['pdf']}`",
        "",
        "## Steps",
        "",
    ]
    for step in steps:
        report.append(f"- `{' '.join(step['command'])}` -> `{step['exit_code']}` ({step['log']})")
    (output_dir / "report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--timeout", type=int, default=600)
    args = parser.parse_args()
    result = build(Path(args.root).expanduser().resolve(), args.timeout)
    print_json(result)
    return 0 if result["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
