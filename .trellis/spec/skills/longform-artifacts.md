# Long-form Chapter Artifacts

## 1. Scope / Trigger

修改 `story-write long` 的章节路由、章节发现、骨架验证或候选采用时使用本规范。目标是防止规划内容或待审正文被识别为已采用故事事实。

## 2. Signatures

- 骨架：`{书名}/骨架/第NNN章_章名.md`
- 候选：`{书名}/候选/第NNN章_章名.md`
- 正稿：`{书名}/正文/**/第NNN章_章名.md`
- 骨架验证：`node skills/story-write/scripts/check-chapter-skeleton.js [--dir DIR] [--from N] [--to N] [--json] [files...]`
- 流程动作：`write_chapter_skeleton`、`expand_chapter_skeleton`、`review_candidate`
- 候选采用：`python skills/story-write/scripts/candidate-commit.py promote --project DIR (--chapter N|--all) [--no-scan]`
- 候选恢复：`python skills/story-write/scripts/candidate-commit.py recover --project DIR (--chapter N|--all)`

## 3. Contracts

- 长篇“写第 N 章 / 续写 / 继续写 / 日更”默认生成骨架；只有明确要求成稿时生成候选。
- `骨架/` 与 `候选/` 必须位于书根，不能放在 `正文/` 下。章节发现只能用 `正文/` 正稿推进正式章号。
- 骨架和候选都不能推进 `_tracking-state.json`。候选追踪事务必须根据实际候选正文构造，不能从骨架直接推算。
- 候选事务必须保留创建时的 `expected_state_revision`，并以 SHA-256 绑定候选、细纲、骨架及 O-ID 覆盖证据；采用时不得刷新旧修订号。
- `promote` 通过项目锁串行执行，按 `prepared → prose_moved → tracking_committed → done` 记录阶段；失败或中断后用 `recover` 幂等恢复。
- `promote` 在首次写入前执行状态、摘要、骨架、覆盖、标题、严格字数、细纲照抄、追踪 dry-run 与 AI 模式检查。`--no-scan` 或 `<!-- 去味:跳过 -->` 只能跳过 AI 模式扫描。
- 确定性扫描通过只表示未发现已登记 blocking 模式，不能表述为文风自然或没有 AI 痕迹。

## 4. Validation & Error Matrix

| 条件 | 结果 |
| --- | --- |
| 骨架缺少必需节、字段、覆盖或预算不一致 | 验证器退出 1 并输出文件级 finding |
| 骨架参数错误、文件不存在或不可读 | 验证器退出 2 |
| 书根骨架或候选存在 | 正式章号不变，流程进入对应待处理动作 |
| 历史 `正文/候选/` 存在 | 章节发现忽略该目录，不自动迁移 |
| 候选缺追踪事务、扫描失败或正稿已存在 | `promote` 退出 2，正稿与追踪不变 |
| 采用在任一持久化阶段中断 | 保留采用日志；`recover` 验证摘要和修订号后继续或确认已完成 |

## 5. Good / Base / Bad Cases

- Good：细纲生成书根骨架，作者扩写到书根候选，采用后正文与追踪同时推进。
- Base：只有细纲时，`flow-state.js` 返回 `write_chapter_skeleton`，不创建正稿。
- Bad：把候选写入 `正文/候选/`，递归扫描会误判为正式章节。

## 6. Tests Required

- `node scripts/test-chapter-skeleton.js`：正常骨架、缺字段、场景越界、预算、覆盖、文件错误和提示项。
- `bash scripts/test-flow-state.sh`：无骨架、骨架待扩写、候选待审、正式章号、历史候选目录与旧动作兼容。
- `python scripts/test-candidate-commit.py`：书根候选、完整预检、状态过期、三阶段故障注入与幂等恢复。
- `bash scripts/static-check.sh`：Skill 链接、frontmatter 和自包含边界。

## 7. Wrong vs Correct

```text
Wrong:  候选写入 正文/候选/，生成后立即更新 tracking。
Correct: 候选写入书根 候选/，采用成功后才进入 正文/ 并更新 tracking。
```
