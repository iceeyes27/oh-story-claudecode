# 候选工作流（Candidate Workflow）

候选模式下，作者或独立模型扩写的正文先写入书根 `候选/`，作者显式采用后才并入正稿 `正文/` 并推进追踪。追踪只在采用时推进——`_tracking-state.json` 永远只反映已批准正文。

本流程完全在 SKILL 层编排：正文来源可以是作者、独立模型或 narrative-writer；追踪事务始终由主会话根据实际候选正文构造。不改 agent 定义，不提升 `agents_version`。

## 何时进入候选模式

- 章节骨架被作者或独立模型扩写成正文后，进入候选模式。
- 用户明确要求本项目生成“成稿 / 最终正文 / 直接写正文”时，也先生成候选，不直接改正稿与追踪。
- 用户说“候选 / 逐章确认 / 先给我看 / 别直接定稿”时明确进入候选模式。
- 只有明确要求“批量成稿并直接定稿”的兼容指令才使用 `workflow-daily.md` 旧版直写流程。

## 目录约定

```
{书名}/
├── 骨架/第002章_章名.md          # 规划产物（可选但推荐）
├── 候选/
│   ├── 第002章_章名.md           # 待批准正文
│   ├── 第002章_追踪事务.json     # 待回放事务（根据实际正文构造，不 commit）
│   └── _历史/
│       └── 第002章_章名_20260821-1530.md
└── 正文/第001章_章名.md          # 正稿（已采用）
```

## 写作阶段（候选模式）

候选正文必须沿用 SKILL.md Phase 4 的细纲边界；存在章节骨架时，还要逐项核对 `细纲覆盖`。本项目生成成稿时有两项固定分支：

1. **step 7 正文执行**：输出路径传书根 `候选/第{N}章_{章名}.md`，不写 `正文/`。
2. **step 12 更新追踪**：不执行 `tracking_commit.py commit`。主会话通读实际候选正文后，按现有事务 schema（`mode` / `chapter` / `delta` / `context` / `character_snapshots` 等）写入 `候选/第{N}章_追踪事务.json`。事务不得从骨架直接推算；必须保存候选创建时的 `expected_state_revision`，不得在采用时刷新。
3. **绑定采用输入**：事务必须包含 `candidate_binding` v1，记录候选正文、细纲、骨架的项目内相对路径与 SHA-256，`quality_profile` 固定为 `fanqie-long-v1`，`coverage` 逐项覆盖骨架中的全部 O-ID 并写出候选正文证据。任一输入变化后，旧候选必须重新检查并重新生成绑定。

写后检查照常作用于候选文件：骨架/细纲覆盖、连续性、标题、字数，以及 `check-ai-patterns.js`、`check-degeneration.js`、`normalize-punctuation.js`、`check-outline-copy.js`。blocking 当轮修正后再提示作者审阅。确定性扫描通过只说明已登记模式没有阻断项，不能证明文风自然或没有 AI 痕迹。

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

**promote 前检查**：在首次写入前核验项目锁、原始状态修订号、全部绑定摘要、骨架结构与 O-ID 覆盖、章节标题、严格 2200～2800 可见字符、细纲照抄、追踪事务 dry-run，以及 AI 句式和退化扫描。候选不可读、依赖缺失或任一检查失败时拒绝采用。`--no-scan` 或标题后六行内的 `<!-- 去味:跳过 -->` 只跳过 AI 模式扫描，不跳过状态、结构、字数、覆盖与追踪检查。

**promote 语义**（见脚本内注释）：检查通过后创建采用日志，并按 `prepared → prose_moved → tracking_committed → done` 持久化阶段。异常中断后运行 `candidate-commit.py recover --project {书名} --chapter X`；恢复过程按文件摘要与状态修订号判断已经完成的步骤，不覆盖已有正稿，也不重复提交追踪。

**采用后**：正稿出现新章，`tracking_commit.py check` 应通过且 `state_revision` 推进；随后可继续写下一章（回到写作阶段）。

## 与既有机制的关系

- **追踪权威唯一**：promote 复用 `tracking_commit.py`，不另造第二套追踪权威。
- **可恢复采用**：采用日志保存在 `候选/_历史/`；拒绝/替换的候选也归档到该目录，不直接删除。
- **骨架与事实分离**：骨架和候选都不能提前改变追踪；采用后的实际正文才是事实来源。

## Dashboard 候选审批（已实现）

`/story dashboard` 的「候选审批」标签页列出各书 `候选/` 待审项（标注 缺追踪事务 / 正稿冲突），审阅视图把候选正文与 上一章正稿 / 本章细纲 / 本章骨架 并排对照，「采用 / 弃用 / 弃用并重写」按钮通过 `POST /api/candidates/action` 调用本目录的 `candidate-commit.py`。Dashboard 不暴露 `--no-scan`：采用一律过 promote 前确定性质量门（fail-closed），被拒时错误信息原样回显给作者。

## 非目标（扩展项，当前未实现）

- 日更批量候选 + provisional tracking（多章暂存、全部采用时统一 finalize）。
- 写后 Hook 直接处理书根候选（当前由本流程和 promote 前检查处理）。
- Dashboard 内逐行 diff 高亮（当前为并排对照视图）。
- 短篇 mode=short 的候选态。
