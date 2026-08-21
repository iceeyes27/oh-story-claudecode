---
name: story
description: "网络小说工具箱主入口。根据用户需求自动路由到对应 skill；当用户只说检查、检查这本小说、帮我检查或检查当前书时，必须执行完整的小说复合检查。也用于分发扫榜、拆文、写作、去AI味、封面、导入、审查和启动本地 Dashboard。触发方式：/story、$story、/story dashboard、$story dashboard、/网文、/检查、「我想写小说」「打开工作台」「检查这本小说」「检查更新」「有新版本吗」。"
metadata: {"openclaw":{"source":"https://github.com/iceeyes27/oh-story-claudecode"}}
---
# story：网文工具箱路由

你是网文工具箱的路由入口。用户的请求模糊时由你分发到具体 skill。

## 路由表

> **合并精简说明（2026-07-12）**：原 `story-long-*` / `story-short-*` 已合并为 `story-scan` / `story-analyze` / `story-write`（用 mode 参数区分长/短篇）；`shuorenhua` 合并进 `story-deslop`（mode=general）；`Humanizer-zh` + `humanizer` 合并为双语 `humanizer`。旧命令仍可使用，自动路由到对应 skill 的 long/short mode。

> Codex CLI 中优先使用 `$story-*` 或 `/skills` 触发；Claude Code / OpenCode 继续使用 `/story-*`；OpenClaw 可用 `/skill story-*` 或自然语言点名 skill。下表以 slash command 展示，Codex 可将 `/story-write` 等价替换为 `$story-write`，OpenClaw 可将其等价替换为 `/skill story-write`。

| 用户意图 | 关键词示例 | 路由到 |
|---|---|---|
| 写长篇 | 开书、写大纲、长篇、连载 | `/story-write` (mode=long) |
| 写短篇 | 短篇、盐言、一万字 | `/story-write` (mode=short) |
| 长篇拆文 | 拆文、分析这本书、黄金三章 | `/story-analyze` (mode=long) |
| 短篇拆文 | 拆短篇、分析这个故事 | `/story-analyze` (mode=short) |
| 长篇扫榜 | 长篇排行、什么火、起点/番茄/晋江 | `/story-scan` (mode=long) |
| 选题决策 | 写什么能爆、帮我选题、选题方向 | `/story-scan` (mode=long) |
| 短篇扫榜 | 短篇排行、知乎盐言排行 | `/story-scan` (mode=short) |
| 去 AI 味 | 去 AI 味、太 AI、去味、说人话 | `/story-deslop` |
| 小说复合检查 | 检查、检查这本小说、帮我检查、检查一下当前书 | 依次执行 `story-review` → `ai-flavor-scan` → `story-deslop` (mode=novel) → `dialogue-naturalness-scan` → `jargon-verb-scan` → `legal-domain-veracity-scan`（涉司法实务题材） → `story-deslop` (mode=general) → `humanizer` |
| 律政专业度 | 检查律政专业度、证据合法性、取证程序、司法硬伤 | `/legal-domain-veracity-scan` |
| 封面 | 封面、封面图 | `/story-cover` |
| 环境部署 | 准备写书、搭环境、初始化 | `/story-setup` |
| 浏览器操控 | 浏览器、抓取、登录态 | `/browser-cdp` |
| 导入小说 | 导入、反向解析、导入小说、把我的书导进来 | `/story-import` |
| 工作台 | dashboard、工作台、看拆文库、浏览项目文件、打开项目面板 | 见下方「Dashboard 工作台」 |
| 检查/更新版本 | 检查更新、有新版本吗、升级、更新工具箱 | 见下方「版本更新检查」 |
| 切换/列出书目 | 切书、换书、列出我的书、我在写哪几本、切换项目 | 见下方「多书切换」 |
| 查故事资料 | 查角色、查伏笔、查进度、查设定、什么状态、写到哪了 | spawn `story-explorer` agent（结构化 prompt：`项目目录：{dir}\n查询类型：{根据意图选择}\n查询参数：{用户查询}`）；agent 不可用时见下方「查询降级」 |
| 查资料 | 查资料、帮我查资料、调研、搜索一下、搜一下 | spawn `story-researcher` agent；agent 不可用时见下方「查询降级」 |

### 导入续写顺序

用户问"导入续写先 setup 还是 import"时，直接回答：**推荐先 `/story-setup`，新开/刷新会话后 `/story-import`，最后 `/story-write 日更` 或 `/story-write 写第N章`**。如果用户已经直接触发 `/story-import`，按 story-import 自带环境检测继续：未 setup 时让用户选择先去 setup 或继续串行导入。

## Dashboard 工作台

用户执行 `/story dashboard`（Codex 为 `$story dashboard`），或明确说“打开工作台 / 看项目文件”时，直接启动随本 skill 分发的本地 Dashboard，不再转发到其他 skill：

1. 把当前工作目录作为默认工作区；用户明确给出目录时改用该目录。目录必须存在。
2. 从当前已加载的 `story` skill 目录定位 `scripts/dashboard-server.mjs`，不要硬编码仓库路径、全局 skill 路径或用户主目录。
3. 检查 `node` 可用后，以长运行进程执行：

   ```bash
   node "<story-skill-dir>/scripts/dashboard-server.mjs" --root "<workspace>" --open
   ```

4. 等待输出出现“本机地址”，把完整 URL 回给用户。工具支持后台进程或 PTY 时让服务保持运行；无法自动拉起浏览器不算失败，仍返回可点击 URL。
5. Dashboard 默认只监听 `127.0.0.1`。不要主动增加 `--allow-network`，不要把工作区暴露到局域网或公网。

工作台会识别标准 `拆文库/{书名}/`，兼容存量 `拆文库-{书名}/`。写作项目识别同时支持：

- 长篇目录结构：目录内含 `正文/`、`大纲/`、`设定/` 或 `追踪/` 任一普通子目录。
- 短篇单文件结构：目录内含普通文件 `正文.md`，并同时含 `小节大纲.md` 或 `设定.md`。

符号链接不作为项目标记，只有单个 `正文.md` 的普通资料目录也不会被误认。浏览器可编辑
`.md`、`.txt`、`.json`、`.yaml`、`.yml`、`.toml`，保存或确认删除前用修改时间防止
误操作外部更新。

停止服务时终止对应的 Node 长运行进程即可。若用户只问用法，不要替他启动；给出 `/story dashboard` / `$story dashboard` 两种平台对应入口。

## 路由流程

1. 分析用户请求，提取意图关键词
2. 匹配上表，找到对应的 skill
3. 如果能明确匹配，直接调用对应 skill（Claude/OpenCode 可用 `Skill("skill-name")` 或 slash command；Codex 用 `$skill-name` / `/skills`；OpenClaw 用 `/skill skill-name` 或自然语言点名）
4. 如果无法匹配，询问用户想做什么（从上表中选择）
5. 如果用户说"我想写小说"但未指定长篇/短篇，询问篇幅类型后再路由

## 小说复合检查硬门禁

复合检查的阶段、过滤器和检查项以 `references/composite-check-manifest.json` 为唯一清单。用户只说“检查”且未限定单项时，不得缩减成一次 `story-review`，必须按清单顺序完成：

1. `story-review`：结构、逻辑、设定、人物、时间线、伏笔和平台适配。
2. `ai-flavor-scan`：正文十层 AI 味实扫，覆盖禁用词、AI 修辞、融合比喻、空洞总结与旁白口号腔、黑话单字、生造搭配、欠写作、物理语义错配、装人设套路组合和章节标题模板套路。
3. `story-deslop`（mode=novel）：正文 AI 味 7 Gate。
4. `dialogue-naturalness-scan`：台词自然度专项，检查模糊指代、书面腔、别扭搭配和解释式台词。
5. `jargon-verb-scan`：行业词或专业名词硬当动词专项，检查被行话隐藏的真实动作。
6. `legal-domain-veracity-scan`：律政实务与证据合规专项，检查取证程序、证明力背书和庭审规范硬伤；题材完全不涉司法实务时整阶段按清单标 `SKIPPED` 并写明判断依据。
7. `story-deslop`（mode=general）：正文及对外文案的套路腔、空话和模板感。
8. `humanizer`：通用 AI 痕迹复核；纯中文正文只作模式复核。

开始前输出当前书名、正文目录、章节总数、八阶段识别结果和清单中的必检项总数。每完成一个阶段，立即输出该阶段的独立结论，至少包含：执行状态、实际检查范围、该阶段必检项数、已返回结果数、问题数量和关键发现。阶段内部必须逐项登记覆盖记录：

```text
filter_id | status | scope | findings | reason
```

`PASS` 表示已执行且无发现，`FAIL` 表示已执行且有发现，`BLOCKED` 表示无法执行，`SKIPPED` 仅能用于清单允许的非适用项并写明原因。普通发现问题不能中断后续过滤器和阶段；输入不可读、范围不完整或没有等价执行器时必须报告阻断，不得静默跳过。Reviewer agent 不可用但 `story-review` 按自身规则完成 solo 降级时，必须标明降级，不能减少清单项目。

只有八个阶段全部有结论、每个必检项都有状态且没有未说明的 `BLOCKED` 或 `SKIPPED` 时，才允许输出清单规定的 `复合检查完成：8/8，过滤项 M/M`；未达到条件不得宣称检查完成。

用户未明确要求修改时，复合检查只读，不写正文文件。

## 查询降级

> Spawn 版本提示（不阻断 spawn）：先读取项目根 `.story-deployed` 的 `agents_version`。与本版 `agents_version: 25` 不一致时（标记缺失、字段缺失/非整数、小于或大于 25）**照常按文件存在性检查并 spawn**，同时报告 `Notice: agents bundle 版本不匹配（项目 {N}，本版 25）` 并提示重新运行 `/story-setup` 后新开会话；大于 25 时额外提示先更新 oh-story-claudecode，不要用本地旧版 setup 降级覆盖。只有 agent 文件缺失、或运行时不暴露 custom agent 时才降级 solo/direct，报告 `Fallback: ... -> solo`。

「查故事资料」「查资料」走 agent 前先做轻量可用性检查（路由只做这一层，不承担全局部署策略）：当前不在子代理上下文、Agent/Task 工具可用、且 `.claude/agents/{story-explorer|story-researcher}.md`、`.opencode/agents/{story-explorer|story-researcher}.md` 或 `.codex/agents/{story-explorer|story-researcher}.toml` 存在 → 可尝试 spawn。任一不满足，或 Codex 运行时返回 `unknown agent_type` / 未暴露 custom-agent registry，则降级，不硬失败：

- `story-explorer` 不可用 → 主线程直接用 Read/Grep 从项目文件检索（角色状态/伏笔/进度/设定），回答前标注 `Fallback: agent unavailable -> direct lookup`；项目尚未部署时提示先 `/story-setup`（Codex 中用 `$story-setup`）。
- `story-researcher` 不可用 → 主线程用现有检索/回答能力完成，或提示用户改用 `/browser-cdp` 采集，同样标注 `Fallback: agent unavailable -> direct lookup`。

## 项目状态感知

路由前先检查当前项目状态：

- **无项目目录**（没有包含 `追踪/` 或 `设定/` 的书名目录）：
  - 如果用户要写作，下一步是先运行 `/story-setup` 初始化环境（Codex 中用 `$story-setup`）
  - 如果用户要扫榜/拆文，直接路由
- **已有项目**：检查 `.story-deployed` 标记，如未部署则先运行 `/story-setup`（Codex 中用 `$story-setup`）

## 多书切换

用户想切换或查看在写的书时（一个项目可同时有多本）：

1. 在项目根查找所有书目录：包含 `追踪/` 或 `设定/` 子目录的目录（含 `长篇/`、`短篇/` 下的子目录）。
2. 列出书名，并标出当前 `.active-book` 指向的那本。
3. 让用户选择，把所选书的相对路径写入项目根 `.active-book`（覆盖原内容）。
4. 只发现一本时直接确认为活跃书，无需询问。

## 版本更新检查

用户问"有没有新版本""检查更新""升级"时执行。**只通知，更不更新由用户定，不自动安装。**

1. **当前版本**：读本 skill 同目录的 `VERSION` 文件；缺失则视为未知。
2. **最新版本**：优先 `gh release view --json tagName,name,url -R iceeyes27/oh-story-claudecode` 取 `tagName`；无 gh 用 `curl -fsS --max-time 5 https://api.github.com/repos/iceeyes27/oh-story-claudecode/releases/latest` 取 `.tag_name`（jq 或 grep）。查不到 → 告知"暂时拉不到最新版本，可手动看 [Releases](https://github.com/iceeyes27/oh-story-claudecode/releases)"，不报错。
3. **比较**：去掉 `v` 前缀按语义版本比（major.minor.patch）。`gh release` 默认取 latest 稳定版，不含 pre-release。
4. **告知**：
   - 已最新 → 「已是最新版 vX.Y.Z」。
   - 有新版 → 列出 当前 vA → 最新 vB + [Releases](https://github.com/iceeyes27/oh-story-claudecode/releases)/[CHANGELOG](https://github.com/iceeyes27/oh-story-claudecode/blob/main/CHANGELOG.md)（能拿到 release notes 就附本次要点），再用 AskUserQuestion 问「现在更新吗？」：
     - 选更新 → 跑 `npx skills add iceeyes27/oh-story-claudecode -y -g`（`-g` 全局，去掉则只更当前目录）；完成后提示：已部署过的项目在项目根重跑 `/story-setup`（Codex 中用 `$story-setup`）同步 hooks/agents/references，并**新开一个会话**让 agents 重新注册。
     - 选先不 → 不动，告知随时可再来。
