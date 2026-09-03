# 3 · 语义扫描触发式接入

原父任务：`.trellis/tasks/09-01-quality-first-gates`；2026-09-02 按父任务评审决定延期，解除本批关联，保留为下一迭代 planning 任务。
依赖：`09-01-outline-contract-promote`（复用 `check` 子命令）

## Goal

让三个只在用户说「检查」时才跑的语义扫描，在日更回路上按**确定性谓词**触发。

## 背景

`ai-flavor-scan`、`dialogue-naturalness-scan`、`jargon-verb-scan` 三个 skill **只有 `SKILL.md`，没有脚本**——纯 LLM 语义扫描，今天只出现在 `/检查` 的十阶段复合流程里，日更回路上完全不接。

原方案 P2-3 把问题描述成「把每 5 章十阶段改成触发式」，**这个描述是错的**：每 5 章 checkpoint 在 `skills/story-review/references/quality-lifecycle.md:157`，明写 `advisory_only`，且属于 gen-eval 质量生命周期，不在日更路径上。改它等于改一条没接到写作回路的规则。

真正的问题是：日更回路上只有 `check-ai-patterns.js` + `check-degeneration.js` 两个确定性扫描器，语义层完全缺席。

## Requirements

- R4.1 触发条件必须是**脚本可判定的确定性谓词**，不得再引入一轮 LLM 分类。
- R4.2 触发点挂在 `candidate-commit.py check`（子任务 1 交付），不挂 hook、不挂 `promote`——语义扫描慢且贵，作者采用时不应被它卡住。
- R4.3 触发子集而非全量：命中什么触发什么。
- R4.4 触发率必须可观测：抽样验证不得出现「每章必触发」（等于没有触发条件）或「从不触发」（等于没接）。

## 候选触发谓词（实现时收敛）

| 扫描 | 谓词 |
|---|---|
| `ai-flavor-scan` 十层 | `check-ai-patterns.js` 的 advisory finding 密度超过阈值 |
| `dialogue-naturalness-scan` | 正文对话占比（引号内字符 / 总字符）超过阈值 |
| `jargon-verb-scan` | 命中黑话词根表（需要一份闭合词根表） |

三条都要求先有确定性前置信号，不做「先 LLM 判断要不要跑 LLM」。

## 非目标

- 不改 `quality-lifecycle.md` 的每 5 章 checkpoint（它 advisory_only，不在日更路径）。
- 不把语义扫描变成 blocking——本批只做触发与呈现，阻断与否留给作者。
- 不给三个 skill 写确定性脚本（那是各自独立的、更大的工作）。

## Acceptance Criteria

- [ ] `candidate-commit.py check` 在满足谓词时输出「建议运行 X 扫描」及触发原因，不满足时静默。
- [ ] 对 demo 20 章逐章跑 `check` 的触发统计：既不是 20/20 也不是 0/20，且触发章与人工直觉大体一致（附抽样说明）。
- [ ] 「从未触发的静默章每 5 章兜底」若实现，必须挂在 `check` 上，不得只写在 skill 散文里。
- [ ] 收尾脚本全绿。

## 备注

本任务可推迟到下一迭代。它省 token、改善语言轴的覆盖，但不引入新的质量保证。若前面几项超期，**优先砍这一项**，不砍子任务 1/2。

## 延期记录（2026-09-02）

恢复 AI pattern blocking 后，原先以 advisory 总密度为核心的触发前提已变化。继续实现需要重新统计剩余 advisory 类别，并重新评审阈值与误报率。本批不实现、不归档为完成。

## 重新研究结果（2026-09-03）

对 demo 20 章逐章运行 `check-ai-patterns.js --json`：共 38 条 advisory，其中 `english-residue` 30 条、`em-dash` 5 条、`period-stutter` 2 条、`metaphor-density-tic` 1 条。`english-residue` 占 78.9%，主要是军宣/短视频题材中的 `MV`、`BGM`、`MCN` 等合法术语。

因此当前三个候选谓词均未达到接入条件：

- advisory 总密度主要测到题材英文术语，不能作为 `ai-flavor-scan` 触发器；
- 对话占比只表示场景形式，不表示台词不自然；
- 黑话词根命中只表示术语出现，不表示“行业名词硬作动词”。

本轮研究结论为 **NO-GO**：在没有更高精度、可解释的确定性前置信号前，不把三项纯 LLM 扫描接入 `candidate-commit.py check`。该结论避免增加稳定误报，不代表三个语义扫描本身无价值；它们继续保留在显式复合检查中。
