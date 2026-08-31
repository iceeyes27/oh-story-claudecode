# 细纲跨章因果字段（子任务 · P1）

> 父任务：[08-26-narrative-logic-overhaul](../08-26-narrative-logic-overhaul/prd.md)
> 对应反馈：**逻辑不通**。在最便宜的位置（细纲）拦截因果断裂，而不是等成稿后再查。

## Goal

给逐章细纲增加记录跨章因果关系的必填字段，并写脚本对 `_tracking-state.json` 校验前因是否指向真实已发生的事实。让"本章为什么发生"在写正文前就必须说清、且可验证。

## 为什么

现有细纲字段（见 `scripts/current-contract.json` 的 `required_outline_sections`：阶段位置、结构公式、禁止提前释放、内容概括、情节安排、人物关系和出场顺序、情节细化、结尾设定和钩子）全是**情绪营销与结构字段**，没有一个记录"本章的前因是第几章的什么事、本章的后果指向哪里"。因果链从细纲阶段就没有落点，成稿自然接不上。

## Requirements

### R1 新增三个细纲字段

在 `required_outline_sections` 增加：
- `前因`：指向具体章号 + 事件（本章由此前哪一章的什么已发生事实驱动）。开篇章可写 `开篇无前因`。
- `后果指向`：本章产生的、后续章节会用到的结果/变化（伏笔、状态、承诺）。
- `读者此刻已知/未知`：进入本章时读者手上应有/尚无的关键信息（与"禁止提前释放"配合，防止用读者还不知道的东西当理所当然）。

### R2 契约同步（本仓库改字段的固定动作）

新增 required section 会牵动多处，必须一致：
- `scripts/current-contract.json` 的 `required_outline_sections`（rule + demo 双列）。
- demo 书 `demo/长篇/.../大纲/细纲_第0NN章.md` 需补齐新字段（`expected_demo_outline_count=20`，20 章都要有），否则契约检查挂。
- `skills/story-write/references/long-mode.md` 与 `chapter-skeleton-workflow.md`、`artifact-protocols.md` 里细纲字段清单同步。
- `skills/story-write/references/workflow-setup.md`（Phase 3 建纲）说明新字段怎么填。
- 注意热路径预算：`long-mode.md` 当前 26223/27500，余量仅 1277 字。新增字段说明**优先放 `artifact-protocols.md`/`workflow-setup.md`**（非最热路径），`long-mode.md` 只加最短引用。必要时在 `scripts/doc-budget.json` 显式调 budget 并写明理由。

### R3 校验脚本

- `scripts/check-outline-causal.py` 增加 `--strict`（与既有 `check-outline-copy.js` 并列）：
  - 检查每章细纲三个新字段存在且非占位。
  - `前因` 指向的章号 ≤ 本章号且该章存在（不能引用未来章作前因）。
  - 有 `_tracking-state.json` 时，交叉验证 `前因` 引用的具体事件锚点是否为已登记的已发生事实；悬空即 fail。无追踪时严格模式仍要求可定位的正文事件锚点。
- 新写作路径调用 `--strict`；缺字段、占位、未来章或悬空事件返回非零。旧项目无 `--strict` 时保持既有 advisory 行为。
- 带回归测试：正常、前因指向未来章、前因指向不存在事件、字段缺失四类。

### R4 校验接入

- 章节骨架/成稿写前检查已经读细纲（`long-mode.md` Phase 4 步骤 1「检查细纲」），在该处调用新脚本，缺字段时按既有"必须先补建细纲再写正文"逻辑阻断。

## Acceptance Criteria

- [x] AC1：细纲模板与 demo 书 20 章补齐三个新字段。
- [x] AC2：`python scripts/check-outline-causal.py <书目录> --strict` 对前因指向未来章/不存在事件/缺字段/占位返回非零并指明；正常细纲返回 0。无 `--strict` 的旧项目行为兼容。回归测试全绿。
- [x] AC3：`python scripts/check-current-skill-contracts.py`（含 `required_outline_sections` 与 demo 计数校验）通过。
- [x] AC4：`bash scripts/check-doc-budget.sh` 通过（新增说明未撑爆热路径，或已显式调 budget 并记录理由）。
- [x] AC5：`bash scripts/static-check.sh` 通过。

## Out of Scope

- 不改追踪事务格式（`tracking_commit.py`）。
- 不做因果的语义正确性判断，只做"前因指向的事实是否真实已发生"的存在性/时序校验。
- 不改短篇细纲。

## 依赖与顺序

- 独立于两个 P0。修改面主要在 story-write 细纲契约，与 reader-comprehension（改 story 复合检查）不冲突，可并行。
