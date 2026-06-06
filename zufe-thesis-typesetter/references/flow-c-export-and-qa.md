# 流程 C：编译、诊断、质检与导出

流程 C 只在流程 B 通过后启动。它负责把当前模板根目录编译成 PDF，诊断失败，执行有限机械修复，完成 QA，并说明交付状态。

流程 C 不重新组织内容，也不修正语义判断。如果章节归属、摘要关键词、图表归属、参考文献真实性或正文内容需要调整，必须回到流程 B。

## 编译前处理

编译前归档旧 `main.pdf`：

```text
workspace/archive/<timestamp>/flow-c-before-build/main.pdf
```

清理或归档临时文件，例如 `main.aux`、`main.bbl`、`main.bcf`、`main.blg`、`main.log`、`main.out`、`main.run.xml`、`main.toc`。必须记录本轮编译开始时间，避免把旧 PDF 当成本轮结果。

## 固定编译链

```text
xelatex main.tex
biber main
xelatex main.tex
xelatex main.tex
```

每一步记录命令、退出码、开始和结束时间、日志路径和产物状态。

## 机械修复边界

流程 C 可以修：

- LaTeX 特殊字符转义。
- 普通正文 ASCII 双引号转为 LaTeX 左右引号，但仅限能确认是脚本生成的普通正文片段；无法确认上下文时，只报告风险并退回流程 B，不做全文件替换。
- 图片路径或资源目录问题。
- 明显引用键格式问题。
- 临时编译文件污染。
- 日志明确定位的资源路径错误。

流程 C 不可以修：

- 正文属于哪一章。
- 摘要或关键词含义。
- 图表语义位置。
- 参考文献真实性或编造字段。
- 正文改写或删除。

自动修复和重编译最多 2 轮。

## 失败分类

- `mechanical_fixable`
- `return_to_flow_b`
- `user_input_required`
- `environment_issue`
- `unclassified_failure`

每个失败项都要给出下一步，而不只是 LaTeX 原始日志。

## QA 范围

第一版只检查日志、文本和页级证据，不做 PDF 截图视觉检查：

- 本轮生成新的 `main.pdf`。
- PDF 页数大于 0。
- PDF 文本可读取。
- 日志无严重编译错误。
- 没有未解析引用或问号引用。
- 参考文献信号存在。
- 目录、摘要、正文和参考文献信号存在。
- 若 `thesis.json` 记录了上标 run，章节源码中应存在对应 `\textsuperscript{...}` 渲染信号。
- 章节源码中不得出现无条件 `\resizebox{\textwidth}{!}` 表格缩放风险；出现时最终状态至少应为 `needs_review`。
- 没有模板蓝字说明或明显占位符，例如 `xx`、`xxxxxxxxxxxx`、`本文……`、`20xx`、`xxx`。
- `workspace/output/report.md` 和 `workspace/output/qa_report.md` 存在。

最终状态：

- `ready_to_submit`：PDF 已生成且 QA 通过。
- `needs_review`：PDF 已生成，但存在非阻断风险。
- `failed`：没有新 PDF、编译失败、关键部分缺失、引用/资源严重错误，或需要退回流程 B。
