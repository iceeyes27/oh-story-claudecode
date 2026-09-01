# 0.7 · 恢复 check-ai-patterns 的规则集与严重度

父任务：`.trellis/tasks/09-01-quality-first-gates`
插队执行（作者 2026-09-01 决定），排在 `09-01-regression-fixture-book` 之前。

## 调查结论：这是两个问题，不是一个

### 问题 A · merge 事故（无争议，纯回归）

commit `7c380a1` "Merge origin/main: quality lifecycle and Antigravity" 取了 stale base：

| | 行数 | rule type 数 | blocking |
|---|---|---|---|
| `7c380a1^1`（本地 main，`skills/_shared/scripts/`） | 2129 | 38 | 24 |
| `7c380a1^2`（incoming，4 个旧布局路径） | 1436 | 21 | 0 |
| 合并结果 = 当前 HEAD | 1436 | 21 | 0 |

`^2` 把该文件放在合并前就已废弃的 4 个路径（`story-deslop` / `story-long-write` / `story-review` / `story-short-write`），而 main 已统一到 `skills/_shared/scripts/`。合并解冲突时取了 `^2` 的旧文件。

**丢失的 17 个规则族**（`^1` 的类型集是 `^2` 的严格超集，合并未新增任何类型）：

```
abstract-authority-slogan   banned-word-abstract-forced  banned-word-antithesis
banned-word-body-shell      banned-word-dangling-identity banned-word-exact
banned-word-pain-object     banned-word-physical-clear   banned-word-syna
contrast-rhetorical         english-residue              grey-crack-in-head
narration-slogan            negation-only-parallel       process-term-as-object
rule-load-error             summary-slogan
```

**同时丢失：`banned-words.md` 的运行时加载器。** `^1` 在 :1590/:1622 用 `readFileSync(path.join(__dirname,'..','references','banned-words.md'))` 解析「一级禁用词」「通感隐喻」「对仗反义俏皮话」三段，并有 `rule-load-error` 兜底（文案：「禁止回退到 skill-local 旧副本」）。

> **修正父任务已知债 #1**：此前记录的「`banned-words.md` 353 行但脚本不读、手工双源」是在描述**损坏后的状态**。设计本来是运行时读文件的，是 merge 把加载器删掉了。

**完好副本**：`.claude/worktrees/sweet-grothendieck-9151bf/skills/_shared/scripts/check-ai-patterns.js` 与 `7c380a1^1` 逐字节一致。

### 问题 B · 他人的有意决策（需作者拍板）

commit `0426bf9` "feat: close P1 story quality lifecycle"（yolanda hao，2026-08-31，133 文件 / 21665 插入 / 单行 commit message）：

- **故意**把 `severity: 'blocking'` 改成 `'advisory'`，28 处（7 条规则 × 4 份副本）
- 新增方针段：「All findings are advisory style/readability evidence, not AIGC verdicts or **automatic rejection rules**. … only semantic review can decide whether it harms clarity, continuity, voice, or pacing.」

该 commit **没有把强制搬到别处**：同批新增的 `scripts/check-prose-policy.py` 是对 `skills/` 文档里过宽写作规则的元检查（拒绝「每章结尾必须有未解悬念」这类全局断言），不是正文强制层，且只被自己的测试引用。

所以降级 = 移除强制，没有替代。

## 现状影响

`candidate-commit.py` 的 `scan_gate()` 以 `--fail-on=blocking` 调用本脚本 → **在采用链上永久空跑**。今天唯一能拦住采用的语言检查只剩 `check-degeneration.js` 的 5 条（复读 / 截断 / 占位拒绝语 / tier1 工程词泄漏）。

与仓库内文档矛盾：`CHANGELOG.md:193`、`skills/story-setup/UPGRADING.md:349/355` 均称 voice-contrast / negation-parade / reverse-not-is / trailer-ending / trailer-summary 为「blocking，经真人语料零误报校准」。

**未受影响**：5 份 hook 核的「毒句式欠账门」用自带 `toxicPhraseFindings()`，不读本脚本 severity，写前拦截仍有效。问题只在采用链一侧。

## Requirements

- RA · 恢复问题 A 丢失的 17 个规则族与 `banned-words.md` 运行时加载器。`^1` 是严格超集，恢复无损。
- RB · 严重度策略按作者裁决（见下方「待裁决」），不得由实现方自行决定。
- RC · `^2` 独有的 51 行中的真人语料校准注释（qimao 5584 章 / heiyan 3983 篇的误报率数据）必须保留，不能因恢复 `^1` 而丢失。
- RD · 文档与代码对齐：无论裁决结果如何，`CHANGELOG.md:193`、`UPGRADING.md:349/355` 与实际 severity 必须一致。
- RE · 恢复后 `scan_gate` 对 demo 20 章的实际拦截面必须实测并记录，避免一恢复就全书变红。

## 裁决（作者，2026-09-01）

**只让词表类 blocking。** severity 按「判定是否需要语境」两分：

| 档 | 规则 | 依据 |
|---|---|---|
| blocking（9） | `banned-word-*` 八条 + `rule-load-error` | 判据来自 `banned-words.md` 明文，不需语境 |
| advisory（其余） | `voice-contrast` / `negation-parade` / `reverse-not-is` / `trailer-ending` / `trailer-summary` / `em-dash` / `english-residue` / 各 `*-tic` / `contrast-rhetorical` / `grey-crack-in-head` / `narration-slogan` / `summary-slogan` / `abstract-authority-slogan` / `negation-only-parallel` / `process-term-as-object` | 需语境判断，交语义审查 |

理由：既尊重 `0426bf9` 方针里「风格需语境判断」的合理部分，又让采用链真的能拦住客观的 AI 味词。`english-residue` 特别降级——本仓库 demo 是军宣短视频题材，MV/BGM 是正当行业词。

## 实施记录

**做法：三方合并，不是覆盖。** 两侧各有独有内容，简单取一边都会丢东西。

```
merge-base d1f8858 (2026-08-25)  1371 行 / 20 types / 7 blocking
ours   = 7c380a1^1               2129 行 / 38 types / 24 blocking
theirs = 7c380a1^2               1436 行 / 21 types / 0 blocking
结果                              2153 行 / 38 types / 9 blocking
```

`git merge-file` 产生 7 处冲突：5 处 ours 侧为空的纯注释增补，自动取 theirs；2 处手工：

1. **文件头方针段**——两侧都改了，重写为准确描述新两档策略的段落，而不是二选一。
2. **`trailer-summary` 的 severity/message**——theirs 侧代码用 `summaryMatch` 变量，而合并后的上下文是 ours 侧的 `match`。直接取 theirs 会引入未定义变量。取了 theirs 的 severity 与更好的 message，保留 ours 的 `match`。

**demo 实测（新策略）**：19/20 章、115 条 blocking，全部 `banned-word-exact`（「一丝」「仿佛」「缓缓」「深吸一口气」「如同」「隐约」），均为真阳性。不阻塞 demo——`scan_gate` 只扫候选正文，不回头重扫已入正稿的章；实际效果是第 21 章起会被真正把关。对比全量恢复 24 blocking 的话是 20/20、150 条，多出的 30 条 `english-residue` 全是 MV/BGM 误杀。

**沿途发现的两条陈旧红测（均在 HEAD 上就已失败，与本次改动无关）**：
- `scripts/test-ai-patterns.sh`：`0426bf9` 降 severity 时没更新自己的回归测试，自 2026-08-31 起一直红。本任务已修好。
- `scripts/test-prose-net-parity.sh`：「写正文守卫 parity 不一致（Claude bash guard vs JS core）：nostate :: pass vs block」。**未修，另行处理**。

两者都不在 `quality-gate.mjs` 里，所以长期无人发现。

**文档处理**：`CHANGELOG.md:193` 与 `UPGRADING.md:349/355` 是历史发布条目，不改写历史；改为在「未发布」新增三条记录当前变更。

## Acceptance Criteria

- [x] 17 个规则族回归，rule type 计数 21 → **38**
- [x] `banned-words.md` 运行时加载生效（「一丝」「仿佛」被拦）；清空词表时 `rule-load-error` 三段全部触发
- [x] `^2` 的真人语料校准注释与 `套式反应` / `trailer-summary` / `quote-emphasis-tic` 规则完整保留
- [x] severity 分布符合裁决（9 blocking，全为词表类）；`CHANGELOG.md` 未发布段已对齐
- [x] demo 实测结果记录在上方
- [x] `test-ai-patterns.sh` 全绿（HEAD 上为红）、`test-candidate-commit.py` 32/32、`check-shared-files.sh` 71 组 0 mismatch、`quality-gate.mjs` fast 7/7、`check-release-manifest.mjs` PASS、`check-doc-budget.sh` PASS
- [ ] `test-prose-net-parity.sh` —— **未通过，且 HEAD 上即已失败**，属既有缺陷，另立任务
