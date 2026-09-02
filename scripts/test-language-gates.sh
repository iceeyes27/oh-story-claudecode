#!/bin/bash
# test-language-gates.sh — 语言门禁回归聚合（quality-gate check: language-gates）
# 覆盖正文语言质量链上所有必须常绿的回归套件；任一套件失败即整批失败。
# 归属：affected + release profile（见 scripts/quality-gate.json）。
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

PYBIN=""
for c in python3 python py; do "$c" -c "" >/dev/null 2>&1 && { PYBIN="$c"; break; }; done
[ -z "$PYBIN" ] && { echo "FAIL: python interpreter not found" >&2; exit 1; }

suites=(
  "test-ai-patterns.sh bash scripts/test-ai-patterns.sh"
  "test-degeneration.sh bash scripts/test-degeneration.sh"
  "test-prose-policy.py $PYBIN scripts/test-prose-policy.py"
  "test-normalize-punctuation.js node --test scripts/test-normalize-punctuation.js"
  "test-charcount-portable.sh bash scripts/test-charcount-portable.sh"
  "test-prose-backstop-hook.sh bash scripts/test-prose-backstop-hook.sh"
  "test-prose-net-parity.sh bash scripts/test-prose-net-parity.sh"
)

for entry in "${suites[@]}"; do
  name="${entry%% *}"
  command="${entry#* }"
  echo "---- $name"
  if ! $command; then
    echo "Language gate regressions FAILED at $name." >&2
    exit 1
  fi
done

echo "Language gate regressions passed."
