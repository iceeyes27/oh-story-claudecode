# 开篇连读体检 · 执行清单

## 1. 脚本 + 测试

- [x] `skills/opening-arc-audit/scripts/arc-ledger.js`：读 ledger JSON、累计计算、阈值裁决、收支表渲染、`--json`、ledger 校验、退出码 0/1/2。
- [x] `skills/opening-arc-audit/scripts/test-arc-ledger.js`：正常推进不 blocking、只开不闭+主线打转→blocking、close 引用不存在 id→退出码 2、close 引用未来章→退出码 2、avgCloseDelay 计算正确、阈值可配、缺参数退出码 2。
- [x] `node scripts/test-arc-ledger.js` 全绿。

## 2. skill 文档

- [x] `SKILL.md`：frontmatter、语义/脚本分工、ledger schema、脚本用法、阈值档位、结论边界、链接两个 references。
- [x] `references/arc-reading-protocol.md`：连读产 ledger 的子代理 prompt（前 N 章、逐章开/闭/推进、输出 ledger JSON）。
- [x] `references/ledger-example.json`：基于 demo 书前 15 章手工构造的示例 ledger（AC1 演示），SKILL.md 链接它。

## 3. 登记与部署

- [x] `scripts/platform-skill-set.json` 加 `opening-arc-audit`（有序）。
- [x] `manage-skill-adapters.js repair` 后 `check`。

## 4. 验证

- [x] `node scripts/test-arc-ledger.js`。
- [x] 用 `references/ledger-example.json` 跑 `arc-ledger.js` 产出 demo 收支表（AC1）。
- [x] `python scripts/static-check.py`、`bash scripts/static-check.sh`。
- [x] `python scripts/check-current-skill-contracts.py`。

## 回退点

- 纯新增。删 `skills/opening-arc-audit/`、还原 skill-set、repair adapters。

## 交接父任务集成

- manifest 接入与 reader-comprehension-scan、qa-budget-rebalance 同批做。
