# 开篇连读体检（子任务 · P0）

> 父任务：[08-26-narrative-logic-overhaul](../08-26-narrative-logic-overhaul/prd.md)
> 对应反馈：**"看了十几章实在看不下去"**。读者是连着看十几章弃书的，现有检查全是逐章或相邻章，没有 arc 级视角。

## Goal

新增一个 arc（开篇 N 章）级连读体检，量化"读者读到第 N 章时的信息负债"，把"故弄玄虚"变成可阻断的信号：**悬念开得多、解得少、主线不推进**。

## 为什么需要

- 现有 `check-chapter-boundary.js` 只看相邻两章，`review-plot-progression` 逐章看事件链。没有任何检查回答"读者连读前 15 章，累计掌握了什么、还欠着多少没解答的悬念、主线到底推进了多少"。
- "故弄玄虚"的本质是悬念只开不闭、主线原地打转。这是个**累积量**，只有 arc 级连读才能测。

## Requirements

### R1 悬念开闭环收支表

- 对开篇 N 章（默认 N=15，可配）连读，逐章登记：本章**新开**的悬念/问号、本章**闭合**的悬念。
- 输出一张收支表：截至第 N 章，累计开环数、累计闭环数、净悬空数、平均闭环延迟（开到闭隔几章）。
- 同时列出"读到第 N 章读者掌握的确定信息清单"和"仍悬而未决的问题清单"——直接对应读者脑内状态。

### R2 主线推进量

- 逐章标注本章是否推进主线（主角目标状态是否发生可指认的改变），给出前 N 章主线实际推进步数。
- 区分"推进"与"原地循环"（同一冲突反复、只加铺垫不结算）。

### R3 阻断阈值（把故弄玄虚量化）

- 给出可配的阻断规则，默认：**净悬空数 > 已闭环数 且 主线推进步数 < N/3** → 判 `arc 级故弄玄虚` blocking，附收支表证据。
- 阈值参数写进 skill 文档，允许按题材/平台调（悬疑本容忍更高悬空，爽文要求更低）。
- 阈值是"信号"不是"铁律"：blocking 输出必须附收支表让作者复核，不做自动改稿。

### R4 落地形态

- 优先做成新 skill `opening-arc-audit` 的语义连读流程（悬念开闭环判定需要语义，难纯脚本化）。
- 可脚本化的辅助部分使用共享 `skills/_shared/scripts/arc-ledger.js` + 回归测试；语义判定留在本 skill 文档。
- 是否并入复合检查作为 stage：**本任务先做成独立可调用 skill**，是否进 manifest 由父任务在两个 P0 都落地后统一决定（避免与 reader-comprehension-scan 同时改 contract 测试）。

## Acceptance Criteria

- [x] AC1：对 demo 书前 15 章连读，产出悬念收支表（累计开环/闭环/净悬空/平均延迟）与已知信息清单、悬而未决清单。
- [x] AC2：对一个人为构造的"只开不闭 + 主线打转"样例，阻断规则命中 `arc 级故弄玄虚` 并附证据；对一个正常推进样例不误报。
- [x] AC3：共享 `skills/_shared/scripts/arc-ledger.js` 有回归测试且 `skills/opening-arc-audit/scripts/test-arc-ledger.js` 通过。
- [x] AC4：阈值参数可配，文档写明不同题材的建议档位。
- [x] AC5：`bash scripts/static-check.sh`、`python scripts/check-current-skill-contracts.py` 通过；若登记新 skill，`platform-skill-set.json`/`local-only-skill-set.json` 与 adapters check 同步。

## Out of Scope

- 不做自动改稿。
- 不覆盖全书（只体检开篇 arc；全书节奏是另一回事）。
- 悬念开闭环判定不强求纯脚本，脚本只做可数部分。

## 依赖与顺序

- 与 [08-26-reader-comprehension-scan](../08-26-reader-comprehension-scan/prd.md) 独立，可并行开发。若两者都决定进 manifest，按父任务统一编排，reader-comprehension 先落地本任务后 rebase。
