#!/usr/bin/env python3
"""Focused regression tests extracted from the former monolithic suite."""

from __future__ import annotations

import contextlib
import io
from unittest.mock import patch

from .support import (
    SCRIPTS_DIR,
    load_module,
)


def test_check_env_reports_missing_required_latex_packages():
    check_env = load_module("check_env")
    original_command_exists = check_env.command_exists
    original_kpsewhich_exists = getattr(check_env, "kpsewhich_exists", None)
    try:
        check_env.command_exists = lambda _name: True
        check_env.kpsewhich_exists = lambda filename: filename != "gb7714-2015.bbx"
        result = check_env.check("latex")
    finally:
        check_env.command_exists = original_command_exists
        if original_kpsewhich_exists is not None:
            check_env.kpsewhich_exists = original_kpsewhich_exists

    checks = {check["name"]: check for check in result["checks"]}
    assert checks["tex_package_ctexbook.cls"]["status"] == "passed"
    assert checks["tex_package_biblatex.sty"]["status"] == "passed"
    assert checks["tex_package_gb7714-2015.bbx"]["status"] == "blocked"
    assert result["status"] == "blocked"
    issues = {issue["code"]: issue for issue in result["issues"]}
    assert issues["tex_core_file_missing"]["severity"] == "blocking"
    assert issues["tex_core_file_missing"]["repair_policy"] == "ask_user_before_install"
    assert (
        str((SCRIPTS_DIR / "check_env.py").resolve())
        in issues["tex_core_file_missing"]["verify_command"]
    )
    assert issues["tex_core_file_missing"]["verify_command"].endswith("--stage latex")


def test_check_env_python_docx_hint_uses_short_timeout_and_mirror_fallback():
    check_env = load_module("check_env")
    original_find_spec = check_env.importlib.util.find_spec
    try:
        check_env.importlib.util.find_spec = lambda name: (
            None if name == "docx" else original_find_spec(name)
        )
        result = check_env.check("minimal")
    finally:
        check_env.importlib.util.find_spec = original_find_spec

    checks = {check["name"]: check for check in result["checks"]}
    hint = checks["python-docx"]["install_hint"]
    assert "--timeout 8" in hint
    assert "pypi.tuna.tsinghua.edu.cn/simple" in hint
    assert "失败、超时或无响应" in hint
    issues = {issue["code"]: issue for issue in result["issues"]}
    assert issues["python_docx_missing"]["severity"] == "blocking"
    assert issues["python_docx_missing"]["layer"] == "python-package"
    assert issues["python_docx_missing"]["verify_command"].endswith("--stage minimal")


def test_check_env_reports_missing_latex_commands_as_structured_issues():
    check_env = load_module("check_env")
    original_command_exists = check_env.command_exists
    original_kpsewhich_exists = getattr(check_env, "kpsewhich_exists", None)
    try:
        check_env.command_exists = lambda name: name not in {"xelatex", "biber"}
        check_env.kpsewhich_exists = lambda _filename: True
        result = check_env.check("latex")
    finally:
        check_env.command_exists = original_command_exists
        if original_kpsewhich_exists is not None:
            check_env.kpsewhich_exists = original_kpsewhich_exists

    issues = result["issues"]
    assert result["status"] == "blocked"
    assert [issue["code"] for issue in issues] == [
        "tex_command_missing",
        "tex_command_missing",
    ]
    assert {issue["target"] for issue in issues} == {"xelatex", "biber"}
    assert all(issue["verify_command"].endswith("--stage latex") for issue in issues)


def test_check_env_qa_stage_reports_optional_tools_without_blocking():
    check_env = load_module("check_env")
    original_command_exists = check_env.command_exists
    try:
        check_env.command_exists = lambda _name: False
        result = check_env.check("qa")
    finally:
        check_env.command_exists = original_command_exists

    checks = {check["name"]: check for check in result["checks"]}
    assert checks["pdfinfo"]["status"] == "needs_review"
    assert checks["pdftotext"]["status"] == "needs_review"
    assert result["status"] == "needs_review"
    assert {issue["code"] for issue in result["issues"]} == {"qa_tool_missing"}
    assert all(issue["severity"] == "optional" for issue in result["issues"])


def test_check_env_main_allows_needs_review_exit_code():
    check_env = load_module("check_env")
    original_check = check_env.check
    try:
        check_env.check = lambda _stage: {
            "status": "needs_review",
            "checks": [],
            "issues": [],
        }
        with contextlib.redirect_stdout(io.StringIO()):
            assert check_env.main([]) == 0
    finally:
        check_env.check = original_check


def test_check_env_distinguishes_missing_kpsewhich_from_tex_packages():
    check_env = load_module("check_env")
    with patch.object(check_env, "command_exists", side_effect=lambda name: name != "kpsewhich"):
        result = check_env.check("latex")

    checks = {check["name"]: check for check in result["checks"]}
    assert checks["kpsewhich"]["status"] == "blocked"
    assert not any(name.startswith("tex_package_") for name in checks)
    assert any(
        issue["code"] == "tex_command_missing" and issue["target"] == "kpsewhich"
        for issue in result["issues"]
    )
    assert result["scope"]["not_checked"]


def test_check_env_blocks_unsupported_python_version():
    check_env = load_module("check_env")
    with (
        patch.object(check_env.sys, "version_info", (3, 9, 18)),
        patch.object(check_env, "command_exists", return_value=True),
    ):
        result = check_env.check("qa")

    assert result["status"] == "blocked"
    assert result["checks"][0]["status"] == "blocked"
    assert any(issue["code"] == "python_version_unsupported" for issue in result["issues"])


def test_check_env_detects_broken_python_docx_import():
    check_env = load_module("check_env")
    with (
        patch.object(check_env.importlib.util, "find_spec", return_value=object()),
        patch.object(
            check_env.importlib,
            "import_module",
            side_effect=ImportError("broken lxml dependency"),
        ),
        patch.object(check_env, "pip_available", return_value=True),
    ):
        result = check_env.check("minimal")

    assert result["status"] == "blocked"
    issue_codes = {issue["code"] for issue in result["issues"]}
    assert "python_docx_import_failed" in issue_codes
    assert "python_docx_missing" not in issue_codes


def test_check_env_rejects_unrelated_docx_module_without_document_api():
    check_env = load_module("check_env")
    with (
        patch.object(check_env.importlib.util, "find_spec", return_value=object()),
        patch.object(check_env.importlib, "import_module", return_value=object()),
        patch.object(check_env, "pip_available", return_value=True),
    ):
        result = check_env.check("minimal")

    python_docx_check = next(check for check in result["checks"] if check["name"] == "python-docx")
    assert result["status"] == "blocked"
    assert "Document API" in python_docx_check["detail"]
    assert {issue["code"] for issue in result["issues"]} >= {"python_docx_import_failed"}
