# 上游增量审计

## 固定引用

- fork：`origin/main` = `6bb119818b9c73ca4876b3b099d6f6ea99731cf0`
- upstream：`upstream/main` = `fde17546758c58ad4d3306ef93d0db8ad28f9f3c`
- 共同基线：`1e2488b80190197bc352bb3f5d852f5d7f251100`
- 分歧：fork 155，upstream 4

## 上游 4 个提交

1. `12a300a`：统一当前请求、本书文风、作者记忆、对标和默认参考的逐维优先级；增加书目录本地白名单及相关测试。
2. `47f90a9`：保留 reference 的按需读取，拆出项目文件、追踪初始化、对标召回和去味 Gate 文档，整合写作检查职责。
3. `abe9663`：发布 v0.7.10、agents version 30 及升级说明。
4. `fde1754`：把短篇 Phase 3/4 细则拆入按阶段加载的 reference，减少入口常驻文本。

## 路径分类

对基线到目标的 109 个路径按当前策略只读分类：

- canonical：63
- unified：33
- shared：6
- generated：3
- forbidden：3
- unknown：1（`docs/reference-workflow-cleanup.md`）

unknown 路径使状态机无法验证。最小修复是在 canonical 规则中增加该精确路径，并在 `scripts/sync-upstream.test.js` 证明该文件可合并、其他未知根路径仍被拒绝。

## Fork 必须保留的边界

- `skills/story-write`、`story-analyze`、`story-scan` 是统一入口；拆分 Skill 仅用于读取上游差异，不进入最终索引。
- `.github/workflows/` 与 OpenCode 资产保持禁用。
- `.trellis/`、`scripts/sync-upstream.js`、`scripts/quality-gate.mjs`、发布清单和候选采用脚本保持 fork 所有权。
- `skills/_shared/` 是共享规则和扫描器的权威来源；部署副本从权威源生成。
- fork 发布身份当前为 `0.8.1`、`setup_skill_version: 1.2.11`、`agents_version: 30`、18 个公开 Skill。上游版本字段不得覆盖 fork 版本字段。

## 验证依据

- 状态机在专用 worktree 固定双方 SHA、保存逐路径决定，并拒绝 origin 漂移或验证后树变化。
- release 配置包含 30 个本地检查；外部 Codex CLI 和 Playwright E2E 在独立 `external` 配置中，不属于本次完成证明。
- 上一轮同类同步在 23 个冲突下完成逐路径迁移并通过 release 全套检查，说明本次应沿用相同流程。
