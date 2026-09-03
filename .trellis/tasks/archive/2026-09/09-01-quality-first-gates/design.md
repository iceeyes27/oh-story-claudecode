# 设计 · 提质优先门禁重排

## 实测基线（2026-09-01，main @ 62614b9）

所有数字为实跑结果，子任务改动后必须重新冻结。

| 事实 | 位置 / 证据 |
|---|---|
| 7 栏契约硬校验 | `skills/story-write/scripts/tracking_commit.py:684` `require(headings == CONTEXT_HEADINGS, ...)` |
| `## 当前位置` 现有 4 条子弹，无数字 | `render_context()` 同文件 :655-664 |
| `TRACKING_SCHEMA_VERSION = 4`，`DELTA_MAX_BYTES = 3072`，`CONTEXT_MAX_BYTES = 12288` | 同文件 :31-38 |
| 测试钉死 schema 4 | `scripts/test-tracking-commit.py:193` |
| `candidate-commit.py` 子命令只有 promote / recover / reject / list | 同文件 :864-880 |
| promote 已有 preflight：skeleton / title / outline-copy / first-mention(rc-01) / arc-ledger(仅第 15 章) / fanqie 字数 / scan_gate | 同文件 :219-229, :471-494 |
| 语言门禁两个绕过口 | `EXEMPTION = /去味(：|:)跳过/` :41，命中前 6 行即跳过 :492；`--no-scan` → `skip_scan` :765/:889 |
| `check-ai-patterns.js` 1436 行、约 24 类指纹；`check-degeneration.js` 330 行 | `skills/_shared/scripts/` |
| 词表双源 | ~~`banned-words.md` 353 行；脚本不读该文件~~ — 已随 `5007cb8`（0.7）恢复运行时加载器，父任务已知债 #1 划掉 |
| `目标情绪` **已是必填** | `check-outline-contract.js:24` `FIELDS`；:35 `INTENT_FIELDS`「实测直接影响正文质量，必须有实际内容」 |
| 该检查不在 promote，且对旧细纲明确不阻断 | `skills/story-write/references/artifact-protocols.md:274` |
| demo 20 章**全部** outline-contract blocking | 逐章实跑：`outline.required-fields` + `outline.reader-contract` + `outline.plotpoint-table`；缺字段 = 单元ID/位置、目标情绪、主角目标/关键选择、结尾拍ID/类型、期待ID/类型、读者验收预期、章节定位、契约风险 |
| demo `字数目标` 系倒填 | 20 章 `actual / 目标` 比值全为 1.00 |
| demo causal `--strict` = 11 blocking | 章 4,5,6,7,8,9,10,13,14,15,20 |
| `--from=N` 与 `--from N` 两种写法均可用 | 实跑确认 |
| demo 为导入书 | `imported_through_chapter=20`, `last_committed_chapter=20`, `state_revision=0`，无逐章记录目录 |
| 抖音泄漏分布 | 正文 11/20 章（真泄漏）、细纲 11 章（真泄漏）、`背景设定.md:30` 与 `金手指.md:88`（合法化名声明，须豁免） |
| `quality_profile` 硬钉常量 | `candidate-commit.py:441` |
| 幽灵脚本 | `AGENTS.md:65` `check-axiom-rewards.js`、`AGENTS.md:73` `check-chapter-length.js`，全仓库不存在。**修正（子任务 0 实施时查明）**：根目录 `AGENTS.md` 被 `.gitignore:14` 忽略、未纳入版本控制，是本地工作文件；`skills/story-setup/references/*/AGENTS.md.tmpl` 六份分发模板均不含这两个引用。所以这是本地配置问题，不是会随发布扩散的仓库缺陷——修了仍有价值（本地 agent 会读它），但不计入提交 |
| 副本同步已自动化 | `scripts/shared-assets.json` 组 `story-tracking-transaction`(1+3)、`story-candidate-transaction`(1+1)；`scripts/sync-shared-assets.py` + `scripts/check-shared-files.sh` |

## 执行中发现的回归（2026-09-01，子任务 0 实施时）

**`check-ai-patterns.js` 的全部 blocking 规则已在一次 merge 中丢失。**

```
7c380a1^1 (合并前 main)  : 24 条 severity: 'blocking'
7c380a1^2                : 该路径不存在此文件
7c380a1  (合并结果)      : 0 条
当前 main / HEAD         : 0 条
```

commit `7c380a1` "Merge origin/main: quality lifecycle and Antigravity"。另一父根本没有这个文件，正常合并应保留 ^1 的版本，结果却产出了 0 blocking 的版本——是解冲突时被错误覆盖。

**后果**：`scan_gate` 用 `--fail-on=blocking` 调用它，而它已无 blocking 规则，**在采用链上是永久空跑**。目前唯一能拦住采用的语言检查只剩 `check-degeneration.js`（复读 / 截断 / 占位拒绝语 / tier1 工程词，5 条 blocking）。

**与文档矛盾**：`CHANGELOG.md:193` 与 `story-setup/UPGRADING.md:349` 都写着 voice-contrast / negation-parade / reverse-not-is / trailer-ending 是「blocking，经真人语料零误报校准」。实际全是 advisory。

**未受影响**：5 份 hook 核的「毒句式欠账门」用自带的 `toxicPhraseFindings()`，不读 `check-ai-patterns.js` 的 severity，仍然有效。所以问题只在采用链这一侧。

**对本批计划的影响**：父任务 `prd.md` 的三轴表里「语言通顺：装备最好，只差堵洞与触发」需要下调——装备是在的（1436 行规则），但在采用链上被降级成了纯建议。这比子任务 0 和 3 加起来更直接地决定「语言通顺」。建议作为独立子任务处理：恢复 24 条 severity 需要逐条按真人语料复核误报率，不是简单 revert。

## 架构决策

### D1 · 所有新门禁挂在 `candidate-commit.py`，不碰 hook

promote 已是唯一写入口，且已有稳定的 `run_node(...) + require(returncode == 0, ...)` 惯例（:226, :253, :348, :490）。新检查一律沿用该惯例，作为 `validate_binding` 的 preflight。

理由：hook parity 要跨 7 个适配器，成本与收益不成比例；采用链是所有平台共用的收口点。

### D2 · 新增 `candidate-commit.py check` 子命令

`promote` 是作者「采用」的写入口，不能兼作「写完自检」的门禁——否则写作 agent 会在作者拍板前把候选搬进正文。

- `check --project ... --chapter N`：跑与 promote **相同**的 `validate_binding`，但不移动文件、不提交事务、不改 `_tracking-state.json`。
- 实现方式：`validate_binding` 已经是纯校验函数，`promote_chapter` 在其后才做搬运。新子命令复用前者即可，不复制校验逻辑。
- `AGENTS.md` 表述：**写完候选后跑 `check`；作者采用时跑 `promote`**。禁止合并成「一条命令」。

归属：在子任务 1 内实现，子任务 3、4 复用。

### D3 · 严重度分级策略：按 `imported_through_chapter` 切分

所有新接入的、依赖细纲质量的检查（outline-contract、causal、母题连排）统一采用：

```
chapter <= state["imported_through_chapter"]  → advisory（记录，不阻断）
chapter >  state["imported_through_chapter"]  → blocking
```

理由：demo 与所有导入书的历史章不是本工具链的产物，用新契约追溯问责会让作者直接拆门禁。这条策略必须实现为**一处共享判定**，不在每个检查里各写一遍。

### D4 · 检查位置：出骨架前 + 采用时，两处都跑

细纲类检查（outline-contract、causal）在**写正文之前**最便宜。只挂 promote 等于写完整章再因细纲措辞被拒。

- 出骨架前：`--from N --to N` 本章范围，拦截；
- `check` / `promote`：再跑一次防漏。

### D5 · 母题复用 `目标情绪`，不新增字段

`目标情绪` 已在 `FIELDS` 与 `INTENT_FIELDS` 中。新增第二个母题字段会造成一本细纲两个情绪字段，重演「金手指 vs 公理点」的双源问题。

改动限于：给该字段加闭合词表校验 + 跨章连排判定。

### D6 · metrics 进 state，渲染为 `## 当前位置` 子弹

```
state["metrics"]  # 缺省 {}，旧书兼容
  → render_context() 在 "## 当前位置" 追加一条：
    "关键数值：抖手粉 100 万｜《如愿》播放 1 亿｜国运 +30000｜任务「老兵的愿望」已结算"
```

约束：
- `CONTEXT_HEADINGS` 不变，`require(headings == CONTEXT_HEADINGS, ...)` 仍成立；
- 名目用**原文措辞**（「话题热度 300 万+」≠「播放量」）；
- 每笔事务交**全量当前表**（与 `character_snapshots` 一致），不交 delta；
- 受 `CONTEXT_MAX_BYTES = 12288` 约束，metrics 渲染需有条目上限与截断策略；
- root `require_known_keys`（`tracking_commit.py:841`）与 `normalize_delta` 的已知键集合都要加 `metrics`；
- schema 版本是否 4→5：**倾向不升**。`metrics` 缺省 `{}` 且旧 state 不含该键时按空表处理，可保持 schema 4，避免改 `test-tracking-commit.py:193` 与 4 份副本的版本常量。此决策在子任务 6 的 `design.md` 内最终敲定。

### D7 · 回写拒绝条件

「结算后请更新台账」是 agent 记性，不是门禁。采用二选一（子任务 6 敲定）：

- (a) 每笔事务必须带完整 metrics 快照（空表也要显式 `{}`），schema 拒收缺字段；或
- (b) 正文命中结算句式（`叮`/`国运`/`任务完成`/`粉丝突破` 等封闭句式表）而 metrics 相对前一 revision 无变化 → promote 拒绝。

(b) 更贴近「杀死结算幻觉」的目标，但需要句式表；(a) 更便宜但只保证在场不保证正确。倾向 **(a) 打底 + (b) 收口**。

### D8 · 专名词典范围与豁免

- 词典只收**封闭的现实平台/产品名**：抖音、快手、B站/哔哩哔哩、微信、小红书、知乎、微博（微博是否入表由书级声明决定）。
- `东风`、`火箭军`、`军报` **不入词典**——demo 明确保留。
- 书级架空声明文件（`设定/世界观/*.md`）中的化名 gloss 必须豁免：`背景设定.md:30`「短视频平台『抖手』（现实抖音的化名）」、`金手指.md:88`「抖手（类抖音）」都是合法用法。**声明文件自身必然包含真名**，这是自指问题，必须在词典范围里显式处理。
- 人名编辑距离 1（`钟嘉嘉`/`钟嘉佳`）只 advisory；别名从角色快照的 `identity` 与设定里的称呼运行时派生，不建手工别名表。

### D9 · 写前注入并进现有派生内容，不新开块

`long-mode.md` 的 Phase 4 写前准备已极为庞大（状态筛选 + 模块召回 a–h + 指令确认）。新内容一律并进 `追踪/上下文.md` 的派生内容：

- 关键数值 → `## 当前位置` 子弹（D6）
- 禁改专名 → 运行时从角色快照名 + 书级架空声明生成
- `_tracking-state.json` 继续**不进** prompt

### D10 · 收尾统一走脚本

每个子任务收尾固定跑：

```bash
python scripts/sync-shared-assets.py
bash scripts/check-shared-files.sh
python scripts/test-tracking-commit.py
python scripts/test-candidate-commit.py
node scripts/check-release-manifest.mjs
```

副本同步是脚本行为，不是手改 4 份文件。

## 兼容性与回滚

- 每个子任务独立可回滚（单独 commit，分支 `feat/quality-first-gates`）。
- 风险最高的是子任务 1 与 6：前者引入新 blocking，后者改 tracking schema 面。二者都必须先在 fixture 书上验证，再对 demo 跑一次「不因历史原因变红」的回归。
- 若 D3 的分级策略实现有误，症状是 demo 无法 promote —— 这是本批最可能的破坏形态，回归验收里已单列。

## 未决问题

1. metrics 保持 schema 4；旧 state 缺字段按空表读取，新事务必须提交结构化全量 metrics。
2. 母题连排阈值确定为 3 章 advisory、4 章 blocking。
3. `artifact-protocols.md` 已改为按 `imported_through_chapter` 分级：新章阻断、历史章 advisory。

## 最终验证（2026-09-02）

- demo causal 严格基线仍为 11 条：章 4、5、6、7、8、9、10、13、14、15、20。
- demo 字数基线保持：under = 2、4、6、7、8、11、12、13、17；over = 16；18 = pass。
- tracking 36 项、candidate 46 项及共享资产、平台适配器检查通过。
- release profile：29/32 PASS、0 FAIL；Dashboard E2E、Codex CLI E2E、OpenCode CLI E2E 因本机依赖缺失标记为 BLOCKED。
