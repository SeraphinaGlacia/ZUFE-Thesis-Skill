# 环境安装与修复参考

本文件只服务流程 A 和流程 C 的环境判断。普通用户不需要先阅读本文件；Codex 应把检查结果转成对话中的简短清单。

## 适用规范与原则

- 流程 A 负责检查环境是否足以进入转换；流程 C 在编译失败时判断是否属于环境问题。
- 任何安装、升级、PATH 修改、系统级配置修改都必须先获得用户明确批准。
- 先给最小修复方案，再给完整发行版兜底方案。
- 不把环境问题伪装成 Word 内容问题，也不把 LaTeX 原始日志直接丢给非技术用户。
- Python 包、TeX 发行版、TeX 宏包、系统字体属于不同层级；修复时必须定位到具体层级。
- `check_env.py` 输出 JSON 供 Codex 判断；面向用户时只说明卡在哪里、影响是什么、是否允许 Codex 修。

## 依赖包与环境

### Python 层

- Python 3.10 或更高版本。
- `python-docx`：读取和预扫描 DOCX 的必需包。

第一版不要求 `PyYAML`。`metadata.yaml` 由 skill 内置的轻量解析逻辑读取。

### 命令层

- `xelatex`：使用 XeLaTeX 编译中文模板。
- `biber`：处理 `biblatex` 参考文献。
- `kpsewhich`：检查 TeX 宏包是否能被当前 TeX 发行版找到。
- `tlmgr`：macOS BasicTeX 或 TeX Live 下用于补装 TeX 宏包；Windows MiKTeX 不使用它。

### 模板核心 TeX 文件

这些文件缺失时，流程 A 应阻止进入流程 B 或至少阻止进入流程 C：

- `ctexbook.cls`
- `biblatex.sty`
- `gb7714-2015.bbx`

`check_env.py` 必须用 `kpsewhich` 检查上述文件。

### 模板常见 TeX 包

当前 `zufe.cls` 直接或实际依赖这些 LaTeX 包：

- `ctexbook`
- `geometry`
- `xeCJK`
- `fontspec`
- `titletoc`
- `setspace`
- `graphicx`
- `fancyhdr`
- `pdfpages`
- `booktabs`
- `multirow`
- `caption`
- `tikz`
- `etoolbox`
- `hyperref`
- `xcolor`
- `array`
- `amsmath`
- `amssymb`
- `biblatex`
- `gb7714-2015`
- `algorithm`
- `algpseudocode`
- `float`
- `lipsum`
- `listings`

`zufe.cls` 中有重复加载的包，例如 `setspace`、`caption`、`pdfpages`；环境检查和安装建议只需按唯一包名处理。

### LaTeX 模板项目文件需求

此 skill 必须在已有的 ZUFE-Thesis LaTeX 模板根目录中工作。当前工作目录不是模板根目录时，流程 A 必须先停止；不能在任意空目录或 skill 自身目录中继续转换。

模板根目录必须包含这些硬门禁文件：

```text
main.tex
zufe.cls
Reference.bib
chapters/basicinfo.tex
chapters/mainbody.tex
misc/cover.tex
misc/abstract.tex
misc/originality.tex
misc/reference.tex
simhei.ttf
stsong.ttf
stkaiti.ttf
InitFile/schoolLogo.png
```

这些文件分别承担的作用：

- `main.tex`：模板编译入口，流程 C 固定从它开始编译。
- `zufe.cls`：学校格式规则和宏包加载入口，不由 skill 重写。
- `Reference.bib`：参考文献目标文件，流程 B 只能写入已确认 BibTeX。
- `chapters/basicinfo.tex`：封面、题目、摘要、关键词、报告类型与个人身份信息。
- `chapters/mainbody.tex`：正文章节聚合入口。
- `misc/cover.tex`：封面模板部件。
- `misc/abstract.tex`：摘要页模板部件。
- `misc/originality.tex`：原创性声明模板部件。
- `misc/reference.tex`：参考文献输出模板部件。
- `simhei.ttf`、`stsong.ttf`、`stkaiti.ttf`：模板指定的中文字体文件。
- `InitFile/schoolLogo.png`：封面所需学校标识资源。

这些文件或目录不作为硬门禁：

- `main.pdf`
- `README.md`
- `docs/`
- `papperCode/`
- 样例章节文件
- 样例图片
- `InitFile/anonyLogo.png`

缺少硬门禁文件时，不应通过安装 Python 包或 TeX 包修复。Codex 应提示用户当前目录不像 ZUFE-Thesis 模板根目录，要求用户切换到完整模板项目，或在用户批准后协助补齐模板文件。

### 字体与模板资源

模板根目录必须有这些字体和资源：

- `simhei.ttf`
- `stsong.ttf`
- `stkaiti.ttf`
- `InitFile/schoolLogo.png`

模板还调用系统字体 `Times New Roman`。Windows 通常内置该字体；macOS 若缺失，应先报告为字体环境问题，获得用户确认后再处理。

### QA 可选增强

- `pdftotext`：用于流程 C 抽取 PDF 文本并做文本级 QA。
- `pdfinfo`：用于流程 C 读取 PDF 页数；比扫描原始 PDF 字节更可靠。

缺少 `pdftotext` 或 `pdfinfo` 不阻止 PDF 编译，但会降低 QA 确定性。此时最终状态不得因为 PDF 可生成就自动宣称 `ready_to_submit`，应把文本级或页数级 QA 不完整写入 `qa_report.md`。

## 运用于不同系统的解决问题方案

### macOS

优先顺序：

1. 确认 Python 环境。
2. 确认 `python-docx`。
3. 确认 `xelatex`、`biber`、`kpsewhich`、`tlmgr`。
4. 用 `kpsewhich` 检查模板核心 TeX 文件。
5. 只有具体文件缺失时，才补装对应 TeX 包。
6. BasicTeX 修复成本过高或反复失败时，才建议 MacTeX 完整安装。

常用检查命令：

```bash
python -c "import sys; print(sys.version)"
python -c "import docx; print(docx.__version__)"
which xelatex biber kpsewhich tlmgr
xelatex --version
biber --version
kpsewhich ctexbook.cls
kpsewhich biblatex.sty
kpsewhich gb7714-2015.bbx
```

Python 包缺失时，在用户当前 Python 环境中修复：

```bash
python -m pip install python-docx
```

BasicTeX 已安装但命令不可见时，优先检查 PATH：

```bash
echo "$PATH"
ls /Library/TeX/texbin/xelatex
ls /Library/TeX/texbin/kpsewhich
```

不要静默修改 shell 配置。需要写入 `~/.zshrc`、`~/.bashrc` 或其他配置文件时，必须先说明影响并获得批准。

BasicTeX 缺 TeX 包时，按日志和 `kpsewhich` 结果补装。常见 TeX Live 包名包括：

```bash
sudo tlmgr install ctex biblatex biblatex-gb7714-2015
sudo tlmgr install geometry xecjk titlesec setspace graphics fancyhdr pdfpages
sudo tlmgr install booktabs multirow caption pgf etoolbox hyperref xcolor tools
sudo tlmgr install amsmath amsfonts algorithms algorithmicx float lipsum listings
```

如果 `tlmgr` 报版本仓库不匹配、权限错误或包名不可用，不要连续试错。应把错误分类为环境问题，向用户说明可选路径：

- 继续按日志精确修复 BasicTeX。
- 改装 MacTeX 完整发行版。

MacTeX 体积较大，只能作为用户明确批准后的兜底方案。

### Windows

优先顺序：

1. 确认 Python 环境。
2. 确认 `python-docx`。
3. 确认 TeX 发行版。
4. 确认 `xelatex` 和 `biber` 在 PATH 中。
5. 用 `kpsewhich` 检查模板核心 TeX 文件。
6. 编译失败时按日志补装具体包，不做全局猜测。

常用检查命令：

```powershell
python --version
python -c "import docx; print(docx.__version__)"
where xelatex
where biber
where kpsewhich
xelatex --version
biber --version
kpsewhich ctexbook.cls
kpsewhich biblatex.sty
kpsewhich gb7714-2015.bbx
```

Python 包缺失时，在用户当前 Python 环境中修复：

```powershell
python -m pip install python-docx
```

Windows 优先建议 MiKTeX，因为它对非技术用户更容易处理缺包。安装或修复 MiKTeX 时应确认：

- `xelatex` 可在 PowerShell 中找到。
- `biber` 可在 PowerShell 中找到。
- MiKTeX Console 中允许安装缺失包，推荐设置为先询问用户。
- `kpsewhich ctexbook.cls`、`kpsewhich biblatex.sty`、`kpsewhich gb7714-2015.bbx` 有输出。

如果用户选择 TeX Live for Windows，也可以使用完整安装；但安装体积和耗时必须提前说明。

Windows 上 PATH 问题常见。若 `xelatex` 已安装但 `where xelatex` 找不到，应先修 PATH，而不是重复安装 TeX 发行版。

## 安全边界

- 不默认安装 6GB 以上完整 TeX 发行版。
- 不默认执行 `sudo`、管理员 PowerShell、全局升级或 PATH 写入。
- 不默认运行 `tlmgr update --all`。
- 不默认覆盖用户已有 Python 环境。
- 不默认删除或替换已有 TeX 发行版。
- 不把 BasicTeX、MacTeX、MiKTeX、TeX Live 混装问题静默处理为普通缺包。
- 不让非技术用户自行阅读 `main.log`、`main.blg` 后决定修复。
- 不在流程 B 中安装依赖；环境修复属于流程 A 或流程 C 诊断后的用户批准动作。

## 修复后验证策略

环境修复后必须重新验证，而不是直接继续。

Python 层修复后运行：

```bash
python -c "import docx; print(docx.__version__)"
python output/zufe-thesis-typesetter/scripts/check_env.py --root . --stage minimal
```

LaTeX 层修复后运行：

```bash
which xelatex biber kpsewhich
xelatex --version
biber --version
kpsewhich ctexbook.cls
kpsewhich biblatex.sty
kpsewhich gb7714-2015.bbx
python output/zufe-thesis-typesetter/scripts/check_env.py --root . --stage latex
```

Windows 使用：

```powershell
where xelatex
where biber
where kpsewhich
xelatex --version
biber --version
kpsewhich ctexbook.cls
kpsewhich biblatex.sty
kpsewhich gb7714-2015.bbx
python output/zufe-thesis-typesetter/scripts/check_env.py --root . --stage latex
```

流程 A 场景下，修复后继续执行 Word 轻量预扫描，确认 DOCX 可读。

流程 C 场景下，修复后重新运行固定编译链：

```text
xelatex -interaction=nonstopmode -halt-on-error -file-line-error main.tex
biber main
xelatex -interaction=nonstopmode -halt-on-error -file-line-error main.tex
xelatex -interaction=nonstopmode -halt-on-error -file-line-error main.tex
```

如果编译成功，再运行 `qa.py`。如果仍失败，必须把失败分类为：

- `mechanical_fixable`
- `return_to_flow_b`
- `user_input_required`
- `environment_issue`
- `unclassified_failure`

所有修复动作、失败分类、重新验证结果都应写入 `workspace/output/report.md`。PDF 文本级 QA 不完整时，还应写入 `workspace/output/qa_report.md`。
