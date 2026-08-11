# 当前实现证据

## 基线

- 分支基线：`main@b70a44b`。
- 统一入口：旧 `story-long-scan`、`story-long-analyze` 已分别归入 `story-scan`、`story-analyze`，方案不得恢复旧入口。
- 项目规范：共享规则与扫描器以 `skills/_shared/` 为权威来源；平台模板或副本必须由既有同步工具生成并校验；只运行本地检查，不新增 GitHub Actions。

## 缺陷到现有实现的映射

| 需求 | 当前证据 | 规划约束 |
|---|---|---|
| R1 / #316 | `skills/story-setup/references/templates/settings-hooks.json:32` 的 Bash 只运行提交检查；正文前后检查仅匹配 `Write|Edit|MultiEdit`（43、55）。 | Bash 写正文必须覆盖首次创建、覆盖、追加、复制、移动；无法可靠识别目标时不得伪称已检查。 |
| R2 / #333 | `skills/story-analyze/references/style-profile-generator.md:61` 宣称 Stage 6 只读 Stage 0 边界表，但同文件 53 起仍给出 Grep/正则切片方法。 | Stage 0 边界表是唯一章节切片来源；Stage 6 只消费并校验。 |
| R3 / #343 | `skills/story-review/SKILL.md:146`、239、330 要求继承上一批 findings，但未定义文件、版本、读写和清理协议；168 又规定 solo 始终只报告。 | 持久化契约必须保持 solo 只读语义，并与追踪事务的权威文件分离。 |
| R4 / #339 | `qidian-rank-scraper.js:103`、300 的列表与移动端归一化缺少字数、总推荐、签约、收费模式；320 的渲染也无字段质量状态。 | mobile-ssr 与 cdp-pc 归一成同一核心 schema；缺失值必须可见。 |
| R5 / #340 | `qimao-rank-scraper.js:37` 只有榜型，149 起只有频道参数；没有日榜/月榜周期参数及页面切换。 | `--period`、页面激活验证、元数据、文件名和测试必须一致。 |
| R6 / #341 | 各平台分别解析参数和简介；起点、七猫、晋江的非法值处理不一致；多个渲染器分别取时间。 | 共享参数校验、简介截断和单次时间快照；四个平台都覆盖非法参数测试。 |
| R7 / #319 | `story_codex_hook.py:122`、419 使用无限深度 `glob("**/...")`，只过滤隐藏目录，未跳过 `node_modules`；JS 当前书发现深度为 4。 | 当前书与全部书采用同一深度和忽略目录契约，保留跨端行为一致性。 |
| R8 / #317 | `story_codex_hook.py:563` 用 `"codex" in value` 判断，会把 `opencode` 当作包含 Codex。 | 按逗号拆分、去空白、精确 token 比较。 |

## 已存在的回归入口

- 扫榜运行时：`scripts/test-scan-runtime.js`。
- Codex hook：`scripts/test-codex-hooks.sh`。
- Claude 部署与大纲守卫：`scripts/check-story-setup-deployment.sh`。
- 正文写后检查：`scripts/test-prose-backstop-hook.sh`。
- 共享副本与静态契约：`scripts/check-shared-files.sh`、`scripts/check-current-skill-contracts.py`、`scripts/static-check.sh`。

## 范围排除

- #315 已有规则、检测器和测试，不重复修改。
- #280、#251 另立平台适配任务。
- `claude/browser-cdp` 适配清单哈希过期不属于本任务。
