# 长篇写作流程（mode = long）

> 本文件是 story-write 的 mode 参考，由 SKILL.md 按模式路由加载；文中 `references/...` 与 `scripts/...` 路径均相对 story-write skill 根目录。

## 长篇 Reference Gate

进入具体阶段前，完整读取该阶段路由的参考文件直到 EOF；`rg` 检索或局部摘读不算完整读取。开书依次路由 `workflow-setup.md`；章节骨架路由 `chapter-skeleton-workflow.md`；明确成稿路由本文件 Phase 4、`candidate-workflow.md`、`writing-craft.md`、`long-format.md`、`long-chapter-quality.md`、`long-chapter-hooks.md`、`long-suspense.md` 与 `long-reversal.md`；修订路由 `workflow-revision.md`；明确批量定稿才路由 `workflow-daily.md`。必需文件缺失或不可读时停止，不得先写正文再补读。

**Constraint Lock**：用户要求、已采用正文、当前设定、细纲、追踪与公理点台账是项目事实权威；references 只提供技法，不得覆盖这些项目事实。

根据用户意图和项目状态选择场景：

| 场景 | 触发条件 | 执行流程 |
|------|----------|----------|
| **开书** | "帮我开书" / 项目目录为空 | Phase 1→2→3：建项目、核心设定、卷纲与首批 10 章细纲；**默认停在细纲交付，不自动写正文** |
| **章节骨架** | "写第 N 章" / "写第1章" / "生成骨架" / "日更" / "续写" / "继续写" | 加载 `references/chapter-skeleton-workflow.md`；默认生成 1 章，日更单轮最多 2 章，不写成品正文、不推进追踪 |
| **成稿候选** | "生成成稿" / "最终正文" / "直接写正文" | Phase 4 成稿分支，只写 1 章到书根 `候选/`；完成 Phase 5 后等待作者采用 |
| **候选审批** | "采用第X章" / "重写第X章" / "弃用第X章" / "有哪些待审" | 加载 `references/candidate-workflow.md`，采用后才并入 `正文/` 并推进追踪 |
| **补纲/扩纲** | "出细纲/补细纲/规划下一段剧情/接下来写XX剧情（先出细纲）" **且**项目已有大纲 | Phase 3「中途补纲/扩纲小流程」：选同类剧情单元→追加剧情单元卡→按剧情批滚动补细纲；**默认停在细纲交付，不自动写正文** |
| **兼容批量定稿** | 明确说"批量成稿并直接定稿" | 加载 `references/workflow-daily.md`；这是旧版兼容行为，普通日更不得进入 |
| **大修** | "修改第X章" / "回炉" / "重写第X章" | 加载 `references/workflow-revision.md` |

> **开新卷**：如果新卷引入新角色/势力/设定，先回 Phase 2 增量补充，再进 Phase 3 补充新卷细纲，最后 Phase 4 写作。如果纯延续，直接回 Phase 3。

### 裸调用与停靠点（防失控）

`/story-write long` 或 `$story-write long` **裸调用**（没有"开书/写第N章/日更/续写/修改"等明确意图）时，先只做项目状态诊断并列出下一步选项，不自动生成骨架或正文：

不得把已有项目默认为日更 3 章。

- 空项目 → 建议说「帮我开书」或先提供 `选题决策.md`；
- 已有设定/大纲但无正文 → 建议说「写第1章骨架」或「日更2章骨架」；
- 已有正文+追踪 → 展示最后采用章节与下一章细纲、骨架、候选状态，建议说「写下一章骨架」「采用第X章」或「修改第X章」。

**开书默认停靠**：用户只说"开书/写大纲/帮我开书"时，完成 Phase 1→3 与首批 10 章细纲后停止；同一句要求"并写第1章/写 N 章"时，后续默认生成章节骨架，不生成成稿。

**产物数量上限**：骨架默认 1 章，日更骨架单轮最多 2 章；成稿候选每轮只生成 1 章，等待采用后才能生成下一章。只有明确的兼容批量定稿指令才沿用 `workflow-daily.md` 的 2～3 章上限。

**匹配优先级**：同时命中多行时，按 大修 → 候选审批 → 兼容批量定稿 → 成稿候选 → 补纲/扩纲 → 章节骨架 → 开书。用户点名要细纲时优先补纲；普通“日更/续写”始终进入章节骨架。

**普通日更保持在骨架流程内**：本次请求进入 `chapter-skeleton-workflow.md` 后，同批“继续/续写/日更”继续生成骨架，不切换成稿。成稿必须重新出现明确成稿意图。

**阶段披露状态**：进入任何长篇场景前先按 `references/progressive-disclosure.md` 做一次轻量识别。`write_chapter_skeleton` 生成骨架，`expand_chapter_skeleton` 等待扩写，`review_candidate` 检查候选。骨架与候选都不推进 `current_chapter`；只有 promote 成功后才推进正式章号。

文件模式可用 `scripts/flow-state.js` 辅助识别和维护状态：`detect --write` 写入 `追踪/写作流程状态.json`，`read` 读取现有状态，`update` 合并当前阶段结果。该工具只处理流程状态，不生成骨架或正文，也不修改追踪事务。

无法判断场景时，列出上述场景表让用户选择，不要开放式提问。

### 成稿候选（作者拍板）

任何长篇成稿默认先写入书根 `候选/`，作者显式采用后才由 `scripts/candidate-commit.py` 并入 `正文/` 并推进追踪。外部扩写正文也走同一流程。完整的检查、事务暂存、采用、重写与弃用规则见 [references/candidate-workflow.md](candidate-workflow.md)。裸调用诊断发现 `候选/` 待审项时，优先展示「候选中：第X章待审」。

### 路径与术语约定

> **拆文库/对标关系**：`拆文库/` = analyze skill 的原始产出，是数据源。`对标/` = 写作项目的引用视图，存放与本项目相关的对标数据子集。首次引用对标书时，从 `拆文库/{书名}/` 复制相关子目录（章节/角色/剧情/设定）、`剧情/节奏.md`、`剧情/情绪模块.md`、`文风.md` 和 `拆文报告.md` 到 `对标/{书名}/`。
>
> **对标书路径查找**：优先 `{项目}/对标/{书名}/`，不存在则回退 `拆文库/{书名}/`。下文所有对标数据加载均使用此规则。

---

### Phase 1：确认选题方向

消费 `选题决策.md`、确认题材方向、做对标发现并登记主/副对标书。

**执行前先读 [references/workflow-setup.md](workflow-setup.md) 的「Phase 1：确认选题方向」节**，按其中步骤执行。

---

### Phase 2：核心设定

产出核心设定表，并创建 `设定/关系.md`、`设定/题材定位.md`、`设定/题材正文提示卡.md`。

**执行前先读 [references/workflow-setup.md](workflow-setup.md) 的「Phase 2：核心设定」节**。

---

### Phase 3：大纲搭建

产出全书体量与阶段总览、卷级大纲、逐章细纲；含大纲安全七检、大纲安全审查、分批建纲与「中途补纲/扩纲小流程」。

**执行前先读 [references/workflow-setup.md](workflow-setup.md) 的「Phase 3：大纲搭建」节**。

每批细纲交付前跑 `python skills/story-write/scripts/check-outline-causal.py <书目录>`；写第 N 章前再跑 `python skills/story-write/scripts/check-outline-causal.py <书目录> --strict --from=N --to=N`，blocking 必须改纲。字段与存量兼容规则见 [artifact-protocols.md](artifact-protocols.md)「因果链三字段」。

---

### Phase 4：章节生产辅助

**默认分支是章节骨架**：未明确要求成稿时，立即加载 [references/chapter-skeleton-workflow.md](chapter-skeleton-workflow.md)，生成 `骨架/第NNN章_章名.md`，运行 `scripts/check-chapter-skeleton.js`，然后停止。不得继续执行下方成稿步骤。

**下方单章写作流程只处理明确成稿意图**：成稿写入书根 `候选/`，不直接写正稿、不立即推进追踪。作者采用流程见 [references/candidate-workflow.md](candidate-workflow.md)。

#### 项目文件结构

长篇写作必须用文件系统管理，不要把内容堆在对话里。在用户指定的工作目录下创建：

```
{书名}/
├── 设定/
│   ├── 世界观/
│   │   ├── 背景设定.md        # 时代背景、地理、历史
│   │   ├── 力量体系.md        # 修炼/能力/等级体系
│   │   └── ...
│   ├── 角色/
│   │   ├── 沈栀.md            # 每个人物一个文件，文件名用角色名
│   │   └── ...
│   ├── 势力/
│   │   ├── 天机阁.md          # 每个势力/组织一个文件
│   │   └── ...
│   ├── 关系.md                # 角色关系映射
│   ├── 题材定位.md            # 题材核心梗+对标分析+终局底牌/升级台阶（防写无可写）
│   └── 题材正文提示卡.md       # 题材正文核心：边界/期待/爽点/节奏/禁漂移
├── 大纲/
│   ├── 大纲.md                # 全书卷级结构
│   ├── 卷纲_第一卷.md         # 每卷一个：对标结构坐标+剧情单元+情绪弧线(含章节定位)+人物弧线+伏笔+反转
│   └── 细纲_第001章.md        # 每章一个：章节定位+事件+钩子(按章节定位,章首/章尾/段落级)+爽点+悬念
├── 骨架/
│   └── 第001章_章名.md         # 可扩写场景执行稿，不是正文事实
├── 候选/
│   ├── 第001章_章名.md         # 待作者采用的成稿
│   └── 第001章_追踪事务.json   # 根据实际成稿构造，采用时回放
├── 正文/
│   ├── 第001章_章名.md
│   └── ...
├── 对标/                          ← 拆文产出的结构化资产
│   └── {对标书名}/
│       ├── 原文/
│       │   ├── 第001章_章名.md
│       │   └── ...
│       ├── 角色/                  ← 从拆文库/结构化输出同步
│       │   └── {角色名}.md
│       ├── 剧情/                  ← 从拆文库/结构化输出同步
│       │   ├── {剧情单元名}.md
│       │   ├── 故事线.md
│       │   ├── 节奏.md             # 关键信息推进 + 情绪触动点 + 爆发节奏（权威节奏索引）
│       │   └── 情绪模块.md         # 读者需求/情绪引擎 + 可复现模块（权威模块索引）
│       ├── 设定/                  ← 从拆文库/结构化输出同步
│       │   ├── 世界观/             ← 按主题拆分到子目录
│       │   │   ├── 背景设定.md
│       │   │   ├── 力量体系.md
│       │   │   ├── 地理.md
│       │   │   └── 金手指.md
│       │   └── 势力/
│       │       └── {势力名}.md
│       └── 拆文报告.md
├── 追踪/
│   ├── _tracking-state.json        ← 唯一结构化权威状态
│   ├── 上下文.md                  ← 派生续写状态卡（固定 7 栏），≤12KB
│   ├── 逐章记录/第NNN章.md          ← 未来相关紧凑记录，≤3072 字节
│   ├── 角色状态/{角色名}.md         ← 派生核心角色当前快照
│   ├── 伏笔.md                    ← 派生伏笔当前视图
│   └── 时间线/{作者真相.md,读者已知.md}
├── 参考资料/
│   └── {topic}.md             # story-researcher 输出的研究资料
```

**产物映射表**（创建模板详见 [references/artifact-protocols.md](artifact-protocols.md)）：

| 文件 | 粒度 | 创建阶段 | 读取时机 |
|------|------|---------|---------|
| 设定/关系.md | 全书 | Phase 2 | 按需：story-explorer relationship 查询、story-review 查设定（不在每章写作回路里逐章读） |
| 设定/题材定位.md（含 `主对标书` 字段，多对标时必填） | 全书 | Phase 2 | Phase 3 大纲、每卷开始前、Phase 4 写前召回 |
| 设定/题材正文提示卡.md | 全书/题材 | Phase 2（缺失则 Phase 4 写前即时生成） | Phase 4 每章写作前：按 `genre-prose-cards.md` 索引匹配后读取 `genre-prose-cards/` 目录对应单题材卡优先、`style-genre-modules.md` 通用模块兜底，与通用正文要求、情绪/节奏召回和文风一起组装 prompt |
| 设定/角色/{角色名}.md、设定/势力/{名}.md | 角色/势力 | Phase 3 细纲后增量补全（首批含主角/主要角色） | Phase 4 状态筛选/写作 |
| 设定/文风.md（自定义文风·优先级最高） | 本书 | 用户自写（Claude Code 可代写）；导入/拆解不覆盖 | Phase 4 每章写作前：含实质内容则取代对标文风作权威风格基 |
| 对标/{书名}/文风.md | 对标书 | analyze Stage 6 输出 → story-import 显式绑定或本 skill 首次引用时同步 | Phase 4 每章写作前（文风召回；有自定义文风时降为参考/句长兜底） |
| 大纲/卷纲_第X卷.md | 卷 | Phase 3 | Phase 4 写卷首章前 |
| 追踪/写作流程状态.json | 书/流程 | Phase 1 推断后创建或更新 | 每轮开始按 `references/progressive-disclosure.md` 读取；只用于判断阶段和资料范围，不进正文 prompt |
| 追踪/_tracking-state.json | 全书 | Phase 3 初始化 | 唯一结构化权威，不进正文 prompt；每章运行 `tracking_commit.py check` 读取章号和修订号 |
| 追踪/伏笔.md | 全书当前视图 | Phase 3 初始化 | 续写状态卡缺项时按 ID 定点查询；每 ID 只一行 |
| 追踪/时间线/{作者真相.md,读者已知.md} | 全书当前事实/认知派生视图 | Phase 3 初始化 | 按作者真相或读者认知的实际问题选择视图 |
| 对标/{书名}/拆文报告.md | 对标书 | 用户手动+analyze | Phase 2 核心设定、Phase 3 大纲、Phase 4 写作 |
| 追踪/逐章记录/第NNN章.md | 章 | Phase 4 每章事务 | 日更不读；目标 ≤1536 字节、硬上限 3072 字节，按需查询历史原因 |
| 追踪/上下文.md（续写状态卡，≤12KB） | 全书当前状态 | Phase 3 初始化 | 日更每章整份读；由事务工具整份重建，固定 7 栏 |
| 参考资料/{topic}.md | 按需 | Phase 4（story-researcher 输出） | Phase 4 后续章节写作时复用 |
| 追踪/角色状态/{角色名}.md | 核心角色 | 首次进入正文或导入初始化 | 久别角色按名读取一个小快照；目标 ≤4096 字节、硬上限 8192 字节；静态人设仍读 `设定/角色/` |
| 对标/{书名}/角色/{角色名}.md | 对标书 | analyze 输出 | Phase 4 模块召回（角色参考） |
| 对标/{书名}/剧情/{剧情单元名}.md | 对标书 | analyze 输出 | Phase 3 卷纲选段与细纲成批（剧情单元卡「对标剧情参照」）、Phase 4 模块召回（剧情模块参考） |
| 对标/{书名}/剧情/情绪模块.md | 对标书 | analyze Stage 3 输出 → story-import 显式绑定或本 skill 首次引用时同步 | Phase 2 核心设定、Phase 3 大纲、Phase 4 每章写作前（读者需求 / 情绪引擎、可复现模块选择） |
| 对标/{书名}/剧情/节奏.md | 对标书 | analyze Stage 3 输出 → story-import 显式绑定或本 skill 首次引用时同步 | Phase 3 大纲、Phase 4 每章写作前（关键信息推进、情绪触动点、爆发节奏参考） |
| 对标/{书名}/设定/*.md | 对标书 | analyze 输出 | Phase 2 设定参考、Phase 4 世界观约束 |
| 骨架/第NNN章_章名.md | 章 | Phase 4 默认分支 | 作者或独立模型扩写；候选检查时核对细纲覆盖，不进入故事事实追踪 |
| 候选/第NNN章_章名.md | 章 | 外部扩写或 Phase 4 明确成稿分支 | Phase 5 检查与作者审批；采用后才移入 `正文/` |

**缺失文件处理**：当前主产物缺失时显式修复，不拼装降级结果：
1. **角色状态文件缺失** → 当前协议项目先运行 `tracking_commit.py check`，再重跑产生该状态的完整事务；已有正文但 `_tracking-state.json` 缺失时重新 `/story-import`。不得从前文临时推断后直接手写快照。
2. **角色、普通剧情单元或设定等非主产物子目录缺失** → 按「对标书路径查找」查找项目视图与根目录数据源，仍缺失则跳过该可选模块。本条不适用于 `剧情/情绪模块.md` 和 `剧情/节奏.md`。
3. **`剧情/情绪模块.md` / `剧情/节奏.md` 缺失** → 写前准备必须停下，设置 `missing_primary_contract: true` 并给出 `repair_action`：重跑 `/story-analyze long` Stage 3+ 或重新 `/story-import`，不得用摘要文件假装已召回权威模块。
4. **有对标书但 `文风.md` 缺失** → 若有 `设定/文风.md`（含实质内容）走自定义文风模式继续；否则日更文风召回 fail-fast，提示先运行 `/story-analyze long` Stage 6 并 `/story-import` 同步。**完全无对标项目**则跳过文风召回、不阻塞（有 `设定/文风.md` 时用它写作）。情绪/节奏轴（`missing_primary_contract`）独立，自定义文风模式不豁免其 fail-fast。
5. **伏笔/时间线文件缺失** → 视为当前语义检查点损坏，停止写正文；先运行 `tracking_commit.py check`，再用事务修复。卷纲/大纲中的计划不能代替已发生事实的当前检查点。
6. **`设定/题材正文提示卡.md` 缺失** → 不阻塞；写前从 `设定/题材定位.md` 精确匹配 `references/genre-prose-cards.md` 索引，并只读取 `references/genre-prose-cards/` 中对应题材单卡（高/中/低置信照原卡标注），无命中再用 `references/style-genre-modules.md` 通用流派模块即时生成短 `genre_prose_card`。只有 `设定/题材定位.md` 也缺失时，退回细纲和目标平台做低置信题材卡，并在意图确认写明。

**对标分析权威优先级（权威读取顺序）**：
1. `剧情/情绪模块.md` 是读者需求 / 情绪引擎、爽文套路框架、可复现模块和重组指南的权威来源。
2. `剧情/节奏.md` 是关键信息推进、章节扩写技法聚合、情绪触动点和爆发节奏的权威来源。
3. `文风.md` 只管句长、标点、对话潜台词、原文锚点等风格；它不能覆盖情绪模块或节奏意图。**自定义文风 `设定/文风.md`（用户自写、不被导入/拆解覆盖）优先级高于对标 `文风.md`**：含实质内容时作权威风格基，对标文风降为参考与句长数值兜底；命中硬安全线的写法（`……` / 破折号 / 段间空行 / 碎句）仍按 narrative-writer 归一，自定义只接管句长 / 软标点 / 潜台词 / 情绪交替。
4. `章节/第K章_摘要.md` 是具体章节证据，用来校验和补足权威索引，不反向覆盖 `情绪模块.md` / `节奏.md`。
5. `拆文报告.md`、`剧情/故事线.md` 是投影/摘要；若与 `剧情/情绪模块.md` 或 `剧情/节奏.md` 冲突，写作以两个权威文件为准，并在写前准备 `gaps.conflict` 记录冲突来源。

**文件组织原则：**
- **人物一个一个文件**：`角色/角色名.md`，方便按需读取
- **势力一个一个文件**：`势力/势力名.md`，组织/门派/家族/国家等
- **世界观按主题拆分**：背景、力量体系、社会结构等各自独立
- **细纲一章一个文件**：`细纲_第XXX章.md`，含钩子设计，与正文一一对应
- **骨架一章一个文件**：`骨架/第XXX章_章名.md`，只保存场景执行设计
- **候选与正稿物理分离**：成稿先写 `候选/第XXX章_章名.md`，采用后才进入 `正文/`
- 不把骨架或候选内容堆在对话里，也不把它们当作已经发生的正文事实

#### 明确成稿的单章流程

只有用户明确要求“成稿 / 最终正文 / 直接写正文”时执行：

1. **检查细纲**：读取 `大纲/细纲_第{N}章.md`，并从对应 `大纲/卷纲_第X卷.md` 读取当前剧情单元（单元ID/位置、卷契约、本卷主推线/战果、终局底牌边界、风险等级）。如果不存在或缺少当前章节蓝图的必需字段，**必须先补建细纲再写正文**，不允许跳过细纲直接写作。补建时参考卷纲中本章对应的事件规划和上下文，补齐阶段位置、结构公式、禁止提前释放、内容概括、情节安排、人物关系/出场顺序、情节细化、结尾设定；无法从已有证据判断的字段写 `[待补充]`，不杜撰副线或关系。
2. **读取上下文**（按需选择；缺失时遵循各项及上方「缺失文件处理」，仅明确标为可选的非主产物跳过。可选快捷路径：如果项目已部署 story-explorer agent（优先检查 `.claude/agents/story-explorer.md` 是否存在；不存在时再检查 `.opencode/agents/`，再不存在时检查 `.codex/agents/`），可 spawn `Agent(subagent_type: "story-explorer", prompt: "项目目录：{dir}\n查询类型：context_load\n查询参数：准备写第 {N} 章\n追踪状态：last_committed_chapter={check 的值}，state_revision={check 的值}")` 一次获取上下文）：
   - (1) `正文/第{N-1}章_*.md` — 上一章正文
   - (2) `大纲/细纲_第{N}章.md` — 本章细纲（含钩子设计）
   - (2a) `大纲/卷纲_第X卷.md` — 当前剧情单元、卷契约与终局储备（主推线/战果、终局底牌边界）
   - (2b) `设定/题材定位.md` — 读取叙事复杂度与标题档位；缺叙事复杂度的旧书按常规，规则见 `narrative-complexity.md`
   - (3) `tracking_commit.py check` + `追踪/上下文.md` — `check` 无 ERROR 输出即通过，从它的紧凑 JSON 取 `last_committed_chapter` / `state_revision`，不把完整 state 加入 prompt；待回收伏笔取 `## 活跃伏笔`，角色当前状态取 `## 核心角色状态`，下一章硬承诺取 `## 下一章承诺`
   - (4) `设定/角色/{相关角色}.md`、`设定/势力/{相关势力}.md`（如存在）— 本章涉及的角色与势力（按细纲出场筛选）
   - (5) 对标书路径下 `拆文报告.md`（按对标书路径查找）— 对标参考
   - (6) `对标/{对标书名}/原文/第{N}章_*.md`（如存在）— 同位置章节参考
   - (7) `参考资料/{topic}.md`（如存在）— 历史研究资料（由 story-researcher 产出）
   - (8) 对标书路径下 `剧情/故事线.md`（按对标书路径查找）— 剧情单元索引，用于确定本章涉及哪些剧情单元
   - (9) 对标书路径下 `剧情/{相关剧情单元}.md`（按对标书路径查找）— 从索引中选择与本章相关的剧情单元文件
   - (10) 对标书路径下 `设定/世界观/*.md`（glob，按对标书路径查找）— 从当前拆文产出的主题化设定中获取参考；目录缺失则记录缺口并跳过本项，不读取扁平历史路径
   - (11) 对标书路径下 `剧情/情绪模块.md`（按对标书路径查找）— 读者需求 / 情绪引擎、爽文套路框架、可复现模块；缺失按上方「缺失文件处理」设置 `missing_primary_contract` 并停止准备
   - (12) 对标书路径下 `剧情/节奏.md`（按对标书路径查找）— 关键信息推进、情绪触动点、爆发节奏；缺失按上方「缺失文件处理」设置 `missing_primary_contract` 并停止准备
   - (13) `设定/题材正文提示卡.md`（如存在）— 本书正文层题材卡；缺失时从 `设定/题材定位.md` + `references/genre-prose-cards.md` 索引 + `references/genre-prose-cards/` 单题材卡目录（按题材分类优先）+ `references/style-genre-modules.md`（兜底）即时生成 `genre_prose_card`，不阻塞写作
3. **写前准备**（下面的 3 步是核心方法在单章写作中的落地：筛选状态 → 召回模块 → 确认意图）：
   - **状态筛选**：从 `追踪/上下文.md` 的 `## 核心角色状态` 取当前角色，从 `## 活跃伏笔` 取需回收/推进项，从 `## 下一章承诺` 取本章必须履行项，输出本节速记（参考 state-tracking.md）。久别角色按名读取 `追踪/角色状态/{名}.md`；只有追查变化原因时才定点查逐章增量。续写状态卡或 meta 不存在时按 workflow-daily 的当前协议处理，不手写替代文件
   - **模块召回、题材卡与文风召回**：
     - ① 本章目标情绪词？② 借鉴哪个参考文件的哪个技法？③ 用在哪些段落？答不出 → 先回读参考再动笔
     - (a) **情绪模块召回**：按「对标书路径查找」规则读 `{对标书路径}/剧情/情绪模块.md`，选出 1 个与本章目标情绪最贴近的 `selected_emotion_module`（读者需求、触发器、戏剧单元、可替换要素、反抄袭提醒）。缺失时设置 `missing_primary_contract: true`，返回明确 `repair_action` 后停止准备
     - (b) **节奏召回**：读 `{对标书路径}/剧情/节奏.md`，选出 1 条 `rhythm_reference`（关键信息 → 扩写技法 → 情绪触动点 → 爆发/冷却）。缺失时设置 `missing_primary_contract: true`，返回明确 `repair_action` 后停止准备
     - (c) **题材正文提示卡召回**：优先读 `设定/题材正文提示卡.md`；缺失则先读 `设定/题材定位.md` + `references/genre-prose-cards.md` 索引，按主题材精确匹配后只读取 `references/genre-prose-cards/` 中对应单题材卡（如 都市脑洞 / 豪门总裁 / 年代 / 双男主；低置信卡必须在意图确认标注低置信，并要求同题材对标校准），无命中再读 `references/style-genre-modules.md` 通用流派模块。跨题材时主题材抽 3-5 条、辅题材抽 1-2 条，生成短 `genre_prose_card`（题材边界、核心逻辑、读者期待、核心爽点/情绪、正文落点、前中后期打法、节奏密度、场景颗粒、禁止漂移、本章取舍、卡片置信度）。题材卡只约束正文层题材味，不改细纲剧情、不覆盖 `selected_emotion_module` / `rhythm_reference` / `设定/文风.md`；只在内部校准取舍，正文里不得出现卡名/标签/置信度/条目/合规自评
     - (d) **文风召回**：先直接读 `设定/文风.md`（不经 explorer）：含实质内容（去空白 ≥200 字，或含 句长 / 标点 / 对话 / 锚点 / 笔调 小节且小节内有可执行约束：比例 / 例句 / 禁止或偏好描述）则置 `custom_style=true`、进入「自定义文风模式」，它作权威风格基（句长 / 软标点 / 潜台词 / 情绪交替），对标 / 拆文 `文风.md` 降为参考（锚点 + 句长兜底）；空 / 仅空白 / 仅标题 / 占位 stub（待办 / 待补充 / ___）视为不存在。否则按「对标书路径查找」规则读 `{对标书路径}/文风.md`（路径优先 `{项目}/对标/{书名}/`，回退 `拆文库/{书名}/`）；多本对标书时从 `设定/题材定位.md` 读 `主对标书` 字段。**未进入自定义文风模式且**文风文件不存在 → **fail-fast 报错**：「对标书 X 缺少 文风.md。请用 `/story-analyze long` 跑 Stage 6 生成文风，再 `/story-import` 同步。」不 inline 生成（自定义文风模式则不 fail-fast；情绪 / 节奏轴 `missing_primary_contract` 仍独立阻塞）
     - (e) **匹配章节挑选**：从 `{对标书路径}/章节/*_摘要.md` grep `基调：(紧张|轻松|悲伤|热血|爽|甜|温馨|恐怖|压抑|其他)`（全角冒号），按本章目标情绪挑章 K——多章同基调时选择规则：先看爽点类型是否接近，再看情节点数量/原文章节估算字数是否接近本章目标字数，最后取章节号最小者；必读 `{对标书路径}/章节/第K章_摘要.md`，若同章存在 `第K章_深度拆解.md` 则加读，否则回退黄金三章深度拆解/文风文件里的可借鉴技巧，不因非黄金三章缺少深度拆解而失败
     - (f) **结构化模块召回**：从对标的结构化子目录（角色/剧情/设定）中按本章情节检索相关模块；若与 `剧情/情绪模块.md` / `剧情/节奏.md` 冲突，权威文件优先，记录 `conflict`
     - (g) 输出"主对标召回摘要 + 副对标召回摘要 + selected_emotion_module + rhythm_reference + genre_prose_card + 文风召回指令 + 原文锚点片段引用"，作为 narrative-writer 的输入。**多对标书时**参 `references/cross-book-recall.md`：主对标提供文风、原文锚点与 selected_emotion_module / rhythm_reference；副对标/参考对标按阶段预算提供结构化摘要，不限制登记书目，不读取副书 `文风.md` / 原文，超过预算时裁条目不裁书目记录。
     - (h) 从题材定位解析 `narrative_complexity`；新书默认平直，旧书缺字段取常规。平直档按 `narrative-complexity.md` 组织因果与章尾。
     - **快捷路径**：项目已部署 story-explorer agent 时，可一次性召回文风/模块材料。
       - 检查顺序：`.claude/agents/story-explorer.md` → `.opencode/agents/` → `.codex/agents/`。
       - 查询类型：`benchmark_style_load`；传入项目目录、章节号、目标基调/字数和爽点类型。
       - 需要返回：`style_profile_path`、`style_profile_summary`、`selected_emotion_module`、`rhythm_reference`、来源路径、匹配章节、锚点片段、`gaps`。
       - `gaps.missing_primary_contract` 为 true 时先按 `repair_action` 修复，不进入正文生成。
       - 主会话另行直接读 `设定/文风.md`：含实质内容时作为本书风格基准；但不豁免情绪/节奏缺失。
   - **指令确认**：综合细纲、本节速记和模块召回结果，用一句话写清本章意图。
	     - 新版细纲必须消费：阶段位置、单元ID/位置、主角目标/关键选择、结构公式、禁止提前释放、内容概括、情节安排、人物关系/出场顺序、情节细化、结尾钩子，并对照当前剧情单元的卷契约、本卷主推线/战果、终局底牌边界。
	     - **细纲优先边界**：正文只能展开本章细纲已有事件、人物、冲突、伏笔和结尾钩子；每个语义点都要独立落地，不许遗漏或把两项压进一句。不得为了凑字或"更精彩"自造新主线、新角色、新反转、提前写后续章剧情，必要的过渡动作只能服务于细纲已列情节点。后续阶段真相、底牌、关系结论和终局矛盾不得因为章尾钩子提前泄露。反过来，细纲是"要发生什么"的契约、不是正文的形状：正文可自由编排叙述顺序、合并/穿插情节点，不必一个情节点一段、也不必按五段式顺写，把每个点演成场景而不是照抄概括语。细纲「复沓锚句」中的原话必须逐字写入标注的情节点，不得改写或挪位（见 writing-craft.md「从细纲到正文」）。
	     - **细纲语义去重**：同一要求在核心事件、五段式、情节安排和情节点中重复，只算一个语义点；生成前合并，不把重复次数当强调，不沿用提纲原句逐项复述。比如多处都写“不带摄像机、先听完再决定拍不拍”，正文只通过一个自然动作或一句人物判断兑现，不能拆成「至于拍不拍，怎么拍…」「不带摄像机，不带采访灯」两轮说明。
	     - 爽点出手前要有可指认的危机/期待铺垫；装逼/打脸/揭露章要写在场配角的差异反应。
	     - 高压/生死/悲痛节拍 要收紧对话声线：搞笑担当让位，信息型角色不当科普嘴，对话逐句承接对方情绪。
	     - 检查任务卡点：本章如果有“办事被卡住”，它必须卡出信息、关系、代价、选择或伏笔变化；没有就不强补。
	     - 契约风险检查：按 `references/reader-contract-and-progression.md` 判定 契约安全 / 需补强 / 契约破坏；若高光/收益被配角、机构或偶然性拿走且没有可见交换，先修纲再写。
     - 例：「快节奏打脸——账单暴露→逼问→反证→公开代价；读者等了三章，这章必须一拳到位。」
4. **资料研究**（按需）：如果写作中遇到需要查证的外部事实（历史年代、地理方位、职业细节等），如果项目已部署 story-researcher agent（优先检查 `.claude/agents/` 下的 `story-researcher.md` 是否存在；不存在时再检查 `.opencode/agents/`，再不存在时检查 `.codex/agents/`），spawn `story-researcher` agent 搜索并输出到 `参考资料/` 目录。如 agent 不可用，由主线程直接执行。研究完成后再继续写作。
5. **标题分档门禁**：从 `设定/题材定位.md` 读取 `标题档位`，缺失取 `fanqie`。写前定名与写后交付都运行 `node .agents/skills/_shared/scripts/check-chapter-titles.js --dir "{正文目录}" --profile {fanqie|terse}`。两档都阻断 AI 偏正摘要句、口号式设问、精确/近似复读；`fanqie` 对单纯超长、普通问句、通用角色词重合只提示，`terse` 保留 2～6 字、最长 7 字的旧严格门禁。详见 `narrative-complexity.md`。
	6. **写作**：第 1 章如果以内心戏、设定认知或独处开场，必须先把内心变化外化为可见事件（决定、误判、对话、物件变化、外部压力），再按字数目标展开；不得用大段心理独白凑字。若第 1 章低于目标，或正文代入感/推进感偏薄，优先回到细纲补有用子事件、对话交锋或选择代价，不要补解释性内心戏；任务卡点只在角色本来有要办的事、且能卡出信息/关系/代价/选择/伏笔变化时使用，没有就不强补。
   - **正文元信息隔离**：`章节：第{N}章`、`上一章：正文/第{N-1}章_*.md`、`匹配第K章`、`细纲文件` 等只用于定位材料。标题行以外的正文不得出现 `第[一二三四五六七八九十百千万两0-9]+章|上一章|上章|前一章|本章|这一章|前文|后文|伏笔|细纲|读者` 这类写作工程词。需要承接前文时，改成角色能感知的事件锚点或相对时间，例如“比第一章那三秒开火更疼”必须写成“比那三秒开火更疼”。例外：角色在故事世界内真实阅读/讨论“第X章”文本，或真实身为作者/读者并谈论读者身份时，可保留相应词。
   - **具体字数表达校验**：正文评价台词、题字、信件、诏令、念头或弹幕时，只有在统计口径明确、已用脚本逐字核对、且故事确有必要时，才使用“这五个字 / 短短四字 / 三个字一落 / 八个字砸下去”这类具体字数表达。不能确保字数计算正确时，一律改成非具体数字表达，如“这句话一落”“这一句落下”“那几个字”“这行字”“话音落下”。例如 `荀攸只说：“他会疑，不会快。”这五个字一落` 应改为 `荀攸只说：“他会疑，不会快。”这句话一落`。
7. **正文执行**：
   - 先检查 narrative-writer agent：`.claude/agents/narrative-writer.md` → `.opencode/agents/` → `.codex/agents/`。
   - 如可用，spawn `Agent(subagent_type: "narrative-writer", prompt: ...)`，prompt 只传本章必需材料：
     - 项目目录、章节、细纲文件、上一章、输出路径。
     - 写前准备输出：本节速记、情绪目标、涉及角色、参考技法。
     - 主对标/拆文路径、主/副对标召回摘要。
     - `selected_emotion_module`、`rhythm_reference` 及来源路径。
     - `genre_prose_card`（题材正文提示卡摘要，只含本章相关条目）。
     - `narrative_complexity`（平直/常规/复杂；旧书缺字段传常规）。
     - 文风路径、文风召回指令、原文锚点片段。
     - `author_preferences`：作者记忆 `query` 结果中匹配本章的 `prose_style` / `story_design` 项；无则不传，禁止把完整画像或待确认项塞进 prompt；作为低优先级倾向自然吸收，不逐条展示或最大化命中，不牺牲连贯、节奏和字数。
     - 阶段位置、本章结构公式、本章可释放信息、本章禁止提前释放信息。
     - 字数目标、情节点预算、格式硬约束。
     - 细纲优先边界：只展开本章细纲，不自造新剧情；若字数目标靠现有情节点无法达标，返回 `outline_underfilled` 欠账点，由主会话补纲/确认后再写。
   - 不把本文件整套规则复制进 prompt；细节以已加载 references 和 narrative-writer 模板为准。
   - agent 输出写入书根 `候选/第XXX章_章名.md`。如 agent 未部署，由主线程直接写作；不得写入 `正文/`。
   - 存在同章 `骨架/` 时，把骨架的场景顺序、细纲覆盖和事实红线加入 prompt；骨架不提供可照抄句子。
8. **字数验证**（写作完成后的第一件事）：用跨平台 Python 字符统计本章实际字数，探测顺序 `python3/python/py`；不要用 `wc -c` 或模型估算，Windows 不直接假定 `python3` 命令可用。macOS/Linux 可用 `wc -m` 备选。
   - 字数 < 细纲目标 90%：对照情节点预算找欠账点。密点（爽点/打脸/反转）被写薄时，重写到对应预算；低压/关系/信息整理章则补细纲内已有铺垫、互动或表演节拍，不硬塞爽点。若现有细纲没有足够可展开内容，停止并输出 `outline_underfilled` 欠账点，先补纲/确认，不能让正文自造新剧情。
   - 字数 > 章目标×1.1：压过场、合并疏点、删多余过渡，不删主线爽点凑数。
   - 90% 只是放行下限，目标仍是 `[章目标, 章目标×1.1]`；重写后重新统计，落进区间再进入步骤 9。
9. **检查**：章尾是否有往下看的理由（低压/过场章弱钩子或留阶段目标即可，不强求爽点）、爽点是否到位（按章节定位，高压/推进章必查）。两条可证伪核对（不达标→修复）：① 爽点出手前是否有可指认的危机/期待段落（指到具体情节点）？指不出=空洞 → 回步骤 8 补铺垫情节点（plot-emotion-system 倒推法）；② 装逼/打脸/揭露章，在场配角是否写出差异化反应（集体震惊/各异），还是只写主角动作？没有 → 补在场配角反应（plot-core-methods）
10. **元信息扫描**：检查标题行以外的正文，命中 `第[一二三四五六七八九十百千万两0-9]+章|上一章|上章|前一章|本章|这一章|前文|后文|伏笔|细纲|读者` 时必须改写为场景内表达；只有角色在故事世界内真实阅读/讨论“第X章”文本，或真实身为作者/读者并谈论读者身份时例外。
	11. **禁用词扫描**：先过**最毒句式速查**（实测最易漏，命中即改）：①「不是A，(而)是B」全家族——含「没有X，没有Y(，只是Z)」排比否定、「是B，不是A」反序、「他没X，也没有Y。他只是Z」先抑后扬，；②声线反差「声音不大/不高…却…」；③「，带着……」万能状语；④预告/总结收尾「没人知道…」「(这)才刚刚开始/开头」「正朝着…压过去」「即将拉开序幕」「这一刻…」；⑤叙述里短词加引号强调（他是被请来"把关"的）。再复核 detector 的 `formulaic-parallelism` advisory：跨段「不是A。/也不是B。/只是C。」、`至于X不X，怎么X`、同动词 `不V A，不V B` 即使写在台词里也不能跳过，确属人物当场的功能性表达才保留。然后对照 `../_shared/references/banned-words.md` 全表：一级词（高频AI腔）命中即替换；二级词（低频/语境相关）高频出现时替换，偶发可参考 `../_shared/references/anti-ai-writing.md` 定性裁定
12. **暂存追踪事务**：主会话根据实际候选正文构造事务 JSON，写到书根 `候选/第XXX章_追踪事务.json`，但不执行 `tracking_commit.py commit`。不得从骨架直接推算最终变化。作者采用时由 `candidate-commit.py promote` 回放；失败语义、修复方式与派生视图规则见 [references/candidate-workflow.md](candidate-workflow.md)。本章首次引入会复用的具名角色或势力时，仍补建静态 `设定/` 档案。
13. **中途快照**（长篇写作安全网）：每连续写完 3 章，在继续前执行以下快照操作：
   - 执行 `scripts/tracking_commit.py check`，确认 `_tracking-state.json` 有效、所有非导入且非显式缺口章节都有规范逐章记录且未超限、所有派生视图一致、续写状态卡恰好 7 栏且 ≤12288 字节
   - 用 `ls -la 正文/` 确认最近 3 个章节文件已成功写入磁盘且大小正常（>100 bytes）
   - 如果发现文件缺失或大小异常，立即重新写入
   - 快照完成后可继续写作

> **候选成稿**：写完一章后停止在作者审批，不进入下一章。兼容批量定稿才使用 `workflow-daily.md`。

#### 写作技巧提醒

| 场景 | 技巧 |
|------|------|
| 开篇 500 字 | 必须有钩子，不能从天气/风景开始（除非反差极大） |
| 对话 | 推进剧情或揭示性格，不能只为了凑字数 |
| 打斗 | 不要流水账，写策略和反转，不写「你一拳我一脚」 |
| 日常 | 日常要有人物互动和伏笔，不能只是「吃饭睡觉」 |
| 任务卡点 | 角色办事被卡住，必须卡出信息/关系/代价/选择/伏笔变化；删掉无损就压缩或删除 |
| 爽点释放 | 铺垫要充分、释放要干脆，读者等得越久释放越要爽 |
| 爽点密度 | 高压/推进章每 3000-5000 字一个「爽」的情绪节点；低压/关系/修炼/信息整理章不强求，但每章仍要有往下看的理由（见 references/outline-structure-theory.md「章节定位与张弛」） |
| 公式约束 | 参考 genre-writing-formulas.md 中的创作公式 |
| 章尾 | 每章结尾都要有让读者想翻下一页的东西 |
| 情绪验证 | 写完每章回头检查：读者到这里应该感受到什么？感受到了吗？没感受到 → 按章节定位补：高压/推进章补冲突或钩子，低压/关系章补关系或情绪质感，别一律加爽点 |

#### 字数验收权威

长篇每章只按本章细纲的 `字数目标` 与步骤 8 的统一 90% 放行下限验收。节奏类型只决定情节点疏密和展开方式，不再叠加另一套静态最低字数。

**细纲缺 `字数目标` 时**：按 3000 字/章代入，走同一条 90% 放行下限，并提示补纲。这是唯一兜底值，不按节奏类型分档——分档正是本次要消除的第二套标准。


#### 追踪文件体积

`追踪/_tracking-state.json` 是唯一结构化权威；`上下文.md`、核心角色快照、`伏笔.md`、作者真相与读者已知时间线都由它确定性派生，程序不反向解析 Markdown。`上下文.md` 固定 7 栏且 ≤12KB。`逐章记录/第NNN章.md` 每章只记录会影响后续连续性的紧凑变化，目标 ≤1536 字节、硬上限 3072 字节，不承诺单独重放出全部当前状态。阶段/卷级回看按需查询逐章记录或正文，不维护另一套长期摘要。所有追踪写入都通过 `scripts/tracking_commit.py`，禁止手改派生文件。

---

### Phase 5：质量检查

检查三个维度：(1) **情绪交付**——每章是否交付了细纲中规划的目标情绪？(2) **契约风险**——按 `references/reader-contract-and-progression.md` 检查因果权 + 结算权、关键节点四问、期待所有权、期待债、终局储备（透支两问）与换书债；章级推进按权威文件的七类状态分档（快节奏保留可见事件/爽点下限），强弱相对本书题材与对标判断，标记 契约安全 / 需补强 / 契约破坏；契约破坏 先修正文或修后续纲。(3) **技术质量**——一致性、格式、禁用词。参考 [references/long-chapter-quality.md](long-chapter-quality.md) 中的通用检查和长篇专项清单。

**能力边界**：确定性扫描器只能识别已注册的词句、结构和退化模式。全部通过只表示“未发现已知 blocking 模式”，不能据此断言成稿自然、没有 AI 味或已经达到出版质量；候选仍须由作者审读后采用。

**正文元信息扫描**：质量检查必须覆盖标题行以外的正文，发现 `第[一二三四五六七八九十百千万两0-9]+章|上一章|上章|前一章|本章|这一章|前文|后文|伏笔|细纲|读者` 这类写作工程词时，先改成角色当下可感知的事件、物件、动作或相对时间，再进入其他检查；故事内真实阅读/讨论“第X章”或真实读者身份语境除外。

**语义错配自检（物理自洽五类）**：写完每章后通读一遍，遇物体接触、痛感、身体反应、抽象对象描写时逐句核五项：① 该物体是否真有所写属性（纸无"棱角"只有"边"、布无"刃口"、水无"硬度"）；② 动作力度与结果是否匹配（擦≠刮≠割≠划，轻触不出持续灼痛）；③ 痛感/感受不能当物理动作的可数宾语（不能"刮出/划出/切出+一道+疼"，改写痛感性质如蜇/灼/锐/钝或身体反应如缩手/倒吸气）；④ 抽象对象不能被当物理对象处理（字/声音/目光/情绪不能被"挤/拽/扯/塞"，承受动作的必须是物理实体）；⑤ 状态归属不能错对象（"发干"归嗓子不归字、"沉重"归身体不归目光、"发紧"归喉咙不归声音）。判定口诀：这物体真有这属性吗？这动作真出得了这结果吗？这宾语是个东西还是个感受？这承受动作的对象是物理实体吗？这状态在现实中归谁？任一答"不"即重写。详见 `ai-flavor-scan` 第 8 层与 `../_shared/references/banned-words.md`「痛感/感受当物理动作的可数宾语」段。

**主谓动线与代词指代自检（三项主谓防错）**：写完每章后通读核验：① 破折/句号切分（双人动作交互必用句号或直接点名新主语断开，严禁在逗号后直接盲接「他/她」导致主语突变）；② 同性同场代词指代（同场存在两名同性角色时，动作与反应承接一律带人名，禁止裸用「他/她」）；③ 物理施受力动线闭环（抛/甩/推/撞动作必须交代运动轨迹与受体部位，严禁受体反应紧贴施力者造成自伤/自残错配）。详见 `创作偏好.md` 与 `../_shared/references/banned-words.md`「句内主谓动线与代词指代错位」段。

**角色履历路径一致性自检**：写完涉及角色年龄、学历、职业年限的章节（尤其是开篇、前史交代、转正/晋升等节点）时，核验：年龄 = 学历毕业年龄 + 法考/考证年限 + 实习/工作年限 + 其他空白（须有交代）。反例：28岁 + 法学院毕业 + 考了证 + 干了一年法援 = 22+1+1=24，差4年无交代。设定、追踪/角色状态、正文三处年龄必须一致；发现不一致时以路径自洽为准修设定和追踪，正文同步改。

**写后同轮处理**：候选成稿生成后必须在**同一轮**内跑完 Phase 4 步骤 10-11、下方确定性脚本与 narrative-writer 审查，blocking 清零后才能进入作者审批；不得先汇报“已写完”再等指示。写后 hook 只会自动处理写入 `正文/` 的文件，书根 `候选/` 必须由主会话手动执行本阶段检查。**唯一豁免**：用户显式说“本章不去味/跳过检查”——豁免时在该章标题行下加一行 `<!-- 去味:跳过 -->`。该标记只对写前 hook 的毒句式欠账门与写后正文网生效；**采用（`candidate-commit.py promote`）不认它**，作者要在采用时跳过语言门禁必须用 `--no-scan --reason "<理由>"`，理由写进采用回执。

**确定性检查**：候选成稿写完后，主会话对实际文件运行 `node ../_shared/scripts/check-ai-patterns.js --check --fail-on=blocking 候选/第XXX章_*.md` 与 `node scripts/check-outline-copy.js 候选/第XXX章_*.md`。blocking 命中先回候选改写并复扫；AI 句式 advisory 与细纲重合逐条读原文判断，确属模板化或照搬时改写，功能性重合则保留，并由主会话补进细纲「复沓锚句」后复扫。其中 `formulaic-parallelism` 必须连同对话一起复核，不能因为脚本不阻断台词就略过。
随后运行 `node ../_shared/scripts/normalize-punctuation.js 候选/第XXX章_*.md`（默认 `--quote-mode keep`）清理无功能省略号、破折号、双连字符和独立分隔线；盐言「」不受影响。`normalize-punctuation` 与下方退化检查仍由主会话运行。

**退化防护**：候选成稿生成后运行 `node ../_shared/scripts/check-degeneration.js --check 候选/第XXX章_*.md`。blocking（复读、截断、拒绝语、tier1 工程词泄漏）只重写受影响章节，最多 2 次；仍失败就报告证据让用户定夺。
advisory 只提示可疑处，先看脚本给出的例外；故事内系统/界面用语、弹幕刷屏、重复台词等有功能则保留。

#### Agent 调用：consistency-checker

质量检查阶段，如果项目已部署 consistency-checker agent（优先检查 `.claude/agents/consistency-checker.md` 是否存在；不存在时再检查 `.opencode/agents/`，再不存在时检查 `.codex/agents/`），spawn `Agent(subagent_type: "consistency-checker", prompt: "项目目录：{dir}\n检查范围：{本次写作的章节}\n检查类型：事实冲突+伏笔断线+角色属性不一致")` 执行一致性检查，获取 S1-S4 分级报告。如 agent 不可用，由主线程参照 long-chapter-quality.md 直接检查。

#### Agent 调用：narrative-writer（去AI味审查）

质量检查阶段，如果项目已部署 narrative-writer agent（优先检查 `.claude/agents/` 下的 `narrative-writer.md` 是否存在；不存在时再检查 `.opencode/agents/`，再不存在时检查 `.codex/agents/`），可 spawn `Agent(subagent_type: "narrative-writer", prompt: "项目目录：{dir}\n任务描述：审查+去AI味\n检查范围：{本次写作的章节}\n作者偏好：{本章 query 命中的 prose_style/story_design 项}\n首次交代：删除前先查是否首次说明动机、关系、能力来历或因果；是则保留信息并改成场内白话，重复解释才可删。\n删除优先：删后不丢伏笔/钩子/角色/情节/必要信息才删，会丢则润色（受比例上限与字数下限约束）。\n必须检查：否定翻转句；对话工整清单；细纲重复字段只消费一次；作者解释总结首次必要的改写、重复的删除；比喻堆叠只留有功能者；连续精致反应改普通动作/感觉；已有屏幕/公告/表单/物证等保留为场内载体；任务卡点只用于原有任务且必须改变信息/关系/代价/选择/伏笔。")` 执行文字质量审查和去AI味检查。如 agent 不可用，由主线程直接执行。

检查后若正文修订改变了连续性事实，必须构造 `mode=revision` 的同章追踪事务并执行 `scripts/tracking_commit.py commit`：
- 伏笔变化用 `foreshadow_changes` 更新同一 ID 的当前行，不追加重复历史；
- 时间线变化写入 `timeline_events`，由 `_tracking-state.json` 统一派生 `作者真相.md` 与 `读者已知.md`，不得把作者秘密泄露到读者视图；
- 核心角色状态变化同时提交该角色截至当前章的完整快照；
- 事务失败后保留原事务 JSON，修正写入环境并重跑同一 `commit`；成功后执行 `check`，确认 state 与全部派生视图一致再继续写作。

---

## 流程衔接

**流水线：** 长篇
**位置：** 写作（第 3/3 步）

| 时机 | 跳转到 | 命令 |
|---|---|---|
| 写完，去 AI 味 | story-deslop | `/story-deslop` |
| 想对比参考书 | story-analyze long | `/story-analyze long` |
| 需要市场方向 | story-scan long | `/story-scan long` |
| 太长，适合短篇 | story-write short | `/story-write short` |

---

## 参考资料索引

按场景加载，不一次全部加载。

### Phase 1：选题方向

| 场景 | 加载文件 |
|------|---------|
| 确定题材类型 | `references/genre-catalog.md` |
| 判断市场方向 | `references/genre-readers.md` |
| 特殊题材考量 | `references/plot-special-topics.md` |
| 女频长篇（题材/文案/平台/感情线） | `references/female-audience-writing.md` |

### Phase 2：核心设定

| 场景 | 加载文件 |
|------|---------|
| 设定人物 | `references/character-basics.md` |
| 设计关系 | `references/character-relations.md` |
| 题材框架与定位 | `references/genre-catalog.md` + `references/genre-core-mechanics.md` |
| 创建 artifact | `references/artifact-protocols.md` |
| 读者契约与主角高光 | `references/reader-contract-and-progression.md` |

### Phase 3：大纲搭建

| 场景 | 加载文件 |
|------|---------|
| 搭建大纲 | `references/outline-methods.md` |
| 设计矛盾与结构 | `references/outline-conflict.md` |
| 深度结构设计 | `references/outline-structure-theory.md` |
| 节奏与升级感 | `references/outline-rhythm.md` |
| 小纲与卡文 | `references/plot-core-methods.md` |
| 选择叙事框架 | `references/plot-frameworks.md` |
| 题材写作公式 | `references/genre-writing-formulas.md` |
| 黄金三章 | `references/opening-design.md` |
| 情绪弧线 | `references/emotional-arc-design.md` |
| 契约/终局储备/剧情单元安全审查 | `references/reader-contract-and-progression.md` |
| 反转设计 | `references/reversal-toolkit.md` |

### Phase 4：章节生产辅助

| 场景 | 加载文件 |
|------|---------|
| 章节钩子 | `references/hooks-chapter.md` |
| 悬念设计 | `references/hooks-suspense.md` |
| 段落级钩子 | `references/hooks-paragraph.md` |
| 题材正文提示卡 / 题材分类卡 | `references/genre-prose-cards.md` 索引 + `references/genre-prose-cards/` 单题材卡目录（按题材分类优先） + `references/style-genre-modules.md`（通用流派补充） |
| 打斗/装逼 | `references/style-combat-face.md` |
| 写作技法 | `references/style-craft.md` |
| 商业创作核心方法 | `references/commercial-core-methods.md` |
| 对话 | `references/dialogue-mastery.md` |
| 人物深化 | `references/character-design-methods.md` |
| 情绪技法 + 叙事单元 | `references/plot-emotion-system.md` + `references/emotional-methods.md` |
| 写作技法全程参考 | `references/writing-craft.md` |
| 格式与结构规范 | `references/format-and-structure.md`（仅对话/段落格式适用长篇） |
| 状态追踪协议 | `references/state-tracking.md` |
| 写作阶段披露协议 | `references/progressive-disclosure.md` |
| 写作流程状态工具 | `scripts/flow-state.js` |
| 章节骨架（长篇默认） | `references/chapter-skeleton-workflow.md` + `scripts/check-chapter-skeleton.js` |
| 候选模式（作者拍板/采用/重写） | `references/candidate-workflow.md` + `scripts/candidate-commit.py` |
| 结构化状态库（实验性旁路） | `references/state-store.md` |
| 当前剧情单元与契约校准 | `references/reader-contract-and-progression.md` |

### Phase 5：质量检查

| 场景 | 加载文件 |
|------|---------|
| 质量检查 | `references/long-chapter-quality.md` + `references/reader-contract-and-progression.md` |
| 禁用词扫描 | `../_shared/references/banned-words.md` |
| AI句式脚本复扫 | `../_shared/scripts/check-ai-patterns.js` |
| 去AI味 | `../_shared/references/anti-ai-writing.md` |

### 按主题快速定位（横切主题）

有些主题横跨多个阶段、散在多个文件里。下表给每个主题一个**权威文件**（先读它，通常够用），配套文件只在需要那个角度时再加载。括号是该文件里对应的小节。

| 主题 | 权威文件（先读） | 配套文件（按角度补充） |
|------|-----------------|----------------------|
| 爽点（按意图分流） | **`references/plot-emotion-system.md`**（爽点设计体系：本质/六种类型/倒推法——"怎么设计爽点"先读这个） | 翻盘/高潮式爽点→`references/plot-core-methods.md`（假胜→崩解）· 打脸/装逼释放→`references/style-combat-face.md`· 题材打脸逆袭公式→`references/genre-writing-formulas.md`· 爽文循环/多层→`references/outline-methods.md`·`references/outline-conflict.md` |
| 情绪模块 | **`对标/{书名}/剧情/情绪模块.md`（项目/书级权威）**；无对标或设计新模块时再读 `references/plot-emotion-system.md` | `references/outline-rhythm.md` 只作理论参考；不得覆盖对标书权威模块 |
| 节奏 | **`对标/{书名}/剧情/节奏.md`（项目/书级权威）**；无对标或设计新节奏时再读 `references/outline-rhythm.md` | `references/plot-core-methods.md` 只作理论参考；不得覆盖对标书权威节奏 |
| 高潮 | **`references/plot-core-methods.md`**（高潮构建公式：蓄能→假胜→崩解） | `references/outline-rhythm.md`（高潮分类与反推）· `references/outline-methods.md`（八节点故事结构：结构定位） |
| 金手指 | **`references/plot-special-topics.md`**（金手指拆分理解与战力防崩 + 进阶设计） | `references/outline-conflict.md`（金手指与身份：四点统一） |
| 感情线 | **`references/character-relations.md`**（好感度体系/四阶段 + 男女频差异） | `references/outline-conflict.md`（感情线设计）· `references/style-combat-face.md`（后宫文女主 / 男频极简爱情线构型）· `references/plot-special-topics.md`（爱情线提纯策略） |
| 反转 | **`references/reversal-toolkit.md`**（反转类型/铺垫/有效性自检） | `references/plot-core-methods.md`（假胜：先给希望再击碎） |
| 人物 | **`references/character-basics.md`**（主角/配角/反派/动机模板速填） | `references/character-design-methods.md`（三层标签反差/九维深化）· `references/character-relations.md`（关系类型/感情线） |
| 女频写作 | **`references/female-audience-writing.md`**（女频长篇：核心原则/文案/题材/感情线长线/平台） | `references/genre-readers.md`（读者心理/平台差异）· `references/character-relations.md`（感情线总框架） |
| 去AI味 | **`../_shared/references/anti-ai-writing.md`**（AI指纹/核心规则/Show Don't Tell） | `../_shared/references/banned-words.md`（禁用词扫描）· `references/long-chapter-quality.md`（成稿检查） |

---

## 语言

- 跟随用户的语言回复，用户用什么语言就用什么语言回复
- 中文回复遵循《中文文案排版指北》

---
