---
name: story-write
version: 2.1.0
description: "网文写作（长篇/短篇统一入口）。mode=long 默认从设定、大纲和细纲生成可扩写的章节骨架，成稿进入作者审批候选；mode=short 走短篇成稿流程。触发方式：/story-write、/写长篇、/写短篇、「帮我开书」「写大纲」「写第N章」「日更」「续写」「生成成稿」「帮我写一篇短篇」——按意图自动路由。"
metadata: {"openclaw":{"source":"https://github.com/iceeyes27/oh-story-claudecode"}}
disable: true
---

# story-write：网文写作（长篇 / 短篇统一入口）

长篇默认生成规划和章节骨架，明确成稿写入候选并经作者采用；短篇从构思写到成稿。

## 阶段 Reference Gate

先确定 mode：长篇从 `references/long-mode.md` 的场景路由定位当前阶段，只读取该阶段执行段；普通成稿写手只完整读取 `references/reader-first-writing.md` 与 `references/long-format.md`，其余按阶段或具体问题加载。短篇完整读取 `references/short-mode.md` 直到 EOF。只读本文件（SKILL.md）不算完成门禁；对明确要求完整读取的核心文件，`rg` 检索或局部摘读都不算完成门禁，必需路径缺失或不可读即停止。

短篇运行 `node .agents/skills/_shared/scripts/check-phase2-contract.js --json {短篇目录}`；最多做 2 轮定向 repair。交付时用户明确的字数范围优先；运行 `node .agents/skills/_shared/scripts/check-delivery-contract.js --json --min-chars {MIN} --max-chars {MAX} --sections {N} {短篇目录}`。

---

> 运行环境兼容性：Claude Code / OpenCode / Codex / ZCode / OpenClaw 是内置适配目标。检查专业 agent 时按 `.claude/agents/{agent}.md` → `.opencode/agents/{agent}.md` → `.codex/agents/{agent}.toml` 查找；找不到、Codex 返回 `unknown agent_type`，或检测到 `.zcode/`（ZCode 3.3.4 不执行项目 custom agents）时，直接 solo/direct 执行并报告 fallback。
>
> Spawn 版本提示（不阻断 spawn）：先读取项目根 `.story-deployed` 的 `agents_version`。与本版 `agents_version: 29` 不一致时（标记缺失、字段缺失/非整数、小于或大于 29）**照常按文件存在性检查并 spawn**，同时报告 `Notice: agents bundle 版本不匹配（项目 {N}，本版 29）` 并提示重新运行 `/story-setup` 后新开会话；大于 29 时额外提示先更新 oh-story-claudecode，不要用本地旧版 setup 降级覆盖。只有 agent 文件缺失、或运行时不暴露 custom agent 时才降级 solo/direct，报告 `Fallback: ... -> solo`。

## 模式路由（mode = long / short）

调用本 skill 时先按以下规则确定 `mode`：

| 用户意图关键词 | mode | 说明 |
|---|---|---|
| 开书 / 大纲 / 日更 / 续写 / 继续写 / 写第N章 / 修改第X章 / 回炉 / 重写第X章 | `long` | 长篇网文写作流程 |
| 短篇 / 盐言 / 一篇短篇 / 写个盐言故事 | `short` | 短篇网文写作流程 |

**路由规则**：
- 用户明确说"开书/大纲/日更/续写/写第N章/回炉" → `mode=long`
- 用户明确说"短篇/盐言/一篇短篇" → `mode=short`
- 用户没指定长篇还是短篇 → 先问「长篇还是短篇？」，不要擅自假设
- **裸调用**（`/story-write` 没有明确意图）→ 先做项目状态诊断并列出下一步选项，**不得自动进入正文写作**：
  - 空项目 → 建议说「帮我开书」（长篇）或「帮我写一篇短篇」（短篇）
  - 已有长篇设定/大纲但无正文 → 建议说「写第1章骨架」或「日更2章骨架」
  - 已有长篇正文+追踪 → 展示最后采用章节、下一章细纲、骨架或候选状态，建议说「写下一章骨架」「日更2章骨架」「采用第X章」或「修改第X章」
  - 已有短篇设定/大纲但无正文 → 建议说「开始写正文」
  - 已有短篇正文 → 展示当前进度，建议说「继续写」或「精修」

---

## 核心方法（长篇 / 短篇共享）

长篇按 `references/reader-first-writing.md` 的三层规则，情绪与模块方法按需使用；短篇按自身协议执行。

1. **先定情绪，再定故事**。选择场景时明确它服务的情绪目标。
2. **参考已有模式**。扫榜找方向，拆文找模块，对标找节奏。
3. **选用模块**。参考反转、爽点、感情的组织方式，用本书人物和素材改造，不套用对标书的事件。
4. **只加载必需信息**。只取本章相关状态、伏笔与设定，其他材料留在文件系统。
5. **阶段披露由状态驱动**。每轮先按 `references/progressive-disclosure.md` 识别 `mode`、`current_phase`、`current_stage`、`missing_inputs`、`artifacts`、`next_action`；只展示和读取当前阶段必需资料。用户说"继续"、"日更"、"精修"、"检查"时，优先回到已识别阶段，不重新展开完整流程。
6. **契约与推进决策走权威参考文件**。涉及读者契约、主角代理权、利益安全、期待债、终局储备（终局底牌/升级台阶）、机构/势力边界和 契约安全 / 需补强 / 契约破坏 风险判定时，先按 `references/reader-contract-and-progression.md` 校准，不在 SKILL.md 内复制长规则。
7. **复用作者习惯**。若作者记忆 state 已存在，正文前用 `.agents/skills/_shared/scripts/author_memory_commit.py query --kind prose_style --kind story_design` 获取本次相关 active 条目（总输出 ≤2KB），原样传给实际正文/改写 agent；设定/大纲按任务查询其他 kind。硬门禁、当前请求、本书设定/文风优先。明确长期声明在收尾用 `record` 写入并回传回执；完整规则见 [.agents/skills/_shared/references/author-memory.md](../_shared/references/author-memory.md)，不混入追踪。

| 题材 | 核心情绪 | 重点参考 |
|------|---------|---------|
| 打脸/逆袭 | 爽感释放 | genre-writing-formulas.md |
| 身份反转 | 震撼+痛快 | reversal-toolkit.md |
| 感情拉扯 | 意难平 | emotional-methods.md |
| 悬疑/惊悚 | 紧张+好奇 | hooks-suspense.md |
| 日常装逼 | 期待感 | hooks-chapter.md |

> 用户只描述情绪时，可从上表反查题材，再用 `genre-catalog.md`（长篇）或 `genre-styles/`（短篇）细分。

---

## 通用执行规则（长篇 / 短篇共享）

长篇允许人物、幽默、生活质感与必要理解；不以以下简写删除好表达或强补悬念。

1. **每句话必须有用**。不推动剧情、不铺垫反转、不推高情绪的句子 → 删。
2. **开头定生死，结尾定传播**。开头必须包含钩子，结尾必须有余韵。
3. **任务卡点必须有功能**：角色办事被卡住，必须卡出信息/关系/代价/选择/伏笔变化；删掉无损就压缩或删除。

> 各模式的具体规则见其流程。

---

# 按模式加载执行流程

模式判定后**只加载对应 mode 参考文件**的适用阶段；不同时加载两种模式：

- `mode = long` → 由 [references/long-mode.md](references/long-mode.md) 定位当前阶段。普通候选写手的固定核心是 [references/reader-first-writing.md](references/reader-first-writing.md) 与 [references/long-format.md](references/long-format.md)，写后再由编排器执行 Phase 5。
- `mode = short` → 读 [references/short-mode.md](references/short-mode.md)。

mode 参考文件内的 `references/...`、`scripts/...` 路径均相对本 skill 根目录。
