#!/usr/bin/env bash
# sync-fork.sh — 一键同步上游的封装（Windows-aware）
#
# 把每次「同步 upstream/main」里每次都一样的机械活自动化，只把需要判断的内容冲突留给人：
#   1. 自动 stash 未提交的 WIP（同步结束后自动 pop）
#   2. Windows 环境垫片：PYTHONUTF8=1 + 为空壳 python3（Windows Store stub）注入真 python shim
#   3. 调 scripts/sync-upstream.js 完成 fetch + merge + 改名目录 modify/delete 自动 rm
#   4. 有内容冲突（判断题）→ 分类打印后停下，让人解；解完跑 `sync-fork.sh --continue`
#   5. 无冲突 → 跑全套本地检查（保守：任一失败即停，不推进、不 pop）
#   6. 全绿 → 推进 unified-skill-upstream-map.json 的 upstream_baseline 到已合并的上游 SHA
#   7. pop 回 WIP，留下已暂存的合并交给人 `git commit`
#
# 保守尺度：只自动处理零风险的（改名 modify/delete 删除 + 环境 + 检查 + baseline）。
# 内容冲突（--ours/--theirs/移植、丢留 fork 特性）一律停下——那是价值判断，工具不替你决定。
#
# 用法：
#   bash scripts/sync-fork.sh              # 正常同步
#   bash scripts/sync-fork.sh --continue   # 人工解完冲突后，继续跑检查+baseline+提交提示
#   bash scripts/sync-fork.sh --help
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

REMOTE="upstream"
BRANCH="main"
MODE="normal"
STASH_MARKER=".git/.sync-fork-stashed"

for arg in "$@"; do
  case "$arg" in
    --continue) MODE="continue" ;;
    --remote=*) REMOTE="${arg#*=}" ;;
    --branch=*) BRANCH="${arg#*=}" ;;
    -h|--help)
      grep '^# ' "$0" | sed 's/^# //'
      exit 0 ;;
    *) echo "未知参数：$arg（用 --help 看用法）" >&2; exit 2 ;;
  esac
done

say() { printf '\n\033[1m[sync-fork]\033[0m %s\n' "$*"; }
warn() { printf '\033[33m[sync-fork] %s\033[0m\n' "$*" >&2; }

# ── 1. Windows 环境垫片 ────────────────────────────────────────────────────────
export PYTHONUTF8=1   # Windows 中文系统默认 GBK，读 UTF-8 文件会 UnicodeDecodeError
SHIM_DIR=""
setup_python_shim() {
  # python3 能正常执行就不动（Linux/mac、或 Windows 上装了真 python3）
  if python3 -c "import sys" >/dev/null 2>&1; then return; fi
  # 否则（Windows Store 空壳 stub，或没有 python3）用真 python/py 造一个 python3 shim
  local real
  real="$(command -v python 2>/dev/null || true)"
  [ -z "$real" ] && real="$(command -v py 2>/dev/null || true)"
  if [ -z "$real" ]; then
    warn "找不到可用的 python/py，跳过 python3 shim；依赖 python 的检查可能失败。"
    return
  fi
  SHIM_DIR="$(mktemp -d)"
  printf '#!/bin/sh\nexec "%s" "$@"\n' "$real" > "$SHIM_DIR/python3"
  chmod +x "$SHIM_DIR/python3"
  export PATH="$SHIM_DIR:$PATH"
  say "python3 是空壳/缺失，已注入真 python shim：$real"
}
# HOLD_STASH=1 时（停在冲突上、等 --continue 收尾）EXIT 不 pop，把 WIP 留到 --continue 再还。
# 其余所有退出路径（成功、检查失败、报错）都由 EXIT trap 兜底 pop，避免 WIP 被静默留在 stash 里。
HOLD_STASH=0
on_exit() {
  [ -n "$SHIM_DIR" ] && rm -rf "$SHIM_DIR" 2>/dev/null || true
  if [ -f "$STASH_MARKER" ] && [ "$HOLD_STASH" = 0 ]; then
    say "恢复之前 stash 的 WIP"
    git stash pop || warn "stash pop 有冲突，请手动 git stash pop 处理"
    rm -f "$STASH_MARKER"
  fi
}
trap on_exit EXIT
setup_python_shim

# ── stash 助手（pop 交给 EXIT trap 统一处理）──────────────────────────────────
auto_stash() {
  if [ -n "$(git status --porcelain)" ]; then
    say "检测到未提交改动，自动 stash（结束后会自动 pop）"
    git stash push -u -m "sync-fork auto-stash $(date -u +%FT%TZ)" >/dev/null
    touch "$STASH_MARKER"
  fi
}

# ── 全套本地检查（Windows-aware；任一失败即返回非零）─────────────────────────────
run_all_checks() {
  say "跑全套本地检查（这一步较慢，含 story-setup 部署回归 >2min）"
  local failures=()
  local -a checks=(
    "node --test scripts/sync-skills.test.js scripts/sync-upstream.test.js"
    "bash scripts/check-current-skill-contracts.sh"
    "bash scripts/check-story-setup-deployment.sh"
    "bash scripts/check-shared-files.sh"
    "bash scripts/check-hook-regex-sync.sh"
    "bash scripts/test-prose-net-parity.sh"
    "node scripts/test-scan-runtime.js"
    "bash scripts/test-codex-hooks.sh"
    "node scripts/test-opencode-plugin.mjs"
    "bash scripts/check-claude-adapter.sh"
    "bash scripts/check-codex-adapter.sh"
    "bash scripts/check-opencode-adapter.sh"
    "bash scripts/check-zcode-adapter.sh"
    "bash scripts/check-reasonix-adapter.sh"
    "python3 scripts/check-unified-skill-upstream-drift.py"
    "bash scripts/static-check.sh"
    "npm run test:dashboard"
  )
  local c
  for c in "${checks[@]}"; do
    printf '  %-55s' "${c:0:55}"
    if eval "$c" >/dev/null 2>&1; then
      printf '\033[32mOK\033[0m\n'
    else
      printf '\033[31mFAIL\033[0m\n'
      failures+=("$c")
    fi
  done
  if [ "${#failures[@]}" -gt 0 ]; then
    warn "以下检查失败，逐条重跑看输出："
    printf '    %s\n' "${failures[@]}" >&2
    return 1
  fi
  say "全套检查通过"
}

# ── 推进 drift baseline 到已合并的上游 SHA ─────────────────────────────────────
advance_baseline() {
  local map="scripts/unified-skill-upstream-map.json"
  local new_sha
  new_sha="$(git rev-parse "$REMOTE/$BRANCH")"
  local cur
  cur="$(python3 -c "import json;print(json.load(open('$map'))['upstream_baseline'])" 2>/dev/null || true)"
  if [ "$cur" = "$new_sha" ]; then
    say "drift baseline 已是最新（$new_sha），无需推进"
    return
  fi
  python3 - "$map" "$new_sha" <<'PY'
import json, sys
path, sha = sys.argv[1], sys.argv[2]
data = json.load(open(path, encoding="utf-8"))
data["upstream_baseline"] = sha
with open(path, "w", encoding="utf-8", newline="\n") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
    f.write("\n")
PY
  git add "$map"
  say "drift baseline 推进到 $new_sha"
}

# ── 冲突分类打印（帮人快速定位判断题）─────────────────────────────────────────
classify_conflicts() {
  local map="scripts/unified-skill-upstream-map.json"
  say "仍有内容冲突（判断题，需人工解）——分类如下："
  git diff --name-only --diff-filter=U | while IFS= read -r f; do
    [ -z "$f" ] && continue
    if grep -qE "agents_version|setup_skill_version|-lt [0-9]+|-gt [0-9]+" "$f" 2>/dev/null \
       && [ "$(grep -c '^<<<<<<< ' "$f" 2>/dev/null)" -gt 0 ]; then
      printf '  \033[36m[可能仅版本号]\033[0m %s\n' "$f"
    else
      printf '  [内容]          %s\n' "$f"
    fi
  done
  cat <<EOF

处理建议：
  - [可能仅版本号]：多半是 fork 文本 + 上游把 agents_version 加了 1，保留 fork 文本、取上游数字即可。
  - [内容]：真正的分叉，按既往约定决定 --ours（保 fork）/ --theirs（取上游）/ 手动移植。
解完并 git add 后，跑：  bash scripts/sync-fork.sh --continue
放弃本次：             git merge --abort
EOF
}

# ── 主流程 ────────────────────────────────────────────────────────────────────
main() {
  if [ "$MODE" = "continue" ]; then
    if [ -n "$(git diff --name-only --diff-filter=U)" ]; then
      warn "还有未解决的冲突，先解完再 --continue"
      git diff --name-only --diff-filter=U | sed 's/^/    /' >&2
      exit 1
    fi
    run_all_checks
    advance_baseline
    say "合并已就绪（WIP 即将 pop 回来）。审阅后 git commit。"
    return
  fi

  auto_stash

  say "调 sync-upstream.js 完成 fetch + merge + 改名目录自动 rm"
  if node scripts/sync-upstream.js --remote "$REMOTE" --branch "$BRANCH"; then
    # sync-upstream.js 自身跑了它那 3 个检查并成功 → 补跑全套 + baseline
    run_all_checks
    advance_baseline
    say "合并已就绪（WIP 即将 pop 回来）。审阅后 git commit。"
  else
    # sync-upstream.js 因内容冲突退出（保守：停下给人）
    if [ -n "$(git diff --name-only --diff-filter=U)" ]; then
      classify_conflicts
      HOLD_STASH=1   # 冲突态不 pop，WIP 留到 --continue 收尾时再还
      exit 1
    fi
    warn "sync-upstream.js 失败但无文件冲突，检查上面的 Git 输出"
    exit 1
  fi
}

main
