# 技术设计

## 设计边界

- 仅处理 PRD 的 R1-R8；#315、#280、#251 和无关适配哈希不进入本任务。
- 保留统一 Skill 名称、`_shared` 边界、平台适配生成规则和本地验证约束。
- 五个子任务独立验证，父任务负责跨组契约与最终质量检查。

## 五个实施组

1. **Claude Bash 正文守卫**：扩展现有 `story_hook_core.js` 事件目标接口，Claude 前置、成功写后、失败写后均注册 Bash；Node 缺失时只保留有明确范围的 Shell 前置兼容。写后通过事件对应的 `additionalContext` 报告，固定 exit 0，不能撤销已发生的写入。
2. **Stage 章节边界**：`_progress.md` 升为 schema v3，记录原文路径、大小和 SHA-256；story-analyze 自有校验器负责唯一性、连续性、行号和来源验证。Stage 1/2/6 只消费该表，旧 schema 回到 Stage 0 重建。
3. **跨批审查状态**：固定 `{书目录}/.story-review/latest.json`，full/lean 写、solo/显式只读只读。写入前以 `O_CREAT|O_EXCL` 申领目标 revision，随后复核 revision 并原子替换；claim_id 决定释放权限，未完成任务不得被其他 review_id 覆盖。
4. **扫榜统一契约**：新增 skill-local `scan-contract.js`，统一 CLI、Unicode 简介截断、单次时间快照和质量标记。起点固定 14 字段 schema；七猫大热榜实现 day/month/all 并验证页面实际激活状态。
5. **Codex 一致性**：建立机器可读的书目发现契约，三种运行时使用同一“最多 4 层 + 忽略目录 + 不跟随符号链接”规则；`target_cli` 按逗号 token 精确判断。

## 关键限制

- Bash 只能可靠识别已声明的直接写入形式，任意间接脚本不承诺静态全覆盖。
- `PostToolUse` / `PostToolUseFailure` 只能提供写后反馈。Claude Code 官方契约见 <https://code.claude.com/docs/en/hooks>。
- solo 审查本次产生的新 findings 不写入状态，因此不能从新会话恢复；报告必须明确该限制。
- 扫榜运行测试使用 fake agent-browser，不依赖实时站点。

## 一致结论

详细决策与边界见 `research/consensus-draft.md`。可维护性、边界条件、回归风险三方最终均为 `APPROVE`。
