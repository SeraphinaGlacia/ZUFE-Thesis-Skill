# 环境检测 SOP

本文件是环境判断的默认入口。Agent 先按本文件执行；只有需要平台命令、安装细节、PATH 修复或 TeX 包补装时，才读取 `environment-setup-and-repair.md`。

## 总原则

- 不自动安装、升级、写 PATH、改 pip 全局配置或执行管理员命令；必须先获得用户明确批准。
- 不把模板文件缺失当成环境问题。模板签名失败时，先回到流程 A 的模板根目录检查。
- 不把 QA 可选工具缺失当成编译阻塞。`pdfinfo`、`pdftotext` 缺失只降低 QA 确定性。
- 修复后必须运行 `check_env.py` 返回的 `verify_command`，不能直接继续。
- 面向用户只说卡在哪里、影响是什么、是否允许 Agent 修复；不要直接丢 LaTeX 日志。

## 启动前提

`check_env.py` 只有在某个 Python 已经能够启动后才能运行。若 `python` 和 `python3` 都找不到，先用系统命令确认 Python 是否存在；此时不要假装脚本能够自行安装运行时。找到解释器后，后续安装和 `verify_command` 必须使用检查结果中的同一个 `sys.executable`，避免把依赖装进另一套 Python。

`check_env.py` 只检查所选 profile 的运行依赖。它明确不检查模板签名、DOCX 可读性、workspace 输入和旧输出保护；这些步骤仍分别由 `check_template.py`、`prescan_docx.py` 和 `prepare_workspace.py` 负责。

## Profile

| Profile | 命令 | 作用 | 阻塞策略 |
| --- | --- | --- | --- |
| `minimal` | `python "<skill-root>/scripts/check_env.py" --root . --stage minimal` | 检查读取 Word 所需的 Python 与 `python-docx` | 失败则不能预扫描 DOCX |
| `latex` | `python "<skill-root>/scripts/check_env.py" --root . --stage latex` | 检查 PDF 编译所需的 `xelatex`、`biber` 和核心 TeX 文件 | 失败则不能进入编译 |
| `qa` | `python "<skill-root>/scripts/check_env.py" --root . --stage qa` | 检查 `pdfinfo`、`pdftotext` 等 QA 增强工具 | 缺失不阻塞编译，只记录 QA 降级 |
| `all` | `python "<skill-root>/scripts/check_env.py" --root . --stage all` | 汇总以上运行依赖；适合最终复查，不替代其他流程 A 门禁 | 任一必需层失败则阻塞 |

`<skill-root>` 表示当前已加载的 `SKILL.md` 所在目录；`.` 表示当前打开的 ZUFE-Thesis 模板根目录。Skill 可以全局或项目级安装，不要把两者当成同一个路径。

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
| `python_docx_missing` | 当前 Python 缺少 `python-docx`，无法读取 Word | 说明影响，询问是否允许安装；先短超时默认源，失败再用清华镜像；修完跑 `verify_command` |
| `python_docx_import_failed` | 已发现 `python-docx`，但实际导入异常 | 报告简短异常；优先修复当前解释器中的冲突或损坏安装，不要换环境猜测 |
| `pip_unavailable` | 当前解释器不能调用 pip | 先修复同一解释器的 pip；不能直接执行后续 python-docx 安装命令 |
| `tex_command_missing` | 缺少 `xelatex`、`biber` 或 `kpsewhich` | 说明这是 TeX 发行版或 PATH 问题；缺 `kpsewhich` 时不得继续推断所有核心包都缺失 |
| `tex_core_file_missing` | `kpsewhich` 找不到模板核心 TeX 文件 | 不重装全部；用户批准后补具体 TeX 包；修完跑 `verify_command` |
| `qa_tool_missing` | 缺少 `pdfinfo` 或 `pdftotext` | 不阻塞编译；询问是否要安装增强 QA，或在 `qa_report.md` 记录 QA 降级 |

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
