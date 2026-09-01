# 执行 · 目标情绪闭合词表与连排门禁

## 前置调研

- [ ] 找齐仓库现有情绪枚举：`long-mode.md:246` 的 `基调：(紧张|轻松|悲伤|热血|爽|甜|温馨|恐怖|压抑|其他)`；`story-analyze` / `story-review` 下的情绪模块文档。**能复用就不新造**。
- [ ] 统计一本真实书的 `目标情绪` 实际分布（若无合格样本，只用 fixture，并在验收里标注样本不足）。

## 实现步骤

1. **定闭合词表**：优先取已有枚举的并集，落到一个单一来源文件（倾向 `skills/_shared/references/` 下，供脚本与模型共用）。**吸取教训**：`banned-words.md` 与 `check-ai-patterns.js` 就是脚本不读文件、手工双源的反例（父任务已登记为债）。本任务的词表**脚本必须真读文件**，不硬编码。
2. **`check-outline-contract.js` 加取值校验**：`目标情绪` 的值必须命中词表，否则 `outline.required-fields`（或新 check id）判失败。
3. **连排判定**：新增跨章检查。输入是 `大纲/细纲_第NNN章.md` 序列，输出连续同值片段。归属选择：
   - 选项 A：`check-outline-contract.js` 加 `--motif-run` 模式（单章入口天然不适合跨章）
   - 选项 B：独立小脚本 `check-emotion-run.js`
   倾向 **B**，理由与父任务 D5 一致——单章契约与跨章节奏是两件事，混在一个函数里会像 `event_anchor_exists` 一样难解释失败。
4. **接进采用链**：复用子任务 1 的 `chapter_is_new` 与 `outline_contract_gate` 同一位置。
5. **更新权威模板**：`workflow-setup.md`「细纲（全书每章）」写明 `目标情绪` 取闭合词表。
6. **fixture 断言 + 阈值决策**：跑 fixture 与真实书，把分布贴进本文件，再定 3/4 阈值。

## 验证

```bash
node skills/_shared/scripts/check-emotion-run.js --project tests/fixtures/quality-gates-book --json
python scripts/test-candidate-commit.py
python scripts/sync-shared-assets.py && bash scripts/check-shared-files.sh
```

## 阈值决策记录

> 待填：fixture 分布 / 真实书分布 / 最终阈值 / 理由

## 评审门

**作者确认阈值**。3 章 blocking 会误伤高潮双章与卷末连击，必须由作者拍板而非我默认。

## 回滚

单 commit revert。词表文件为新增，可一并删除。
