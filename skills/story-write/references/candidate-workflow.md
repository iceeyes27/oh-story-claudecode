# 候选工作流（Candidate Workflow）

借鉴 narralume「AI 出候选，作者拍板」：候选模式下正文先落到书根 `候选/`，作者显式采用后才并入正稿 `正文/` 并推进追踪。追踪只在采用时推进——`_tracking-state.json` 永远只反映已批准正文。

> **候选目录为何在书根、不在 `正文/` 下**：写后 hook 会把 `正文/` 下（含任意子目录）的 `第N章*.md` 认成正式章节并卷进章节序号 / 追踪欠账门 / gap 检测。候选章按设计尚未提交追踪，若放 `正文/候选/` 会与 hook 冲突。放书根 `候选/` 后 hook 直接跳过候选文件，彻底隔离。

本流程**完全在 SKILL 层编排**：narrative-writer 的输出路径本就是 prompt 参数，追踪事务 JSON 本就由主会话构造。候选模式只是「改输出路径 + 暂存事务不 commit + 增加审批门」，不改 agent 定义、不 bump `agents_version`。

## 何时进入候选模式

- 用户意图含「候选 / 逐章确认 / 先给我看 / 别直接定稿」→ 候选模式。
- 单章写作与「逐章确认」日更适合候选；**纯批量日更**（路由到 `workflow-daily.md`）默认维持直写不变，不强加审批门。
- 候选是 opt-in：未触发时单章写作行为与现状完全一致。

## 目录约定

```
{书名}/
├── 正文/
│   └── 第001章_章名.md          # 正稿（已采用）
└── 候选/                        # 书根，刻意不在 正文/ 之下
    ├── 第002章_章名.md          # 待批准正文
    ├── 第002章_追踪事务.json    # 待回放的追踪事务（主会话构造，不 commit）
    └── _历史/
        └── 第002章_章名_20260821-1530.md   # 被替换/弃用的候选归档
```

## 写作阶段（候选模式）

沿用 SKILL.md Phase 4 单章写作流程的写前准备、模块召回、细纲边界等全部规则，只有两处分支：

1. **step 7 正文执行**：给 narrative-writer 的「输出路径」传 `候选/第{N}章_{章名}.md`（书根候选目录，而不是 `正文/`）。其余 prompt 材料不变。
2. **step 12 更新追踪**：**不执行 `tracking_commit.py commit`**。改为把本该提交的追踪事务 JSON 原样写到 `候选/第{N}章_追踪事务.json` 暂存。事务 JSON 的构造规则与直写模式完全一致（`mode` / `chapter` / `delta` / `context` / `character_snapshots` 等），`expected_state_revision` 可省略，promote 时按当前状态自动刷新。

写后质量网照常：step 10-11 元信息/禁用词扫描与 Phase 5「写后同轮清零」的确定性收尾脚本（`check-ai-patterns.js` / `check-degeneration.js` / `normalize-punctuation.js` / `check-outline-copy.js`）都**作用于候选文件**，blocking 当轮清零后再提示作者审阅。作者看到的必须是已清理文本。

写完不自动进入下一章——候选模式下「审批门」就是天然的串行门：下一章要等本章采用后才写（因为追踪未推进，下一章也读不到本章状态）。这也顺势承接了原「毒句式欠账门」。

## 审批阶段（作者拍板）

作者审阅候选后，用命令行脚本落地决定。工具：`skills/story-write/scripts/candidate-commit.py`（探测 `python3/python/py`）。

| 作者说 | 动作 | 命令 |
|---|---|---|
| 采用第X章 / 这章可以 / 定稿 | 并入正稿 + 回放追踪 + 归档事务 | `candidate-commit.py promote --project {书名} --chapter X` |
| 全部采用 | 按章号升序逐章采用 | `candidate-commit.py promote --project {书名} --all` |
| 重写第X章 更XX | 归档旧候选，随后按新意图重走写作阶段产出新候选 | `candidate-commit.py reject --project {书名} --chapter X --rewrite` |
| 弃用第X章 / 不要这版 | 归档候选，正稿与追踪不动 | `candidate-commit.py reject --project {书名} --chapter X` |
| 有哪些待审 | 列出候选目录待审项 | `candidate-commit.py list --project {书名}` |

**promote 语义**（见脚本内注释）：先过**质量门**，再移动正文到正稿（同盘 rename 原子），再回放追踪事务；回放失败自动把正文移回候选、追踪不推进，修好事务后重跑同一条 promote 即可。promote 拒绝覆盖已存在的正稿（避免误清正文）。

**采用前质量门**（低质量候选进不了正稿）：promote 移动前对候选正文跑现成的 `check-ai-patterns.js` 与 `check-degeneration.js`（`--fail-on=blocking`），blocking 命中即拒绝采用、正稿与追踪不动。这是硬关卡，与写作时 SKILL 写后手动扫描互补（写时给即时反馈、采用时兜底）。豁免同写后 hook：候选标题行下 6 行内加 `<!-- 去味:跳过 -->`，或 `promote --no-scan` 显式绕过。node 或脚本缺失时放行（不误伤）。

**采用后**：正稿出现新章，`tracking_commit.py check` 应通过且 `state_revision` 推进；随后可继续写下一章（回到写作阶段）。

## 与既有机制的关系

- **追踪权威唯一**：promote 复用 `tracking_commit.py`，不另造第二套追踪权威。
- **可逆安全网**：拒绝/替换的候选进 `候选/_历史/` 而非硬删，符合仓库既有「中途快照」安全网理念。
- **日更纯批量不变**：不破坏「不询问是否继续」的串行批量流。

## 非目标（扩展项，当前未实现）

- 日更批量候选 + provisional tracking（多章暂存、全部采用时统一 finalize）。
- 写后 hook 路径覆盖候选目录的跨端 parity（当前靠本流程的主会话手动扫描兜底）。
- `/story dashboard` 候选审阅视图 + 候选/正稿 diff。
- 短篇 mode=short 的候选态。
