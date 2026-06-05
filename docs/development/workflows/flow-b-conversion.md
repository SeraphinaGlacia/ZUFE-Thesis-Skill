# 流程 B：转换与模糊确认

流程 B 在流程 A 通过后启动，负责对 Word 做正式抽取、结构识别和内容转换。流程 B 的结果会进入流程 C 编译与交付。

## 当前预览

- 从 `workspace/input/thesis.docx` 正式抽取段落、标题、图片、表格、编号、样式等信号。
- 生成 `workspace/intermediate/thesis.json` 和 `workspace/intermediate/extracted.md`。
- Codex 根据抽取结果判断章节结构、摘要、关键词和参考文献。
- 对低置信度内容生成确认问题，不静默猜测。
- 生成 ZUFE-Thesis LaTeX 工程草稿。

## 待确认问题

- DOCX 正式抽取需要保留哪些原始信号。
- 标题样式、字号、编号、居中、加粗等信号如何共同判断章节层级。
- 摘要、关键词、中英文题目与流程 A 的 metadata 候选如何衔接。
- 图片和表格第一版是完整转换，还是先生成占位并在报告中提醒。
- 参考文献优先使用 Word 抽取、用户提供 BibTeX，还是两者合并。
- 低置信度内容如何提问，最多一次问几个问题。
