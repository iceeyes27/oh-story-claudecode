# Repair fork integrity — Design

## Canonical ownership

- 共享写作规则与扫描器固定在 `skills/_shared/`。
- `deslop-register` 根据自身安装位置定位 `_shared`，不再扫描机器上的框架副本，也不依赖旧 Skill 目录。
- 统一 Skill 与上游拆分 Skill 的对应关系由 `scripts/unified-skill-upstream-map.json` 声明，并由漂移检查阻止未处理的上游修改。

## Static-check boundary

普通 Skill 的本地路径仍逐条校验。`trellis-*` 是工作流说明 Skill，其中 `prd.md`、`.trellis/` 等名称指向使用者项目的任务工件而非 Skill 资产；仅跳过此类文档的内联路径检查，Markdown 链接、跨 Skill 文件引用、frontmatter 与 agent 校验保持有效。用独立回归用例证明此边界。

## Compatibility

- Python 命令示例采用解释器探测变量，不直接调用 `python3`。
- 旧的本地绝对路径替换为当前 Skill 目录相对路径或通用项目目录表述。
- 同名 `overview.md` 仅在全部属于 `trellis-meta` 的层级说明时排除内容一致性比较；其它同名文件继续检查。

## Verification

先执行目标回归，再执行完整静态、共享资产、Python 调用与写作规则校验；最后检查 Git diff、旧目录、worktree 与可删分支状态。
