---
name: zufe-thesis-typesetter
description: 当用户需要使用 ZUFE-Thesis 模板处理 Word 论文或报告，并交付符合格式、经过检查的 LaTeX/PDF 排版结果时使用。
---

# ZUFE Thesis Typesetter

## 总览

使用此 Skill 将 Word 论文转换为 ZUFE-Thesis LaTeX/PDF 交付物。严格按三个流程推进：

- **流程 A**：严格门禁与智能预准备。
- **流程 B**：DOCX 正式抽取、内容清点账本、语义确认与模板写入。
- **流程 C**：编译、诊断、质检与交付说明。

面向非技术用户的主要反馈必须在对话中给出。脚本负责稳定检查、抽取、文件写入、编译和生成机器可读证据。

## 核心契约

必须从 ZUFE-Thesis 模板根目录运行。修改任何文件前，先确认模板签名完整。

如果用户尚未准备模板项目，先说明本 Skill 依赖原始 ZUFE-Thesis LaTeX 模板，并按下面顺序处理：

1. 默认引导用户使用原始模板 GitHub 仓库：`https://github.com/sqsssq/ZUFE-Thesis`。
2. 如果 GitHub 因网络环境不可用，可在用户确认后改用国内备用链接：`https://gitee.com/cwf818/ZUFE-Thesis`。
3. 如果 GitHub 和 Gitee 都不可用，停止转换，要求用户提供模板压缩包、已解压的完整模板目录，或其他可信获取方式。

Agent 可以在用户确认后协助下载、解压或切换到模板根目录，但不得静默跳过模板准备，也不得在空目录、本 Skill 仓库或缺失模板签名的目录中继续转换。

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
2. **流程 B**：把 Word 每个可见或可抽取内容块写入 `thesis.json`；Agent 负责分配语义槽位并向用户确认低置信度内容；脚本只渲染已确认映射。
3. **流程 C**：再次确认流程 B 门禁和输入指纹，归档旧编译产物，运行 `xelatex -> biber -> xelatex -> xelatex`，诊断失败，做有限机械修复，并质检新 PDF。

## 详细参考（`references/`）

- 做流程 A 前，读取 `references/flow-a-gatekeeping.md`。
- 做环境判断或修复时，先读取 `references/environment-sop.md`。
- 只有需要平台命令、安装细节、PATH 修复或 TeX 包补装时，才读取 `references/environment-setup-and-repair.md`。
- 做流程 B 抽取或渲染前，读取 `references/flow-b-conversion.md`。
- 做流程 C 编译或 QA 前，读取 `references/flow-c-export-and-qa.md`。
- 手动编辑 `thesis.json` 前，读取 `references/thesis-json-schema.md`。

## 脚本使用（`scripts/`）

所有可执行脚本接受 `--root`，并输出 JSON 或写入 JSON 报告。先以当前已加载的 `SKILL.md` 所在目录作为 Skill 根目录，从该目录解析 `scripts/`，再把完整的 ZUFE-Thesis 模板根目录传给 `--root`；不要假定 Skill 文件夹位于模板工作区内。高数据量命令的 stdout 只给有界摘要和完整报告路径；Agent 先读摘要，只在需要具体证据时分页查询或读取报告。正常执行优先使用已文档化的 CLI，只有调试或维护脚本时才读取源码。

- `scripts/check_template.py`：检查 ZUFE-Thesis 模板签名。
- `scripts/prepare_workspace.py`：创建 `workspace/`，把 DOCX 放到标准路径，并可在用户批准后归档旧输出。
- `scripts/check_env.py`：按 `--stage` 检查 Python、`python-docx`、`xelatex`、`biber`、模板关键 TeX 包和 QA 工具；它不替代模板签名或 DOCX 可读性检查。
- `scripts/prescan_docx.py`：流程 A 的 DOCX 轻量预扫描和 metadata 候选提取。不得生成正式 `thesis.json`。
- `scripts/import_docx.py`：流程 B 正式抽取，生成 `thesis.json` 和 `extracted.md`。
- `scripts/ledger.py`：只读汇总、分页查询源块并生成带前后文的标题候选大纲；不得用它绕过 Agent 的语义判断。
- `scripts/export_assets.py`：核对源 DOCX 指纹后，抽取媒体到 `Images/word_media/` 并记录证据。
- `scripts/render_basicinfo.py`：把 metadata、摘要和关键词写入 `chapters/basicinfo.tex`。
- `scripts/render_chapters.py`：在拒绝重复章节目标和无效图片资源后，把已确认章节映射写入 `chapters/*.tex` 和 `chapters/mainbody.tex`。
- `scripts/render_bib.py`：只有所有参考文献项均已确认时才原子写入 `Reference.bib`，不得编造或部分覆盖参考文献。
- `scripts/check_flow_b_gate.py`：若仍有未处理、未确认或未渲染源块，则阻止流程 B 完成。
- `scripts/build.py`：强制重跑流程 B 门禁，通过后才归档旧 `main.pdf`、清理临时文件并运行固定编译链。
- `scripts/diagnose_build.py`：把构建失败分类为可行动问题。
- `scripts/qa.py`：核对构建所用账本与当前输入，再检查固定编译链、PDF 新鲜度、文本、关键信号、引用、模板残留和占位符；通过后仍须人工视觉检查。

## Agent 职责

Agent 负责语义判断，脚本不得替代：

- 判断段落属于章节标题、正文、摘要、参考文献、致谢、附录、图表标题或可丢弃噪声。
- 归并低置信度问题，并向用户确认。
- 在对话中解释卡住的位置、原因和下一步。
- 不静默丢弃内容，不静默错放内容。
- 不从文件名猜测学院、专业、日期、导师或报告类型；metadata 只能来自 Word 证据或用户确认。
- 不把 run 级样式问题当成普通文本问题忽略；上标、下标、表格字号异常都必须在流程 B/C 暴露。
- 流程 C 不修正文档语义；内容归属错误必须退回流程 B。
- 处理标题前，先通读全文并根据内容关系重建完整大纲；不能仅凭段落样式、编号外观或局部上下文逐段猜测标题及其层级。
- 对每个标题判断它是否属于真正的文章结构，并检查上下级关系、同级并列关系和出现顺序是否连贯；脚本候选、Word 样式和原文编号只能提供线索，不能替代语义判断。
- 区分标题正文与原文手写编号。确认 `第一章`、`1.1`、`一、` 等内容只是人工编号后，从最终标题文字中去除，只保留标题正文，再由 LaTeX 按已经确认的层级自动编号；不得让原文编号与 LaTeX 编号同时出现。

## 转换质量硬约束

- DOCX 段落不得只保留纯文本；必须保留 run 级 `bold`、`italic`、`superscript`、`subscript` 和字号证据。上标数字必须渲染为 `\textsuperscript{...}`，不得压平成正文普通数字。
- Word 中疑似参考标号的上标数字不得静默改写成普通文本。若要转为正式 `\cite`/`\supercite`，必须先确认参考文献映射；否则至少保留视觉上标。
- Word 正文中的手写图表编号，例如 `图2.1`、`图 2.1`、`表1.2`，不得原样带入最终章节源码。Agent 必须确认它对应的图表块，给图表写入稳定 `label`，并把正文改写为 `图~\ref{...}` 或 `表~\ref{...}`；无法确认时阻塞流程 B。
- 普通正文中的 ASCII 双引号必须转换为 LaTeX 左右引号 ``...''；中文智能引号默认保留。不得对 raw LaTeX、图片路径、引用命令和公式套用正文引号转换。
- 缺失英文摘要或英文关键词时，必须让用户选择：确认留空、手动提供或允许生成；不得默认留空或自动根据中文补写。若用户允许生成，必须先说明这是内容性补写，并在 metadata 中记录授权。
- 生成 `chapters/basicinfo.tex` 时必须写入全局 `\hypersetup{hidelinks,pdfborder={0 0 0},pdfborderstyle={/S/U/W 0}}`，避免图表引用和 URL 在 PDF 中显示彩色链接边框。
- 映射到 `chapters/basicinfo.tex` 的源块必须声明 `metadata_fields`，且脚本必须核对整个源块都有去向；不能被宏承接的文字须改映射，或用 `metadata_excluded_text` 和 `metadata_exclusion_reason` 显式记录。
- 表格默认使用模板风格字号 `\zihao{5}`。不得无条件使用 `\resizebox{\textwidth}{!}{...}`，因为它会把较窄表格放大并破坏字号。
- 只有表格自然宽度确实超过版心且没有更稳妥的列宽方案时，才允许缩小表格；禁止为了“填满版心”放大表格。
- 脚注、尾注、公式、超链接、批注、修订痕迹、文本框、内容控件、外部导入内容、链接图片、Word 域/自动编号、图表/SmartArt、OLE 对象和页眉页脚等暂不自动转换内容必须进入 `unsupported_features`，不得静默忽略。

## 踩坑清单

- 标题编号重复与层级误判：这是全文语义理解问题，不能交给正则或其他机械规则裁决。Agent 必须先结合全文内容、标题候选及其前后文重新整理文章结构，统一确认哪些内容是真正的标题以及各自层级，再识别并去除标题中已有的手写编号。写入 LaTeX 后，还要复核最终大纲和编号是否连续、是否与文章逻辑一致；仍有歧义时向用户确认。
- 图片题注误填：图片媒体路径和源块摘要不得自动充当图题；`caption` 只能来自 Word 证据或 Agent/用户确认。
- 引用类型误判：`reference_rewrites` 必须显式写入 `target_kind` 或 `prefix`；类型缺失时不得默认按图片引用生成 `图~\ref{...}`。

## 人机协作

非技术用户不需要先打开报告。先在对话中给出：

- 门禁卡在哪里。
- 为什么继续会不安全。
- Agent 可以自动修什么。
- 哪些操作需要用户批准或提供文件。

技术用户需要细节时，再补充报告路径。
