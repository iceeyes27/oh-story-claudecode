# 叙事逻辑与读者可读性整改（父任务）

## Goal

针对“逻辑不通、叙事混乱、故弄玄虚”的读者反馈，重排长篇写作与验收规则：正文必须先让读者理解因果，再处理表达风格；候选正文采用前必须提供可复验的读者理解证据；新书默认支持平直叙事。

## Background：源需求

读者对本工具箱产出的长篇给出的原始反馈：

> 题材不错，可惜看了十几章实在看不下去，逻辑不通，叙事混乱。写作水平低就不要故弄玄虚，简单平直地写未尝不好。

三句话对应三处仓库机制，均已在当前代码中核实：

### 1. 逻辑不通 ← 验收预算失衡 + 缺读者视角检查

- [skills/story/references/composite-check-manifest.json](../../../skills/story/references/composite-check-manifest.json) 已是 10 个 stage、108 个 required 检查项；逻辑类为原 8 项加 `rc-01/02/03`、`arc-01/02`，共 13/108 = 12.04%。旧八阶段基线是 103 项，其中 8 项逻辑、95 项非逻辑。
- 确定性脚本层同样失衡：`skills/_shared/scripts/` 共 9 个脚本 3923 行，`check-ai-patterns.js` 一个文件 2080 行；管跨章连贯的 `check-chapter-boundary.js` 只有 159 行且仅输出 advisory，`check-subject-switch.js` 100 行。逻辑相关合计 259 行，占 6.6%。
- **结构性缺口**：现有全部逻辑检查都是"作者视角"——拿正文比对 `设定/`、`追踪/_tracking-state.json`、细纲。没有任何一项检查是"读者视角"——只给正文、不给设定，判断读者是否看得懂。设定文件自洽 ≠ 正文里交代过。

### 2. 叙事混乱 ← 三条规则叠加删除因果连接组织

- `skills/story-deslop/SKILL.md:239`「删除优先判断（**先于各 Gate**）」：能删就删，不进润色。
- Gate G「解释腔与上帝视角」删作者解释；`skills/story-write/references/long-mode.md:348` 给 narrative-writer 的 prompt 明写「检查作者解释总结…**优先删掉**」。
- `skills/story-write/references/dialogue-mastery.md:157`「角色不当科普嘴」：**前因后果不能靠任何角色整段讲解**，要拆成半句话 + 身体反应 + 留白。

旁白不能解释、角色不能解释、能删就删——因果链在文本层没有落点，只活在 `追踪/` 里，读者看不到。

### 3. 故弄玄虚 ← 硬门禁强制，不是模型自由发挥

- 章节标题门禁（`long-mode.md:249-256`）要求 **2～6 字、最长 7 字、只允许硬质物证/数字/实体**，说明性标题判 blocking。
- 用仓库自带 demo 书验证：`node .agents/skills/_shared/scripts/check-chapter-titles.js --dir "demo/长篇/让你管账号，你高燃混剪炸全网/正文"` —— 前 20 章有 13 条 blocking、涉及 11 章（11 条超长、1 条第 10 章普通问句、1 条第 6/7 章“记者”通用角色词重合）。
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

**执行顺序**：事实基线 → 首次交代保护 → 父任务候选采用逻辑门 → QA 预算 → 平直叙事。父任务直接负责候选采用集成，不新增第七个子任务。实现状态与证据以本文件 AC、各子任务 AC 和 `research/demo-evidence.md` 为准。

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

### R6 候选采用 v2 逻辑证据

- 复用既有 `candidate-commit.py promote`，不改 Dashboard 入口或 recover 语义，不接入 `quality_lifecycle.py` 的另一套命名与 HEAD/stage 模型。
- `candidate_binding` 升级为 v2，新增 `logic_checks`，只允许 `rc-01/02/03`、`arc-01/02`。每章采用要求三个 `rc-*`；只有第 15 章要求两个 `arc-*`，范围为已采用 1～14 章加候选第 15 章。
- 语义证据必须含 `run_id`、状态、finding/证据锚点、候选 SHA、每个实际读取正文文件的路径与 SHA，以及有序文件清单总摘要。
- promote 在创建采用日志前构造临时正文视图，复验确定性 `rc-01`；第 15 章还要从 binding 读取 ledger 并复验 `arc-02`。arc 阻断只接受与当前结果摘要精确绑定的作者批准。
- v1 候选明确要求重新生成；`--no-scan` 只影响原 AI 扫描，不得绕过逻辑检查。

### R7 共享实现与细纲严格模式

- `check-first-mention.js`、`arc-ledger.js` 的确定性实现只保存在 `.agents/skills/_shared/scripts/`，业务 skill 与测试直接引用共享路径，禁止业务 skill 之间互相导入或保留同名副本。
- `check-outline-causal.py --strict` 用于新写作路径，缺字段、占位、未来章或悬空具体事件均返回非零；旧项目未启用 strict 时保持既有 advisory 行为。

### R8 适用预算与平直叙事

- AC2 的统计定义固定为：`纯中文正文适用的逻辑 required 数 / 纯中文正文适用的全部 required 数 >= 25%`。不适用的英文、Markdown、非正文项不进入该场景分母，但在其适用场景仍是 required。
- 新建书默认 `叙事复杂度: 平直`；已有书缺字段时保持常规行为。平直档按时序写明主语、前因、动作、结果和过渡，章尾可直接说明下一步。
- 标题提供 `fanqie` 与 `terse` 档；默认 `fanqie` 将单纯超长、普通市场问句、相邻通用角色词重合降为 advisory，真正的 AI 摘要句、口号式设问和近似复读仍 blocking；`terse` 保留旧严格结果。

## 跨子任务验收标准

> 完成核对于 2026-08-31：六个子任务 AC 全部通过；复合检查为 10 阶段、完整目录 108 项，纯中文正文场景适用项 46 项。

- [x] AC1：对 demo 书 `demo/长篇/让你管账号，你高燃混剪炸全网/` 跑读者视角检查，`check-first-mention.js` 产出 7 处候选（4 blocking），每处带章节:行号与首现上下文，可逐条核查，未误报到不可用。首轮发现的两类精度毛刺已修：量词切分残留（"个系统"）由 `MEASURE_PREFIX` 过滤掉（数词不滤，避免误杀 三清殿/九幽阁 这类真专名）；真实歌曲这类现实世界实体改由作者在 `正文/_已知实体.txt` 或 `--known=` 一次性声明，脚本不猜。
- [x] AC2：纯中文正文场景的适用逻辑 required 占比达到 25% 以上；契约测试确认 13/46 = 28.26%，并校验适用 filter ID。
- [x] AC3：demo 前 20 章默认 `fanqie` 从 13 条 blocking 降到 0，`terse` 保持原 13 条；真正的 AI 病态标题跨档仍 blocking。
- [x] AC4：`叙事复杂度=平直` 档位可用，且在该档下"每章必须卡关键信息"不再是硬要求；新书默认平直，旧书缺字段保持常规。
- [x] AC5：候选 v2 覆盖缺 ID、伪造 ID、逐文件摘要过期、确定性复验失败、第 15 章缺 ledger、第 14/16 章不要求 arc、v1 明确报错、`--no-scan` 不绕过逻辑检查，且崩溃恢复语义不变；候选事务测试 30/30。
- [x] AC6：六个子任务各自的 AC 全部关闭，无例外项。
- [x] AC7：`manage-skill-adapters.js check` 达到 103/103；文档预算、共享文件、当前 skill 契约、针对性测试与 release profile 全部通过，发布档为 23/23 PASS，Dashboard E2E 为 17/17。

## Out of Scope

- 不改短篇流程（`short-mode.md`）。
- 不改 Dashboard、封面、发布、扫榜相关 skill。
- 不新建 GitHub Actions。
- 不试图让确定性脚本判断所有上下文相关的逻辑问题；脚本只覆盖可机械判定的子集。
- 不重写 `check-ai-patterns.js` 的现有规则（只在 P2 调整调用它的阶段编排）。
