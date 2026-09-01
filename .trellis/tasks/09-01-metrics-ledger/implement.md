# 执行 · 数值台账与写前注入

## 前置调研（动手前必做）

- [ ] 读 `require_known_keys` 实现，确认是否严格白名单 → 敲定 schema 4 保持 or 升 5，结论写回 `design.md`
- [ ] 读 `normalize_delta`（:689-704）与 state root 校验（:841）的关系
- [ ] 确认 `character_snapshots` 的「全量而非 delta」是怎么实现的，metrics 照抄同一模式
- [ ] 从 `金手指.md` 任务史与正文抽出 demo 的真实数值，作为回填素材

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
