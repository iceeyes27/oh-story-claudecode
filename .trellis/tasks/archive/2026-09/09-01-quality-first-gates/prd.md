# 提质优先：叙事质量门禁重排

## Goal

让本仓库产出的小说满足作者提出的三条标准：**没有基本毛病、语言通顺、读者爱看**。

做法不是新造检查器，而是**先把仓库里已经写好但没接到写作回路上的质量契约接上**，再补真正缺失的台账。这与 grok 原方案（v2 / 审核 v2.1）覆盖同一批问题，但重排了顺序：原方案把最贵、读者收益最间接的「数值台账」排第一，唯一提质的「情绪母题」排最后；本任务反过来。

## 三条轴与当前覆盖

| 轴 | 现状 | 结论 |
|---|---|---|
| 没有基本毛病 | `check-outline-causal.py` 存在但未接采用链；专名漂移检查不存在；数值台账不存在 | 要新建，最贵 |
| 语言通顺 | `check-ai-patterns.js` 规则集与词表加载器已恢复（0.7），`banned-word-*` / `rule-load-error` 为 blocking；正文自带豁免已关闭（子任务 0）。三个语义扫描 skill 仍无脚本、不在日更回路；原「advisory 密度峰值」触发前提已不成立，子任务 3 推迟并重做设计 | 装备已经接上；剩下的是 advisory 风格类触发，不是堵洞 |
| 读者爱看 | `check-outline-contract.js` 已定义整套读者体验必填字段，但只在建纲时跑、对既有项目明确不阻断、promote 不跑 | 定义齐全，只差接线 |

## Requirements

### R1 · 语言门禁不可被写作方自行关闭
- `candidate-commit.py` 的 `EXEMPTION`（正文前 6 行写 `去味：跳过`）必须移除或改为需作者显式授权并留痕。
- `--no-scan` 必须要求理由并写入采用回执。
- 依据：写正文的 agent 不得在自己的输出里关掉检查自己的门。

### R2 · 读者体验契约进入唯一写入口
- `check-outline-contract.js` 的 `INTENT_FIELDS`（`目标情绪` / `主角目标/关键选择` / `结尾拍ID/类型` / `期待ID/类型` / `读者验收预期`）必须在 promote 时对**新写章** blocking。
- 历史章（`imported_through_chapter` 及之前）保持 advisory，避免导入书全红。
- `outline.plotpoint-table` / `outline.reader-contract` 本批只 advisory。

### R3 · 情绪母题连排可被检出
- 复用已必填的 `目标情绪`，**不新增母题字段**。
- 该字段取值必须来自闭合词表。
- 连续同值达阈值时给出 finding。

### R4 · 语义扫描按确定性谓词触发
- `ai-flavor-scan` / `dialogue-naturalness-scan` / `jargon-verb-scan` 目前只在用户说「检查」时跑；需要在候选检查阶段按确定性条件触发子集。
- 触发条件必须是脚本可判定的谓词，不得再引入一轮 LLM 分类。

### R5 · 因果链进入采用链
- `check-outline-causal.py --strict --from N --to N` 在出骨架前与 promote 各跑一次。
- 导入书历史章 advisory，新写章 strict。

### R6 · 专名漂移可检出且不误杀
- 封闭的现实平台/产品名词典；`东风` / `军报` / `微博` 不入词典。
- 正文与细纲 blocking；设定层的化名声明（如「抖手（现实抖音的化名）」）必须豁免。

### R7 · 活数字有唯一权威并在写前注入
- 关键数值进 `_tracking-state.json`，渲染为 `## 当前位置` 下的子弹。
- **不得新增第 8 个 `##` 栏**。
- 结算回写必须有拒绝条件，不能只靠提示语。

### R8 · 回归验收不建立在不合格样本上
- demo 的 20 章细纲当前**全部** outline-contract blocking，且 `字数目标` 是按正文实际字数倒填（20 章比值全为 1.00）。
- R2 / R3 的验收必须使用新建 fixture，不得使用 demo。

## Constraints

- **7 栏契约不动**：`CONTEXT_HEADINGS` 与 `render_context` 的 `require(headings == CONTEXT_HEADINGS, ...)` 保持不变。
- **不扩 hook**：不做跨平台 hook parity（7 个适配器：antigravity/codex/openclaw/opencode/reasonix/zcode/claude）。
- **不新增扫描器**：角色行为不变量只改文档与写前注入，不做出现性扫描。
- **副本同步走脚本**：`tracking_commit.py` 4 副本、`candidate-commit.py` 2 副本由 `scripts/sync-shared-assets.py` 同步，不手改。
- 字数权威冲突（AGENTS.md 2200–2800 且 <2000 blocking ／ `candidate-commit.py` 硬要求 pass ／ `long-mode.md` 细纲目标 90%）本批**不解决**，只登记；`quality_profile` 目前硬钉 `fanqie-long-v2`，做「按书声明」需新增 profile 轴，超出本批范围。

## 子任务映射

按执行顺序：

| # | 子任务 | 轴 | 满足 | 依赖 |
|---|---|---|---|---|
| 0 | `09-01-scan-gate-bypass` | 语言通顺 | R1 | 无（已完成） |
| 0.7 | `09-01-restore-ai-pattern-blocking` | 语言通顺 | 规则集/词表加载器 | 插队（已完成） |
| B | `09-01-quality-gate-coverage-audit` | 测试网 | 消灭 test-* 孤儿 | 插在 0.5 前 |
| 0.5 | `09-01-regression-fixture-book` | 验收基础 | R8 | 无 |
| 1 | `09-01-outline-contract-promote` | 读者爱看 | R2 | 0.5 |
| 2 | `09-01-emotion-motif-gate` | 读者爱看 | R3 | 1 |
| 3 | `09-01-semantic-scan-triggers` | 语言通顺 | R4 | 1（复用 `check` 子命令）；**推迟下一迭代**，触发谓词需针对剩余 advisory 风格类密度重做 |
| 4 | `09-01-causal-promote` | 基本毛病 | R5 | 1 |
| 5 | `09-01-name-drift-dict` | 基本毛病 | R6 | 4 |
| 6 | `09-01-metrics-ledger` | 基本毛病 | R7 | 无（但排最后） |

父子结构不是依赖系统；上表的依赖同时写进各子任务的 `prd.md`。

## Acceptance Criteria

跨子任务的整体验收：

- [x] 采用链（`candidate-commit.py promote`）上，语言门禁无法由候选正文自身内容关闭。
- [x] 新写章缺 `目标情绪` / `结尾拍ID/类型` / `期待ID/类型` / `读者验收预期` 时无法采用；fixture 书上可复现。
- [x] fixture 书上连续同 `目标情绪` 达阈值时产出 finding。
- [x] demo 20 章在新门禁下**不因历史原因变红**：`promote` 对 `imported_through_chapter` 内的章仍可运行（causal / outline-contract 均降级 advisory）。
- [x] demo 已知基线不回归：causal `--strict` 仍为 11 条（章 4,5,6,7,8,9,10,13,14,15,20）；`fanqie_length` under = 2,4,6,7,8,11,12,13,17，over = 16，18 = pass。
- [x] 第 11、20 章正文的 `抖音` 被 name-drift blocking；`微博` / `东风` / `知乎` 不 blocking；设定层化名声明不 blocking。
- [x] fixture 书上新写一章，正文结算数字与 metrics 台账一致；台账未更新时 promote 拒绝。
- [x] `scripts/check-shared-files.sh` 通过；`scripts/test-tracking-commit.py`、`scripts/test-candidate-commit.py` 通过。
- [x] `AGENTS.md` 不再引用不存在的脚本。

## Final verification

- 2026-09-02：`node scripts/quality-gate.mjs --profile release` 完成，29/32 PASS、0 FAIL。
- 3 项为环境阻断：本机缺 Playwright Chromium、Codex CLI、OpenCode CLI。
- R4 的语义扫描触发任务已从本批解除父子关系，保留为下一迭代独立 planning 任务。

## Out of Scope

- 字数权威三选一 / `quality_profile` 多档（登记为债）
- ~~`banned-words.md` 与 `check-ai-patterns.js` 硬编码词表双源~~（0.7 已恢复运行时加载器，本条划掉）
- 逐章记录回填、causal 过去时预设规则（下一迭代）
- 角色行为不变量出现性扫描
- 跨平台 hook parity

## 已知债（本批登记，不修）

1. ~~`check-ai-patterns.js` **不读** `skills/_shared/references/banned-words.md`~~ — 0.7（`5007cb8`）已恢复规则集与词表加载器，本条划掉。
2. 字数三套权威并存。
3. demo 的 `字数目标` 系倒填，`细纲目标 90%` 这套权威在 demo 上恒过。
4. ~~`promote` 不跑 `check-outline-contract.js`，且旧文档与分级策略矛盾~~ — 已按 `imported_through_chapter` 完成新章 blocking、历史章 advisory，并同步文档。

## Notes

本 PRD 的事实依据来自 2026-09-01 对 `main`（62614b9）的实跑核对，证据见 `design.md` 的「实测基线」。
