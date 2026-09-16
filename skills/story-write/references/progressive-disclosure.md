# progressive-disclosure.md：写作阶段披露协议

本协议用于控制 `story-write` 每一轮只读取、展示和产出当前阶段必需的信息。目标是降低长篇上下文膨胀、减少重复提问，并让“继续”“日更”“精修”“检查”等短指令能稳定回到正确阶段。

## 定位

- 本协议是流程控制规则，不替代 `追踪/_tracking-state.json`、`追踪/上下文.md`、细纲、正文或 `state-store.md`。
- `state-store.md` 记录故事事实事件；本协议记录写作流程走到哪里、下一步需要什么。
- 没有持久状态文件时，先从现有项目文件推断阶段；能推断时继续，不能推断时只问缺失的最小问题。

## 状态字段

写作流程可维护一个轻量状态对象，建议存放在项目根或书目录的 `追踪/写作流程状态.json`：

```json
{
  "schema_version": 1,
  "mode": "long",
  "current_phase": "chapter_writing",
  "current_book": "书名",
  "current_chapter": 21,
  "current_stage": "skeleton_ready",
  "known_inputs": ["题材定位", "卷纲", "本章细纲", "续写状态卡", "本章骨架"],
  "missing_inputs": [],
  "artifacts": [
    "设定/题材定位.md",
    "大纲/细纲_第021章.md",
    "追踪/上下文.md",
    "骨架/第021章_章名.md"
  ],
  "execution_status": "ready",
  "next_action": "expand_chapter_skeleton"
}
```

字段含义：

| 字段 | 含义 |
| --- | --- |
| `mode` | `long` 或 `short` |
| `current_phase` | `topic`、`setting`、`outline`、`chapter_writing`、`revision`、`quality_check`、`publish_ready` |
| `current_book` | 当前书名或相对目录 |
| `current_chapter` | 当前要写、改或检查的章节号；短篇可省略 |
| `current_stage` | 阶段内位置，如 `detect`、`plan`、`ready_first_skeleton`、`skeleton_ready`、`candidate_review`、`validate`、`repair`、`done` |
| `known_inputs` | 已识别且本阶段会使用的资料 |
| `missing_inputs` | 阻塞当前阶段的最小缺失项 |
| `artifacts` | 本阶段允许读取或写入的主要文件 |
| `execution_status` | `ready`、`blocked`、`running`、`needs_repair`、`done` |
| `next_action` | 下一步动作名，必须能映射到本 skill 的流程；长篇章节阶段依次为 `write_chapter_skeleton`、`expand_chapter_skeleton`、`review_candidate` |

## 阶段读取规则

| 阶段 | 只读取 | 不读取 |
| --- | --- | --- |
| `topic` | `选题决策.md`、扫榜结果、对标候选索引 | 正文全文、全部角色档案 |
| `setting` | 题材参考、对标情绪/节奏、核心角色资料 | 未来章节正文、无关题材包 |
| `outline` | 设定、卷纲、对标结构、契约规则 | 正文全文 |
| `chapter_writing` | 本章细纲、上一章正式正文、续写状态卡、本章出场角色、相关伏笔；按阶段加读同章骨架或候选正文 | 全部正文、全部对标章节、其他章骨架或候选 |
| `revision` | 被修改章节、该章时点状态、相邻章节、相关追踪 | 不相关卷的正文 |
| `quality_check` | 本次必读正文、质量规则、扫描脚本；理解疑点可向前检索已采用正文并回查；累计连读可比较此前相似单元正文 | 当前所判章节之后的正文答案；盲读者不读设定、大纲、追踪、设计卡、写作意图或其他版本 |
| `publish_ready` | 待发布章节、平台格式规则、发布队列 | 大纲和设定全文 |

`quality_check` 的必读范围不是前文访问禁令。逐章理解按 [分批精读协议](../../reader-comprehension-scan/references/reading-protocol.md)，记录精读/检索/回查范围及证据，未核实保持待核实。父流程可读取设计材料用于后置对照，但不得传给独立读者；普通作者视角一致性检查所需资料与正文盲读输入分开。

累计体验检查按 [长篇连读协议](../../story-review/references/longform-reading.md) 完整读取应读单元或十五章窗口，再比较旧单元正文；不能以本阶段“减少上下文”为由截断必读范围，也不能拼接分批报告冒充独立顺序连读。

## 交互输出

每轮开始先给短状态，不展开长说明：

```text
已识别：{任务类型}
当前阶段：{current_phase}/{current_stage}
已有资料：{known_inputs 简表}
当前缺少：{missing_inputs；无则写 无}
本次执行：{next_action}
```

只有 `missing_inputs` 非空时才提问；问题必须只针对缺失项。已有资料不得重复向用户确认。

## 更新时机

在以下节点更新流程状态：

1. 完成选题确认后，进入 `setting`。
2. 写完核心设定后，进入 `outline`。
3. 生成可写细纲后，进入 `chapter_writing/ready_*_skeleton`，下一步生成章节骨架。
4. 骨架通过结构验证后，进入 `chapter_writing/skeleton_ready`；骨架不推进正式章号或追踪。
5. 收到成稿候选后，进入 `chapter_writing/candidate_review`；只有候选采用并通过追踪事务后才推进 `current_chapter`。
6. 用户要求修改旧章时，临时进入 `revision`，完成后回到修改前阶段。
7. 用户只说“检查”时，进入 `quality_check`，保持只读，除非用户明确要求修改。

## 长篇到期连读的派生状态

- 新书在 Phase 3 完成单元规划和 tracking 第0章初始化后、首章生成前执行 `review-state.js longform init --new-book`（完整参数见长篇连读协议），旧书无策略即未启用；显式选择起始章节后按长篇连读协议执行，不自动补迁移或将历史漏审写成已审。
- 当前章按既有规则采用后，若检查点到期则先进入 `pending_reading`；下一章正文生成前，必须由共同检查点计算/验证入口确认有效已审记录或明确的作者继续授权。detect/update、单元收口与写前组装使用同一入口，规划工作可继续。
- `.story-review/` 的独立长篇记录由 `review-state.js` 管理，flow-state 只派生显示和引用。不得在上述轻量状态对象里另存可变的审查结果或用 `current_stage=done`、手填 PASS 绕过读取与核验。
- 正文/比较材料版本、边界或要求范围变化使旧结果 `stale`；独立阅读不可用、失败或缺读保留待审。已审与问题已解决分开，下单元处理项必须在下一检查点回应。
- 作者临时继续保持待审并限定适用范围，到下一检查点回收；明确豁免记 `waived`，不算已审，不重复索要同一有效授权。旧版流程状态的 `done` 不推导为新策略已完成。
- 实际入口为 `review-state.js longform`，状态源 `.story-review/longform-v1.json`；写操作传 `--expected-revision`，状态只引用返回的 revision 与检查点。完整参数及 JSON 输入见长篇连读协议「实际接口与最小操作例」。接口错误或 gate 未通过时保留待审，不能手写状态替代运行器。

## 与状态库的分工

- 写作流程状态回答“现在该做什么”。
- `state-store.md` 回答“第 N 章时故事事实是什么”。
- `追踪/_tracking-state.json` 和派生 Markdown 仍是长篇追踪权威；本协议只决定何时读取它们。

## 失败处理

- 状态文件不存在：从目录结构和追踪文件推断；推断成功后继续。
- 状态字段缺失：补齐能从文件得到的字段，只问无法推断的必需项。
- 状态与产物冲突：正式故事事实以 `正文/` 和追踪事务为准；骨架与候选只能决定流程阶段，不能覆盖事实状态。
- `missing_inputs` 非空：停止进入下一阶段，只报告缺失项和修复动作。
