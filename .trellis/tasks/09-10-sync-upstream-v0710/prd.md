# 合并上游 v0.7.10 更新

## Goal

将 `zenstory-ai/oh-story-claudecode:main` 的 4 个新增提交完整吸收到 `iceeyes27/oh-story-claudecode:main`，保留本 fork 的统一 Skill、作者审批、平台支持和本地质量门禁，并将验证后的结果推送到 `origin/main`。

## Background

- 2026-09-10 刷新远端后，`origin/main` 为 `6bb119818b9c73ca4876b3b099d6f6ea99731cf0`，`upstream/main` 为 `fde17546758c58ad4d3306ef93d0db8ad28f9f3c`，共同基线为 `1e2488b80190197bc352bb3f5d852f5d7f251100`。
- 两端分歧为 fork 独有 155 个提交、upstream 独有 4 个提交；4 个上游提交均未被 fork 等价吸收。
- 上游增量共 109 个路径、2693 行新增、1019 行删除；54 个路径双方自共同基线后都修改过。
- 当前主工作区在建立本任务前为干净状态；其他 Trellis 任务不属于本次同步。

## Requirements

- R1：吸收上游 4 个提交中的文风优先级、引用读取、写作检查整合、短篇分阶段加载和 v0.7.10 说明。
- R2：只使用 `scripts/sync-upstream.js` 的 `prepare → review → validate → promote` 状态机，并固定双方完整 SHA；不得直接在主工作区执行普通合并。
- R3：先把 `docs/reference-workflow-cleanup.md` 精确登记为可合并文档并增加策略回归测试，消除唯一 unknown 路径，不扩大整个 `docs/` 的默认权限。
- R4：排除 `.github/workflows/` 和 OpenCode 路径；保留 `.trellis/`、同步状态机、质量门、发布清单、作者候选采用边界等 fork 资产。
- R5：把上游 `story-long-write` / `story-short-write` 的 33 个变更逐项迁入统一 `story-write`；不得恢复被 fork 删除的拆分 Skill 跟踪路径。
- R6：共享资源从 `skills/_shared/` 维护，部署副本和平台适配入口通过生成工具重建，不手工复制生成文件。
- R7：保留 fork 版本 `0.8.1`、`setup_skill_version: 1.2.11` 和 18 个公开 Skill 的发布身份；纳入上游 v0.7.10 变更说明，不把 fork 降级为上游 `0.7.10`。
- R8：只有完整 release 质量配置通过后才能创建双亲合并提交；提交前按 Trellis 规则再次向用户展示提交批次。
- R9：合并提交的第二父节点必须是 `fde17546758c58ad4d3306ef93d0db8ad28f9f3c`；随后仅快进本地主工作区并普通推送到 `origin/main`，禁止强推。

## Acceptance Criteria

- [ ] 同步策略对 109 个上游路径均有合法分类，没有 unknown、pending review 或未解决冲突。
- [ ] Git 不跟踪 `.github/workflows/`、OpenCode 路径或 `story-long-*` / `story-short-*` 拆分 Skill。
- [ ] 4 个上游提交均成为最终 `origin/main` 的祖先，合并提交第二父节点为固定上游 SHA。
- [ ] 文风逐维优先级、书目录本地白名单、引用按需读取、短篇 Phase 3/4 分工在统一架构中有对应实现和测试。
- [ ] fork 的候选采用、追踪事务、作者记忆、复合检查、平台清单和版本身份保持有效。
- [ ] `node scripts/quality-gate.mjs --profile release` 返回完整 PASS；相关专项测试和 `git diff --check` 通过。
- [ ] 最终本地 `main`、`origin/main` 与合并提交一致，分歧为 `0/0`，工作区没有未合并或意外暂存文件。
- [ ] 现有无关 Trellis 任务和历史评估资料未被改写。

## Out of Scope

- 恢复 GitHub Actions 或 OpenCode 支持。
- 恢复上游拆分的长短篇 Skill 架构。
- 修改用户小说项目或向上游仓库推送。
- 运行依赖外部 CLI 或浏览器安装的 `external` 质量配置。
