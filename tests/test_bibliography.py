#!/usr/bin/env python3
"""Focused regression tests extracted from the former monolithic suite."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from .support import (
    load_module,
)


def test_qa_flags_bibtex_and_citation_lint_failures():
    qa = load_module("qa")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "chapters").mkdir()
        (root / "workspace/intermediate").mkdir(parents=True)
        (root / "chapters/1_intro.tex").write_text(
            r"正文引用 \cite{known,missing}。",
            encoding="utf-8",
        )
        (root / "chapters/mainbody.tex").write_text(
            "\\input{chapters/1_intro}\n",
            encoding="utf-8",
        )
        (root / "Reference.bib").write_text(
            "@article{known,\n"
            "  title={A}\n"
            "}\n"
            "@book{known,\n"
            "  title={B}\n"
            "}\n"
            "@misc{broken,\n"
            "  title={Broken}\n",
            encoding="utf-8",
        )
        (root / "workspace/intermediate/thesis.json").write_text("{}", encoding="utf-8")

        checks = {check["name"]: check for check in qa.source_quality_checks(root)}
        assert checks["bibtex_duplicate_keys"]["status"] == "failed"
        assert "known" in checks["bibtex_duplicate_keys"]["detail"]
        assert checks["bibtex_braces_balanced"]["status"] == "failed"
        assert checks["citation_keys_defined"]["status"] == "failed"
        assert "missing" in checks["citation_keys_defined"]["detail"]


def test_qa_ignores_stale_chapters_not_referenced_by_current_mainbody():
    qa = load_module("qa")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "chapters").mkdir()
        (root / "workspace/intermediate").mkdir(parents=True)
        (root / "chapters/mainbody.tex").write_text(
            "\\input{chapters/active}\n",
            encoding="utf-8",
        )
        (root / "chapters/active.tex").write_text("当前正文。\n", encoding="utf-8")
        (root / "chapters/stale.tex").write_text(
            "xxxxxxxxxxxx\\label{duplicate}\\label{duplicate}\\ref{missing}\n",
            encoding="utf-8",
        )
        thesis = {"structure": {"chapters": []}, "source_blocks": []}
        (root / "workspace/intermediate/thesis.json").write_text(
            json.dumps(thesis),
            encoding="utf-8",
        )

        source_text = qa.rendered_source_text(root, thesis)
        checks = {check["name"]: check for check in qa.source_quality_checks(root, thesis)}

        assert "当前正文" in source_text
        assert "xxxxxxxxxxxx" not in source_text
        assert checks["source_duplicate_latex_labels"]["status"] == "passed"
        assert checks["source_undefined_latex_refs"]["status"] == "passed"


def test_qa_reads_parenthesized_bibtex_keys():
    qa = load_module("qa")
    assert qa.bibtex_keys("@article(parenthesized, title={A})\n") == ["parenthesized"]


def test_render_bib_preserves_existing_file_until_mapping_is_confirmed():
    render_bib = load_module("render_bib")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "workspace/intermediate").mkdir(parents=True)
        target = root / "Reference.bib"
        target.write_text("% existing bibliography\n", encoding="utf-8")
        empty_bib = root / "workspace/input/references.bib"
        empty_bib.parent.mkdir(parents=True)
        empty_bib.write_text("\n", encoding="utf-8")
        thesis_path = root / "workspace/intermediate/thesis.json"
        thesis_path.write_text(
            json.dumps(
                {
                    "references": [],
                    "source_blocks": [
                        {
                            "id": "r0001",
                            "status": "needs_confirmation",
                            "target_slot": "Reference.bib",
                            "bibtex": "@article{confirmed, title={Confirmed}}",
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        result = render_bib.render(root, thesis_path, input_bib=empty_bib)
        assert result["status"] == "needs_confirmation"
        assert result["target_written"] is False
        assert any("外部 BibTeX 文件为空" in warning for warning in result["warnings"])
        assert target.read_text(encoding="utf-8") == "% existing bibliography\n"

        thesis = json.loads(thesis_path.read_text(encoding="utf-8"))
        thesis["source_blocks"][0]["status"] = "mapped"
        thesis_path.write_text(json.dumps(thesis, ensure_ascii=False), encoding="utf-8")
        result = render_bib.render(root, thesis_path, input_bib=None)
        rendered = json.loads(thesis_path.read_text(encoding="utf-8"))

        assert result["status"] == "passed"
        assert result["target_written"] is True
        assert "@article{confirmed" in target.read_text(encoding="utf-8")
        assert rendered["source_blocks"][0]["status"] == "rendered"
        assert rendered["source_blocks"][0]["render_result"]["path"] == "Reference.bib"


def test_render_bib_does_not_partially_write_when_any_entry_is_unresolved():
    render_bib = load_module("render_bib")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "workspace/intermediate").mkdir(parents=True)
        target = root / "Reference.bib"
        target.write_text("% existing bibliography\n", encoding="utf-8")
        thesis_path = root / "workspace/intermediate/thesis.json"
        thesis_path.write_text(
            json.dumps(
                {
                    "references": [],
                    "source_blocks": [
                        {
                            "id": "r0001",
                            "status": "mapped",
                            "target_slot": "Reference.bib",
                            "bibtex": "@article{confirmed, title={Confirmed}}",
                        },
                        {
                            "id": "r0002",
                            "status": "mapped",
                            "target_slot": "Reference.bib",
                            "text": "尚未转换的参考文献",
                        },
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        result = render_bib.render(root, thesis_path, input_bib=None)
        thesis = json.loads(thesis_path.read_text(encoding="utf-8"))
        assert result["status"] == "needs_confirmation"
        assert result["target_written"] is False
        assert target.read_text(encoding="utf-8") == "% existing bibliography\n"
        assert thesis["source_blocks"][0]["status"] == "mapped"
        assert thesis["source_blocks"][1]["status"] == "needs_confirmation"

        thesis["source_blocks"][1]["status"] = "discarded_with_reason"
        thesis["source_blocks"][1]["discard_reason"] = "用户确认该行不是参考文献"
        thesis_path.write_text(json.dumps(thesis, ensure_ascii=False), encoding="utf-8")
        result = render_bib.render(root, thesis_path, input_bib=None)

        assert result["status"] == "passed"
        assert result["target_written"] is True
        assert "@article{confirmed" in target.read_text(encoding="utf-8")
