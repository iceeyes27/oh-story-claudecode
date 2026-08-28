# 细纲跨章因果字段 · 执行清单

## 1. 校验脚本（先行，可独立测）

- [ ] `skills/story-write/scripts/check-outline-causal.py`：三字段存在/非占位、前因章号解析与存在性校验、tracking 交叉验证（有则验无则降级）、blocking/advisory 分级、退出码。
- [ ] `scripts/test-outline-causal.py`：正常、前因未来章(blocking)、前因不存在(blocking)、缺字段(advisory)、占位(advisory)、参数错误(2)。
- [ ] `python scripts/test-outline-causal.py` 全绿。

## 2. 契约与模板

- [ ] `scripts/current-contract.json` 加 3 条 `{rule, demo}`。
- [ ] `story-outline.md`「细纲必填项」加 3 条 `- rule：说明`。
- [ ] `python scripts/check-current-skill-contracts.py`（此时会要求 demo 20 章有字段，先失败——下一步补 demo）。

## 3. demo 数据

- [ ] demo 20 章各追加 `#### 因果链`（前因/后果指向/读者已知），值自洽、前因指向真实更早章。
- [ ] `python skills/story-write/scripts/check-outline-causal.py "demo/长篇/让你管账号，你高燃混剪炸全网"` 无 blocking。
- [ ] `python scripts/check-current-skill-contracts.py` 通过（demo 20 章字段齐）。

## 4. 文档同步

- [ ] `artifact-protocols.md`：细纲模板加因果链段说明（主说明放这里）。
- [ ] `workflow-setup.md` Phase 3：新字段怎么填。
- [ ] `long-mode.md`：Phase 4「检查细纲」加最短引用 + 因果字段一行；跑 `check-outline-causal.py` 的 blocking/advisory 语义。
- [ ] `bash scripts/check-doc-budget.sh` 通过（未撑爆或已显式调 budget 记理由）。

## 5. 验证

- [ ] `python scripts/test-outline-causal.py`
- [ ] `python skills/story-write/scripts/check-outline-causal.py "demo/长篇/让你管账号，你高燃混剪炸全网"`
- [ ] `python scripts/check-current-skill-contracts.py`
- [ ] `bash scripts/static-check.sh`、`bash scripts/check-doc-budget.sh`
- [ ] `node .agents/skills/story-setup/scripts/manage-skill-adapters.js check`

## 回退点

- 还原 current-contract.json / story-outline.md / demo 20 章 / 3 文档，删脚本+测试。字段是叠加，无迁移。
