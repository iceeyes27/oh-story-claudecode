---
name: story-write
version: 2.1.0
description: "网文写作（长篇/短篇统一入口）。mode=long 支持只讨论结构、只写大纲或指定细纲；章节生产默认从设定、大纲和细纲生成可扩写的章节骨架，成稿进入作者审批候选；mode=short 走短篇成稿流程。触发方式：/story-write、/写长篇、/写短篇、「帮我开书」「规划剧情」「写大纲」「补细纲」「写第N章」「日更」「续写」「生成成稿」「帮我写一篇短篇」——按意图自动路由。"
metadata: {"openclaw":{"source":"https://github.com/iceeyes27/oh-story-claudecode"}}
disable: true
---

# story-write：网文写作（长篇 / 短篇统一入口）

长篇默认生成规划和章节骨架，明确成稿写入候选并经作者采用；短篇从构思写到成稿。

## 独立编辑与读者审阅

长篇候选、续写与修订均执行 [文字编辑规范](references/copy-editor-specification.md)：扫描后先独立编辑两遍通读及修后复核，再由另一位无历史的 reader 只读截至当前章正文。编辑与读者不得参与该段创作/规划；通用独立 agent 可承载完整编辑协议；reader 仅接收当前任务段，先派发自然首读，实际返回后再派发七问回查，不把完整诊断协议提前交给首读者。无独立调用时自查仍可进行，但独立项标 NOT_EVALUATED，不签通过。下方一般 solo/direct 兼容规则不豁免这一边界。

新章绑定按 [编辑凭证](references/editor-review-receipt.md) 与 [候选逻辑绑定](references/candidate-logic-binding.md)；已采用章修订按 [workflow-revision.md](references/workflow-revision.md) 分开保存编辑、正文盲读和新旧稿连续性复核。正文修改使旧相关凭证失效，原 reader 修后仅为定向复核；实质理解、信息、动机、场景节奏或兑现修改必须换未接触旧稿与答案的新 reader；纯错字标点且不改意可只做编辑及必要定向复核。趣味不以模型评分阻止采用，研究 P1 不因启用常规审阅而自动开启。

## 审阅效果执行契约

编辑部署预检必须同时匹配 `Review Protocol: independent-editor-v1`、`Review Process: review-quality-v2` 及唯一编辑规范引用；旧同名角色不能算当前过程覆盖。可用无历史通用 agent 完整执行现行规范并如实记录来源，不能以旧角色名冒充新过程；无等价独立执行则标未评估。

行为规范共用项目根 `.agents/skills/story-write/references/reader-first-writing.md` 与 `.agents/skills/story-write/references/copy-editor-specification.md`；过程及机器字段唯一来源为项目根 `.agents/skills/story-write/references/review-process.md`（review-quality-v2），实际字段使用该协议和运行器模板，不自行定义。

读者先自然逐章顺读，固定返回当时理解、投入与困惑、想略读的位置、已得到的收获及后续期待，引用原句；这些反应返回后才进行七问回查。首读不提供问题标签、修改答案、作者预期或其他版本，不把代理反应称为真人指标。编辑独立两遍通读，覆盖准确、清楚、自然、连贯及句段节奏；区分硬伤、待核实、有证据的体验缺陷、个人偏好与建议保留，不能把“能猜懂”当成文字已自然。

统筹按文字表达、信息安排或场景设计根因处理意见。所有重要意见沿用原 ID，记录采纳、部分采纳、拒绝、待核实或延期及理由；保留原首读反应，不能用规划答案抹去困惑，不以投票消除分歧。硬伤全量处理，体验修改每轮优先 1～2 个根因，不限制问题登记数量。涉及理解、信息、动机、场景节奏或兑现的实质修改，必须另派无旧稿及问题答案的新读者只读新版；仅不改意的错字标点可由编辑和必要定向复核处理。任何改动仍使受影响凭证失效，按协议重新合法绑定，不覆写旧首读。

编辑修后读取新全文及受影响前文；盲编辑与 reader 只读截至当前章的正文，跨章疑点从当前章及已读前两章起按证据扩展；只有已采用章修订的独立连续性事实复核可读相邻后章，不把后章或未来答案交给盲编辑与首读者。一次修后问题仍在则重诊，第二次无改善停止自动改写；未解决硬伤仍阻断，趣味分歧交作者决定。分列“审核已执行 / 底线是否通过 / 体验改善证据”，不同版本或不同读者的差异本身不证明质量提升，不增加文学评分采用门。

## 阶段 Reference Gate

先确定 mode：长篇从 `references/long-mode.md` 的场景路由定位当前阶段，只读取该阶段执行段；普通成稿写手只完整读取 `references/reader-first-writing.md` 与 `references/long-format.md`，其余按阶段或具体问题加载。短篇完整读取 `references/short-mode.md` 直到 EOF。只读本文件（SKILL.md）不算完成门禁；对明确要求完整读取的核心文件，`rg` 检索或局部摘读都不算完成门禁，必需路径缺失或不可读即停止。

短篇运行 `node .agents/skills/_shared/scripts/check-phase2-contract.js --json {短篇目录}`；最多做 2 轮定向 repair。交付时用户明确的字数范围优先；运行 `node .agents/skills/_shared/scripts/check-delivery-contract.js --json --min-chars {MIN} --max-chars {MAX} --sections {N} {短篇目录}`。

---

> 运行环境兼容性：Claude Code / Codex / ZCode / OpenClaw 是内置适配目标。检查专业 agent 时按 `.claude/agents/{agent}.md` → `.codex/agents/{agent}.toml` 查找；找不到、Codex 返回 `unknown agent_type`，或检测到 `.zcode/`（ZCode 3.3.4 不执行项目 custom agents）时，直接 solo/direct 执行并报告 fallback。
>
> Spawn 版本提示（不阻断 spawn）：先读取项目根 `.story-deployed` 的 `agents_version`。与本版 `agents_version: 30` 不一致时（标记缺失、字段缺失/非整数、小于或大于 30）**照常按文件存在性检查并 spawn**，同时报告 `Notice: agents bundle 版本不匹配（项目 {N}，本版 30）` 并提示重新运行 `/story-setup` 后新开会话；大于 30 时额外提示先更新 oh-story-claudecode，不要用本地旧版 setup 降级覆盖。只有 agent 文件缺失、或运行时不暴露 custom agent 时才降级 solo/direct，报告 `Fallback: ... -> solo`。
>
> **卷纲取段器**：读取卷纲内容时运行 `{PYTHON} {skill 根}/scripts/outline_view.py`。先用 `--toc` 定位单元，只取卷级契约用 `--contract`，取单元闭包用 `--unit {单元ID}`；写正文加 `--stage write`，排纲保留默认 `--stage outline`。找不到单元或作用域声明无效时按脚本错误修复，不能改为整读卷纲。新建卷纲写入后运行 `outline_view.py --check --strict {卷纲路径}`；存量卷纲未声明作用域时保守纳入并提示补充。

## 模式路由（mode = long / short）

调用本 skill 时先按以下规则确定 `mode`：

| 用户意图关键词 | mode | 说明 |
|---|---|---|
| 开书 / 大纲 / 日更 / 续写 / 继续写 / 写第N章 / 修改第X章 / 回炉 / 重写第X章 | `long` | 长篇网文写作流程 |
| 短篇 / 盐言 / 一篇短篇 / 写个盐言故事 | `short` | 短篇网文写作流程 |

**路由规则**：
- 用户明确说"开书/大纲/日更/续写/写第N章/回炉" → `mode=long`
- 用户明确说"短篇/盐言/一篇短篇" → `mode=short`
- 用户没指定长篇还是短篇 → 先问「长篇还是短篇？」，不要擅自假设
- **裸调用**（`/story-write` 没有明确意图）→ 先做项目状态诊断并列出下一步选项，**不得自动进入正文写作**：
  - 空项目 → 建议说「帮我开书」（长篇）或「帮我写一篇短篇」（短篇）
  - 已有长篇设定/大纲但无正文 → 建议说「写第1章骨架」或「日更2章骨架」
  - 已有长篇正文+追踪 → 展示最后采用章节、下一章细纲、骨架或候选状态，建议说「写下一章骨架」「日更2章骨架」「采用第X章」或「修改第X章」
  - 已有短篇设定/大纲但无正文 → 建议说「开始写正文」
  - 已有短篇正文 → 展示当前进度，建议说「继续写」或「精修」

---

## 长篇设定流程

开书、增补设定、单元建纲、写前与设定复核时，读取 [references/setting-payoff.md](references/setting-payoff.md) 的当前阶段：完善性审查 → 分类登记 → 事件与章节目标 → 写前关卡 → 语义/读者复核 → 作者采用记账。普通写手只接收已审定的章节任务和相关规则；缺口返回对应阶段，不能以直写正文补规划漏洞。

## 长篇持续验收

单元建纲、单元收口、每十五章连读、扩卷或挤占收束空间时，按 `references/workflow-setup.md`、`references/workflow-daily.md` 的对应步骤执行，并读取 [长篇连读协议](references/longform-reading.md)。设计对照用于发现风险，独立正文连读用于核查实际效果；新书默认启用检查点，旧书明确起点后启用。到期漏审或证据失效时不得直接推进下一章正文生成；作者继续或豁免须保留范围与原因。检查完成不等于作者认可，更不等于文学问题已解决。

## 核心方法（长篇 / 短篇共享）

长篇按 `references/reader-first-writing.md` 的三层规则，情绪与模块方法按需使用；短篇按自身协议执行。

1. **先定情绪，再定故事**。选择场景时明确它服务的情绪目标。
2. **参考已有模式**。扫榜找方向，拆文找模块，对标找节奏。
3. **选用模块**。参考反转、爽点、感情的组织方式，用本书人物和素材改造，不套用对标书的事件。
4. **只加载必需信息**。只取本章相关状态、伏笔与设定，其他材料留在文件系统。
5. **阶段披露由状态驱动**。每轮先按 `references/progressive-disclosure.md` 识别 `mode`、`current_phase`、`current_stage`、`missing_inputs`、`artifacts`、`next_action`；只展示和读取当前阶段必需资料。用户说"继续"、"日更"、"精修"、"检查"时，优先回到已识别阶段，不重新展开完整流程。
6. **契约与推进决策走权威参考文件**。涉及读者契约、主角代理权、利益安全、期待债、终局储备（终局底牌/升级台阶）、机构/势力边界和 契约安全 / 需补强 / 契约破坏 风险判定时，先按 `references/reader-contract-and-progression.md` 校准，不在 SKILL.md 内复制长规则。
7. **复用作者习惯**。若作者记忆 state 已存在，正文前用 `.agents/skills/_shared/scripts/author_memory_commit.py query --kind prose_style --kind story_design` 获取本次相关 active 条目（总输出 ≤2KB），原样传给实际正文/改写 agent；设定/大纲按任务查询其他 kind。硬门禁、当前请求、本书设定/文风优先。明确长期声明在收尾用 `record` 写入并回传回执；完整规则见 [.agents/skills/_shared/references/author-memory.md](../_shared/references/author-memory.md)，不混入追踪。

| 题材 | 核心情绪 | 重点参考 |
|------|---------|---------|
| 打脸/逆袭 | 爽感释放 | genre-writing-formulas.md |
| 身份反转 | 震撼+痛快 | reversal-toolkit.md |
| 感情拉扯 | 意难平 | emotional-methods.md |
| 悬疑/惊悚 | 紧张+好奇 | hooks-suspense.md |
| 日常装逼 | 期待感 | hooks-chapter.md |

> 用户只描述情绪时，可从上表反查题材，再用 `genre-catalog.md`（长篇）或 `genre-styles/`（短篇）细分。

---

## 通用执行规则（长篇 / 短篇共享）

长篇允许人物、幽默、生活质感与必要理解；不以以下简写删除好表达或强补悬念。

1. **每句话必须有用**。不推动剧情、不铺垫反转、不推高情绪的句子 → 删。
2. **开头定生死，结尾定传播**。开头必须包含钩子，结尾必须有余韵。
3. **任务卡点必须有功能**：角色办事被卡住，必须卡出信息/关系/代价/选择/伏笔变化；删掉无损就压缩或删除。

> 各模式的具体规则见其流程。

---

# 按模式加载执行流程

模式判定后**只加载对应 mode 参考文件**的适用阶段；不同时加载两种模式：

- `mode = long` → 由 [references/long-mode.md](references/long-mode.md) 定位当前阶段。普通候选写手的固定核心是 [references/reader-first-writing.md](references/reader-first-writing.md) 与 [references/long-format.md](references/long-format.md)，写后再由编排器执行 Phase 5。
- `mode = short` → 读 [references/short-mode.md](references/short-mode.md)。

mode 参考文件内的 `references/...`、`scripts/...` 路径均相对本 skill 根目录。
