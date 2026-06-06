#!/usr/bin/env python3
"""Regression tests for DOCX fidelity issues found in real conversions."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from pathlib import Path

from docx import Document


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = SKILL_DIR / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))


def load_module(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS_DIR / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_import_docx_preserves_superscript_runs():
    import_docx = load_module("import_docx")
    document = Document()
    paragraph = document.add_paragraph()
    paragraph.add_run("引用")
    ref = paragraph.add_run("1")
    ref.font.superscript = True

    runs = import_docx.run_payload(paragraph)
    assert runs == [
        {
            "index": 1,
            "text": "引用",
            "bold": False,
            "italic": False,
            "superscript": False,
            "subscript": False,
            "font_size_pt": None,
        },
        {
            "index": 2,
            "text": "1",
            "bold": False,
            "italic": False,
            "superscript": True,
            "subscript": False,
            "font_size_pt": None,
        },
    ]


def test_render_chapters_preserves_superscript_and_heading_levels():
    render_chapters = load_module("render_chapters")
    assert render_chapters.block_to_latex(
        {"semantic_role": "heading", "level": 2, "text": "二级标题"}
    ) == "\\section{二级标题}"
    assert render_chapters.block_to_latex(
        {
            "source_type": "paragraph",
            "text": "引用1",
            "runs": [
                {"text": "引用", "superscript": False},
                {"text": "1", "superscript": True},
            ],
        }
    ) == "引用\\textsuperscript{1}\n"
    assert render_chapters.block_to_latex(
        {
            "source_type": "paragraph",
            "runs": [
                {"text": '"产品', "superscript": False},
                {"text": '差异化"', "superscript": False},
            ],
        }
    ) == "``产品差异化''\n"


def test_latex_escape_ascii_double_quotes_and_single_scan():
    common = load_module("common")
    assert common.latex_escape('"产品差异化"') == "``产品差异化''"
    assert common.latex_escape('A&B "test"') == r"A\&B ``test''"
    assert common.latex_escape("“中文引号”") == "“中文引号”"
    assert common.latex_escape("student's") == "student's"
    assert common.latex_escape(r"\alpha {x}") == r"\textbackslash{}alpha \{x\}"


def test_render_chapters_table_uses_fixed_font_without_resizebox():
    render_chapters = load_module("render_chapters")
    latex = render_chapters.block_to_latex(
        {
            "source_type": "table",
            "table": {"rows": [["指标", "值"], ["样本", "1"]]},
        }
    )
    assert "\\zihao{5}" in latex
    assert "\\songti" in latex
    assert "\\resizebox" not in latex
    assert "\\begin{tabular}{@{}ll@{}}" in latex


def test_qa_flags_missing_superscript_rendering_and_resizebox():
    qa = load_module("qa")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "chapters").mkdir()
        (root / "workspace/intermediate").mkdir(parents=True)
        (root / "chapters/1_test.tex").write_text(
            "\\resizebox{\\textwidth}{!}{bad table}\n引用1\n",
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
        assert checks["source_superscript_runs_rendered"]["status"] == "warning"


if __name__ == "__main__":
    test_import_docx_preserves_superscript_runs()
    test_render_chapters_preserves_superscript_and_heading_levels()
    test_latex_escape_ascii_double_quotes_and_single_scan()
    test_render_chapters_table_uses_fixed_font_without_resizebox()
    test_qa_flags_missing_superscript_rendering_and_resizebox()
    print("DOCX fidelity regression tests passed")
