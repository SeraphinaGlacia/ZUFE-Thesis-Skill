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
    "fonts/simhei.ttf",
    "fonts/stsong.ttf",
    "fonts/stkaiti.ttf",
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
MANUAL_CROSS_REFERENCE_RE = re.compile(
    r"(?<![\\A-Za-z])([图表])\s*[0-9０-９]+(?:\s*[.-]\s*[0-9０-９]+)+"
)
LATEX_LABEL_RE = re.compile(r"\\label\s*\{([^}]+)\}")
LATEX_REF_RE = re.compile(r"\\(?:ref|autoref|pageref|eqref)\s*\{([^}]+)\}")


def now_iso() -> str:
    """生成带本地时区的 ISO 时间戳。

    Returns:
        str: 秒级精度的 ISO 8601 时间字符串。
    """
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def timestamp() -> str:
    """生成适合目录名使用的本地时间戳。

    Returns:
        str: ``YYYYMMDD-HHMMSS`` 格式的时间戳。
    """
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def rel(path: Path, root: Path) -> str:
    """把路径尽量转换为相对模板根目录的 POSIX 表示。

    Args:
        path (Path): 待转换路径。
        root (Path): ZUFE-Thesis 模板根目录。

    Returns:
        str: 相对 root 的路径；不在 root 下时返回原路径字符串。
    """
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def safe_resolve_under(root: Path, path: str | Path, allowed_dir: str | Path) -> Path:
    """解析路径并强制限制在指定目录下。

    Args:
        root (Path): ZUFE-Thesis 模板根目录。
        path (str | Path): 用户或账本提供的目标路径。
        allowed_dir (str | Path): 允许写入的目录，通常是 ``chapters`` 或 ``Images``。

    Returns:
        Path: 解析后的安全绝对路径。

    Raises:
        ValueError: 当目标路径逃逸出 allowed_dir 时抛出。
    """
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
    """读取 JSON 文件，支持显式默认值。

    Args:
        path (Path): JSON 文件路径。
        default (Any | None): 文件不存在时返回的默认值。

    Returns:
        Any: 解析后的 JSON 数据。

    Raises:
        FileNotFoundError: 文件不存在且没有提供默认值时抛出。
        json.JSONDecodeError: 文件内容不是合法 JSON 时抛出。
    """
    if not path.exists():
        if default is not None:
            return default
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    """以 UTF-8 和缩进格式写入 JSON 文件。

    Args:
        path (Path): 输出文件路径。
        data (Any): 可 JSON 序列化的数据。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def print_json(data: Any) -> None:
    """把数据作为 UTF-8 友好的 JSON 打印到 stdout。

    Args:
        data (Any): 可 JSON 序列化的数据。
    """
    print(json.dumps(data, ensure_ascii=False, indent=2))


def item(name: str, status: str, detail: str, **extra: Any) -> dict[str, Any]:
    """创建统一结构的检查项。

    Args:
        name (str): 检查项名称。
        status (str): 检查状态，例如 ``passed``、``blocked``。
        detail (str): 面向 Agent 或用户的简短说明。
        **extra (Any): 需要附加到检查项中的结构化字段。

    Returns:
        dict[str, Any]: 标准检查项字典。
    """
    data = {"name": name, "status": status, "detail": detail}
    data.update(extra)
    return data


def overall_status(items: list[dict[str, Any]]) -> str:
    """根据检查项列表汇总门禁状态。

    Args:
        items (list[dict[str, Any]]): 检查项列表。

    Returns:
        str: ``blocked``、``needs_confirmation`` 或 ``passed``。
    """
    statuses = {entry.get("status") for entry in items}
    if "blocked" in statuses or "failed" in statuses:
        return "blocked"
    if "needs_confirmation" in statuses or "warning" in statuses:
        return "needs_confirmation"
    return "passed"


def strip_latex_comment(line: str) -> str:
    """移除单行 LaTeX 注释，保留转义百分号。

    Args:
        line (str): 单行 LaTeX 源码。

    Returns:
        str: 去掉非转义 ``%`` 之后的文本。
    """
    escaped = False
    for index, char in enumerate(line):
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == "%":
            return line[:index]
    return line


def manual_cross_reference_hits(source_text: str, limit: int = 20) -> list[str]:
    """查找正文源码中残留的手写图表编号。

    这类 ``图2.1`` / ``表 1.2`` 字符串在重排后很容易与 LaTeX 自动编号不一致，
    应由 Agent 确认后改写为 ``图~\\ref{...}`` 或 ``表~\\ref{...}``。

    Args:
        source_text (str): 章节 LaTeX 源码。
        limit (int): 最多返回多少条命中摘要。

    Returns:
        list[str]: 带行号和短上下文的命中摘要。
    """
    hits = []
    for line_number, raw_line in enumerate(source_text.splitlines(), start=1):
        line = strip_latex_comment(raw_line)
        for match in MANUAL_CROSS_REFERENCE_RE.finditer(line):
            start = max(0, match.start() - 24)
            end = min(len(line), match.end() + 24)
            snippet = line[start:end].strip()
            hits.append(f"line {line_number}: {snippet}")
            if len(hits) >= limit:
                return hits
    return hits


def latex_label_reference_issues(source_text: str) -> dict[str, list[str]]:
    """检查章节源码中的 label/ref 闭环。

    Args:
        source_text (str): 章节 LaTeX 源码。

    Returns:
        dict[str, list[str]]: ``duplicate_labels`` 和 ``undefined_refs`` 列表。
    """
    labels = []
    refs = []
    for raw_line in source_text.splitlines():
        line = strip_latex_comment(raw_line)
        labels.extend(label.strip() for label in LATEX_LABEL_RE.findall(line) if label.strip())
        refs.extend(ref.strip() for ref in LATEX_REF_RE.findall(line) if ref.strip())
    seen = set()
    duplicate_labels = []
    for label in labels:
        if label in seen and label not in duplicate_labels:
            duplicate_labels.append(label)
        seen.add(label)
    undefined_refs = sorted(set(refs) - set(labels))
    return {
        "duplicate_labels": duplicate_labels,
        "undefined_refs": undefined_refs,
    }


def command_exists(name: str) -> bool:
    """判断命令是否存在于 PATH。

    Args:
        name (str): 命令名称。

    Returns:
        bool: 命令可执行时返回 True。
    """
    return shutil.which(name) is not None


def ensure_workspace(root: Path) -> None:
    """创建流程 A/B/C 使用的标准 workspace 目录。

    Args:
        root (Path): ZUFE-Thesis 模板根目录。
    """
    for dirname in WORKSPACE_DIRS:
        (root / dirname).mkdir(parents=True, exist_ok=True)


def archive_path(root: Path, label: str) -> Path:
    """生成本轮归档目录路径。

    Args:
        root (Path): ZUFE-Thesis 模板根目录。
        label (str): 归档用途标签。

    Returns:
        Path: ``workspace/archive/<timestamp>/<label>`` 路径。
    """
    return root / "workspace" / "archive" / timestamp() / label


def load_metadata_yaml(path: Path) -> dict[str, Any]:
    """读取第一版 metadata.yaml 支持的简单 key: value 结构。

    第一版刻意不强依赖 PyYAML，避免把流程 A 的最小环境门槛抬高。

    Args:
        path (Path): metadata.yaml 路径。

    Returns:
        dict[str, Any]: 解析后的 metadata 字典。
    """
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
    """解析 metadata 简单标量值。

    Args:
        value (str): 冒号右侧的原始字符串。

    Returns:
        Any: 字符串、布尔值、整数、列表或空字符串。
    """
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
    """按候选键顺序读取第一个非空 metadata 值。

    Args:
        metadata (dict[str, Any]): metadata 字典。
        *keys (str): 候选字段名。
        default (str): 所有候选都为空时返回的默认值。

    Returns:
        str: 第一个非空值的字符串形式。
    """
    for key in keys:
        value = metadata.get(key)
        if value not in (None, ""):
            return str(value)
    return default


def metadata_bool(metadata: dict[str, Any], key: str, default: bool = False) -> bool:
    """读取 metadata 布尔值，兼容中文和常见字符串写法。

    Args:
        metadata (dict[str, Any]): metadata 字典。
        key (str): 字段名。
        default (bool): 字段缺失时的默认值。

    Returns:
        bool: 解析后的布尔值。
    """
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
    """转义普通正文可安全写入 LaTeX。

    Args:
        text (Any): 待转义文本。
        convert_quotes (bool): 是否把 ASCII 双引号转换为 LaTeX 左右引号。
        quote_state (dict[str, bool] | None): 跨片段共享的引号开闭状态。

    Returns:
        str: 已转义的 LaTeX 普通正文片段。
    """
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
    """生成单行文本摘要。

    Args:
        text (str): 原始文本。
        limit (int): 摘要最大字符数。

    Returns:
        str: 压缩空白并截断后的摘要。
    """
    compact = re.sub(r"\s+", " ", text or "").strip()
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1] + "..."


def classify_text(text: str, style_name: str = "") -> tuple[str, float]:
    """对 Word 文本块做轻量候选类型分类。

    Args:
        text (str): 段落或单元格文本。
        style_name (str): Word 样式名称。

    Returns:
        tuple[str, float]: 候选类型和置信度。
    """
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
