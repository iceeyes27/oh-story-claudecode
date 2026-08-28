#!/bin/bash
# Cross-platform launcher for the structured skill Markdown checker.

set -euo pipefail

# `set -e` 下裸赋值会继承命令替换的退出码：git 失败（非仓库/无 git）时脚本会直接中断，
# 下面的诊断分支永远走不到。用 `|| true` 兜住，把判定交给 -z 检查。
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [ -z "$REPO_ROOT" ]; then
  # A linked worktree created by Windows Git stores a drive-letter path in its
  # `.git` pointer. WSL Git cannot resolve that pointer directly, so validate
  # the marker ourselves and keep the worktree root as the scan root.
  fallback_root="$(cd "$(dirname "$0")/.." && pwd)"
  git_marker="$fallback_root/.git"
  if [ -d "$git_marker" ] && [ -f "$git_marker/HEAD" ]; then
    REPO_ROOT="$fallback_root"
  elif [ -f "$git_marker" ]; then
    git_dir="$(sed -n 's/^gitdir:[[:space:]]*//p' "$git_marker" | head -1 | tr -d '\r')"
    if printf '%s' "$git_dir" | grep -Eq '^[A-Za-z]:'; then
      if command -v wslpath >/dev/null 2>&1; then
        git_dir="$(wslpath -u "$git_dir" 2>/dev/null || true)"
      fi
    elif [ "${git_dir#/}" = "$git_dir" ]; then
      git_dir="$fallback_root/$git_dir"
    fi
    if [ -f "$git_dir/HEAD" ] && [ -f "$git_dir/commondir" ]; then
      REPO_ROOT="$fallback_root"
    fi
  fi
fi
if [ -z "$REPO_ROOT" ]; then
  echo "Error: not in a git repository" >&2
  exit 1
fi

PYBIN=""
for candidate in python3 python py; do
  if "$candidate" -c "" >/dev/null 2>&1; then
    PYBIN="$candidate"
    break
  fi
done
if [ -z "$PYBIN" ]; then
  echo "Error: Python 3 is required for scripts/static-check.py" >&2
  exit 1
fi

exec "$PYBIN" "$REPO_ROOT/scripts/static-check.py" --root "$REPO_ROOT"
