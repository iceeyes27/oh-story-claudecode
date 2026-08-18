# 实施计划

## 顺序

1. 加载 `trellis-before-dev` 与 Skill 层规范，复核当前工作区和任务状态。
2. 更新 `skills/story-deslop/SKILL.md`：加入 general 子任务路由、显式翻译触发、按需加载规则、翻译输出和参考导航；保持 novel 部分不变。
3. 新增 `skills/story-deslop/references/general-ai-trace-index.md`、`general-ai-trace-guide.md` 与 `translation-guardrails.md`，内容独立编写，不复制上游文本。
4. 新增 `skills/story-deslop/tests/general-mode-contract.test.js`，覆盖路由、按需加载、结构保护、信息守恒、索引锚点、advisory 语义和小说边界。
5. 更新 `package.json` 的 `test:contracts`，同时运行复合检查契约和 general-mode 契约。
6. 先运行新增测试与 Markdown 静态检查；失败时只修相关契约，不放宽既有检查。
7. 运行当前 Skill 契约、公开 Skill 覆盖、共享资产、小说扫描器和平台适配回归，确认框架执行不受影响。
8. 检查 `.agents/skills -> skills` 及 Claude/Codex/WorkBuddy adapter 状态，确认各入口读取同一权威资产。
9. 执行 `git diff --check`、差异范围和工作区检查；确认没有 CI、Hook、小说共享扫描器或无关文件改动。
10. 按 Trellis Phase 3 检查是否产生新的可复用规范；没有新增规范时记录无需修改 `.trellis/spec/`，再完成提交前检查。

## 验证命令

```text
node --test skills/story-deslop/tests/general-mode-contract.test.js
npm run test:contracts
bash scripts/static-check.sh
python scripts/test-static-check.py
python scripts/check-current-skill-contracts.py
python scripts/test-current-skill-contracts.py
node --test scripts/skill-publication-coverage.test.js
bash scripts/check-shared-files.sh
bash scripts/test-ai-patterns.sh
bash scripts/check-claude-adapter.sh
bash scripts/check-codex-adapter.sh
bash scripts/check-opencode-adapter.sh
bash scripts/check-zcode-adapter.sh
bash scripts/check-openclaw-skills.sh
bash scripts/check-reasonix-adapter.sh
node skills/story-setup/scripts/manage-skill-adapters.js check --root=.
npm run test:dashboard
git diff --check
```

完整 `npm test` 额外依赖 Playwright 浏览器；运行环境可用时执行并记录结果。浏览器依赖缺失必须单独报告，不得把确定性契约测试的通过结果扩大为浏览器验证通过。

## 验证结果（2026-08-18）

- `story-deslop` 定向契约 7/7、仓库契约 14/14 通过。
- 当前 Skill 契约、公开 Skill 覆盖、共享资产和小说扫描器回归通过。
- Claude、Codex、OpenCode、ZCode、OpenClaw、Reasonix 平台检查通过；adapter manager 94/94。
- Dashboard 单元测试 22 项通过，4 项因 Windows 权限语义跳过。
- `story-deslop` 静态检查与 `git diff --check` 通过；全仓静态检查仍报告 `HEAD` 已存在的 `story` 复合清单跨 Skill 诊断，本任务未修改相关文件。
- 完整 `npm test` 在 Playwright 阶段因本机未安装其 Chromium 可执行文件而停止；契约和 Dashboard 单元阶段均通过。

## 风险检查点

- `SKILL.md` 顶部共享判断和 general 的 “When to use” 必须同步修改，不能一处允许翻译、另一处仍拒绝。
- 翻译护栏不得把 Markdown 链接文本与链接目标混为同一保护范围；链接文本可翻译，目标必须原样保留。
- 表格内容可翻译，列数、分隔行与单元格对应关系不能改变。
- 通用痕迹指南中的规则不得标成小说 scanner 的 blocking 类别，也不得修改 `_shared`。
- adapter 验证只检查现有链接和内容一致性，不重建或覆盖用户自有平台 Skill。
