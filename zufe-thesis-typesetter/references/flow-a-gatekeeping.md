# 流程 A：严格门禁与智能预准备

流程 A 是 Word 转 LaTeX 之前的准入门禁。只要模板、标准输入、metadata、旧输出状态或运行环境不安全，就不能进入流程 B。

## 顺序

1. 检查模板签名。
2. 创建或确认 `workspace/`，把 Word 文件放到 `workspace/input/thesis.docx`。
3. 检查最小 Python DOCX 抽取环境。
4. 轻量预扫描 Word。
5. 确认或补齐 `workspace/input/metadata.yaml`。
6. 保护旧 `workspace/intermediate/` 和 `workspace/output/` 产物。
7. 检查 `xelatex`、`biber` 和模板关键 TeX 包。

## 模板签名

模板根目录必须包含：

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

不要把 `main.pdf`、`README.md`、`docs/`、`papperCode/`、样例章节或样例图片作为门禁。第一版不把 `InitFile/anonyLogo.png` 作为硬门禁。

## 工作区

用户批准后创建：

```text
workspace/
├── input/
│   └── assets/
├── intermediate/
└── output/
```

如果用户提供或 @ 了 Word 文件，必须先说明：移动文件会让原文件离开原位置。批准后移动或复制到：

```text
workspace/input/thesis.docx
```

不得静默覆盖已有目标文件。第一版标准输入是 `.docx`。`.doc` 需要单独说明转换风险并获得批准。

## metadata 范围

流程 A 只确认封面和身份字段：

- `report_style`
- `thesis_title_cn`
- `thesis_title_abs_cn`，可选，摘要页中文题目；缺省时模板回退使用 `thesis_title_cn`
- `thesis_title_en`
- `has_subtitle`
- `thesis_subtitle_cn`
- `thesis_subtitle_en`
- `college`
- `major`
- `name`
- `student_id`
- `mentor`
- `class_name`
- `date`

`report_style` 是必须确认项，不能默认写成 `0`。候选值可以来自 Word 封面文字或表格；无法确认时必须询问用户。

候选字段只能来自 Word 预扫描证据或用户确认，不得从文件名猜测学院、专业、日期、导师或报告类型。`prescan_docx.py` 应扫描正文段落和封面表格单元格，避免漏掉 Word 前几页的结构化封面信息。

摘要、关键词、章节、图片、表格、公式、参考文献、致谢和附录属于流程 B。

## 用户反馈

失败时，在对话中说明卡住的门禁、原因和下一步。脚本可以写 JSON 供 Codex 使用，但普通用户不应该被要求先打开 Gate Report。
