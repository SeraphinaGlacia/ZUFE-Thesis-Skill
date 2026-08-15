#!/usr/bin/env python3
"""检查 Python DOCX 与 LaTeX/Biber 环境门禁。"""

from __future__ import annotations

import argparse
import importlib
import importlib.util
import shlex
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

MINIMUM_PYTHON = (3, 10)
PYTHON_COMMAND = shlex.quote(sys.executable)
PYTHON_DOCX_INSTALL_HINT = (
    f"先短超时尝试：{PYTHON_COMMAND} -m pip install --timeout 8 --retries 1 python-docx；"
    "若失败、超时或无响应，改用中国大陆镜像："
    f"{PYTHON_COMMAND} -m pip install --timeout 15 --retries 2 "
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
            f"{PYTHON_COMMAND} zufe-thesis-typesetter/scripts/check_env.py "
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
        timeout=8,
    )
    return process.returncode == 0 and bool(process.stdout.strip())


def pip_available() -> bool:
    """检查当前 Python 解释器是否能调用 pip。

    Returns:
        bool: ``python -m pip --version`` 成功时返回 True。
    """
    try:
        process = subprocess.run(
            [sys.executable, "-m", "pip", "--version"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=8,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return process.returncode == 0


def python_docx_import_error() -> str | None:
    """验证 python-docx 不仅可发现，而且能够实际导入。

    Returns:
        str | None: 导入成功时为 None，否则为简短错误信息。
    """
    if importlib.util.find_spec("docx") is None:
        return "not_installed"
    try:
        docx_module = importlib.import_module("docx")
    except Exception as exc:
        return f"{type(exc).__name__}: {exc}"
    if not callable(getattr(docx_module, "Document", None)):
        return "docx module does not expose the python-docx Document API"
    return None


def check(stage: str) -> dict:
    """执行 Python、DOCX 和 LaTeX 环境门禁检查。

    Args:
        stage (str): 检查阶段，可为 ``minimal``、``latex``、``qa`` 或 ``all``。

    Returns:
        dict: 流程 A 环境检查结果，包含每个依赖项的状态和修复提示。
    """
    python_supported = sys.version_info >= MINIMUM_PYTHON
    version_text = ".".join(str(part) for part in sys.version_info[:3])
    checks = [
        item(
            "python",
            "passed" if python_supported else "blocked",
            (
                f"Python {version_text} 可运行：{sys.executable}"
                if python_supported
                else f"Python {version_text} 低于最低要求 3.10。"
            ),
        )
    ]
    issues = []
    if not python_supported:
        issues.append(
            issue(
                "python_version_unsupported",
                version_text,
                "python-runtime",
                "blocking",
                "ask_user_before_install",
                "install_supported_python",
                stage,
            )
        )
    if stage in {"minimal", "all"}:
        docx_error = python_docx_import_error()
        if docx_error:
            missing = docx_error == "not_installed"
            checks.append(
                item(
                    "python-docx",
                    "blocked",
                    (
                        "缺少 python-docx，无法预扫描和抽取 DOCX。"
                        if missing
                        else f"python-docx 已安装但导入失败：{docx_error}"
                    ),
                    install_hint=PYTHON_DOCX_INSTALL_HINT,
                )
            )
            issues.append(
                issue(
                    "python_docx_missing" if missing else "python_docx_import_failed",
                    "python-docx",
                    "python-package",
                    "blocking",
                    "ask_user_before_install",
                    "install_python_docx",
                    "minimal",
                )
            )
            if pip_available():
                checks.append(item("pip", "passed", "当前 Python 可以调用 pip。"))
            else:
                checks.append(
                    item(
                        "pip",
                        "blocked",
                        "当前 Python 无法调用 pip，不能按建议安装 python-docx。",
                    )
                )
                issues.append(
                    issue(
                        "pip_unavailable",
                        "pip",
                        "python-package-manager",
                        "blocking",
                        "ask_user_before_install",
                        "repair_python_pip",
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
        if not command_exists("kpsewhich"):
            checks.append(
                item(
                    "kpsewhich",
                    "blocked",
                    "缺少 kpsewhich，无法判断模板核心 TeX 文件是否可用。",
                    install_hint="获得用户批准后修复 TeX 发行版或 PATH。",
                )
            )
            issues.append(
                issue(
                    "tex_command_missing",
                    "kpsewhich",
                    "tex-command",
                    "blocking",
                    "ask_user_before_install",
                    "install_or_repair_tex_distribution",
                    "latex",
                )
            )
        else:
            checks.append(item("kpsewhich", "passed", "kpsewhich 在 PATH 中。"))
            for filename, detail in REQUIRED_TEX_FILES.items():
                try:
                    available = kpsewhich_exists(filename)
                except (OSError, subprocess.TimeoutExpired):
                    available = False
                if available:
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
        "profile": stage,
        "status": status,
        "scope": {
            "checked": {
                "minimal": ["python_version", "python_docx_import"],
                "latex": ["python_version", "xelatex", "biber", "kpsewhich", "tex_core_files"],
                "qa": ["python_version", "pdfinfo", "pdftotext"],
                "all": [
                    "python_version",
                    "python_docx_import",
                    "xelatex",
                    "biber",
                    "kpsewhich",
                    "tex_core_files",
                    "pdfinfo",
                    "pdftotext",
                ],
            }[stage],
            "not_checked": [
                "ZUFE-Thesis 模板签名（使用 check_template.py）",
                "DOCX 可读性和内容结构（使用 prescan_docx.py）",
                "workspace 输入和旧输出保护（使用 prepare_workspace.py）",
            ],
        },
        "checks": checks,
        "issues": issues,
        "next_steps": []
        if status == "passed"
        else [
            "向用户说明缺失依赖的影响。",
            "Python 包或 LaTeX 发行版只能在用户明确批准后安装。",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    """解析命令行参数并输出环境检查 JSON。

    Args:
        argv (list[str] | None): 显式命令行参数；None 时读取系统参数。

    Returns:
        int: 环境门禁通过时返回 0，否则返回 2。
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".", help="保持接口一致，当前脚本不读取该目录。")
    parser.add_argument("--stage", choices=["minimal", "latex", "qa", "all"], default="all")
    args = parser.parse_args(argv)
    Path(args.root).expanduser().resolve()
    result = check(args.stage)
    print_json(result)
    return 2 if result["status"] == "blocked" else 0


if __name__ == "__main__":
    raise SystemExit(main())
