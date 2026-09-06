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
| `quality_check` | 本次检查范围、质量规则、扫描脚本 | 非检查范围正文 |
| `publish_ready` | 待发布章节、平台格式规则、发布队列 | 大纲和设定全文 |

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

## 与状态库的分工

- 写作流程状态回答“现在该做什么”。
- `state-store.md` 回答“第 N 章时故事事实是什么”。
- `追踪/_tracking-state.json` 和派生 Markdown 仍是长篇追踪权威；本协议只决定何时读取它们。

## 失败处理

- 状态文件不存在：从目录结构和追踪文件推断；推断成功后继续。
- 状态字段缺失：补齐能从文件得到的字段，只问无法推断的必需项。
- 状态与产物冲突：正式故事事实以 `正文/` 和追踪事务为准；骨架与候选只能决定流程阶段，不能覆盖事实状态。
- `missing_inputs` 非空：停止进入下一阶段，只报告缺失项和修复动作。
