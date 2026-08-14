# 可追溯分析结果层实施计划

## 实施步骤

1. 扩展 `scripts/current-contract.json` 和检查器，登记 `analysis_manifest_schema_version: 1`。
2. 新增 `skills/story-analyze/scripts/analysis-manifest.js`：
   - 复用 `chapter-boundary.js` 的校验结果。
   - 实现清单初始化、验证和原子替换。
   - 实现 Stage 状态、Stage 2 尝试、恢复查询和完成检查；显式 `--allow-failures` 保留现有部分失败继续执行语义。
   - 实现关系草稿验证、别名归一、证据指纹、去重发布和修订元数据。
3. 新增 Node 单元测试，覆盖正常流程、边界条件、篡改检测和发布原子性。
4. 新增 `references/analysis-manifest.md`，并修改 `SKILL.md`、`pipeline-ops.md`、`output-templates.md` 中的相关 Stage 调用点。
5. 扩展当前契约回归，确保 schema 、CLI 调用和文档规则不会各自变化。
6. 在 `CHANGELOG.md` 的 v0.8.0 中记录新增能力。

## 验证命令

```text
node --test skills/story-analyze/scripts/chapter-boundary.test.js skills/story-analyze/scripts/analysis-manifest.test.js
python scripts/test-current-skill-contracts.py
python scripts/check-current-skill-contracts.py
bash scripts/static-check.sh
python scripts/test-static-check.py
bash scripts/check-python-invocation.sh
git diff --check
```

## 高风险位置

- 清单更新中途中断：必须使用同目录临时文件 + rename，失败时保留旧文件。
- 关系结果已写但清单未更新：先写唯一临时结果，验证后 rename，再更新清单；清单失败时删除本次新结果，不动既有修订。
- 证据路径逃出：同时做词法路径和真实路径检查，拒绝符号链接文件。
- 输出文件外部修改：成功尝试和已发布结果的校验都重算 SHA-256。

## 回退方式

本功能是新增可选产物。回退代码后，既有 `_progress.md` 和 Markdown 产物仍可使用；用户书项目中的 `_analysis-manifest.json` 和 `_analysis/results/` 可保留为只读记录。
