#!/usr/bin/env python3
"""Focused regression tests extracted from the former monolithic suite."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from .support import (
    TINY_PNG,
    load_module,
)


def test_heading_uses_explicit_agent_title_and_level():
    render_chapters = load_module("render_chapters")
    assert (
        render_chapters.block_to_latex(
            {
                "semantic_role": "heading",
                "level": 1,
                "render_title": "一级标题",
                "text": "第一章 一级标题",
            }
        )
        == "\\chapter{一级标题}"
    )
    assert (
        render_chapters.block_to_latex(
            {
                "semantic_role": "heading",
                "level": 2,
                "render_title": "二级标题",
                "text": "1.1 二级标题",
            }
        )
        == "\\section{二级标题}"
    )
    assert (
        render_chapters.block_to_latex(
            {
                "semantic_role": "heading",
                "level": 3,
                "render_title": "3.14 是圆周率吗？",
                "text": "3.14 是圆周率吗？",
            }
        )
        == "\\subsection{3.14 是圆周率吗？}"
    )
    assert (
        render_chapters.block_to_latex(
            {
                "semantic_role": "heading",
                "level": 3,
                "render_title": "三级标题",
                "text": "（一）三级标题",
            }
        )
        == "\\subsection{三级标题}"
    )


def test_render_chapters_preserves_superscript_and_heading_levels():
    render_chapters = load_module("render_chapters")
    assert (
        render_chapters.block_to_latex(
            {
                "semantic_role": "heading",
                "level": 2,
                "render_title": "二级标题",
                "text": "1.1 二级标题",
            }
        )
        == "\\section{二级标题}"
    )
    assert (
        render_chapters.block_to_latex(
            {
                "source_type": "paragraph",
                "text": "引用1",
                "runs": [
                    {"text": "引用", "superscript": False},
                    {"text": "1", "superscript": True},
                ],
            }
        )
        == "引用\\textsuperscript{1}\n"
    )
    assert (
        render_chapters.block_to_latex(
            {
                "source_type": "paragraph",
                "runs": [
                    {"text": '"产品', "superscript": False},
                    {"text": '差异化"', "superscript": False},
                ],
            }
        )
        == "``产品差异化''\n"
    )


def test_render_chapters_uses_explicit_agent_titles_without_reinterpreting_numbers():
    render_chapters = load_module("render_chapters")

    assert (
        render_chapters.block_to_latex(
            {
                "semantic_role": "heading",
                "level": 1,
                "render_title": "绪论",
                "text": "第一章 绪论",
            }
        )
        == "\\chapter{绪论}"
    )
    assert (
        render_chapters.block_to_latex(
            {
                "semantic_role": "heading",
                "level": 1,
                "render_title": "3.14 是圆周率吗？",
                "text": "3.14 是圆周率吗？",
            }
        )
        == "\\chapter{3.14 是圆周率吗？}"
    )
    assert (
        render_chapters.block_to_latex(
            {
                "semantic_role": "heading",
                "level": 2,
                "render_title": "一、二线城市消费差异",
                "text": "一、二线城市消费差异",
            }
        )
        == "\\section{一、二线城市消费差异}"
    )
    assert (
        render_chapters.block_to_latex(
            {
                "semantic_role": "heading",
                "level": 3,
                "render_title": "研究问题",
                "text": "（一）研究问题",
            }
        )
        == "\\subsection{研究问题}"
    )
    assert (
        render_chapters.block_to_latex(
            {
                "source_type": "paragraph",
                "text": "一、这里是正文列表，不是标题。",
            }
        )
        == "一、这里是正文列表，不是标题。\n"
    )


def test_heading_semantics_require_explicit_agent_decisions():
    common = load_module("common")
    assert common.classify_text("一、研究设计", "Normal") == ("body", 0.35)
    assert common.classify_text("第一章 绪论", "Normal") == ("heading", 0.8)
    assert common.classify_text("2024 年行业报告", "Normal") == ("body", 0.35)
    assert common.classify_text("1. 参考文献条目", "Normal") == ("reference_or_list", 0.45)
    issues = common.heading_contract_issues(
        [
            {
                "id": "p0001",
                "candidate_type": "heading",
                "status": "mapped",
                "text": "第一章 绪论",
            },
            {
                "id": "p0002",
                "semantic_role": "heading",
                "level": 1,
                "status": "mapped",
                "text": "1.2 研究背景",
            },
            {
                "id": "p0003",
                "semantic_role": "heading",
                "level": 2,
                "render_title": "研究设计",
                "status": "mapped",
                "text": "一、研究设计",
            },
            {
                "id": "p0004",
                "candidate_type": "heading",
                "semantic_role": "body",
                "status": "mapped",
                "text": "1. 正文列表",
            },
            {
                "id": "p0005",
                "candidate_type": "body",
                "semantic_role": "body",
                "level": 2,
                "status": "mapped",
                "text": "普通正文",
            },
            {
                "id": "p0006",
                "candidate_type": "heading",
                "semantic_role": "heading",
                "level": True,
                "render_title": "无效布尔层级",
                "status": "mapped",
                "text": "无效布尔层级",
            },
            {
                "id": "p0007",
                "candidate_type": "heading",
                "semantic_role": "heading",
                "level": 1,
                "render_title": "",
                "status": "mapped",
                "text": "第一章",
            },
        ]
    )

    issue_names = {issue["check"] for issue in issues}
    assert issue_names == {
        "heading_semantic_role",
        "heading_semantic_role_conflict",
        "heading_semantic_level",
        "heading_render_title",
    }
    assert {issue["block_id"] for issue in issues} == {
        "p0001",
        "p0002",
        "p0005",
        "p0006",
        "p0007",
    }


def test_render_chapters_blocks_unconfirmed_heading_semantics_before_writing():
    render_chapters = load_module("render_chapters")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "chapters").mkdir()
        (root / "workspace/intermediate").mkdir(parents=True)
        thesis_path = root / "workspace/intermediate/thesis.json"
        thesis_path.write_text(
            json.dumps(
                {
                    "source_blocks": [
                        {
                            "id": "p0001",
                            "source_type": "paragraph",
                            "candidate_type": "heading",
                            "semantic_role": "heading",
                            "level": 1,
                            "text": "第一章 绪论",
                            "status": "mapped",
                            "target_slot": "chapters/1_intro.tex",
                        }
                    ],
                    "structure": {
                        "chapters": [
                            {
                                "title": "绪论",
                                "file": "chapters/1_intro.tex",
                                "block_ids": ["p0001"],
                            }
                        ]
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        result = render_chapters.render(root, thesis_path, allow_incomplete=False)

        assert result["status"] == "blocked"
        assert "heading_render_title" in {issue["check"] for issue in result["issues"]}
        assert not (root / "chapters/1_intro.tex").exists()


def test_render_chapters_outputs_labels_and_reference_rewrites():
    render_chapters = load_module("render_chapters")
    figure_latex = render_chapters.block_to_latex(
        {
            "source_type": "image",
            "asset_output": "Images/word_media/image3.png",
            "caption": "年龄分布图",
            "label": "fig:age-distribution",
        }
    )
    assert r"\caption{年龄分布图}" in figure_latex
    assert r"\label{fig:age-distribution}" in figure_latex

    uncaptioned_figure_latex = render_chapters.block_to_latex(
        {
            "source_type": "image",
            "asset_output": "Images/word_media/image4.png",
            "summary": "word/media/image4.png",
        }
    )
    assert r"\caption{" not in uncaptioned_figure_latex
    assert "word/media/image4.png" not in uncaptioned_figure_latex

    table_latex = render_chapters.block_to_latex(
        {
            "source_type": "table",
            "caption": "样本信息",
            "label": "tab:sample-info",
            "table": {"rows": [["指标", "值"], ["样本", "205"]]},
        }
    )
    assert r"\caption{样本信息}" in table_latex
    assert r"\label{tab:sample-info}" in table_latex

    paragraph_latex = render_chapters.block_to_latex(
        {
            "source_type": "paragraph",
            "text": "具体可见图2.1和表 1.2。",
            "reference_rewrites": [
                {
                    "source_text": "图2.1",
                    "target_kind": "figure",
                    "target_label": "fig:age-distribution",
                },
                {
                    "source_text": "表 1.2",
                    "target_kind": "table",
                    "target_label": "tab:sample-info",
                },
            ],
        }
    )
    assert "图2.1" not in paragraph_latex
    assert "表 1.2" not in paragraph_latex
    assert r"图~\ref{fig:age-distribution}" in paragraph_latex
    assert r"表~\ref{tab:sample-info}" in paragraph_latex

    overlapping_latex = render_chapters.block_to_latex(
        {
            "source_type": "paragraph",
            "text": "见图2.1、图2.10。",
            "reference_rewrites": [
                {
                    "source_text": "图2.1",
                    "target_kind": "figure",
                    "target_label": "fig:short",
                },
                {
                    "source_text": "图2.10",
                    "target_kind": "figure",
                    "target_label": "fig:long",
                },
            ],
        }
    )
    assert r"图~\ref{fig:short}、图~\ref{fig:long}" in overlapping_latex
    assert r"\ref{fig:short}0" not in overlapping_latex

    unresolved_kind_latex = render_chapters.block_to_latex(
        {
            "source_type": "paragraph",
            "text": "具体可见表1.2。",
            "reference_rewrites": [
                {
                    "source_text": "表1.2",
                    "target_label": "tab:sample-info",
                }
            ],
        }
    )
    assert "表1.2" in unresolved_kind_latex
    assert r"图~\ref{tab:sample-info}" not in unresolved_kind_latex


def test_latex_escape_ascii_double_quotes_and_single_scan():
    common = load_module("common")
    assert common.latex_escape('"产品差异化"') == "``产品差异化''"
    assert common.latex_escape('A&B "test"') == r"A\&B ``test''"
    assert common.latex_escape("“中文引号”") == "“中文引号”"
    assert common.latex_escape("student's") == "student's"
    assert common.latex_escape(r"\alpha {x}") == r"\textbackslash{}alpha \{x\}"


def test_render_chapters_blocks_prefix_path_escape():
    render_chapters = load_module("render_chapters")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "chapters").mkdir()
        (root / "workspace/intermediate").mkdir(parents=True)
        thesis_path = root / "workspace/intermediate/thesis.json"
        thesis_path.write_text(
            json.dumps(
                {
                    "source_blocks": [
                        {
                            "id": "p0001",
                            "status": "mapped",
                            "text": "越界正文",
                            "target_slot": "chapters_evil/escape.tex",
                        }
                    ],
                    "structure": {
                        "chapters": [
                            {
                                "title": "bad",
                                "file": "chapters_evil/escape.tex",
                                "block_ids": ["p0001"],
                            }
                        ]
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        result = render_chapters.render(root, thesis_path, allow_incomplete=False)
        assert result["status"] == "blocked"
        assert not (root / "chapters_evil/escape.tex").exists()


def test_render_chapters_blocks_duplicate_chapter_targets_before_writing():
    render_chapters = load_module("render_chapters")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "chapters").mkdir()
        (root / "workspace/intermediate").mkdir(parents=True)
        thesis_path = root / "workspace/intermediate/thesis.json"
        thesis_path.write_text(
            json.dumps(
                {
                    "source_blocks": [
                        {
                            "id": "p0001",
                            "status": "mapped",
                            "source_type": "paragraph",
                            "text": "第一段",
                            "target_slot": "chapters/1_intro.tex",
                        },
                        {
                            "id": "p0002",
                            "status": "mapped",
                            "source_type": "paragraph",
                            "text": "第二段",
                            "target_slot": "chapters/1_intro.tex",
                        },
                    ],
                    "structure": {
                        "chapters": [
                            {
                                "title": "第一章",
                                "file": "chapters/1_intro.tex",
                                "block_ids": ["p0001"],
                            },
                            {
                                "title": "重复目标",
                                "file": "chapters/./1_intro.tex",
                                "block_ids": ["p0002"],
                            },
                        ]
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        result = render_chapters.render(root, thesis_path, allow_incomplete=False)

        assert result["status"] == "blocked"
        assert "duplicate_chapter_file" in {issue["check"] for issue in result["issues"]}
        assert not (root / "chapters/1_intro.tex").exists()


def test_render_chapters_requires_an_exported_existing_image_asset():
    render_chapters = load_module("render_chapters")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "chapters").mkdir()
        (root / "workspace/intermediate").mkdir(parents=True)
        thesis_path = root / "workspace/intermediate/thesis.json"
        thesis = {
            "source_blocks": [
                {
                    "id": "i0001",
                    "status": "mapped",
                    "source_type": "image",
                    "summary": "示例图片",
                    "target_slot": "chapters/1_intro.tex",
                }
            ],
            "structure": {
                "chapters": [
                    {
                        "title": "第一章",
                        "file": "chapters/1_intro.tex",
                        "block_ids": ["i0001"],
                    }
                ]
            },
        }
        thesis_path.write_text(json.dumps(thesis, ensure_ascii=False), encoding="utf-8")

        result = render_chapters.render(root, thesis_path, allow_incomplete=False)
        assert result["status"] == "blocked"
        assert result["invalid_structure_blocks"][0]["status"] == "image_asset_invalid"
        assert not (root / "chapters/1_intro.tex").exists()

        asset = root / "Images/word_media/image1.png"
        asset.parent.mkdir(parents=True)
        asset.write_bytes(TINY_PNG)
        thesis["source_blocks"][0]["asset_status"] = "exported"
        thesis["source_blocks"][0]["asset_output"] = "Images/word_media/image1.png"
        thesis_path.write_text(json.dumps(thesis, ensure_ascii=False), encoding="utf-8")

        result = render_chapters.render(root, thesis_path, allow_incomplete=False)
        chapter_text = (root / "chapters/1_intro.tex").read_text(encoding="utf-8")
        assert result["status"] == "passed"
        assert "Images/word\\_media/image1.png" in chapter_text
        assert "chapters/1_intro.tex}" not in chapter_text


def test_render_chapters_blocks_discarded_block_in_structure():
    render_chapters = load_module("render_chapters")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "chapters").mkdir()
        (root / "workspace/intermediate").mkdir(parents=True)
        thesis_path = root / "workspace/intermediate/thesis.json"
        thesis_path.write_text(
            json.dumps(
                {
                    "source_blocks": [
                        {
                            "id": "p0001",
                            "status": "discarded_with_reason",
                            "discard_reason": "模板说明文字",
                            "text": "不应该被写入正文",
                            "target_slot": "chapters/1_intro.tex",
                        }
                    ],
                    "structure": {
                        "chapters": [
                            {
                                "title": "intro",
                                "file": "chapters/1_intro.tex",
                                "block_ids": ["p0001"],
                            }
                        ]
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        result = render_chapters.render(root, thesis_path, allow_incomplete=False)
        thesis = json.loads(thesis_path.read_text(encoding="utf-8"))

        assert result["status"] == "blocked"
        assert result["blocking_blocks"] == ["p0001"]
        assert not (root / "chapters/1_intro.tex").exists()
        assert thesis["source_blocks"][0]["status"] == "discarded_with_reason"
        assert thesis["source_blocks"][0].get("render_result") is None


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
