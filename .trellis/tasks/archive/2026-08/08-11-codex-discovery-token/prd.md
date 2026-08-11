# Codex 目录发现与部署标记

## Goal

修复 R7-R8：有界目录发现契约与 target_cli 精确 token。

## Requirements

- 建立机器可读书目发现契约：标记距根最多 4 层，跳过点目录、`.git`、`node_modules` 和符号链接。
- JS、Bash、Python 的当前书与全部书发现使用相同深度语义和生成契约。
- Python 删除无限深度 glob。
- `target_cli` 按逗号拆分、去空白并精确匹配 `codex`；缺失、空值、重复字段视为无效。

## Acceptance Criteria

- [ ] 第 3/4 层可发现，第 5 层不可发现。
- [ ] 大型 `node_modules`、点目录、`.git` 和符号链接不会进入遍历。
- [ ] 越界 `.active-book` 不被采用。
- [ ] `opencode` 不再误判为 `codex`，单目标和多目标 Codex 正常。

## Notes

详细技术约束见父任务 `design.md` 与 `research/consensus-draft.md`。
