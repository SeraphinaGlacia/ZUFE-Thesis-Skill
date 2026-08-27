#!/usr/bin/env python3
"""Focused regression tests extracted from the former monolithic suite."""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

from .support import (
    load_module,
)


def test_flow_b_gate_requires_explicit_float_and_reference_contracts():
    check_flow_b_gate = load_module("check_flow_b_gate")
    issues = check_flow_b_gate.ledger_schema_issues(
        {
            "source_blocks": [
                {
                    "id": "img0001",
                    "source_type": "image",
                    "status": "mapped",
                    "label": "fig:missing-caption",
                },
                {
                    "id": "p0001",
                    "source_type": "paragraph",
                    "candidate_type": "body",
                    "status": "mapped",
                    "reference_rewrites": [
                        {
                            "source_text": "表1.2",
                            "target_label": "tab:sample-info",
                        }
                    ],
                },
            ]
        }
    )

    assert {issue["check"] for issue in issues} == {
        "labeled_float_caption",
        "reference_rewrite_fields",
    }


def test_flow_b_gate_blocks_unconfirmed_unsupported_features():
    check_flow_b_gate = load_module("check_flow_b_gate")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "chapters").mkdir()
        (root / "workspace/intermediate").mkdir(parents=True)
        (root / "chapters/basicinfo.tex").write_text("基本信息\n", encoding="utf-8")
        (root / "chapters/mainbody.tex").write_text("\\input{chapters/1_intro}\n", encoding="utf-8")
        (root / "chapters/1_intro.tex").write_text("正文\n", encoding="utf-8")
        (root / "Reference.bib").write_text("% empty\n", encoding="utf-8")
        thesis_path = root / "workspace/intermediate/thesis.json"
        thesis_path.write_text(
            json.dumps(
                {
                    "counts": {"total_source_blocks": 0},
                    "source_blocks": [],
                    "unsupported_features": [
                        {
                            "type": "equation_omml",
                            "count": 1,
                            "severity": "high",
                            "status": "needs_confirmation",
                            "locations": [{"part": "word/document.xml", "count": 1}],
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        result = check_flow_b_gate.check(root, thesis_path)
        assert result["status"] == "blocked"
        assert any(
            issue["check"] == "unsupported_feature_confirmation" for issue in result["issues"]
        )


def test_flow_b_gate_blocks_manual_figure_reference_numbers():
    check_flow_b_gate = load_module("check_flow_b_gate")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "chapters").mkdir()
        (root / "workspace/intermediate").mkdir(parents=True)
        (root / "chapters/basicinfo.tex").write_text("基本信息\n", encoding="utf-8")
        (root / "chapters/mainbody.tex").write_text("\\input{chapters/1_intro}\n", encoding="utf-8")
        (root / "chapters/1_intro.tex").write_text(
            "正文具体可见图2.1。\n"
            "\\begin{figure}[htbp]\n"
            "\\caption{年龄分布图}\n"
            "\\label{fig:age-distribution}\n"
            "\\end{figure}\n",
            encoding="utf-8",
        )
        (root / "Reference.bib").write_text("% empty\n", encoding="utf-8")
        thesis_path = root / "workspace/intermediate/thesis.json"
        thesis_path.write_text(
            json.dumps(
                {
                    "counts": {"total_source_blocks": 1},
                    "unsupported_features": [],
                    "source_blocks": [
                        {
                            "id": "p0001",
                            "status": "rendered",
                            "text": "正文具体可见图2.1。",
                            "target_slot": "chapters/1_intro.tex",
                            "render_result": {
                                "path": "chapters/1_intro.tex",
                                "kind": "chapter_tex",
                            },
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        result = check_flow_b_gate.check(root, thesis_path)
        assert result["status"] == "blocked"
        issue = next(
            issue
            for issue in result["issues"]
            if issue["check"] == "manual_cross_reference_numbers"
        )
        assert "图2.1" in issue["examples"][0]


def test_flow_b_gate_blocks_broken_latex_label_refs():
    check_flow_b_gate = load_module("check_flow_b_gate")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "chapters").mkdir()
        (root / "workspace/intermediate").mkdir(parents=True)
        (root / "chapters/basicinfo.tex").write_text("基本信息\n", encoding="utf-8")
        (root / "chapters/mainbody.tex").write_text("\\input{chapters/1_intro}\n", encoding="utf-8")
        (root / "chapters/1_intro.tex").write_text(
            "正文具体可见图~\\ref{fig:missing}。\n"
            "\\begin{figure}[htbp]\n"
            "\\caption{年龄分布图}\n"
            "\\label{fig:duplicate}\n"
            "\\end{figure}\n"
            "\\begin{figure}[htbp]\n"
            "\\caption{年龄分布图副本}\n"
            "\\label{fig:duplicate}\n"
            "\\end{figure}\n",
            encoding="utf-8",
        )
        (root / "Reference.bib").write_text("% empty\n", encoding="utf-8")
        thesis_path = root / "workspace/intermediate/thesis.json"
        thesis_path.write_text(
            json.dumps(
                {
                    "counts": {"total_source_blocks": 1},
                    "unsupported_features": [],
                    "source_blocks": [
                        {
                            "id": "p0001",
                            "status": "rendered",
                            "text": "正文具体可见图2.1。",
                            "target_slot": "chapters/1_intro.tex",
                            "render_result": {
                                "path": "chapters/1_intro.tex",
                                "kind": "chapter_tex",
                            },
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        result = check_flow_b_gate.check(root, thesis_path)
        assert result["status"] == "blocked"
        issues = {issue["check"]: issue for issue in result["issues"]}
        assert issues["duplicate_latex_labels"]["labels"] == ["fig:duplicate"]
        assert issues["undefined_latex_refs"]["labels"] == ["fig:missing"]


def test_high_volume_cli_summaries_are_bounded_without_truncating_results():
    check_flow_b_gate = load_module("check_flow_b_gate")
    prescan_docx = load_module("prescan_docx")
    issues = [
        {"check": "source_block_state", "block_id": f"p{index:04d}", "detail": "待处理"}
        for index in range(50)
    ]
    gate_result = {
        "flow": "B",
        "gate": "completion",
        "status": "blocked",
        "issues": issues,
    }
    gate_summary = check_flow_b_gate.cli_summary(gate_result, "workspace/output/flow_b_gate.json")
    preview = [
        {"index": index, "text": f"段落 {index}", "candidate_type": "body"} for index in range(80)
    ]
    prescan_result = {
        "flow": "A",
        "gate": "word_prescan",
        "status": "passed",
        "metadata_candidates": {"thesis_title_cn": "题" * 1000},
        "structure_preview": preview,
    }
    prescan_summary = prescan_docx.cli_summary(
        prescan_result, "workspace/intermediate/prescan.json"
    )

    assert gate_summary["issue_count"] == 50
    assert len(gate_summary["issue_examples"]) == 5
    assert len(gate_result["issues"]) == 50
    assert prescan_summary["structure_preview_count"] == 80
    assert len(prescan_summary["structure_preview_examples"]) == 10
    assert len(prescan_summary["metadata_candidates"]["thesis_title_cn"]) == 240
    assert len(prescan_result["structure_preview"]) == 80
    assert len(prescan_result["metadata_candidates"]["thesis_title_cn"]) == 1000


def test_flow_b_gate_cli_writes_full_report_and_prints_its_path():
    check_flow_b_gate = load_module("check_flow_b_gate")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        stdout = io.StringIO()
        argv = ["check_flow_b_gate.py", "--root", str(root)]

        with patch.object(sys, "argv", argv), contextlib.redirect_stdout(stdout):
            exit_code = check_flow_b_gate.main()

        summary = json.loads(stdout.getvalue())
        report_path = root / summary["report_path"]
        report = json.loads(report_path.read_text(encoding="utf-8"))
        assert exit_code == 2
        assert summary["status"] == "blocked"
        assert summary["issue_count"] == len(report["issues"])
        assert report["issues"][0]["check"] == "thesis_json_missing"


def test_prescan_cli_refuses_to_overwrite_the_formal_ledger():
    prescan_docx = load_module("prescan_docx")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        stdout = io.StringIO()
        argv = [
            "prescan_docx.py",
            "--root",
            str(root),
            "--output",
            "workspace/intermediate/thesis.json",
        ]

        with patch.object(sys, "argv", argv), contextlib.redirect_stdout(stdout):
            exit_code = prescan_docx.main()

        payload = json.loads(stdout.getvalue())
        assert exit_code == 2
        assert payload["error_code"] == "prescan_cannot_overwrite_thesis_json"
        assert not (root / "workspace/intermediate/thesis.json").exists()


def test_ledger_queries_are_paginated_and_preserve_heading_context():
    ledger = load_module("ledger")
    blocks = [
        {
            "id": f"p{index:04d}",
            "order": index,
            "source_type": "paragraph",
            "candidate_type": "heading" if index == 3 else "body",
            "semantic_role": "heading" if index == 3 else None,
            "level": 1 if index == 3 else None,
            "render_title": "绪论" if index == 3 else None,
            "text": "第一章 绪论" if index == 3 else f"正文段落 {index}",
            "status": "mapped" if index == 3 else "needs_confirmation",
            "evidence": {"style": "Heading 1" if index == 3 else "Normal"},
        }
        for index in range(1, 26)
    ]
    thesis = {
        "schema_version": "1.0",
        "source_blocks": blocks,
        "structure": {"chapters": []},
        "unsupported_features": [],
    }

    summary = ledger.summary(thesis, "workspace/intermediate/thesis.json")
    page = ledger.pending(thesis, offset=5, limit=4)
    outline = ledger.outline(thesis, offset=0, limit=20)
    block = ledger.get_block(thesis, "p0003")

    assert summary["source_block_count"] == 25
    assert summary["heading_candidate_count"] == 1
    assert page["returned"] == 4
    assert page["has_more"] is True
    assert len(page["items"]) == 4
    assert outline["total"] == 1
    assert outline["items"][0]["text"] == "第一章 绪论"
    assert outline["items"][0]["render_title"] == "绪论"
    assert outline["items"][0]["evidence"]["style"] == "Heading 1"
    assert outline["items"][0]["previous"]["id"] == "p0002"
    assert outline["items"][0]["next"]["id"] == "p0004"
    assert block["block"]["text"] == "第一章 绪论"


def test_ledger_cli_blocks_malformed_source_blocks():
    ledger = load_module("ledger")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        thesis_path = root / "workspace/intermediate/thesis.json"
        thesis_path.parent.mkdir(parents=True)
        thesis_path.write_text(
            json.dumps({"source_blocks": [{"id": "p0001"}, "invalid"]}, ensure_ascii=False),
            encoding="utf-8",
        )
        stdout = io.StringIO()
        argv = ["ledger.py", "--root", str(root), "summary"]

        with patch.object(sys, "argv", argv), contextlib.redirect_stdout(stdout):
            exit_code = ledger.main()

        result = json.loads(stdout.getvalue())
        assert exit_code == 2
        assert result["status"] == "blocked"
        assert result["error_code"] == "source_blocks_invalid"


def test_flow_b_gate_validates_ledger_identity_and_chapter_ownership():
    check_flow_b_gate = load_module("check_flow_b_gate")
    thesis = {
        "counts": {"total_source_blocks": 2, "paragraphs": 2},
        "source_blocks": [
            {
                "id": "p0001",
                "source_type": "paragraph",
                "status": "mapped",
                "target_slot": "chapters/1_intro.tex",
            },
            {
                "id": "p0001",
                "source_type": "paragraph",
                "status": "unknown",
                "target_slot": "chapters/2_method.tex",
            },
        ],
        "structure": {
            "chapters": [
                {
                    "title": "保留文件误用",
                    "file": "chapters/mainbody.tex",
                    "block_ids": ["p0001", "missing"],
                },
                {
                    "title": "重复归属",
                    "file": "chapters/2_method.tex",
                    "block_ids": ["p0001"],
                },
            ]
        },
    }

    issue_names = {issue["check"] for issue in check_flow_b_gate.ledger_schema_issues(thesis)}
    assert "duplicate_source_block_id" in issue_names
    assert "source_block_status_value" in issue_names
    assert "chapter_file" in issue_names
    assert "chapter_unknown_block" in issue_names
    assert "chapter_duplicate_block_reference" in issue_names
    assert "chapter_target_mismatch" in issue_names


def test_flow_b_gate_reports_malformed_source_block_without_crashing():
    check_flow_b_gate = load_module("check_flow_b_gate")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "workspace/intermediate").mkdir(parents=True)
        thesis_path = root / "workspace/intermediate/thesis.json"
        thesis_path.write_text(
            json.dumps(
                {
                    "counts": {"total_source_blocks": 2},
                    "source_blocks": [
                        None,
                        {
                            "id": "p0001",
                            "status": [],
                            "source_type": {},
                            "text": "畸形状态源块",
                        },
                    ],
                    "structure": {"chapters": []},
                    "unsupported_features": [{"type": "field_code", "count": 1, "status": []}],
                }
            ),
            encoding="utf-8",
        )

        result = check_flow_b_gate.check(root, thesis_path)

        assert result["status"] == "blocked"
        issue_names = {issue["check"] for issue in result["issues"]}
        assert "source_block_type" in issue_names
        assert "source_block_status_value" in issue_names
        assert "unsupported_feature_confirmation" in issue_names


def test_flow_b_gate_rechecks_source_docx_fingerprint_before_flow_c():
    check_flow_b_gate = load_module("check_flow_b_gate")
    common = load_module("common")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "chapters").mkdir()
        (root / "workspace/input").mkdir(parents=True)
        (root / "workspace/intermediate").mkdir(parents=True)
        source = root / "workspace/input/thesis.docx"
        source.write_bytes(b"source version one")
        (root / "chapters/basicinfo.tex").write_text("基本信息\n", encoding="utf-8")
        (root / "chapters/mainbody.tex").write_text(
            "\\input{chapters/1_intro}\n",
            encoding="utf-8",
        )
        (root / "chapters/1_intro.tex").write_text("正文\n", encoding="utf-8")
        (root / "Reference.bib").write_text("% empty\n", encoding="utf-8")
        thesis_path = root / "workspace/intermediate/thesis.json"
        thesis_path.write_text(
            json.dumps(
                {
                    "source_docx": "workspace/input/thesis.docx",
                    "source_docx_fingerprint": common.file_fingerprint(source),
                    "counts": {"total_source_blocks": 0},
                    "source_blocks": [],
                    "structure": {"chapters": []},
                    "unsupported_features": [],
                }
            ),
            encoding="utf-8",
        )

        assert check_flow_b_gate.check(root, thesis_path)["status"] == "passed"

        source.write_bytes(b"source version two")
        result = check_flow_b_gate.check(root, thesis_path)
        assert result["status"] == "blocked"
        assert "source_docx_changed" in {issue["check"] for issue in result["issues"]}
