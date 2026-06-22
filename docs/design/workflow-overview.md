# ZUFE Thesis Skill 工作流设计

本文档保留开发期用户侧 A/B/C 工作流总览。当前可执行 Skill 的运行时约束以 `zufe-thesis-typesetter/SKILL.md` 和 `zufe-thesis-typesetter/references/` 为准；`docs/archive/early-workflows/` 用于记录早期设计演进和维护背景。

如果需要理解 Skill 包内部如何调动 `SKILL.md`、`references/`、`scripts/` 和 `tests/`，先读 `docs/design/internal-execution.md`。

## 总览

| 流程 | 名称 | 目标 | 早期设计记录 | 记录状态 |
| --- | --- | --- | --- | --- |
| A | 环境与输入确认 | 严格门禁与智能预准备，确保能安全进入转换 | `docs/archive/early-workflows/flow-a-gatekeeping.md` | 已确认第一版 |
| B | 转换与模糊确认 | 正式抽取 Word 内容，识别结构，处理低置信度内容 | `docs/archive/early-workflows/flow-b-conversion.md` | 严谨性门槛已确认，细节继续细化 |
| C | 编译、质检与导出 | 生成 LaTeX 工程和 PDF，诊断错误并交付结果 | `docs/archive/early-workflows/flow-c-export-and-qa.md` | 已确认第一版 |

## 流程关系

```text
流程 A：严格门禁与智能预准备
  输入：模板项目、用户提供或 @ 的 Word、可能已有的 workspace
  输出：标准 workspace、thesis.docx、metadata.yaml、可用环境
  进入条件：用户希望把 Word 转为 ZUFE-Thesis LaTeX/PDF

流程 B：转换与模糊确认
  输入：workspace/input/thesis.docx、metadata.yaml
  输出：正式中间结构、转换报告、待确认问题、LaTeX 工程草稿
  进入条件：流程 A 通过

流程 C：编译、质检与导出
  输入：流程 B 生成的 ZUFE-Thesis LaTeX 工程
  输出：main.pdf、完整工程、质检结果、交付说明
  进入条件：流程 B 完成必要确认并生成工程
```

## 设计原则

- 先确认 A/B/C 的用户侧工作流，再决定 Skill 包结构、脚本拆分和项目文件组织。
- 流程 A 保持严格门禁，不带病进入流程 B。
- 流程 B 负责正式内容理解，不把章节、摘要、关键词、图片表格和参考文献识别提前塞进流程 A。
- 流程 C 负责可交付结果，必须能说明成功文件位置和失败修复路径。
- 面向非技术用户的主反馈应出现在对话中，内部报告和 JSON 主要供 Agent 与脚本使用。
