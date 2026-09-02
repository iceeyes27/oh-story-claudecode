# 1 · 读者体验契约接进采用链

父任务：`.trellis/tasks/09-01-quality-first-gates`
依赖：`09-01-regression-fixture-book`（验收需要合格样本）
被依赖：子任务 2、3、4（复用 `check` 子命令与分级判定）

## Goal

把仓库里**已经定义好但没接线**的读者体验契约接到唯一写入口上，让「写这一章之前必须先回答读者要什么」成为门禁而非建议。

## 背景

`skills/story-write/scripts/check-outline-contract.js:35` 定义了 `INTENT_FIELDS`，脚本注释明写「**这两个字段实测直接影响正文质量，必须有实际内容**」：

- `目标情绪`
- `主角目标/关键选择`
- `结尾拍ID/类型`
- `期待ID/类型`
- `读者验收预期`

这是全仓库最接近「怎么让书好看」的成文契约。但：

1. `skills/story-write/references/artifact-protocols.md:274` 把它限定为「只在新建/补建/回填时执行；**既有项目的旧细纲不因此阻断写正文**」；
2. `candidate-commit.py` 的 preflight 工具链里没有它；
3. demo 20 章一个字段都没有——这本书是在从没回答过这些问题的情况下写完的，卷纲第 122 行「16–20 章五连同母题」的事后批注正是这个空缺的产物。

## Requirements

- R2.1 `check-outline-contract.js` 进入 `candidate-commit.py` 的 `validate_binding` preflight，沿用现有 `run_node + require(returncode == 0)` 惯例。
- R2.2 **只对 `INTENT_FIELDS` blocking**。`outline.plotpoint-table`、`outline.reader-contract` 本批降为 advisory（记录不阻断）。
- R2.3 按 `imported_through_chapter` 分级（父任务 D3）：历史章 advisory，新写章 blocking。该判定实现为**一处共享逻辑**，供子任务 2、4 复用。
- R2.4 新增 `candidate-commit.py check --project ... --chapter N` 子命令（父任务 D2）：跑与 promote 相同的 `validate_binding`，不移动文件、不提交事务、不改 `_tracking-state.json`。
- R2.5 细纲类检查在**出骨架前**也跑一次本章范围（父任务 D4）。
- R2.6 `artifact-protocols.md:274` 与 `AGENTS.md` 同步修订，表述改为按 `imported_through_chapter` 分级，消除「旧细纲不阻断」与新门禁的自相矛盾。
- R2.7 `AGENTS.md` 明确写「写完候选后跑 `check`；作者采用时跑 `promote`」，**不得**合并成一条命令。

## 非目标

- 不要求 `outline.plotpoint-table` / `outline.reader-contract` 通过（本批 advisory）。
- 不回填 demo 的 20 章细纲。
- 不判断字段内容好不好——`artifact-protocols.md:274` 自述该检查「不判内容好坏」，本任务不改变这一点。它保证有人被迫思考，不保证答案好。

## Acceptance Criteria

- [x] 缺字段候选：`check` 与 `promote` 均因 INTENT_FIELDS blocking 失败，报错文本点名缺失字段。
- [x] 合格候选：`check` 通过。
- [x] `imported_through_chapter` 内的历史章：outline-contract 降为 advisory，不因旧细纲缺字段变红。
- [x] `check` 子命令运行后 `_tracking-state.json` 的 `state_revision` 与文件 mtime 不变，候选文件未移动。
- [x] `promote` 与 `check` 复用同一份 `validate_binding` 预检。
- [x] `AGENTS.md` 与 `artifact-protocols.md` 无「旧细纲不阻断」与新门禁矛盾的表述。
- [x] `scripts/test-candidate-commit.py` 全部 35 项通过。

## 验证记录（2026-09-02）

- 新章缺 INTENT_FIELDS：`check` 退出 1，`promote` 退出 2，正文与追踪均未改变。
- 历史章缺 INTENT_FIELDS：通过真实 `check` 入口，候选仍留在原位，追踪状态未推进。
- 合格新章：`check` 返回 `ok=true`；`state_revision`、状态文件 mtime 和正文目录保持不变。
- `scripts/test-candidate-commit.py`：35/35 PASS。

## 风险

**本批最可能造成破坏的一步**。新引入 blocking，若 D3 分级实现有误，症状是 demo 无法 promote。发生时先查分级判定，**不要直接放宽 blocking**。
