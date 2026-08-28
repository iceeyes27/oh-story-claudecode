# Canonical Assets

## Ownership

- `skills/_shared/` 是通用写作规则、禁用词与扫描器的唯一来源；业务 Skill 通过 `../_shared/...` 引用它。
- 复制公开 Skill 到独立项目时，必须同时复制非 Skill 支持资产 `_shared`；`_shared` 不计入公开 Skill 数量，但缺失时不得宣称完整检查可执行。
- `scripts/sync-shared-assets.py` 维护 story-setup 的部署副本。修改 hook 或共享扫描器后，先同步再运行 `bash scripts/check-shared-files.sh`。
- `skills/story-write`、`story-analyze`、`story-scan` 是统一入口。不要新增旧的 `story-long-*`、`story-short-*` 目录。

## Upstream mapping

`scripts/upstream-integration.json` 是上游同步策略的唯一来源，声明固定基线、保护路径、禁止路径、生成资产与旧拆分目录到统一 Skill 的映射。同步只使用 `node scripts/sync-upstream.js prepare|review|validate|promote|abort`：工具在专用 worktree 中固定双方 SHA，要求 upstream 禁止 push，记录逐路径决定，并在 promote 前执行统一质量门禁。上游语义必须人工迁移到统一资产；旧拆分目录、生成入口和 `.github/workflows/` 不得直接进入 fork。

## Self-contained runtime rule

独立 Skill 不得读取其它业务 Skill 的脚本或参考文件。仅 `browser-cdp` 与 `_shared` 可作为基础依赖；需要其它能力时用路由说明而非文件路径。
