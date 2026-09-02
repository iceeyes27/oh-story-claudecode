# quality-gate 覆盖审计实测（2026-09-01，HEAD=47c1f81，分支 feat/quality-first-gates）

## 引用图结论

49 个 `test-*` 中，被 quality-gate profile 真正跑到的只有 **11 个**：

| 通路 | 测试 |
|---|---|
| 直接引用（5） | test-candidate-commit.py · test-chapter-skeleton.js · test-tracking-commit.py · test-tracking-workflow-contracts.py · test-unified-skill-upstream-drift.py |
| 经 `contracts`（npm test:contracts，4） | test-narrative-complexity.js · test-chapter-titles.js · test-foreshadow-overdue.js · test-foreshadow-gate.js |
| 经 `codex-adapter`（1） | test-codex-hook-merge.py |
| 经 `opencode-adapter`（1） | test-opencode-plugin.mjs |

**38 个真孤儿**（docs/注释里出现的引用不算运行时引用）。另有 4 个孤儿 wrapper/checker：

- `check-antigravity-adapter.sh`（内部跑 3 个 antigravity test-*）——antigravity 是 7 适配器里唯一没进 profile 的
- `check-hook-locale-safety.sh`（对 `test-hook-encoding-portable.sh` **只有注释引用**，无调用；该测试已直挂 `platform-gates`）
- `check-hook-regex-sync.sh`（对 test-prose-net-parity.sh 只有注释引用，无调用；该测试已进 `language-gates`）
- `check-prose-policy.py`（checker 本身也没进 profile，行为由其 test 覆盖）

## 实跑结果（38 孤儿，Windows 本机）

- **33 PASS**
- **3 真红**：
  1. `test-prose-policy.py` —— `detector-style-blocking` 规则（0426bf9，08-31「全部降 advisory」方针）拦下 check-ai-patterns.js 里 9 处 `severity: 'blocking'`。这 9 处是 5007cb8（0.7）按作者裁意恢复的：1 处 `rule-load-error` + 8 处 `banned-word-*` 免语境词表族。**方针冲突：本批父 PRD R1 胜出，测试需改成「blocking 仅允许 rule-load-error / banned-word-* 类型」的精确不变量**。
  2. `test-shared-assets.py` —— 期望 stdout 含 "Shared File Governance Check"，实际是 "Shared File Consistency Check"。**根因：merge 3abf00f（08-31 07:25）把 upstream #379（5ca4da5）的 manifest 治理版静默回退成 fork 旧启发式版**，与 5007cb8 修的 check-ai-patterns.js 属同一类 merge 解冲突取错边。回退连带丢了 4 个 guard（check-reference-similarity / check-agent-reference-consumers / check-short-analysis-scope / shared-references.py check）。5 个被调脚本在 HEAD 全部存在，无人依赖旧 header → 直接恢复 `git show 0426bf9:scripts/check-shared-files.sh`（与 upstream 现版逐字一致）。
  3. `test-scan-runtime-policy.py` —— Windows tempfile 清理竞态（WinError 32，子进程仍持句柄），非仓库逻辑错。
- **2 环境红**：test-codex-cli-e2e.sh / test-opencode-cli-e2.sh（CLI 不在 PATH；用 `blocked_patterns` 归 BLOCKED）。

## A 项诊断（test-prose-net-parity.sh）

- **main（62614b9）上红**：`nostate :: block`，4 failures —— 与计划描述一致。
- **本分支 HEAD 绿**（5007cb8 恢复规则集时一并修复）。A 不需要修，只需把该测试接进 profile 防再烂。
- 顺带发现第三起同类 merge 回退（check-shared-files.sh），说明「merge 静默回退」是系统性风险，值得写进 spec。

## 归位方案（实施于 quality-gate.json）

新增聚合 runner（沿用 test-story-continuity.sh 可调用其他 test 的先例）：

| 新 check | runner | 内容 | profile |
|---|---|---|---|
| `language-gates` | scripts/test-language-gates.sh | ai-patterns · degeneration · prose-policy · normalize-punctuation · charcount-portable · prose-backstop-hook · prose-net-parity | affected + release |
| `narrative-gates` | scripts/test-narrative-gates.sh | outline-causal · outline-contract · outline-copy · phase2-contract · delivery-contract · scan-contract · scan-runtime · scan-runtime-policy · review-state · story-continuity · chapter-completion-lifecycle · longform-stability · state-store · author-memory-commit · flow-state | release |
| `platform-gates` | scripts/test-platform-gates.sh | zcode-hooks · reasonix-adapter · codex-hooks · skill-numbering · storyctl · current-skill-contracts · shared-assets · shared-references · static-check · hook-encoding-portable · quality-gate.test.mjs | release |
| `quality-lifecycle` | 直跑 test-quality-lifecycle.py | 90s，单独成 check | release |
| `antigravity-adapter` | 直跑 check-antigravity-adapter.sh | 与其他 6 适配器对齐 | release |
| `hook-regex-sync` | 直跑 check-hook-regex-sync.sh | 5 份 hook 核正则同步 | release |
| `hook-locale-safety` | 直跑 check-hook-locale-safety.sh | 静态 locale 守卫（不跑行为测试） | release |
| `codex-cli-e2e` | test-codex-cli-e2e.sh + blocked_patterns | CLI 缺失→BLOCKED | release |
| `opencode-cli-e2e` | test-opencode-cli-e2e.sh + blocked_patterns | 同上 | release |

修复三红后落地；fast profile 不动。

## 追加：聚合 runner 暴出两条 Windows-only 可移植性红（2026-09-02，HEAD=47c1f81）

把孤儿测试接进 `language-gates` 聚合后，顺序执行在 Windows 本机连撞两条**新**红——均为 Linux 审计看不见的环境可移植性问题（本文件 L33「本分支 HEAD 绿」的结论建立在 python3 可用的机器上）。两条都**不是 hook/生产逻辑 bug**，修在测试侧。

### 红 1 · test-prose-backstop-hook.sh（Windows 10/10 稳定红）

- **现象**：`post-Edit/MultiEdit output is not valid hook JSON` + `missed prose findings`，共 16 fails；`JSON.parse("")` 炸。
- **根因**：测试用 `mktemp -d` 得 MSYS 路径 `/tmp/tmp.xxx`。Git Bash 把 **argv** 里的 `/tmp/...` 自动转成原生 Windows 路径，但 **env/stdin 内容**（塞进 payload 的 `file_path`）不转。hook 收到的 ROOT（走 argv，已转）与 payload 目标路径（未转，`path.resolve` 映射到当前盘根 `C:\tmp\...`，不存在）解析到不同位置 → `pathWithin` 失败 → 目标被丢 → 空输出。核心函数 `proseAfterWrite` 用真实路径直调**正常**，证明 hook 无辜。
- **修复**：`TMP="$(cygpath -m "$TMP" 2>/dev/null || printf '%s' "$TMP")"`——混合式 `C:/...`（正斜杠）让 bash 文件操作、Node `path.resolve`、JSON 无转义三者一致；Linux 无 cygpath 时回退 `/tmp` 不变。
- **验证**：修后 5/5 通过（symlink 别名用例在 Windows 无符号链接时 SKIP，已被原 guard 覆盖）。

### 红 2 · test-prose-net-parity.sh（Windows 稳定红）

- **现象**：`功能 parity 不一致（codex python 网 vs zcode JS 网）`，diff `0a1,46`——python 侧 0 行、JS 侧 46 行；D 段「写正文守卫 parity」`nostate :: pass/block` 亦随之漂移。
- **根因**：测试**裸调 `python3`**，Windows 上落到 Microsoft Store 占位程序（exit 49、空输出），而 `command -v python3` 仍返回桩路径使可用性守卫失效。python 网整体产空 → parity 假性 diff。属仓库既有「Windows python3 桩」类问题（`scripts/python3-shim.sh` 已为 6 个 check-*.sh 兜底，test-*.sh 历史上裸调）。
- **修复**：ROOT 校验后 `. "$ROOT/scripts/python3-shim.sh"`——定义同名 shell 函数委托真 `python`（命令替换继承函数）；Linux 上 python3 可用则 no-op。
- **验证**：修后四段 parity 全过；`test-language-gates.sh` 聚合整体 exit 0。

### 未决 · release-only 聚合待复验

`narrative-gates` / `platform-gates`（仅 release profile）含更多裸调 python3 的 `.sh`（codex-hooks / hook-encoding-portable / skill-numbering / zcode-hooks / story-continuity 等）。聚合 runner 本身已用 `for c in python3 python py` 解析 `PYBIN` 正确回退，但被它们调用的子 `.sh` 各自是否兜底需在 `quality:release` 实跑逐条确认，红则同样按「自带解析 or source shim」处理，不动生产逻辑。

## 追加：release 复验发现 hook 合并回归与 platform 误判（2026-09-02）

### hook-regex-sync · merge `7c380a1` 回退了实现文案

- `check-hook-regex-sync.sh` 报 10 处缺失：五条功能复核提示分别未出现在 JS/Python hook 核。
- `git show 0426bf9` 证明五条提示当时已同时进入 canonical JS、Codex Python 与三个 JS 部署副本；merge `7c380a1` 把实现恢复成旧祈使式文案，但保留了新校验。
- 这是已有实现的合并回归，不是待定文案。修复应恢复 `0426bf9` 的五条提示，再运行 `scripts/sync-shared-assets.py sync`；不修改 `check-hook-regex-sync.sh`，也不把 hook 展示文案复制进 `check-ai-patterns.js`。

### platform-gates · 子用例说明被提升为整个 check 的 SKIP

- `test-static-check.py` 在 Windows/WSL 子用例不适用时打印行首 `SKIP:`，但测试主体继续成功退出。
- `quality-gate.mjs` 会把任一行首 `SKIP:` 识别为整个 check 的 SKIP，因此 `platform-gates` 虽 exit 0 仍令 release 聚合成为 BLOCKED。
- 最小修复是把这两条子用例输出改为 `note:`；真实环境跳过仍由 quality-gate 的既有语义处理。
- release 复验又发现 `test-hook-encoding-portable.sh` 的可选盘符/GBK 子场景使用同一行首标记；四条说明统一改为 `note:`，主测试的 cp936 等价覆盖与最终 PASS 不变。

### platform-gates · WSL Node 18 无 `import.meta.dirname`

- `test-platform-gates.sh` 在 WSL 中调用 Node 18；`quality-gate.test.mjs` 导入 `quality-gate.mjs` 时，Node 18 不提供 `import.meta.dirname`，导致模块加载失败。
- 仓库同时覆盖 Node 18/22，根路径改为 `dirname(fileURLToPath(import.meta.url))`；Windows Node 22 与 WSL Node 18 的同一测试均通过。
