# 执行 · 读者体验契约接进采用链

## 前置调研（动手前必做，见 design.md「未决」）

- [x] 读 `check-outline-contract.js` 全文：报告没有结构化 `missing` 数组，因此采用 Python 侧独立判定 INTENT_FIELDS。
- [x] 两份 `check-outline-contract.js` 在本任务开始时无与采用链相关的漂移。
- [x] `check` 不进入 `project_lock`，也不调用 `assert_no_unfinished_adoption`。
- [x] `validate_binding` 只做读取、哈希与追踪事务内存预演；写盘、移动和锁均在 `promote_chapter` 外层。

## 实现步骤

1. [x] **抽 `chapter_is_new(state, chapter)` helper**，放 `candidate-commit.py` 顶层。
2. [x] **加 `OUTLINE_CONTRACT_TOOL` 常量**，与 `SKELETON_TOOL` 并列。
3. [x] **写 `outline_contract_gate(project, chapter, state)`**：
   - `run_node([tool, "--json", "--project", str(project), "--chapter", str(chapter)], "细纲契约检查")`
   - `parse_node_json(result, ..., {0, 1})`
   - 按 design.md 的严重度表裁决；advisory 项打印但不 `require`
   - `INTENT_FIELDS` 缺失判定按调研结论走结构化或 Python 侧独立判定
4. [x] **接进 `validate_binding`**：放在 `skeleton_result` 之后、`validate_titles` 之前。
5. [x] **`check` 子命令**：
   - argparse 加 `check`（`--project` `--chapter` `--json`）
   - `check_chapter()` 复用 `validate_binding`；副作用若存在先外提
   - 输出结构化结果，exit 1 表示有 blocking
6. [x] **文档**：
   - `artifact-protocols.md:274` 改写（design.md G 节原文）
   - `AGENTS.md` 加 `check` / `promote` 分工条目
   - `long-mode.md` Phase 4 加「出骨架前跑本章细纲契约检查」，并入现有写前准备，**不新开块**
7. [x] **同步副本**：`candidate-commit.py` 的生成副本随同更新，并由共享资产检查验证。
8. [x] **补测试**：覆盖新写章缺字段被拒、新写章合格通过、历史章缺字段放行。

## 验证

```bash
python scripts/test-candidate-commit.py && python scripts/sync-shared-assets.py && bash scripts/check-shared-files.sh
```

fixture 断言：

```bash
python skills/story-write/scripts/candidate-commit.py check --project tests/fixtures/quality-gates-book --chapter 3
```

demo 不回归（关键）：确认 20 章 outline-contract 全部降为 advisory，`promote` 路径不被新门禁阻断。

## 评审门

**作者评审**：新 blocking 的误伤面。交付时附上「fixture 通过 / demo 不变红」两份实跑输出。

## 回滚

单 commit revert。无 schema 变更。若已合入子任务 2（复用 `chapter_is_new`），按相反顺序回滚。
