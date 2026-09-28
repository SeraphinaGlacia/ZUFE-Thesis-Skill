# 环境检测 SOP

本文件是环境判断的默认入口。Agent 先按本文件执行；只有需要平台命令、安装细节、PATH 修复或 TeX 包补装时，才读取 `environment-setup-and-repair.md`。

## 总原则

- 不自动安装、升级、写 PATH、改 pip 全局配置或执行管理员命令；必须先获得用户明确批准。
- 不把模板文件缺失当成环境问题。模板签名失败时，先回到流程 A 的模板根目录检查。
- 不把 QA 可选工具缺失当成编译阻塞。`pdfinfo`、`pdftotext` 缺失只降低 QA 确定性。
- 修复后必须运行 `check_env.py` 返回的 `verify_command`，不能直接继续。
- 面向用户只说卡在哪里、影响是什么、是否允许 Agent 修复；不要直接丢 LaTeX 日志。

## 启动前提

`check_env.py` 需要已有 Python ≥ 3.10 才能启动。先确定用户模板根目录、管理依赖的项目和所选解释器，不能因为脚本存放在 Skill 中就使用 Skill 开发仓库的环境。没有可启动解释器时报告缺口，不为了诊断自动安装。

优先直接调用目标项目现有的 `.venv/bin/python`（Windows 为 `.venv/Scripts/python.exe`），或已确认的 Conda/其他环境解释器。不要用可能同步依赖的普通 `uv run` 做诊断；直接调用解释器不需要 pip。

```bash
"/目标项目/.venv/bin/python" -B "<skill-root>/scripts/check_env.py" \
  --root "/目标模板" --project-root "/目标项目" --stage minimal
```

`--project-root` 默认等于 `--root`；模板在依赖工作区子目录时显式指定其管理根目录。脚本只读取该目录的项目声明，不向父目录或 Skill 源码目录猜测。输出 `environment` 记录根目录、解释器、环境前缀、管理器证据；uv 由 `uv.lock`、`uv.toml` 或 `[tool.uv]` 标记识别。依赖是否已声明、所属 group/extra 和复杂工作区配置仍须读取声明确认，不靠包名文本命中推断。

uv 默认目标是项目 `.venv`；既有自定义环境通过 `UV_PROJECT_ENVIRONMENT` 明确指定，输出及复查命令会保留该路径。当前解释器与目标环境不一致时先切回目标解释器，不检查错误环境中的 docx，也不向它安装。目标环境不存在时说明缺口，不能用开发仓库的包冒充通过。

后续抽取、安装和修复后验证必须使用同一目标解释器。`verify_command` 含绝对模板路径、依赖项目路径和解释器路径，换工作目录后也应复查同一目标。

`check_env.py` 只检查所选 profile 的运行依赖。它明确不检查模板签名、DOCX 可读性、workspace 输入和旧输出保护；这些步骤仍分别由 `check_template.py`、`prescan_docx.py` 和 `prepare_workspace.py` 负责。

## Profile

| Profile | 命令 | 作用 | 阻塞策略 |
| --- | --- | --- | --- |
| `minimal` | `python "<skill-root>/scripts/check_env.py" --root . --stage minimal` | 检查读取 Word 所需的 Python 与 `python-docx` | 失败则不能预扫描 DOCX |
| `latex` | `python "<skill-root>/scripts/check_env.py" --root . --stage latex` | 检查 PDF 编译所需的 `xelatex`、`biber` 和核心 TeX 文件 | 失败则不能进入编译 |
| `qa` | `python "<skill-root>/scripts/check_env.py" --root . --stage qa` | 检查 `pdfinfo`、`pdftotext` 等 QA 增强工具 | 缺失不阻塞编译，只记录 QA 降级 |
| `all` | `python "<skill-root>/scripts/check_env.py" --root . --stage all` | 汇总以上运行依赖；适合最终复查，不替代其他流程 A 门禁 | 任一必需层失败则阻塞 |

表中的 `python` 均替换为上面确认的解释器绝对路径。`<skill-root>` 表示当前已加载的 `SKILL.md` 所在目录；`.` 表示当前打开的 ZUFE-Thesis 模板根目录。Skill 可以全局或项目级安装，不要把两者当成同一个路径。

## 流程 A 环境顺序

1. 模板签名通过后，运行 `--stage minimal`。
2. `minimal` 通过后，运行 `prescan_docx.py` 读取 Word。
3. metadata 确认和旧输出保护完成后，运行 `--stage latex`。
4. `latex` 通过后，才能进入流程 B/C 的生成和编译准备。
5. `--stage qa` 只在流程 C 编译前或 QA 前运行；失败不阻止编译。

## Issue Code 决策表

| code | 含义 | Agent 下一步 |
| --- | --- | --- |
| `python_version_unsupported` | 当前解释器低于 Python 3.10 | 说明版本边界；用户批准后安装或切换解释器，再使用新解释器运行检查 |
| `python_environment_mismatch` | 检查解释器不属于目标项目环境 | 用 `verify_command` 指向的既有解释器重查；环境不存在时报告缺口，不自动创建 |
| `python_docx_missing` | 目标 Python 缺少 `python-docx`，无法读取 Word | 读取项目声明，按下述管理器分支修复；修完跑 `verify_command` |
| `python_docx_import_failed` | 已发现 `python-docx`，但实际导入异常 | 报告简短异常；优先修复当前解释器中的冲突或损坏安装，不要换环境猜测 |
| `tex_command_missing` | 缺少 `xelatex`、`biber` 或 `kpsewhich` | 说明这是 TeX 发行版或 PATH 问题；缺 `kpsewhich` 时不得继续推断所有核心包都缺失 |
| `tex_core_file_missing` | `kpsewhich` 找不到模板核心 TeX 文件 | 不重装全部；用户批准后补具体 TeX 包；修完跑 `verify_command` |
| `qa_tool_missing` | 缺少 `pdfinfo` 或 `pdftotext` | 不阻塞编译；询问是否要安装增强 QA，或在 `qa_report.md` 记录 QA 降级 |

缺 pip 不是运行依赖问题，不再输出阻塞性的 `pip_unavailable`。docx 可导入时直接通过；docx 缺失时才评估安装方式：

- uv 项目：已声明时按锁文件及所属组/extra 同步；未声明且任务需要持久依赖时用 `uv add`。命令绑定 `environment.project_root`、`environment.prefix` 和 `environment.python`；不先修 pip。
- Conda、Poetry、PDM 或管理器尚未确定的 pyproject 项目：先核对既有管理方式与环境路径，再修目标项目，不绕过其声明直接全局 pip 安装。
- 普通 venv/requirements 环境：用所选解释器的 `-m pip`；若无 pip 但已有 uv，可用 `uv pip install --python <同一解释器>`。两者都不可用时再判断安装器如何补齐，不能推断环境已损坏。

## 用户提示模板

```text
环境检查停在：<code / target>
影响：<为什么不能继续或为什么 QA 会降级>
建议：<next_action 的普通用户表述>
需要你确认：是否允许 Agent 执行修复命令？
```

如果 `severity=optional`，提示应改为：

```text
这不是阻塞问题。缺少 <target> 只会降低 QA 确定性；你可以先继续编译，也可以允许 Agent 安装可选工具。
```

## 何时读取长参考

- 需要 macOS / Windows / Linux 或云环境的具体处理方法。
- 需要处理 PATH 找不到已安装 TeX 的情况。
- `pip`、`tlmgr`、MiKTeX 或 TeX Live 安装失败。
- 需要解释 BasicTeX、MacTeX、MiKTeX、TeX Live 的选择成本。

读取长参考时，只读相关小节，不要整篇重扫。
