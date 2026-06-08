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

PYTHON_DOCX_INSTALL_HINT = (
    "先短超时尝试：python -m pip install --timeout 8 --retries 1 python-docx；"
    "若失败、超时或无响应，改用中国大陆镜像："
    "python -m pip install --timeout 15 --retries 2 "
    "-i https://pypi.tuna.tsinghua.edu.cn/simple python-docx"
)


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
        stage (str): 检查阶段，可为 ``minimal``、``latex`` 或 ``all``。

    Returns:
        dict: 流程 A 环境检查结果，包含每个依赖项的状态和修复提示。
    """
    checks = [item("python", "passed", f"Python 可运行：{sys.executable}")]
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
    status = overall_status(checks)
    return {
        "flow": "A",
        "gate": f"environment_{stage}",
        "status": status,
        "checks": checks,
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
    parser.add_argument("--stage", choices=["minimal", "latex", "all"], default="all")
    args = parser.parse_args()
    Path(args.root).expanduser().resolve()
    result = check(args.stage)
    print_json(result)
    return 0 if result["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
