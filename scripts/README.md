# scripts/ —— 仓库开发脚本索引

这些是开发本仓库（skill 套件本体）用的**守卫 / 测试 / 代码生成**脚本，**不是** skill 运行时脚本（运行时脚本在各 skill 自己的 `scripts/` 下，如 `story-deslop/scripts/check-ai-patterns.js`，跨 skill 字节同步）。

- 本 fork 不使用 GitHub Actions；提交前本地检查命令见 [CONTRIBUTING.md](../CONTRIBUTING.md)「本地检查」。
- **改名 / 移动任一脚本**，要同步改 `CONTRIBUTING.md`、本文件，以及调用它的兄弟脚本（见下方「何时跑」里的调用关系）。

## 静态守卫（check-*）

| 脚本 | 检查什么 | 何时跑 |
|---|---|---|
| `static-check.sh` + `static-check.py` | 结构化验证 frontmatter、Markdown 路径/锚点、Agent 引用、references 可达性；除基础组件 `browser-cdp` 外禁止跨 Skill 文件引用 | 提交前本地 |
| `check-doc-budget.sh` + `doc-budget.json` | 热路径文档字符预算（去空白字符数），防 skill/agent 模板无声膨胀；超预算需显式调高并说明理由 | 改动登记文件后本地；提交前本地 |
| `skill-numbering.py check` | 工作流 Step/Phase/Stage 编号策略、引用绑定、SKILL.md 裸编号/子步骤小数守卫 | 提交前本地；改工作流结构后 |
| `check-current-skill-contracts.sh` + `.py` + `current-contract.json` | 从结构化 manifest 校验当前版本、Phase、schema、主产物、细纲契约与 GitHub Actions 禁用策略；保留 legacy/path 守卫并拦截缺主产物后的静默替代 | 提交前本地 |
| `check-unified-skill-upstream-drift.py` + `upstream-integration.json` | 固定上游基线并检查 split skill 到 unified skill 的人工迁移义务；`--report` 只读输出 source -> target 清单 | 上游同步后；提交前本地 |
| `check-shared-files.sh` | Shared File Governance Check：依次跑 `sync-shared-assets.py check`、`shared-references.py check`、`check-reference-similarity.py`、`check-agent-reference-consumers.py`、`check-short-analysis-scope.py` 五个 guard | `shared-assets`（affected + release） |
| `check-scan-runtime-policy.sh` | scraper 输出文件名依赖本地日期 helper；CDP 探测/Windows 监听解析的源码策略 | 提交前本地；这些依赖方向无法由隔离 helper 测试证明 |
| `check-story-setup-deployment.sh` | story-setup 部署/运行时回归（慢，>2min） | story-setup 改动后本地 |
| `check-hook-regex-sync.sh` | 5 份 hook 核正则同步 | `hook-regex-sync`（release） |
| `check-hook-locale-safety.sh` | 部署 hook 在 Windows 中文 GBK 区域的字节安全（静态守卫；行为回归见 `test-hook-encoding-portable.sh`） | `hook-locale-safety`（release） |
| `check-antigravity-adapter.sh` | Antigravity 适配层 + 内部跑 3 个 antigravity `test-*` | `antigravity-adapter`（release） |
| `check-python-invocation.sh` | 技能文档禁止裸调 `python3`（须 python3→python→py 探测） | 提交前本地 |
| `check-doc-budget.sh` + `doc-budget.json` | 校验每次会话或每章加载的热路径文档没有超过显式预算 | 修改 Skill 入口与写作热路径后 |
| `platform-skill-set.json` | 跨平台公开发布 Skill 的唯一清单；Claude、OpenCode、ZCode 与 OpenClaw 校验共用 | 增减公开 Skill 时先修改 |
| `local-only-skill-set.json` | 不进入跨平台公开部署的 Skill 及原因；与公开清单的并集必须覆盖仓库全部 Skill | 新增或改变 Skill 发布范围时修改 |
| `sync-upstream.js` | 在专用 worktree 中固定双方 SHA，按策略分类、记录审阅决定、验证并生成双亲 merge commit；不改调用者工作区 | 同步上游时运行 |
| `platform-capabilities.json` + `check-platform-capabilities.mjs` | 平台能力、降级行为、Windows 启动方式与公开 Skill 完整性 | 平台适配改动后 |
| `quality-gate.json` + `quality-gate.mjs` | `fast` / `affected` / `release` 本地质量配置与 JSON 报告 | 改动后或发布前 |
| `release-manifest.json` + `check-release-manifest.mjs` | 发布身份、上游基线与权威资产摘要 | 发布前 |
| `check-claude-adapter.sh` | Claude marketplace 与公开 Skill 清单的一一映射；可选真实 CLI strict validate | 本地静态；`CLAUDE_REAL_CHECK=1`（真实 CLI） |
| `check-opencode-adapter.sh` | OpenCode 适配层同步 + commands/agents/config 结构 + plugin 行为回归 | 本地（调 sync-opencode.py） |
| `check-openclaw-skills.sh` | OpenClaw AgentSkills/frontmatter 兼容性 | 本地 |
| `check-codex-adapter.sh` | Codex 适配层：repo skills symlink、agent TOML、hooks 与跨平台 launcher | 本地（调 generate-codex-agents.py 验生成确定性） |
| `check-zcode-adapter.sh` | ZCode plugin/marketplace、Skills/Commands/Hooks 与部署锚点 | 本地 |
| `check-reasonix-adapter.sh` | Reasonix plugin manifest、公开 Skill 清单和 AGENTS 路由名一致性 | 本地 |

## 测试回归（test-*）

`scripts/test-*` 必须被 `quality-gate.json` 的某个 profile 跑到（直接引用、聚合 runner 或适配器内部调用都算）。注释/文档里出现的名字不算运行时引用。新增 `test-*` 不接线会让 `scripts/quality-gate.test.mjs` 在 `platform-gates` 红掉。`fast` 的 check 集保持原样，不承担这张回归网。

聚合 runner（沿用 `test-story-continuity.sh` 可调其他 test 的先例）：

| runner | quality-gate check | profile |
|---|---|---|
| `test-language-gates.sh` | `language-gates` | affected + release |
| `test-narrative-gates.sh` | `narrative-gates` | release |
| `test-platform-gates.sh` | `platform-gates` | release |

| 脚本 | 测什么 | 归属 |
|---|---|---|
| `test-ai-patterns.sh` | 确定性 AI 句式检测器 `check-ai-patterns.js` 回归 | `language-gates` |
| `test-degeneration.sh` | 模型退化检测器 `check-degeneration.js` 回归 | `language-gates` |
| `test-prose-policy.py` | 写作策略守卫：全局规则冲突 + detector blocking 仅允许 `banned-word-*` / `rule-load-error` | `language-gates` |
| `test-normalize-punctuation.js` | 标点归一化的只读检查、frontmatter/fence、CRLF、引号模式与幂等性 | `language-gates` |
| `test-charcount-portable.sh` | 跨平台字符统计命令在三平台 + Windows 的正确性 | `language-gates` |
| `test-prose-backstop-hook.sh` | `check-prose-after-write.sh` 回归 | `language-gates` |
| `test-prose-net-parity.sh` | 正文后置「轻量确定性网」Claude/OpenCode/Codex/ZCode parity | `language-gates` |
| `test-chapter-titles.js` | 章节标题设问规则回归：明确疑问形态 blocking、悬念式疑问词开头 advisory | `contracts`（fast/affected/release） |
| `test-narrative-complexity.js` | 平直叙事模式契约 | `contracts` |
| `test-foreshadow-overdue.js` | 逾期伏笔门 | `contracts` |
| `test-foreshadow-gate.js` | 伏笔热卡/欠账门 | `contracts` |
| `test-candidate-commit.py` | 候选采用事务：预检、语义证据、状态过期、故障注入与幂等恢复 | `candidate-transaction`（fast/affected/release） |
| `test-tracking-commit.py` | 单权威追踪行为：state 最后提交、失败同事务重跑、派生一致性、修订语义、导入截止章 | `tracking`（affected/release） |
| `test-tracking-workflow-contracts.py` | 追踪工作流契约 | `tracking-workflow`（affected/release） |
| `test-chapter-skeleton.js` | 章节骨架验证器 | `chapter-skeleton`（affected/release） |
| `test-unified-skill-upstream-drift.py` | 上游旧拆分目录变化时，迁移检查会显示统一目标路径，并验证 `--report` 只读返回成功 | `sync-drift`（fast/affected/release） |
| `test-outline-causal.py` | 细纲因果链 | `narrative-gates` |
| `test-outline-contract.js` | 细纲读者体验契约 | `narrative-gates` |
| `test-emotion-run.js` | 目标情绪闭合词表连排：3 章 advisory / 4 章 blocking | `narrative-gates` |
| `test-name-drift.js` | 现实专名漂移：demo 抖音 blocking，微博/东风/知乎/设定 gloss 不误杀 | `narrative-gates` |
| `test-outline-copy.sh` | 细纲照抄门 | `narrative-gates` |
| `test-phase2-contract.js` | Phase 2 契约 | `narrative-gates` |
| `test-delivery-contract.js` | 交付契约 | `narrative-gates` |
| `test-scan-contract.js` | 扫榜契约 | `narrative-gates` |
| `test-scan-runtime.js` | CDP argv 边界/报错/JSON 契约与 7 个 scraper 无副作用 import | `narrative-gates` |
| `test-scan-runtime-policy.py` | 变异验证 scan/browser 静态策略不会被无关或死代码关键词骗过 | `narrative-gates` |
| `test-review-state.js` | 审查状态 | `narrative-gates` |
| `test-story-continuity.sh` | `detect-story-gaps.sh` 跨批连续性后置回归 | `narrative-gates` |
| `test-chapter-completion-lifecycle.py` | 章节完成生命周期 | `narrative-gates` |
| `test-longform-stability.sh` | 长篇稳定性工具链回归 | `narrative-gates` |
| `test-state-store.sh` | 结构化状态库回归 | `narrative-gates` |
| `test-author-memory-commit.py` | 工作区作者记忆行为 | `narrative-gates` |
| `test-flow-state.sh` | `story-write` 写作阶段披露状态工具回归 | `narrative-gates` |
| `test-zcode-hooks.sh` | ZCode 严格 JSON Hook、正文守卫与连续性回归 | `platform-gates` |
| `test-codex-hooks.sh` | Codex hook 合成 stdin/stdout 契约 | `platform-gates` |
| `test-reasonix-adapter.sh` | Reasonix AGENTS 路由表拒绝已废弃的 split Skill 名称 | `platform-gates` |
| `test-skill-numbering.sh` | Step 重排级联安全、锚点 fail-closed、代码块引用、验证零写入/提交回滚、dry-run/write/幂等性 | `platform-gates` |
| `test-storyctl.py` | storyctl 回归 | `platform-gates` |
| `test-current-skill-contracts.py` | current-contract manifest 类型/固定值与主产物 fail-fast 语义 fixture | `platform-gates` |
| `test-shared-assets.py` | 共享资产 manifest 的 drift、sync、路径越界、basename 单一 owner 与未登记重复检测 | `platform-gates` |
| `test-shared-references.py` | 共享 reference 组登记 | `platform-gates` |
| `test-static-check.py` | 真 frontmatter block、精确路径/锚点、跨 Skill 引用、fence、死 reference、Agent 与章节链接 fixture | `platform-gates` |
| `test-hook-encoding-portable.sh` | 部署 hook 在 Windows 中文系统的编码健壮性 | `platform-gates`（不经 locale-safety 守卫，后者只做静态检查） |
| `test-codex-hook-merge.py` | Codex hook 合并 | `codex-adapter`（release） |
| `test-opencode-plugin.mjs` | 直接执行 OpenCode TypeScript plugin，验大纲守卫、Bash 绕过、写后检查与 compact 恢复 | `opencode-adapter`（release） |
| `test-antigravity-hook-merge.py` / `test-antigravity-hooks.mjs` / `test-antigravity-skills-deploy.py` | Antigravity 适配回归 | `antigravity-adapter`（release） |
| `test-quality-lifecycle.py` | 质量生命周期（约 90s） | `quality-lifecycle`（release） |
| `test-codex-cli-e2e.sh` | 隔离 HOME 后用真实 Codex CLI 检查完整仓库 Skill 的发现结果 | `codex-cli-e2e`（release；CLI 缺失 → BLOCKED） |
| `test-opencode-cli-e2e.sh` | 真实 OpenCode CLI 加载 smoke | `opencode-cli-e2e`（release；CLI 缺失 → BLOCKED） |

## 代码生成 / 同步

| 脚本 | 干什么 | 何时跑 |
|---|---|---|
| `sync-opencode.py` | 从 Claude agent 模板 + `CLAUDE.md.tmpl` 生成 `opencode/agents/` 与 `AGENTS.md.tmpl`；`--check` 只读验同步 | 改 agent 模板后手动跑；被 check-opencode-adapter 调 |
| `generate-codex-agents.py` | 从 Claude agent 模板生成 Codex `.toml` agents | 改 agent 模板后手动跑；被 check-codex-adapter 调验确定性 |
| `generate-codex-hooks.py` | 从 6 个 event 清单生成 `hooks.json`，POSIX/Windows 共用 launcher 负责解释器探测 | 改 Codex hook 注册后；被 check-codex-adapter 调验确定性 |
| `shared-assets.json` + `sync-shared-assets.py` | 为必须随 skill 独立部署的重复 runtime 脚本指定唯一源和目标 | 改共享 runtime 后跑 `sync`；提交前跑 `check` |

> 改了 `skills/story-setup/references/templates/agents/*.md` 或 `CLAUDE.md.tmpl`，必须重跑这两个生成脚本并提交结果，否则本地适配检查失败。详见 [CONTRIBUTING.md](../CONTRIBUTING.md)「OpenCode 模板同步」「Codex 适配维护」。

## 上游同步

先确认 `upstream` 的 push URL 已禁用，再从任意工作区运行：

```bash
node scripts/sync-upstream.js prepare
node scripts/sync-upstream.js review --decisions path/to/decisions.json
node scripts/sync-upstream.js validate
node scripts/sync-upstream.js promote
```

`prepare` 记录 origin/upstream 的固定 SHA 并创建专用 worktree；`review` 导入逐路径决定；`validate` 要求冲突、未知路径、禁止路径和未处理项均为零，并执行 `release` 质量配置；`promote` 只在 origin SHA 未变化、验证树未变化时创建以 upstream 为第二父节点的 merge commit。中止使用 `node scripts/sync-upstream.js abort`。

## 工作流编号维护

`skill-numbering.py` 默认扫描 canonical `skills/**/*.md`，用于阻止迭代插入把工作流编号累积成 `Step 1.3`、`Phase 2.5` 一类小数标签。

```bash
python3 scripts/skill-numbering.py audit          # 只读盘点；发现问题仍退出 0
python3 scripts/skill-numbering.py check          # 本地守卫；发现问题退出非 0
python3 scripts/skill-numbering.py fix --dry-run  # 先看完整 diff，不落盘
python3 scripts/skill-numbering.py fix --write    # 校验通过后一次性落盘
bash scripts/test-skill-numbering.sh              # 隔离 fixture 回归
```

维护策略：

- 只有形如 `### Step N` 的**显式 Step 标题**会自动重排；分组键是「文件 + 标题层级 + 最近父标题」，每组从 1 连续编号。
- 标题与可唯一绑定的 `Step N` 引用基于旧文本同时换号，包含 fenced code block 内的命令/示例引用，避免 `1.5 → 2` 后又被 `2 → 3` 二次级联。
- fractional Step 引用找不到本文件标题，或一个旧标签可能映射到多个新标签时，`fix` 会在任何写入前失败。多文件写入先全量校验/暂存并带回滚，不接受半套结果。
- 标题改号会改变 GitHub Markdown anchor；只要仓库内存在指向旧 anchor 的同文件或跨文件链接，`fix` 就在写入前 fail-closed，并报告每个 fragment，要求先显式更新链接后再重试。局部路径模式同样扫描仓库内入站链接。
- `Step N.M` / `Phase N.M` / `Stage N.M`、直接 `skills/*/SKILL.md` 中的裸小数标题及 bullet 小数子步骤由 `check` 报错，但不做猜测式自动修改。
- `references/` 手册本身的 `3.1` 章节/列表编号不属于工作流标签，不检查、不改写。如果管道 ID 需要插入中间阶段，使用语义名称或 `Stage 2A`，不用小数。
- 可在命令末尾传文件或目录做局部审计，例如 `... audit skills/story-cover/SKILL.md`；合入前仍须跑默认全量 `check`。
