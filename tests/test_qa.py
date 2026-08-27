#!/usr/bin/env python3
"""Focused regression tests extracted from the former monolithic suite."""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

from .support import (
    load_module,
)


def test_qa_flags_missing_superscript_rendering_and_resizebox():
    qa = load_module("qa")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "chapters").mkdir()
        (root / "workspace/intermediate").mkdir(parents=True)
        (root / "chapters/1_test.tex").write_text(
            "\\resizebox{\\textwidth}{!}{bad table}\n引用1\n具体可见图2.1。\n",
            encoding="utf-8",
        )
        (root / "chapters/mainbody.tex").write_text(
            "\\input{chapters/1_test}\n",
            encoding="utf-8",
        )
        thesis = {
            "source_blocks": [
                {
                    "id": "p0001",
                    "status": "rendered",
                    "runs": [
                        {"text": "引用", "superscript": False},
                        {"text": "1", "superscript": True},
                    ],
                }
            ]
        }
        (root / "workspace/intermediate/thesis.json").write_text(
            json.dumps(thesis, ensure_ascii=False),
            encoding="utf-8",
        )
        checks = {check["name"]: check for check in qa.source_quality_checks(root)}
        assert checks["source_table_resizebox_textwidth"]["status"] == "warning"
        assert checks["source_manual_cross_reference_numbers"]["status"] == "failed"
        assert "图2.1" in checks["source_manual_cross_reference_numbers"]["detail"]
        assert checks["source_duplicate_latex_labels"]["status"] == "passed"
        assert checks["source_undefined_latex_refs"]["status"] == "passed"
        assert checks["source_superscript_runs_rendered"]["status"] == "warning"


def test_qa_flags_broken_latex_label_refs():
    qa = load_module("qa")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "chapters").mkdir()
        (root / "workspace/intermediate").mkdir(parents=True)
        (root / "chapters/1_test.tex").write_text(
            "正文见图~\\ref{fig:missing}。\n"
            "\\caption{图一}\\label{fig:duplicate}\n"
            "\\caption{图二}\\label{fig:duplicate}\n",
            encoding="utf-8",
        )
        (root / "chapters/mainbody.tex").write_text(
            "\\input{chapters/1_test}\n",
            encoding="utf-8",
        )
        (root / "workspace/intermediate/thesis.json").write_text("{}", encoding="utf-8")

        checks = {check["name"]: check for check in qa.source_quality_checks(root)}
        assert checks["source_duplicate_latex_labels"]["status"] == "failed"
        assert checks["source_duplicate_latex_labels"]["detail"] == "fig:duplicate"
        assert checks["source_undefined_latex_refs"]["status"] == "failed"
        assert checks["source_undefined_latex_refs"]["detail"] == "fig:missing"


def test_qa_placeholder_scan_includes_generated_chapter_files():
    qa = load_module("qa")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "chapters").mkdir()
        (root / "workspace/intermediate").mkdir(parents=True)
        (root / "chapters/basicinfo.tex").write_text("基本信息\n", encoding="utf-8")
        (root / "chapters/mainbody.tex").write_text(
            "\\input{chapters/1_intro}\n",
            encoding="utf-8",
        )
        (root / "chapters/1_intro.tex").write_text(
            "正文里残留 xxxxxxxxxxxx\n",
            encoding="utf-8",
        )
        (root / "workspace/intermediate/thesis.json").write_text("{}", encoding="utf-8")
        result = qa.qa(root)
        checks = {check["name"]: check for check in result["checks"]}
        assert checks[r"placeholder_xxxxxxxxxxxx"]["status"] == "warning"


def test_qa_requires_build_result_for_pdf_freshness():
    qa = load_module("qa")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "chapters").mkdir()
        (root / "workspace/intermediate").mkdir(parents=True)
        (root / "main.pdf").write_bytes(b"%PDF-1.7\n1 0 obj << /Type /Page >> endobj\n")
        (root / "workspace/intermediate/thesis.json").write_text(
            "{}",
            encoding="utf-8",
        )

        result = qa.qa(root)
        checks = {check["name"]: check for check in result["checks"]}
        assert checks["pdf_exists"]["status"] == "passed"
        assert checks["pdf_freshness"]["status"] == "failed"
        assert "build_result.json" in checks["pdf_freshness"]["detail"]
        assert result["status"] == "failed"


def test_qa_reports_malformed_json_inputs_without_crashing():
    qa = load_module("qa")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "workspace/intermediate").mkdir(parents=True)
        (root / "workspace/output").mkdir(parents=True)
        (root / "workspace/intermediate/thesis.json").write_text("{broken", encoding="utf-8")
        (root / "workspace/output/build_result.json").write_text("[broken", encoding="utf-8")

        result = qa.qa(root)
        checks = {check["name"]: check for check in result["checks"]}

        assert result["status"] == "failed"
        assert checks["flow_b_gate_current"]["status"] == "failed"
        assert checks["build_chain_passed"]["status"] == "failed"


def test_qa_unverifiable_page_count_requires_review_instead_of_false_failure():
    qa = load_module("qa")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "workspace/intermediate").mkdir(parents=True)
        (root / "main.pdf").write_bytes(b"%PDF-1.7\ncompressed objects\n")
        (root / "workspace/intermediate/thesis.json").write_text("{}", encoding="utf-8")

        with patch.object(qa, "count_pdf_pages", return_value=0):
            result = qa.qa(root)

        page_check = next(check for check in result["checks"] if check["name"] == "page_count")
        assert page_check["status"] == "warning"
        assert "无法可靠确认" in page_check["detail"]


def test_qa_counts_pages_with_pdfinfo_before_byte_fallback():
    qa = load_module("qa")
    with tempfile.TemporaryDirectory() as tmp:
        pdf = Path(tmp) / "main.pdf"
        pdf.write_bytes(b"%PDF-1.7\ncompressed page objects without plain markers\n")

        completed = subprocess.CompletedProcess(
            args=["pdfinfo", str(pdf)],
            returncode=0,
            stdout="Title: test\nPages:          15\n",
        )
        with (
            patch.object(qa.shutil, "which", return_value="/usr/bin/pdfinfo"),
            patch.object(qa.subprocess, "run", return_value=completed),
        ):
            assert qa.count_pdf_pages(pdf) == 15


def test_qa_tool_timeouts_degrade_without_crashing():
    qa = load_module("qa")
    with tempfile.TemporaryDirectory() as tmp:
        pdf = Path(tmp) / "main.pdf"
        pdf.write_bytes(b"%PDF-1.7\n")
        timeout = subprocess.TimeoutExpired(cmd=["pdf-tool"], timeout=30)

        with (
            patch.object(qa.shutil, "which", return_value="/usr/bin/pdf-tool"),
            patch.object(qa.subprocess, "run", side_effect=timeout),
        ):
            assert qa.extract_text_with_pdftotext(pdf) == ""
            assert qa.count_pdf_pages_with_pdfinfo(pdf) == 0


def test_qa_body_signal_tolerates_malformed_ledger_sections():
    qa = load_module("qa")
    found, detail = qa.body_signal(
        {"structure": [], "source_blocks": {}},
        "正文文本",
    )
    assert found is False
    assert "no audited" in detail


def test_qa_success_requires_manual_visual_review():
    qa = load_module("qa")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "chapters").mkdir()
        (root / "workspace/intermediate").mkdir(parents=True)
        (root / "workspace/output").mkdir(parents=True)
        (root / "workspace/input").mkdir(parents=True)
        (root / "chapters/1_intro.tex").write_text("绪论\n正文内容完整。\n", encoding="utf-8")
        (root / "Reference.bib").write_text("% no cited entries\n", encoding="utf-8")
        (root / "main.pdf").write_bytes(b"%PDF-1.7\n")
        (root / "workspace/output/report.md").write_text("# Build Report\n", encoding="utf-8")
        (root / "workspace/input/metadata.yaml").write_text(
            "english_content_decision: omit\n",
            encoding="utf-8",
        )
        (root / "workspace/output/build_result.json").write_text(
            json.dumps(
                {
                    "status": "passed",
                    "new_pdf": True,
                    "steps": [{"exit_code": 0} for _ in range(4)],
                    "flow_b_gate": {
                        "status": "passed",
                        "thesis_json_fingerprint": {"sha256": "thesis", "size_bytes": 1},
                        "source_docx_fingerprint": {"sha256": "docx", "size_bytes": 1},
                    },
                }
            ),
            encoding="utf-8",
        )
        (root / "workspace/intermediate/thesis.json").write_text(
            json.dumps(
                {
                    "structure": {
                        "chapters": [
                            {
                                "title": "绪论",
                                "file": "chapters/1_intro.tex",
                                "block_ids": [],
                            }
                        ]
                    },
                    "source_blocks": [],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        pdf_text = "目录\n摘要\n绪论\n正文内容完整。\n参考文献\n"
        with (
            patch.object(
                qa,
                "check_flow_b_gate",
                return_value={
                    "status": "passed",
                    "thesis_json_fingerprint": {"sha256": "thesis", "size_bytes": 1},
                    "source_docx_fingerprint": {"sha256": "docx", "size_bytes": 1},
                },
            ),
            patch.object(qa, "extract_text_with_pdftotext", return_value=pdf_text),
            patch.object(qa, "count_pdf_pages", return_value=8),
        ):
            result = qa.qa(root)

        assert result["status"] == "ready_for_manual_review"
        assert result["manual_review_required"] is True
        checks = {check["name"]: check for check in result["checks"]}
        assert checks["signal_abstract_en"]["status"] == "passed"
        assert "明确选择省略" in checks["signal_abstract_en"]["detail"]
        assert (root / "workspace/output/qa_report.md").exists()

        changed_gate = {
            "status": "passed",
            "thesis_json_fingerprint": {"sha256": "changed", "size_bytes": 2},
            "source_docx_fingerprint": {"sha256": "docx", "size_bytes": 1},
        }
        with (
            patch.object(qa, "check_flow_b_gate", return_value=changed_gate),
            patch.object(qa, "extract_text_with_pdftotext", return_value=pdf_text),
            patch.object(qa, "count_pdf_pages", return_value=8),
        ):
            changed_result = qa.qa(root)

        changed_checks = {check["name"]: check for check in changed_result["checks"]}
        assert changed_result["status"] == "failed"
        assert changed_checks["flow_b_gate_current"]["status"] == "passed"
        assert changed_checks["build_flow_b_binding"]["status"] == "failed"
