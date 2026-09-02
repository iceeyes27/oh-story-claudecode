#!/bin/bash
# test-narrative-gates.sh — 叙事契约回归聚合（quality-gate check: narrative-gates）
# 覆盖细纲/因果/扫描/交付/追踪生命周期类回归套件；任一套件失败即整批失败。
# 归属：release profile（见 scripts/quality-gate.json）。
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

PYBIN=""
for c in python3 python py; do "$c" -c "" >/dev/null 2>&1 && { PYBIN="$c"; break; }; done
[ -z "$PYBIN" ] && { echo "FAIL: python interpreter not found" >&2; exit 1; }

suites=(
  "test-outline-causal.py $PYBIN scripts/test-outline-causal.py"
  "test-outline-contract.js node --test scripts/test-outline-contract.js"
  "test-emotion-run.js node scripts/test-emotion-run.js"
  "test-outline-copy.sh bash scripts/test-outline-copy.sh"
  "test-phase2-contract.js node --test scripts/test-phase2-contract.js"
  "test-delivery-contract.js node --test scripts/test-delivery-contract.js"
  "test-scan-contract.js node --test scripts/test-scan-contract.js"
  "test-scan-runtime.js node --test scripts/test-scan-runtime.js"
  "test-scan-runtime-policy.py $PYBIN scripts/test-scan-runtime-policy.py"
  "test-review-state.js node --test scripts/test-review-state.js"
  "test-story-continuity.sh bash scripts/test-story-continuity.sh"
  "test-chapter-completion-lifecycle.py $PYBIN scripts/test-chapter-completion-lifecycle.py"
  "test-longform-stability.sh bash scripts/test-longform-stability.sh"
  "test-state-store.sh bash scripts/test-state-store.sh"
  "test-author-memory-commit.py $PYBIN scripts/test-author-memory-commit.py"
  "test-flow-state.sh bash scripts/test-flow-state.sh"
)

for entry in "${suites[@]}"; do
  name="${entry%% *}"
  command="${entry#* }"
  echo "---- $name"
  if ! $command; then
    echo "Narrative gate regressions FAILED at $name." >&2
    exit 1
  fi
done

echo "Narrative gate regressions passed."
