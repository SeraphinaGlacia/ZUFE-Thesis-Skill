---
name: zufe-thesis-typesetter
description: 将用户的 Word 论文或报告转换为 ZUFE-Thesis LaTeX 工程并完成 PDF 质检。当 Codex 需要运行 A/B/C 论文工作流时使用：验证 ZUFE 模板根目录，准备 workspace/input/thesis.docx 和 metadata.yaml，抽取 DOCX 到 thesis.json 且避免静默丢失，写入模板文件，使用 xelatex/biber 编译，诊断失败并生成 QA 报告。
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
- `scripts/check_env.py`：检查 Python、`python-docx`、`xelatex`、`biber`。
- `scripts/prescan_docx.py`：流程 A 的 DOCX 轻量预扫描和 metadata 候选提取。不得生成正式 `thesis.json`。
- `scripts/import_docx.py`：流程 B 正式抽取，生成 `thesis.json` 和 `extracted.md`。
- `scripts/export_assets.py`：抽取 DOCX 媒体到 `Images/word_media/` 并记录证据。
- `scripts/render_basicinfo.py`：把 metadata、摘要和关键词写入 `chapters/basicinfo.tex`。
- `scripts/render_chapters.py`：把已确认章节映射写入 `chapters/*.tex` 和 `chapters/mainbody.tex`。
- `scripts/render_bib.py`：把已确认 BibTeX 写入 `Reference.bib`，不得编造参考文献。
- `scripts/check_flow_b_gate.py`：若仍有未处理、未确认或未渲染源块，则阻止流程 B 完成。
- `scripts/build.py`：归档旧 `main.pdf`，清理临时编译文件，运行固定编译链。
- `scripts/diagnose_build.py`：把构建失败分类为可行动问题。
- `scripts/qa.py`：检查 PDF 新鲜度、文本、关键信号、未解析引用、模板残留和占位符。

## Codex 职责

Codex 负责语义判断，脚本不得替代：

- 判断段落属于章节标题、正文、摘要、参考文献、致谢、附录、图表标题或可丢弃噪声。
- 归并低置信度问题，并向用户确认。
- 在对话中解释卡住的位置、原因和下一步。
- 不静默丢弃内容，不静默错放内容。
- 不把 run 级样式问题当成普通文本问题忽略；上标、下标、表格字号异常都必须在流程 B/C 暴露。
- 流程 C 不修正文档语义；内容归属错误必须退回流程 B。

## 详细参考

- 做流程 A 前，读取 `references/flow-a-gatekeeping.md`。
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
