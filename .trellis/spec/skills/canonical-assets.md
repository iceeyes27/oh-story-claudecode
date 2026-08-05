# Canonical Assets

## Ownership

- `skills/_shared/` 是通用写作规则、禁用词与扫描器的唯一来源；业务 Skill 通过 `../_shared/...` 引用它。
- `scripts/sync-shared-assets.py` 维护 story-setup 的部署副本。修改 hook 或共享扫描器后，先同步再运行 `bash scripts/check-shared-files.sh`。
- `skills/story-write`、`story-analyze`、`story-scan` 是统一入口。不要新增旧的 `story-long-*`、`story-short-*` 目录。

## Upstream mapping

上游仍可能修改旧拆分目录。`scripts/unified-skill-upstream-map.json` 声明旧目录到统一 Skill 的映射，`scripts/check-unified-skill-upstream-drift.py` 在本地检查基线后的未处理修改。上游变更必须人工迁移到对应统一资产，并更新基线。

## Self-contained runtime rule

独立 Skill 不得读取其它业务 Skill 的脚本或参考文件。仅 `browser-cdp` 与 `_shared` 可作为基础依赖；需要其它能力时用路由说明而非文件路径。
