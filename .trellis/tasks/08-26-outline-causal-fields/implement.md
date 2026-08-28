# 细纲跨章因果字段 · 执行清单

## 1. 校验脚本（先行，可独立测）

- [x] `skills/story-write/scripts/check-outline-causal.py`：三字段存在/非占位、前因章号解析与存在性校验、tracking 交叉验证（有则验无则降级）、blocking/advisory 分级、退出码。
- [x] `scripts/test-outline-causal.py`：正常、前因未来章(blocking)、前因不存在(blocking)、缺字段(advisory)、占位(advisory)、参数错误(2)。
- [x] `python scripts/test-outline-causal.py` 全绿。

## 2. 契约与模板

- [x] `scripts/current-contract.json` 加 3 条 `{rule, demo}`。
- [x] `story-outline.md`「细纲必填项」加 3 条 `- rule：说明`。
- [x] `python scripts/check-current-skill-contracts.py`（此时会要求 demo 20 章有字段，先失败——下一步补 demo）。

## 3. demo 数据

- [x] demo 20 章各追加 `#### 因果链`（前因/后果指向/读者已知），值自洽、前因指向真实更早章。
- [x] `python skills/story-write/scripts/check-outline-causal.py "demo/长篇/让你管账号，你高燃混剪炸全网"` 无 blocking。
- [x] `python scripts/check-current-skill-contracts.py` 通过（demo 20 章字段齐）。

## 4. 文档同步

- [x] `artifact-protocols.md`：细纲模板加因果链段说明（主说明放这里）。
- [x] `workflow-setup.md` Phase 3：新字段怎么填。
- [x] `long-mode.md`：Phase 4「检查细纲」加最短引用 + 因果字段一行；跑 `check-outline-causal.py` 的 blocking/advisory 语义。
- [x] `bash scripts/check-doc-budget.sh` 通过（未撑爆或已显式调 budget 记理由）。

## 5. 验证

- [x] `python scripts/test-outline-causal.py`
- [x] `python skills/story-write/scripts/check-outline-causal.py "demo/长篇/让你管账号，你高燃混剪炸全网"`
- [x] `python scripts/check-current-skill-contracts.py`
- [x] `bash scripts/static-check.sh`、`bash scripts/check-doc-budget.sh`
- [x] `node .agents/skills/story-setup/scripts/manage-skill-adapters.js check`

## 进度（2026-08-28 完成）

- 第 1-5 节全部完成。`python scripts/test-outline-causal.py` 7 项全绿；对 demo 书跑 `check-outline-causal.py` findings 0。
- 与原清单的两处偏差（按仓库实际结构调整，非缩减）：
  - 清单写的「`story-outline.md`『细纲必填项』」实际路径是 `skills/story-setup/references/templates/rules/story-outline.md`；细纲模板的唯一权威副本在 `workflow-setup.md` 的 Phase 3，`artifact-protocols.md` 按既有约定只放说明不放模板副本，避免双模板漂移。
  - demo 的三字段写成一个 `#### 因果链` 段承载三条 `- 字段：值`，契约仍按三条 `{rule, demo}` 逐字段强制。
- 热路径预算：long-mode 26418/27500、workflow-setup 12448/13000，长篇日更主会话 46675/48500，均未超。

## 回退点

- 还原 current-contract.json / story-outline.md / demo 20 章 / 3 文档，删脚本+测试。字段是叠加，无迁移。
