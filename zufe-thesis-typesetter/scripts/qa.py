#!/usr/bin/env python3
"""流程 C 的 PDF 文本级和源码级 QA。"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
from pathlib import Path

from common import print_json, read_json, write_json


PLACEHOLDER_PATTERNS = [
    r"xxxxxxxxxxxx",
    r"\b20xx\b",
    r"本文……",
    r"摘要的内容要包括",
    r"\bxxx\b",
]

KEY_SIGNALS = {
    "abstract_cn": r"摘\s*要",
    "abstract_en": r"Abstract",
    "references": r"参考文献|References",
}


def extract_text_with_pdftotext(pdf: Path) -> str:
    if shutil.which("pdftotext") is None:
        return ""
    process = subprocess.run(["pdftotext", str(pdf), "-"], text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    return process.stdout or ""


def count_pdf_pages(pdf: Path) -> int:
    data = pdf.read_bytes()
    return len(re.findall(rb"/Type\s*/Page\b", data))


def qa(root: Path) -> dict:
    output_dir = root / "workspace/output"
    output_dir.mkdir(parents=True, exist_ok=True)
    build_result = read_json(output_dir / "build_result.json", default={})
    pdf = root / "main.pdf"
    checks = []
    if pdf.exists():
        checks.append({"name": "pdf_exists", "status": "passed", "detail": "main.pdf 存在。"})
    else:
        checks.append({"name": "pdf_exists", "status": "failed", "detail": "main.pdf 缺失。"})

    new_pdf = bool(build_result.get("new_pdf")) if build_result else pdf.exists()
    checks.append({"name": "pdf_freshness", "status": "passed" if new_pdf else "failed", "detail": f"new_pdf={new_pdf}"})

    page_count = count_pdf_pages(pdf) if pdf.exists() else 0
    checks.append({"name": "page_count", "status": "passed" if page_count > 0 else "failed", "detail": str(page_count)})

    text = extract_text_with_pdftotext(pdf) if pdf.exists() else ""
    checks.append({"name": "pdf_text", "status": "passed" if text.strip() else "warning", "detail": "已抽取 PDF 文本。" if text.strip() else "pdftotext 未能抽取 PDF 文本。"})

    for name, pattern in KEY_SIGNALS.items():
        found = re.search(pattern, text) is not None
        checks.append(
            {
                "name": f"signal_{name}",
                "status": "passed" if found else "warning",
                "detail": f"PDF 文本中{'找到' if found else '未找到'} {pattern!r}。",
            }
        )

    source_text = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for path in [root / "chapters/basicinfo.tex", root / "chapters/mainbody.tex"]
        if path.exists()
    )
    combined = text + "\n" + source_text
    for pattern in PLACEHOLDER_PATTERNS:
        found = re.search(pattern, combined, flags=re.IGNORECASE) is not None
        checks.append({"name": f"placeholder_{pattern}", "status": "warning" if found else "passed", "detail": "found" if found else "not found"})

    logs = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for path in [root / "main.log", root / "main.blg"]
        if path.exists()
    )
    unresolved = re.search(r"undefined references|Citation .* undefined|LaTeX Warning: Reference .* undefined|\?\?", logs + "\n" + text, flags=re.IGNORECASE)
    checks.append({"name": "unresolved_references", "status": "failed" if unresolved else "passed", "detail": unresolved.group(0) if unresolved else "none"})

    failed = [check for check in checks if check["status"] == "failed"]
    warnings = [check for check in checks if check["status"] == "warning"]
    final_status = "failed" if failed else "needs_review" if warnings else "ready_to_submit"
    result = {
        "flow": "C",
        "step": "qa",
        "status": final_status,
        "pdf": "main.pdf" if pdf.exists() else None,
        "page_count": page_count,
        "checks": checks,
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
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    args = parser.parse_args()
    result = qa(Path(args.root).expanduser().resolve())
    print_json(result)
    return 0 if result["status"] != "failed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
