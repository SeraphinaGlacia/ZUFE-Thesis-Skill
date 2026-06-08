---
name: zufe-thesis-typesetter
description: 当用户需要使用 ZUFE-Thesis 模板处理 Word 论文或报告，并交付符合格式、经过检查的 LaTeX/PDF 排版结果时使用。
---

# ZUFE Thesis Typesetter

## 总览

使用此 skill 将 Word 论文转换为 ZUFE-Thesis LaTeX/PDF 交付物。严格按三个流程推进：

- **流程 A**：严格门禁与智能预准备。
- **流程 B**：DOCX 正式抽取、内容清点账本、语义确认与模板写入。
- **流程 C**：编译、诊断、质检与交付说明。

面向非技术用户的主要反馈必须在对话中给出。脚本负责稳定检查、抽取、文件写入、编译和生成机器可读证据。

## 核心契约

必须从 ZUFE-Thesis 模板根目录运行。修改任何文件前，先确认模板签名完整。

标准输入：

```text
workspace/input/thesis.docx
workspace/input/metadata.yaml
```

标准中间产物：

```text
workspace/intermediate/thesis.json
workspace/intermediate/extracted.md
```

标准输出：

```text
main.pdf
workspace/output/report.md
workspace/output/qa_report.md
```

## 流程顺序

按顺序运行流程，不要因为后续脚本可能补救而跳过门禁。

1. **流程 A**：检查模板、workspace、DOCX、metadata、旧输出、Python DOCX 环境、LaTeX/Biber 环境。
2. **流程 B**：把 Word 每个可见或可抽取内容块写入 `thesis.json`；Codex 负责分配语义槽位并向用户确认低置信度内容；脚本只渲染已确认映射。
3. **流程 C**：归档旧编译产物，运行 `xelatex -> biber -> xelatex -> xelatex`，诊断失败，做有限机械修复，并质检新 PDF。

## 脚本使用

所有脚本接受 `--root`，并输出 JSON 或写入 JSON 报告。Codex 使用 JSON 做判断，再把结果翻译成普通用户能理解的简短清单。

- `scripts/check_template.py`：检查 ZUFE-Thesis 模板签名。
- `scripts/prepare_workspace.py`：创建 `workspace/`，把 DOCX 放到标准路径，并可在用户批准后归档旧输出。
- `scripts/check_env.py`：检查 Python、`python-docx`、`xelatex`、`biber` 和模板关键 TeX 包。
- `scripts/prescan_docx.py`：流程 A 的 DOCX 轻量预扫描和 metadata 候选提取。不得生成正式 `thesis.json`。
- `scripts/import_docx.py`：流程 B 正式抽取，生成 `thesis.json` 和 `extracted.md`。
- `scripts/export_assets.py`：抽取 DOCX 媒体到 `Images/word_media/` 并记录证据。
- `scripts/render_basicinfo.py`：把 metadata、摘要和关键词写入 `chapters/basicinfo.tex`。
- `scripts/render_chapters.py`：把已确认章节映射写入 `chapters/*.tex` 和 `chapters/mainbody.tex`。
- `scripts/render_bib.py`：把已确认 BibTeX 写入 `Reference.bib`，不得编造参考文献。
- `scripts/check_flow_b_gate.py`：若仍有未处理、未确认或未渲染源块，则阻止流程 B 完成。
- `scripts/build.py`：归档旧 `main.pdf`，清理临时编译文件，运行固定编译链。
- `scripts/diagnose_build.py`：把构建失败分类为可行动问题。
- `scripts/qa.py`：检查 PDF 新鲜度、文本、关键信号、未解析引用、BibTeX/引用闭环、模板残留和占位符。

## Codex 职责

Codex 负责语义判断，脚本不得替代：

- 判断段落属于章节标题、正文、摘要、参考文献、致谢、附录、图表标题或可丢弃噪声。
- 归并低置信度问题，并向用户确认。
- 在对话中解释卡住的位置、原因和下一步。
- 不静默丢弃内容，不静默错放内容。
- 不从文件名猜测学院、专业、日期、导师或报告类型；metadata 只能来自 Word 证据或用户确认。
- 不把 run 级样式问题当成普通文本问题忽略；上标、下标、表格字号异常都必须在流程 B/C 暴露。
- 流程 C 不修正文档语义；内容归属错误必须退回流程 B。

## 转换质量硬约束

- DOCX 段落不得只保留纯文本；必须保留 run 级 `bold`、`italic`、`superscript`、`subscript` 和字号证据。上标数字必须渲染为 `\textsuperscript{...}`，不得压平成正文普通数字。
- Word 中疑似参考标号的上标数字不得静默改写成普通文本。若要转为正式 `\cite`/`\supercite`，必须先确认参考文献映射；否则至少保留视觉上标。
- 普通正文中的 ASCII 双引号必须转换为 LaTeX 左右引号 ``...''；中文智能引号默认保留。不得对 raw LaTeX、图片路径、引用命令和公式套用正文引号转换。
- 缺失英文摘要或英文关键词时，必须让用户选择：确认留空、手动提供或允许生成；不得默认留空或自动根据中文补写。若用户允许生成，必须先说明这是内容性补写，并在 metadata 中记录授权。
- 生成 `chapters/basicinfo.tex` 时必须写入全局 `\hypersetup{hidelinks,pdfborder={0 0 0},pdfborderstyle={/S/U/W 0}}`，避免图表引用和 URL 在 PDF 中显示彩色链接边框。
- 表格默认使用模板风格字号 `\zihao{5}`。不得无条件使用 `\resizebox{\textwidth}{!}{...}`，因为它会把较窄表格放大并破坏字号。
- 只有表格自然宽度确实超过版心且没有更稳妥的列宽方案时，才允许缩小表格；禁止为了“填满版心”放大表格。
- 脚注、尾注、公式、超链接、批注、修订痕迹、文本框、页眉页脚等暂不自动转换内容必须进入 `unsupported_features`，不得静默忽略。

## 详细参考

- 做流程 A 前，读取 `references/flow-a-gatekeeping.md`。
- 遇到依赖缺失、环境安装或编译环境修复时，读取 `references/environment-setup-and-repair.md`。
- 做流程 B 抽取或渲染前，读取 `references/flow-b-conversion.md`。
- 做流程 C 编译或 QA 前，读取 `references/flow-c-export-and-qa.md`。
- 手动编辑 `thesis.json` 前，读取 `references/thesis-json-schema.md`。

## 用户反馈

非技术用户不需要先打开报告。先在对话中给出：

- 门禁卡在哪里。
- 为什么继续会不安全。
- Codex 可以自动修什么。
- 哪些操作需要用户批准或提供文件。

技术用户需要细节时，再补充报告路径。
