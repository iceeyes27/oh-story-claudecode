#!/usr/bin/env bash
# Compatibility entrypoint. The Node state machine owns all sync state and
# validation; this wrapper intentionally performs no stash, merge, or checks.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

if [ "${1:-}" = "--continue" ]; then
  echo "sync-fork.sh --continue was removed. Use: node scripts/sync-upstream.js validate --id <sync-id>" >&2
  exit 2
fi

exec node scripts/sync-upstream.js "$@"
