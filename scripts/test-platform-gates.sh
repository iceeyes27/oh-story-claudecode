#!/bin/bash
# test-platform-gates.sh — 平台/共享资产回归聚合（quality-gate check: platform-gates）
# 覆盖各端 hook 合成测试、skill 编号、共享资产与静态检查回归；任一失败即整批失败。
# 归属：release profile（见 scripts/quality-gate.json）。
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

PYBIN=""
for c in python3 python py; do "$c" -c "" >/dev/null 2>&1 && { PYBIN="$c"; break; }; done
[ -z "$PYBIN" ] && { echo "FAIL: python interpreter not found" >&2; exit 1; }

suites=(
  "test-zcode-hooks.sh bash scripts/test-zcode-hooks.sh"
  "test-codex-hooks.sh bash scripts/test-codex-hooks.sh"
  "test-reasonix-adapter.sh bash scripts/test-reasonix-adapter.sh"
  "test-skill-numbering.sh bash scripts/test-skill-numbering.sh"
  "test-storyctl.py $PYBIN scripts/test-storyctl.py"
  "test-current-skill-contracts.py $PYBIN scripts/test-current-skill-contracts.py"
  "test-shared-assets.py $PYBIN scripts/test-shared-assets.py"
  "test-shared-references.py $PYBIN scripts/test-shared-references.py"
  "test-static-check.py $PYBIN scripts/test-static-check.py"
  "test-hook-encoding-portable.sh bash scripts/test-hook-encoding-portable.sh"
  "quality-gate.test.mjs node --test scripts/quality-gate.test.mjs"
)

for entry in "${suites[@]}"; do
  name="${entry%% *}"
  command="${entry#* }"
  echo "---- $name"
  if ! $command; then
    echo "Platform gate regressions FAILED at $name." >&2
    exit 1
  fi
done

echo "Platform gate regressions passed."
