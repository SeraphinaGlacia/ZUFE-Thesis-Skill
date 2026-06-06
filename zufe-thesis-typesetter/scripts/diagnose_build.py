#!/usr/bin/env python3
"""把 LaTeX/Biber 构建失败分类为流程 C 可行动问题。"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from common import print_json, write_json


PATTERNS = [
    ("environment_issue", r"command not found|not recognized|I can't find the format file|font.*not found|File `.+\\.sty' not found"),
    ("user_input_required", r"File `([^']+\\.(png|jpg|jpeg|pdf|eps))' not found|Cannot find image"),
    ("mechanical_fixable", r"Missing \\$ inserted|Misplaced alignment tab character|Unicode character .* not set up|Undefined control sequence"),
    ("return_to_flow_b", r"Runaway argument|Paragraph ended before|Extra alignment tab has been changed|Citation '.+' undefined"),
]


def read_log(root: Path, relative: str) -> str:
    path = root / relative
    return path.read_text(encoding="utf-8", errors="ignore") if path.exists() else ""


def next_step(category: str) -> str:
    return {
        "mechanical_fixable": "只有日志定位到确切文件、路径或字符时，才做机械修复并重编译。",
        "return_to_flow_b": "退回流程 B；流程 C 不修正文档语义或内容归属。",
        "user_input_required": "向用户索要缺失文件，或请求批准后重新链接资源。",
        "environment_issue": "向用户说明环境依赖，获得批准后再安装。",
        "unclassified_failure": "保留日志并人工查看失败命令。",
    }[category]


def classify(text: str) -> list[dict]:
    issues = []
    for category, pattern in PATTERNS:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            issues.append(
                {
                    "category": category,
                    "evidence": match.group(0)[:240],
                    "next_step": next_step(category),
                }
            )
    if not issues and text.strip():
        issues.append(
            {
                "category": "unclassified_failure",
                "evidence": "日志存在，但没有匹配已知模式。",
                "next_step": next_step("unclassified_failure"),
            }
        )
    return issues


def diagnose(root: Path) -> dict:
    logs = ["main.log", "main.blg"]
    output_dir = root / "workspace/output"
    if output_dir.exists():
        logs.extend(sorted(str(path.relative_to(root)) for path in output_dir.glob("build-step-*.log")))
    combined = "\n".join(read_log(root, log) for log in logs)
    issues = classify(combined)
    status = "passed" if not issues else "needs_action"
    result = {
        "flow": "C",
        "step": "diagnose_build",
        "status": status,
        "logs_checked": [log for log in logs if (root / log).exists()],
        "issues": issues,
    }
    write_json(root / "workspace/output/diagnosis.json", result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    args = parser.parse_args()
    result = diagnose(Path(args.root).expanduser().resolve())
    print_json(result)
    return 0 if result["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
