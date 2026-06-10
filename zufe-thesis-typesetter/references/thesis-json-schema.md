# thesis.json 契约

`workspace/intermediate/thesis.json` 是流程 B 的审计账本。判断 Word 内容是否被处理时，以它为准。

## 顶层结构

```json
{
  "schema_version": "1.0",
  "source_docx": "workspace/input/thesis.docx",
  "created_at": "2026-06-06T12:00:00+08:00",
  "counts": {
    "total_source_blocks": 0,
    "paragraphs": 0,
    "tables": 0,
    "images": 0,
    "unsupported_features": 0
  },
  "metadata_candidates": {},
  "metadata": {},
  "structure": {
    "chapters": []
  },
  "unsupported_features": [],
  "source_blocks": [],
  "render_log": [],
  "warnings": []
}
```

## 源块结构

```json
{
  "id": "p0001",
  "order": 1,
  "source_type": "paragraph",
  "candidate_type": "body",
  "text": "原始文本",
  "runs": [
    {
      "index": 1,
      "text": "1",
      "bold": false,
      "italic": false,
      "superscript": true,
      "subscript": false,
      "font_size_pt": 9.0
    }
  ],
  "summary": "短摘要",
  "evidence": {
    "style": "Normal",
    "alignment": "CENTER",
    "bold_any": false,
    "italic_any": false,
    "superscript_any": true,
    "subscript_any": false,
    "font_sizes_pt": [12.0]
  },
  "asset_status": null,
  "asset_output": null,
  "target_slot": "chapters/1_introduction.tex",
  "status": "mapped",
  "confidence": 0.72,
  "requires_confirmation": false,
  "confirmation": {
    "confirmed_by": "user",
    "confirmed_at": "2026-06-06T12:00:00+08:00",
    "note": "已确认章节归属"
  },
  "discard_reason": null,
  "render_result": null
}
```

## 状态规则

- `needs_confirmation` 表示必须由 Agent 询问或基于明确证据确认后才能渲染。
- `blocked` 表示流程 B 必须停止。
- `mapped` 表示已归属但还没写入。
- `rendered` 必须有 `render_result`。
- `discarded_with_reason` 必须有 `discard_reason`。

不要在没有用户确认原因的情况下，把高风险源块改成 `discarded_with_reason`。

## Run 级格式规则

- `text` 是便于检索和语义判断的纯文本；LaTeX 渲染不得只依赖 `text`。
- 非空段落必须尽量写入 `runs`，记录 Word run 的 `bold`、`italic`、`superscript`、`subscript` 和 `font_size_pt`。
- 若 `runs[].superscript=true`，渲染结果必须保留视觉上标，例如 `\textsuperscript{1}`。
- 若上标数字实际是参考文献标号，Agent 可以在确认映射后改成引用命令；未确认前不得压平成普通数字。

## 英文内容决策

如果英文摘要或英文关键词缺失，必须在渲染 `chapters/basicinfo.tex` 前记录用户选择：

```json
{
  "metadata": {
    "english_content_decision": "omit"
  }
}
```

允许值：

- `omit`：用户确认留空。
- `manual`：用户会手动提供英文摘要和英文关键词。
- `generate`：用户允许 Agent 生成英文摘要和英文关键词。

选择 `manual` 或 `generate` 后，`metadata.abstract_en` 和 `metadata.keywords_en` 必须存在。生成内容还必须记录来源，例如 `english_content_source=generated`，并在 `metadata.yaml` 中记录 `allow_generated_english: true`。

## 暂不支持特性结构

```json
{
  "type": "equation_omml",
  "count": 1,
  "severity": "high",
  "status": "needs_confirmation",
  "summary": "检测到 Word OMML 公式，第一版不会自动转换公式。",
  "locations": [
    {"part": "word/document.xml", "count": 1}
  ]
}
```

`status=needs_confirmation` 会阻止流程 B 完成。用户确认风险或完成补救后，可改为 `accepted_with_warning`、`confirmed` 或 `resolved`。

## 图片资源规则

- image 源块的 `evidence.docx_media_path` 指向 DOCX 内部媒体路径，例如 `word/media/image1.png`。
- 若图片来自正文段落锚点，`evidence.anchor_paragraph_id` 和 `evidence.anchor_text` 记录位置证据。
- `asset_status=pending_export` 表示资源尚未复制；`asset_status=exported` 表示 `asset_output` 已指向 `Images/word_media/...`。
- `asset_status=exported` 不代表图片语义位置已确认。图片仍需通过 `target_slot` 或章节结构确认放入哪个章节文件。
- 已确认的图片或表格若会被正文引用，必须写入稳定 `label`，并在渲染时紧跟 `\caption{...}` 输出 `\label{...}`。

## 图表引用改写规则

正文中的 `图2.1`、`图 2.1`、`表1.2` 等手写编号必须被识别。Agent 确认映射后，在正文源块写入：

```json
{
  "id": "p0012",
  "text": "具体可见图2.1。",
  "reference_rewrites": [
    {
      "source_text": "图2.1",
      "target_kind": "figure",
      "target_label": "fig:age-distribution",
      "confirmation": {
        "confirmed_by": "agent",
        "note": "根据相邻图题“年龄分布图”和图片顺序确认"
      }
    }
  ]
}
```

目标图片或表格源块需要有对应 label：

```json
{
  "id": "img0001",
  "source_type": "image",
  "caption": "年龄分布图",
  "label": "fig:age-distribution"
}
```

`render_chapters.py` 会把上例渲染为 `图~\ref{fig:age-distribution}`。如果正文编号和图题编号互相矛盾，或一个编号对应多个候选图表，必须保持 `needs_confirmation` 或 `blocked`。

## 目标槽位示例

- `chapters/basicinfo.tex`
- `chapters/mainbody.tex`
- `chapters/1_introduction.tex`
- `chapters/acknowledgement.tex`
- `chapters/appendix.tex`
- `Images/word_media/image1.png`
- `Reference.bib`

## 已确认章节结构

Agent 确认章节顺序后，写入：

```json
{
  "structure": {
    "chapters": [
      {
        "title": "绪论",
        "file": "chapters/1_introduction.tex",
        "block_ids": ["p0007", "p0008", "p0009"]
      }
    ]
  }
}
```

`scripts/render_chapters.py` 可以从这个结构渲染，或按 `target_slot` 对已确认源块分组。
