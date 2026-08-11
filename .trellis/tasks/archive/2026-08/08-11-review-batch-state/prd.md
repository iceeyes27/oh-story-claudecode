# 跨批审查状态

## Goal

修复 R3：版本化跨批 findings 状态、solo 只读与并发安全。

## Requirements

- 固定 `{书目录}/.story-review/latest.json` 和版本化 schema。
- full/lean 可写，solo 与显式只读模式只读。
- 用目标 revision 的独占申领文件、二次 revision 校验和原子替换避免并发覆盖。
- 未完成 review 不得被其他 review_id 替换；损坏、输入变化和异常申领均明确报告。

## Acceptance Criteria

- [ ] 新建、恢复、幂等重跑、完成后新任务通过。
- [ ] revision 冲突和并发申领不会丢 findings。
- [ ] solo/显式只读不创建、更新或删除任何状态相关文件。
- [ ] 损坏 JSON、内容变化和异常申领恢复均有测试。

## Notes

详细技术约束见父任务 `design.md` 与 `research/consensus-draft.md`。
