# 技术设计

## 总体流程

本次采用“两阶段提交 + 专用 worktree”结构：先修复同步策略的唯一 unknown 路径，再由仓库状态机创建并验证上游双亲合并提交。主工作区不直接解决内容冲突。

## 阶段 A：同步策略准备

- 在 `scripts/upstream-integration.json` 的 canonical 规则中只增加 `docs/reference-workflow-cleanup.md` 精确路径。
- 在 `scripts/sync-upstream.test.js` 增加正反用例，避免把整个 `docs/` 无条件开放。
- 运行同步单测和快速质量检查；按 Trellis 提交确认流程提交并推送该准备提交，使新的 `origin/main` 成为状态机可固定的基线。

## 阶段 B：受控上游集成

1. 使用更新后的 `origin/main` 与固定上游 `fde1754...` 执行 `prepare`，在专用 worktree 产生真实冲突清单。
2. 生成逐路径 decision 文件：
   - forbidden：`reject`；
   - shared / generated：`regenerate`；
   - canonical：`merge` 后逐冲突检查 fork 身份和本地扩展；
   - unified：`adapt` 到 `skills/story-write` 对应入口；
   - protected：仅在出现时逐项说明，默认保留 fork 资产。
3. 按功能组处理冲突，而不是采用整批 ours/theirs：
   - 文风优先级与书目录白名单；
   - reference 索引、项目文件与追踪初始化；
   - 长篇 prompt 组装和现有候选边界；
   - 短篇 Phase 3/4 按需加载；
   - 去味、审查、Hook 与共享资源；
   - 发布说明和 fork 版本身份。
4. 从 `skills/_shared/` 同步共享副本，再重建平台适配入口。生成文件只接受生成器输出。
5. `review` 登记所有人工迁移理由，`validate` 更新上游基线并执行 release 质量配置。

## 兼容规则

- 上游新行为进入统一 `story-write` 的 long/short mode，不恢复拆分目录。
- 文风要求只能改变表达，不能改写细纲事实、信息揭露、候选采用和追踪事务边界。
- 上游发布版本 `0.7.10` 作为同步来源记录；fork 对外版本保持 `0.8.1`，插件数量与 fork 安装地址保持现状。
- 上游对 agent/template 的变化需要在升级说明中明确重新部署和新开会话；fork 的部署契约号保持当前 `agents_version: 30`，不采用更低版本。

## 提交与发布

- 准备提交：同步策略精确分类及回归测试。
- 集成提交：由 `promote` 创建的双亲上游合并提交。
- 验证通过后将本地 `main` 快进到集成提交并普通推送 `origin/main`。
- 任一阶段失败时停止推送；`promote` 前可用 `abort` 删除专用 worktree 和集成分支，主工作区内容不受影响。
