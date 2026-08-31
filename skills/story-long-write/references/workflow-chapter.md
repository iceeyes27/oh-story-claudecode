# workflow-chapter.md：单章正文工作流（Phase 4-5）

本文件是「写一章正文」的完整流程。SKILL.md 路由到 Phase 4 后按本文件执行；日更批量由 `workflow-daily.md` 控制批次与追踪事务，每章正文仍走本文件。

项目文件结构、产物映射表、缺失文件处理、对标分析权威优先级在 `SKILL.md` Phase 4 开头，本文件不重复（SKILL.md 恒在上下文里）。

本文件提到的 agent 都只检查当前端 canonical 目录；Antigravity 使用 `.agents/agents/agent-name/agent.md`（`agent-name` 为目标 agent 名）和 `invoke_subagent` + 同名 `TypeName`，其余端使用各自 Agent 工具。

---

## 单章写作流程

当用户准备写某一章时：

1. **检查细纲**：读取 `大纲/细纲_第{N}章.md`，并从对应 `大纲/卷纲_第X卷.md` 读取当前剧情单元（单元ID/位置、卷契约、本卷主推线/战果、终局底牌边界、风险等级）。如果不存在或缺少当前章节蓝图的必需字段，**必须先补建细纲再写正文**，不允许跳过细纲直接写作。补建时参考卷纲中本章对应的事件规划和上下文，补齐阶段位置、结构公式、禁止提前释放、内容概括、情节安排、人物关系/出场顺序、情节细化、结尾设定；无法从已有证据判断的字段写 `[待补充]`，不杜撰副线或关系。补建后按 `artifact-protocols.md` 跑 `check-outline-contract.js` 结构验收，失败只补点名字段再复验。普通旧纲走兼容检查；只有显式启用 P1 treatment 时追加 `--require-p1`，并要求 `P1质量契约.scene_catalog` 与最终情节点表逐行同序映射。
2. **读取上下文**（按需选择；缺失时遵循各项及SKILL.md Phase 4 的「缺失文件处理」，仅明确标为可选的非主产物跳过。可选快捷路径：对应 agent 已部署时 spawn story-explorer 一次获取上下文。Prompt：`项目目录：{dir}\n查询类型：context_load\n查询参数：准备写第 {N} 章\n追踪状态：last_committed_chapter={check 的值}，state_revision={check 的值}`）：
   - (1) `正文/第{N-1}章_*.md` — 上一章正文
   - (2) `大纲/细纲_第{N}章.md` — 本章细纲（含钩子设计）
   - (2a) `大纲/卷纲_第X卷.md` — 当前剧情单元、卷契约与终局储备（主推线/战果、终局底牌边界）
   - (3) `tracking_commit.py check` + `追踪/上下文.md` — `check` 无 ERROR 输出即通过，从它的紧凑 JSON 取 `last_committed_chapter` / `state_revision`，不把完整 state 加入 prompt；待回收伏笔取 `## 活跃伏笔`，角色当前状态取 `## 核心角色状态`，下一章硬承诺取 `## 下一章承诺`
   - (4) `设定/角色/{相关角色}.md`、`设定/势力/{相关势力}.md`（如存在）— 本章涉及的角色与势力（按细纲出场筛选）
   - (5) 对标书路径下 `拆文报告.md`（按对标书路径查找）— 对标参考
   - (6) `对标/{对标书名}/原文/第{N}章_*.md`（如存在）— 同位置章节参考
   - (7) `参考资料/{topic}.md`（如存在）— 历史研究资料（由 story-researcher 产出）
   - (8) 对标书路径下 `剧情/故事线.md`（按对标书路径查找）— 剧情单元索引，用于确定本章涉及哪些剧情单元
   - (9) 对标书路径下 `剧情/{相关剧情单元}.md`（按对标书路径查找）— 从索引中选择与本章相关的剧情单元文件
   - (10) 对标书路径下 `设定/世界观/*.md`（glob，按对标书路径查找）— 从当前拆文产出的主题化设定中获取参考；目录缺失则记录缺口并跳过本项，不读取扁平历史路径
   - (11) 对标书路径下 `剧情/情绪模块.md`（按对标书路径查找）— 读者需求 / 情绪引擎、爽文套路框架、可复现模块；缺失按SKILL.md Phase 4 的「缺失文件处理」设置 `missing_primary_contract` 并停止准备
   - (12) 对标书路径下 `剧情/节奏.md`（按对标书路径查找）— 关键信息推进、情绪触动点、爆发节奏；缺失按SKILL.md Phase 4 的「缺失文件处理」设置 `missing_primary_contract` 并停止准备
   - (13) `设定/题材正文提示卡.md`（如存在）— 本书正文层题材卡；缺失时从 `设定/题材定位.md` + `references/genre-prose-cards.md` 索引 + `references/genre-prose-cards/` 单题材卡目录（按题材分类优先）+ `references/style-genre-modules.md`（兜底）即时生成 `genre_prose_card`，不阻塞写作
3. **写前准备**（下面的 3 步是核心方法在单章写作中的落地：筛选状态 → 召回模块 → 确认意图）：
   - **状态筛选**：从 `追踪/上下文.md` 的 `## 核心角色状态` 取当前角色，从 `## 活跃伏笔` 取需回收/推进项，从 `## 下一章承诺` 取本章必须履行项，输出本节速记（参考 state-tracking.md）。久别角色按名读取 `追踪/角色状态/{名}.md`；只有追查变化原因时才定点查逐章增量。续写状态卡或 meta 不存在时按 workflow-daily 的当前协议处理，不手写替代文件
   - **模块召回、题材卡与文风召回**：
     - ① 本章目标情绪词？② 借鉴哪个参考文件的哪个技法？③ 用在哪些段落？答不出 → 先回读参考再动笔
     - (a) **情绪模块召回**：按「对标书路径查找」规则读 `{对标书路径}/剧情/情绪模块.md`，选出 1 个与本章目标情绪最贴近的 `selected_emotion_module`（读者需求、触发器、戏剧单元、可替换要素、反抄袭提醒）。缺失时设置 `missing_primary_contract: true`，返回明确 `repair_action` 后停止准备
     - (b) **节奏召回**：读 `{对标书路径}/剧情/节奏.md`，选出 1 条 `rhythm_reference`（关键信息 → 扩写技法 → 情绪触动点 → 爆发/冷却）。缺失时设置 `missing_primary_contract: true`，返回明确 `repair_action` 后停止准备
     - (c) **题材正文提示卡召回**：优先读 `设定/题材正文提示卡.md`；缺失则先读 `设定/题材定位.md` + `references/genre-prose-cards.md` 索引，按主题材精确匹配后只读取 `references/genre-prose-cards/` 中对应单题材卡（如 都市脑洞 / 豪门总裁 / 年代 / 双男主；低置信卡必须在意图确认标注低置信，并要求同题材对标校准），无命中再读 `references/style-genre-modules.md` 通用流派模块。跨题材时主题材抽 3-5 条、辅题材抽 1-2 条，生成短 `genre_prose_card`（题材边界、核心逻辑、读者期待、核心爽点/情绪、正文落点、前中后期打法、节奏密度、场景颗粒、禁止漂移、本章取舍、卡片置信度）。题材卡只约束正文层题材味，不改细纲剧情、不覆盖 `selected_emotion_module` / `rhythm_reference` / `设定/文风.md`；只在内部校准取舍，正文里不得出现卡名/标签/置信度/条目/合规自评
     - (d) **文风召回**：先直接读 `设定/文风.md`（不经 explorer）：含实质内容（去空白 ≥200 字，或含 句长 / 标点 / 对话 / 锚点 / 笔调 小节且小节内有可执行约束：比例 / 例句 / 禁止或偏好描述）则置 `custom_style=true`、进入「自定义文风模式」，它作权威风格基（句长 / 软标点 / 潜台词 / 情绪交替），对标 / 拆文 `文风.md` 降为参考（锚点 + 句长兜底）；空 / 仅空白 / 仅标题 / 占位 stub（待办 / 待补充 / ___）视为不存在。否则按「对标书路径查找」规则读 `{对标书路径}/文风.md`（路径优先 `{项目}/对标/{书名}/`，回退 `拆文库/{书名}/`）；多本对标书时从 `设定/题材定位.md` 读 `主对标书` 字段。**未进入自定义文风模式且**文风文件不存在 → **fail-fast 报错**：「对标书 X 缺少 文风.md。请用 `/story-long-analyze` 跑 Stage 6 生成文风，再 `/story-import` 同步。」不 inline 生成（自定义文风模式则不 fail-fast；情绪 / 节奏轴 `missing_primary_contract` 仍独立阻塞）
     - (e) **匹配章节挑选**：从 `{对标书路径}/章节/*_摘要.md` grep `基调：(紧张|轻松|悲伤|热血|爽|甜|温馨|恐怖|压抑|其他)`（全角冒号），按本章目标情绪挑章 K——多章同基调时选择规则：先看爽点类型是否接近，再看情节点数量/原文章节估算字数是否接近本章目标字数，最后取章节号最小者；必读 `{对标书路径}/章节/第K章_摘要.md`，若同章存在 `第K章_深度拆解.md` 则加读，否则回退黄金三章深度拆解/文风文件里的可借鉴技巧，不因非黄金三章缺少深度拆解而失败
     - (f) **结构化模块召回**：从对标的结构化子目录（角色/剧情/设定）中按本章情节检索相关模块；若与 `剧情/情绪模块.md` / `剧情/节奏.md` 冲突，权威文件优先，记录 `conflict`
     - (g) 输出"主对标召回摘要 + 副对标召回摘要 + selected_emotion_module + rhythm_reference + genre_prose_card + 文风召回指令 + 原文锚点片段引用"，作为 narrative-writer 的输入。**多对标书时**参 `references/cross-book-recall.md`：主对标提供文风、原文锚点与 selected_emotion_module / rhythm_reference；副对标/参考对标按阶段预算提供结构化摘要，不限制登记书目，不读取副书 `文风.md` / 原文，超过预算时裁条目不裁书目记录。
     - **快捷路径**：项目已部署 story-explorer agent 时，可一次性召回文风/模块材料。
       - 按本文件顶部规则确认 story-explorer 已部署。
       - 查询类型：`benchmark_style_load`；传入项目目录、章节号、目标基调/字数和爽点类型。
       - 需要返回：`style_profile_path`、`style_profile_summary`、`selected_emotion_module`、`rhythm_reference`、来源路径、匹配章节、锚点片段、`gaps`。
       - `gaps.missing_primary_contract` 为 true 时先按 `repair_action` 修复，不进入正文生成。
       - 主会话另行直接读 `设定/文风.md`：含实质内容时作为本书风格基准；但不豁免情绪/节奏缺失。
   - **指令确认**：综合细纲、本节速记和模块召回结果，用一句话写清本章意图。
	     - 新版细纲必须消费：阶段位置、单元ID/位置、主角目标/关键选择、结构公式、禁止提前释放、内容概括、情节安排、人物关系/出场顺序、情节细化、结尾钩子，并对照当前剧情单元的卷契约、本卷主推线/战果、终局底牌边界。
	     - **细纲优先边界**：正文只能展开本章细纲已有事件、人物、冲突、伏笔和结尾钩子；不得为了凑字或"更精彩"自造新主线、新角色、新反转、提前写后续章剧情，必要的过渡动作只能服务于细纲已列情节点。后续阶段真相、底牌、关系结论和终局矛盾不得因为章尾钩子提前泄露。反过来，细纲是"要发生什么"的契约、不是正文的形状：正文可自由编排叙述顺序、合并/穿插情节点，不必一个情节点一段、也不必按五段式顺写，把每个点演成场景而不是照抄概括语（见 writing-craft.md「从细纲到正文」）。
	     - **细纲语义去重**：同一要求在核心事件、五段式、情节安排和情节点中重复，只算一个语义点；生成前合并，不把重复次数当强调，不沿用提纲原句逐项复述。比如多处都写“不带摄像机、先听完再决定拍不拍”，正文只通过一个自然动作或一句人物判断兑现，不能拆成「至于拍不拍，怎么拍…」「不带摄像机，不带采访灯」两轮说明。
	     - 爽点出手前要有可指认的危机/期待铺垫；装逼/打脸/揭露章要写在场配角的差异反应。
	     - 高压/生死/悲痛节拍 要收紧对话声线：搞笑担当让位，信息型角色不当科普嘴，对话逐句承接对方情绪。
	     - 检查任务卡点：本章如果有“办事被卡住”，它必须卡出信息、关系、代价、选择或伏笔变化；没有就不强补。
	     - 契约风险检查：按 `references/reader-contract-and-progression.md` 判定 契约安全 / 需补强 / 契约破坏；若高光/收益被配角、机构或偶然性拿走且没有可见交换，先修纲再写。
     - 例：「快节奏打脸——账单暴露→逼问→反证→公开代价；读者等了三章，这章必须一拳到位。」
4. **资料研究**（按需）：遇到需查证的外部事实且 story-researcher 已部署时，spawn 搜索并输出到 `参考资料/`；不可用则主线程直接执行。研究完成后再继续写作。
5. **标题预检**：写正文前从细纲读取章名；如与既有章节同名或明显重复，先按本章核心事件改名，并同步细纲标题与正文文件名。
5a. **显式 P1 treatment（含 P0；默认关闭）**：见 `quality-p1.md` §3.1。冻结共同 base/预算/停止规则后 `open-treatment-run`；P0 只写 `single_draft`，P1 冻结因果拍/oracle 后独立调用 A `plain_direct`、B `voice_restore`。步骤 8–11 后才 `close-treatment-run`；close 后修改须新 run。
6. **写作与唯一 checkpoint**：将批准情节点按叙事顺序分成连续两组，同一 session 先写前组临时 segment，再且只运行一次 `{PYTHON} {skill 根}/scripts/storyctl.py wordcount checkpoint --file {前组临时文件} --target {字数目标} --chapter {N}`。把 `actual`、`remaining_user_range` 和后组原始情节点交回 writer，并明确：
   - 只完成剩余情节点，不得为字数新增独立事件、人物决定、关系变化、揭示或支线。
   - 剩余情节点完成即停，即使仍欠长也不加剧情。
   两段完成后一次组装最终正文；不做逐点配额、字数 retry、完整重写或落盘后扩写。
   - **正文元信息隔离**：`章节：第{N}章`、`上一章：正文/第{N-1}章_*.md`、`匹配第K章`、`细纲文件` 等只用于定位材料。标题行以外的正文不得出现 `第[一二三四五六七八九十百千万两0-9]+章|上一章|上章|前一章|本章|这一章|前文|后文|伏笔|细纲|读者` 这类写作工程词。需要承接前文时，改成角色能感知的事件锚点或相对时间，例如“比第一章那三秒开火更疼”必须写成“比那三秒开火更疼”。例外：角色在故事世界内真实阅读/讨论“第X章”文本，或真实身为作者/读者并谈论读者身份时，可保留相应词。
7. **正文执行**：
   - 按本文件顶部规则确认 narrative-writer 已部署。
   - 如可用，spawn `Agent(subagent_type: "narrative-writer", prompt: ...)`，prompt 只传本章必需材料：
     - 项目目录、章节、细纲文件、上一章、输出路径。
     - 写前准备输出：本节速记、情绪目标、涉及角色、参考技法。
     - 主对标/拆文路径、主/副对标召回摘要。
     - `selected_emotion_module`、`rhythm_reference` 及来源路径。
     - `genre_prose_card`（题材正文提示卡摘要，只含本章相关条目）。
     - 文风路径、文风召回指令、原文锚点片段。
     - `author_preferences`：作者记忆 `query` 结果中匹配本章的 `prose_style` / `story_design` 项；无则不传，禁止把完整画像或待确认项塞进 prompt；作为低优先级倾向自然吸收，不逐条展示或最大化命中，不牺牲连贯、节奏和字数。
     - 阶段位置、本章结构公式、本章可释放信息、本章禁止提前释放信息。
     - 字数目标、`visible_chars_v1` 口径、格式硬约束；前组后由机器给出一次剩余用户区间，不让 writer 心算或填写逐情节点配额。
     - 显式 treatment 传 `quality_treatment_mode`；P1/A 加因果拍+oracle，P1/B 加 A hash+五项 invariants；close 记 run ID（`quality-p1.md` §3.1）。
     - 细纲优先边界（内容层）：只展开本章细纲，不自造新剧情；每条情节点都要独立落地，不许漏、不许两条并一句。不得仅为追字数自动补纲、扩写或重写；实际长度统一留到步骤 8 测量。
     - 正文形状（形状层）：落地位置、顺序、拆成几处由子代理编排，可打散重排、把相邻几条缝进同一个连续动作；不要一条一段平推，不把细纲措辞原样搬进叙述。
   - 不把本文件整套规则复制进 prompt；细节以已加载 references 和 narrative-writer 模板为准。
   - agent 在同一 session 内写两个临时 segment并组装候选；P1 两次独立调用产出 A/B，父流程记录 run ID，evaluator/selector 不兼任 writer。验收前不得写 `正文/`。如 agent 未部署，由主线程保持同一隔离语义。
8. **非对称收口**：对 `草稿/待验收/第XXX章_*.md` 运行 `storyctl.py wordcount check --file {候选稿} --target {细纲目标}`，并直接对候选稿运行确定性质量脚本；此步只测量/修候选，不写 `正文/`、不提交 tracking。P1 分别处理 A/B；P0 只处理 single draft。
   - 带内 + pass → 进入六视角审查与 quality `stage/certify/accept`；fail / `invalid` → 停止。
   - `under` + pass → 展示 `accept-current-length / revise-outline-or-target / discard`，不补/重试；选择接受时在 quality `stage --resolution accepted_current_length` 留痕。
   - `over` + pass → 删除区间随 `compress-once` 交 narrative-writer；一次净删，零新语义/契约改动。会话核对情节点与钩子后复检；带内提交，否则上述三动作。
9. **检查**：章尾是否有往下看的理由（低压/过场章弱钩子或留阶段目标即可，不强求爽点）、爽点是否到位（按章节定位，高压/推进章必查）。两条可证伪核对（不达标→只修复细纲已批准内容）：① 爽点前是否有可指认的危机/期待段落？② 装逼/打脸/揭露章，在场配角是否有差异化反应？质量修复后重跑步骤 8，但不得借质量修复补新剧情追字数。
10. **元信息扫描**：检查标题行以外的正文，命中 `第[一二三四五六七八九十百千万两0-9]+章|上一章|上章|前一章|本章|这一章|前文|后文|伏笔|细纲|读者` 时必须改写为场景内表达；只有角色在故事世界内真实阅读/讨论“第X章”文本，或真实身为作者/读者并谈论读者身份时例外。
	11. **表达扫描**：detector 与禁用词表只生成 findings，不按句形自动改。逐处判断是否造成因果断裂、读感机械、声线失真或无功能重复；有证据才修，承担辩解、悬念排除、角色声线、打断或节奏功能的写法可 `PRESERVED_WITH_FUNCTION`。一级/二级仅表示复核优先级，不表示严重度。
12. **关闭 treatment、深审、抽取与逻辑原子 accept**：显式 run 在步骤 8–11 后按 5a 关闭；P1 隔离评估/盲选后复制胜出稿，P0 保存原稿与逐次修复版本。关闭正文不再修改。
   - 取最新 `state_revision`，按 workflow-daily 构造不含 `wordcount` 的逐章 JSON；执行六视角审查、盲评、独立 reader cohort + judge、writer 隔离完整抽取，形成 `story-quality-review/v1`。按 `quality-lifecycle.md` 依次 `stage → certify → accept → check`；显式 P0/P1 绑定已关闭的 `treatment_run_id`，accept 将边界写入代际。其余 accept 原子投影、失败保留和静态档案规则不变。
13. **中途快照**（长篇写作安全网）：每连续写完 3 章，在继续前执行以下快照操作：
   - 先执行 `scripts/quality_lifecycle.py check`，再执行 `scripts/tracking_commit.py check`；确认 HEAD、正文、追踪、证书/读者链没有待重放范围，tracking state 有效、逐章记录连续且派生视图一致。通过后才清理可删除的临时 segment；pending、revision、review、reader、event 冷档不删除
   - 用 `ls -la 正文/` 确认最近 3 个章节文件已成功写入磁盘且大小正常（>100 bytes）
   - 如果发现文件缺失或大小异常，立即重新写入
   - 快照完成后可继续写作

> **日更模式**：此步骤自动跳过——workflow-daily Step 2 已按章更新上下文.md。

## 写作技巧提醒

| 场景 | 技巧 |
|------|------|
| 开篇 500 字 | 必须有钩子，不能从天气/风景开始（除非反差极大） |
| 对话 | 推进剧情或揭示性格，不能只为了凑字数 |
| 打斗 | 不要流水账，写策略和反转，不写「你一拳我一脚」 |
| 日常 | 日常要有人物互动和伏笔，不能只是「吃饭睡觉」 |
| 任务卡点 | 角色办事被卡住，必须卡出信息/关系/代价/选择/伏笔变化；删掉无损就压缩或删除 |
| 爽点释放 | 铺垫要充分、释放要干脆，读者等得越久释放越要爽 |
| 爽点密度 | 高压/推进章每 3000-5000 字一个「爽」的情绪节点；低压/关系/修炼/信息整理章不强求，但每章仍要有往下看的理由（见 references/outline-structure-theory.md「章节定位与张弛」） |
| 长篇结构约束 | 参考 genre-prose-cards.md 与当前题材卡的长线约束 |
| 章尾 | 兑现细纲 `ending_beat_id` 与 `expectation_id`；可以是目标、选择、关系、兑现余波或开放问题，不强制强悬念 |
| 情绪验证 | 写完每章回头检查：读者到这里应该感受到什么？感受到了吗？没感受到 → 按章节定位补：高压/推进章补冲突或钩子，低压/关系章补关系或情绪质感，别一律加爽点 |

## 字数测量权威

字数权威默认是细纲 `字数目标` + `visible_chars_v1`：内带 ±12%，用户带 ±15%；**本轮用户明确给出上下限时，原样范围优先于自动比例带**。无节奏下限，缺目标即 `invalid`。带内提交，`under` 不补，`over` 最多净删一次；仍带外由用户接受、改目标/细纲或放弃。下一章只看 tracking 提交。

---

## 质量检查

检查三个维度：(1) **情绪交付**——每章是否交付了细纲中规划的目标情绪？(2) **契约风险**——按 `references/reader-contract-and-progression.md` 检查因果权 + 结算权、关键节点四问、期待所有权、期待债、终局储备（透支两问）与换书债；章级推进按权威文件的七类状态分档（快节奏保留可见事件/爽点下限），强弱相对本书题材与对标判断，标记 契约安全 / 需补强 / 契约破坏；契约破坏 先修正文或修后续纲。(3) **技术质量**——一致性、格式、禁用词。参考 [references/long-chapter-quality.md](long-chapter-quality.md) 中的通用检查和长篇专项清单。

**新增独立剧情 blocking**：新饭局、承诺、选择、关系变化、支线或后续义务均阻断；闲话、微连接允许。命中不自动修、不重试、不提交，并提示偏纲。

**正文元信息扫描**：按上方步骤 10 清掉标题行以外的写作工程词，再进入其他检查。`check-degeneration.js` 会确定性复扫这一项。

**写后同轮验收**：候选稿落盘不是汇报时机——每章必须在**同一轮**内跑完确定性扫描、六视角深审、问题逐条处置、盲评选择、顺序读者 cohort、完整写后抽取和逻辑原子 accept；`quality_lifecycle.py check` 通过才算完成，不得先汇报“已写完”再等指示。写后 hook 只是兜底。用户显式要求跳过去 AI 检测时，`<!-- 去味:跳过 -->` 只豁免对应 detector，不豁免逻辑/事实/理解/追读/人物/连续性深审，也不能绕过 quality lifecycle。

**确定性收尾**：主会话对待验收候选运行 `node scripts/check-ai-patterns.js --check --json 草稿/待验收/第XXX章_*.md` 与 `node scripts/check-outline-copy.js 草稿/待验收/第XXX章_*.md`。`check-ai-patterns` 的句式与标点命中全部是语义复核 finding，不按词面硬阻断；逐条读原文判断，确属问题才生成新 revision candidate，功能性写法用 `PRESERVED_WITH_FUNCTION` 处置，不为归零机械改写。其中 `formulaic-parallelism` 连同对话复核；`stock-reaction-tic` 逐处做删除测试，证书写明删除项及保留功能。
随后运行 `node scripts/normalize-punctuation.js 草稿/待验收/第XXX章_*.md`（默认 `--quote-mode keep`）清理确无功能的标点；省略、停顿和留白若服务本书声线则进入盲评，不做全局归一。narrative-writer agent 不运行这些脚本。

**退化防护**：候选落盘后运行 `node scripts/check-degeneration.js --check 草稿/待验收/第XXX章_*.md`。blocking（复读、截断、拒绝语、tier1 工程词泄漏）只修受影响区域；相同 finding 再现就重新诊断，结构/全文重写需作者批准。
advisory 只提示可疑处，先看脚本给出的例外；故事内系统/界面用语、弹幕刷屏、重复台词等有功能则保留。

### Agent 调用：consistency-checker

质量检查阶段，consistency-checker 已部署时，仅按当前运行时的 canonical agent 目录检查并 spawn，获取 S1-S4 报告。Prompt：`项目目录：{dir}\n检查范围：{本次写作的章节}\n检查类型：事实冲突+伏笔断线+角色属性不一致`。不可用则主线程参照 long-chapter-quality.md 直接检查。

### Agent 调用：narrative-writer（去AI味审查）

质量检查阶段，narrative-writer 已部署时可 spawn 文字质量与去AI味检查。Prompt：`项目目录：{dir}\n任务描述：审查+去AI味\n检查范围：{本次写作的章节}\n作者偏好：{本章 query 命中的 prose_style/story_design 项}\n删除优先：每条 AI 味项先判能否删除——删后不丢伏笔/钩子/角色/情节/必要信息的直接删，会丢才润色（删除受比例上限与字数下限约束，跌破下限改降AI重写）\n检查项按你自己的 7 Gate、禁止事项与写完后对话自检全量执行，其中否定翻转句式和台词里的工整否定清单不因脚本豁免台词而跳过`。不可用则主线程按 `references/anti-ai-writing.md` 与 `references/banned-words.md` 执行。

检查与修复全过程按 [quality-lifecycle.md](quality-lifecycle.md) 执行。候选稿先 `stage`，六视角证书 `certify` 后才 `accept`；accept 在临时代际内调用 tracking 事务并切换唯一 HEAD。禁止先运行 `tracking_commit.py commit` 再补证书。

检查后若旧章修订改变了连续性事实，必须构造 `mode=revision` 的同章追踪事务随 pending generation 一起提交：
- 伏笔变化用 `foreshadow_changes` 更新同一 ID 的当前行，不追加重复历史；
- 时间线变化写入 `timeline_events`，由 `_tracking-state.json` 统一派生 `作者真相.md` 与 `读者已知.md`，不得把作者秘密泄露到读者视图；
- 核心角色状态变化同时提交该角色截至当前章的完整快照；
- 事务失败后保留 pending 与原事务 JSON；修正候选或证书后新建 revision/pending，不覆写旧档。成功后执行 `quality_lifecycle.py check`，确认 HEAD、正文、追踪、读者链和证书一致，再继续写作。
