#!/usr/bin/env python3
"""检查 Python DOCX 与 LaTeX/Biber 环境门禁。"""

from __future__ import annotations

import argparse
import importlib.util
import subprocess
import sys
from pathlib import Path

from common import command_exists, item, overall_status, print_json

REQUIRED_TEX_FILES = {
    "ctexbook.cls": "ctexbook 是 ZUFE 模板的文档类基础。",
    "biblatex.sty": "biblatex 是参考文献编译基础。",
    "gb7714-2015.bbx": "gb7714-2015 是模板使用的国标参考文献样式。",
}

QA_TOOLS = {
    "pdfinfo": "用于读取 PDF 页数；缺失时 QA 会退回较弱的页数判断。",
    "pdftotext": "用于抽取 PDF 文本；缺失时无法完成文本级 QA。",
}

PYTHON_DOCX_INSTALL_HINT = (
    "先短超时尝试：python -m pip install --timeout 8 --retries 1 python-docx；"
    "若失败、超时或无响应，改用中国大陆镜像："
    "python -m pip install --timeout 15 --retries 2 "
    "-i https://pypi.tuna.tsinghua.edu.cn/simple python-docx"
)


def issue(
    code: str,
    target: str,
    layer: str,
    severity: str,
    repair_policy: str,
    next_action: str,
    verify_stage: str,
) -> dict:
    """创建环境 SOP 使用的结构化问题项。

    Args:
        code (str): 稳定问题代码，用于在 SOP 中查表。
        target (str): 缺失或异常的命令、文件或包名。
        layer (str): 问题所在层级，例如 ``python-package`` 或 ``tex-command``。
        severity (str): ``blocking`` 或 ``optional``。
        repair_policy (str): 修复动作的权限策略。
        next_action (str): Agent 下一步动作代号。
        verify_stage (str): 修复后应重新运行的 ``check_env.py`` stage。

    Returns:
        dict: 面向 Agent 的结构化环境问题。
    """
    return {
        "code": code,
        "target": target,
        "layer": layer,
        "severity": severity,
        "repair_policy": repair_policy,
        "next_action": next_action,
        "verify_command": (
            "python zufe-thesis-typesetter/scripts/check_env.py "
            f"--root . --stage {verify_stage}"
        ),
    }


def kpsewhich_exists(filename: str) -> bool:
    """使用 kpsewhich 判断 TeX 文件是否可被当前发行版找到。

    Args:
        filename (str): 需要检查的 TeX 文件名，例如 ``ctexbook.cls``。

    Returns:
        bool: 文件可由 kpsewhich 解析时返回 True。
    """
    if not command_exists("kpsewhich"):
        return False
    process = subprocess.run(
        ["kpsewhich", filename],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    return process.returncode == 0 and bool(process.stdout.strip())


def check(stage: str) -> dict:
    """执行 Python、DOCX 和 LaTeX 环境门禁检查。

    Args:
        stage (str): 检查阶段，可为 ``minimal``、``latex``、``qa`` 或 ``all``。

    Returns:
        dict: 流程 A 环境检查结果，包含每个依赖项的状态和修复提示。
    """
    checks = [item("python", "passed", f"Python 可运行：{sys.executable}")]
    issues = []
    if stage in {"minimal", "all"}:
        if importlib.util.find_spec("docx") is None:
            checks.append(
                item(
                    "python-docx",
                    "blocked",
                    "缺少 python-docx，无法预扫描和抽取 DOCX。",
                    install_hint=PYTHON_DOCX_INSTALL_HINT,
                )
            )
            issues.append(
                issue(
                    "python_docx_missing",
                    "python-docx",
                    "python-package",
                    "blocking",
                    "ask_user_before_install",
                    "install_python_docx",
                    "minimal",
                )
            )
        else:
            checks.append(item("python-docx", "passed", "python-docx 可导入。"))
    if stage in {"latex", "all"}:
        for command in ("xelatex", "biber"):
            if command_exists(command):
                checks.append(item(command, "passed", f"{command} 在 PATH 中。"))
            else:
                checks.append(
                    item(
                        command,
                        "blocked",
                        f"缺少 {command}，流程 C 无法编译。",
                        install_hint="获得用户批准后安装完整 TeX Live 或 MacTeX。",
                    )
                )
                issues.append(
                    issue(
                        "tex_command_missing",
                        command,
                        "tex-command",
                        "blocking",
                        "ask_user_before_install",
                        "install_or_repair_tex_distribution",
                        "latex",
                    )
                )
        for filename, detail in REQUIRED_TEX_FILES.items():
            if kpsewhich_exists(filename):
                checks.append(
                    item(
                        f"tex_package_{filename}",
                        "passed",
                        f"{filename} 可由 kpsewhich 找到。",
                    )
                )
            else:
                checks.append(
                    item(
                        f"tex_package_{filename}",
                        "blocked",
                        f"缺少 {filename}：{detail}",
                        install_hint="获得用户批准后使用 tlmgr 安装对应 TeX Live 包。",
                    )
                )
                issues.append(
                    issue(
                        "tex_core_file_missing",
                        filename,
                        "tex-package",
                        "blocking",
                        "ask_user_before_install",
                        "install_tex_package",
                        "latex",
                    )
                )
    if stage in {"qa", "all"}:
        for command, detail in QA_TOOLS.items():
            if command_exists(command):
                checks.append(item(command, "passed", f"{command} 在 PATH 中。"))
            else:
                checks.append(
                    item(
                        command,
                        "needs_review",
                        f"缺少 {command}：{detail}",
                        install_hint="可选增强工具；不阻止编译，但会降低 QA 确定性。",
                    )
                )
                issues.append(
                    issue(
                        "qa_tool_missing",
                        command,
                        "qa-tool",
                        "optional",
                        "ask_user_before_install",
                        "install_optional_qa_tool",
                        "qa",
                    )
                )
    status = overall_status(checks)
    if status == "passed" and issues:
        status = "needs_review"
    return {
        "flow": "A",
        "gate": f"environment_{stage}",
        "status": status,
        "checks": checks,
        "issues": issues,
        "next_steps": [] if status == "passed" else [
            "向用户说明缺失依赖的影响。",
            "Python 包或 LaTeX 发行版只能在用户明确批准后安装。",
        ],
    }


def main() -> int:
    """解析命令行参数并输出环境检查 JSON。

    Returns:
        int: 环境门禁通过时返回 0，否则返回 2。
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".", help="保持接口一致，当前脚本不读取该目录。")
    parser.add_argument("--stage", choices=["minimal", "latex", "qa", "all"], default="all")
    args = parser.parse_args()
    Path(args.root).expanduser().resolve()
    result = check(args.stage)
    print_json(result)
    return 2 if result["status"] == "blocked" else 0


if __name__ == "__main__":
    raise SystemExit(main())
