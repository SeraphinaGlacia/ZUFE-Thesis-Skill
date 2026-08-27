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


def test_build_xelatex_uses_noninteractive_error_flags():
    build = load_module("build")
    xelatex_steps = [command for command in build.COMPILE_CHAIN if command[0] == "xelatex"]
    assert xelatex_steps
    for command in xelatex_steps:
        assert command[:4] == [
            "xelatex",
            "-interaction=nonstopmode",
            "-halt-on-error",
            "-file-line-error",
        ]
        assert command[-1] == "main.tex"


def test_build_timeout_preserves_byte_output_without_type_error():
    build = load_module("build")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        timeout = subprocess.TimeoutExpired(
            cmd=build.COMPILE_CHAIN[0],
            timeout=1,
            output=b"partial build output\n",
        )
        with patch.object(build.subprocess, "run", side_effect=timeout):
            steps = build.run_chain(root, timeout=1)

        assert steps[0]["exit_code"] == 124
        log = (root / steps[0]["log"]).read_text(encoding="utf-8")
        assert "partial build output" in log
        assert "command timed out after 1 seconds" in log


def test_build_success_writes_machine_and_human_reports():
    build = load_module("build")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "workspace/output").mkdir(parents=True)

        def successful_chain(project_root: Path, timeout: int) -> list[dict]:
            assert timeout == 30
            (project_root / "main.pdf").write_bytes(b"%PDF-1.7\n")
            return [
                {
                    "index": index,
                    "command": command,
                    "exit_code": 0,
                    "started_at": "2026-01-01T00:00:00Z",
                    "ended_at": "2026-01-01T00:00:01Z",
                    "log": f"workspace/output/build-step-{index}.log",
                }
                for index, command in enumerate(build.COMPILE_CHAIN, start=1)
            ]

        with (
            patch.object(
                build,
                "check_flow_b_gate",
                return_value={
                    "status": "passed",
                    "thesis_json_fingerprint": {"sha256": "thesis", "size_bytes": 1},
                    "source_docx_fingerprint": {"sha256": "docx", "size_bytes": 1},
                },
            ),
            patch.object(build, "prepare_build", return_value=[]),
            patch.object(build, "run_chain", side_effect=successful_chain),
        ):
            result = build.build(root, timeout=30)

        assert result["status"] == "passed"
        assert result["new_pdf"] is True
        machine_report = json.loads(
            (root / "workspace/output/build_result.json").read_text(encoding="utf-8")
        )
        human_report = (root / "workspace/output/report.md").read_text(encoding="utf-8")
        assert machine_report["status"] == "passed"
        assert len(machine_report["steps"]) == len(build.COMPILE_CHAIN)
        assert "- Status: `passed`" in human_report


def test_build_stops_before_archiving_when_flow_b_gate_is_blocked():
    build = load_module("build")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        old_pdf = root / "main.pdf"
        old_pdf.write_bytes(b"old pdf")
        with (
            patch.object(
                build,
                "check_flow_b_gate",
                return_value={
                    "status": "blocked",
                    "issues": [{"check": "source_docx_changed"}],
                },
            ),
            patch.object(build, "prepare_build") as prepare_build,
            patch.object(build, "run_chain") as run_chain,
        ):
            result = build.build(root, timeout=30)

        assert result["status"] == "blocked"
        assert result["steps"] == []
        assert old_pdf.read_bytes() == b"old pdf"
        prepare_build.assert_not_called()
        run_chain.assert_not_called()
        assert (root / "workspace/output/build_result.json").exists()


def test_diagnose_build_classifies_standard_latex_missing_file_messages():
    diagnose_build = load_module("diagnose_build")
    issues = diagnose_build.classify(
        "! LaTeX Error: File `missing-package.sty' not found.\n"
        "! LaTeX Error: File `Images/missing-figure.png' not found.\n"
    )
    categories = {issue["category"] for issue in issues}
    assert "environment_issue" in categories
    assert "user_input_required" in categories


def test_diagnose_build_writes_actionable_result():
    diagnose_build = load_module("diagnose_build")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "workspace/output").mkdir(parents=True)
        (root / "main.log").write_text(
            "! LaTeX Error: File `missing-package.sty' not found.\n",
            encoding="utf-8",
        )

        result = diagnose_build.diagnose(root)
        written = json.loads((root / "workspace/output/diagnosis.json").read_text(encoding="utf-8"))

        assert result["status"] == "needs_action"
        assert result["logs_checked"] == ["main.log"]
        assert result["issues"][0]["category"] == "environment_issue"
        assert written == result


def test_diagnose_build_deduplicates_repeated_log_evidence():
    diagnose_build = load_module("diagnose_build")
    message = "! LaTeX Error: File `missing-package.sty' not found."

    issues = diagnose_build.classify(f"{message}\n{message}\n")

    assert len(issues) == 1
    assert issues[0]["category"] == "environment_issue"
