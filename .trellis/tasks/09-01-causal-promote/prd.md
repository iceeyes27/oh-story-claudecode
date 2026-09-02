# 4 · causal 接进采用链

父任务：`.trellis/tasks/09-01-quality-first-gates`
依赖：`09-01-outline-contract-promote`（复用 `chapter_is_new` 与 `check` 子命令）

## Goal

把已存在但没接线的 `check-outline-causal.py` 接进采用链，且不让导入书的历史旧账挡住新章。

## 背景

`skills/story-write/scripts/check-outline-causal.py` 已实现，CLI：

```
python check-outline-causal.py <书目录> [--json] [--strict] [--from=N] [--to=N]
```

`--from=N` 与 `--from N` 两种写法均可用（实跑确认）。但它不在 `candidate-commit.py` 的 preflight 里。

demo 全量 `--strict` = **11 条 blocking**，章号 4,5,6,7,8,9,10,13,14,15,20。全是「前因事件在上一章找不到具体锚点」——释义对不上，例如第 4 章写「首批观众完成口碑反转」，而第 3 章正文是「东风齐射 / 这个拍 MV 的人太懂」。

**关键**：这 11 条不是靠回填逐章记录能消掉的。它们是细纲前因释义与上一章正文/细纲的措辞差，而 demo 的细纲根本不是现行契约的产物（20 章全部 outline-contract blocking）。不要指望本任务修好它们。

## Requirements

- R5.1 `check-outline-causal.py --strict` 接进 `candidate-commit.py` 的 `check` 与 `promote` preflight。
- R5.2 **只跑本章范围** `--from N --to N`。全量 20 章会让第 21 章因旧账无法采用。
- R5.3 按父任务 D3 分级：`imported_through_chapter` 及之前 advisory，新写章 strict blocking。
- R5.4 出骨架前也跑一次本章范围（父任务 D4）。写完整章再因细纲前因措辞被拒，成本太高。

## 非目标

- **不修 demo 的 11 条**。它们是基线，不是待办。
- 不改 `event_anchor_exists` 的匹配算法（脆弱的子串/≥4 字 token 匹配，改动会让基线全部失效）。
- 不加「过去时预设」规则（原 P1-4，推迟到下一迭代；且应做成独立 code 默认 advisory，不与前因锚点混在同一函数）。

## Acceptance Criteria

- [x] demo 全量 `--strict` 仍为 11 条，章号为 4,5,6,7,8,9,10,13,14,15,20。
- [x] `imported_through_chapter` 内的历史章走真实 `check` 入口时，causal 降为 advisory。
- [x] 新写章缺因果三字段时被 blocking。
- [x] 采用链只传 `--from=N --to=N`；测试证明未来坏细纲不影响当前章。
- [x] `test-candidate-commit.py` 全部 38 项通过。

## 验证记录（2026-09-02）

- demo 严格基线：11 条，章号与任务记录一致。
- 新章删去 `前因` / `后果指向` / `读者已知` 后，`check` 退出 1，正文与追踪不变。
- 历史章相同缺失仅输出 `细纲因果 advisory`，`check` 返回 `ok=true`。
- 第 2 章故意放入坏因果字段时，第 1 章 `check` 仍通过。
