"""Shared fixtures and module-loading helpers for repository tests."""

from __future__ import annotations

import base64
import importlib.util
import sys
import tempfile
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = REPO_ROOT / "skills" / "zufe-thesis-typesetter"
SCRIPTS_DIR = SKILL_DIR / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
)


def load_module(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS_DIR / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_tiny_png(path: Path) -> None:
    path.write_bytes(TINY_PNG)


def write_template_files(root: Path, relative_paths: list[str]) -> None:
    """写入用于模板签名测试的最小占位文件。

    Args:
        root (Path): 临时模板根目录。
        relative_paths (list[str]): 需要创建的相对路径列表。
    """
    for relative_path in relative_paths:
        path = root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("placeholder\n", encoding="utf-8")


def write_template_contract(
    root: Path,
    *,
    version: str | None = "1.0.1",
    include_family: bool = True,
) -> None:
    declarations = []
    if include_family:
        declarations.append(r"\newcommand{\zufeTemplateName}{ZUFE-Thesis}")
    if version is not None:
        declarations.append(rf"\newcommand{{\zufeTemplateVersion}}{{{version}}}")
    (root / "zufe.cls").write_text(
        "\n".join(
            [
                r"\ProvidesClass{zufe}",
                r"\newcommand{\haveSub}[1]{}",
                r"\RequirePackage{graphicx}",
                r"\RequirePackage{booktabs}",
                r"\RequirePackage{array}",
                r"\RequirePackage{hyperref}",
                r"\RequirePackage{amsmath}",
                r"\RequirePackage{amssymb}",
                *declarations,
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (root / "main.tex").write_text(
        "\\input{chapters/basicinfo}\n\\input{chapters/mainbody}\n",
        encoding="utf-8",
    )
    (root / "misc/cover.tex").write_text(
        "\\thesisTitle\n\\yourStudentID\n\\mentorName\n",
        encoding="utf-8",
    )
    (root / "misc/abstract.tex").write_text(
        "\\abstractCN\n\\keywordsCN\n\\abstractEN\n\\keywordsEN\n",
        encoding="utf-8",
    )
    (root / "misc/reference.tex").write_text("\\printbibliography\n", encoding="utf-8")


def basic_metadata_yaml(*, title_cn: str = "测试题目", extra: str = "") -> str:
    return (
        "report_style: 1\n"
        f"thesis_title_cn: {title_cn}\n"
        "thesis_title_en: Test Title\n"
        "college: 测试学院\n"
        "major: 测试专业\n"
        "name: 测试姓名\n"
        "student_id: 20260001\n"
        "mentor: 张老师\n"
        "class_name: 测试班级\n"
        "date: 2026年6月\n"
        f"{extra}"
    )


def rewrite_docx_xml(
    docx_path: Path,
    replacements: dict[str, str],
    additions: dict[str, str] | None = None,
) -> None:
    original = docx_path.read_bytes()
    with tempfile.TemporaryDirectory() as tmp:
        original_zip = Path(tmp) / "original.docx"
        rewritten_zip = Path(tmp) / "rewritten.docx"
        original_zip.write_bytes(original)
        with (
            zipfile.ZipFile(original_zip, "r") as source,
            zipfile.ZipFile(rewritten_zip, "w") as target,
        ):
            for info in source.infolist():
                data = source.read(info.filename)
                if info.filename in replacements:
                    data = replacements[info.filename].encode("utf-8")
                target.writestr(info, data)
            for filename, text in (additions or {}).items():
                target.writestr(filename, text.encode("utf-8"))
        docx_path.write_bytes(rewritten_zip.read_bytes())
