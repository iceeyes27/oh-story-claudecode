# 长篇章节骨架模式 · 执行清单

## 1. 恢复候选系统基线

- [x] 统一候选目录为书根 `候选/`。
- [x] 恢复 promote 前质量检查和 `--no-scan`。
- [x] 运行 `python scripts/test-candidate-commit.py`，既有 13 项与新增环境失败项共 14/14 通过。

## 2. 新增骨架协议与验证器

- [x] 新增 `references/chapter-skeleton-workflow.md`。
- [x] 新增 `scripts/check-chapter-skeleton.js`。
- [x] 新增 `scripts/test-chapter-skeleton.js`，覆盖正常与主要边界。
- [x] 运行 `node scripts/test-chapter-skeleton.js`。

## 3. 接入 Skill 路由和状态

- [x] 修改 `SKILL.md`：长篇默认骨架、显式成稿、候选采用、扫描结论边界。
- [x] 修改 `progressive-disclosure.md`：三种章节状态与读取范围。
- [x] 修改 `workflow-daily.md`：仅显式成稿进入旧日更正文流程。
- [x] 修改 `candidate-workflow.md`：书根候选目录、外部成稿接入与实际正文追踪事务。
- [x] 修改 `flow-state.js` 及 `test-flow-state.sh`。

## 4. 验证

- [x] `node scripts/test-chapter-skeleton.js`
- [x] `bash scripts/test-flow-state.sh`
- [x] `python scripts/test-candidate-commit.py`
- [x] `python scripts/check-current-skill-contracts.py`
- [ ] `python C:/Users/Administrator/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/story-write`（已执行；通用验证器拒绝仓库既有 `version`、`disable` 扩展字段，仓库 `static-check.sh` 为 31/31）
- [x] `bash scripts/static-check.sh`
- [ ] `python scripts/check-unified-skill-upstream-drift.py`（重放最新 `origin/main` 后发现 `upstream/main` 又有 5 个统一目录映射变更；属于独立上游同步任务，本次不混入）
- [x] `node .agents/skills/story-setup/scripts/manage-skill-adapters.js repair`（基线 check 失败后执行）
- [x] `node .agents/skills/story-setup/scripts/manage-skill-adapters.js check`
- [x] `git diff --check`

## 5. 提交与推送

- [x] 检查全部变更，排除无关文件。
- [x] 只暂存本任务文件，按仓库现有中文 Conventional Commit 风格提交。
- [x] 推送到 `origin/main`，验证本地与远端提交一致（`196e304`）。

## 回退点

- 骨架功能是新增文件和集中路由修改，可按组件分别撤销。
- 候选系统只恢复先前通过测试的实现；出现问题时以 `33054da` 和 13 项回归测试为比较基线。
