# 修复仓库检查并停用 CI

## Goal

修复当前仓库已确认的检查与文档缺陷，并永久移除 GitHub Actions CI；所有质量验证改为在本地执行。

## Requirements

- 删除 `.github/workflows/` 下全部 GitHub Actions 工作流，不保留自动、定时或手动触发入口。
- 保留并继续维护 `scripts/` 与 npm 中的本地检查命令。
- 将退化检测回归脚本改为调用 `_shared` 中的唯一检测器实体，并在目标缺失时给出明确错误。
- 在确认上游 `story-long-analyze` 变更已迁入统一 `story-analyze` 后，将漂移基线更新到当前 `upstream/main`。
- 将 story-setup v22 升级步骤中的 `setup_skill_version` 修正为当前权威值 `1.2.7`，并扩大契约回归以覆盖升级步骤。
- 更新仍把 GitHub CI 描述为验证入口的仓库文档与 Trellis 规范。
- 不修改小说示例、业务 Skill 行为或无关文件。
- 完成本地验证后提交并推送到 `origin/main`。

## Acceptance Criteria

- [x] GitHub Actions 工作流全部删除，并由本地契约检查禁止重新引入。
- [x] `scripts/test-degeneration.sh` 使用 `skills/_shared/scripts/check-degeneration.js`，回归测试通过。
- [x] `python scripts/check-unified-skill-upstream-drift.py` 通过。
- [x] 当前契约检查能验证升级步骤中的版本值，相关测试通过。
- [x] 静态检查、共享资源检查、Dashboard API 测试及变更相关回归通过。
- [x] 工作区只包含本任务修改，`git diff --check` 通过。

## Constraints

- 不再依赖 GitHub Actions 结果判定仓库质量。
- 上游将来新增工作流时，不自动合并进本 fork；仍以本地验证脚本为准。
