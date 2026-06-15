# 环境检测 SOP

本文件是环境判断的默认入口。Agent 先按本文件执行；只有需要平台命令、安装细节、PATH 修复或 TeX 包补装时，才读取 `environment-setup-and-repair.md`。

## 总原则

- 不自动安装、升级、写 PATH、改 pip 全局配置或执行管理员命令；必须先获得用户明确批准。
- 不把模板文件缺失当成环境问题。模板签名失败时，先回到流程 A 的模板根目录检查。
- 不把 QA 可选工具缺失当成编译阻塞。`pdfinfo`、`pdftotext` 缺失只降低 QA 确定性。
- 修复后必须运行 `check_env.py` 返回的 `verify_command`，不能直接继续。
- 面向用户只说卡在哪里、影响是什么、是否允许 Agent 修复；不要直接丢 LaTeX 日志。

## Profile

| Profile | 命令 | 作用 | 阻塞策略 |
| --- | --- | --- | --- |
| `minimal` | `python zufe-thesis-typesetter/scripts/check_env.py --root . --stage minimal` | 检查读取 Word 所需的 Python 与 `python-docx` | 失败则不能预扫描 DOCX |
| `latex` | `python zufe-thesis-typesetter/scripts/check_env.py --root . --stage latex` | 检查 PDF 编译所需的 `xelatex`、`biber` 和核心 TeX 文件 | 失败则不能进入编译 |
| `qa` | `python zufe-thesis-typesetter/scripts/check_env.py --root . --stage qa` | 检查 `pdfinfo`、`pdftotext` 等 QA 增强工具 | 缺失不阻塞编译，只记录 QA 降级 |

## 流程 A 环境顺序

1. 模板签名通过后，运行 `--stage minimal`。
2. `minimal` 通过后，运行 `prescan_docx.py` 读取 Word。
3. metadata 确认和旧输出保护完成后，运行 `--stage latex`。
4. `latex` 通过后，才能进入流程 B/C 的生成和编译准备。
5. `--stage qa` 只在流程 C 编译前或 QA 前运行；失败不阻止编译。

## Issue Code 决策表

| code | 含义 | Agent 下一步 |
| --- | --- | --- |
| `python_docx_missing` | 当前 Python 缺少 `python-docx`，无法读取 Word | 说明影响，询问是否允许安装；先短超时默认源，失败再用清华镜像；修完跑 `verify_command` |
| `tex_command_missing` | 缺少 `xelatex` 或 `biber`，无法编译 PDF | 说明这是 TeX 发行版或 PATH 问题；用户批准后按平台修复；修完跑 `verify_command` |
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

- 需要 macOS / Windows 具体安装命令。
- 需要处理 PATH 找不到已安装 TeX 的情况。
- `pip`、`tlmgr`、MiKTeX 或 TeX Live 安装失败。
- 需要解释 BasicTeX、MacTeX、MiKTeX、TeX Live 的选择成本。

读取长参考时，只读相关小节，不要整篇重扫。
