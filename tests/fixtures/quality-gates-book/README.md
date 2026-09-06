# 质量门禁样本

这不是给读者看的小说，是 `09-01-quality-first-gates` 子任务 1 / 2 的回归 fixture。

## 为什么不能用 demo

`demo/长篇/让你管账号，你高燃混剪炸全网` 的 20 章细纲全部 `outline-contract` blocking，且 `字数目标` 按正文倒填（比值全 1.00）。在全红样本上验收「缺字段能否拦住」是空转。证据见父任务 `design.md`「实测基线」。

demo 继续承担 causal / 字数 / name-drift 的基线，不承担本 fixture 的用途。

## 验什么

| 项 | 设计 |
|---|---|
| 细纲契约 | 第 1–5 章字段齐全，`check-outline-contract.js` 对每章 `ok=true` |
| 缺字段变体 | `variants/细纲_第003章.bad.md` 去掉 `目标情绪` / `结尾拍ID/类型` / `期待ID/类型` / `读者验收预期`（不放进 `大纲/`，避免 `check-outline-contract.js --chapter 3` 误命中） |
| 目标情绪连排 | 第 1 章 `打脸`，第 2–5 章连续 `家国`；第 4 章的 3 连和第 5 章的 4 连均为 advisory，不按标签连排阻断 |
| 新写书 | `imported_through_chapter = 0`（`tracking_commit.py init`，`last_chapter=0`） |

## 字数冲突（已记录，不改 fixture 凑数）

正文刻意写短，不满足 `fanqie_length` 2200–2800。子任务 1 / 2 的验收走 `candidate-commit.py check`，不走 `promote`；不要把正文注水到区间里。

当前完整采用链另由 `scripts/test-candidate-commit.py` 的临时测试书覆盖：四章同为 `紧张`，事件分别为救粮、渡口分批上船、断桨拖船和找回孩子；第 4 章通过只读 `check` 后可 `promote`，追踪正常推进。该用例验证标签不会误拒绝，测试填充正文不作为小说质量或读者满意度证据。输入不可读时仍拒绝，因果、事实和字数门保持原有回归覆盖。

## 目录

```
设定/  大纲/  正文/  追踪/
```

初始化：

```bash
python skills/story-write/scripts/tracking_commit.py init --project tests/fixtures/quality-gates-book --input tests/fixtures/quality-gates-book/tracking-init.json
```
