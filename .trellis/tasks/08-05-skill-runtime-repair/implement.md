# 实施计划

1. 更新公开 Skill 清单、Claude marketplace、README 和版本说明。
2. 修复两个测试路径与 OpenCode Node 能力检测。
3. 运行现有适配管理器修复本仓库平台目录及清单。
4. 执行定向测试、平台检查和仓库本地质量检查。
5. 检查工作区范围，提交、归档并推送 `main`。

## 验证命令

- `node --test skills/story/tests/composite-check-contract.test.js`
- `node scripts/test-normalize-punctuation.js`
- `bash scripts/check-opencode-adapter.sh`
- `node skills/story-setup/scripts/manage-skill-adapters.js check --root=...`
- `bash scripts/static-check.sh`
- `python scripts/test-static-check.py`
- `bash scripts/check-shared-files.sh`
- `python scripts/check-current-skill-contracts.py`
