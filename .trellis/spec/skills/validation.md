# Validation

## Required checks

- `bash scripts/static-check.sh`：校验 Skill frontmatter、链接、引用、agent 和自包含边界。
- `python scripts/test-static-check.py`：覆盖静态检查的边界回归。
- `bash scripts/check-shared-files.sh`：校验共享副本和部署模板一致性。
- `bash scripts/check-python-invocation.sh`：禁止 Windows 环境会失败的裸 `python3` 调用。
- `bash scripts/check-hook-regex-sync.sh` 与 `bash scripts/test-ai-patterns.sh`：校验实时 hook 与共享扫描规则同步。
- `python scripts/check-unified-skill-upstream-drift.py`：校验统一目录对上游拆分目录的人工迁移义务。

## CI expectation

`.github/workflows/cross-platform.yml` 运行跨平台静态与脚本校验。增加或改变校验规则时，必须补充 `scripts/test-*.py` 或 `scripts/test-*.sh` 回归，证明新规则不会扩大豁免范围。
