# 流程 B：转换与模糊确认

流程 B 在流程 A 通过后启动，负责对 Word 做正式抽取、结构识别、内容确认和模板写入。流程 B 的结果会进入流程 C 编译与交付。

流程 B 的质量门槛是：无静默丢失、无静默错放。Word 中每个可见或可抽取的内容块，都必须被识别、归属、写入、确认或明确标记丢弃。只要存在未识别、未归属、未写入或高风险未确认内容，流程 B 就阻止完成，不能进入流程 C。

## B.1 边界

流程 B 只接受流程 A 标准化后的输入：

- `workspace/input/thesis.docx`
- `workspace/input/metadata.yaml`

流程 B 不处理任意 Word 路径、环境安装、workspace 创建或旧输出归档。这些都属于流程 A。

流程 B 完成后，当前模板根目录应已被写成用户论文工程，但不运行 `xelatex` 或 `biber`。编译、日志诊断、PDF 质检和最终交付属于流程 C。

## B.2 中间结构与清点账本

`workspace/intermediate/thesis.json` 同时承担正式中间结构和内容清点账本职责。

每个 Word 源块必须记录：

- 唯一 ID。
- 原始顺序。
- 原始类型或候选类型。
- 抽取内容摘要。
- 原始证据：样式名、字号、加粗、居中、编号、空行、图片位置、表格结构、页内顺序等。
- 目标槽位。
- 当前状态。
- 置信度。
- 是否需要用户确认。
- 用户确认结果。
- 丢弃原因，如果被丢弃。
- 渲染结果位置，如果已写入模板。

`workspace/intermediate/extracted.md` 只作为人类和 Codex 辅助阅读材料，不承担审计职责。

## B.3 源块状态机

每个源块至少区分以下状态：

- `mapped`：已经归属到目标槽位，但尚未完成渲染。
- `rendered`：已经写入目标文件或目标资源。
- `needs_confirmation`：需要用户确认后才能继续。
- `discarded_with_reason`：已明确丢弃，并记录原因。
- `blocked`：无法安全归属、丢弃或写入，流程 B 必须停止。

任何 `blocked` 或未处理源块都会阻止流程 B 完成。用户必须确认归属、允许丢弃或修正识别后才能继续。

丢弃不能静默发生。空段、批注、模板说明、页眉页脚残留等可以丢弃，但必须在 `thesis.json` 中记录原因；有风险的丢弃必须进入用户确认清单。

## B.4 内容映射

流程 B 必须建立“源块 -> 模板槽位”的映射。

| Word 内容 | 目标槽位 |
| --- | --- |
| 封面和身份信息补充 | `chapters/basicinfo.tex` |
| 中文摘要、英文摘要、关键词 | `chapters/basicinfo.tex` |
| 正文结构入口 | `chapters/mainbody.tex` |
| 各章各节正文 | `chapters/*.tex` |
| 图片 | `Images/` 和对应章节 `.tex` |
| 表格 | 对应章节 `.tex` |
| 公式 | 对应章节 `.tex` |
| 参考文献数据 | `Reference.bib` |
| 参考文献页面 | 仍由 `misc/reference.tex` 打印 |
| 致谢 | `chapters/acknowledgement.tex` |
| 附录 | `chapters/appendix.tex` |

流程 B 不修改：

- `zufe.cls`
- `main.tex`
- `misc/cover.tex`
- `misc/abstract.tex`
- `misc/reference.tex`

## B.5 结构识别原则

流程 B 不要求用户 Word 遵守任何固定标题样式。

scripts 只采集格式信号，例如样式名、字号、加粗、居中、编号、空行和段落位置。Codex 结合全文语义和格式信号做最终判断。

如果正文段落、图片、表格、公式、参考文献、致谢或附录的归属不清楚，流程 B 必须把问题放入分组风险清单，不能静默归入某个章节。

风险清单一次性列全，但按类型分组展示，例如：

- 章节结构。
- 正文归属。
- 摘要与关键词。
- 图片、表格、公式。
- 参考文献。
- 致谢和附录。
- 可能丢弃的内容。

## B.6 参考文献、图片和表格

参考文献以 Word 抽取为主，尝试转换为 BibTeX；用户额外提供 BibTeX 时再合并。无法可靠转换时，流程 B 标记风险，不编造条目。

图片和表格采用“尽量转换 + 低信心确认”：

- 能抽取就写入 `Images/` 或对应章节 `.tex`。
- 位置、标题、编号、归属不明确时进入确认清单。
- 无法可靠转换时，必须保留源块记录并阻止静默丢失。

## B.7 写入策略

流程 B 直接写当前模板根目录。这个项目库通常是学生下载后的个人模板副本，因此流程 B 默认把当前模板内容改造成该学生论文工程。

流程 B 可以直接覆盖原模板示例章节和示例文献，不做自动备份。恢复模板需要重新下载原始项目。

正文章节文件名使用“数字 + 英文语义名”，例如：

```text
chapters/1_introduction.tex
chapters/2_literature_review.tex
chapters/3_methodology.tex
```

`chapters/mainbody.tex` 按用户确认后的论文结构顺序引用这些章节文件。

## B.8 scripts 与 Codex 分工

scripts 负责稳定抽取、证据记录和文件写入：

- `import_docx.py`：正式抽取 DOCX，生成 `thesis.json` 和 `extracted.md`。
- `render_basicinfo.py`：把 metadata、摘要、关键词写入 `chapters/basicinfo.tex`。
- `render_chapters.py`：把确认后的章节结构写入 `chapters/*.tex` 和 `chapters/mainbody.tex`。
- `export_assets.py`：把 Word 图片和附件写入 `Images/`，并返回 TeX 引用路径。
- `render_bib.py`：把 Word 参考文献和用户 BibTeX 合并写入 `Reference.bib`。

Codex 负责语义判断、正文归属、风险清单、用户确认和低置信度修正。

## B.9 完成门禁

流程 B 完成前必须通过以下检查：

- Word 源块总数与 `thesis.json` 中记录的源块一致。
- 每个非空、非噪声源块都有目标槽位或明确丢弃原因。
- 每个目标槽位都写入成功，例如 `chapters/basicinfo.tex`、`chapters/mainbody.tex`、`chapters/*.tex`、`Reference.bib`、`Images/`。
- 所有低置信度结构问题已经进入分组风险清单并获得用户确认。
- 没有正文段落处于章节归属不明状态。
- 没有图片、表格、公式、参考文献处于已抽取但未放置状态。
- 没有摘要或关键词冲突未确认。
- 生成的章节引用顺序与确认后的论文结构一致。
- 所有 `mapped` 内容都有对应 `rendered` 目标记录。

只有通过这些检查，流程 B 才能把工程交给流程 C。

## B.10 测试场景

- 标准 DOCX：能生成 `thesis.json`、章节文件、`mainbody.tex` 和 `basicinfo.tex`。
- 无规范标题样式 DOCX：Codex 能基于语义和格式信号识别章节，并列出低置信度问题。
- Word 中每个普通正文段落都映射到某个章节文件。
- 正文段落归属不清时，流程 B 阻止完成并要求用户确认。
- 图片抽取成功但标题或位置不清时，流程 B 阻止完成或进入必答确认。
- 表格无法可靠转换时，流程 B 记录源块并阻止静默丢失。
- 模板说明、批注、空段被丢弃时，`thesis.json` 记录丢弃原因。
- 参考文献无法可靠转 BibTeX 时，流程 B 标记风险，不编造条目。
- 渲染完成后，所有 `mapped` 内容都有对应 `rendered` 目标记录。
