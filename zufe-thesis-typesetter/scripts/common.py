#!/usr/bin/env python3
"""ZUFE Thesis Typesetter 脚本共享工具。"""

from __future__ import annotations

import json
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TEMPLATE_SIGNATURE = [
    "main.tex",
    "zufe.cls",
    "Reference.bib",
    "chapters/basicinfo.tex",
    "chapters/mainbody.tex",
    "misc/cover.tex",
    "misc/abstract.tex",
    "misc/originality.tex",
    "misc/reference.tex",
    "simhei.ttf",
    "stsong.ttf",
    "stkaiti.ttf",
    "InitFile/schoolLogo.png",
]

WORKSPACE_DIRS = [
    "workspace/input/assets",
    "workspace/intermediate",
    "workspace/output",
]

BUILD_TEMP_FILES = [
    "main.aux",
    "main.bbl",
    "main.bcf",
    "main.blg",
    "main.log",
    "main.out",
    "main.run.xml",
    "main.toc",
    "main.fdb_latexmk",
    "main.fls",
]

FINAL_BLOCK_STATES = {"rendered", "discarded_with_reason"}


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def timestamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def rel(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def safe_resolve_under(root: Path, path: str | Path, allowed_dir: str | Path) -> Path:
    """Resolve path and require it to stay under allowed_dir inside root."""
    root = root.resolve()
    allowed = Path(allowed_dir)
    allowed_path = allowed.resolve() if allowed.is_absolute() else (root / allowed).resolve()
    candidate = Path(path)
    target = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
    try:
        target.relative_to(allowed_path)
    except ValueError as exc:
        raise ValueError(f"unsafe path outside {rel(allowed_path, root)}: {path}") from exc
    return target


def read_json(path: Path, default: Any | None = None) -> Any:
    if not path.exists():
        if default is not None:
            return default
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def print_json(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def item(name: str, status: str, detail: str, **extra: Any) -> dict[str, Any]:
    data = {"name": name, "status": status, "detail": detail}
    data.update(extra)
    return data


def overall_status(items: list[dict[str, Any]]) -> str:
    statuses = {entry.get("status") for entry in items}
    if "blocked" in statuses or "failed" in statuses:
        return "blocked"
    if "needs_confirmation" in statuses or "warning" in statuses:
        return "needs_confirmation"
    return "passed"


def command_exists(name: str) -> bool:
    return shutil.which(name) is not None


def ensure_workspace(root: Path) -> None:
    for dirname in WORKSPACE_DIRS:
        (root / dirname).mkdir(parents=True, exist_ok=True)


def archive_path(root: Path, label: str) -> Path:
    return root / "workspace" / "archive" / timestamp() / label


def load_metadata_yaml(path: Path) -> dict[str, Any]:
    """读取第一版 metadata.yaml 支持的简单 key: value 结构，不强依赖 PyYAML。"""
    data: dict[str, Any] = {}
    if not path.exists():
        return data
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        if key:
            data[key] = parse_scalar(value.strip())
    return data


def parse_scalar(value: str) -> Any:
    if value in {"", "null", "None", "~"}:
        return ""
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        return value[1:-1]
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [parse_scalar(part.strip()) for part in inner.split(",")]
    if re.fullmatch(r"-?\d+", value):
        try:
            return int(value)
        except ValueError:
            return value
    return value


def metadata_value(metadata: dict[str, Any], *keys: str, default: str = "") -> str:
    for key in keys:
        value = metadata.get(key)
        if value not in (None, ""):
            return str(value)
    return default


def metadata_bool(metadata: dict[str, Any], key: str, default: bool = False) -> bool:
    value = metadata.get(key, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "是", "有"}
    return default


LATEX_SPECIAL_CHARS = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}


def latex_escape(
    text: Any,
    *,
    convert_quotes: bool = True,
    quote_state: dict[str, bool] | None = None,
) -> str:
    if text is None:
        return ""
    next_quote_is_opening = True
    if quote_state is not None:
        next_quote_is_opening = quote_state.get("next_quote_is_opening", True)

    parts: list[str] = []
    for char in str(text):
        if char == '"' and convert_quotes:
            parts.append("``" if next_quote_is_opening else "''")
            next_quote_is_opening = not next_quote_is_opening
            continue
        parts.append(LATEX_SPECIAL_CHARS.get(char, char))

    if quote_state is not None:
        quote_state["next_quote_is_opening"] = next_quote_is_opening
    return "".join(parts)


def block_summary(text: str, limit: int = 80) -> str:
    compact = re.sub(r"\s+", " ", text or "").strip()
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1] + "..."


def classify_text(text: str, style_name: str = "") -> tuple[str, float]:
    stripped = (text or "").strip()
    lower_style = (style_name or "").lower()
    if not stripped:
        return "empty", 1.0
    if "heading" in lower_style or "标题" in style_name:
        return "heading", 0.75
    if re.match(r"^第[一二三四五六七八九十百零\d]+[章节]\s*", stripped):
        return "heading", 0.8
    if stripped in {"摘要", "摘 要"} or stripped.startswith("摘要："):
        return "abstract_cn", 0.7
    if stripped.lower() == "abstract" or stripped.lower().startswith("abstract:"):
        return "abstract_en", 0.7
    if stripped.startswith("关键词") or stripped.lower().startswith("key words"):
        return "keywords", 0.7
    if stripped in {"参考文献", "References"}:
        return "references_heading", 0.8
    if stripped in {"致谢", "谢辞", "Acknowledgement", "Acknowledgements"}:
        return "acknowledgement_heading", 0.8
    if stripped.startswith("附录") or stripped.lower().startswith("appendix"):
        return "appendix_heading", 0.8
    if re.match(r"^\[[0-9]+\]", stripped) or re.match(r"^[0-9]+[.、]\s", stripped):
        return "reference_or_list", 0.45
    return "body", 0.35
