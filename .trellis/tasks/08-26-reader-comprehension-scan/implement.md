# 读者视角理解力检查 · 执行清单

## 1. 脚本 + 测试（先行，可独立验证）

- [x] 新增 `skills/reader-comprehension-scan/scripts/check-first-mention.js`：收集 `正文/`、候选专名提取、首现定位、交代锚点判定、advisory/blocking 分级、`--json`、退出码。
- [x] 新增 `skills/reader-comprehension-scan/scripts/test-first-mention.js`：正常交代不报、首现零交代报 advisory、跨章回扣+首现零交代升 blocking、参数错误退出码 2。
- [x] `node skills/reader-comprehension-scan/scripts/test-first-mention.js` 全绿。
- [x] 对 demo 书 `node skills/reader-comprehension-scan/scripts/check-first-mention.js "demo/长篇/让你管账号，你高燃混剪炸全网"` 产出可核查清单、且不误报到不可用。

## 2. skill 文档

- [x] `SKILL.md`：frontmatter（name=reader-comprehension-scan、description）、只读正文原则、脚本用法、三问法概述、链接 references/reading-protocol.md、结论边界。
- [x] `references/reading-protocol.md`：三问分批子代理 prompt（5 章/批、只喂正文、重写/追问对照、穷举输出）。
- [x] 确认 SKILL.md 链接到 reading-protocol.md（避免 dead-reference warning）。

## 3. 登记与部署

- [x] `scripts/platform-skill-set.json` 加 `reader-comprehension-scan`（保持数组有序）。
- [x] `node .agents/skills/story-setup/scripts/manage-skill-adapters.js repair` 后 `check`。

## 4. 验证

- [x] `python scripts/static-check.py`（新 skill frontmatter/链接/dead-reference 全过）。
- [x] `python scripts/check-current-skill-contracts.py`。
- [x] `node skills/reader-comprehension-scan/scripts/test-first-mention.js`。
- [x] `git diff --check`。

## 回退点

- 纯新增。删 `skills/reader-comprehension-scan/`、还原 `platform-skill-set.json`、repair adapters 即完全回退。

## 交接给父任务集成

- manifest 接入（新增 `reader-comprehension` stage + 同步 4 处计数）不在本清单，记入父任务统一编排，与 qa-budget-rebalance 的计数变化同批做。
