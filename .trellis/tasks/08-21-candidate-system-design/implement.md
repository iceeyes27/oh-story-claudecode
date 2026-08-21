# 候选系统 · 执行计划

> 顺序按依赖排列；每步含验证命令与回滚点。MVP 只做长篇 mode=long、单章 + 逐章确认候选。

## 实现记录（2026-08-21）

**关键简化**：narrative-writer 的输出路径本就是 prompt 参数、追踪事务 JSON 本就由主会话构造，故候选流程可**完全在 SKILL 层编排**——写候选路径 + 主会话暂存事务不 commit + 审批门。因此**步骤 2（改 agent 定义 + bump agents_version）在 MVP 中不需要**，跨端 parity 无变更风险。

**已完成**：
- 步骤 1 ✓ `skills/story-write/scripts/candidate-commit.py`（promote/reject/list，move-first+失败回滚）+ `scripts/test-candidate-commit.py`（10 用例全绿）。
- 步骤 3 ✓ `references/candidate-workflow.md` + SKILL.md 候选模式小节、Phase 4 step7/12 分支、参考索引接入。
- 步骤 4 ✓ 质量网覆盖候选（由 candidate-workflow.md 规定，作用于候选文件）。
- 验证 ✓ static-check 30/30、current-skill-contracts、shared-files、upstream-drift、tracking(31)+candidate(10) 回归全绿。AC5 由 tracking 测试与 opt-in 设计保证。

**MVP 外（未做，留扩展）**：步骤 2 agent 原生参数、步骤 5 中 hook 路径覆盖候选（`check-story-setup-deployment.sh` 的 `Claude Bash prose pre-guard` FAIL 为 **main 既有**、与本任务无关）、日更批量候选、dashboard 审阅视图、短篇候选、README/CHANGELOG（步骤 6，待用户决定是否本轮提交时再补）。


## 步骤 0 — 基线固化（回归护栏）
- [ ] 跑现有相关测试建立绿基线：
  ```bash
  python skills/story-write/scripts/tracking_commit.py --help
  bash scripts/test-tracking-commit.py 2>/dev/null || python scripts/test-tracking-commit.py
  bash scripts/test-longform-stability.sh
  ```
- [ ] 记录当前 `agents_version`（应为 25）与 `scripts/current-contract.json`。
- 回滚点：本步只读，无改动。

## 步骤 1 — candidate-commit.py（核心脚本，先行且可独立测试）
- [ ] 新建 `skills/story-write/scripts/candidate-commit.py`：`promote` / `reject` / `list` 三子命令（契约见 design 3.2）。
- [ ] promote 复用 `tracking_commit.py commit` 回放暂存事务；失败语义对齐（move 失败不推进、commit 失败可重跑）。
- [ ] 新建测试 `scripts/test-candidate-commit.py`（参照 `scripts/test-tracking-commit.py`）：覆盖 promote 幂等、reject 归档、追踪不提前推进、commit 失败重跑。
- 验证：
  ```bash
  python scripts/test-candidate-commit.py
  ```
- 回滚点：删除两个新文件即可，无外部依赖。

## 步骤 2 — narrative-writer 候选模式（agents_version bump）
- [ ] 在 narrative-writer 各端定义（`.claude/agents/`、`skills/story-setup/references/{opencode,codex,...}/agents/`）加 `candidate_mode` / `output_dir` 参数：候选模式写候选路径 + 暂存事务 JSON、不 commit；非候选模式逐字节不变。
- [ ] bump `agents_version` 25→26；同步 `scripts/current-contract.json` 与各端 parity 清单。
- 验证：
  ```bash
  bash scripts/check-claude-adapter.sh && bash scripts/check-codex-adapter.sh && bash scripts/check-opencode-adapter.sh
  python scripts/check-current-skill-contracts.py
  ```
- 回滚点：还原 agent 定义与 agents_version。

## 步骤 3 — story-write SKILL 候选路由与审批门
- [ ] SKILL.md：模式路由新增「候选/逐章确认/先给我看」；裸调用诊断展示「候选中：第X章待审」。
- [ ] Phase 4 step 7/12 加候选分支；Phase 5「写后同轮清零」明确覆盖候选文件 + 审批门话术（采用/重写/弃用 → candidate-commit 命令）。
- [ ] 抽 `references/candidate-workflow.md` 承载完整候选流程，SKILL.md 只留入口（控制 1019 行膨胀）。
- 验证：
  ```bash
  python scripts/check-current-skill-contracts.py
  bash scripts/check-unified-skill-upstream-drift.py 2>/dev/null || python scripts/check-unified-skill-upstream-drift.py
  ```
- 回滚点：还原 SKILL.md 与删除 references 新文件。

## 步骤 4 — 质量网覆盖候选（SKILL 级，先不动 hook）
- [ ] SKILL Phase 5 明确：候选文件也跑 `check-ai-patterns.js` / `check-degeneration.js` / `normalize-punctuation.js` / `check-outline-copy.js`，blocking 当轮清零后才提示审阅。
- [ ] 「毒句式欠账门」在候选模式由审批门承接，文档说明二者关系。
- 验证：对一个候选样例文件手动跑上述脚本，确认命中被清零。
- 回滚点：还原 Phase 5 文案。

## 步骤 5 — story-setup 打包与跨端 parity
- [ ] 确认新脚本随 `/story-setup` 分发到目标项目；更新 `scripts/local-only-skill-set.json` / `platform-skill-set.json`（如涉及）。
- [ ] 跑部署与 parity 检查。
- 验证：
  ```bash
  bash scripts/check-story-setup-deployment.sh
  bash scripts/check-shared-files.sh
  bash scripts/test-prose-net-parity.sh
  ```
- 回滚点：还原打包清单。

## 步骤 6 — 回归 + 文档
- [ ] 跑全量相关测试确认 AC5（未开启候选行为不变）：
  ```bash
  bash scripts/test-longform-stability.sh
  bash scripts/test-story-continuity.sh
  python scripts/test-tracking-commit.py
  python scripts/test-candidate-commit.py
  ```
- [ ] README / README_EN / CHANGELOG 记候选系统、agents_version 26、「重跑 /story-setup 新开会话」。
- 回滚点：文档独立，可单独还原。

## 审查门
- 步骤 1 完成后：脚本契约 + 测试先过，再动 agent/SKILL（降低返工）。
- 步骤 2、5 完成后：跨端 parity 必须绿，否则阻断。
- 全部完成后：`trellis-check` 全量走一遍再提交。

## 验证命令汇总
```bash
python scripts/test-candidate-commit.py
python scripts/test-tracking-commit.py
python scripts/check-current-skill-contracts.py
bash scripts/check-story-setup-deployment.sh
bash scripts/test-prose-net-parity.sh
bash scripts/test-longform-stability.sh
```
