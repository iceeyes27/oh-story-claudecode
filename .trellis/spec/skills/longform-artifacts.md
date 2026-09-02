# Long-form Chapter Artifacts

## 1. Scope / Trigger

修改 `story-write long` 的章节路由、章节发现、骨架验证或候选采用时使用本规范。目标是防止规划内容或待审正文被识别为已采用故事事实。

## 2. Signatures

- 骨架：`{书名}/骨架/第NNN章_章名.md`
- 候选：`{书名}/候选/第NNN章_章名.md`
- 正稿：`{书名}/正文/**/第NNN章_章名.md`
- 骨架验证：`node skills/story-write/scripts/check-chapter-skeleton.js [--dir DIR] [--from N] [--to N] [--json] [files...]`
- 情绪连排：`node skills/_shared/scripts/check-emotion-run.js --json --project DIR [--chapter N]`
- 细纲因果：`python skills/story-write/scripts/check-outline-causal.py DIR --json --strict --from=N --to=N`
- 专名漂移：`node skills/_shared/scripts/check-name-drift.js --json --project DIR [--chapter N] [--fail-on=blocking]`
- 流程动作：`write_chapter_skeleton`、`expand_chapter_skeleton`、`review_candidate`
- 候选采用：`python skills/story-write/scripts/candidate-commit.py promote --project DIR --chapter N [--no-scan --reason "<理由>"]`（兼容 `--all` 只接受单候选）
- 候选预检：`python skills/story-write/scripts/candidate-commit.py check --project DIR --chapter N [--json]`
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
- `check` 与 `promote` 复用 `validate_binding`；`check` 不获取项目锁、不移动候选、不写采用日志或追踪状态。`imported_through_chapter` 之后的新章缺任一 INTENT_FIELDS 时阻断，历史章只输出 advisory。
- `目标情绪` 只取 `skills/_shared/references/target-emotion-vocab.md` 的首个词；词表外取值对新章 blocking、历史章 advisory。连排 3 章为 advisory、4 章为 blocking；传 `--chapter N` 时只读取 `N` 及以前的细纲，不得用未来章节阻断当前章。
- `check` 与 `promote` 对本章运行严格因果检查，只传相同的 `--from=N --to=N`；新章 blocking，`imported_through_chapter` 内的历史章 advisory。不得为写第 N 章扫描整本书的历史因果欠账。
- 专名漂移扫描只读共享现实平台/产品词典及项目 `设定/题材定位.md` 的 `保留真名`；扫描正文、候选与细纲，不扫描设定正文。现实专名对新章 blocking、历史章 advisory；从角色设定、角色快照和追踪状态运行时派生的 3～4 字人名，单字替换近似只作 advisory。正文卷目录必须递归发现。
- 确定性扫描通过只表示未发现已登记 blocking 模式，不能表述为文风自然或没有 AI 痕迹。

## 4. Validation & Error Matrix

| 条件 | 结果 |
| --- | --- |
| 骨架缺少必需节、字段、覆盖或预算不一致 | 验证器退出 1 并输出文件级 finding |
| 骨架参数错误、文件不存在或不可读 | 验证器退出 2 |
| 书根骨架或候选存在 | 正式章号不变，流程进入对应待处理动作 |
| 历史 `正文/候选/` 存在 | 章节发现忽略该目录，不自动迁移 |
| 候选缺追踪事务、扫描失败或正稿已存在 | `promote` 退出 2，正稿与追踪不变 |
| `check` 发现候选预检 blocking | 退出 1，候选、正文与追踪均不变 |
| `check` 调用错误、文件不可读或运行环境故障 | 退出 2，候选、正文与追踪均不变 |
| 当前章形成 4 章同目标情绪连排 | 新章 `check` 退出 1；历史章只输出 advisory |
| 仅未来章会把连排推到 4 章 | 当前章不受未来细纲影响 |
| 新章本章因果字段缺失或前因无锚点 | `check` 退出 1；候选、正文与追踪均不变 |
| 历史章存在严格因果 finding | 输出 advisory，继续其余采用预检 |
| 新章出现未声明现实平台/产品名 | `check` 退出 1；候选、正文与追踪均不变 |
| 历史章现实专名或新章疑似单字人名漂移 | 输出 advisory，继续其余采用预检 |
| 候选绑定为 v1、逻辑项缺失或出现未知 ID | `promote` 退出 2，要求重新生成绑定 |
| evidence 为空、路径不属于读者视图或 anchor 无法定位 | `promote` 退出 2，首次写入前终止 |
| 第 15 章 arc-02 为 blocking 且没有绑定当前结果的作者批准 | `promote` 退出 2；旧结果或正文变化会使批准失效 |
| `--all` 匹配多个候选 | `promote` 退出 2，任何候选均不移动 |
| 采用在任一持久化阶段中断 | 保留采用日志；`recover` 验证摘要和修订号后继续或确认已完成 |

## 5. Good / Base / Bad Cases

- Good：细纲生成书根骨架，作者扩写到书根候选，采用后正文与追踪同时推进。
- Base：写完候选先跑 `check`，通过后仍等待作者决定；普通章节的 v2 绑定只包含三个 rc receipt，第 15 章才增加两个 arc receipt。
- Bad：把候选写入 `正文/候选/`，用未来细纲阻断当前章，或用空 evidence、旧 prose 摘要与 v1 绑定绕过采用检查。

## 6. Tests Required

- `node scripts/test-chapter-skeleton.js`：正常骨架、缺字段、场景越界、预算、覆盖、文件错误和提示项。
- `bash scripts/test-flow-state.sh`：无骨架、骨架待扩写、候选待审、正式章号、历史候选目录与旧动作兼容。
- `python scripts/test-candidate-commit.py`：书根候选、`check` 只读保证、新章/历史章细纲分级、完整预检、语义证据锚点、状态过期、批量拒绝、三阶段故障注入与幂等恢复。
- `node scripts/test-emotion-run.js`：第 2 章无 finding、第 4 章仅 3 连 advisory、第 5 章 4 连 blocking，并证明未来细纲不影响当前章。
- `node --test scripts/test-outline-contract.js`：闭合词表合法值通过、非法值命中 `outline.emotion-vocab`。
- `python scripts/test-outline-causal.py`：严格/非严格、缺字段、悬空事件、章节范围与退出码。
- `python scripts/test-candidate-commit.py`：新章因果 finding 阻断、历史章 advisory、未来坏细纲不影响当前章。
- `node scripts/test-name-drift.js`：共享词典、项目白名单、设定豁免、卷目录发现、3～4 字人名单字替换 advisory 与错误退出码。
- `python scripts/test-candidate-commit.py`：新章现实专名阻断、历史章现实专名 advisory、人名近似不阻断。
- `bash scripts/static-check.sh`：Skill 链接、frontmatter 和自包含边界。

## 7. Wrong vs Correct

```text
Wrong:  候选写入 正文/候选/，用 N+1 之后的细纲计算第 N 章连排，或把 check 通过当成作者已采用。
Correct: 候选写入书根 候选/；第 N 章只检查截至 N 的情绪序列；作者明确采用并通过 promote 后才进入 正文/ 并更新 tracking。
```
