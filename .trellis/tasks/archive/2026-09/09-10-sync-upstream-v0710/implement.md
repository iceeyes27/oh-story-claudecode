# 执行计划

1. 读取 `trellis-before-dev`、Skill 规范和本任务材料，重新确认主工作区状态及双方固定 SHA。
2. 修改同步策略和策略单测，运行：
   - `node --test scripts/sync-upstream.test.js`
   - `node scripts/quality-gate.mjs --profile fast`
   - `git diff --check`
3. 按 Trellis 提交确认要求展示准备提交，确认后提交并推送 `origin/main`；再次 fetch 并固定新的 origin SHA。
4. 执行 `node scripts/sync-upstream.js prepare --origin-sha <new-origin-sha> --upstream-sha fde17546758c58ad4d3306ef93d0db8ad28f9f3c --worktree D:\\code\\oh-story-upstream-fde1754`。
5. 检查状态文件、真实冲突和每个上游路径，编写 decisions JSON；按 `design.md` 的功能组在专用 worktree 迁移内容。
6. 重建共享与平台资产：
   - `python scripts/sync-shared-assets.py sync`
   - `node skills/story-setup/scripts/manage-skill-adapters.js repair --root=.`
   - 独立执行 adapter `check`
7. 执行专项测试：同步分类、统一 Skill 漂移、文风优先级、作者记忆、写手管线、共享文件、部署和平台适配。
8. 执行 `review`，确认 pending、unknown、冲突和禁止路径均为零。
9. 执行 `validate --quality-profile release`；要求 30 个本地检查全部 PASS，并运行 `git diff --check`。
10. 由 `trellis-check` 对全部改动、版本身份、统一架构、边界条件和回归风险做最终检查，修复后重跑相关验证。
11. 展示最终提交批次；用户确认后执行 `promote`，核对双亲、树哈希和固定上游 SHA。
12. 主工作区执行 `git merge --ff-only <merge-commit>`，普通推送 `origin main`；验证本地与远端提交一致、分歧 `0/0`，且无未合并或意外暂存内容。
13. 完成 Trellis 任务记录与归档，不把其他活动任务并入本次提交。
