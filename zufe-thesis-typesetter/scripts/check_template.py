#!/usr/bin/env python3
"""检查当前目录是否像 ZUFE-Thesis 模板根目录。"""

from __future__ import annotations

import argparse
from pathlib import Path

from common import TEMPLATE_SIGNATURE, item, overall_status, print_json


def check_template(root: Path) -> dict:
    """检查模板根目录是否包含第一版必需签名文件。

    Args:
        root (Path): 待检查的 ZUFE-Thesis 模板根目录。

    Returns:
        dict: 流程 A 模板签名门禁结果，包含缺失文件和用户摘要。
    """
    checks = []
    missing = []
    for relative in TEMPLATE_SIGNATURE:
        path = root / relative
        if path.exists():
            checks.append(item(relative, "passed", "已找到模板签名文件。"))
        else:
            missing.append(relative)
            checks.append(item(relative, "blocked", "缺少必需的模板签名文件。"))
    status = overall_status(checks)
    return {
        "flow": "A",
        "gate": "template_signature",
        "status": status,
        "root": str(root),
        "missing": missing,
        "checks": checks,
        "user_summary": (
            "当前目录像 ZUFE-Thesis 模板根目录。"
            if status == "passed"
            else "当前目录不像完整的 ZUFE-Thesis 模板根目录。"
        ),
        "next_steps": [] if status == "passed" else [
            "请从下载后的 ZUFE-Thesis 模板根目录运行本 skill。",
            "继续前需要恢复或重新下载缺失的签名文件。",
        ],
    }


def main() -> int:
    """解析命令行参数并输出模板签名检查结果。

    Returns:
        int: 模板签名完整时返回 0，否则返回 2。
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".", help="ZUFE-Thesis 模板根目录")
    args = parser.parse_args()
    result = check_template(Path(args.root).expanduser().resolve())
    print_json(result)
    return 0 if result["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
