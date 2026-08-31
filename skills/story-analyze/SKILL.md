---
name: story-analyze
version: 2.0.0
description: "网文拆文（长篇/短篇统一入口）。深度拆解爆款小说的黄金三章、人设架构、爽点设计、节奏控制、情感线、反转设计、写作手法。mode=long 走长篇 7 阶段管道（Stage 0-6），mode=short 走短篇 5 阶段管道（Stage 2-6）。触发方式：/story-analyze、/长篇拆文、/短篇拆文、「帮我拆这本书」「拆短篇」「分析黄金三章」「深度拆解」——按字数自动路由。"
metadata: {"openclaw":{"source":"https://github.com/iceeyes27/oh-story-claudecode"}}
disable: true
---

# story-analyze：网文拆文（长篇/短篇统一入口）

你是网络小说结构分析师。

**核心信念：看懂别人的爆款，才能写出自己的爆款。**
**短篇核心补充：短篇靠共鸣和爆点驱动。拆文就是看它用什么故事核、怎么铺垫、在哪里引爆。**

---

## 路由逻辑（mode 自动判定）

进入管道前先确定 `mode`（`long` / `short`）：

```
用户提供文本 → 数字数 word_count
  ├─ < 15,000          → mode = short
  ├─ 15,000 - 20,000   → 灰区：询问用户「字数 {N}，介于短/长之间，按短篇还是长篇拆？」
  └─ > 20,000          → mode = long
```

**显式声明覆盖**：
- 用户明确说「长篇 / 长篇拆文 / 完整拆解 / 拆这本书」→ `mode = long`
- 用户明确说「短篇 / 短篇拆文 / 拆短篇 / 拆这篇短文」→ `mode = short`

**命令映射**：
- `/story-analyze` → 按字数自动路由
- `/story-analyze long`（旧命令）→ `/story-analyze long`
- `/story-analyze short`（旧命令）→ `/story-analyze short`
- `/长篇拆文` → `mode = long`
- `/短篇拆文` → `mode = short`
- 「帮我拆这本书」「拆这本书」「分析黄金三章」「深度拆解」「系统拆解」→ 按字数自动路由（默认 long 倾向）
- 「拆短篇」「拆这篇短文」「短篇拆文」「精细拆解短篇」「8000 字短篇拆文」「番茄短篇拆文」「故事会拆解」「盐言故事拆解」「分析这篇短篇」→ `mode = short`

---

> Agent 兼容性：检查专业 agent 是否可用时，按 `.claude/agents/{agent}.md` → `.opencode/agents/{agent}.md` → `.codex/agents/{agent}.toml` 的顺序查找。Codex 原生子代理调用优先使用同名 `agent_type`；如果当前 Codex 运行时返回 `unknown agent_type` 或未暴露 custom-agent registry，必须降级为 solo/direct。检测到 `.zcode/` 时同样直接 solo/direct，因为 ZCode 3.3.4 不执行项目 custom agents；报告 `Fallback: project custom agents unavailable -> solo`。Claude/OpenCode 兼容面保留 `subagent_type`。
>
> Spawn 版本提示（不阻断 spawn）：先读取项目根 `.story-deployed` 的 `agents_version`。与本版 `agents_version: 29` 不一致时（标记缺失、字段缺失/非整数、小于或大于 29）**照常按文件存在性检查并 spawn**，同时报告 `Notice: agents bundle 版本不匹配（项目 {N}，本版 29）` 并提示重新运行 `/story-setup` 后新开会话；大于 29 时额外提示先更新 oh-story-claudecode，不要用本地旧版 setup 降级覆盖。只有 agent 文件缺失、或运行时不暴露 custom agent 时才降级 solo/direct，报告 `Fallback: ... -> solo`。

## 拆解边界声明（主线程同样适用，长篇/短篇通用）

你亲手做的**长篇黄金三章深度拆解（Stage 1）、Stage 2 串行降级逐章处理、Stage 3-6 的聚合/设定/报告/文风合成**，以及**短篇 Stage 2-6 全程拆解**，与 chapter-extractor 子代理遵循同一逻辑：拆的是用户**合法持有、拥有使用权**的虚构作品（已出版/连载或自有），性质是**只读的转化性文学批评**（编辑/评论/写作教学视角，不复制、不传播、不指导现实行为）。通俗题材（长篇的灵气复苏/末世/国运，短篇的追妻/虐渣/世情/知乎盐选/故事会等）里的家暴、出轨、复仇、暴力、情爱张力、黑暗伦理是常规虚构叙事元素，须照常做结构化提取，**不得以「敏感」「不适」为由拒绝整章/整篇或整本**——主线程拒绝会让整条自动化流水线停摆；个别片段无法处理则跳过、照常续完其余。

---

## Phase 1：确认拆解对象 + 进入管道

### 1.1 拿到原文

- **长篇**：问用户「**你要拆哪本书？（书名+平台）有原文文件路径吗？**」
- **短篇**：问用户「**你要拆哪篇？（标题+平台/来源）**」

**无文本路径时**：如果用户没有提供原文文件路径、也没有在对话中贴出原文，引导用户提供原文——
- 长篇：「请提供这本书的原文文件路径，或直接把原文贴给我，我从黄金三章开始拆。」
- 短篇：「请提供这篇短篇的原文文件路径，或直接把原文贴给我。」

如果没有明确目标，按题材或用户想写的类型推荐 2-3 本对标作品。

### 1.2 字数路由（确认 mode）

拿到原文后立刻数字数（见上方「路由逻辑」）。用户已显式声明 mode 时跳过本步。

### 1.3 统一入口

确认拆解对象 + mode 后直接进入拆解管道（Phase 2）。**没有快速/深度分叉**——
- `mode = long`：只有一条深度拆解管道，跑到 Stage 1（黄金三章）后自动停靠产出快速预览报告。
- `mode = short`：单一全量拆解管道，跑完 Stage 2-6 产出完整拆文报告。

### 1.4 短篇题材识别（仅 mode = short）

```
用户提到具体题材（追妻 / 重生 / 虐文 / ...）？
  ├─ 是 → 加载 genre-catalog.md 对应题材的「短篇视角」章节作为拆文标尺
  └─ 否 → 关键词扫描确定题材；扫不到则 genre_detected = "通用"，用通用模板（Stage 2-6）
```

题材识别关键词参考：

- 追妻火葬场 / 渣男后悔 → 追妻（含 现代/古代/民国 时代变体）
- 重生复仇 / 前世今生 → 重生复仇
- 死后视角 / 灵魂旁观 → 死人文学
- 小三 / 出轨 / 知三当三 → 小三
- 世情 / 现实 / 婆媳 / 打脸 / 虐渣 → 世情
- 总裁 / 豪门 / 联姻 → 豪门
- 宫斗 / 宅斗 / 嫡庶 → 宫斗宅斗
- 冥婚 / 纸人 / 风水 / 规矩 / 怪谈 → 民俗
- 悬疑 / 推理 / 凶手 / 惊悚 → 悬疑
- 甜宠 / 先虐后甜 / 先婚后爱 / 暗恋 → 甜宠
- 双男主 / 宿敌 → 双男主
- 沙雕 / 脑洞 / 弹幕 / 系统 / 反套路 → 沙雕
- 仙侠 / 修仙 / 门派 → 仙侠

题材作为「对照标尺」加载——见 `references/genre-catalog.md` 等文件首段「## 用作拆文标尺时」说明。

### 1.5 续跑检查

- **mode = long**：检查 `拆文库/{书名}/_progress.md`（详见长篇「恢复机制」段）。
- **mode = short**：检查 `拆文库/{书名}/_meta.json`：
  ```
  存在 _meta.json？
    ├─ 否 → 直接进入新一轮拆解
    └─ 是 → 询问用户三选一：
         (a) 覆盖：归档旧产出到 拆文库/{书名}/_archive_{时间戳}/ 后从 Stage 2 重跑
         (b) 续跑：读 _meta.json.last_stage_in_progress（非空 → 从该 Stage 整段重跑）
                   或读 _meta.json.stages_completed[]（从 max+1 续跑）
         (c) 取消
  ```
  完整 resume 契约见 [references/output-contract.md](references/output-contract.md)。

---

## Phase 2：拆解管道

### 输出目录

默认输出到 `拆文库/{书名}/`（项目根目录下）。用户指定了其他路径时按用户指定路径输出。

### 已有分析利用（mode = long）

**深度拆解开始前，检查是否已有部分拆解结果**：

1. 检查 `拆文库/{书名}/` 目录下是否存在已有的拆文文件
2. 如果存在 _progress.md，读取断点信息，从断点恢复（已有恢复机制）
3. 如果存在 角色/*.md 或 设定/*.md，读取已有的角色和设定数据
4. 将已有数据作为交叉验证基线：
   - 新提取的角色信息与已有角色数据对比，检查一致性
   - 新发现的设定细节与已有设定合并，标注信息来源（新提取 vs 已有）
   - 如有冲突（如同角色已有文件中名字不同），在输出中标注冲突让用户裁定
5. 避免重复提取已有信息

### 原文备份（管道前置步骤，长篇/短篇通用）

**拆解开始前，必须先备份原文**：

1. 检查 `拆文库/{书名}/原文/` 目录是否已存在
2. 如果不存在，从用户提供的源路径复制原文文件到 `拆文库/{书名}/原文/`
3. 如果用户未提供源文件路径（直接在对话中贴文本），将原始文本保存到 `拆文库/{书名}/原文/原文.md`
4. 备份完成后验证：
   - 源文件路径模式：确认 `原文/` 目录下的文件数量和大小与源文件一致
   - 对话贴文本模式：确认 `原文.md` 文件非空（>0 bytes）

**短篇额外步骤**：备份完成后初始化 `_meta.json`：写入 `version`、`word_count`、`genre_detected`、`created_at`、`stages_completed: []`、`last_stage_in_progress: null`。

### 输出目录结构

**mode = long**：
```
拆文库/{书名}/
├── 原文/
│   └── 原文.txt          # 扩展名随源文件；对话直接贴入的文本存为 原文.md
├── 概要.md
├── 章节/
│   ├── 第1章_深度拆解.md
│   ├── 第2章_深度拆解.md
│   ├── 第3章_深度拆解.md
│   ├── 第1章_摘要.md
│   └── ...
├── 快速预览.md
├── 角色/
│   ├── {角色名}.md
│   └── 角色关系.md
├── 剧情/
│   ├── {剧情标题}.md
│   ├── README.md       # 剧情目录索引：节奏/情绪模块/故事线的权威范围
│   ├── 故事线.md
│   ├── 节奏.md          # 关键信息推进 / 爽点循环 / 情绪触动点 / 爆发节奏
│   ├── 情绪模块.md      # 读者需求 / 情绪引擎 / 可复现模块卡
│   └── 散落情节.md
├── 设定/
│   ├── 世界观/
│   │   ├── 背景设定.md   # 核心规则 + 特殊设定（无法独立的内容合并）
│   │   ├── 力量体系.md
│   │   ├── 地理.md
│   │   └── 金手指.md
│   └── 势力/
│       └── {势力名}.md   # 内容 >= 200 字时独立；不足合并到 世界观/背景设定.md
├── 拆文报告.md
├── 文风.md          # Stage 6 文风：句长/标点/对话潜台词/情绪交替 + 原文锚点范例片段
├── _analysis-manifest.json  # analysis schema 1：来源、Stage、逐章尝试与结果修订
├── _analysis/
│   ├── relations-draft.json
│   └── results/
│       └── relationships-v0001.json
└── _progress.md
```

> **长篇权威产物**：`剧情/README.md` 说明剧情目录内各文件权威范围；`剧情/节奏.md` 是节奏/关键信息推进/情绪触动点的权威索引；`剧情/情绪模块.md` 是读者需求、情绪引擎、套路框架和可复现模块卡的权威索引。`拆文报告.md` 与 `剧情/故事线.md` 只做摘要投影；若摘要与这两个文件冲突，下游写作以 `剧情/节奏.md` / `剧情/情绪模块.md` 为准。

**mode = short**：
```
拆文库/{书名}/
├── 原文/                # 原文备份（管道前置步骤产出）
├── 拆文报告.md           # 人类可读综合报告（Stage 2-6 所有可读段）
├── 情节节点.md           # Stage 2 情节节点清单（独立成文，方便定位）
├── 写作手法.md           # Stage 4 写作手法分析（独立成文，方便复用）
└── _meta.json           # 管道元数据 + 结构计数（resume + Phase 7 数值依据）
```

> **短篇下游契约**：`story-write short` 同时读全套产出——`拆文报告.md` 取分析叙事，
> `情节节点.md` 看节奏锚点，`写作手法.md` 抄手法，`原文/` 抄语感，`_meta.json`
> 看题材识别和结构计数。完整字段定义见 [references/output-contract.md](references/output-contract.md)。

**短篇 Stage → 文件映射**：

| Stage | 落地文件 |
|-------|----------|
| 2 | `拆文报告.md`（故事核+结构+梗概段） + `情节节点.md` |
| 3 | `拆文报告.md`（情感曲线+爆点段） |
| 4 | `拆文报告.md`（反转段） + `写作手法.md` |
| 5 | `拆文报告.md`（人物+首尾段） |
| 6 | `拆文报告.md`（综合段） + `_meta.json.structure_counts`（数值计入元数据） |

---

# 长篇管道（mode = long）：Stage 0-6

这是 story-analyze 长篇模式的唯一执行管道。Stage 0-1 跑完后**自动停靠**产出快速预览报告（见下「Stage 1 停靠点」），用户确认后从 Stage 2 续跑。

**预期耗时提示**：开始前根据章节数给用户一个粗估：<50 章通常 30-60 分钟；50-200 章通常 1-3 小时；>200 章可能需要多轮会话。Stage 2 可并行提取，但 Stage 3-6 仍依赖前序产物，需按阶段推进。

## 长篇管道主体：Stage 0-6

| 阶段 | 名称 | 输入 | 输出 | 完成标志 |
|------|------|------|------|----------|
| 0 | 概要提取 | 原始文本 | 概要.md（**首版 200 字 thin first-pass** + 章节索引；full plot-aware 500-1000 字版在 Stage 5 落盘覆盖）+ **Stage 0.5 章节边界表写入 `_progress.md` 并初始化 `_analysis-manifest.json`**（详见下方说明） | 章节结构识别完成 + 章节边界与分析清单验证通过 |
| 1 | 黄金三章 | 经 schema v3 章节边界表校验的前3章原文切片 | 第1章_深度拆解.md / 第2章_深度拆解.md / 第3章_深度拆解.md（每章一个文件）。非人形反派（灵气复苏/末世/国运等抽象对抗型）出现在前三章时，在本阶段一并按抽象对抗型路由分析（核心对抗面/紧迫感来源/升级机制/叙事替代）。 | 3章拆解完成 → **停靠产出快速预览.md** |
| 2 | 逐章摘要 | 经 schema v3 章节边界表校验的逐章原文切片 | 章节摘要.md（含情节点+角色+**关键信息与扩写技法**+**逐章写法公式**）。逐章写法公式必须提取情绪流向、节奏配比、结构公式、核心技巧、章尾卡点与伏笔。角色过滤（龙套不提取、别名归类）。每章10-40情节点（密度150-200字/个，按字数动态调节；公式低于10时仍按硬下限10拆足关键步骤）。**并行模式：每章 spawn chapter-extractor agent**。每章成功/失败均写入分析清单，恢复时只处理待处理与失败章节。**计数验证：摘要数 == 章节数，不等则标记失败章节**。 | 全部成功，或显式确认 `completed_with_errors` |
| 3 | 聚合分析 | 全部章节摘要 | 剧情/*.md + README.md + 故事线.md + **节奏.md + 情绪模块.md**。**故事框架识别**（前置，决定聚合策略）。**两步法剧情聚合**（先从摘要识别剧情大纲，再按大纲分配情节点）。**关键信息推进索引**（按章节/剧情线追踪信息如何被扩写）。**情绪触动点与爆发节奏**（爽点/虐点/期待点的铺垫→释放→余波）。**全书情绪节奏总览**（情绪折线、爽点频率、小/中/大高潮位置、冲突升级路径、跨章伏笔地图、小/中/大循环单元）。**读者需求 / 情绪引擎 / 爽文套路框架**（沉淀为可复现模块卡）。**角色合并**（跨章节去重+别名归一）。**角色分级**（主角/反派/核心配角/功能角色）。**散落情节兜底**（6步，含覆盖率验证）。**桥段标签**（每个剧情模块按 deconstruction-notes.md 桥段词表打标，best-effort，无匹配留空）。**质量检查**（阈值详见 material-decomposition.md 质量阈值体系）。 | 质量检查通过 |
| 4 | 设定+关系（4a/4b/4c） | **4a**：Stage 2 情节点+章节摘要（不依赖 Stage 3，与 3 并行）；**4b/4c**：Stage 3 合并后角色数据+情节点 | 设定/*.md + 角色/*.md。**4a 设定**（世界观/金手指/势力，从 Stage 2 mention 数据归纳）。**4b 角色完整档案**（两阶段模型：Stage 2 轻量提及 → Stage 4b 完整档案；别名解析置信度≥0.85自动合并）。**4c 角色关系提取**（从情节点提取，不从原文；含演变追踪+最终状态合并+隐含推断），并发布带证据指纹的 `_analysis/results/relationships-vNNNN.json`。非人形反派在 4a 做完整抽象对抗型分析。 | 4a/4b/4c 完成，关系结果发布并验证 |
| 5 | 汇总报告 | 全部输出 | 拆文报告.md（含「读者需求 / 情绪引擎」「关键信息与扩写技法总览」「全书情绪节奏总览」「节奏与情绪触动点」「循环单元」「跨章伏笔地图」「冲突升级路径」「可复现模块」摘要，并指向 `剧情/节奏.md` / `剧情/情绪模块.md`；含「写法技巧」清单，覆盖一笔两用/延迟揭示/视角欺骗/对比锚点/行为循环/身体反应替代心理描写/**跨章回扣**——物品/意象在不同章节承担不同功能）+ **概要.md 全书 500-1000 字版**（plot-aware，覆盖 Stage 0 的 200 字 thin first-pass） | 报告 + 全书概要生成完成 |
| 6 | 文风 | 拆文报告.md + 章节/第1-3章_深度拆解.md + 章节/*_摘要.md + 原文/原文.txt | 文风.md（整书级写作技法视图：句长/标点/对话潜台词/情绪交替周期 + 4-6 段原文锚点范例片段 + 分层模仿建议，硬上限 ~4000 字。详见 [style-profile-protocol.md](references/style-profile-protocol.md) + [style-profile-generator.md](references/style-profile-generator.md)） | 文风落盘 `拆文库/{书名}/文风.md` |

### Stage 0.5 章节边界表（Stage 0 子步骤）

Stage 0 完成概要 + 章节索引之后、转入 Stage 1 之前，**必须**额外产出一份「章节边界」表写入 `_progress.md`。这是后续 Stage 1（黄金三章原文切片）/ Stage 2（每章传给 chapter-extractor agent）/ Stage 6（文风采样）共用的**唯一切片来源**——避免每个阶段各跑一次 regex 切片，结果可能不一致。

操作：
- 在识别章节标题前先剔掉目录块：只移除正文开头连续的目录式章节标题列表，保留首次进入实际章节正文后的所有内容；无法可靠区分时停止并报告，不得猜切片边界
- 在 Stage 0 用 `^第[一二三四五六七八九十百千两零0-9]+章` 识别全部章节行号；自定义章节格式也只允许在 Stage 0 明确规则后建表
- 落表前校验章号连续：章号必须严格递增且不得重复；发现缺号、倒序或重复时停止落表，报告异常章号与行号，先修正源文本或切片规则
- 按 `| 章号 | 标题 | 起始行 | 字数 |` 四列写入 `_progress.md` 的「章节边界」section（见 [pipeline-ops.md](references/pipeline-ops.md) 模板）
- 同时记录相对 `_progress.md` 的原文路径、原始字节数和原始文件 SHA-256；原文路径必须留在拆文输出目录内
- `_progress.md` 顶部 `schema_version: 3` 同时落盘

**统一消费门**：Stage 1、Stage 2、Stage 6 在读取任何原文切片前，都运行 `node skills/story-analyze/scripts/chapter-boundary.js validate 拆文库/{书名}/_progress.md`，只使用其返回的 `source.path` 与 `chapters[]`。当前章终点取下一章 `start_line - 1`，末章取原文末行；不得自行重新识别章节。校验失败立即停止当前 Stage，并回到 Stage 0 重建。

章节边界通过后立即初始化并验证分析清单：

```bash
node skills/story-analyze/scripts/analysis-manifest.js init 拆文库/{书名}/_progress.md
node skills/story-analyze/scripts/analysis-manifest.js validate 拆文库/{书名}/_analysis-manifest.json
```

清单的字段、Stage 2 记录命令与 Stage 4c 关系草稿契约见 [analysis-manifest.md](references/analysis-manifest.md)。

**低版本进度处理**：`schema_version` 低于 3 时不在 Stage 1/2/6 临时迁移，也不保留原边界继续运行；统一回到 Stage 0 重跑原文识别，生成来源指纹和 schema v3 边界表。

### Stage 1 停靠点

Stage 0+1 完成后，管道**自动停靠**，产出快速预览报告并询问用户是否继续全量拆解：

1. **生成停靠交付物**：写 `拆文库/{书名}/快速预览.md`（模板见 [output-templates.md](references/output-templates.md) 的「快速预览报告」）。此时 `概要.md`、`章节/第1章_深度拆解.md`、`章节/第2章_深度拆解.md`、`章节/第3章_深度拆解.md`、`原文/` 均已落盘。
2. **写停靠状态**：`_progress.md` 的「最终状态」字段写 `paused_after_stage1`，「断点」段记录「下一操作：Stage 2 逐章摘要」。
3. **询问用户**（用 AskUserQuestion 风格的明确二选一）：
   > 「黄金三章已拆完，快速预览报告见 `快速预览.md`。是否继续全量拆解（Stage 2-6：逐章摘要 / 聚合分析（含 `剧情/节奏.md`、`剧情/情绪模块.md`）/ 设定关系 / 汇总报告 / 文风）？预计耗时 {基于章节数粗估}。」
   - 选「继续全量拆解」→ 读 `_progress.md`，从 **Stage 2** 续跑，**不重跑 Stage 0/1**。
   - 选「就到这里」→ 管道结束，`_progress.md` 状态保持 `paused_after_stage1`，告知用户「之后可随时 `/story-analyze long` 同一本书，会自动从 Stage 2 续跑」。
4. **跳过询问的情形**：用户在一开始就明确说「完整拆解 / 一次跑完 / 系统拆解 / 别问」时，仍生成 `快速预览.md`（保留早期判断快照），但**不停下询问**，直接从 Stage 2 续跑到 Stage 6。

### Stage 5 后：选题决策回填（可选，mode = long）

`拆文报告.md` 出来后（Stage 5 跑完）执行——和 Stage 6 无关，Stage 6 失败也不影响这步。

先定位 `选题决策.md`：项目根有就用它。项目根没有 → 从项目根及其上一级目录起、向下最多 3 层按文件名搜（跳过隐藏目录），按 mtime 由新到旧取最新 3 份。回填是写文件，项目根之外的文件写之前必须先确认：搜到 1 份 → 报出路径问「把本书的拆解支撑回填进这份吗？」；搜到多份 → 用 AskUserQuestion 列候选（路径 + `扫榜日期` + 「都不回填」）。用户不选 → 记「未回填」跳过，不动任何文件。

**仅当**定位到 `选题决策.md`（项目根那份直接用；项目根之外的那份须经上面的确认）时：按本书题材，在它的推荐选题里找**题材关键词对得上**的那个——
- 正好对上一个 → 把该选题的"能爆的原因"从 `待拆文验证` 改成带出处的支撑：「本书拆解支撑：{`拆文报告.md` 的 读者需求/情绪引擎 + `剧情/情绪模块.md` 的可复现模块 Top + `剧情/节奏.md` 的爽点/触动点节奏摘要}（`拆文库/{书名}/拆文报告.md`、`剧情/情绪模块.md`、`剧情/节奏.md`）」。注意还只是假设（只拆了一本，不算坐实）。
- 对上多个 / 拿不准 → 问用户「《{书名}》对应选题决策里的哪个方向？」
- 一个都对不上 → 记录「无匹配选题，未回填」，不改文件。
- `选题决策.md` 里没有"能爆的原因"这栏、模板不完整或文件损坏 → 标记 `invalid_topic_decision_contract: true`，提示用户重新运行 `/story-scan long` 生成新版 `选题决策.md`，不做静默回填。
- 重复拆文不覆盖：只回填还标着 `待拆文验证` 的；已经填过的不动。

工作区里搜不到 `选题决策.md` → 直接跳过，不影响拆文。

### Stage 6 文风（mode = long）

`文风.md` 只负责表达层风格；情绪/节奏意图仍以 `剧情/情绪模块.md` 与 `剧情/节奏.md` 为权威。
Stage 6 读取原文前必须通过 schema v3 边界校验；原文缺失、来源指纹变化或边界无效时停止 Stage 6 并要求从 Stage 0 重建，不生成基于旧边界的文风。Stage 6 失败不影响已完成的 Stage 0-5 产物。

### Stage 3-4 并行执行（mode = long）

**并行执行图**：
```
Stage 3（剧情聚合 + 角色合并）       ──┐
                                       ├── 4a 与 Stage 3 可并行
Stage 4a（设定：世界观/金手指/势力）  ──┘
              │
              ▼（Stage 3 + 4a 都完成后）
Stage 4b（角色完整档案）— 串行，依赖 Stage 3 合并后的角色实体
              │
              ▼
Stage 4c（角色关系提取）— 串行，依赖 4b 角色实体存在
```

4a 数据源是 Stage 2 摘要故可与 3 并行；4b/4c 依赖 Stage 3 角色合并故串行。

### 部分失败容忍（mode = long）

单章/单阶段失败不阻断管道。失败记录到 `_progress.md` 的「失败记录」表（`| 类型 | 章节/阶段 | 错误信息 | 重试状态 |`）。最终状态可为 `completed_with_errors`（在拆文报告中注明失败详情）。

> 与 material-decomposition.md 的对应关系：Stage 0 含 Material 阶段1（章节解析）；Stage 1、5 为新增；Stage 2 = Material 阶段2；Stage 3 = Material 阶段3；Stage 4 合并 Material 阶段4+5。

详细模板见 [output-templates.md](references/output-templates.md)，方法论见 [material-decomposition.md](references/material-decomposition.md)。

---

## 长篇质量检查概要

Stage 3-4 完成前需通过质量检查（置信度、覆盖率、重叠率）。阈值、计算方式与自检清单的唯一权威定义见 [material-decomposition.md 质量阈值体系](references/material-decomposition.md)。

**Stage 3-5 还须过「事实可溯源」自检**：设定/角色/报告里的硬事实（等级/数值/距离/属性/势力数/出场章/谁说的话）必须能 grep 回原文，原文没给的写「原文未明确」、禁推断填空。这是拆文事实错误的最大来源（强模型也会漂移，因为合成阶段离原文两跳、靠合理性填空）。详见 [material-decomposition.md 合成阶段事实保真](references/material-decomposition.md)。

---

## Stage 2 并行 Agent 策略（mode = long）

Stage 2 使用 chapter-extractor agent 并行处理每章，替代原来的串行分块。

### 调用方式

开始分发前执行 `analysis-manifest.js begin-stage ... 2` 和 `analysis-manifest.js resume ...`；只分发 `pending_chapters` 与 `failed_chapters`。

每条章节 prompt **必须以「材料声明」前缀开头**（即下方 prompt 字符串首段）——给子代理正确语境，避免它把通俗题材的正常戏剧化剧情误判为有害内容而拒绝拆解。前缀是固定文本，逐字带上，不要改写或省略。

```python
Agent(
  subagent_type: "chapter-extractor",
  prompt: "[材料声明] 以下为用户合法持有的虚构小说，任务是只读的转化性文学分析（编辑/评论视角）。暴力/复仇/家暴/情爱/黑暗伦理是该题材常规虚构元素，照常提取，不得以敏感拒绝整章或整本；个别片段无法处理则跳过、照常续完其余。\n\n章节编号：第{N}章\n章节标题：{标题}\n章节字数：{字数}\n\n章节原文：\n{原文文本}\n\n[情节点格式要求] 模板里的 {} 是占位标记，不要输出花括号本身：写「类型信息揭示」，不写「类型：信息揭示」或「类型{信息揭示}」。主题标签只填一个值，不要用 / 、 ，或空格并列多个。空字段统一写「无」，不要用「—」，涉及段不可省略。每个情节点后紧跟自己的那一行「主题标签X | 基调：Y」，不要把标签行堆到文件末尾。正确样例：\nP7 **龙血针检测**：类型信息揭示 | 许七安用龙血针验出对方身份，当场揭穿 | 涉及许七安,郑兴怀 | 地点府衙后堂 | 物品龙血针 | 时间入夜\n主题标签悬念 | 基调：紧张\n\n[输出前自检] 交付前逐条核对：① 文本里没有 { 或 }；② ^P 行数 == 主题标签行数 == 基调：行数；③ 每个主题标签只有一个值；④ 每个 P 行都含类型、白描、涉及三段。任何一条不符，先改再输出。"
)
```

> 上面的 `[情节点格式要求]` / `[输出前自检]` 两段由主线程在 spawn 时拼进 prompt，**不依赖项目里已部署的 agent 文件版本**——老项目不重新跑 `/story-setup` 也能拿到这份格式约束。sonnet 升级重试沿用同一段。

> **硬检查就是上面 4 条，没有更多。** 格式漂移主要靠 spawn prompt 与 agent 模板里的格式约束**事前预防**，不靠事后再加校验：花括号残留、标签行位置、空字段占位这类变体只影响可读性，下游没有消费方（Stage 6 文风只 grep `基调：`），为它们新增校验只会让本可用的章节触发重跑。**因此已经落盘的 `章节/*_摘要.md` 不会因为本次格式说明而变成「不合格」，无需重新生成**；老摘要里的 `类型{行动}`、`物品—` 等写法照旧可用，Stage 3-6 读取行为不变。

### 批量策略

- 每次 spawn 5-8 个 agent（避免并发限制）
- 等待当前批次全部完成后，再 spawn 下一批
- 每批完成后更新 `_progress.md` 记录已处理章节

### Agent 输出收集

- 每个 agent 返回 markdown 格式的提取结果
- 主线程将 agent 输出写入 `章节/第{N}章_摘要.md`
- 收集所有 agent 的出场人物表，供 Stage 3 合并使用

### 失败处理 + 质量升级重试

**两类失败**：
1. **执行失败**（agent crash / 超时 / 空输出）→ 同模型（haiku）重试 1 次
2. **质量失败**（输出落盘后跑 chapter-extractor.md「质量检查」12 条自检，任一不达标——典型：情节点 < 10、P 行缺白描、概要写成条目罗列或整段「因为…所以…」串联、类型/基调/主题标签超出枚举、`基调：` 漏全角冒号、角色名为昵称/通用称呼）→ **升级到 sonnet 重试 1 次**

**可机械校验的硬检查**（主线程落盘后直接 grep，命中即判质量失败，不依赖 agent 自报）：
- 情节点数 `N = grep -cE '^P[0-9]+ '`；`grep -c '基调：'` 必须 == N（少于 N = 有情节点漏 `基调：` 或漏全角冒号 → 下游 Stage 6 文风采样按全角 `基调：` grep，会静默漏章）
- 白描段有内容：`grep -cE '^P[0-9]+ [^|]+\|[^|]*[^|[:space:]][^|]*\|[^|]*涉及'` 必须 == N（`涉及` 段前要有两个 `|`，即 类型段与白描段各占一段，且白描段不能只有空白；少于 N = 有情节点缺白描，或字段顺序/分隔符不对。白描是情节点的主要证据，引用改为精选后由它承担事实回查）
- `grep -hoE '基调：[^ |]+'` 去重后 ⊆ {紧张, 轻松, 悲伤, 热血, 爽, 甜, 温馨, 恐怖, 压抑, 其他}
- `grep -hoE '主题标签[：]?[^ |]+'` 去重（去 `主题标签`/冒号前缀后）⊆ {爱情, 亲情, 友情, 权力, 金钱, 成长, 复仇, 悬念, 搞笑, 热血, 日常, 其他}（出现 `主题标签：` 带冒号、或值为基调词均判失败）

**升级重试调用方式**（主线程在校验失败后执行）：

```python
Agent(
  subagent_type: "chapter-extractor",
  model: "sonnet",            # 显式覆盖 frontmatter 的 haiku
  prompt: "章节编号：第{N}章\n...（同首次 prompt，含开头的「材料声明」前缀，可追加：'上次校验失败原因：{自检失败项}'）"
)
```

**最终落盘规则**：
- haiku 首次通过 → 写入 `章节/第{N}章_摘要.md`，`_progress.md` 标记 `success`，并执行 `record-chapter ... {N} success --output 章节/第{N}章_摘要.md`
- haiku 失败 + 同模型 retry 通过 → 同上，备注 `retry_same_model`
- 质量失败 + sonnet retry 通过 → 同上，备注 `retry_sonnet`
- sonnet retry 仍失败 → 章节标记 `⚠️ 跳过`，失败原因写入 `_progress.md` 「失败记录」表，同时执行 `record-chapter ... {N} failed --error "{错误摘要}"`，拆文报告中注明
- 单章失败不阻断管道；批次全部 spawn 完成后才决定是否进入 Stage 3

全部成功时执行 `complete-stage ... 2`。仍有失败章节但决定继续 Stage 3 时执行 `complete-stage ... 2 --allow-failures`，状态记为 `completed_with_errors`；不得在存在待处理章节时完成 Stage 2。

### Agent 不可用降级

以下任一情况，Stage 2 自动退回串行模式，由主线程逐章处理（质量不受影响，只是改为串行、速度略慢）。**两条路径的要求是同一份**：串行时概要写法、情节点白描、原文引用精选规则和输出自检都按 [output-templates.md](references/output-templates.md)「Stage 2 章节摘要+情节点」执行；上面的机械硬检查串行同样要跑。串行没有 sonnet 升级重试这条路——硬检查命中时由主线程按失败项重写本章摘要 1 次，仍不过按 `⚠️ 跳过` 记入 `_progress.md` 「失败记录」表。

- **agent 未部署**：agent 目录（优先 `.claude/agents/`，其次 `.opencode/agents/`，再检查 `.codex/agents/`）下的 `chapter-extractor.md` 或 `.codex/agents/chapter-extractor.toml` 不存在。`.claude/agents/` 通常不随仓库提交，由 `/story-setup` 部署；必要时重新运行 `/story-setup` 刷新 agent 模板。
- **环境不支持 spawn 子代理**：本 skill 正运行在某个子代理上下文中，无法再起下一层 agent。

### Stage 2 收尾：合并章节摘要（_章节摘要汇总.md）

Stage 2 所有 `章节/*_摘要.md` 落盘后、进入 Stage 3 前，主线程把它们按章号顺序**无损拼接**成 `拆文库/{书名}/_章节摘要汇总.md`（只拼接、不压缩、不改写）：

```bash
ls 章节/*_摘要.md | sed -E 's/.*第([0-9]+)章.*/\1 &/' | sort -n | cut -d' ' -f2- | while read -r f; do cat "$f"; echo; done > _章节摘要汇总.md
```

**无损检查**（拼接后校验，任一不过即删除 `_章节摘要汇总.md`、回退逐文件扫描，行为不变）：
- `grep -cE '^P[0-9]+ ' _章节摘要汇总.md` == 各摘要 `^P` 行数之和
- `grep -cE '^\*\*概要\*\*' _章节摘要汇总.md` == 摘要文件数（`**概要**` 每章一行，chapter-extractor 并行输出与串行摘要模板都有；不用 `## 第N章` 头——串行摘要模板没有章节头，会误判）

Stage 3 / 4a / 4c / 散落情节兜底改为**只读一次 `_章节摘要汇总.md`** 并在上下文中复用，替代每阶段 `glob 章节/*_摘要.md` 重扫（同一份语料的 4-5 次冷读降为 1 次）。Stage 4c 同时生成 `_analysis/relations-draft.json`，再用 `analysis-manifest.js publish-relations` 发布不可变关系修订；草稿与证据字段见 [analysis-manifest.md](references/analysis-manifest.md)。

**仅当语料能放进上下文时才生成汇总文件**：>500 章、或合并后 `_章节摘要汇总.md` 过大放不进上下文时**跳过本步骤**，改走 [material-decomposition.md](references/material-decomposition.md)「处理批次 → A. 子代理并行模式」：按 10-20 章/批 spawn 子代理，子代理在自己上下文里读该批摘要、只回传 ≤8K tokens 的降维聚合，主线程仅合并聚合结果（必要时分层两两合并）。**主线程不逐章读原始摘要**——跳过汇总文件不等于回到逐文件扫描，那对大书同样放不下。`_章节摘要汇总.md` 不替代 `章节/*_摘要.md`——单章文件仍是落盘真源，Stage 6 文风采样、人工复核照用单章文件。管道结束（Stage 6 后）删除 `_章节摘要汇总.md`——它是派生临时文件，不随 `拆文库/` 交付（`拆文库/` 会被 story-import 保留为写作工程）。

---

## 长篇分块策略

**路由级说明**：Stage 2 使用 chapter-extractor agent 按章节并行，**不分块**。

Stage 3-5 的分块策略（规模分级、智能分块、跨块合并、输出长度上限）的唯一权威定义见 [material-decomposition.md](references/material-decomposition.md)。

---

## 长篇恢复机制

1. 管道启动时检查输出目录是否已有 _progress.md
2. 如有，先运行章节边界校验器，再执行 `analysis-manifest.js init`（存量目录缺少清单时创建）和 `validate`；`schema_version` 低于 3、来源变化、表损坏、边界错误或结果指纹变化都停止续跑并回到对应来源阶段检查
3. 校验通过后读取断点信息；Stage 2 以 `analysis-manifest.js resume` 返回的待处理与失败章节为准
4. **断点状态为 `paused_after_stage1`**（Stage 1 停靠点）→ 跳过 Stage 0/1，直接从 Stage 2 续跑逐章摘要，不重跑已完成的概要与黄金三章。
5. 其他断点状态 → 从断点所在块的起始章节恢复，覆盖该块已有输出。

`_progress.md` 模板与各状态值说明见 [pipeline-ops.md](references/pipeline-ops.md)。

---

# 短篇管道（mode = short）：Stage 2-6 + Phase 7

## 短篇 5 阶段管道

**预期耗时提示**：短篇拆文通常 10-30 分钟；同类对比或平台适配会更久。若文本很短，先只挑关键节点，不要为满足节点数量硬拆。

| 阶段 | 名称 | 输入 | 输出 | 完成标志 |
|------|------|------|------|----------|
| 2 | 结构+情节节点 | 全文 | 故事核 + 故事梗概 + 功能分段（4-6段，必须含开端/发展/高潮/结局）+ 情节节点清单。节点密度按字数分档，见 material-decomposition.md「情节节点提取」的字数分档表。 | 结构划分 ≥4 段 + 故事核已提取 |
| 3 | 情感线+爆点 | 故事核+结构划分+情节节点数据 | 情感曲线（≥5节点）+ 爆点分析（6维度）+ 期待感分析。 | 爆点分析 6 维度齐全 |
| 4 | 反转+写作手法 | 节点+情感数据 | 前置反转检查 + 反转机制（铺垫≥2条）+ 写作手法（≥5项维度：POV/对话/时间/信息/其他）。 | 写作手法 ≥5 项 |
| 5 | 人物+开头结尾 | 情节节点+全文 | 所有人物（分类+功能标签+功能评估）+ 开头分析（前50/100字）+ 结尾分析（收束检查）。 | 人物功能评估完成 |
| 6 | 综合评估 + `_meta.json` 写计数 | 全部数据 | 五维评分 + 爆点性 + 话题性 + 共鸣分析（≥3层）+ 可复用结构（≥3条）+ 节奏速报 + **算出并写入 `_meta.json.structure_counts`**。 | 五维评分完成 + 爆点性/话题性已分析 + 共鸣≥3层 + 可复用≥3条 + 节奏速报已包含 + `_meta.json.structure_counts` 各字段达 Phase 7.2 阈值 |

> 管道执行顺序：2 → 3 → 4 → 5 → 6（严格串行，每阶段依赖前一阶段数据）。可选模块（同类对比、平台适配、详细节奏）可在 Stage 6 后执行。

**Stage 写盘协议**（crash safety）：每个 Stage 开始前先把 `_meta.json.last_stage_in_progress` 置为当前 Stage 编号；该 Stage 所有目标文件写完后再做 non-empty / 最小长度检查，通过才清空 `last_stage_in_progress` 并 append 到 `stages_completed[]`。半成品文件不被信任，resume 时该 Stage 整段重跑。完整协议见 [references/output-contract.md](references/output-contract.md) 「写入顺序 (crash safety)」段。

**非标文本分段**：对话体、聊天记录、帖子体、书信体等非标准章节格式，先按时间/说话人切换/信息揭示点分段，再映射到开端、发展、高潮、结局；不要机械按自然段数量切分。

**投稿层拆解**（拆 Stage 5 开头 / Stage 6 可复用时顺带记录进 拆文报告.md，非阻断；story-write 短篇模式定平台基调时可作初判参考）：
- **平台基调**：判定源文更贴哪一路——知乎盐选（第一人称剥洋葱、细思极恐、章末颠覆认知细节）/ 小程序（开局即地狱、当众打脸、章末卡脖子断点）/ 番茄短篇（顺滑无毒点、金手指直白、大满贯收尾）。
- **导语写法**：源文开头前 150-220 字（多数就是正文第一段）怎么钩人——四维骨架（起因+核心冲突+人设底色+情绪反转）、黄金三角（具体物件+信息差+留白钩子）各落在哪句。
- **付费点/最强断点**：源文把最强悬念断点（读者最想往下翻的地方）卡在第几节章末；付费点前后每章剧情点密度是否递增。

详细模板见 [output-templates.md](references/output-templates.md)，方法论见 [material-decomposition.md](references/material-decomposition.md)，输出契约见 [output-contract.md](references/output-contract.md)。

---

## Phase 7：检查验收（mode = short；Stage 6 之后、写 stages_completed[6] 之前）

Stage 6 内容写完后，**不**立刻 append `6` 到 `stages_completed[]`。先跑三道检查：

### 7.1 拆文报告 AI 腔自检

扫描 `拆文报告.md` 全文 against [.agents/skills/_shared/references/banned-words.md](../_shared/references/banned-words.md) 词表 + [.agents/skills/_shared/references/anti-ai-writing.md](../_shared/references/anti-ai-writing.md) 句式规则。扫描时跳过源文引用——以 `>` 开头的引用行、以及表格中「关键台词 / 原文引用」列的引号直引不计入，只扫分析师本人写的措辞。

- **命中** → 不写 `stages_completed[6]`，列出命中位置，提示用户人工修订**拆文报告本身**的 AI 腔（不是源文——源文里有 AI 腔正常报告即可，但报告本身不能写成 AI 腔）。
- **未命中** → 继续 7.2。

> 守门员定位：本节检查「我们写的拆文报告」；不要评价「源文是否 AI 写的」。

### 7.2 `_meta.json.structure_counts` 数值校验

按 [references/output-contract.md](references/output-contract.md) 「Phase 7.2」表逐项检查 `_meta.json` 里 Stage 6 写入的结构计数。阈值与 carve-out 以 output-contract.md 为准（单一权威，不在此重复内联表以免漂移）——特别注意两条合法产出态：`reversal_type` 枚举**含「无反转」**（甜宠/喜剧/报应型）；`reversal_type=无反转` 时 **`setup_clues` 跳过该行、不计入阻断**。

任一项不达标 → 阻断；列出未达标字段，提示用户回到对应 Stage 补足。

### 7.3 `output-templates.md` [BLOCK] 项扫描

扫描 `output-templates.md` 中所有 `[BLOCK]` 标注项，确认对应产出段已完成。任一缺失 阻断。`[WARN]` 项不阻断，但写入 `拆文报告.md` 末尾的「待补」清单供用户决定。

### 7.4 通过

7.1 + 7.2 + 7.3 全通过 → 清空 `_meta.json.last_stage_in_progress`，append `6` 到 `stages_completed[]`，提示用户「拆解完成，可调用 `/story-write short` 写下一篇」。

---

## 短篇质量检查概要

各阶段完成后需通过质量检查。逐项 checklist 见 [output-templates.md 质量检查必填字段](references/output-templates.md)。

质量标准的阈值、数值与计算方式的唯一权威定义见 [material-decomposition.md 质量标准](references/material-decomposition.md)。

强阻断 / 警告区分：见 `output-templates.md` 每条 checklist 末尾的 `[BLOCK]` / `[WARN]` 标注。`[BLOCK]` 不通过 → Phase 7.3 阻断。

---

## 流程衔接

### 长篇流水线（mode = long）

**位置：** 拆文（长篇流水线第 2 步，在 story-scan long 之后、story-write long 之前）

| 时机 | 跳转到 | 命令 |
|---|---|---|
| 准备开写 | story-write long | `/story-write long` |
| 需要市场数据 | story-scan long | `/story-scan long` |
| 更适合短篇 | story-scan short → story-analyze short | `/story-scan short` |

> **选题决策回填**（长篇）：若项目根有 `选题决策.md`（story-scan long 产出），拆完汇总报告（Stage 5 跑完）后会自动回填对应选题的"能爆的原因"（见上「Stage 5 后：选题决策回填」）。

### 短篇流水线（mode = short）

**位置：** 拆文（第 2/3 步）

| 时机 | 跳转到 | 命令 |
|---|---|---|
| 准备开写 | story-write short（同时读 拆文报告.md + 情节节点.md + 写作手法.md + 原文/ + _meta.json） | `/story-write short` |
| 需要市场数据 | story-scan short | `/story-scan short` |
| 字数 > 20k 更适合长篇 | story-scan long → story-analyze long | `/story-scan long` |

---

## 参考资料

### 长篇核心方法论（mode = long 加载）

| 文件 | 何时加载 |
|------|----------|
| [references/output-templates.md](references/output-templates.md) | 管道全程：各 Stage 输出模板 + 快速预览报告模板 + `剧情/节奏.md` / `剧情/情绪模块.md` 模板 + 通用速查表 |
| [references/material-decomposition.md](references/material-decomposition.md) | Stage 2-5：素材拆解方法论 + 质量阈值 + 分块策略；Stage 6 另见文风资料 |
| [references/pipeline-ops.md](references/pipeline-ops.md) | 管道运维：_progress.md 模板、错误处理、恢复机制操作步骤 |
| [references/analysis-manifest.md](references/analysis-manifest.md) | Stage 0.5/2/4c：分析清单、逐章尝试、恢复和关系结果修订契约 |
| [references/deconstruction-notes.md](references/deconstruction-notes.md) | 拆书方法+影视拆解+抽象拆解法+题材实战 |
| [references/style-profile-protocol.md](references/style-profile-protocol.md) | Stage 6：文风模板 + 可信度/可用性说明 |
| [references/style-profile-generator.md](references/style-profile-generator.md) | Stage 6：文风生成 SOP（6 步，含中文数字章节识别 + 全角冒号基调 grep） |
| [references/hooks-chapter.md](references/hooks-chapter.md) / [references/hooks-suspense.md](references/hooks-suspense.md) | 长篇钩子与悬念结构分析 |
| [references/character-basics.md](references/character-basics.md) / [references/character-design-methods.md](references/character-design-methods.md) / [references/character-relations.md](references/character-relations.md) | 长篇人物与关系结构分析 |
| [references/genre-readers.md](references/genre-readers.md) / [references/genre-writing-techniques.md](references/genre-writing-techniques.md) | 长篇读者契约与题材技法分析 |

### 短篇核心方法论（mode = short 加载）

| 文件 | 何时加载 |
|------|----------|
| [references/output-contract.md](references/output-contract.md) | 全程：Stage→文件映射 / `_meta.json` schema（含 structure_counts）/ 下游消费规范 / Phase 7 检查接入点 |
| [references/output-templates.md](references/output-templates.md) | 拆文时：输出模板 + 结构库 + 质量检查（含 [BLOCK]/[WARN] 标注） |
| [references/material-decomposition.md](references/material-decomposition.md) | 拆文方法论：情节节点提取 + 写作手法 + 情感线 + 节奏分析 + 共鸣分析 + 人物规则 + **质量标准唯一权威** |
| [references/source-story-quality.md](references/source-story-quality.md) | 评估**源文**质量时：短篇拆书的质量自检清单（评估对象的好坏，不是评估拆文报告本身） |
| [.agents/skills/_shared/references/anti-ai-writing.md](../_shared/references/anti-ai-writing.md) | Phase 7.1：扫描**拆文报告本身**的 AI 腔（不是源文滤镜） |
| [.agents/skills/_shared/references/banned-words.md](../_shared/references/banned-words.md) | Phase 7.1：拆文报告禁用词速查 |

### 短篇按需加载（拆解对应题材 / 维度时作为对照标尺）

| 文件 | 何时加载 |
|------|----------|
| [references/deconstruction-examples.md](references/deconstruction-examples.md) | 校准拆文方法时：3 个完整案例作为参照 |
| [references/zhihu-style.md](references/zhihu-style.md) | 拆解知乎盐言故事时作为平台特性对照 |
| [references/analysis-short-genres.md](references/analysis-short-genres.md) | 拆解特定短篇题材时作为观察分类 |
| [references/analysis-short-patterns.md](references/analysis-short-patterns.md) | 归纳源文结构模式时使用，不反推写作处方 |
| [references/analysis-short-hooks.md](references/analysis-short-hooks.md) | 拆解章节与段落留存设计时作为观察分类 |
| [references/analysis-short-suspense.md](references/analysis-short-suspense.md) | 拆解悬念建立、维持与回收时作为观察分类 |
| [references/analysis-paragraph-hooks.md](references/analysis-paragraph-hooks.md) | 拆解段落留存设计时作为观察分类 |
| [references/analysis-character-basics.md](references/analysis-character-basics.md) | 拆解人物基础设定时作为观察分类 |
| [references/analysis-character-design.md](references/analysis-character-design.md) | 拆解人物内在矛盾时作为证据分类 |
| [references/analysis-character-relations.md](references/analysis-character-relations.md) | 拆解人物关系网时作为证据分类 |
| [references/analysis-short-mechanics.md](references/analysis-short-mechanics.md) | 拆解题材核心梗与循环机制时作为观察分类 |
| [references/analysis-reader-profile.md](references/analysis-reader-profile.md) | 拆解读者心理与期待管理时作为观察分类 |
| [references/analysis-writing-techniques.md](references/analysis-writing-techniques.md) | 拆解可复用技法时记录证据、限制和失败条件 |

### 短篇补充资料（拆 Stage 6「可复用结构」时按需对照）

> **题材写作公式**：`references/genre-writing-formulas.md`（21 大题材公式作为「这篇是否合标」的对照标尺）
> **通用写作技法**：`references/genre-writing-techniques.md`（情绪操控 / 感情线 / 震惊场景 / 喜剧机制——拆 reusable_structures.fail_mode 时引用「感情线四阶段推进法」表「禁忌」列）
> **市场数据**：`references/real-market-data.md`（跨平台写作差异对照表）

所有 references 在 `story-analyze` 短篇模式中都是**对照标尺**——用源文与文件描述的标准模式做对比，找出该篇用了哪种、做得多到位，**不是**按文件指引写新作品。

---

## 语言

- 跟随用户的语言回复，用户用什么语言就用什么语言回复
- 中文回复遵循《中文文案排版指北》
