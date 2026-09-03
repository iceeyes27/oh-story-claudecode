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
- 数值状态：`_tracking-state.json.metrics: Record<string, {value, as_of_chapter, source_phrase}>`
- 追踪事务：`transaction.metrics` 必填全量快照；无变化也显式提交 `{}`，可选 `metrics_unchanged_reason`
- 流程动作：`write_chapter_skeleton`、`expand_chapter_skeleton`、`review_candidate`
- 候选采用：`python skills/story-write/scripts/candidate-commit.py promote --project DIR --chapter N [--no-scan --reason "<理由>"]`（兼容 `--all` 只接受单候选）
- 候选预检：`python skills/story-write/scripts/candidate-commit.py check --project DIR --chapter N [--json]`
- 候选恢复：`python skills/story-write/scripts/candidate-commit.py recover --project DIR (--chapter N|--all)`
- 作者声纹：`python skills/story-write/scripts/author_voice_profile.py (check|update) --project DIR [--json] [--dry-run]`（`--dry-run` 仅用于 `update`）
- 旧书修订实验：先运行 `python skills/story-write/scripts/quality_lifecycle.py record-experiment-preregistration --project DIR --input FILE` 记录 `story-revision-appeal-preregistration/v1`，再运行同脚本的 `check-revision-appeal-experiment --project DIR --input FILE` 校验 `story-revision-appeal-between-subject/v1`
- 声纹效果实验：先运行 `python skills/story-write/scripts/quality_lifecycle.py record-experiment-preregistration --project DIR --input FILE` 记录 `story-author-voice-effect-preregistration/v1`，再运行同脚本的 `check-author-voice-effect --project DIR --input FILE` 校验 `story-author-voice-effect/v1`

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
- tracking schema 保持 4：旧 state 可缺 `metrics` 且 `check` 不改写；新事务必须提交结构化全量 metrics。每条记录保存原文名目、当前值、事实章号和可在正文定位的来源短语。上下文仍为 7 栏，只在 `## 当前位置` 显示按事实章倒序的前 12 项，超出时报告隐藏数量。
- 候选正文命中共享结算句式而 metrics 无变化时阻断，只有非空 `metrics_unchanged_reason` 可说明本章为何不改数值。变更记录的来源短语必须能在正文定位；数值按“正文直接值”或“前值 + 本章增量”验证，非数值状态只验证来源锚点。
- 确定性扫描通过只表示未发现已登记 blocking 模式，不能表述为文风自然或没有 AI 痕迹。
- 作者声纹工具只递归采样书根 `正文/` 下章号唯一的 UTF-8 正式章节，拒绝符号链接并排除候选、骨架、对标和归档目录。工具只能替换 `设定/文风.md` 中唯一一组 `author-voice:machine` 标记区；标记外作者内容保持原字节，机器统计不得表述为读者偏好提升。
- 旧书局部修订不复用生成实验的被试内 `story-quality-longitudinal/v2`。A/B 必须绑定同一连续 15 章，B 只能修改预注册章，每名真人只读取一个盲码 arm；主要终点固定为 `first_quit_chapter`，secondary 不得事后替换主要终点。
- 旧书 pilot 只能返回 `UNDERPOWERED_PILOT`；powered 结果必须由事前功效设计和固定判定规则推导，且只证明该作品。作者声纹效果实验冻结剧情、模型、上下文、预算和停止规则，只改变 voice treatment；没有非 synthetic 真人证据时只能返回 `PENDING_HUMAN_EVIDENCE`。
- 证据等级不可互换：revision 证书证明修订正确性；单书 pilot 证明流程可行；单书 powered 提供该书效果证据；系统层效果仍要求多个全新 held-out 故事包和功效审计。

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
| 新事务缺 `metrics`、记录形状非法或事实章晚于当前章 | tracking 拒绝，state 与派生视图不变 |
| 正文出现结算句式但 metrics 未变且无理由 | `check` 退出 1，候选、正文与追踪均不变 |
| metrics 来源短语无法定位，或数字既非直接值也非前值加增量 | `check` 退出 1，候选、正文与追踪均不变 |
| 候选绑定为 v1、逻辑项缺失或出现未知 ID | `promote` 退出 2，要求重新生成绑定 |
| evidence 为空、路径不属于读者视图或 anchor 无法定位 | `promote` 退出 2，首次写入前终止 |
| 第 15 章 arc-02 为 blocking 且没有绑定当前结果的作者批准 | `promote` 退出 2；旧结果或正文变化会使批准失效 |
| `--all` 匹配多个候选 | `promote` 退出 2，任何候选均不移动 |
| 采用在任一持久化阶段中断 | 保留采用日志；`recover` 验证摘要和修订号后继续或确认已完成 |
| 声纹标记缺失/重复/倒置，正文空白、重复章号、非法 UTF-8 或含符号链接 | `author_voice_profile.py` 退出 2，`文风.md` 不变 |
| 声纹机器区与当前正式正文不一致 | `check` 退出 1；`update --dry-run` 退出 0 且不写文件 |
| 旧书实验同一 reader 跨 arm、非预注册章变化、主要终点漂移或 synthetic 冒充真人 | 实验校验退出 2，不产生效果结论 |
| pilot 声称 winner，或 powered 缺功效字段/低于自身功效假设 | 实验校验退出 2 |
| 声纹 treatment 条件漂移或缺少真人数据却声称效果通过 | 实验校验退出 2；合法的无真人状态为 `PENDING_HUMAN_EVIDENCE` |

## 5. Good / Base / Bad Cases

- Good：细纲生成书根骨架，作者扩写到书根候选，采用后正文与追踪同时推进。
- Base：写完候选先跑 `check`，通过后仍等待作者决定；普通章节的 v2 绑定只包含三个 rc receipt，第 15 章才增加两个 arc receipt。
- Bad：把候选写入 `正文/候选/`，用未来细纲阻断当前章，或用空 evidence、旧 prose 摘要与 v1 绑定绕过采用检查。
- Good：从正式正文幂等更新声纹机器区；按预注册的被试间 15 章协议导入不可变真人 evidence，再由校验器推导结果。
- Base：声纹工程检查通过但尚无真人数据，效果状态保持 `PENDING_HUMAN_EVIDENCE`；旧书 pilot 只报告可行性与观测分布。
- Bad：采样候选正文生成声纹、把 revision 证书写成留存提升、让同一 reader 读旧书实验两臂，或用 LLM/synthetic 数据替代真人结论。

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
- `python scripts/test-tracking-commit.py`：schema 4 旧 state 兼容、事务必填、结构化记录、7 栏渲染与 12 项显示上限。
- `python scripts/test-candidate-commit.py`：结算无更新阻断、显式理由、直接值与累计增量、来源锚点和采用后上下文。
- `bash scripts/static-check.sh`：Skill 链接、frontmatter 和自包含边界。
- `python scripts/test-author-voice-profile.py`：正式正文限定、作者区字节保护、幂等、只读/dry-run、损坏标记、空样本、非法 UTF-8、重复章号、短证据和符号链接。
- `python scripts/test-quality-lifecycle.py`：旧书被试间实验与声纹效果实验的 preregistration、不可变 arm/human evidence、15 章、单 reader 单 arm、端点冻结、pilot 非结论、powered 功效字段、条件漂移和 `PENDING_HUMAN_EVIDENCE`。

## 7. Wrong vs Correct

```text
Wrong:  候选写入 正文/候选/，用 N+1 之后的细纲计算第 N 章连排，或只在设定文档维护会过期的当前数值。
Correct: 候选写入书根 候选/；第 N 章只检查截至 N 的情绪序列；活数字由 tracking metrics 维护，采用前绑定正文来源，作者明确采用后才同时推进正文与 tracking。

Wrong:  把声纹统计当作吸引力证据，或让旧书局部修订沿用同一读者重复阅读两臂的生成实验。
Correct: 声纹工程结果与真人效果分开；旧书使用预注册的被试间单臂阅读，pilot 不判胜负，缺真人声纹数据时明确保持待验证状态。
```
