# Stage 章节边界唯一来源

## Goal

修复 R2：schema v3、来源指纹、边界校验器与 Stage 1/2/6 单一切片来源。

## Requirements

- `_progress.md` 升为 schema v3，记录原文相对路径、字节数和 SHA-256。
- 新增统一边界校验器，检查章号、起始行、来源指纹和原文范围。
- Stage 1/2/6 只使用章节边界表；Stage 6 删除 Grep、正则调整和重新切片分支。
- v1/v2 只能回到 Stage 0 重建，不在消费阶段临时迁移。

## Acceptance Criteria

- [ ] 有效表可供三个 Stage 使用。
- [ ] 重复、缺号、倒序、越界、原文变化和旧 schema 均快速失败。
- [ ] 静态契约能拒绝 Stage 6 重新切片说明。

## Notes

详细技术约束见父任务 `design.md` 与 `research/consensus-draft.md`。
