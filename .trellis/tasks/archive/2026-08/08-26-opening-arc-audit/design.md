# 开篇连读体检 · 技术设计

## 1. 分工：语义判开闭环，脚本做确定性裁决

悬念"开/闭"、主线"推进/打转"本质是语义判断，不可靠地纯脚本化。但一旦语义层把判断写成结构化 ledger，**累计计算与阈值裁决就是纯确定性的**，可回归测试。故：

- **语义层**（连读子代理，`references/arc-reading-protocol.md`）：读前 N 章，逐章产出「本章开了哪些悬念(open) / 闭了哪些悬念(close，引用被闭的 open id) / 是否推进主线(mainAdvance)」，写成 ledger JSON。
- **脚本层**（`skills/_shared/scripts/arc-ledger.js`）：吃 ledger JSON，算累计开环/闭环/净悬空/平均闭环延迟/主线推进步数，套阈值判 blocking，渲染收支表。

## 2. 目录形态

```
skills/opening-arc-audit/
├── SKILL.md
├── scripts/
│   └── test-arc-ledger.js   # 直接测试共享实现
└── references/
    ├── arc-reading-protocol.md   # 连读产 ledger 的子代理协议
    └── ledger-example.json       # 基于 demo 书前 15 章的示例 ledger（AC1 演示）
```

## 3. ledger schema

```json
{
  "book": "书名", "window": 15,
  "chapters": [
    {"num": 1, "opens": [{"id": "Q1", "q": "5天涨粉100万能不能成"}],
     "closes": [], "mainAdvance": true},
    {"num": 2, "opens": [{"id": "Q2", "q": "钟记者为何盯上江晨"}],
     "closes": ["Q1"], "mainAdvance": true}
  ]
}
```

- `opens[].id` 全局唯一；`closes` 是本章闭合的 open id 列表。
- `mainAdvance`：本章主角核心目标状态是否发生可指认改变（true=推进，false=原地循环/纯铺垫）。

## 4. arc-ledger.js 计算与裁决

- 窗口 = `min(window, 实际章数)`。
- 累计：`openCount`=所有 opens 数；`closeCount`=所有有效 closes 数（引用了存在且更早/同章开的 id）；`netOpen`=openCount−closeCount；`avgCloseDelay`=Σ(closeChapter−openChapter)/闭合数。
- `mainAdvanceSteps`=mainAdvance 为 true 的章数。
- **阈值裁决**（可配，默认）：`netOpen > closeCount && mainAdvanceSteps < ceil(window/3)` → `arc 级故弄玄虚` blocking。
- 校验：close 引用不存在的 id / 引用未来章开的 id → ledger 错误（退出码 2，防语义层填错表蒙混）。
- 输出：收支表（累计开/闭/净悬空/平均延迟/推进步数）+ 已知信息清单（所有 close 掉的 q）+ 悬而未决清单（未 close 的 open q）+ 裁决。`--json` 结构化。
- 退出码：0 无 blocking / 1 blocking / 2 ledger 错误或参数错误。

## 5. 阈值可配与题材

`--net-ratio`、`--advance-floor` 可覆盖默认。文档给建议档：爽文容忍低悬空（严）、悬疑容忍高悬空（松）。阈值是信号非铁律，blocking 必附收支表供作者复核，不自动改稿。

## 6. manifest 接入：延后

同 reader-comprehension-scan：是否进复合检查由父任务统一编排（避免与它、qa-budget 同时改 contract 计数）。本任务先交付独立可调用 skill，登记 `platform-skill-set.json`。

## 7. 回退

纯新增目录 + skill-set 一行 + adapters repair。回退 = 删目录、还原、repair。零现有回归面。
