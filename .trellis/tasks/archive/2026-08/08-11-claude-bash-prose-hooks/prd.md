# Claude Bash 正文守卫

## Goal

修复 R1：Claude Bash 前置守卫、成功与失败写后检查及真实注册测试。

## Requirements

- 复用现有共享正文目标解析，Claude 的前置、`PostToolUse`、`PostToolUseFailure` 均覆盖 Bash。
- 支持重定向、追加、`tee`、`touch`、`cp`、`mv` 和多目标；非写入命令不误报。
- Node 缺失时只保留文档明确的有限前置兼容；写后依赖必须可见。
- 写后仅通过 `additionalContext` 报告，固定 exit 0，不宣称撤销写入。

## Acceptance Criteria

- [ ] 真实 settings 注册测试覆盖成功和失败 Bash 事件。
- [ ] 命令部分写入后返回非零仍会检查现存正文。
- [ ] 空格、中文、Windows 路径、多目标及只读命令回归通过。
- [ ] 共享核心与平台副本检查通过。

## Notes

详细技术约束见父任务 `design.md` 与 `research/consensus-draft.md`。
