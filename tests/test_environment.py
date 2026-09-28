#!/usr/bin/env python3
"""Focused regression tests extracted from the former monolithic suite."""

from __future__ import annotations

import contextlib
import io
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

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


def test_check_env_python_docx_hint_uses_short_timeout_and_mirror_fallback(tmp_path):
    check_env = load_module("check_env")
    original_find_spec = check_env.importlib.util.find_spec
    try:
        check_env.importlib.util.find_spec = lambda name: (
            None if name == "docx" else original_find_spec(name)
        )
        with patch.object(check_env, "pip_available", return_value=True):
            result = check_env.check("minimal", tmp_path)
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
        check_env.check = lambda _stage, _root, _project_root: {
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


def test_docx_available_without_pip_passes_without_consulting_installers(tmp_path):
    check_env = load_module("check_env")
    with (
        patch.object(
            check_env,
            "pip_available",
            side_effect=AssertionError("pip is not a runtime dependency"),
        ),
        patch.object(
            check_env, "command_exists", side_effect=AssertionError("no installer needed")
        ),
    ):
        result = check_env.check("minimal", tmp_path)
    assert result["status"] == "passed"
    assert result["issues"] == []


@pytest.mark.parametrize("marker", ["uv.lock", "uv.toml", "tool.uv"])
def test_uv_missing_docx_offers_bound_sync_and_add_without_pip(tmp_path, monkeypatch, marker):
    check_env = load_module("check_env")
    project = tmp_path / "template with spaces"
    project.mkdir()
    manifest = '[project]\nname = "thesis"\nversion = "0.1.0"\ndependencies = ["python-docx"]\n'
    if marker == "tool.uv":
        manifest += "[tool.uv]\npackage = false\n"
    else:
        (project / marker).write_text("", encoding="utf-8")
    (project / "pyproject.toml").write_text(manifest, encoding="utf-8")
    prefix = project / ".venv"
    python = prefix / "bin/python"
    monkeypatch.delenv("UV_PROJECT_ENVIRONMENT", raising=False)
    with (
        patch.object(check_env.sys, "prefix", str(prefix)),
        patch.object(check_env.sys, "executable", str(python)),
        patch.object(check_env, "python_docx_import_error", return_value="not_installed"),
        patch.object(
            check_env, "pip_available", side_effect=AssertionError("uv does not need pip")
        ),
        patch.object(check_env, "command_exists", return_value=True),
    ):
        result = check_env.check("minimal", project)
    assert result["environment"]["manager"] == "uv"
    assert {problem["code"] for problem in result["issues"]} == {"python_docx_missing"}
    hint = next(row["install_hint"] for row in result["checks"] if row["name"] == "python-docx")
    assert "uv sync" in hint and "uv add" in hint
    assert ("--locked" in hint) is (marker == "uv.lock")
    assert f"--project {shlex.quote(str(project))}" in hint
    assert f"--python {shlex.quote(str(python))}" in hint
    assert f"UV_PROJECT_ENVIRONMENT={shlex.quote(str(prefix))}" in hint
    assert "ensurepip" not in hint
    assert not prefix.exists()


def test_wrong_development_interpreter_does_not_validate_or_repair_template(tmp_path, monkeypatch):
    check_env = load_module("check_env")
    template = tmp_path / "user-template"
    template.mkdir()
    (template / "uv.lock").write_text("", encoding="utf-8")
    monkeypatch.delenv("UV_PROJECT_ENVIRONMENT", raising=False)
    with patch.object(
        check_env, "python_docx_import_error", side_effect=AssertionError("wrong interpreter")
    ):
        result = check_env.check("minimal", template)
    assert result["status"] == "blocked"
    assert {row["code"] for row in result["issues"]} == {"python_environment_mismatch"}
    command = shlex.split(result["issues"][0]["verify_command"])
    assert str(template / ".venv/bin/python") in command
    assert str(template) == command[command.index("--root") + 1]
    assert not any("install_hint" in row for row in result["checks"])


@pytest.mark.parametrize("uv_available", [True, False])
def test_non_uv_missing_docx_without_pip_reports_only_runtime_blocker(tmp_path, uv_available):
    check_env = load_module("check_env")
    with (
        patch.object(check_env, "python_docx_import_error", return_value="not_installed"),
        patch.object(check_env, "pip_available", return_value=False),
        patch.object(check_env, "command_exists", return_value=uv_available),
    ):
        result = check_env.check("minimal", tmp_path)
    assert {row["code"] for row in result["issues"]} == {"python_docx_missing"}
    hint = next(row["install_hint"] for row in result["checks"] if row["name"] == "python-docx")
    if uv_available:
        assert f"uv pip install --python {shlex.quote(sys.executable)}" in hint
    else:
        assert "普通 venv" in hint


@pytest.mark.parametrize(
    "marker,manager",
    [
        ("poetry.lock", "poetry"),
        ("pdm.lock", "pdm"),
        ("environment.yml", "conda"),
        ("pyproject.toml", "project"),
    ],
)
def test_other_project_managers_do_not_fall_back_to_pip(tmp_path, marker, manager):
    check_env = load_module("check_env")
    (tmp_path / marker).write_text("", encoding="utf-8")
    with (
        patch.object(check_env, "python_docx_import_error", return_value="not_installed"),
        patch.object(
            check_env, "pip_available", side_effect=AssertionError("respect project manager")
        ),
    ):
        result = check_env.check("minimal", tmp_path)
    assert result["environment"]["manager"] == manager
    assert result["issues"][0]["next_action"] == "inspect_project_dependencies"


def test_real_uv_diagnostic_and_verification_keep_target_from_another_cwd(tmp_path):
    project = tmp_path / "user workspace"
    template = project / "thesis"
    template.mkdir(parents=True)
    prefix = project / "custom environment"
    subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(prefix)], check=True)
    python = prefix / "bin/python"
    (project / "pyproject.toml").write_text(
        '[project]\nname = "thesis"\nversion = "0.0.0"\nrequires-python = ">=3.10"\n'
        'dependencies = ["python-docx"]\n[tool.uv]\npackage = false\n',
        encoding="utf-8",
    )
    before = {
        str(path.relative_to(project)): (path.read_bytes(), path.stat().st_mtime_ns)
        for path in project.rglob("*")
        if path.is_file() and not path.is_symlink()
    }
    env = {**os.environ, "UV_PROJECT_ENVIRONMENT": str(prefix), "PYTHONDONTWRITEBYTECODE": "1"}
    initial = subprocess.run(
        [
            str(python),
            "-B",
            str(SCRIPTS_DIR / "check_env.py"),
            "--root",
            str(template),
            "--project-root",
            str(project),
            "--stage",
            "minimal",
        ],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert initial.returncode == 2, initial.stderr
    result = json.loads(initial.stdout)
    assert {row["code"] for row in result["issues"]} == {"python_docx_missing"}
    # 复查命令自身保留自定义环境，不能依赖上次 shell 的目录或临时变量。
    env.pop("UV_PROJECT_ENVIRONMENT")
    verified = subprocess.run(
        shlex.split(result["issues"][0]["verify_command"]),
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert verified.returncode == 2, verified.stderr
    assert json.loads(verified.stdout)["environment"] == result["environment"]
    after = {
        str(path.relative_to(project)): (path.read_bytes(), path.stat().st_mtime_ns)
        for path in project.rglob("*")
        if path.is_file() and not path.is_symlink()
    }
    assert after == before
    assert not (project / "uv.lock").exists()


def test_target_resolution_never_searches_parent_or_skill_development_repo(tmp_path):
    check_env = load_module("check_env")
    (tmp_path / "uv.lock").write_text("", encoding="utf-8")
    template = tmp_path / "template"
    template.mkdir()
    target = check_env.environment_target(template)
    assert target.manager == "pip"
    assert target.declarations == ()
