#!/usr/bin/env python3
"""Focused regression tests extracted from the former monolithic suite."""

from __future__ import annotations

import tempfile
from pathlib import Path

from .support import (
    load_module,
    write_template_contract,
    write_template_files,
)


def test_check_template_requires_new_fonts_directory_layout():
    check_template = load_module("check_template")
    base_signature = [
        "main.tex",
        "zufe.cls",
        "Reference.bib",
        "chapters/basicinfo.tex",
        "chapters/mainbody.tex",
        "misc/cover.tex",
        "misc/abstract.tex",
        "misc/originality.tex",
        "misc/reference.tex",
        "InitFile/schoolLogo.png",
    ]

    with tempfile.TemporaryDirectory() as tmp:
        old_root = Path(tmp) / "old"
        write_template_files(
            old_root,
            base_signature + ["simhei.ttf", "stsong.ttf", "stkaiti.ttf"],
        )
        write_template_contract(old_root)
        old_result = check_template.check_template(old_root)
        assert old_result["status"] == "blocked"
        assert old_result["missing"] == [
            "fonts/simhei.ttf",
            "fonts/stsong.ttf",
            "fonts/stkaiti.ttf",
        ]

        new_root = Path(tmp) / "new"
        write_template_files(
            new_root,
            base_signature + ["fonts/simhei.ttf", "fonts/stsong.ttf", "fonts/stkaiti.ttf"],
        )
        write_template_contract(new_root)
        new_result = check_template.check_template(new_root)
        assert new_result["status"] == "passed"
        assert new_result["compatibility"]["detected_family"] == "ZUFE-Thesis"
        assert new_result["compatibility"]["detected_version"] == "1.0.1"


def test_check_template_requires_confirmation_for_compatible_unknown_versions():
    check_template = load_module("check_template")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write_template_files(root, check_template.TEMPLATE_SIGNATURE)
        write_template_contract(root, version="2.0.0")

        review = check_template.check_template(root)
        assert review["status"] == "needs_confirmation"
        assert review["compatibility"]["review_reasons"] == ["模板版本 2.0.0 尚未列入已验证版本。"]

        confirmed = check_template.check_template(root, confirm_compatible=True)
        assert confirmed["status"] == "passed"
        assert confirmed["compatibility"]["confirmation_applied"] is True


def test_check_template_does_not_let_confirmation_bypass_missing_interfaces():
    check_template = load_module("check_template")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write_template_files(root, check_template.TEMPLATE_SIGNATURE)
        write_template_contract(root, version=None, include_family=False)
        (root / "misc/abstract.tex").write_text("\\abstractCN\n", encoding="utf-8")

        result = check_template.check_template(root, confirm_compatible=True)
        assert result["status"] == "blocked"
        assert result["compatibility"]["confirmation_applied"] is True
        assert {entry["anchor"] for entry in result["compatibility"]["missing_anchors"]} == {
            "keywords_cn_macro",
            "abstract_en_macro",
            "keywords_en_macro",
        }


def test_check_template_guides_template_download_fallbacks():
    check_template = load_module("check_template")
    with tempfile.TemporaryDirectory() as tmp:
        result = check_template.check_template(Path(tmp))
        next_steps = "\n".join(result["next_steps"])
        assert "https://github.com/sqsssq/ZUFE-Thesis" in next_steps
        assert "https://gitee.com/cwf818/ZUFE-Thesis" in next_steps
        assert "模板压缩包" in next_steps
        assert "已解压的完整模板目录" in next_steps


def test_prepare_workspace_requires_consent_then_archives_old_outputs():
    prepare_workspace = load_module("prepare_workspace")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        source = root / "incoming.docx"
        source.write_bytes(b"word source")
        target = root / "workspace/input/thesis.docx"

        result = prepare_workspace.prepare(
            root,
            source,
            move_word=False,
            copy_word=False,
            archive_existing=False,
        )
        assert result["status"] == "needs_confirmation"
        assert source.exists()
        assert not target.exists()

        result = prepare_workspace.prepare(
            root,
            source,
            move_word=False,
            copy_word=True,
            archive_existing=False,
        )
        assert result["status"] == "passed"
        assert source.exists()
        assert target.read_bytes() == b"word source"

        old_result = root / "workspace/output/qa_result.json"
        old_result.write_text("{}", encoding="utf-8")
        result = prepare_workspace.prepare(
            root,
            target,
            move_word=False,
            copy_word=False,
            archive_existing=False,
        )
        assert result["status"] == "blocked"
        assert old_result.exists()

        result = prepare_workspace.prepare(
            root,
            target,
            move_word=False,
            copy_word=False,
            archive_existing=True,
        )
        assert result["status"] == "passed"
        assert not old_result.exists()
        old_outputs = next(check for check in result["checks"] if check["name"] == "old_outputs")
        assert old_outputs["archived"]
