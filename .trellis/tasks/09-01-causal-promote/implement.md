# 执行 · causal 接进采用链

## 前置

- [ ] 重跑并记录 demo 基线：`python skills/story-write/scripts/check-outline-causal.py "demo/长篇/让你管账号，你高燃混剪炸全网" --strict`
      期望 11 条 blocking，章 4,5,6,7,8,9,10,13,14,15,20
- [ ] 确认 `--json` 输出结构可用于分级裁决

## 实现步骤

1. 加 `CAUSAL_TOOL` 常量（`Path(__file__).resolve().parent / "check-outline-causal.py"`），与 `SKELETON_TOOL` 并列。注意这是 **Python 脚本**，不能用 `run_node`——查 `candidate-commit.py` 是否已有 `run_python` 等价物；没有则加一个，沿用 `run_node` 的错误处理形状。
2. 写 `causal_gate(project, chapter, state)`：
   - 调 `--json --strict --from {chapter} --to {chapter}`
   - `chapter_is_new(state, chapter)` 为真 → blocking；否则 advisory 打印
3. 接进 `validate_binding`，位置紧跟 `outline_contract_gate`（细纲类检查集中）。
4. 文档：`AGENTS.md` / `long-mode.md` 写明出骨架前跑本章范围 causal，并入现有写前准备，不新开块。
5. `python scripts/sync-shared-assets.py`

## 验证

```bash
# 基线不变
python skills/story-write/scripts/check-outline-causal.py "demo/长篇/让你管账号，你高燃混剪炸全网" --strict | head -3
# demo 历史章不被阻断
python skills/story-write/scripts/candidate-commit.py check --project "demo/长篇/让你管账号，你高燃混剪炸全网" --chapter 20
# 收尾
python scripts/test-candidate-commit.py && bash scripts/check-shared-files.sh
```

## 回滚

单 commit revert。
