# 实施计划

## 顺序

1. 执行子任务 `08-11-claude-bash-prose-hooks`，验证真实 Claude 前置、成功写后和失败写后事件。
2. 执行子任务 `08-11-stage-boundary-authority`，完成 schema v3、校验器和 Stage 1/2/6 唯一来源。
3. 执行子任务 `08-11-review-batch-state`，完成状态 schema、revision 申领、恢复和只读限制。
4. 执行子任务 `08-11-scan-contract-parity`，完成起点字段、七猫周期及四平台通用契约。
5. 执行子任务 `08-11-codex-discovery-token`，完成目录发现与部署 token 修复。
6. 运行生成/同步工具，检查派生差异，再执行父任务完整验证。

## 验证层级

- 定向：Claude deployment/prose backstop、story-analyze boundary、story-review state、scan runtime、Codex hooks。
- 跨平台：shared files、hook parity、Claude/Codex/OpenCode/ZCode/story-setup adapter。
- 仓库：static check、static-check tests、current skill contracts、Python invocation、AI patterns。

## 分组恢复

- 每个子任务单独形成提交点并独立通过定向测试。
- 某一组失败时只处理该组；已通过组保持不变。
- 本地检查全部通过后才进入提交、推送或发布步骤；这些动作不属于当前规划任务。
