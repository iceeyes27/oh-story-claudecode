# 移除 OpenCode 平台并解除 release 的外部工具依赖

## Goal

让 `quality-gate --profile release` 在本机达到 `PASS`（而非 `BLOCKED`），从而解除上游同步 `validate` 阶段的阻塞；同时按作者决定，把 OpenCode 从本 fork 的支持平台中完整移除。

背景：`sync-upstream.js:516` 要求 quality 报告状态字面等于 `PASS`，`BLOCKED` 同样抛错。当前 release 是 `30/33 PASS, 0 FAIL, 3 BLOCKED`，三项全部卡在外部工具缺失。

## 作者决定（2026-09-07）

| 项 | 决定 |
|---|---|
| OpenCode | **完整移除平台**。作者已删除本机 CLI，不再保留该平台。 |
| Codex | **保留平台**，但把 `codex-cli-e2e` 移出 release（本机未装 Codex CLI，且不打算装） |
| Playwright | **不下载**浏览器分包，把 `dashboard-e2e` 移出 release |

## Requirements

### R1：release profile 不再依赖本机外部工具

- `codex-cli-e2e`、`dashboard-e2e` 移出 `release` profile
- 两项检查本身保留在 `checks` 注册表里，便于装好工具的环境按名单独运行；只是不再是 release 的准入条件
- 移出理由写入配置或提交信息，不留无解释的删除

### R2：完整移除 OpenCode 平台

删除：
- `scripts/check-opencode-adapter.sh`、`scripts/sync-opencode.py`、`scripts/test-opencode-cli-e2e.sh`、`scripts/test-opencode-plugin.mjs`
- `skills/story-setup/references/opencode/`（31 个文件）

清理引用：
- `scripts/quality-gate.json`：删 `opencode-adapter`、`opencode-cli-e2e` 两项检查及其在 release 中的引用
- `scripts/platform-capabilities.json`：删 `opencode` 平台条目
- `scripts/shared-assets.json`：删指向 opencode 的同步目标（`story-hook-core`、`book-discovery-contract`）
- `scripts/release-manifest.json`：重新生成
- 其余脚本内引用：`check-codex-adapter.sh`、`check-current-skill-contracts.py`、`check-platform-capabilities.mjs`、`check-story-setup-deployment.sh`、`check-hook-regex-sync.sh`、`generate-codex-agents.py`、`skill-numbering.py`、`static-check.py`、`test-prose-net-parity.sh`、`test-static-check.py`
- story 系列技能里的 agent 查找顺序（`.claude/agents/` → `.opencode/agents/` → `.codex/agents/`）：`story-setup`、`story-write`、`story-analyze`、`story-import`、`story-review`、`story-deslop`、`story`、`browser-cdp` 的 SKILL.md，以及 `long-mode.md`、`workflow-setup.md`
- 共享 hook 核心里的 opencode 分支：`templates/hooks/story_hook_core.js` 及其 antigravity / zcode 同步副本、`codex/hooks/story_codex_hook.py`
- 文档：`README.md`、`README_EN.md`、`CONTRIBUTING.md`、`AGENTS.md`、`scripts/README.md`、`skills/story-setup/UPGRADING.md`

### R3：让上游同步不再反复冲突

上游 `zenstory-ai` 仍然发布 OpenCode 支持。若只是删除文件，未来每次同步都会把这些路径重新带回来并产生冲突（本次同步已有 21 个冲突，不能再加）。

- 在 `scripts/upstream-integration.json` 的 `forbidden` 策略中登记 OpenCode 路径前缀，与 `.github/workflows/` 同一机制，使编排器每次自动 `reject`
- 理由字段要写清是 fork 的平台取舍，不是临时跳过

## 范围边界（明确假设）

**不在本任务范围内**，即使文中出现 "opencode" 字样：

- `skills/trellis-*`：Trellis 是开发工作流框架，其对 OpenCode 的平台支持独立于小说工具是否部署到该平台；删除会打断 Trellis 自身能力
- `.trellis/tasks/archive/`、`.trellis/spec/`：历史任务与既有规范，不改写历史
- `docs/evaluations/**/evidence/`：不可变证据快照
- `CHANGELOG.md` 既有条目：追加新条目，不改写历史记录
- `.claude/worktrees/`：其他分支的工作区

## Constraints

- 热路径文档预算（`check-doc-budget.sh`）必须保持通过；删除 opencode 相关行会释放预算，不得顺手塞入其他内容
- 受管共享资产改动后必须 `sync-shared-assets.py sync`，`check-shared-files.sh` 保持通过
- 不得为让门禁变绿而删测试或放宽断言；`platform-capabilities`、`static-check`、`check-story-setup-deployment` 等平台契约检查必须真实通过

## Acceptance Criteria

- [x] `node scripts/quality-gate.mjs --profile release` 状态为 **PASS**（不是 BLOCKED）
- [x] `node scripts/quality-gate.mjs --profile affected` 全项通过
- [x] `git ls-files | grep -i opencode` 在排除范围边界所列路径后无输出
- [x] `scripts/upstream-integration.json` 含 OpenCode 的 forbidden 规则，且 `sync-upstream.js status` 可正常加载策略
- [x] `bash scripts/check-doc-budget.sh` 通过
- [x] `bash scripts/check-shared-files.sh` 通过
- [x] `codex-cli-e2e` 与 `dashboard-e2e` 仍存在于 `checks` 注册表，只是不在 release profile 中

## 后续依赖

完成后重新执行上游同步：`upstream/main` 的 `b446c365d398`（10 个 commit）重新 `prepare`。已定策略——`tests/` 已归类 canonical（`709b7af`）；四个确定性检查器走 `adapt`（改 `skills/_shared/` 源后 sync）；短篇 `SKILL.md` 重构与 `workflow-design.md` 走 `reject`；OpenCode 路径由本任务加入 forbidden 后自动 reject。
