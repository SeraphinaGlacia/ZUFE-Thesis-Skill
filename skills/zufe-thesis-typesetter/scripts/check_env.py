#!/usr/bin/env python3
"""检查 Python DOCX 与 LaTeX/Biber 环境门禁。"""

import argparse
import importlib
import importlib.util
import os
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from common import command_exists, item, overall_status, print_json

REQUIRED_TEX_FILES = {
    "ctexbook.cls": "ctexbook 是 ZUFE 模板的文档类基础。",
    "biblatex.sty": "biblatex 是参考文献编译基础。",
    "gb7714-2015.bbx": "gb7714-2015 是模板使用的国标参考文献样式。",
}

QA_TOOLS = {
    "pdfinfo": "用于读取 PDF 页数；缺失时 QA 会退回较弱的页数判断。",
    "pdftotext": "用于抽取 PDF 文本；缺失时无法完成文本级 QA。",
}

MINIMUM_PYTHON = (3, 10)


@dataclass(frozen=True)
class EnvironmentTarget:
    """一次检查的模板、依赖项目和解释器；不从 Skill 安装目录推断目标。"""

    root: Path
    project_root: Path
    python: Path
    prefix: Path
    manager: str
    declarations: tuple[Path, ...]
    expected_prefix: Path | None

    @property
    def mismatch(self) -> bool:
        """当前解释器是否偏离目标项目声明的环境。"""
        return self.expected_prefix is not None and self.prefix != self.expected_prefix

    def verify_command(self, stage: str) -> str:
        """生成绑定相同目标的复查命令；环境错配时先切回目标解释器。"""
        python = self.python
        if self.mismatch and self.expected_prefix is not None:
            windows_python = self.expected_prefix / "Scripts/python.exe"
            python = (
                windows_python
                if os.name == "nt" or windows_python.is_file()
                else self.expected_prefix / "bin/python"
            )
        command = [
            str(python),
            "-B",
            str(Path(__file__).resolve()),
            "--root",
            str(self.root),
            "--project-root",
            str(self.project_root),
            "--stage",
            stage,
        ]
        if self.manager == "uv" and self.expected_prefix is not None:
            command = ["env", f"UV_PROJECT_ENVIRONMENT={self.expected_prefix}", *command]
        return shlex.join(command)


def environment_target(root: Path, project_root: Path | None = None) -> EnvironmentTarget:
    """只读识别指定项目的管理器证据与目标环境。

    不向父目录或 Skill 源码目录搜索。模板位于依赖工作区子目录时，调用者须显式
    传入 project_root。这里只识别管理器标记，不用文本匹配猜测依赖是否已经声明。
    """
    root = root.expanduser().resolve()
    project_root = (project_root or root).expanduser().resolve()
    for directory in (root, project_root):
        if not directory.is_dir():
            raise ValueError(f"目标目录不存在或不是目录：{directory}")
    names = (
        "pyproject.toml",
        "uv.lock",
        "uv.toml",
        "poetry.lock",
        "pdm.lock",
        "requirements.txt",
        "environment.yml",
        "environment.yaml",
    )
    declarations = tuple(project_root / name for name in names if (project_root / name).is_file())
    manifest = project_root / "pyproject.toml"
    source = manifest.read_text(encoding="utf-8") if manifest.is_file() else ""
    prefix = Path(sys.prefix).resolve()
    manager = "pip"
    for candidate, markers in (
        ("uv", ("uv.lock", "uv.toml")),
        ("poetry", ("poetry.lock",)),
        ("pdm", ("pdm.lock",)),
    ):
        if any((project_root / name).is_file() for name in markers) or re.search(
            rf"(?m)^\s*\[\s*tool\.{candidate}(?:\s*\]|\.)", source
        ):
            manager = candidate
            break
    else:
        if (prefix / "conda-meta").is_dir() or any(
            (project_root / name).is_file() for name in ("environment.yml", "environment.yaml")
        ):
            manager = "conda"
        elif manifest.is_file():
            manager = "project"
    expected_prefix: Path | None = project_root / ".venv"
    if manager == "uv":
        configured = Path(os.environ.get("UV_PROJECT_ENVIRONMENT", ".venv")).expanduser()
        expected_prefix = project_root / configured
    elif not expected_prefix.is_dir():
        expected_prefix = None
    return EnvironmentTarget(
        root,
        project_root,
        Path(os.path.abspath(sys.executable)),
        prefix,
        manager,
        declarations,
        expected_prefix.resolve() if expected_prefix is not None else None,
    )


def docx_repair_hint(target: EnvironmentTarget) -> tuple[str, str]:
    """给出同一环境的条件式修复建议，不执行安装或修改依赖声明。"""
    python = shlex.quote(str(target.python))
    project = shlex.quote(str(target.project_root))
    if target.manager == "uv":
        if not (target.project_root / "pyproject.toml").is_file():
            return "inspect_project_dependencies", (
                f"{project} 有 uv 标记但缺少 pyproject.toml；先核对依赖项目根目录，"
                "不要自动初始化项目或向其他环境安装。"
            )
        binding = f"env UV_PROJECT_ENVIRONMENT={shlex.quote(str(target.prefix))} uv"
        options = f"--project {project} --python {python} --no-python-downloads"
        locked = " --locked" if (target.project_root / "uv.lock").is_file() else ""
        available = "" if command_exists("uv") else "先定位已有 uv 命令；缺少 uv 不表示需要修 pip。"
        return "sync_or_add_uv_dependency", (
            available + "先读取目标项目声明。若 python-docx 已声明，按所属依赖组或 extra 同步："
            f"{binding} sync {options}{locked} --inexact；"
            "非默认组或 extra 需补 --group <组名> 或 --extra <名称>。"
            "若未声明且任务需要持久使用，再添加："
            f"{binding} add {options} python-docx。"
            "add 会修改目标 pyproject.toml 和 uv.lock；无锁时 sync 也会创建锁文件。"
        )
    if target.manager != "pip":
        return "inspect_project_dependencies", (
            f"按目标 {project} 的 {target.manager} 声明和既有管理器修复，"
            f"安装目标必须对应解释器 {python}（环境 {target.prefix}）。"
            "先确认包所在依赖组及管理器的环境路径，不改 Skill 开发仓库，不先补 pip。"
        )
    requirements = target.project_root / "requirements.txt"
    declaration_hint = (
        f"先核对 {requirements}；未声明时按任务补充声明，再按该文件安装。"
        if requirements.is_file()
        else ""
    )
    packages = f"-r {shlex.quote(str(requirements))}" if requirements.is_file() else "python-docx"
    if pip_available():
        return "install_python_docx", (
            declaration_hint
            + f"先短超时尝试：{python} -m pip install --timeout 8 --retries 1 {packages}；"
            "若失败、超时或无响应，改用中国大陆镜像："
            f"{python} -m pip install --timeout 15 --retries 2 "
            f"-i https://pypi.tuna.tsinghua.edu.cn/simple {packages}"
        )
    if command_exists("uv"):
        return "install_python_docx_with_uv_pip", (
            declaration_hint
            + f"当前环境无 pip，可用已有 uv：uv pip install --python {python} {packages}。"
            "该命令不需要目标环境安装 pip。"
        )
    return "locate_python_installer", (
        "当前解释器没有 pip，且 PATH 中未找到 uv；这是安装方式缺口，运行阻塞来自 python-docx。"
        f"先确认 {python} 的既有环境管理方式；仅在确认是普通 venv 且确需 pip 时，"
        f"才考虑 {python} -m ensurepip，再用同一解释器安装。"
    )


def issue(
    code: str,
    target: str,
    layer: str,
    severity: str,
    repair_policy: str,
    next_action: str,
    verify_stage: str,
) -> dict:
    """创建环境 SOP 使用的结构化问题项。

    Args:
        code (str): 稳定问题代码，用于在 SOP 中查表。
        target (str): 缺失或异常的命令、文件或包名。
        layer (str): 问题所在层级，例如 ``python-package`` 或 ``tex-command``。
        severity (str): ``blocking`` 或 ``optional``。
        repair_policy (str): 修复动作的权限策略。
        next_action (str): Agent 下一步动作代号。
        verify_stage (str): 修复后应重新运行的 ``check_env.py`` stage。

    Returns:
        dict: 面向 Agent 的结构化环境问题。
    """
    return {
        "code": code,
        "target": target,
        "layer": layer,
        "severity": severity,
        "repair_policy": repair_policy,
        "next_action": next_action,
        "verify_stage": verify_stage,
    }


def kpsewhich_exists(filename: str) -> bool:
    """使用 kpsewhich 判断 TeX 文件是否可被当前发行版找到。

    Args:
        filename (str): 需要检查的 TeX 文件名，例如 ``ctexbook.cls``。

    Returns:
        bool: 文件可由 kpsewhich 解析时返回 True。
    """
    if not command_exists("kpsewhich"):
        return False
    process = subprocess.run(
        ["kpsewhich", filename],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        timeout=8,
    )
    return process.returncode == 0 and bool(process.stdout.strip())


def pip_available() -> bool:
    """检查当前 Python 解释器是否能调用 pip。

    Returns:
        bool: ``python -m pip --version`` 成功时返回 True。
    """
    try:
        process = subprocess.run(
            [sys.executable, "-m", "pip", "--version"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=8,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return process.returncode == 0


def python_docx_import_error() -> str | None:
    """验证 python-docx 不仅可发现，而且能够实际导入。

    Returns:
        str | None: 导入成功时为 None，否则为简短错误信息。
    """
    if importlib.util.find_spec("docx") is None:
        return "not_installed"
    try:
        docx_module = importlib.import_module("docx")
    except Exception as exc:
        return f"{type(exc).__name__}: {exc}"
    if not callable(getattr(docx_module, "Document", None)):
        return "docx module does not expose the python-docx Document API"
    return None


def check(stage: str, root: Path = Path("."), project_root: Path | None = None) -> dict:
    """执行 Python、DOCX 和 LaTeX 环境门禁检查。

    Args:
        stage (str): 检查阶段，可为 ``minimal``、``latex``、``qa`` 或 ``all``。
        root: 用户模板根目录，与脚本所在目录无关。
        project_root: 管理依赖的项目或工作区根目录；默认等于 root。

    Returns:
        dict: 流程 A 环境检查结果，包含每个依赖项的状态和修复提示。
    """
    target = environment_target(root, project_root)
    python_supported = sys.version_info >= MINIMUM_PYTHON
    version_text = ".".join(str(part) for part in sys.version_info[:3])
    checks = [
        item(
            "python",
            "passed" if python_supported else "blocked",
            (
                f"Python {version_text} 可运行：{sys.executable}"
                if python_supported
                else f"Python {version_text} 低于最低要求 3.10。"
            ),
        )
    ]
    issues = []
    if not python_supported:
        issues.append(
            issue(
                "python_version_unsupported",
                version_text,
                "python-runtime",
                "blocking",
                "ask_user_before_install",
                "install_supported_python",
                stage,
            )
        )
    if stage in {"minimal", "all"}:
        if target.mismatch:
            checks.append(
                item(
                    "python_environment",
                    "blocked",
                    f"当前环境 {target.prefix} 与目标环境 {target.expected_prefix} 不一致；"
                    "未检查另一环境的 python-docx，也不生成针对它的安装建议。",
                )
            )
            issues.append(
                issue(
                    "python_environment_mismatch",
                    str(target.expected_prefix),
                    "python-runtime",
                    "blocking",
                    "select_existing_environment",
                    "rerun_in_target_environment",
                    "minimal",
                )
            )
        docx_error = None if target.mismatch else python_docx_import_error()
        if docx_error:
            missing = docx_error == "not_installed"
            action, hint = docx_repair_hint(target)
            if not missing:
                action = "inspect_python_docx_import"
                hint = "先核对导入异常、同名 docx 包或文件及损坏依赖，再选择修复动作。" + hint
            checks.append(
                item(
                    "python-docx",
                    "blocked",
                    (
                        "缺少 python-docx，无法预扫描和抽取 DOCX。"
                        if missing
                        else f"python-docx 已安装但导入失败：{docx_error}"
                    ),
                    install_hint=hint,
                )
            )
            issues.append(
                issue(
                    "python_docx_missing" if missing else "python_docx_import_failed",
                    "python-docx",
                    "python-package",
                    "blocking",
                    "ask_user_before_install",
                    action,
                    "minimal",
                )
            )
        elif not target.mismatch:
            checks.append(item("python-docx", "passed", "python-docx 可导入。"))
    if stage in {"latex", "all"}:
        for command in ("xelatex", "biber"):
            if command_exists(command):
                checks.append(item(command, "passed", f"{command} 在 PATH 中。"))
            else:
                checks.append(
                    item(
                        command,
                        "blocked",
                        f"缺少 {command}，流程 C 无法编译。",
                        install_hint="获得用户批准后安装完整 TeX Live 或 MacTeX。",
                    )
                )
                issues.append(
                    issue(
                        "tex_command_missing",
                        command,
                        "tex-command",
                        "blocking",
                        "ask_user_before_install",
                        "install_or_repair_tex_distribution",
                        "latex",
                    )
                )
        if not command_exists("kpsewhich"):
            checks.append(
                item(
                    "kpsewhich",
                    "blocked",
                    "缺少 kpsewhich，无法判断模板核心 TeX 文件是否可用。",
                    install_hint="获得用户批准后修复 TeX 发行版或 PATH。",
                )
            )
            issues.append(
                issue(
                    "tex_command_missing",
                    "kpsewhich",
                    "tex-command",
                    "blocking",
                    "ask_user_before_install",
                    "install_or_repair_tex_distribution",
                    "latex",
                )
            )
        else:
            checks.append(item("kpsewhich", "passed", "kpsewhich 在 PATH 中。"))
            for filename, detail in REQUIRED_TEX_FILES.items():
                try:
                    available = kpsewhich_exists(filename)
                except (OSError, subprocess.TimeoutExpired):
                    available = False
                if available:
                    checks.append(
                        item(
                            f"tex_package_{filename}",
                            "passed",
                            f"{filename} 可由 kpsewhich 找到。",
                        )
                    )
                else:
                    checks.append(
                        item(
                            f"tex_package_{filename}",
                            "blocked",
                            f"缺少 {filename}：{detail}",
                            install_hint="获得用户批准后使用 tlmgr 安装对应 TeX Live 包。",
                        )
                    )
                    issues.append(
                        issue(
                            "tex_core_file_missing",
                            filename,
                            "tex-package",
                            "blocking",
                            "ask_user_before_install",
                            "install_tex_package",
                            "latex",
                        )
                    )
    if stage in {"qa", "all"}:
        for command, detail in QA_TOOLS.items():
            if command_exists(command):
                checks.append(item(command, "passed", f"{command} 在 PATH 中。"))
            else:
                checks.append(
                    item(
                        command,
                        "needs_review",
                        f"缺少 {command}：{detail}",
                        install_hint="可选增强工具；不阻止编译，但会降低 QA 确定性。",
                    )
                )
                issues.append(
                    issue(
                        "qa_tool_missing",
                        command,
                        "qa-tool",
                        "optional",
                        "ask_user_before_install",
                        "install_optional_qa_tool",
                        "qa",
                    )
                )
    status = overall_status(checks)
    if status == "passed" and issues:
        status = "needs_review"
    for problem in issues:
        problem["verify_command"] = target.verify_command(problem.pop("verify_stage"))
    return {
        "flow": "A",
        "gate": f"environment_{stage}",
        "profile": stage,
        "status": status,
        "environment": {
            "root": str(target.root),
            "project_root": str(target.project_root),
            "python": str(target.python),
            "prefix": str(target.prefix),
            "manager": target.manager,
            "declarations": [str(path) for path in target.declarations],
            "expected_prefix": str(target.expected_prefix)
            if target.expected_prefix is not None
            else None,
        },
        "scope": {
            "checked": {
                "minimal": ["python_version", "python_docx_import"],
                "latex": ["python_version", "xelatex", "biber", "kpsewhich", "tex_core_files"],
                "qa": ["python_version", "pdfinfo", "pdftotext"],
                "all": [
                    "python_version",
                    "python_docx_import",
                    "xelatex",
                    "biber",
                    "kpsewhich",
                    "tex_core_files",
                    "pdfinfo",
                    "pdftotext",
                ],
            }[stage],
            "not_checked": [
                "ZUFE-Thesis 模板签名（使用 check_template.py）",
                "DOCX 可读性和内容结构（使用 prescan_docx.py）",
                "workspace 输入和旧输出保护（使用 prepare_workspace.py）",
            ],
        },
        "checks": checks,
        "issues": issues,
        "next_steps": []
        if status == "passed"
        else [
            "向用户说明缺失依赖的影响。",
            "Python 包或 LaTeX 发行版只能在用户明确批准后安装。",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    """解析命令行参数并输出环境检查 JSON。

    Args:
        argv (list[str] | None): 显式命令行参数；None 时读取系统参数。

    Returns:
        int: 环境门禁通过时返回 0，否则返回 2。
    """
    parser = argparse.ArgumentParser(
        description="按阶段检查 ZUFE-Thesis 转换所需的 Python、LaTeX 和 QA 环境。"
    )
    parser.add_argument("--root", type=Path, default=Path("."), help="用户模板根目录。")
    parser.add_argument(
        "--project-root", type=Path, help="依赖项目或工作区根目录，默认与 --root 相同。"
    )
    parser.add_argument(
        "--stage",
        choices=["minimal", "latex", "qa", "all"],
        default="all",
        help="要检查的环境阶段，默认 all。",
    )
    args = parser.parse_args(argv)
    try:
        result = check(args.stage, args.root, args.project_root)
    except (OSError, ValueError) as exc:
        print_json({"status": "blocked", "error": str(exc)})
        return 2
    print_json(result)
    return 2 if result["status"] == "blocked" else 0


if __name__ == "__main__":
    raise SystemExit(main())
