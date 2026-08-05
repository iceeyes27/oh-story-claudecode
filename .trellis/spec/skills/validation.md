# Validation

## Required checks

- `bash scripts/static-check.sh`：校验 Skill frontmatter、链接、引用、agent 和自包含边界。
- `python scripts/test-static-check.py`：覆盖静态检查的边界回归。
- `bash scripts/check-shared-files.sh`：校验共享副本和部署模板一致性。
- `bash scripts/check-python-invocation.sh`：禁止 Windows 环境会失败的裸 `python3` 调用。
- `bash scripts/check-hook-regex-sync.sh` 与 `bash scripts/test-ai-patterns.sh`：校验实时 hook 与共享扫描规则同步。
- `python scripts/check-unified-skill-upstream-drift.py`：校验统一目录对上游拆分目录的人工迁移义务。
- `python scripts/check-current-skill-contracts.py`：除版本与产物契约外，拒绝 `.github/workflows/` 中的任何文件，保持本 fork 仅使用本地验证。
- 跨平台校验必须读取 `scripts/platform-skill-set.json`，不得另建公开 Skill 名单；复合检查契约测试还要证明其全部 Skill 依赖属于该公开集合且资产存在。

## Public Skill / Deployment Contract

### 1. Scope / Trigger

修改公开 Skill 清单、marketplace、平台命令模板或 `story` 复合检查路由时触发。

### 2. Signatures

- 清单：`scripts/platform-skill-set.json.skills: string[]`
- 适配检查：`bash scripts/check-{claude,opencode,zcode,openclaw,reasonix}-*.sh`
- 本地适配：`node skills/story-setup/scripts/manage-skill-adapters.js check --root=<project>`

### 3. Contracts

- 清单中的每个名称必须有 `skills/<name>/SKILL.md`。
- `story` 复合检查依赖必须全部在清单中。
- 独立项目部署公开 Skill 时，必须同时部署 `skills/_shared/`；它不是可发现 Skill，不计入数量。
- Claude marketplace、ZCode/OpenCode command 模板和 OpenClaw/Reasonix 校验必须从同一清单得到公开集合。

### 4. Validation & Error Matrix

| 条件 | 结果 |
| --- | --- |
| 清单名称重复或缺少 `SKILL.md` | 失败 |
| 复合检查依赖未发布 | 回归测试失败 |
| `_shared` 缺失 | 部署契约失败 |
| Node 不支持 `--experimental-strip-types` | OpenCode 行为测试明确跳过，静态检查继续 |

### 5. Good / Base / Bad Cases

- Good：14 个公开 Skill、`_shared`、14 个 command 和各 marketplace 一致。
- Base：仓库内 `.agents/skills` 发现全部 30 个 Skill，公开集合仍为 14 个。
- Bad：平台只安装 `story` 与 10 个旧公开 Skill，却宣称复合检查 7/7。

### 6. Tests Required

- `skills/story/tests/composite-check-contract.test.js`：断言七阶段顺序和公开依赖集合。
- 平台检查：断言 marketplace、commands、frontmatter、manifest 与清单一一对应。
- `check-story-setup-deployment.sh`：断言 `_shared` 与部署资源完整。

### 7. Wrong vs Correct

```text
Wrong: 各平台脚本分别维护公开 Skill 数量，部署只复制含 SKILL.md 的目录。
Correct: 读取 platform-skill-set.json，并额外复制 skills/_shared/。
```

## Local-only expectation

本 fork 不使用 GitHub Actions。提交前必须在本地运行与改动范围对应的静态与脚本校验；涉及跨平台行为时应在对应系统验证。增加或改变校验规则时，必须补充 `scripts/test-*.py` 或 `scripts/test-*.sh` 回归，证明新规则不会扩大豁免范围。
