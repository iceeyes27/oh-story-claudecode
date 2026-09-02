# quality-gate 覆盖审计：消灭 test-* 孤儿

## Goal

49 个 `test-*` 中 38 个不被任何 quality-gate profile 跑到，导致红测长期无人发现（本批已撞出 2 条）。本任务查清引用图、修复审计中发现的三条真红测、把全部孤儿归入合适 profile，让测试网重新闭合。

## Requirements

- R1 引用图落盘：research/coverage-audit.md 记录 11 个可达、38 个孤儿、4 个孤儿 wrapper 的判定依据（docs/注释引用不算运行时引用）。
- R2 修复审计与 release 实跑发现的真红：
  - `test-shared-files.sh` 恢复 upstream #379 的 manifest 治理版（merge 3abf00f 静默回退，丢 4 个 guard），`test-shared-assets.py` 转绿。
  - `check-prose-policy.py` 的 `detector-style-blocking` 改为精确不变量：check-ai-patterns.js 内 `severity: 'blocking'` 仅允许 `rule-load-error` 与 `banned-word-*` 类型（0.7 恢复的作者裁意），`test-prose-policy.py` 转绿并新增负样本断言。
  - `test-scan-runtime-policy.py` Windows tempfile 清理竞态修复（best-effort 清理，不因句柄未释放误报）。
  - `check-hook-regex-sync.sh` 恢复 `0426bf9` 已进入 JS/Python hook 核、后被 merge `7c380a1` 回退的五条功能复核提示；用共享资产同步脚本更新三个 JS 部署副本，不改校验期望。
  - `test-static-check.py` 对“不适用的 Windows/WSL 子用例”输出普通说明，避免整个 `platform-gates` 在测试主体成功时被 quality-gate 误判为 SKIP；不放宽真实 SKIP 的判定。
  - `test-hook-encoding-portable.sh` 的可选平台/locale 子场景同样输出普通说明；主测试已有 cp936 等价覆盖时，不能把整个聚合检查标成 SKIP。
  - `quality-gate.mjs` 用 `import.meta.url` 解析仓库根目录，确保聚合 runner 在 Node 18 与 Node 22 下都能加载质量门模块。
- R3 孤儿归位：按 research/coverage-audit.md 的归位方案改 quality-gate.json；新增 3 个聚合 runner（test-language-gates.sh / test-narrative-gates.sh / test-platform-gates.sh）沿用 test-story-continuity.sh 聚合先例；fast profile 不动。
- R4 环境依赖测试（codex/opencode CLI e2e）用 `blocked_patterns` 归 BLOCKED，不因环境缺 CLI 误报 FAIL。
- R5 scripts/README.md 的测试表更新归位说明，避免文档继续暗示「只在本地跑」。

## Acceptance Criteria

- [x] `python scripts/test-prose-policy.py`、`python scripts/test-shared-assets.py`、`python scripts/test-scan-runtime-policy.py` 在 Windows 本机全绿。
- [x] `bash scripts/check-shared-files.sh` 输出 "Shared File Governance Check" 且 5 个子 guard 全部执行。
- [x] `npm run quality:fast` 结果不劣化（check 集不变）。
- [x] `npm run quality:affected` / `quality:release` 全绿（e2e 允许 BLOCKED）。
- [x] `bash scripts/check-hook-regex-sync.sh` 通过，`platform-gates` 为 PASS 而非子用例说明触发的 SKIP。
- [x] 49 个 test-* 无一游离于全部 profile 之外（含经 wrapper/聚合 runner 间接可达）。
- [x] `node .agents/skills/story-setup/scripts/manage-skill-adapters.js check` 通过（若触及 skills 部署镜像）。

## Verification

- `quality:fast`：7/7 PASS。
- `quality:affected`：14/14 PASS。
- `quality:release`：29/32 PASS，Dashboard/Codex/OpenCode 三项按环境依赖归 BLOCKED，零 FAIL、零意外 SKIP。
- adapter check：103/103；hook regex、shared assets、static、Windows/GBK 可移植性检查全部通过。

## Out of Scope

- 修 main 上已由 0.7 顺带修复的 prose parity（A 项仅归档诊断结论）。
- 各测试自身的断言扩充；只做归位与三红修复。
