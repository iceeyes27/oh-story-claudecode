# Validation

## Required checks

- `bash scripts/static-check.sh`：校验 Skill frontmatter、链接、引用、agent 和自包含边界。
- `python scripts/test-static-check.py`：覆盖静态检查的边界回归。
- `bash scripts/check-shared-files.sh`：校验共享副本和部署模板一致性。
- `bash scripts/check-python-invocation.sh`：禁止 Windows 环境会失败的裸 `python3` 调用。
- `bash scripts/check-hook-regex-sync.sh` 与 `bash scripts/test-ai-patterns.sh`：校验实时 hook 与共享扫描规则同步。
- `bash scripts/test-flow-state.sh`：改 `story-write` 写作阶段披露协议或 `flow-state.js` 时运行，校验阶段识别、状态更新边界和关键缺失项行为。
- `python scripts/check-unified-skill-upstream-drift.py`：校验统一目录对上游拆分目录的人工迁移义务。
- 需要查看迁移范围时使用 `python scripts/check-unified-skill-upstream-drift.py --report`；该报告只读，不自动覆盖统一 Skill。
- `python scripts/check-current-skill-contracts.py`：除版本与产物契约外，拒绝 `.github/workflows/` 中的任何文件，保持本 fork 仅使用本地验证。
- `node scripts/check-platform-capabilities.mjs`：校验各平台能力、降级行为与 Windows 启动方式。
- `node scripts/quality-gate.mjs --profile affected|release`：统一执行本地质量检查并生成机器可读报告。
- `node scripts/check-release-manifest.mjs`：校验发布身份、上游基线与权威资产摘要。
- 跨平台校验必须读取 `scripts/platform-skill-set.json`，不得另建公开 Skill 名单；不公开的 Skill 必须在 `scripts/local-only-skill-set.json` 中写明原因，两个集合必须无交集且完整覆盖仓库 Skill。复合检查及其嵌套路由的契约测试还要证明全部必需 Skill 依赖属于公开集合且资产存在。

## Public Skill / Deployment Contract

### 1. Scope / Trigger

修改公开 Skill 清单、marketplace、平台命令模板或 `story` 复合检查路由时触发。

### 2. Signatures

- 清单：`scripts/platform-skill-set.json.skills: string[]`
- 本地专用清单：`scripts/local-only-skill-set.json.skills: Record<string, string>`
- 适配检查：`bash scripts/check-{claude,opencode,zcode,openclaw,reasonix}-*.sh`
- 本地适配：`node skills/story-setup/scripts/manage-skill-adapters.js check --root=<project>`

### 3. Contracts

- 清单中的每个名称必须有 `skills/<name>/SKILL.md`。
- 仓库每个 Skill 必须且只能属于公开清单或带原因的本地专用清单。
- `story` 复合检查依赖及其必需的嵌套路由依赖必须全部在清单中。
- 独立项目部署公开 Skill 时，必须同时部署 `skills/_shared/`；它不是可发现 Skill，不计入数量。
- Claude marketplace、ZCode/OpenCode command 模板和 OpenClaw/Reasonix 校验必须从同一清单得到公开集合。

### 4. Validation & Error Matrix

| 条件 | 结果 |
| --- | --- |
| 清单名称重复或缺少 `SKILL.md` | 失败 |
| 新 Skill 未归类、重复归类或本地专用原因为空 | 覆盖测试失败 |
| 复合检查依赖未发布 | 回归测试失败 |
| `_shared` 缺失 | 部署契约失败 |
| Node 不支持 `--experimental-strip-types` | OpenCode 行为测试明确跳过，静态检查继续 |

### 5. Good / Base / Bad Cases

- Good：公开 Skill 清单、`_shared`、生成 command 和各 marketplace 一致。
- Base：仓库 Skill 均归入公开或本地专用清单，数量从清单计算。
- Bad：平台只安装 `story` 与 10 个旧公开 Skill，却宣称复合检查 10/10。

### 6. Tests Required

- `skills/story/tests/composite-check-contract.test.js`：断言十阶段顺序、108 个必检项、读者视角阶段的只读正文约束和公开依赖集合。
- `scripts/skill-publication-coverage.test.js`：断言公开与本地专用集合无遗漏、无重叠且原因非空。
- 平台检查：断言 marketplace、commands、frontmatter、manifest 与清单一一对应。
- 平台 AGENTS 路由模板中的 Skill 名称也必须与 `platform-skill-set.json` 一致，禁止保留已删除的 `story-long-*` / `story-short-*` 名称。
- `scripts/test-unified-skill-upstream-drift.py`：验证旧路径变化会显示对应的统一目标路径。
- `scripts/test-reasonix-adapter.sh`：验证 Reasonix 路由名必须来自公开 Skill 清单。
- `check-story-setup-deployment.sh`：断言 `_shared` 与部署资源完整。

### 7. Wrong vs Correct

```text
Wrong: 各平台脚本分别维护公开 Skill 数量，部署只复制含 SKILL.md 的目录。
Correct: 读取 platform-skill-set.json，并额外复制 skills/_shared/。
```

## Local-only expectation

本 fork 不使用 GitHub Actions。提交前必须在本地运行与改动范围对应的静态与脚本校验；涉及跨平台行为时应在对应系统验证。增加或改变校验规则时，必须补充 `scripts/test-*.py` 或 `scripts/test-*.sh` 回归，证明新规则不会扩大豁免范围。

## Composite Check and Post-Event Hook Contract

### 1. Scope / Trigger

修改 `skills/story/SKILL.md` 复合检查路由、复合检查内部过滤项、或 Claude 写作后 Hook 时触发。

### 2. Signatures

- 复合检查清单：`skills/story/references/composite-check-manifest.json`。
- Claude CLI：`node story_hook_cli.js prose-after-event <project-root>`，输入来自 stdin 或 `HOOK_INPUT`。

### 3. Contracts

- 清单必须声明十个有序阶段与完整目录 108 项。前两个阶段是读者视角（`reader-comprehension` / `opening-arc`），只读 `正文/`。
- 场景适用项由 manifest 的 profile 明确列出；纯中文正文为 46 项，其中逻辑项 13 项，`13/46 = 28.26%`。profile 外项目用 `NOT_APPLICABLE` 及原因登记，不进入适用分母。
- 每个必检项必须有唯一 `id`、`executor`、`scope`、`required` 和 `report`。
- Hook 输入使用 `hook_event_name`、`tool_name`、`tool_input`；Write/Edit/MultiEdit 读取 `file_path`、`path`、`filePath`，Bash 读取 `command`、`cmd` 或 `script`。
- Hook 的项目根、工作目录和目标文件必须先按物理路径归一化再做范围判断：允许 `/var` 与 `/private/var`、项目根别名等同对象路径，拒绝词法位于根内但经符号链接逃到根外的目标。
- 有正文发现时输出 `hookSpecificOutput.hookEventName` 和非空 `additionalContext`；失败 Bash 事件前置“命令失败但文件可能已改变：”。

### 4. Validation & Error Matrix

| 条件 | 结果 |
| --- | --- |
| 必检项缺少记录 | 复合检查不能报告完成 |
| 过滤器发现问题 | 记录 `FAIL`，继续执行后续项目 |
| 输入不可读或执行器缺失 | 记录 `BLOCKED`，不能报告完成 |
| `SKIPPED` 无原因 | 契约测试失败 |
| profile 外项目未记 `NOT_APPLICABLE` 或缺原因 | 契约测试失败 |
| Hook 无目标、非正文或无发现 | 静默退出 |
| Hook 输入无法解析 | 静默退出，不改变工具结果 |

### 5. Good / Base / Bad Cases

- Good：十阶段全部有结论，完整目录 108 项均有状态；纯中文正文 46 个适用项全部返回，输出 `复合检查完成：10/10，过滤项 46/46（完整目录 108 项）`。
- Base：某项发现问题但仍执行后续项目，输出 `FAIL` 而不是中断。
- Bad：只报告十个阶段名称，或把无法读取的文件静默排除后输出完成。

### 6. Tests Required

- `node --test skills/story/tests/composite-check-contract.test.js`：阶段顺序、108 项目录、纯中文 13/46 预算、规范同步、依赖来源、漏项、阻断和触发词。
- `bash scripts/test-prose-backstop-hook.sh`：Bash 成功/失败、Write、Edit、MultiEdit 的合法 Hook JSON 与正文发现，并覆盖物理同路径别名及符号链接逃逸。
- `bash scripts/test-story-continuity.sh`：章节号与 tracking state 判定，不依赖固定 mtime 延迟。
- `bash scripts/check-story-setup-deployment.sh`：部署模板必须包含 `prose-after-event` 路由。

### 7. Wrong vs Correct

```text
Wrong: 只检查 story-review，并把“八阶段已列出”当成复合检查完成。
Correct: 读取 composite-check-manifest.json，逐项记录状态；只有阶段和全部必检项都有结果时才报告完成。
```
