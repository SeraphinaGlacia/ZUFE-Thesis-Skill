# 流程 A：环境与输入确认

流程 A 是进入 Word 转 LaTeX 的严格门禁：只要模板骨架、输入文件、元数据、输出状态或运行环境不满足要求，就不得进入流程 B。

但它面向无计算机基础用户，因此不是让用户手动准备一切，而是在用户批准后协助整理工作区、移动 Word、预扫描 Word、生成元数据候选，并让用户确认。

## A.1 最终顺序

1. 模板签名检查：确认当前目录像 ZUFE-Thesis 模板根目录。
2. 工作区与 Word 整理：创建标准 `workspace/`，把用户在对话中提供或 @ 的 Word 整理到固定路径。
3. 最小 Python 提取环境检查：先确保能读取 DOCX。
4. Word 轻量预扫描：读取全文结构，用于判断 Word 是否可读、是否像论文、能否生成元数据候选。
5. `metadata.yaml` 确认/补齐：展示候选表，让用户确认或修改封面身份信息。
6. 输出目录保护：检查旧输出，避免覆盖。
7. LaTeX/Biber 环境检查：确认后续生成和编译链可用。

## A.2 模板签名检查

必查文件和目录：

- `main.tex`
- `zufe.cls`
- `Reference.bib`
- `chapters/basicinfo.tex`
- `chapters/mainbody.tex`
- `misc/cover.tex`
- `misc/abstract.tex`
- `misc/originality.tex`
- `misc/reference.tex`
- `simhei.ttf`
- `stsong.ttf`
- `stkaiti.ttf`
- `InitFile/schoolLogo.png`

不作为流程 A 门禁：

- `main.pdf`
- `README.md`
- `docs/`
- `papperCode/`
- 样例章节
- 样例图片

第一版暂不正式支持匿名模板，`InitFile/anonyLogo.png` 不作为硬门禁。

## A.3 工作区与 Word 整理

用户批准后，流程 A 可以创建标准工作区骨架：

```text
workspace/
├── input/
│   └── assets/
├── intermediate/
└── output/
```

`assets/` 是可选附件区，不代表用户必须提供图片或附件。

如果用户在对话框中直接 @ Word，流程 A 经用户确认后将其移动为：

```text
workspace/input/thesis.docx
```

移动前必须明确提示用户：原文件会离开原位置，之后以 `workspace/input/thesis.docx` 为准。如果目标文件已存在，流程 A 必须阻止并询问，不默认覆盖。

`.docx` 是标准输入格式。`.doc` 是可修复情况，需说明转换风险并经用户批准后再尝试转换；转换成功后仍落到 `workspace/input/thesis.docx`。

## A.4 最小 Python 提取环境

在正式要求用户确认元数据前，先检查能否进行 Word 预扫描：

- Python 可运行。
- `python-docx` 可导入。

如果缺少 Python 包，应说明影响和风险。用户批准后可以自动安装。`pdfplumber` 不属于 DOCX 第一版的必需依赖；只有未来支持 PDF 输入时才纳入检查。

## A.5 Word 轻量预扫描

流程 A 可以轻量抽取 Word 全文结构，但只用于门禁和候选生成：

- 判断 Word 是否可读。
- 判断文件是否像论文或报告。
- 为题目、姓名、学号、学院、专业、导师、班级、日期等生成候选。

预扫描结果只在内存和对话上下文中使用，不生成正式 `thesis.json`。正式章节识别、图片表格处理、参考文献整理和 LaTeX 生成仍属于流程 B。

如果 Word 损坏、加密、不可读或格式不支持，流程 A 阻止进入后续流程，并说明原因；能自动处理的情况先说明影响和风险，再请求用户批准。

## A.6 metadata.yaml 确认/补齐

流程 A 只确认封面和身份信息：

- 报告类型：默认毕业论文，即 `report_style: 0`；允许用户改为专业实践 1/2。
- 中文题目。
- 英文题目。
- 是否有副标题；默认无副标题。
- 中文副标题和英文副标题，仅在用户确认有副标题时填写。
- 学院。
- 专业。
- 姓名。
- 学号。
- 导师。
- 班级。
- 日期。

摘要、关键词、正文结构不在流程 A 中要求用户填写，交给流程 B 从 Word 中抽取和语义识别。

流程 A 可以从 Word 预扫描结果生成候选表，但写入 `workspace/input/metadata.yaml` 前必须展示给用户确认。用户确认或修改后，才生成或更新 `metadata.yaml`。

## A.7 输出目录保护

如果 `workspace/intermediate/` 或 `workspace/output/` 已有旧产物，流程 A 阻止覆盖。

用户批准后，可以把旧产物归档到：

```text
workspace/archive/<timestamp>/
```

流程 A 不默认删除旧结果。

## A.8 LaTeX/Biber 环境检查

最后检查后续生成和编译链：

- `xelatex`
- `biber`

缺失时，流程 A 应说明安装成本、耗时、磁盘占用和可能影响。用户批准后，可以按官方或本机方案协助安装；LaTeX 发行版安装必须单独确认。

## A.9 用户反馈

失败时，不要求非技术用户打开 Gate Report 文件，而是在对话中给出简短门禁清单：

- 卡在哪里。
- 为什么不能继续。
- Codex 可以帮忙做什么。
- 哪些操作需要用户批准。

通过时，只给简短准入摘要：模板、Word、metadata、输出状态、环境都已就绪，可以进入流程 B。

脚本内部可以输出 JSON 或日志供 Codex 使用，但它不是普通用户的主要交互界面。

## A.10 测试场景

- 正确模板根目录、完整输入、环境完整：流程 A 通过。
- 缺模板签名文件：阻止，提示当前目录不像 ZUFE-Thesis 根目录。
- 用户直接 @ DOCX 且无 `workspace/`：确认后创建工作区并移动为 `workspace/input/thesis.docx`。
- 目标 `thesis.docx` 已存在：阻止并询问如何处理。
- DOCX 可读：预扫描生成元数据候选表。
- DOCX 损坏、加密或不可读：阻止并解释，提示换文件或另存为 DOCX。
- 缺 `metadata.yaml`：通过候选表和分组问答生成，确认后重新预检。
- 缺 Python 包：说明影响，用户批准后安装。
- 缺 LaTeX/Biber：说明安装成本和风险，用户批准后按官方或本机方案处理。
- 旧输出存在：阻止覆盖，用户批准后归档到 `workspace/archive/<timestamp>/`。
