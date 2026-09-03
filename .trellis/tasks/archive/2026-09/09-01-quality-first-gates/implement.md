# 执行计划 · 提质优先门禁重排（父任务）

父任务本身不承载实现，只负责顺序、评审门与最终整合。每个子任务在自己的 `implement.md` 里展开。

分支：`feat/quality-first-gates`（已建，基于 `main` @ 62614b9）

## 执行顺序与评审门

| 序 | 子任务 | 工期 | 评审门 |
|---|---|---|---|
| 1 | `09-01-scan-gate-bypass` | 0.5d | 已完成 |
| 1b | `09-01-restore-ai-pattern-blocking` | — | 已完成（插队） |
| 1c | `09-01-quality-gate-coverage-audit` | 0.5d | 已完成 |
| 2 | `09-01-regression-fixture-book` | 0.5d | 已完成 |
| 3 | `09-01-outline-contract-promote` | 1d | 已完成 |
| 4 | `09-01-emotion-motif-gate` | 0.5d | 已完成：3 章 advisory / 4 章 blocking |
| 5 | `09-01-semantic-scan-triggers` | 0.5d | **推迟下一迭代**（触发谓词前提已变） |
| 6 | `09-01-causal-promote` | 0.5d | 已完成：demo 11 条基线不变且不阻断 |
| 7 | `09-01-name-drift-dict` | 1d | 已完成：demo 误杀面为 0 |
| 8 | `09-01-metrics-ledger` | 1.5–2d | 已完成：schema 4 + fixture 端到端 |

合计 5.5–6 天。第 1–4 项（约 2.5 天）交付后即产生读者可感知的改善。

## 回滚点

- 每个子任务一个 commit，可单独 revert。
- 子任务 3 与 8 落地后各打一个 tag 或记录 commit hash，作为回滚锚点。
- 破坏形态预案：若 demo 因新门禁无法 promote，先查 D3 分级判定，不要直接放宽 blocking。

## 全批收尾（父任务负责）

- [x] 跨子任务验收清单（见 `prd.md`）逐条实跑并记录输出
- [x] 重新冻结 demo 基线数字（causal 条数、字数 under/over 名单），写回 `design.md`「实测基线」
- [x] `AGENTS.md` 幽灵脚本引用清理完成（在子任务 1 内顺手做，父任务复核）
- [x] `artifact-protocols.md:274` 与新分级策略不矛盾
- [x] 当前可执行契约登记到 `.trellis/spec/skills/longform-artifacts.md`
- [x] 提交前运行 release profile：29/32 PASS、0 FAIL、3 项环境阻断

## 不做

见 `prd.md` 的 Out of Scope。执行中若发现某项「顺手就能做」，登记为新任务，不并入本批——本批的价值在于顺序，不在于覆盖面。
