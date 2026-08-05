# 设计

## 边界

- `scripts/platform-skill-set.json` 继续作为跨平台公开 Skill 的唯一清单。
- Claude marketplace 显式列出每个公开 Skill；其余平台校验从公开清单读取。
- `.agents/skills` 继续作为仓库内 Skill 唯一来源，平台目录只保存受管理的链接或兼容副本。

## 变更方案

1. 在公开清单和 Claude marketplace 增加三个专项扫描 Skill，并把相关数量与版本说明更新为 14 / 0.8.0。
2. 使用现有适配管理器修复 Claude、Codex、WorkBuddy 目录，避免手工维护重复副本。
3. 把两个测试改为引用仓库内现存的权威路径。
4. OpenCode 检查先探测 `--experimental-strip-types`；支持时执行插件运行测试，不支持时执行静态语法与生成一致性检查并明确标记运行测试已跳过。

## 兼容性

- 不改变 Skill 名称或调用方式。
- 不引入新依赖，不触发网络访问。
- Node 18 仍可完成除 TypeScript 直接执行以外的 OpenCode 本地检查；Node 22 保持完整验证。
