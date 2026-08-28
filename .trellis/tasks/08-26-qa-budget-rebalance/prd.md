# 复合检查预算再平衡（子任务 · P2）

> 父任务：[08-26-narrative-logic-overhaul](../08-26-narrative-logic-overhaul/prd.md)
> 对应反馈：**逻辑不通（预算侧）**。把花在对中文正文低效的风格项上的验收预算，让给逻辑层。

## Goal

精简复合检查里对中文小说正文低效或高度重叠的检查项，把节省出的验收注意力让给新增的读者视角/逻辑层阶段，实现父任务 AC2（逻辑层 required 占比 7.8% → ≥25%，提升来自新增逻辑项与精简冗余风格项两侧）。

## 为什么

`composite-check-manifest.json` 现状：
- stage 8 `humanizer`（25 项）里 `title case`、`curly quotes`、`emoji`、`boldface`、`-ing analysis`、`copula avoidance` 等对**中文小说正文**基本无效——它们是英文/Markdown 文档的 AI 痕迹。
- stage 7 `general-deslop`（10 项）与 stage 3 `novel-deslop`（15 项）大量重叠（都在查套路腔、空话、模板感）。
- 结果：102 个 required 项里 94 项是风格/AI 味，逻辑仅 8 项（7.8%）。

## Requirements

### R1 humanizer 阶段中文裁剪

- 对纯中文正文，把明显英文/Markdown 专属项（title case、curly quotes、emoji、boldface、inline headings、-ing analysis、copula avoidance 等）从**必检**降级或标注"中文正文不适用可 SKIPPED"。
- 保留跨语言有效项（filler phrases、excessive hedging、generic conclusion、significance 夸大、否定式排比、三段式）。
- 用 manifest 的 `skipPolicy`（`allowedOnlyWhen: not-applicable` + `requiresReason`）机制表达，不是硬删项——保持对双语/英文文案仍可用。

### R2 general-deslop 与 novel-deslop 去重

- 审两个 stage 的 filter，把与 novel-deslop 完全重叠的项在 general-deslop 里合并或标注"正文已由 novel-deslop 覆盖"，只保留 general 模式真正独有的（对外文案、非正文文本）。
- 不降低对正文套路腔的实际清理力度——去的是**重复执行**，不是**检查维度**。

### R3 契约与文案同步

- manifest 改动后同步 `skills/story/SKILL.md` 的八阶段说明、`复合检查完成：8/8，过滤项 M/M` 里的 M（required 计数会变）。
- `skills/story/tests/composite-check-contract.test.js` 硬编码了 stage 顺序与 required 契约，必须同步更新并通过。
- `stageCount`（`completion.stageCount`）若因 P0 新增 stage 而变化，以父任务统一后的实际值为准。

### R4 与 P0 的编排

- 本任务**依赖两个 P0 已把新逻辑 stage 落地**：占比目标（≥25%）的分子（逻辑项）来自 reader-comprehension（可能还有 opening-arc）。故本任务在 P0 之后执行，基于 P0 之后的 manifest 做再平衡与占比核算。
- 避免与 P0 同时改 `expectedStages`/`stageCount`：本任务 rebase 到 P0 落地后的 manifest 再动。

## Acceptance Criteria

- [ ] AC1：humanizer 阶段对纯中文正文，英文/Markdown 专属项按 `not applicable` 合规 SKIPPED，跨语言有效项保留必检。
- [ ] AC2：general-deslop 与 novel-deslop 的重叠项去重，正文套路腔覆盖维度不减。
- [ ] AC3：逻辑层 required 项占比 ≥25%（分母 = 再平衡后 required 总数，分子 = 逻辑/连续性/读者视角项），在任务 notes 给出计算式。
- [ ] AC4：`node skills/story/tests/composite-check-contract.test.js` 通过；`复合检查完成：N/N` 文案与实际一致。
- [ ] AC5：`bash scripts/static-check.sh`、`python scripts/check-current-skill-contracts.py` 通过。

## Out of Scope

- 不删任何一个 stage（humanizer/general-deslop 仍在，只是中文正文下部分项合规跳过）。
- 不改各 skill 内部的检查规则实现，只改 manifest 编排与必检/跳过策略。
- 不动 P0 新增的逻辑 stage 内容。

## 依赖与顺序

- **强依赖两个 P0（尤其 reader-comprehension-scan）先落地**——占比分子来自它们。本任务是六个子任务里最后执行的一个。此依赖写在此处，不由树位置隐含。
