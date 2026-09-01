# 0.5 · 回归 fixture 书

父任务：`.trellis/tasks/09-01-quality-first-gates`
依赖：无。子任务 1、2 依赖本任务。

## Goal

建一本 3–5 章的最小 fixture 书，作为「读者体验契约」与「情绪母题」两项新门禁的验收样本。

## 为什么不能用 demo

`demo/长篇/让你管账号，你高燃混剪炸全网` 有两个致命问题（2026-09-01 实跑）：

1. **20 章细纲全部 outline-contract blocking**。每章都挂 `outline.required-fields` + `outline.reader-contract` + `outline.plotpoint-table`；缺的字段正好包含本批要 blocking 的全部 `INTENT_FIELDS`（`目标情绪` / `主角目标/关键选择` / `结尾拍ID/类型` / `期待ID/类型` / `读者验收预期`）。在一本全红的书上验收「新门禁能否检出缺字段」是空转。
2. **`字数目标` 是按正文实际字数倒填的**。20 章 `actual / 目标` 比值全为 1.00，`细纲目标 90%` 这套权威在 demo 上恒过。

demo 继续作为 **causal / 字数 / name-drift** 的回归 fixture（那三项的基线数字有效），但不作 outline-contract 与母题 fixture。

## Requirements

- R8.1 新建 fixture 书，3–5 章，目录结构符合长篇项目规范（`设定/` `大纲/` `正文/` `追踪/`）。
- R8.2 细纲**全部字段齐全**，`check-outline-contract.js` 对每章 `ok=true`。
- R8.3 `目标情绪` 取值可控，且**刻意包含一段连续同值**（用于子任务 2 的连排验收）与一段正常分布。
- R8.4 是**新写书**而非导入书：`imported_through_chapter = 0`，以便触发新写章的 blocking 分支。
- R8.5 提供一份**故意缺字段**的细纲变体（如 `细纲_第003章.bad.md` 或测试内联生成），用于断言 blocking 确实触发。
- R8.6 体量最小化：正文可短（不必满足番茄 2200–2800，若字数门禁阻碍则在 fixture 内声明或走测试专用路径），重点是细纲与追踪状态，不是正文质量。

## 非目标

- 不是一本可读的小说，不做文学质量要求。
- 不替代 demo 的既有回归用途。
- 不回填 demo 的 20 章细纲（那是独立的、更贵的工作，本批不做）。

## Acceptance Criteria

- [ ] `node skills/story-write/scripts/check-outline-contract.js --json --project <fixture> --chapter N` 对每章 `ok=true`。
- [ ] fixture 的 `_tracking-state.json` 通过 `tracking_commit.py` 的 state 校验，`imported_through_chapter = 0`。
- [ ] `目标情绪` 序列中存在连续 ≥4 章同值的片段（供子任务 2 调阈值观察）。
- [ ] 缺字段变体能被 `check-outline-contract.js` 判为 `ok=false` 且命中 `outline.required-fields`。
- [ ] fixture 放置位置不污染 `demo/` 的既有内容，且被 `scripts/check-release-manifest.mjs` 接受（或明确排除）。

## 未决

- 放 `demo/` 下还是 `tests/fixtures/` 下：倾向 `tests/fixtures/`，因为它不是给用户看的示例。落位前确认 `check-release-manifest.mjs` 与 `check-doc-budget.sh` 的扫描范围。
- 章数 3 还是 5：连排验收需要至少 4 章同值 + 1 章不同值才能区分 3/4 阈值，倾向 **5 章**。
