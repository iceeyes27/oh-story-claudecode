# Skill Repository Guidelines

## Scope

本仓库交付可安装的写作 Skill、共享参考资料、跨平台部署模板与仓库校验工具。主要资产位于 `skills/`，自动化位于 `scripts/`，GitHub CI 位于 `.github/workflows/cross-platform.yml`。

## Guidelines Index

| Guide | Applies to |
| --- | --- |
| [Canonical assets](./canonical-assets.md) | `skills/` 中的共享与独立 Skill 资产 |
| [Validation](./validation.md) | `scripts/`、CI 和任何影响 Skill 契约的修改 |

## Entry rule

修改 Skill 前先确认其是独立资产还是 `_shared` 基础资产。修改后必须运行与变更范围对应的校验，不能以合并成功代替内容验证。
