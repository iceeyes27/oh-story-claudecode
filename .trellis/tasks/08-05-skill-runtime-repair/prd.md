# 修复 Skill 发布与适配一致性

## Goal

修复审计确认的 Skill 发布、平台适配和本地回归缺陷，使公开安装与仓库内使用都能执行完整小说检查。

## Requirements

- 将完整小说检查依赖的三个专项扫描 Skill 纳入跨平台公开清单与 Claude marketplace。
- 修复仓库内 Claude、Codex、WorkBuddy 的 Skill 适配状态及适配清单漂移。
- 修复完整检查契约测试和标点规范化测试的失效路径。
- OpenCode 本地检查必须明确识别 Node 版本能力，不能直接以不支持的参数失败。
- 统一当前发布版本信息与公开 Skill 数量说明。
- 仅使用本地验证；不得新增或启用 GitHub Actions，不得下载浏览器或依赖。

## Acceptance Criteria

- [ ] `platform-skill-set.json` 与 Claude marketplace 同时公开 14 个 Skill，包含三个完整检查依赖。
- [ ] `manage-skill-adapters.js check` 对仓库中已启用的平台全部通过。
- [ ] 两个已确认失效的 Node 回归测试通过。
- [ ] OpenCode 检查在 Node 18 下给出可理解的跳过或替代结果，在 Node 22 下执行类型脚本测试。
- [ ] 核心静态检查、共享资产检查、平台适配检查和相关单元测试通过。
- [ ] `.github/workflows/` 保持不存在，工作过程无下载。

## Notes

- 用户已确认继续执行审计后的最佳方案。
