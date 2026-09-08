# 验收记录

2026-09-08：实现及验收完成，任务进入 review；未提交、未推送、未执行后续上游 prepare。

## 完成内容

- release 保留 29 项；Codex CLI 和 Dashboard 浏览器 E2E 归入 external，原环境阻断判定不变。
- 移除 OpenCode 部署资产、平台入口及当前支持说明；保留历史记录、合成夹具和禁止回归规则。
- 恢复 Claude hooks 部署清单、settings 合并步骤和参考行，并增加误删回归验证。
- 旧 sentinel 含不受支持目标时停止并要求重新选择，保留旧目录与原 sentinel。
- 上游六类 OpenCode 路径自动 forbidden，保留其他平台与 Trellis 范围。
- 三个既有扫描器测试按当前规则分类契约修复；保留命中与负例，额外验证作者禁令 blocking 和完整大 JSON。扫描器生产规则未改。

## 实跑证据

| 验收 | 结果 | 证据 |
|---|---|---|
| affected | PASS 18/18 | affected.json / affected.log |
| release | PASS 29/29，0 FAIL、0 BLOCKED | release.json / release.log |
| 适配入口最终检查 | PASS 103/103 | manage-skill-adapters.js repair 后 check |
| 部署专项 | PASS TS1–TS12 | deployment.log |
| 适配与共享规则测试 | PASS 14/14 | adapter-tests.log |
| 外部 profile / 上游策略回归 | PASS 8/8 | node --test scripts/quality-gate.test.mjs scripts/sync-upstream.test.js；亦由完整 profiles 覆盖 |
| 发布清单与 diff 空白检查 | PASS | check-release-manifest.mjs；git diff --check HEAD |
| OpenCode 跟踪文件 | 仅剩排除范围内历史证据 | git ls-files '*opencode*' |

两份完整报告的 config_sha256 均与最终 quality-gate.json 一致。release 报告时间为 2026-09-08T01:39:52 UTC。WSL 契约测试较慢，但已完整结束，未用专项结果替代。

测试生成了 Python 缓存，导致平台适配源摘要变化；完整测试结束后通过生成工具重新 repair/check，最终 103/103。未手工修改生成 manifest。

external 未运行：本任务明确不要求安装 Codex CLI 或下载 Playwright 浏览器；未声明真实 CLI / 浏览器 E2E 验证。

现有 .trellis/spec 按 PRD 范围保留；本任务新增约定记录在 design.md、scripts/README.md 和 profile_notes。
