#!/usr/bin/env python3
"""检查当前目录是否像 ZUFE-Thesis 模板根目录。"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from common import TEMPLATE_SIGNATURE, item, overall_status, print_json, strip_latex_comment

TEMPLATE_FAMILY = "ZUFE-Thesis"
SUPPORTED_TEMPLATE_VERSIONS = {"1.0.1"}
TEMPLATE_NAME_RE = re.compile(
    r"\\newcommand\s*\{\\zufeTemplateName\}\s*\{([^{}]+)\}",
)
TEMPLATE_VERSION_RE = re.compile(
    r"\\newcommand\s*\{\\zufeTemplateVersion\}\s*\{([^{}]+)\}",
)
TEMPLATE_ANCHORS = {
    "zufe.cls": {
        "class_identity": r"\\ProvidesClass\s*\{zufe\}",
        "subtitle_switch": r"\\newcommand\s*\{\\haveSub\}",
        "graphicx_package": r"\\RequirePackage(?:\[[^\]]*\])?\s*\{graphicx\}",
        "booktabs_package": r"\\RequirePackage(?:\[[^\]]*\])?\s*\{booktabs\}",
        "array_package": r"\\RequirePackage(?:\[[^\]]*\])?\s*\{array\}",
        "hyperref_package": r"\\RequirePackage(?:\[[^\]]*\])?\s*\{hyperref\}",
        "amsmath_package": r"\\RequirePackage(?:\[[^\]]*\])?\s*\{amsmath\}",
        "amssymb_package": r"\\RequirePackage(?:\[[^\]]*\])?\s*\{amssymb\}",
    },
    "main.tex": {
        "basicinfo_input": r"\\input\s*\{chapters/basicinfo\}",
        "mainbody_input": r"\\input\s*\{chapters/mainbody\}",
    },
    "misc/cover.tex": {
        "cover_title_macro": r"\\thesisTitle\b",
        "cover_identity_macro": r"\\yourStudentID\b",
        "cover_mentor_macro": r"\\mentorName\b",
    },
    "misc/abstract.tex": {
        "abstract_cn_macro": r"\\abstractCN\b",
        "keywords_cn_macro": r"\\keywordsCN\b",
        "abstract_en_macro": r"\\abstractEN\b",
        "keywords_en_macro": r"\\keywordsEN\b",
    },
    "misc/reference.tex": {
        "bibliography_output": r"\\printbibliography\b",
    },
}


def tex_source(path: Path) -> str:
    """读取 TeX 源码并移除注释，避免把注释示例误当作兼容接口。"""
    return "\n".join(
        strip_latex_comment(line)
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines()
    )


def command_value(pattern: re.Pattern[str], source: str) -> str | None:
    """读取模板身份命令的字面值；缺失或为空时返回 ``None``。"""
    match = pattern.search(source)
    if match is None:
        return None
    value = match.group(1).strip()
    return value or None


def check_template(root: Path, *, confirm_compatible: bool = False) -> dict:
    """检查模板文件、身份版本和渲染器依赖的语义接口。

    Args:
        root (Path): 待检查的 ZUFE-Thesis 模板根目录。
        confirm_compatible (bool): 用户是否已明确接受无版本或未知版本但接口完整的模板。

    Returns:
        dict: 流程 A 模板兼容性门禁结果，包含缺失文件、接口和版本证据。
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

    family = None
    version = None
    review_reasons = []
    missing_anchors = []
    class_path = root / "zufe.cls"
    if class_path.is_file():
        class_source = tex_source(class_path)
        family = command_value(TEMPLATE_NAME_RE, class_source)
        version = command_value(TEMPLATE_VERSION_RE, class_source)
        if family is None:
            review_reasons.append("模板没有声明 zufeTemplateName，可能是旧版模板。")
        elif family != TEMPLATE_FAMILY:
            checks.append(
                item(
                    "template_family",
                    "blocked",
                    f"模板声明为 {family}，不是受支持的 {TEMPLATE_FAMILY}。",
                )
            )
        else:
            checks.append(item("template_family", "passed", f"模板身份为 {family}。"))

        if version is None:
            review_reasons.append("模板没有声明 zufeTemplateVersion，无法自动确认版本。")
        elif version not in SUPPORTED_TEMPLATE_VERSIONS:
            review_reasons.append(f"模板版本 {version} 尚未列入已验证版本。")
        else:
            checks.append(item("template_version", "passed", f"模板版本 {version} 已验证。"))

    for relative, anchors in TEMPLATE_ANCHORS.items():
        path = root / relative
        if not path.is_file():
            continue
        source = tex_source(path)
        for anchor_name, pattern in anchors.items():
            if re.search(pattern, source):
                checks.append(
                    item(
                        f"{relative}:{anchor_name}",
                        "passed",
                        "已找到渲染器依赖的模板接口。",
                    )
                )
            else:
                missing_anchors.append({"file": relative, "anchor": anchor_name})
                checks.append(
                    item(
                        f"{relative}:{anchor_name}",
                        "blocked",
                        "模板文件存在，但缺少渲染器依赖的接口。",
                    )
                )

    if review_reasons:
        checks.append(
            item(
                "template_compatibility_review",
                "passed" if confirm_compatible else "needs_confirmation",
                (
                    "用户已确认继续使用接口完整但未列入已验证版本的模板。"
                    if confirm_compatible
                    else "模板接口完整，但身份或版本需要用户确认。"
                ),
                reasons=review_reasons,
            )
        )
    status = overall_status(checks)
    return {
        "flow": "A",
        "gate": "template_signature",
        "status": status,
        "root": str(root),
        "missing": missing,
        "compatibility": {
            "expected_family": TEMPLATE_FAMILY,
            "detected_family": family,
            "detected_version": version,
            "verified_versions": sorted(SUPPORTED_TEMPLATE_VERSIONS),
            "missing_anchors": missing_anchors,
            "review_reasons": review_reasons,
            "confirmation_applied": bool(confirm_compatible and review_reasons),
        },
        "checks": checks,
        "user_summary": (
            "当前目录包含与渲染器兼容的 ZUFE-Thesis 模板。"
            if status == "passed"
            else (
                "模板接口完整，但身份或版本需要确认。"
                if status == "needs_confirmation"
                else "当前目录不是完整且兼容的 ZUFE-Thesis 模板根目录。"
            )
        ),
        "next_steps": []
        if status == "passed"
        else (
            [
                "向用户说明模板身份或版本尚未自动验证；确认来源可信且接受兼容性风险后，使用 --confirm-compatible-template 重新检查。",
                "该确认只能接受接口完整的旧版或未知版本，不能绕过缺失文件、错误模板身份或缺失接口。",
            ]
            if status == "needs_confirmation"
            else [
                "请从完整的 ZUFE-Thesis 模板根目录运行本 skill。",
                "原始模板默认获取地址：https://github.com/sqsssq/ZUFE-Thesis",
                "如果 GitHub 无法访问，可在用户确认后改用国内备用链接：https://gitee.com/cwf818/ZUFE-Thesis",
                "如果两个链接都不可用，请要求用户提供模板压缩包、已解压的完整模板目录，或其他用户明确确认的可信获取方式；不要在空目录、本 Skill 仓库或缺失模板签名的目录中继续转换。",
                "继续前需要恢复缺失文件或接口；版本确认不能绕过实际不兼容。",
            ]
        ),
    }


def main() -> int:
    """解析命令行参数并输出模板签名检查结果。

    Returns:
        int: 模板签名完整时返回 0，否则返回 2。
    """
    parser = argparse.ArgumentParser(description="检查 ZUFE-Thesis 模板签名和兼容性接口。")
    parser.add_argument("--root", default=".", help="ZUFE-Thesis 模板根目录")
    parser.add_argument(
        "--confirm-compatible-template",
        action="store_true",
        help="仅在用户已确认后，接受接口完整但无版本或版本未验证的模板。",
    )
    args = parser.parse_args()
    result = check_template(
        Path(args.root).expanduser().resolve(),
        confirm_compatible=args.confirm_compatible_template,
    )
    print_json(result)
    return 0 if result["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
