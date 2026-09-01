# 0 · 堵住语言门禁的两个绕过口

父任务：`.trellis/tasks/09-01-quality-first-gates`
依赖：无。本批第一个执行。

## Goal

让 `candidate-commit.py promote` 上的语言门禁（`check-ai-patterns.js` + `check-degeneration.js`）**无法由写正文的一方自行关闭**。

## 背景

`scan_gate()`（`skills/story-write/scripts/candidate-commit.py:219-229`）以 `--fail-on=blocking` 跑两个确定性扫描器，这是「语言通顺」这条轴上唯一接进采用链的门禁。但它有两个绕过口：

1. `EXEMPTION = re.compile(r"去味(：|:)跳过")`（:41），在候选正文**前 6 行**命中即整体跳过（:492）。写正文的 agent 自己就能在输出里写这行。
2. `--no-scan` → `skip_scan=True`（:765 / :889），无需理由、不留痕。

## Requirements

- R1.1 移除 `EXEMPTION` 的「正文自带豁免」语义。正文内容不得决定门禁是否运行。
- R1.2 `--no-scan` 保留（作者确有跳过需求），但必须：
  - 要求同时提供 `--reason "<非空理由>"`；
  - 把 `skip_scan` 与理由写入采用回执 / 事务记录，可事后审计。
- R1.3 顺手修正 `AGENTS.md` 两处幽灵脚本引用（`AGENTS.md:65` `check-axiom-rewards.js`、`AGENTS.md:73` `check-chapter-length.js`），指向真实存在的入口或删除该条。**不写 wrapper**。

## 非目标

- 不改 `check-ai-patterns.js` / `check-degeneration.js` 的规则本身。
- 不解决 `banned-words.md` 与脚本硬编码词表的双源问题（父任务已登记为债）。
- 不改字数权威。

## Acceptance Criteria

- [x] 候选正文前 6 行写入 `去味：跳过` 后，`promote` 仍运行 `scan_gate`（新测试 `test_promote_ignores_in_prose_exemption_marker`）。
- [x] `promote --no-scan` 不带 `--reason` 时报错退出（`test_promote_no_scan_requires_reason`）。
- [x] `promote --no-scan --reason "..."` 成功后，理由可从采用回执中读到（`test_promote_records_scan_skip_reason`，回执落 `候选/_历史/采用事务-*.json` 的 `scan_skip.reason`）。
- [x] demo 的既有采用链行为不因本改动变化（不引入新 blocking）。
- [x] `grep -rn "check-axiom-rewards\|check-chapter-length" AGENTS.md` 无输出。**注**：根 `AGENTS.md` 被 `.gitignore:14` 忽略、未受版本控制，此项改动只影响本地；六份分发模板 `AGENTS.md.tmpl` 本来就不含幽灵引用。
- [x] 收尾脚本全绿：`test-candidate-commit.py` 32/32、`test-tracking-commit.py` 31/31、`test-normalize-punctuation.js` OK、`sync-shared-assets.py sync` + `check-shared-files.sh`（71 组 0 mismatch）、`quality-gate.mjs` fast 7/7。

## 实施记录

**`<!-- 去味:跳过 -->` 的真实身份比 PRD 预想的大。** 它不是随手加的绕过口，是 v0.7.0 起的文档化用户豁免，被 5 份 hook 核（antigravity/codex/opencode/templates/zcode）的「毒句式欠账门」、`normalize-punctuation.js` 的保留逻辑及其测试、`long-mode.md:337`「唯一豁免」、CHANGELOG/README/UPGRADING 共同依赖。

按 PRD Notes 的预案处置：**只摘掉 promote/check 一侧对正文标记的信任，hook 侧一行未动**。依据是仓库自己已有的方向——`candidate-workflow.md:68` 早写着「Dashboard 不暴露 `--no-scan`：采用一律过 promote 前确定性质量门（fail-closed）」。采用点本就该是收口的地方，这个标记是候选系统之前的遗留。

同步修订了四处会自相矛盾的文档：`candidate-workflow.md:54`、`.trellis/spec/skills/longform-artifacts.md:14/26`、`long-mode.md:337`（补明标记只对 hook 生效）、`AGENTS.md:65/73`。

**发现的空测**：原 `test_promote_exemption_marker_bypasses_gate` 是假的——它通过不是因为豁免生效，而是因为 `TOXIC` 样本产出的全是 advisory，`--fail-on=blocking` 根本不触发。已换成 `GATE_BLOCKING`（`check-degeneration.js` 的 `meta-leak`，真 blocking）并重写为反向断言。

**溢出发现（不在本任务范围）**：`check-ai-patterns.js` 的 24 条 blocking 规则在 merge `7c380a1` 中被整批降为 advisory，详见父任务新增的记录。
