# 2 · 目标情绪闭合词表与连排门禁

父任务：`.trellis/tasks/09-01-quality-first-gates`
依赖：`09-01-outline-contract-promote`（字段先得必填）、`09-01-regression-fixture-book`

## Goal

让「连续多章同一情绪母题」这个真实弃书原因可被检出。

## 背景

demo 卷纲第 122 行有一条**事后**批注：「第 16-20 章连 5 章『家国 / 老兵 / 泪目』同母题高位运行……是本卷真正的疲劳源」。这是写完之后才发现的问题——没有任何机制在写之前拦住它。

grok 原方案提议新增「情绪母题 tag」字段。**这是错的**：`check-outline-contract.js:24` 的 `FIELDS` 已含 `目标情绪`，且 `:35` 的 `INTENT_FIELDS` 把它列为必须有实际内容。新增第二个情绪字段会造成一本细纲两个情绪源，重演「金手指 vs 公理点」的双源腐烂。

## Requirements

- R3.1 **复用 `目标情绪`，不新增字段**。
- R3.2 该字段取值必须来自**闭合词表**（家国 / 打脸 / 日常 / 事业 / 感情 / 危机 / 悬疑 / 燃 / 温情 …，最终清单在实现时定）。禁止自由发挥——「家国泪目」「老兵」这类自造值会让扫描失效。
- R3.3 词表写进细纲契约（`check-outline-contract.js` + `workflow-setup.md` 权威模板），否则该字段会像因果三字段一样长期缺失。
- R3.4 跨章连排判定：连续同值达阈值时产出 finding，按父任务 D3 分级（历史章 advisory）。
- R3.5 阈值**先不写死**。fixture 与真实书的分布出来后再定；起步建议 3 章 advisory / 4 章 blocking，理由是高潮双章、卷末连击是合法写法，3 章 blocking 会误伤。

## 非目标

- 不结构化卷纲（原方案已砍：卷纲风险标记会腐烂，demo 第 122 行本身就是事后批注）。
- 不做情绪强度/曲线建模。
- 不改 `目标情绪` 之外的任何细纲字段语义。

## Acceptance Criteria

- [x] fixture 第 2–5 章连续 4 章 `家国`：第 4 章报 advisory，第 5 章报 blocking；第 2 章不读取未来细纲。
- [x] 细纲写入闭合词表外的取值（如 `家国泪目`）时，`check-outline-contract.js` 判 `ok=false`，新章采用预检阻断。
- [x] 历史章复用 `chapter_is_new` 分级，连排与非法词值只作 advisory。
- [x] 阈值决策与 fixture、真实书样本情况已记录在本任务的 `implement.md`。
- [x] `test-emotion-run.js`、`test-outline-contract.js`、`test-candidate-commit.py` 全绿。

## 验证记录（2026-09-02）

- `test-emotion-run.js`：第 2/4/5 章边界全部通过，完整序列 4 连 blocking。
- `test-outline-contract.js`：非法值 `家国泪目` 命中 `outline.emotion-vocab`。
- `test-candidate-commit.py`：37/37 PASS，覆盖非法值与新章第 4 连排阻断。
- demo 20 章没有可统计的 `目标情绪`，因此不会形成连排 finding。

## 未决

- 闭合词表的最终清单与粒度。参考已有素材：`skills/story-write/references/` 下的情绪模块相关文档、`story-analyze` 的基调枚举（`紧张|轻松|悲伤|热血|爽|甜|温馨|恐怖|压抑|其他`，见 `long-mode.md:246` 的 grep 模式）。**优先复用已有枚举**而不是另造一套——这正是本任务反对新增字段的同一条理由。
