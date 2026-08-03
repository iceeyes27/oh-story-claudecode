# Repair fork integrity

## Goal

修复统一 Skill 分叉在重命名后的静默上游漂移、运行时守卫不同步和仓库结构校验失效，使公开仓库的 Skill 资产、元数据与校验脚本保持可验证的一致状态。

## Requirements

- 保持 11 个统一 Skill 的目录结构；不得恢复已废弃的 `story-long-*` 或 `story-short-*` Skill。
- 以 `skills/_shared/` 为唯一共享规则来源，运行时 hook、扫描器和说明引用同一份规则。
- 修复静态检查中确认的本地路径、跨 Skill 依赖与错误引用；Trellis 指令中的项目工件名称不得被误判为 Skill 资产路径。
- 统一公开元数据版本为 `0.8.0`。
- 清除仅存在于本机的空旧目录与失效 Git worktree 登记；只删除已确认合入 main 的本地分支。
- 不提交、不推送本次变更。

## Acceptance Criteria

- [ ] `bash scripts/static-check.sh` 通过。
- [ ] `bash scripts/check-shared-files.sh` 通过。
- [ ] `bash scripts/check-python-invocation.sh` 通过。
- [ ] `bash scripts/check-hook-regex-sync.sh`、`bash scripts/test-ai-patterns.sh`、`bash scripts/test-prose-net-parity.sh` 通过。
- [ ] `python scripts/test-static-check.py` 通过，且包含 Trellis 项目工件引用的回归用例。
- [ ] `python scripts/check-unified-skill-upstream-drift.py` 通过。
- [ ] `git diff --check` 通过。

## Notes

- 本任务只修复已确认问题；不改变写作流程的业务语义。
