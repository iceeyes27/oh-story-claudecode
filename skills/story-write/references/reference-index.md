# 参考资料索引

## mode=short

## 参考资料

按当前阶段 Reference Gate 和写前准备加载必需文件，其余按需：

| 文件 | 何时加载 |
|------|----------|
| [references/short-format.md](short-format.md) | 写作前必读（短篇正文格式，两平台模板） |
| [references/submission-craft.md](submission-craft.md) | 投稿前必读（平台基调 知乎/小程序/番茄 · 导语门面 · 付费点断点） |
| [references/short-craft.md](short-craft.md) | 写作全程参考（短篇通用底座：情绪直写与场景支撑、在场叙述、超短章节制） |
| [references/genre-styles/](genre-styles/) | **定方向后必读**：按题材加载对应风格包（追妻火葬场 / 世情打脸 / 复仇打脸 / 总裁豪门 / 宅斗宫斗 / 民俗怪谈 / 悬疑 / 甜宠 / 双男主 / 沙雕脑洞），正文风格随之切换 |
| [references/short-deslop.md](short-deslop.md) | 去AI味时必读（短篇专属，只杀真·AI腔，不杀情绪烈度） |
| [references/workflow-design.md](workflow-design.md) | Phase 2 构思、设计字段、Agent 调用与完成门禁；Phase 3/4 不预加载 |
| [references/workflow-draft.md](workflow-draft.md) | Phase 3 写正文前必读：参数与逐场景写作；完成门槛见入口 |
| [references/workflow-revision.md](workflow-revision.md) | Phase 4 精修/自检前必读：检查分工、去味调用、扫描与交付验收 |
| [references/writing-workflow.md](writing-workflow.md) | Phase 2 设计任务 + Phase 4 精修 |
| [references/genre-writing-formulas.md](genre-writing-formulas.md) | 冷门题材结构骨架补充（核心 10 题材直接用 genre-styles/） |
| [references/genre-writing-techniques.md](genre-writing-techniques.md) | 跨题材通用技法（震惊场景/三翻四震/感情线四阶段/喜剧flag） |
| [references/emotional-methods.md](emotional-methods.md) | 设计情感时 |
| [references/hooks-chapter.md](hooks-chapter.md) | 章节钩子设计 |
| [references/short-suspense.md](short-suspense.md) | 短篇悬念设计 |
| [references/hooks-paragraph.md](hooks-paragraph.md) | 段落钩子技巧 |
| [references/villain-and-reveal.md](villain-and-reveal.md) | Phase 2 设计反派时 |
| [references/short-reversal.md](short-reversal.md) | 设计短篇反转时 |
| [references/short-prose-quality.md](short-prose-quality.md) | 精修检查时 |
| [_shared/references/banned-words.md](../../_shared/references/banned-words.md) | 禁用词表 |
| [_shared/references/style-resolution.md](../../_shared/references/style-resolution.md) | 写作、改写、去味和审稿的文风冲突裁决 |
| [_shared/scripts/normalize-punctuation.js](../../_shared/scripts/normalize-punctuation.js) | Phase 4 文件模式确定性标点整理 |
| [_shared/scripts/check-ai-patterns.js](../../_shared/scripts/check-ai-patterns.js) | Phase 3 完成门槛与 Phase 4 复扫；报告 AI 句式、标点与密度风险，结合书级白名单复核 |
| [_shared/scripts/check-degeneration.js](../../_shared/scripts/check-degeneration.js) | Phase 3 完成门槛与 Phase 4 复扫；报告模型退化（复读/截断/工程词泄漏），blocking 需重新生成 |
| [_shared/scripts/check-phase2-contract.js](../../_shared/scripts/check-phase2-contract.js) | Phase 2 产物确定性验收；返回具名失败与最小 repair_scope |
| [_shared/scripts/check-delivery-contract.js](../../_shared/scripts/check-delivery-contract.js) | 最终交付确定性验收；按用户参数检查非空白字符、节数与小节格式 |
| [references/dialogue-mastery.md](dialogue-mastery.md) | 写对话时 |
| [references/output-contract.md](output-contract.md) | Phase 2 对标上下文加载时（理解 analyze 产出格式与消费规范） |

### 按主题快速定位（横切主题）

有些主题散在多个文件里。下表给每个主题一个**权威文件**（先读它，通常够用），配套文件只在需要那个角度时再加载。括号是该文件里对应的小节。

| 主题 | 权威文件（先读） | 配套文件（按角度补充） |
|------|-----------------|----------------------|
| 情绪落地（怎么写情绪） | **`references/short-craft.md` 第2节**（情绪直写、场景支撑与重复说明取舍） | 各 `genre-styles/` 包的「情绪烈度与模式」 |
| 情绪设计（情感结构） | **`references/emotional-methods.md`**（情感三板斧 + 拉扯节奏 + 失败模式） | `references/genre-writing-techniques.md`（情绪操控核心法则 / 情绪三层次） |
| 反转 | **`references/short-reversal.md`**（反转类型 / 铺垫 / 揭示位置 / 有效性自检） | `references/villain-and-reveal.md`（真相揭露机制 / 反转有效性自检） |
| 反派揭露 | **`references/villain-and-reveal.md`**（反派模板 / 揭露机制 / 报应设计） | `references/short-reversal.md` |
| 人物 | **各 `genre-styles/{题材}.md` 的「对话风格」「招式库」**（受害者-复仇者主角声线、白月光软刀、施害者道德绑架人设，corpus-grounded） | `references/villain-and-reveal.md`（反派/揭露）· `references/genre-writing-techniques.md`（三层标签反差 / 人设从缺点开始）· `references/dialogue-mastery.md`（声线差异） |
| 钩子 | **`references/hooks-chapter.md`**（章节/开篇钩子类型） | `references/hooks-paragraph.md`（段落钩子）· `references/short-suspense.md`（悬念设计） |
| 女频写作 | **对应 `genre-styles/{题材}.md`**（追妻火葬场 / 总裁豪门 / 宅斗宫斗 / 甜宠 / 世情打脸的题材声线、虐爽比例、招式） | `references/genre-writing-techniques.md`（女频读者心理与写作技法 / 感情线四阶段推进法）· `references/emotional-methods.md`（情绪拉扯） |
| 题材风格 | **`references/genre-styles/{题材}.md`**（核心 10 题材的腔调/开篇/钩子/情绪烈度/招式/收尾，corpus-grounded） | `references/genre-writing-formulas.md`（冷门题材结构骨架）· `references/genre-writing-techniques.md`（核心梗 / 卖点 / 通用技法） |
| 开头 | **各 `genre-styles/{题材}.md` 的「开篇范式」**（关系锚 + 全弧剧透导语 + 火葬场预告，真实开篇范例）+ `short-craft.md` 第12节（开头事件密度） | `references/hooks-chapter.md`（开篇钩子类型）· `references/hooks-paragraph.md`（段钩密度） |
| 格式与节奏 | **`references/short-format.md`**（短篇正文格式，两平台模板） | `references/short-craft.md`（情绪落地/三维度揉进/疏密）· `references/writing-workflow.md`（设计/精修工作流） |
| 对话 | **`references/dialogue-mastery.md`**（对话技法主文件：差异化/潜台词/对话节奏） | `references/short-craft.md`（三类台词与对话权力博弈）· 各 `genre-styles/` 包的真实金句库 |
| 去AI味 | **`references/short-deslop.md`**（短篇专属：只杀真·AI腔，不杀情绪烈度/审判句/火葬场预告） | `_shared/references/banned-words.md`（禁用词扫描）· `_shared/scripts/check-ai-patterns.js`（AI句式复扫）· `references/short-prose-quality.md`（成稿检查） |

---

## mode=long

长篇阶段主入口是 [long-mode.md](long-mode.md)，项目结构和主产物权威见 [project-files.md](project-files.md)，写前召回见 [benchmark-recall.md](benchmark-recall.md)，追踪初始化见 [tracking-initialization.md](tracking-initialization.md)。按当前阶段再定点读取：

| 阶段 | 必读或主参考 |
|---|---|
| Phase 1-2 选题与设定 | `long-genre-catalog.md`、`genre-readers.md`、`character-basics.md`、`reader-contract-and-progression.md` |
| Phase 3 大纲 | `workflow-setup.md`、`outline-methods.md`、`outline-structure-theory.md`、`artifact-protocols.md` |
| Phase 4 正文 | `benchmark-recall.md`、`writing-craft.md`、`long-format.md`、`state-tracking.md` |
| Phase 5 检查 | `long-chapter-quality.md`、`reader-contract-and-progression.md` 与 `_shared` 扫描器 |

题材、人物、反转、对话等技法只在当前问题命中时读取；不得因索引存在而一次加载全部参考。
