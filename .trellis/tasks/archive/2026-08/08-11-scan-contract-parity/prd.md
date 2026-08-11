# 扫榜统一契约

## Goal

修复 R4-R6：起点字段、七猫周期、严格 CLI、简介和时间一致性。

## Requirements

- 统一四平台 CLI 结构校验、整数范围、Unicode 简介截断和单次时间快照。
- 起点 mobile-ssr 与 cdp-pc 均输出固定 14 字段 schema 和 `missing_fields`。
- 七猫大热榜实现 `day|month|all`，点击后验证页面实际激活状态；非大热榜拒绝显式 period。
- 所有参数错误在浏览器、网络和文件副作用前失败。

## Acceptance Criteria

- [ ] 四平台未知、重复、缺值、空值、类型和范围错误测试通过。
- [ ] 起点两来源字段键完全一致，缺失值为 `null` 且有质量说明。
- [ ] 七猫日/月文件头、标题、文件名可区分且不会覆盖。
- [ ] 中文、emoji 和本地日期跨日边界测试通过。

## Notes

详细技术约束见父任务 `design.md` 与 `research/consensus-draft.md`。
