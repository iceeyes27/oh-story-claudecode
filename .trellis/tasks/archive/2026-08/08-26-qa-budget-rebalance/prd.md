# 复合检查预算再平衡（子任务 · P2）

> 父任务：[08-26-narrative-logic-overhaul](../08-26-narrative-logic-overhaul/prd.md)
> 对应反馈：**逻辑不通（预算侧）**。把花在对中文正文低效的风格项上的验收预算，让给逻辑层。

## Goal

为复合检查声明场景适用范围，使纯中文正文只计算实际适用的 required 项，并让逻辑项在该场景占比达到 25% 以上。阶段与 filter 目录均保留。

## 为什么

`composite-check-manifest.json` 现状为 10 个 stage、108 个 required，逻辑类 13 项，占 12.04%。即使简单移除 humanizer 26 项和 general-deslop 10 项，也只有 13/72 = 18.06%，不能实现目标：
- stage 8 `humanizer`（25 项）里 `title case`、`curly quotes`、`emoji`、`boldface`、`-ing analysis`、`copula avoidance` 等对**中文小说正文**基本无效——它们是英文/Markdown 文档的 AI 痕迹。
- stage 7 `general-deslop`（10 项）与 stage 3 `novel-deslop`（15 项）大量重叠（都在查套路腔、空话、模板感）。
- 结果：同一 required 分母混入了当前场景不执行的规则，不能表达实际验收预算。

## Requirements

### R1 humanizer 阶段中文裁剪

- 对纯中文正文，把明显英文/Markdown 专属项（title case、curly quotes、emoji、boldface、inline headings、-ing analysis、copula avoidance 等）从**必检**降级或标注"中文正文不适用可 SKIPPED"。
- 保留跨语言有效项（filler phrases、excessive hedging、generic conclusion、significance 夸大、否定式排比、三段式）。
- 为 filter 增加显式 `appliesWhen`；不适用项必须给出理由，且不进入该场景 required 分母。不能只报 SKIPPED 后仍计入分母。

### R2 general-deslop 与 novel-deslop 去重

- 审两个 stage 的 filter，把与 novel-deslop 完全重叠的项在 general-deslop 里合并或标注"正文已由 novel-deslop 覆盖"，只保留 general 模式真正独有的（对外文案、非正文文本）。
- 不降低对正文套路腔的实际清理力度——去的是**重复执行**，不是**检查维度**。

### R3 契约与文案同步

- manifest 改动后同步十阶段说明；完整目录仍为 108 项，完成文案另报告当前场景适用项完成数。
- `skills/story/tests/composite-check-contract.test.js` 硬编码了 stage 顺序与 required 契约，必须同步更新并通过。
- `stageCount`（`completion.stageCount`）若因 P0 新增 stage 而变化，以父任务统一后的实际值为准。

### R4 与 P0 的编排

- 本任务**依赖两个 P0 已把新逻辑 stage 落地**：占比目标（≥25%）的分子（逻辑项）来自 reader-comprehension（可能还有 opening-arc）。故本任务在 P0 之后执行，基于 P0 之后的 manifest 做再平衡与占比核算。
- 避免与 P0 同时改 `expectedStages`/`stageCount`：本任务 rebase 到 P0 落地后的 manifest 再动。

## Acceptance Criteria

- [x] AC1：humanizer 阶段对纯中文正文，英文/Markdown 专属项按 `not applicable` 合规 SKIPPED，跨语言有效项保留必检。
- [x] AC2：general-deslop 与 novel-deslop 的重叠项去重，正文套路腔覆盖维度不减。
- [x] AC3：纯中文正文场景中，逻辑 required 项占比 ≥25%；测试列出分子、分母、适用 filter ID 和计算式，不适用项不进入分母。
- [x] AC4：`node skills/story/tests/composite-check-contract.test.js` 通过；`复合检查完成：N/N` 文案与实际一致。
- [x] AC5：`bash scripts/static-check.sh`、`python scripts/check-current-skill-contracts.py` 通过。

## Out of Scope

- 不删任何一个 stage（humanizer/general-deslop 仍在，只是中文正文下部分项合规跳过）。
- 不改各 skill 内部的检查规则实现，只改 manifest 编排与必检/跳过策略。
- 不动 P0 新增的逻辑 stage 内容。

## 依赖与顺序

- **强依赖两个 P0（尤其 reader-comprehension-scan）先落地**——占比分子来自它们。本任务是六个子任务里最后执行的一个。此依赖写在此处，不由树位置隐含。
