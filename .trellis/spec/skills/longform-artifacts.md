# Long-form Chapter Artifacts

## 1. Scope / Trigger

修改 `story-write long` 的章节路由、章节发现、骨架验证或候选采用时使用本规范。目标是防止规划内容或待审正文被识别为已采用故事事实。

## 2. Signatures

- 骨架：`{书名}/骨架/第NNN章_章名.md`
- 候选：`{书名}/候选/第NNN章_章名.md`
- 正稿：`{书名}/正文/**/第NNN章_章名.md`
- 骨架验证：`node skills/story-write/scripts/check-chapter-skeleton.js [--dir DIR] [--from N] [--to N] [--json] [files...]`
- 流程动作：`write_chapter_skeleton`、`expand_chapter_skeleton`、`review_candidate`
- 候选采用：`python skills/story-write/scripts/candidate-commit.py promote --project DIR --chapter N [--no-scan --reason "<理由>"]`（兼容 `--all` 只接受单候选）
- 候选恢复：`python skills/story-write/scripts/candidate-commit.py recover --project DIR (--chapter N|--all)`

## 3. Contracts

- 长篇“写第 N 章 / 续写 / 继续写 / 日更”默认生成骨架；只有明确要求成稿时生成候选。
- `骨架/` 与 `候选/` 必须位于书根，不能放在 `正文/` 下。章节发现只能用 `正文/` 正稿推进正式章号。
- 骨架和候选都不能推进 `_tracking-state.json`。候选追踪事务必须根据实际候选正文构造，不能从骨架直接推算。
- 候选事务必须保留创建时的 `expected_state_revision`，并以 SHA-256 绑定候选、细纲、骨架及 O-ID 覆盖证据；采用时不得刷新旧修订号。
- 候选绑定必须使用 `candidate_binding.schema_version = 2` 与 `quality_profile = fanqie-long-v2`。每章必须包含 `rc-01`、`rc-02`、`rc-03`；只有第 15 章增加 `arc-01`、`arc-02`，其他章号不按倍数触发 arc 门。
- `rc-01/02/03` 与 `arc-01` 的语义 receipt 必须包含 `run_id`、`status`、`findings`、非空 `evidence`、`candidate_sha256`、逐文件 `prose_files` 和 `prose_set_sha256`。每个 evidence 路径必须属于 `prose_files`，其非空 anchor 必须能在对应文件中直接定位；`rc-01` 另存确定性结果摘要，第 15 章的两个 arc receipt 绑定同一 ledger 摘要。
- `promote` 通过项目锁串行执行，按 `prepared → prose_moved → tracking_committed → done` 记录阶段；失败或中断后用 `recover` 幂等恢复。恢复在移动正文或回放追踪前重验原始事务、逐文件读者视图摘要和文件集合摘要。
- `promote` 在首次写入前执行状态、摘要、骨架、覆盖、标题、严格字数、细纲照抄、追踪 dry-run 与 AI 模式检查。只有 `--no-scan --reason "<理由>"` 能跳过 AI 模式扫描，理由写进采用回执；正文内的 `<!-- 去味:跳过 -->` 对采用无效。
- 确定性扫描通过只表示未发现已登记 blocking 模式，不能表述为文风自然或没有 AI 痕迹。

## 4. Validation & Error Matrix

| 条件 | 结果 |
| --- | --- |
| 骨架缺少必需节、字段、覆盖或预算不一致 | 验证器退出 1 并输出文件级 finding |
| 骨架参数错误、文件不存在或不可读 | 验证器退出 2 |
| 书根骨架或候选存在 | 正式章号不变，流程进入对应待处理动作 |
| 历史 `正文/候选/` 存在 | 章节发现忽略该目录，不自动迁移 |
| 候选缺追踪事务、扫描失败或正稿已存在 | `promote` 退出 2，正稿与追踪不变 |
| 候选绑定为 v1、逻辑项缺失或出现未知 ID | `promote` 退出 2，要求重新生成绑定 |
| evidence 为空、路径不属于读者视图或 anchor 无法定位 | `promote` 退出 2，首次写入前终止 |
| 第 15 章 arc-02 为 blocking 且没有绑定当前结果的作者批准 | `promote` 退出 2；旧结果或正文变化会使批准失效 |
| `--all` 匹配多个候选 | `promote` 退出 2，任何候选均不移动 |
| 采用在任一持久化阶段中断 | 保留采用日志；`recover` 验证摘要和修订号后继续或确认已完成 |

## 5. Good / Base / Bad Cases

- Good：细纲生成书根骨架，作者扩写到书根候选，采用后正文与追踪同时推进。
- Base：普通章节的 v2 绑定只包含三个 rc receipt；第 15 章才增加两个 arc receipt。
- Bad：把候选写入 `正文/候选/`，或用空 evidence、旧 prose 摘要与 v1 绑定绕过采用检查。

## 6. Tests Required

- `node scripts/test-chapter-skeleton.js`：正常骨架、缺字段、场景越界、预算、覆盖、文件错误和提示项。
- `bash scripts/test-flow-state.sh`：无骨架、骨架待扩写、候选待审、正式章号、历史候选目录与旧动作兼容。
- `python scripts/test-candidate-commit.py`：书根候选、完整预检、语义证据锚点、状态过期、批量拒绝、三阶段故障注入与幂等恢复。
- `bash scripts/static-check.sh`：Skill 链接、frontmatter 和自包含边界。

## 7. Wrong vs Correct

```text
Wrong:  候选写入 正文/候选/，用报告结论代替读者视图摘要，生成后立即更新 tracking。
Correct: 候选写入书根 候选/，用 v2 receipt 绑定实际读取文件与证据锚点，采用成功后才进入 正文/ 并更新 tracking。
```
