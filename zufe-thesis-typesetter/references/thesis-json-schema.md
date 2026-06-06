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
    "images": 0
  },
  "metadata_candidates": {},
  "metadata": {},
  "structure": {
    "chapters": []
  },
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

- `needs_confirmation` 表示必须由 Codex 询问或基于明确证据确认后才能渲染。
- `blocked` 表示流程 B 必须停止。
- `mapped` 表示已归属但还没写入。
- `rendered` 必须有 `render_result`。
- `discarded_with_reason` 必须有 `discard_reason`。

不要在没有用户确认原因的情况下，把高风险源块改成 `discarded_with_reason`。

## Run 级格式规则

- `text` 是便于检索和语义判断的纯文本；LaTeX 渲染不得只依赖 `text`。
- 非空段落必须尽量写入 `runs`，记录 Word run 的 `bold`、`italic`、`superscript`、`subscript` 和 `font_size_pt`。
- 若 `runs[].superscript=true`，渲染结果必须保留视觉上标，例如 `\textsuperscript{1}`。
- 若上标数字实际是参考文献标号，Codex 可以在确认映射后改成引用命令；未确认前不得压平成普通数字。

## 目标槽位示例

- `chapters/basicinfo.tex`
- `chapters/mainbody.tex`
- `chapters/1_introduction.tex`
- `chapters/acknowledgement.tex`
- `chapters/appendix.tex`
- `Images/word_media/image1.png`
- `Reference.bib`

## 已确认章节结构

Codex 确认章节顺序后，写入：

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
