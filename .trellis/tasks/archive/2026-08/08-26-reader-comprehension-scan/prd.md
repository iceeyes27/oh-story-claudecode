# 读者视角理解力检查（子任务 · P0）

> 父任务：[08-26-narrative-logic-overhaul](../08-26-narrative-logic-overhaul/prd.md)
> 对应反馈：**逻辑不通**。这是整改的第一优先项：纯新增、不动现有门禁、无回归风险，用来验证"十几章弃书"能否被机制捕获。

## Goal

新增一个**只读正文、不读设定/大纲/追踪**的检查，判断读者在只有已发布正文的情况下能否看懂当前章。产出可核查的 findings 清单，作为复合检查的一个新阶段。

## 为什么现有检查不够

现有全部逻辑检查（`review-structure-logic`、`review-setting-consistency`、`review-timeline-space` 等，见父任务 PRD Background 1）都拿正文去比对 `设定/`、`追踪/_tracking-state.json`、细纲——**作者视角**。设定里自洽不等于正文里交代过。读者手上只有正文，弃书弃在"正文没说清楚"，不在"设定没写"。本检查专门补这个视角缺口。

## Requirements

### R1 输入隔离（本任务的立身之本）

- 检查执行时**只允许读取 `正文/` 目录下的章节文件**。不得读取 `设定/`、`大纲/`、`追踪/`、`对标/`。
- 语义判读子代理的 prompt 里不得注入任何设定/大纲/追踪内容——一旦注入，等于把缺口重新盖住。
- 唯一例外：为定位章号顺序可读文件名，不读其它目录正文。

### R2 确定性脚本层：专名首现检查

- 确定性实现使用共享 `skills/_shared/scripts/check-first-mention.js`，本 skill 测试直接引用共享实现，避免候选采用再维护副本。
- 扫描全部正文，提取被当作**已知前提**使用的专名/机构/物件/能力（人名、组织名、金手指名、关键道具），检查其**首次出现处**附近是否有一次身份/来历交代。
- 判据（可机械化的子集）：一个专名 token 首现时，若同段或相邻段内没有任何解释性锚点（同位语、"是…"判断句、动作交代、外貌/职务描述），标记 `未交代即使用` finding，输出 `章节:行号 + token + 首现上下文`。
- blocking / advisory 语义：默认 advisory（专名首现有大量正常情况，如主角自己）；只有"该 token 在后续章节被当作读者已知的关键前提回扣、但首现处零交代"才升级 blocking。这一步能机械判定的只有首现位置，"是否被当已知前提"由语义层补。
- 必须带回归测试 `skills/reader-comprehension-scan/scripts/test-first-mention.js`：正常交代、首现零交代、跨章回扣未交代三类样例。

### R3 语义判读层：三问连读

- 新 skill 文档给出"三问"通读法，对每章（或每批章）只喂正文，逐章回答：
  1. 这章谁在做什么？（能不能从正文本身说清）
  2. 为什么做——前因在**正文哪一章**明写过？（指不到具体章 = 前因悬空）
  3. 读者读到这里，手上信息够不够理解本章的关键转折？（不够 = 理解断点）
- 任一问答不出 → finding，附 `章节 + 断点描述 + 读者此刻缺的信息`。
- 分批派只读子代理（参考 `dialogue-naturalness-scan` 第 3 层的分批纪律，默认 5 章/批），禁止单代理通读全书退化成抽查。

### R4 接入复合检查

- 在 `skills/story/references/composite-check-manifest.json` 新增一个 stage（`reader-comprehension`），登记 R2/R3 的 filter 项。
- **必须同步更新** `skills/story/tests/composite-check-contract.test.js`——该测试硬编码了 `expectedStages` 的 8 项顺序数组；新增 stage 后 stageCount、expectedStages、`skills/story/SKILL.md` 的阶段列表与 `复合检查完成：N/N` 文案三处必须一致。
- 新 skill 登记进 `scripts/platform-skill-set.json`（或 `local-only-skill-set.json`，二选一并说明）。

### R5 结论边界

沿用仓库约定：本检查通过只表述为"已知理解断点模式未发现"，不得声称"读者一定看得懂"。

## Acceptance Criteria

- [x] AC1：对 demo 书 `demo/长篇/让你管账号，你高燃混剪炸全网/` 跑本检查，只读 `正文/`，产出可核查的理解断点/首现未交代清单。
- [x] AC2：共享 `check-first-mention.js <书目录>` 对首现零交代样例返回 finding，对正常交代样例不误报；`node skills/reader-comprehension-scan/scripts/test-first-mention.js` 全绿。
- [x] AC3：manifest 新增 stage 后 `node skills/story/tests/composite-check-contract.test.js` 通过，`复合检查完成：N/N` 文案与实际 stage 数一致。
- [x] AC4：`bash scripts/static-check.sh`、`python scripts/check-current-skill-contracts.py`、`node .agents/skills/story-setup/scripts/manage-skill-adapters.js check` 通过。
- [x] AC5：语义三问通读法产出的 findings 在 demo 书上人工抽查，命中的确是"正文没交代清楚"，不是"设定里有但正文省略"被误判成——即隔离生效。

## Out of Scope

- 不改任何现有 stage 的 filter。
- 不做自动修正正文（report-only）。
- 脚本不试图判定语义前因，只判首现位置的交代缺失。

## 依赖与顺序

- 与 [08-26-qa-budget-rebalance](../08-26-qa-budget-rebalance/prd.md) 都要改 manifest 与 contract 测试。**本任务先落地**（新增 stage），预算再平衡任务在其之后 rebase，避免两边同时改 `expectedStages` 冲突。此顺序写在此处，不由树位置隐含。
