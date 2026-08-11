# 统一方案草案

## 共同原则

1. 只修改当前统一入口，不恢复 `story-long-*` / `story-short-*`。
2. 共享行为有一份权威实现或机器可检验的权威契约；平台文件通过既有生成或同步工具更新。
3. 每个工作组先完成定向测试，再执行跨平台检查和仓库本地质量检查；不新增 GitHub Actions。
4. 本任务拆成五个可独立验证的实施组，按“安全守卫 → 数据边界 → 审查状态 → 扫榜契约 → Codex 一致性”的顺序实施。

## A. Claude Bash 正文守卫（R1）

- 在共享 `story_hook_core.js` 中保留 Bash 正文目标解析的唯一主实现，Claude 的 `story_hook_cli.js` 增加“从完整 hook 事件提取全部正文目标”和“逐目标写后检查”接口。
- `settings-hooks.json` 的正文前置和写后 matcher 均加入 `Bash`，并为 `PostToolUseFailure:Bash` 注册同一写后检查；提交检查仍是独立 hook，不合并职责。
- `guard-outline-before-prose.sh` 与 `check-prose-after-write.sh` 支持多目标；Node 可用时统一调用共享解析。无 Node 时，前置守卫保留有限 Shell 兼容，仅识别已声明的重定向、追加、`tee`、`touch`、`cp`、`mv`；间接执行任意脚本无法静态保证识别，文档不得写成全覆盖。写后检查继续明确依赖 Node，并由 session-start 报告依赖缺失。
- 写后检查在 `PostToolUse` 和 `PostToolUseFailure` 均固定返回 exit 0，以事件对应的 `additionalContext` 报告结果；它只能提示修复，不能撤销已经发生的写入。失败命令已部分写入正文时仍检查现存目标并明确提示“命令失败但文件可能已改变”。
- 回归覆盖首次创建、覆盖、追加、复制、移动、多目标、带空格/中文/Windows 路径、只读命令、间接脚本限制，以及“先写文件再返回非零”的失败命令；必须通过真实 Claude settings 注册调用前置、成功/失败事件和写后 hook，不能只测 helper。

依据：Claude Code 官方 Hook 文档明确区分成功后的 `PostToolUse` 与失败后的 `PostToolUseFailure`，并说明写后 hook 不能撤销工具已经产生的副作用：<https://code.claude.com/docs/en/hooks>。

## B. 唯一章节边界（R2）

- `_progress.md` 章节边界契约升为 schema v3，增加原文相对路径、字节数和 SHA-256；章节表继续保存章号、标题、起始行、字数。
- 新增 story-analyze 自有边界校验器：校验 schema、来源指纹、章号唯一且连续、起始行严格递增、行号在原文范围内。Stage 1/2/6 在读取切片前都调用同一校验器。
- Stage 6 删除 Grep 原文、调整正则和自行重新识别章节的分支，只按表中行号取样；表缺失、损坏或原文指纹变化时停止并要求重建 Stage 0。
- schema v1/v2 统一通过 Stage 0 子步骤重建为 v3，不在 Stage 6 临时迁移。
- 静态契约测试锁定 Stage 6 禁止重新切片，运行测试覆盖有效表、重复/缺号/倒序/越界、原文变化和旧 schema。

## C. 跨批 findings 状态（R3）

- 固定路径为 `{书目录}/.story-review/latest.json`，由 `story-review/scripts/review-state.js` 独占读写；不进入 `追踪/`，不修改正文、设定或大纲。
- schema v1 至少包含：`schema_version`、`state_revision`、`review_id`、`effective_mode`、`status`、书目相对路径、批次 ID/范围/输入文件摘要、已完成批次、开放 findings、受影响的已审范围、更新时间。
- full/lean 由主会话在每批综合完成后以 `expected_state_revision` 比较更新，并采用同目录临时文件 + 原子替换；同一批次 ID 重跑为幂等更新，旧 revision 或并发写入直接失败。损坏文件停止继承并报告，不静默覆盖。
- 真正的比较更新使用确定性申领文件：写入前以独占创建（Node `open` 的 `wx`，对应 `O_CREAT|O_EXCL`）申领 `{书目录}/.story-review/.cas-{expected_state_revision + 1}`，内容记录 schema、目标 revision、review_id、进程、主机、创建时间和随机 claim_id；同一目标 revision 只能有一个写入者成功。申领成功后重新读取 `latest.json` 并校验 expected revision，再原子替换；完成或失败时只删除本次 claim_id 对应的申领文件。申领已存在时立即报告冲突，不等待、不覆盖、不自动删除。
- solo 和用户明确指定的只读审查只读取已有状态，不创建或更新状态；报告明确说明 solo 本次新增开放项不能供新会话恢复。此限制保留当前只读契约。
- 写入工具只清理自己本次创建且 claim_id 匹配的临时文件与申领文件；不在启动时清理其他文件。异常退出遗留项由状态检查报告但不自动删除。显式 `release-claim` 维护命令必须同时匹配 claim_id、目标 revision 与 `latest.json` 当前 revision，并要求操作者确认对应写入者已停止；不满足任一条件就拒绝。solo/显式只读模式绝不创建、更新或删除状态、临时或申领文件。
- `status=active` 时不同 `review_id` 必须失败，只能恢复当前任务或用带 `expected_state_revision` 的显式 reset；不得直接覆盖未完成 findings。`status=completed` 后才允许初始化下一任务。只保留一个 `latest.json`，不生成无限历史文件。输入文件摘要变化时，相关旧 finding 标为 `needs_revalidation`，不得当成当前事实直接继承。
- 测试覆盖新建、恢复、幂等重跑、revision 冲突、损坏 JSON、内容变化、完成后新任务、solo/显式只读不写。

## D. 扫榜统一契约（R4-R6）

- 新增 `story-scan/scripts/scan-contract.js`，统一：完整 CLI 解析、100 个 Unicode 字符的简介截断、单次 `Date` 快照生成本地日期和带时区抓取时间、字段质量标记。
- CLI 统一拒绝未知参数、重复参数、缺值、空值、把后续 flag 当作值和意外位置参数；`port` 仅允许 1-65535，`top` 与 `detail-limit` 仅允许 1-100。四个平台再分别校验：番茄 channel/type，七猫 channel/type/period，晋江榜型及数字频道，起点 type/mode/detail。所有失败都必须发生在浏览器/网络访问、目录创建和文件写入之前，并以非零状态列出问题与合法值。
- 起点 mobile-ssr 与 cdp-pc 的逐书机器 schema 固定为：`rank`、`title`、`author`、`genre`、`status`、`contractStatus`、`chargeMode`、`wordCount`、`totalRecommend`、`tags`、`latestUpdate`、`url`、`description`、`missing_fields`。两种来源必须输出全部 key；值不可获得时使用 `null` 并写入 `missing_fields` 与文件头质量摘要，不用空字符串伪装完整。
- 七猫仅大热榜具有周期维度：`--period day|month|all`，默认 `day`；非大热榜显式传 period 直接失败。`--type all` 时按 period 采大热榜，其他榜型各采一次。点击周期页签后验证实际激活状态，未激活则该目标失败。日榜/月榜必须同时写入标题、文件头和文件名，避免同日覆盖。
- 每个采集目标只创建一次时间快照，并同时传给 Markdown 渲染和文件命名；简介均通过共享截断函数。网络回归使用现有 fake agent-browser，不依赖实时站点。
- 测试覆盖两种起点来源的字段归一化与缺失质量、七猫日/月切换及 `all` 组合、四平台非法参数、中文/emoji 截断、UTC 跨日本地时间一致性和文件名不覆盖。

## E. Codex 与目录发现一致性（R7-R8）

- 新增机器可读的书目发现契约，精确定义：标记文件或目录距项目根最多 4 层；跳过所有点目录、`.git`、`node_modules` 和符号链接；显式 `.active-book` 仍优先，但必须解析到项目根内的真实目录。
- JS、Bash、Python 均读取部署到各自 hook 目录的同一生成契约；源契约只有一份，平台副本由 story-setup 的同步步骤产生。当前书发现与全部书发现使用同一深度语义。
- Python 删除 `**` glob，改为不跟随符号链接的有界遍历；JS 修正当前 `findFirst(root, 4)` 与全部书 `walk(root, 8)` 的层级差异；Bash `find` 增加 prune 条件。
- `target_cli` 读取后按逗号拆分、去空白、去除空 token，再精确判断 `codex`；字段缺失、空值和重复字段按无效部署标记处理。
- 测试覆盖第 3/4/5 层、巨大 `node_modules`、点目录、`.git`、符号链接、越界 `.active-book`，以及 `codex`、多目标、`opencode`、空白、空值、缺失和重复 `target_cli`。

## 实施与验证顺序

1. 每组先提交权威契约/实现与定向测试，完成该组验证后再进入下一组。
2. 共享核心或部署模板变化后运行既有同步/生成脚本，检查生成差异只包含预期平台副本。
3. 定向测试：Claude 部署/正文写后、story-analyze 边界、story-review 状态、scan runtime、Codex hooks。
4. 跨平台检查：shared files、hook regex parity、Claude/Codex/OpenCode/ZCode/story-setup adapter。
5. 仓库检查：static check、static-check tests、current skill contracts、Python invocation、AI patterns；全部本地执行。
6. 每组保持独立提交点；某组失败时只撤销该组，不改动已验证组。
