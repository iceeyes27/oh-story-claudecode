# 执行 · 目标情绪闭合词表与连排门禁

## 前置调研

- [x] 已合并仓库既有基调枚举与父任务建议值；脚本从单一词表文件读取，不硬编码第二份。
- [x] demo 20 章均缺 `目标情绪`，已记录为无可用真实分布样本。

## 实现步骤

1. [x] **定闭合词表**：词表位于 `skills/_shared/references/target-emotion-vocab.md`，两个检查器都运行时读取。
2. [x] **`check-outline-contract.js` 加取值校验**：非法值命中独立的 `outline.emotion-vocab`。
3. [x] **连排判定**：新增独立 `check-emotion-run.js`；传章节号时只读取当前章及以前的细纲。
   - 选项 A：`check-outline-contract.js` 加 `--motif-run` 模式（单章入口天然不适合跨章）
   - 选项 B：独立小脚本 `check-emotion-run.js`
   倾向 **B**，理由与父任务 D5 一致——单章契约与跨章节奏是两件事，混在一个函数里会像 `event_anchor_exists` 一样难解释失败。
4. [x] **接进采用链**：复用 `chapter_is_new`；非法词值和 4 连对新章 blocking、历史章 advisory。
5. [x] **更新权威模板**：`workflow-setup.md` 已写明闭合词表及可追加说明的格式。
6. [x] **fixture 断言 + 阈值决策**：确定 3 章 advisory / 4 章 blocking。

## 验证

```bash
node skills/_shared/scripts/check-emotion-run.js --project tests/fixtures/quality-gates-book --json
python scripts/test-candidate-commit.py
python scripts/sync-shared-assets.py && bash scripts/check-shared-files.sh
```

## 阈值决策记录

> fixture：第 1 章 `打脸`，第 2–5 章连续 `家国`。
> 真实书：demo 20 章缺 `目标情绪`，无可用分布。
> 最终阈值：**3 章 advisory / 4 章 blocking**（仅新写章 blocking；历史章一律 advisory）。
> 理由：高潮双章与卷末连击是合法写法，3 章 blocking 会误伤；fixture 第 4 章可观察 3 连、第 5 章可观察 4 连。

## 评审门

**作者确认阈值**。3 章 blocking 会误伤高潮双章与卷末连击，必须由作者拍板而非我默认。

## 回滚

单 commit revert。词表文件为新增，可一并删除。
