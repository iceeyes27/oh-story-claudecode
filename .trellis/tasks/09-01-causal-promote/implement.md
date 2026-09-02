# 执行 · causal 接进采用链

## 前置

- [x] 重跑并记录 demo 基线：`python skills/story-write/scripts/check-outline-causal.py "demo/长篇/让你管账号，你高燃混剪炸全网" --strict`
      期望 11 条 blocking，章 4,5,6,7,8,9,10,13,14,15,20
- [x] `--json` 返回 `outlines`、`blocking` 与结构化 `findings`，可用于分级裁决。

## 实现步骤

1. [x] 加 `CAUSAL_TOOL` 常量与 UTF-8 `run_python` helper。
2. [x] 写 `causal_gate(project, chapter, state)`：
   - 调 `--json --strict --from {chapter} --to {chapter}`
   - `chapter_is_new(state, chapter)` 为真 → blocking；否则 advisory 打印
3. [x] 接进 `validate_binding`，位置紧跟情绪门禁。
4. [x] 文档写明出骨架前只跑本章范围 causal。
5. [x] 生成副本已同步并通过共享资产检查。

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
