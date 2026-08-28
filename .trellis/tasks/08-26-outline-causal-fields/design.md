# 细纲跨章因果字段 · 技术设计

## 1. 三个新字段

| rule（story-outline.md 必填项名） | demo（细纲 bullet 名） | 语义 |
|---|---|---|
| 前因 | 前因 | 本章由此前哪一章的什么已发生事实驱动；开篇写「开篇无前因」 |
| 后果指向 | 后果指向 | 本章产生的、后续章节会用到的结果/伏笔/承诺 |
| 读者已知 | 读者已知 | 进入本章时读者手上应有/尚无的关键信息（与「禁止提前释放」配合） |

demo 每章以 `#### 因果链` 段承载，段内三条 bullet（`- 前因：…` 等）——`extract_demo_outline_fields` 认 `- X：` 前缀，追加到文件尾不破坏现有结构。

## 2. 契约同步点（check-current-skill-contracts.py 强制）

校验逻辑（已核对源码）：
- `outline_rule_contract_findings`：每个 `rule` 必须出现在 `story-outline.md`「细纲必填项」列表（`- rule：`）。
- demo 校验：`required_outline_sections` 每个 `demo` 必须出现在 demo **20 章每一章**的 heading 或 `- demo：` bullet。
- 测试 `test_structured_outline_contract` 从 manifest 派生字段名、非硬编码 → 加字段不破坏测试。

改动：
1. `scripts/current-contract.json` `required_outline_sections` 加 3 条 `{rule, demo}`。
2. `skills/story-setup/references/templates/rules/story-outline.md`「细纲必填项」加 3 条 `- rule：说明`。
3. demo 20 章 `细纲_第0NN章.md` 各追加 `#### 因果链` 段（值自洽，前因指向真实更早章）。
4. 同步字段清单的文档：`story-write/references/long-mode.md`、`artifact-protocols.md`、`workflow-setup.md`。热路径预算紧（long-mode 余 1277 字），**主说明放 artifact-protocols.md / workflow-setup.md（冷/次热），long-mode.md 只加最短引用**；撑爆则显式调 `doc-budget.json` 记理由。

## 3. 校验脚本 check-outline-causal.py

- 位置：`skills/story-write/scripts/check-outline-causal.py`（与 candidate-commit.py、flow-state.js 并列）；测试 `scripts/test-outline-causal.py`（仓库根惯例）。
- 检查每章细纲：
  - 三字段存在且非占位（`待补充/TBD/___/空` 视为缺）。
  - `前因` 若非「开篇无前因」，解析出的章号必须 ≤ 本章号且该章细纲存在。
  - 有 `_tracking-state.json` 时交叉验证前因引用的事实是否已登记；无追踪则降级只验章号存在性。
- **严重度分级（稳健性关键）**：
  - `前因指向未来章 / 不存在的章` = **blocking**（逻辑错误，退出码 1）。
  - `字段缺失 / 占位` = **advisory**（退出码 0，提示补建）。理由：存量用户项目的旧细纲没有这些字段，若硬 blocking 会把所有旧项目卡死。新写细纲按模板带上，旧的渐进补。
- 退出码：0 无 blocking / 1 有 blocking / 2 参数或读取错误。带回归测试：正常、前因未来章(blocking)、前因不存在章(blocking)、字段缺失(advisory)、占位(advisory)。

## 4. 写作流程接入

`long-mode.md` Phase 4「检查细纲」处加一句：写前对本章细纲跑 `check-outline-causal.py`，**blocking（前因指向错误）阻断**，advisory（缺字段）提示补建但不阻断。不改现有必填字段的 fail-fast 语义（那些仍硬阻断）。

## 5. 兼容与回退

- 新字段对存量项目是 advisory，不 breaking。
- demo 数据与文档是叠加，回退 = 还原 4 处文件 + 删脚本/测试。
- 不改 tracking_commit.py / 追踪事务格式。
