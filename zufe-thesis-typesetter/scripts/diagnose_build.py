#!/usr/bin/env python3
"""把 LaTeX/Biber 构建失败分类为流程 C 可行动问题。"""

from __future__ import annotations

import argparse
import re
from collections import Counter
from pathlib import Path

from common import block_summary, print_json, write_json

PATTERNS = [
    (
        "environment_issue",
        r"command not found|not recognized|I can't find the format file|"
        r"font[^\r\n]*not found|"
        r"(?:LaTeX Error:\s*)?File\s+[`'\"]?[^`'\"\r\n]+\.sty[`'\"]?\s+not found",
    ),
    (
        "user_input_required",
        r"File\s+[`'\"]?[^`'\"\r\n]+\.(?:png|jpe?g|pdf|eps|svg)[`'\"]?\s+not found|"
        r"Cannot find image",
    ),
    (
        "mechanical_fixable",
        r"Missing \\$ inserted|Misplaced alignment tab character|"
        r"Unicode character .* not set up|Undefined control sequence",
    ),
    (
        "return_to_flow_b",
        r"Runaway argument|Paragraph ended before|"
        r"Extra alignment tab has been changed|Citation '.+' undefined",
    ),
]


def read_log(root: Path, relative: str) -> str:
    """读取构建日志，缺失时返回空字符串。

    Args:
        root (Path): ZUFE-Thesis 模板根目录。
        relative (str): 相对 root 的日志路径。

    Returns:
        str: 日志文本；文件不存在时为空字符串。
    """
    path = root / relative
    return path.read_text(encoding="utf-8", errors="ignore") if path.exists() else ""


def next_step(category: str) -> str:
    """把诊断类别转换为面向 Agent 的下一步动作。

    Args:
        category (str): 诊断类别。

    Returns:
        str: 对应的下一步处理建议。
    """
    return {
        "mechanical_fixable": "只有日志定位到确切文件、路径或字符时，才做机械修复并重编译。",
        "return_to_flow_b": "退回流程 B；流程 C 不修正文档语义或内容归属。",
        "user_input_required": "向用户索要缺失文件，或请求批准后重新链接资源。",
        "environment_issue": "向用户说明环境依赖，获得批准后再安装。",
        "unclassified_failure": "保留日志并人工查看失败命令。",
    }[category]


def classify(text: str) -> list[dict]:
    """根据编译日志文本识别可行动问题。

    Args:
        text (str): 合并后的 LaTeX/Biber 日志文本。

    Returns:
        list[dict]: 已识别问题列表；包含类别、证据片段和下一步。
    """
    issues = []
    seen = set()
    for category, pattern in PATTERNS:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            evidence = match.group(0)[:240]
            identity = (category, evidence)
            if identity in seen:
                continue
            seen.add(identity)
            issues.append(
                {
                    "category": category,
                    "evidence": evidence,
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
    """汇总构建日志并输出流程 C 诊断结果。

    Args:
        root (Path): ZUFE-Thesis 模板根目录。

    Returns:
        dict: 诊断结果，同时写入 ``workspace/output/diagnosis.json``。
    """
    logs = ["main.log", "main.blg"]
    output_dir = root / "workspace/output"
    if output_dir.exists():
        logs.extend(
            sorted(str(path.relative_to(root)) for path in output_dir.glob("build-step-*.log"))
        )
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


def cli_summary(result: dict) -> dict:
    """生成有界的构建诊断 CLI 输出。

    Args:
        result (dict): ``diagnose`` 返回并写入文件的完整诊断结果。

    Returns:
        dict: 分类计数、少量证据示例和完整报告路径。
    """
    raw_issues = result.get("issues", [])
    issues = raw_issues if isinstance(raw_issues, list) else []
    counts = Counter(
        str(issue.get("category") or "unknown") for issue in issues if isinstance(issue, dict)
    )
    return {
        "flow": result.get("flow"),
        "step": result.get("step"),
        "status": result.get("status"),
        "logs_checked": result.get("logs_checked", []),
        "issue_count": len(issues),
        "issue_counts_by_category": dict(sorted(counts.items())),
        "issue_examples": [
            {
                "category": issue.get("category"),
                "evidence": block_summary(str(issue.get("evidence") or ""), 160),
                "next_step": issue.get("next_step"),
            }
            for issue in issues[:5]
            if isinstance(issue, dict)
        ],
        "report_path": "workspace/output/diagnosis.json",
    }


def main() -> int:
    """解析命令行参数并输出构建诊断 JSON。

    Returns:
        int: 没有识别到问题时返回 0，否则返回 2。
    """
    parser = argparse.ArgumentParser(description="汇总 LaTeX/Biber 日志并分类为流程 C 可行动问题。")
    parser.add_argument("--root", default=".", help="ZUFE-Thesis 模板根目录。")
    args = parser.parse_args()
    result = diagnose(Path(args.root).expanduser().resolve())
    print_json(cli_summary(result))
    return 0 if result["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
