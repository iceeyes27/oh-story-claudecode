# 实施计划

- [x] 修正文档基线、状态说明与验收公式，激活父任务。
- [x] 实现首次交代保护及“首次保留、重复可删”测试。
- [x] 抽取 rc-01、arc-02 共享实现并复跑 13/13、12/12。
- [x] 实现 candidate binding v2、逐文件摘要验证、临时正文视图与第 15 章 arc 复验。
- [x] 补候选逻辑门的边界测试与崩溃恢复测试。
- [x] 实现 manifest 场景适用范围和纯中文逻辑占比契约。
- [x] 实现平直叙事冷路径、新书默认值、旧书兼容读取和标题双档。
- [x] 用 canonical 工具同步共享资产和平台适配。
- [x] 执行针对性测试、文档预算、共享/适配检查与 release 23 项；回写 AC 和任务状态。

## 主要验收命令

```powershell
node skills/reader-comprehension-scan/scripts/test-first-mention.js
node skills/opening-arc-audit/scripts/test-arc-ledger.js
python scripts/test-outline-causal.py
node scripts/test-chapter-titles.js
node skills/story/tests/composite-check-contract.test.js
bash scripts/check-doc-budget.sh
bash scripts/check-shared-files.sh
python scripts/check-current-skill-contracts.py
node .agents/skills/story-setup/scripts/manage-skill-adapters.js check
node scripts/quality-gate.mjs --profile release
```
