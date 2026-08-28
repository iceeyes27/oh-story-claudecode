# 叙事逻辑与读者可读性整改（父任务）

## Goal

让本工具箱产出的长篇在**读者视角**下读得懂、跟得上、不弃书。当前流水线在文字层（AI 味、禁用词、黑话、标点）投入了绝大部分验收预算，在逻辑层与读者可理解性上几乎没有阻断能力，且多条硬门禁在主动生产"故弄玄虚"。本任务重排验收预算与写作门禁，把"读者能否看懂"变成一等公民。

## Background：源需求

读者对本工具箱产出的长篇给出的原始反馈：

> 题材不错，可惜看了十几章实在看不下去，逻辑不通，叙事混乱。写作水平低就不要故弄玄虚，简单平直地写未尝不好。

三句话对应三处仓库机制，均已在当前代码中核实：

### 1. 逻辑不通 ← 验收预算失衡 + 缺读者视角检查

- [skills/story/references/composite-check-manifest.json](../../../skills/story/references/composite-check-manifest.json) 的 8 个 stage 共 102 个 required 检查项，只有 8 项属于因果/连续性范畴（`review-structure-logic`、`review-setting-consistency`、`review-timeline-space`、`review-plot-progression`、`review-foreshadow-tracking`、`review-evidence-program-boundary` + `review-subject-switch`、`review-chapter-boundary`），占 7.8%。
- 确定性脚本层同样失衡：`skills/_shared/scripts/` 共 9 个脚本 3923 行，`check-ai-patterns.js` 一个文件 2080 行；管跨章连贯的 `check-chapter-boundary.js` 只有 159 行且仅输出 advisory，`check-subject-switch.js` 100 行。逻辑相关合计 259 行，占 6.6%。
- **结构性缺口**：现有全部逻辑检查都是"作者视角"——拿正文比对 `设定/`、`追踪/_tracking-state.json`、细纲。没有任何一项检查是"读者视角"——只给正文、不给设定，判断读者是否看得懂。设定文件自洽 ≠ 正文里交代过。

### 2. 叙事混乱 ← 三条规则叠加删除因果连接组织

- `skills/story-deslop/SKILL.md:239`「删除优先判断（**先于各 Gate**）」：能删就删，不进润色。
- Gate G「解释腔与上帝视角」删作者解释；`skills/story-write/references/long-mode.md:348` 给 narrative-writer 的 prompt 明写「检查作者解释总结…**优先删掉**」。
- `skills/story-write/references/dialogue-mastery.md:157`「角色不当科普嘴」：**前因后果不能靠任何角色整段讲解**，要拆成半句话 + 身体反应 + 留白。

旁白不能解释、角色不能解释、能删就删——因果链在文本层没有落点，只活在 `追踪/` 里，读者看不到。

### 3. 故弄玄虚 ← 硬门禁强制，不是模型自由发挥

- 章节标题门禁（`long-mode.md:249-256`）要求 **2～6 字、最长 7 字、只允许硬质物证/数字/实体**，说明性标题判 blocking。
- 用仓库自带 demo 书验证：`node .agents/skills/_shared/scripts/check-chapter-titles.js --dir "demo/长篇/让你管账号，你高燃混剪炸全网/正文"` —— 真实番茄书前 20 章有 9 章被判 blocking（《军报记者来采访了！》《专业团队拍得还不如他拍的好？》《"江晨，这次你完了！"》等）。门禁在禁止市场上有效的写法。
- 叠加"每章必须钩子""禁止提前释放""章尾卡关键信息""元信息隔离禁止承接前文"，整套配置在训练故弄玄虚。
- 现有文风配置只有"对标文风 / `设定/文风.md`"两条路，**没有叙事复杂度维度**——"简单平直地写"在当前系统里不是一个可选档位。

## 子任务映射

| 优先级 | 子任务 | 对应反馈 | 交付物 |
|---|---|---|---|
| P0 | [08-26-reader-comprehension-scan](../08-26-reader-comprehension-scan/prd.md) | 逻辑不通 | 新 skill `reader-comprehension-scan` + 专名首现脚本 + 接入复合检查 stage 0 |
| P0 | [08-26-opening-arc-audit](../08-26-opening-arc-audit/prd.md) | 看了十几章看不下去 | 开篇 N 章连读体检：悬念收支表 + 主线推进量，阻断阈值 |
| P1 | [08-26-outline-causal-fields](../08-26-outline-causal-fields/prd.md) | 逻辑不通 | 细纲新增跨章因果必填字段 + 契约与校验脚本 |
| P1 | [08-26-first-mention-protection](../08-26-first-mention-protection/prd.md) | 叙事混乱 | 首次交代保护区；删除优先顺序改为先查信息首现完整性 |
| P2 | [08-26-plain-narrative-mode](../08-26-plain-narrative-mode/prd.md) | 故弄玄虚 | 标题门禁按平台分档 + `叙事复杂度` 三档（平直/常规/复杂） |
| P2 | [08-26-qa-budget-rebalance](../08-26-qa-budget-rebalance/prd.md) | 逻辑不通（预算） | 精简 humanizer/general-deslop 阶段，把预算让给逻辑层 |

**执行顺序**：P0 两项纯新增、不动现有门禁、无回归风险，先做并验证能否捕获"十几章弃书"。P1 两项动细纲契约与 Gate 顺序，需回归测试。P2 两项动既有 blocking 门禁，必须以 demo 书为基线。子任务间的依赖写在各自 `prd.md` / `implement.md`，不由树位置隐含。

## 跨子任务需求

### R1 读者视角是新增维度，不替换作者视角

现有作者视角检查（比对设定/追踪）全部保留。新增检查一律只读 `正文/`，不读 `设定/`、`大纲/`、`追踪/`，否则等于把缺口重新盖住。

### R2 新增门禁必须是确定性脚本 + 语义判读两层

可机械判定的部分（专名首现、悬念开闭环计数、细纲字段完整性）写成脚本并带回归测试；需要语感的部分写进 skill 文档由模型判读。不得只写文档不写脚本——本仓库已有的教训是纯文档规则不会被稳定执行。

### R3 热路径文档预算是硬约束

`scripts/doc-budget.json` 登记的文件当前余量很紧（`long-mode.md` 26223/27500，长篇日更主会话路径 46480/48500）。任何写进热路径的新规则，要么删等量旧文本，要么在 `doc-budget.json` 里显式调高 budget 并写明理由。冷路径（新 skill 自身的 references）不受此限——**优先把新规则放冷路径**。

### R4 不破坏既有验收基线

`scripts/static-check.sh`、`check-current-skill-contracts.py`、`test-scan-contract.js`、`test-chapter-titles.js`、`manage-skill-adapters.js check` 必须全绿。新增 skill 需登记进 `scripts/platform-skill-set.json` 或 `local-only-skill-set.json`。

### R5 检查结论边界

沿用仓库既有约定：扫描通过只能表述为"已知确定性模式未发现阻断项"，不得据此声称"逻辑自洽"或"读者一定看得懂"。

## 跨子任务验收标准

> 状态核对于 2026-08-28，P0 两项已接入复合检查（清单 8→10 阶段、必检项 103→108）。

- [x] AC1：对 demo 书 `demo/长篇/让你管账号，你高燃混剪炸全网/` 跑读者视角检查，`check-first-mention.js` 产出 8 处候选（4 blocking），每处带章节:行号与首现上下文，可逐条核查，未误报到不可用。注意候选提取仍有精度毛刺（"个系统" 这类中文切分残留、歌曲名被当专名），属 advisory 级需人工复核，已写在 skill 能力边界里。
- [ ] AC2：复合检查的逻辑层 required 项占比从 7.8% 提升到 ≥25%，且提升来自新增逻辑项与精简冗余风格项两侧，不是单纯加项。
      **当前 13/108 = 12.0%**（原 8 项 + 新增 rc-01/02/03、arc-01/02 共 5 项）。只加项到不了 25%，**必须等 P2 `qa-budget-rebalance` 精简 humanizer / general-deslop 的冗余风格项**才能关闭——这是 AC2 对 P2 的硬依赖。
- [ ] AC3：真实爆款书的说明性章节标题不再被判 blocking（以 demo 书前 20 章为基线，blocking 数从 9 降到 0）。属 P2 `plain-narrative-mode`，未开工。
- [ ] AC4：`叙事复杂度=平直` 档位可用，且在该档下"每章必须卡关键信息"不再是硬要求。属 P2 `plain-narrative-mode`，未开工。
- [x] AC5：`node scripts/quality-gate.mjs --profile release` 22/23 PASS，唯一非 PASS 是 `dashboard-e2e` BLOCKED（本机未安装 Playwright chromium，属清单声明的 blocked 条件，非失败）。含 `static-check.sh`、`check-current-skill-contracts.py`、`check-doc-budget.sh` 全绿。
- [ ] AC6：六个子任务各自的 AC 全部关闭，或未关闭项在本文件写明例外理由。
      当前：P0 两项（reader-comprehension-scan、opening-arc-audit）已完成并接线；P1 `outline-causal-fields` 只完成脚本+测试，契约/demo 数据/文档三块未做；P1 `first-mention-protection` 未开工；P2 两项仍在 planning。

## Out of Scope

- 不改短篇流程（`short-mode.md`）。
- 不改 Dashboard、封面、发布、扫榜相关 skill。
- 不新建 GitHub Actions。
- 不试图让确定性脚本判断所有上下文相关的逻辑问题；脚本只覆盖可机械判定的子集。
- 不重写 `check-ai-patterns.js` 的现有规则（只在 P2 调整调用它的阶段编排）。
