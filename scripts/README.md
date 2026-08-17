# scripts/ —— 仓库开发脚本索引

这些是开发本仓库（skill 套件本体）用的**守卫 / 测试 / 代码生成**脚本，**不是** skill 运行时脚本（运行时脚本在各 skill 自己的 `scripts/` 下，如 `story-deslop/scripts/check-ai-patterns.js`，跨 skill 字节同步）。

- 本 fork 不使用 GitHub Actions；提交前本地检查命令见 [CONTRIBUTING.md](../CONTRIBUTING.md)「本地检查」。
- **改名 / 移动任一脚本**，要同步改 `CONTRIBUTING.md`、本文件，以及调用它的兄弟脚本（见下方「何时跑」里的调用关系）。

## 静态守卫（check-*）

| 脚本 | 检查什么 | 何时跑 |
|---|---|---|
| `static-check.sh` + `static-check.py` | 结构化验证 frontmatter、Markdown 路径/锚点、Agent 引用、references 可达性；除基础组件 `browser-cdp` 外禁止跨 Skill 文件引用 | 提交前本地 |
| `skill-numbering.py check` | 工作流 Step/Phase/Stage 编号策略、引用绑定、SKILL.md 裸编号/子步骤小数守卫 | 提交前本地；改工作流结构后 |
| `check-current-skill-contracts.sh` + `.py` + `current-contract.json` | 从结构化 manifest 校验当前版本、Phase、schema、主产物、细纲契约与 GitHub Actions 禁用策略；保留 legacy/path 守卫并拦截缺主产物后的静默替代 | 提交前本地 |
| `check-unified-skill-upstream-drift.py` + `unified-skill-upstream-map.json` | 上游 split skill 改动后强制人工映射到 unified skill；`--report` 只读输出 source -> target 迁移清单 | 合并上游后；提交前本地 |
| `check-shared-files.sh` | 调 `sync-shared-assets.py check` 验 runtime 副本，再验共享 reference 字节一致 | 提交前本地 |
| `check-scan-runtime-policy.sh` | scraper 输出文件名依赖本地日期 helper；CDP 探测/Windows 监听解析的源码策略 | 提交前本地；这些依赖方向无法由隔离 helper 测试证明 |
| `check-story-setup-deployment.sh` | story-setup 部署/运行时回归（慢，>2min） | story-setup 改动后本地 |
| `check-hook-regex-sync.sh` | `detect-story-gaps.sh` 伏笔状态检测行为 | 相关改动后本地 |
| `check-hook-locale-safety.sh` | 部署 hook 在 Windows 中文 GBK 区域的字节安全 | hook 改动后本地 |
| `check-python-invocation.sh` | 技能文档禁止裸调 `python3`（须 python3→python→py 探测） | 提交前本地 |
| `platform-skill-set.json` | 跨平台公开发布的 15 个 Skill 唯一清单；Claude、OpenCode、ZCode 与 OpenClaw 校验共用 | 增减公开 Skill 时先修改 |
| `local-only-skill-set.json` | 不进入跨平台公开部署的 Skill 及原因；与公开清单的并集必须覆盖仓库全部 Skill | 新增或改变 Skill 发布范围时修改 |
| `sync-upstream.js` | 安全拉取并合并 `upstream/main`；按统一 Skill 映射自动处理旧 split 目录冲突，漂移未迁移时拒绝提交 | 同步上游时运行 |
| `check-claude-adapter.sh` | Claude marketplace 与公开 Skill 清单的一一映射；可选真实 CLI strict validate | 本地静态；`CLAUDE_REAL_CHECK=1`（真实 CLI） |
| `check-opencode-adapter.sh` | OpenCode 适配层同步 + commands/agents/config 结构 + plugin 行为回归 | 本地（调 sync-opencode.py） |
| `check-openclaw-skills.sh` | OpenClaw AgentSkills/frontmatter 兼容性 | 本地 |
| `check-codex-adapter.sh` | Codex 适配层：repo skills symlink、agent TOML、hooks 与跨平台 launcher | 本地（调 generate-codex-agents.py 验生成确定性） |
| `check-zcode-adapter.sh` | ZCode plugin/marketplace、Skills/Commands/Hooks 与部署锚点 | 本地 |
| `check-reasonix-adapter.sh` | Reasonix plugin manifest、公开 Skill 清单和 AGENTS 路由名一致性 | 本地 |

## 测试回归（test-*）

| 脚本 | 测什么 | 何时跑 |
|---|---|---|
| `test-ai-patterns.sh` | 确定性 AI 句式检测器 `check-ai-patterns.js` 回归 | 本地 |
| `test-degeneration.sh` | 模型退化检测器 `check-degeneration.js` 回归 | 本地 |
| `test-prose-net-parity.sh` | 正文后置「轻量确定性网」Claude/OpenCode/Codex/ZCode parity | 本地（调 check-hook-regex-sync） |
| `test-prose-backstop-hook.sh` | `check-prose-after-write.sh` 回归 | 本地 |
| `test-story-continuity.sh` | `detect-story-gaps.sh` 跨批连续性后置回归 | 本地 |
| `test-longform-stability.sh` | 长篇稳定性工具链（`stability-audit.js` + `handoff-pack.js` + `archive-stability.js`）回归：契约 beat/禁词/门控/角色不变量 POV 扫描/世界观不变量违规词/交接继承/归档透明回退 | 本地 |
| `test-flow-state.sh` | `story-write` 写作阶段披露状态工具（`flow-state.js`）回归：阶段识别、`.active-book` 路径边界、缺追踪/缺细纲阻塞、短篇正文检查路径、状态更新字段校验 | 改 `flow-state.js` 或 `progressive-disclosure.md` 后 |
| `test-state-store.sh` | 结构化状态库（`state-query.js`）回归：分片路由/时点快照折叠/活跃与超期伏笔/矛盾检测（死亡后活动、未埋先收、重复回收、分片错位） | 本地 |
| `test-codex-hooks.sh` | Codex hook 合成 stdin/stdout 契约 | 本地 |
| `test-static-check.py` | 真 frontmatter block、精确路径/锚点、跨 Skill 引用、fence、死 reference、Agent 与章节链接 fixture | 本地 |
| `test-current-skill-contracts.py` | current-contract manifest 类型/固定值与主产物 fail-fast 语义 fixture | 本地 |
| `test-shared-assets.py` | 共享资产 manifest 的 drift、sync、路径越界、basename 单一 owner 与未登记重复检测 | 本地 |
| `test-normalize-punctuation.js` | 标点归一化的只读检查、frontmatter/fence、CRLF、引号模式与幂等性 | 本地 |
| `test-scan-runtime.js` | CDP argv 边界/报错/JSON 契约与 7 个 scraper 无副作用 import | 本地 |
| `test-scan-runtime-policy.py` | 变异验证 scan/browser 静态策略不会被无关或死代码关键词骗过 | 本地；改 `check-scan-runtime-policy.sh` 后 |
| `test-opencode-plugin.mjs` | 直接执行 OpenCode TypeScript plugin，验大纲守卫、Bash 绕过、写后检查与 compact 恢复 | 被 `check-opencode-adapter.sh` 调用 |
| `test-codex-cli-e2e.sh` | 隔离 HOME 后用真实 Codex CLI 检查完整仓库 Skill 的发现结果 | 可选本地；需已安装 `codex` |
| `test-zcode-hooks.sh` | ZCode 严格 JSON Hook、正文守卫与连续性回归 | 本地 |
| `test-charcount-portable.sh` | 跨平台字符统计命令在三平台 + Windows 的正确性 | 本地（调 check-python-invocation） |
| `test-hook-encoding-portable.sh` | 部署 hook 在 Windows 中文系统的编码健壮性 | 本地 |
| `test-opencode-cli-e2e.sh` | 真实 OpenCode CLI 加载 smoke（公开 Skill 命令 / 7 agents / plugin） | 可选本地；需已安装 `opencode` |
| `test-skill-numbering.sh` | Step 重排级联安全、锚点 fail-closed、代码块引用、验证零写入/提交回滚、dry-run/write/幂等性 | 对应系统本地 |
| `test-unified-skill-upstream-drift.py` | 上游旧拆分目录变化时，迁移检查会显示统一目标路径，并验证 `--report` 只读返回成功 | 改上游漂移检查后 |
| `test-reasonix-adapter.sh` | Reasonix AGENTS 路由表拒绝已废弃的 split Skill 名称 | 改 Reasonix 模板或检查脚本后 |

## 代码生成 / 同步

| 脚本 | 干什么 | 何时跑 |
|---|---|---|
| `sync-opencode.py` | 从 Claude agent 模板 + `CLAUDE.md.tmpl` 生成 `opencode/agents/` 与 `AGENTS.md.tmpl`；`--check` 只读验同步 | 改 agent 模板后手动跑；被 check-opencode-adapter 调 |
| `generate-codex-agents.py` | 从 Claude agent 模板生成 Codex `.toml` agents | 改 agent 模板后手动跑；被 check-codex-adapter 调验确定性 |
| `generate-codex-hooks.py` | 从 6 个 event 清单生成 `hooks.json`，POSIX/Windows 共用 launcher 负责解释器探测 | 改 Codex hook 注册后；被 check-codex-adapter 调验确定性 |
| `shared-assets.json` + `sync-shared-assets.py` | 为必须随 skill 独立部署的重复 runtime 脚本指定唯一源和目标 | 改共享 runtime 后跑 `sync`；提交前跑 `check` |

> 改了 `skills/story-setup/references/templates/agents/*.md` 或 `CLAUDE.md.tmpl`，必须重跑这两个生成脚本并提交结果，否则本地适配检查失败。详见 [CONTRIBUTING.md](../CONTRIBUTING.md)「OpenCode 模板同步」「Codex 适配维护」。

## 上游同步

从干净工作区运行：

```bash
node scripts/sync-upstream.js
```

脚本会 fetch `upstream/main`、开始一个不自动提交的 merge，并按 `unified-skill-upstream-map.json` 自动保留已统一 Skill 对旧 split 目录的删除。若上游修改了旧目录，漂移检查会暂停合并，列出必须迁入 `story-write`、`story-analyze` 或 `story-scan` 的目标；其它语义冲突也会原样列出。处理完并通过检查后手动 `git commit`，或一开始传 `--commit` 让全套检查通过后自动创建 merge commit。放弃本次同步用 `git merge --abort`。

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
