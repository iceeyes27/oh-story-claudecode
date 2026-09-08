# 贡献指南

感谢你对网文写作 skill 包的关注，欢迎贡献。

## 仓库结构

```
skills/
├── story/                   # 工具箱路由
├── story-setup/             # 环境部署
├── story-import/            # 逆向导入
├── story-write/             # 长短篇统一写作入口
├── story-analyze/           # 长短篇统一拆文入口
├── story-scan/              # 长短篇统一扫榜入口
├── story-deslop/            # 去AI味
├── story-review/            # 多视角审查
├── story-cover/             # 封面生成
└── browser-cdp/             # 浏览器操控
scripts/                       # 开发守卫 / 测试 / 代码生成（完整索引见 scripts/README.md）
```

每个 skill 由一个 `SKILL.md`（入口）和 `references/` 目录（知识库）组成。

## Skill 格式

`SKILL.md` 开头必须有 frontmatter：

```yaml
---
name: skill-name
description: "一句话描述。触发方式：/skill-name、触发词1、触发词2"
metadata: {"openclaw":{"source":"https://github.com/iceeyes27/oh-story-claudecode"}}
---
```

为兼容 OpenClaw，frontmatter 必须保持单行键值：`description` 不使用 `|`/`>` 块，`metadata` 必须是单行 JSON 对象。更长的触发说明放到正文中。

`references/` 中的文件由 skill 按需加载，不会全部塞进上下文。

## 如何贡献

### 改进现有 skill

1. Fork 仓库
2. 从 `main` 创建分支：`git checkout -b feat/your-feature main`
3. 修改对应的 `SKILL.md` 或 `references/` 文件
4. 提交 PR，说明改了什么、为什么改

### 新增 skill

1. 在 `skills/` 下创建目录，包含 `SKILL.md` 和 `references/`
2. 确保在仓库根目录运行 `npx skills validate` 无报错
3. 提交 PR

## 本地检查

本 fork 不使用 GitHub Actions。提交或发起 PR 前，贡献者必须在本地运行与改动范围对应的检查：

- `scripts/static-check.sh` — frontmatter、引用路径、死文件、references 交叉引用
- `scripts/check-doc-budget.sh` — 热路径文档字符预算（防 skill/agent 模板无声膨胀，改动 story-write/_shared/narrative-writer 相关文档后必跑）
- `scripts/check-hook-regex-sync.sh` — hook 伏笔状态检测行为
- `scripts/check-shared-files.sh` — Shared File Governance Check（5 个 guard：runtime 副本、shared-references、reference similarity、agent reference consumers、short analysis scope）
- `scripts/check-scan-runtime-policy.sh` — scraper 本地日期依赖与 CDP 源码策略守卫
- `python3 scripts/test-scan-runtime-policy.py` — 验证无关/死代码关键词不能骗过 scan/browser 策略守卫
- `scripts/check-story-setup-deployment.sh` — story-setup 部署完整性
- `scripts/check-claude-adapter.sh` — Claude marketplace 与 skill 映射检查
- `scripts/check-openclaw-skills.sh` — OpenClaw 单行 frontmatter、`metadata.openclaw` 与可选真实 CLI 发现检查
- `scripts/check-codex-adapter.sh` — Codex repo skills symlink、custom-agent TOML（schema + 生成确定性）与 hooks 锚点检查
- `scripts/test-codex-hooks.sh` — Codex hooks 合成事件测试
- `scripts/check-zcode-adapter.sh` — ZCode plugin/marketplace、公开 Skill/Commands、受支持 Hook 事件与部署锚点检查
- `scripts/test-reasonix-adapter.sh` — Reasonix 路由名称与公开 Skill 清单回归检查
- `scripts/test-zcode-hooks.sh` — ZCode 严格 JSON Hook 契约、正文守卫、连续性与跨平台 Node runner 测试
- 采集脚本 `node --check` 语法校验

以上为代表性列举；完整清单与触发时机见 [scripts/README.md](scripts/README.md)。真实 CLI smoke 需要本机安装对应 CLI，按改动范围手动执行。

跨平台改动必须在对应系统本地验证；无法访问目标系统时，在提交说明中明确未验证范围。

提交前优先跑闭合质量网，而不是只挑几个 `test-*` 手跑：`npm run quality:fast`（check 集不变）、改动相关时 `npm run quality:affected`（含 `language-gates`）、发版前 `npm run quality:release`。`scripts/test-*` 的归属见 [scripts/README.md](scripts/README.md)；文档/注释里出现的名字不算运行时引用。

提交前运行本地检查：

```bash
bash scripts/static-check.sh
bash scripts/check-doc-budget.sh
bash scripts/check-hook-regex-sync.sh
bash scripts/check-shared-files.sh
python3 scripts/test-shared-assets.py
node scripts/test-normalize-punctuation.js
node scripts/test-scan-runtime.js
bash scripts/check-scan-runtime-policy.sh
python3 scripts/test-scan-runtime-policy.py
bash scripts/test-ai-patterns.sh
bash scripts/test-degeneration.sh
bash scripts/test-prose-backstop-hook.sh
bash scripts/test-prose-net-parity.sh
bash scripts/test-story-continuity.sh
python3 scripts/test-author-memory-commit.py
bash scripts/check-story-setup-deployment.sh
bash scripts/check-claude-adapter.sh
bash scripts/check-codex-adapter.sh
bash scripts/check-openclaw-skills.sh
bash scripts/test-codex-hooks.sh
bash scripts/check-python-invocation.sh
bash scripts/check-hook-locale-safety.sh
bash scripts/test-hook-encoding-portable.sh
bash scripts/test-charcount-portable.sh
bash scripts/test-charcount-portable.sh --stub

# 可选真实 CLI smoke（需分别安装对应 CLI）
CLAUDE_REAL_CHECK=1 bash scripts/check-claude-adapter.sh
bash scripts/test-codex-cli-e2e.sh
OPENCLAW_REAL_CHECK=1 bash scripts/check-openclaw-skills.sh
```

涉及 agent/skill/plugin/hook 协议的断言必须先核对对应项目官方文档，再以真实 CLI 输出复核；不要从其他 agent 的相似字段推断。

## 共享文件规范

部分文件跨 skill 共享（如 banned-words.md、anti-ai-writing.md），修改时必须同步所有副本。
运行 `bash scripts/check-shared-files.sh` 检查一致性。

### 知识库贡献

最有价值的贡献类型：

- **实战数据**：各平台最新榜单分析、题材趋势变化
- **新题材框架**：新的题材写作公式、结构模板
- **去AI味规则**：新的 AI 痕迹模式、改写范例
- **平台规则更新**：投稿要求、推荐机制的变化

## 质量要求

- **操作性**：内容必须能让 AI agent 直接执行，不要写教程
- **简洁**：用表格和模板，不要长篇叙述
- **无冗余**：不同 skill 的 `references/` 之间可以共享文件（通过路径引用），但同一 skill 内不要重复
- **中文**：所有内容用中文

## 提交流程

```
fork → branch → commit → PR → review → merge
```

- 一个 PR 聚焦一个改动
- commit message 用中文，格式：`类型: 简短描述`
- 类型：`feat`（新增）/ `fix`（修复）/ `docs`（文档）/ `refactor`（重构）

## OpenClaw 适配维护

OpenClaw 当前采用 **Phase 1 skills-only** 适配：

- canonical source 仍是仓库根 `skills/`；不要为 OpenClaw 维护第二份 skill。
- 所有 `SKILL.md` frontmatter 必须符合 OpenClaw/AgentSkills 约束：单行 `name`、单行 `description`、单行 JSON `metadata`，且 `metadata.openclaw` 存在。
- `metadata.openclaw.requires.bins/env/config/anyBins` 用于 OpenClaw load-time gating；例如 `story-cover` 通过 `GPT_IMAGE_API_KEY` 控制可见性。
- `story-setup target_cli=openclaw` 只部署项目 `skills/` 与 `references/openclaw/AGENTS.md.tmpl`，不部署 OpenClaw agents/hooks/plugin。
- OpenClaw 会在 session 启动时 snapshot eligible skills；变更后需要新 session 或等待 skills watcher 刷新。

### OpenClaw 检查步骤

```bash
bash scripts/check-openclaw-skills.sh
OPENCLAW_REAL_CHECK=1 bash scripts/check-openclaw-skills.sh  # 本机安装 openclaw 时可选
```

`OPENCLAW_REAL_CHECK=1` 会用临时 profile + 临时 workspace 创建隔离 agent，确认 OpenClaw CLI 能从 workspace `skills/` 发现公开清单中的 Skill；脚本结束后清理临时 profile。

### OpenClaw 已知边界

- **agents 暂缓**：OpenClaw 的 agent/session 模型与 Claude/Codex 项目内 agent 文件不同，暂不生成 OpenClaw Gateway agents。涉及 agent 协作的 skill 必须降级 solo/direct。
- **hooks 暂缓**：写正文前大纲守卫、commit 提醒、session-start/compact 注入未迁移为 OpenClaw hook/plugin；OpenClaw 下只作为 skill 流程软约束。
- **package 暂缓**：OpenClaw 可识别 workspace/personal/managed skill roots；现阶段不发布 OpenClaw 原生 plugin package。

## ZCode 适配维护

ZCode 采用「原生 plugin + `story-setup` workspace 部署」双入口：

- `.zcode-plugin/plugin.json` 与根 `marketplace.json` 暴露 `scripts/platform-skill-set.json` 声明的同一组公开 Skills、Commands 和 ZCode Hooks；版本必须与 `skills/story/VERSION` 同步。
- `skills/story-setup/references/zcode/` 是 workspace 部署模板，包含 `AGENTS.md.tmpl`、Commands、`config.json.patch` 与无第三方依赖的 Node Hook runner。
- ZCode 3.3.4 只支持 `SessionStart`、`UserPromptSubmit`、`PreToolUse`、`PermissionRequest`、`PostToolUse`、`PostToolUseFailure`、`Stop`。不要复制 Claude 的 `PreCompact`、`PostCompact`、`SessionEnd`、`SubagentStop` 或 `Notification`。
- Hook stdout 为空表示放行；只要非空就必须满足严格 JSON schema。诊断只写 stderr，异常 fail-open；优先使用 `process` + `node`，不要引入 shell/Python launcher 的跨平台分支。
- 3.3.4 不执行项目级或 plugin custom agents，也不发现 `.zcode/rules`。不要生成 `.zcode/agents/` / `.zcode/rules/` 或默认写入用户 home；涉及专业 Agent 的 Skill 必须明确报告 solo/direct fallback。

### ZCode 检查步骤

```bash
bash scripts/check-zcode-adapter.sh
bash scripts/test-zcode-hooks.sh
bash scripts/test-prose-net-parity.sh
```

更新正文轻量确定性网时，必须同步 Claude、Codex、ZCode 三端，并让 parity 测试通过。

## Reasonix 适配维护

Reasonix（DeepSeek-Reasonix CLI）当前支持 skills + 原生 plugin manifest + skills-only 的项目级 `story-setup` 部署；hooks 与 custom agents 留待后续阶段（涉及专业 Agent 的 Skill 走 solo/direct fallback）：

- 根 `reasonix-plugin.json` 是 plugin manifest；`version` 必须与 `skills/story/VERSION` 同步（`check-reasonix-adapter.sh` 守卫）。
- Reasonix 原生扫描项目 skill root（`.agents/skills` 等，指向 `skills/` 的 symlink，与 Codex 共用）发现仓库 Skill。
- `story-setup` 的 `target_cli=reasonix` 走 skills-only 部署：复制 `scripts/platform-skill-set.json` 声明的公开 Skill 到项目 `skills/`、写入 `references/reasonix/AGENTS.md.tmpl`，不部署 hooks/agents（与 OpenClaw / generic 同构，由 `check-story-setup-deployment.sh` 守卫）。改动 Reasonix 部署路径或模板时同步该守卫。
- 真实 CLI 校验 `reasonix doctor capabilities` 不在默认本地检查内，发版前手动运行。

### Reasonix 检查步骤

```bash
bash scripts/check-reasonix-adapter.sh
bash scripts/test-reasonix-adapter.sh
```

## Codex 适配维护

本项目同时支持 Codex CLI（repo skills 发现 + `$story-setup` 项目部署）：

- repo-local skills：`.agents/skills` 是指向 `skills/` 的相对 symlink（`../skills`，agentskills.io 标准路径），Codex 扫描它发现 skill，别复制第二份。必须是有效相对 symlink（`check-codex-adapter.sh` 守卫 target=`../skills`；无效/绝对会让发现失效，见 openai/codex#11314）；Windows 需 git `core.symlinks=true`。OpenClaw 原生扫 workspace `skills/`，不依赖它。
- project deployment hooks：`skills/story-setup/references/codex/hooks/hooks.json` 面向 `$story-setup` 部署到写作项目，`command`（POSIX sh）通过当前目录向上查找定位项目 `.codex/hooks/story_codex_hook.py`，不得要求项目必须是 Git 仓库；并把查到的根以 `CODEX_PROJECT_DIR=` 传给 Python（Codex 本身不注入该变量，root 解析以 Python 的 `__file__` 自定位为准）。
- Windows hooks：Codex 在 Windows 下用 `%COMSPEC% /C`（cmd.exe）跑 hook 命令，**不是** POSIX shell，所以每个 hook 必须带 `commandWindows`（cmd.exe 语法）。当前 `commandWindows` 为 `if exist .codex\hooks\story_codex_hook.py python ... <event>`：cwd 为项目根时运行、否则干净 no-op（best-effort，上溯查找仅 POSIX `command` 具备）。Python hook 本体跨平台、已做 UTF-8 字节 stdio 与 `__file__` 自定位。改 `command` 时必须同步改 `commandWindows`（`check-codex-adapter.sh` 守卫 event 一致 + cmd.exe 安全）。
- custom agents：`skills/story-setup/references/codex/agents/*.toml` 由 `scripts/generate-codex-agents.py` 从 `references/templates/agents/*.md` 生成。修改 Claude agent 模板后必须重新生成并提交。

### Codex 同步步骤

```bash
python3 scripts/generate-codex-agents.py
bash scripts/check-codex-adapter.sh
bash scripts/test-codex-hooks.sh
```

### Codex 关键兼容性问题

- **hooks 信任门槛**：Codex project `.codex/` 配置层需要被 trust，非 managed command hooks 还需要用户在 `/hooks` review/trust 后才会运行。
- **hook JSON 契约**：`PreToolUse`、`PreCompact`、`PostCompact` 的普通 stdout 会被忽略；需要输出 JSON，如 `hookSpecificOutput.permissionDecision = "deny"` 或 `hookSpecificOutput.additionalContext`。
- **PreToolUse 不完整拦截**：Codex 官方说明当前 shell/edit 拦截不是完备安全边界；story hooks 只作为写作流程 guardrail，不能替代版本控制和人工审查。
- **agent 文件格式**：Codex custom agents 是 `.codex/agents/{name}.toml`，必需 `name`、`description`、`developer_instructions`；只读 agent 使用 `sandbox_mode = "read-only"`。
- **custom-agent 运行时注册**：`$story-setup` 写入 `.codex/agents/*.toml` 后，需要 trust 项目 `.codex/` 配置层并新开 Codex 会话。若当前 Codex 运行时仍返回 `unknown agent_type`（本地 `codex exec 0.141.0` 临时项目烟测可复现），skill 必须降级 solo/direct 并报告 fallback；自动化硬门槛是 TOML schema 与文件部署检查。
