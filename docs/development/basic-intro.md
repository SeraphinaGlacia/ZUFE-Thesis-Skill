### 文件结构

本仓库已经从原先 fork 仓库中的辅助目录迁移为独立 Skill 仓库。当前核心文件结构如下：

- `zufe-thesis-typesetter/`：可安装的 Skill 包，包含 `SKILL.md`、脚本、参考文档、测试和示例 metadata。
- `docs/development/`：开发期工作流说明和历史设计记录。
- `docs/others/`：项目愿景、设计初衷和面向读者的背景说明。
- `README.md`：面向普通用户和潜在使用者的公开介绍。
- `assets/schoolLogo.png`：README 展示用校徽资源。

运行时以 `zufe-thesis-typesetter/SKILL.md` 和 `zufe-thesis-typesetter/references/` 为准；`docs/development/` 主要用于保留设计演进和维护背景。

### 基本目标

开发并维护一个面向 ZUFE-Thesis 模板的 Agent Skill。用户在完整的 ZUFE-Thesis 模板项目中安装本 Skill 后，可以通过 Kimi Work、Codex 等 Agent 工具，把 Word 初稿转换为 LaTeX 工程并生成 PDF。

这个项目的重点不是替代原始 LaTeX 模板，而是在模板基础上补充 AI 入口层：让不熟悉 LaTeX 的用户也能通过对话完成格式整理、模板写入、编译和质检。

### 开发抓手

- `zufe-thesis-typesetter/SKILL.md`：Skill 触发条件、核心契约和质量硬约束。
- `zufe-thesis-typesetter/references/`：当前运行时 A/B/C 流程、环境修复和 `thesis.json` 契约。
- `docs/development/workflow-design.md`：开发期用户侧 A/B/C 工作流总览。
- `docs/others/让 LaTeX 的好处先发生：我的 ZUFE Thesis Skill 设计初衷.md`：项目愿景与设计初衷。
