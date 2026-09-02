# 执行 · 语义扫描触发式接入

## 前置调研

- [ ] 读 `check-ai-patterns.js` 的 JSON 输出结构，确认 advisory finding 可按类别计数（1436 行、约 24 类指纹）
- [ ] 读三个 skill 的 `SKILL.md`，确认各自的输入契约（要传什么给 LLM 扫描）
- [ ] 确认 `check` 子命令的输出结构能承载「建议运行」这类非阻断信息

## 实现步骤

1. **写谓词函数**（Python 侧，`candidate-commit.py` 内或独立模块）：
   - `ai_flavor_density(prose, ai_patterns_report) -> bool`
   - `dialogue_ratio(prose) -> float`：引号内字符占比，注意中文引号 `「」""` 全形态
   - `jargon_root_hit(prose, root_table) -> list[str]`：需要一份闭合词根表文件（**脚本读文件，不硬编码**）
2. **定阈值**：先对 demo 20 章跑一遍统计，看分布再定，不拍脑袋。
3. **接进 `check`**：触发结果作为 advisory 段输出，含触发原因与建议命令。
4. **兜底规则**（可选）：连续 N 章未触发任何扫描时提示一次，挂在 `check` 上。
5. **文档**：`AGENTS.md` / `long-mode.md` 说明触发式语义扫描的位置，明确它是建议不是阻断。

## 验证

```bash
for n in $(seq 1 20); do python skills/story-write/scripts/candidate-commit.py check --project "demo/长篇/让你管账号，你高燃混剪炸全网" --chapter $n --json; done
```

统计触发分布，贴进本文件。要求：非 0/20、非 20/20。

## 触发率记录

> 待填：demo 20 章各谓词命中统计 / 最终阈值

## 回滚

单 commit revert。

## 当前状态

2026-09-02：按父任务已评审的执行顺序延期到下一迭代。原谓词设计需基于恢复 blocking 后的剩余 advisory 分布重新研究；本批没有代码实现。
