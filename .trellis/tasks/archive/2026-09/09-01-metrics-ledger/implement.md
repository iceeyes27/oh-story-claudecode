# 执行 · 数值台账与写前注入

## 前置调研（动手前必做）

- [x] 读 `require_known_keys` 实现，确认是否严格白名单 → **保持 schema 4**：state 允许缺 `metrics`（按 `{}`），事务必须显式带 `metrics`（空表也要 `{}`）
- [x] 读 `normalize_delta` 与 state root 校验的关系
- [x] 确认 `character_snapshots` 的「全量而非 delta」是怎么实现的，metrics 照抄同一模式
- [x] 从第 11、20 章正文抽出 demo 的真实数值，使用 `demo-backfill.json` 经 tracking 事务回填；旧 state 兼容由独立回归覆盖

## 实现步骤

1. **state 侧**：`metrics` 加入 root 已知键；读取一律 `root.get("metrics", {})`；`init` 与构造处给缺省 `{}`。
2. **事务侧**：payload 的 `metrics` 必填（空表显式 `{}`）；缺键 `require` 失败，错误文案点名。
3. **渲染**：`render_context()` 加子弹（`design.md` 的格式），空表不输出；实现 `CONTEXT_MAX_BYTES` 截断。
4. **拒绝条件**：结算句式表文件（脚本读文件）+ `candidate-commit.py` 的 `validate_binding` 里挂判定；提供 `metrics_unchanged_reason` 显式豁免。
5. **回填 demo**：走事务工具写入，**不手改 `_tracking-state.json`**。素材来自 `金手指.md` 任务史。注意 demo 的 `state_revision = 0`。
6. **三本账收口**：改 `金手指.md`、`题材定位.md`、`AGENTS.md`（`design.md` R7.6 节）。
7. **写前注入**：`long-mode.md` 状态筛选一步加半句，不新开块。
8. **同步 4 份副本**：`python scripts/sync-shared-assets.py` —— 必须一次性同步，不可分批（`design.md` 已说明原因）。
9. **补测试**：`test-tracking-commit.py` 加——旧 state 无 metrics 可读、事务缺 metrics 被拒、渲染后仍 7 栏、空表不输出子弹。

## 执行记录（2026-09-02）

- [x] schema 保持 4；旧 state 缺 metrics 可读且不改写，新事务 metrics 必填。
- [x] metrics 采用结构化全量记录，保留 value、事实章和正文来源短语。
- [x] 上下文仍为 7 栏，显示最近 12 项并标注隐藏数量。
- [x] 结算句式无数值变化时阻断；显式理由、正文直接值与累计增量均有回归。
- [x] demo 经 tracking 事务回填 4 项当前值，`tracking_commit.py check` 通过。
- [x] tracking 36 项、candidate 45 项全量回归通过；追加累计值修正后 5 项定向回归通过。
- [x] 4 份 tracking 副本、共享文件治理与 Skill adapter 检查通过。

## 端到端验收（本批唯一需要新写一章的）

在 fixture 书上写第 N+1 章，正文含结算情节：

1. metrics 未更新 → `promote` 应拒绝
2. metrics 更新且与正文一致 → `promote` 通过
3. 通过后 `上下文.md` 的 `## 当前位置` 出现正确的「关键数值」子弹
4. `上下文.md` 仍恰好 7 个 `##`

这一项单列预算，不算附带。

## 验证

```bash
python scripts/test-tracking-commit.py && python scripts/test-candidate-commit.py && python scripts/sync-shared-assets.py && bash scripts/check-shared-files.sh && node scripts/check-release-manifest.mjs
```

demo 不回归：`_tracking-state.json` 未被强制迁移时 `check` 仍可运行。

## 评审门

**作者评审**：schema 决策 + 端到端结果。

## 回滚

本任务改动面最大。单 commit，但涉及 4 份副本——回滚后必须重跑 `sync-shared-assets.py` 与 `check-shared-files.sh` 确认一致性。若已回填 demo 的 metrics，回滚需同时还原 `_tracking-state.json`（走事务工具，不手改）。
