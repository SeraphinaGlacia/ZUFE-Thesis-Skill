# 流程 B：转换、清点、确认与写入

流程 B 只在流程 A 通过后启动。质量门槛是：无静默丢失、无静默错放。

Word 中每个可见或可抽取内容块，都必须被识别、归属、写入、确认或明确记录丢弃原因。只要存在未识别、未归属、未写入或高风险未确认内容，流程 B 就没有完成，不能进入流程 C。

## 输入

```text
workspace/input/thesis.docx
workspace/input/metadata.yaml
```

流程 B 不创建 workspace，不安装依赖，不处理任意 Word 路径，也不归档旧输出。

## 清点账本

`workspace/intermediate/thesis.json` 同时是正式中间结构和内容清点账本。每个源块需要记录：

- 稳定 ID。
- 原始顺序。
- 原始类型或候选类型。
- 文本或内容摘要。
- 抽取证据，例如样式、加粗、字号、对齐、编号、表格形状、图片路径和原始位置。
- 目标槽位。
- 当前状态。
- 置信度。
- 确认状态。
- 丢弃原因，如果被丢弃。
- 渲染结果，如果已写入。

`workspace/intermediate/extracted.md` 只作为人类和 Codex 辅助阅读材料，不承担审计职责。

## 源块状态

允许的源块状态：

- `mapped`：已经归属到目标，但尚未渲染。
- `rendered`：已经写入目标文件或资源。
- `needs_confirmation`：需要用户或 Codex 明确确认。
- `discarded_with_reason`：已经明确丢弃，并记录原因。
- `blocked`：无法安全归属、丢弃或写入。

任何 `blocked`、`needs_confirmation` 或未处理源块都会阻止流程 B 完成。

## 模板槽位

把 Word 内容映射到：

| 内容 | 目标 |
| --- | --- |
| 封面和身份字段 | `chapters/basicinfo.tex` |
| 中英文摘要和关键词 | `chapters/basicinfo.tex` |
| 正文结构入口 | `chapters/mainbody.tex` |
| 章节和小节 | `chapters/*.tex` |
| 图片 | `Images/` 加对应章节 `.tex` 引用 |
| 表格 | 对应章节 `.tex` |
| 公式 | 对应章节 `.tex` |
| 参考文献数据 | `Reference.bib` |
| 参考文献页面 | `misc/reference.tex` 负责打印 |
| 致谢 | `chapters/acknowledgement.tex` |
| 附录 | `chapters/appendix.tex` |

不要修改 `zufe.cls`、`main.tex`、`misc/cover.tex`、`misc/abstract.tex` 或 `misc/reference.tex`。

## Codex 与脚本分工

脚本采集证据并做确定性写入。Codex 做语义判断、槽位分配、风险归并和用户确认。

脚本不得编造参考文献，不得静默丢弃表格、图片或公式，也不得在低置信度时擅自猜测章节归属。

## 完成门禁

进入流程 C 前，运行 `scripts/check_flow_b_gate.py`。只有满足以下条件，流程 B 才通过：

- 源块数量与清点账本一致。
- 每个非空、非噪声源块都已渲染或带原因丢弃。
- 每个目标槽位存在并有渲染证据。
- 低置信度结构问题有确认记录。
- 没有正文段落处于章节归属不明状态。
- 没有图片、表格、公式或参考文献处于已抽取但未放置状态。
- 摘要和关键词冲突已解决。
- `chapters/mainbody.tex` 中的章节输入顺序与确认后的结构一致。
