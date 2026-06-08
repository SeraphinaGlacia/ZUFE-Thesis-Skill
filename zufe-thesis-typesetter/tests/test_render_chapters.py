#!/usr/bin/env python3
"""Regression tests for chapter rendering helpers."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts/render_chapters.py"
SCRIPTS_DIR = SCRIPT_PATH.parent
sys.path.insert(0, str(SCRIPTS_DIR))


def load_render_chapters():
    spec = importlib.util.spec_from_file_location("render_chapters", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_heading_level_takes_precedence():
    module = load_render_chapters()
    assert module.block_to_latex(
        {"semantic_role": "heading", "level": 1, "text": "一级标题"}
    ) == "\\chapter{一级标题}"
    assert module.block_to_latex(
        {"semantic_role": "heading", "level": 2, "text": "二级标题"}
    ) == "\\section{二级标题}"
    assert module.block_to_latex(
        {"semantic_role": "heading", "level": 3, "text": "三级标题"}
    ) == "\\subsection{三级标题}"


if __name__ == "__main__":
    test_heading_level_takes_precedence()
    print("render_chapters heading level regression passed")
