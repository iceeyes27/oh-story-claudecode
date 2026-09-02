#!/usr/bin/env bash
# test-codex-hooks.sh — synthetic Codex hook contract tests.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
# Windows 上裸 python3 落到 Microsoft Store 占位程序（exit 49、空输出）；shim 委托真 python。
. "$REPO_ROOT/scripts/python3-shim.sh"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

fail() { echo "FAIL: $*" >&2; exit 1; }

HOOKS_SRC="$REPO_ROOT/skills/story-setup/references/codex/hooks"
HOOK_SRC="$HOOKS_SRC/story_codex_hook.py"
ROOT="$TMP_DIR/story-project"
HOOK="$ROOT/.codex/hooks/story_codex_hook.py"
mkdir -p "$ROOT/.codex/hooks"
cp "$HOOK_SRC" "$HOOK"
cp "$HOOKS_SRC/run-story-hook.sh" "$HOOKS_SRC/run-story-hook.cmd" "$HOOKS_SRC/book-discovery-contract.json" "$ROOT/.codex/hooks/"
chmod +x "$HOOK"

git -C "$ROOT" init -q
git -C "$ROOT" config user.email codex-hook@example.invalid
git -C "$ROOT" config user.name codex-hook-test

run_hook() {
  local event="$1" payload="$2"
  (cd "$ROOT" && printf '%s' "$payload" | CODEX_PROJECT_DIR="$ROOT" python3 "$HOOK" "$event")
}

# Read the hook's stdout as UTF-8 bytes (not locale-decoded text): the hook emits
# UTF-8 Chinese deny reasons, and Windows Python defaults stdin to the ANSI code page,
# which would raise UnicodeDecodeError here even when the hook output is correct.
assert_json() {
  python3 -c 'import json,sys; json.loads(sys.stdin.buffer.read().decode("utf-8"))' >/dev/null
}

assert_denied() {
  local out="$1" label="$2"
  printf '%s' "$out" | assert_json || fail "$label did not emit valid JSON: $out"
  printf '%s' "$out" | python3 -c 'import json,sys; o=json.loads(sys.stdin.buffer.read().decode("utf-8")); h=o.get("hookSpecificOutput",{}); assert h.get("hookEventName")=="PreToolUse" and h.get("permissionDecision")=="deny" and h.get("permissionDecisionReason")' || fail "$label was not denied: $out"
}

assert_additional_context() {
  local out="$1" label="$2"
  printf '%s' "$out" | assert_json || fail "$label did not emit valid JSON: $out"
  printf '%s' "$out" | python3 -c 'import json,sys; o=json.loads(sys.stdin.buffer.read().decode("utf-8")); h=o.get("hookSpecificOutput",{}); assert h.get("additionalContext")' || fail "$label missing additionalContext: $out"
}

assert_empty() {
  local out="$1" label="$2"
  [ -z "$out" ] || fail "$label expected empty allow output, got: $out"
}

write_clean_state() {
  mkdir -p "$1/追踪"
  printf '{"schema_version":4,"state_revision":0,"last_committed_chapter":%s}\n' "${2:-0}" > "$1/追踪/_tracking-state.json"
  printf '%s\n' '> 状态修订：0' > "$1/追踪/上下文.md"
}

echo "Codex hook synthetic tests"
echo "=========================="
echo "Fixture: $ROOT"

mkdir -p "$ROOT/book/正文" "$ROOT/book/大纲" "$ROOT/book/设定"
out="$(run_hook pre-tool-prose-guard '{"tool_name":"Bash","tool_input":{"command":"cat > book/正文/第001章_开端.md <<EOF\n正文\nEOF"}}')"
assert_denied "$out" "long prose without outline"
: > "$ROOT/book/大纲/细纲_第1章.md"
out="$(run_hook pre-tool-prose-guard '{"tool_name":"Bash","tool_input":{"command":"cat > book/正文/第001章_开端.md <<EOF\n正文\nEOF"}}')"
assert_denied "$out" "long prose without tracking metadata"
printf '%s' "$out" | grep -q '_tracking-state.json 缺失' || fail "missing tracking denial did not explain re-import/init: $out"
write_clean_state "$ROOT/book"
out="$(run_hook pre-tool-prose-guard '{"tool_name":"Bash","tool_input":{"command":"cat > book/正文/第001章_开端.md <<EOF\n正文\nEOF"}}')"
assert_empty "$out" "long prose with outline"

mkdir -p "$ROOT/bare/正文" "$ROOT/cwd-book/正文" "$ROOT/cwd-book/大纲"
out="$(run_hook pre-tool-prose-guard '{"tool_name":"Write","tool_input":{"file_path":"bare/正文/第1章_首章.md"}}')"
assert_denied "$out" "bare long project without scaffolding"
relative_payload="$(python3 - "$ROOT/cwd-book" <<'PY'
import json, sys
from pathlib import Path
payload = {"cwd": str(Path(sys.argv[1]).resolve()), "tool_name": "Write", "tool_input": {"file_path": "正文/第8章_相对.md"}}
sys.stdout.buffer.write(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
PY
)"
out="$(run_hook pre-tool-prose-guard "$relative_payload")"
assert_denied "$out" "relative prose target from hook cwd"
printf '%s' "$out" | grep -q 'cwd-book/大纲' || fail "relative target was not resolved from hook cwd: $out"
: > "$ROOT/cwd-book/大纲/细纲_第8章.md"
out="$(run_hook pre-tool-prose-guard "$relative_payload")"
assert_denied "$out" "relative prose target without tracking metadata"
write_clean_state "$ROOT/cwd-book" 7
out="$(run_hook pre-tool-prose-guard "$relative_payload")"
assert_empty "$out" "relative prose target with cwd-local outline"

out="$(run_hook pre-tool-prose-guard '{"tool_name":"apply_patch","tool_input":{"command":"*** Begin Patch\n*** Add File: book/正文/第002章_新局.md\n+正文\n*** End Patch\n"}}')"
assert_denied "$out" "apply_patch long prose without outline"
: > "$ROOT/book/正文/第009章_已存在.md"
out="$(run_hook pre-tool-prose-guard '{"tool_name":"Write","tool_input":{"file_path":"book/正文/第009章_已存在.md","content":"改稿"}}')"
assert_empty "$out" "existing prose rewrite"
printf '%s\n' '{"schema_version":4,"state_revision":1,"last_committed_chapter":0}' > "$ROOT/book/追踪/_tracking-state.json"
out="$(run_hook pre-tool-prose-guard '{"tool_name":"Write","tool_input":{"file_path":"book/正文/第009章_已存在.md","content":"改稿"}}')"
assert_denied "$out" "existing prose rewrite with mismatched derived state"
printf '%s' "$out" | grep -q 'mode=revision 事务重建派生视图' || fail "state mismatch denial missed retry action: $out"
write_clean_state "$ROOT/book"

mkdir -p "$ROOT/short"
: > "$ROOT/short/设定.md"
out="$(run_hook pre-tool-prose-guard '{"tool_name":"Write","tool_input":{"file_path":"short/正文.md","content":"正文"}}')"
assert_denied "$out" "short prose without outline"
: > "$ROOT/short/小节大纲.md"
out="$(run_hook pre-tool-prose-guard '{"tool_name":"Write","tool_input":{"file_path":"short/正文.md","content":"正文"}}')"
assert_empty "$out" "short prose with outline"

mkdir -p "$ROOT/impbook/正文" "$ROOT/拆文库/impbook"
out="$(run_hook pre-tool-prose-guard '{"tool_name":"Write","tool_input":{"file_path":"impbook/正文/第1章_导入.md","content":"正文"}}')"
assert_empty "$out" "story-import long migration"
mkdir -p "$ROOT/impbook/大纲" "$ROOT/impbook/追踪"
: > "$ROOT/impbook/大纲/细纲_第2章.md"
printf '%s\n' '{"schema_version":4,"state_revision":1,"last_committed_chapter":1}' > "$ROOT/impbook/追踪/_tracking-state.json"
printf '%s\n' '> 状态修订：0' > "$ROOT/impbook/追踪/上下文.md"
out="$(run_hook pre-tool-prose-guard '{"tool_name":"Write","tool_input":{"file_path":"impbook/正文/第2章_导入后续.md","content":"正文"}}')"
assert_denied "$out" "imported project must not permanently bypass invalid tracking guard"

echo "  OK outline-before-prose guard"

# The shared parser's full syntax matrix lives in test-prose-net-parity.sh. Here we only verify
# that the Codex adapter forwards one write and one read-only mention correctly.
out="$(run_hook pre-tool-prose-guard '{"tool_name":"Bash","tool_input":{"command":"grep -n book/正文/第7章.md notes.md"}}')"
assert_empty "$out" "command merely mentioning prose path is not denied"
out="$(run_hook pre-tool-prose-guard '{"tool_name":"Bash","tool_input":{"command":"cat draft.md > book/正文/第7章_x.md"}}')"
assert_denied "$out" "write to prose without outline is denied"

echo "  OK prose command-scan precision"

cat > "$ROOT/book/正文/第1章.md" <<'TXT'
年龄：18
TXT
cat > "$ROOT/short/正文.md" <<'TXT'
身高: 180
TXT
git -C "$ROOT" add book/正文/第1章.md short/正文.md
out="$(run_hook pre-tool-commit-advisory '{"tool_name":"Bash","tool_input":{"command":"git commit -m test"}}')"
assert_additional_context "$out" "commit advisory"
echo "$out" | grep -q '正文硬编码角色属性' || fail "commit advisory did not inspect staged markdown"
echo "$out" | grep -q 'short/正文.md' || fail "commit advisory missed short prose"
out="$(run_hook pre-tool-commit-advisory '{"tool_name":"Bash","tool_input":{"command":"echo git commit docs"}}')"
assert_empty "$out" "non-commit bash command"

echo "  OK commit advisory"

mkdir -p "$ROOT/book/追踪"
cat > "$ROOT/.story-deployed" <<'TXT'
deployed_at: 2026-06-25T00:00:00Z
agents_version: 19
setup_skill_version: 1.2.9
target_cli: codex
resolver_strategy: project-local-skill-reference
references_dir: .codex/skills/story-setup/references/agent-references
TXT
printf 'book\n' > "$ROOT/.active-book"
printf '%s\n' '> 状态修订：0' > "$ROOT/book/追踪/上下文.md"
out="$(run_hook session-start '{"hook_event_name":"SessionStart"}')"
assert_additional_context "$out" "session-start context"
echo "$out" | grep -q 'Active book' || fail "session-start did not mention active book"
printf '%s\n' '{"schema_version":4,"state_revision":1,"last_committed_chapter":0}' > "$ROOT/book/追踪/_tracking-state.json"
out="$(run_hook session-start '{"hook_event_name":"SessionStart"}')"
assert_additional_context "$out" "session-start tracking mismatch warning"
echo "$out" | grep -q '状态修订' || fail "session-start missed tracking revision mismatch: $out"
write_clean_state "$ROOT/book"
out="$(run_hook pre-compact '{"hook_event_name":"PreCompact"}')"
printf '%s' "$out" | assert_json || fail "pre-compact invalid JSON: $out"
echo "$out" | grep -q 'Story Compact Summary' || fail "pre-compact missing summary"
out="$(run_hook post-compact '{"hook_event_name":"PostCompact"}')"
printf '%s' "$out" | assert_json || fail "post-compact invalid JSON: $out"
out="$(run_hook stop '{"hook_event_name":"Stop"}')"
printf '%s' "$out" | assert_json || fail "stop invalid JSON: $out"

echo "  OK session/compact/stop JSON"

# ── Stop content sweep: Codex 无 PostToolUse，回合结束对 git 改动正文复扫硬信号（轻量网）──
# 新写一章带截断、留作 git 改动（untracked）→ stop 必须点名并报截断；非改动文件不复扫。
PAD6='江晨握紧拳头慢慢走向门口盘算着每一步。'  # bash 重复填充，避开 Windows python 文本 stdout 的 cp1252 崩溃
printf '# 第6章\n\n%s\n他冲过去一拳砸在' "$PAD6$PAD6$PAD6$PAD6$PAD6$PAD6" > "$ROOT/book/正文/第006章_截断.md"
out="$(run_hook stop '{"hook_event_name":"Stop"}')"
printf '%s' "$out" | assert_json || fail "stop content-sweep invalid JSON: $out"
echo "$out" | grep -q '截断' || fail "stop did not flag truncated git-changed prose: $out"
echo "$out" | grep -q '第006章_截断.md' || fail "stop did not name the changed prose file: $out"
# 已提交（无 git 改动）的章节不应被复扫——只兜本回合改动集。
git -C "$ROOT" add -A && git -C "$ROOT" commit -qm wip >/dev/null 2>&1
out="$(run_hook stop '{"hook_event_name":"Stop"}')"
printf '%s' "$out" | python3 -c 'import json,sys; o=json.loads(sys.stdin.buffer.read().decode("utf-8")); assert "截断" not in o.get("systemMessage","")' || fail "stop re-flagged already-committed prose: $out"
echo "  OK stop content sweep (git-changed only)"

# ── SessionStart continuity: 追踪 staleness（写了章但 上下文.md 没跟上）+ 章节标题去重 ──
mkdir -p "$ROOT/contbook/正文" "$ROOT/contbook/追踪"
write_clean_state "$ROOT/contbook"
printf '> 状态修订：0\n旧上下文\n' > "$ROOT/contbook/追踪/上下文.md"
python3 - "$ROOT/contbook/追踪/上下文.md" <<'PY'
import os, sys, time
old = time.time() - 5
os.utime(sys.argv[1], (old, old))
PY
printf '# 第1章 决战\n正文。\n' > "$ROOT/contbook/正文/第001章_决战.md"
printf '# 第2章 决战\n正文。\n' > "$ROOT/contbook/正文/第002章_决战.md"
out="$(run_hook session-start '{"hook_event_name":"SessionStart"}')"
assert_additional_context "$out" "session-start continuity"
echo "$out" | grep -q '续写状态卡更早' || fail "session-start missed 追踪 staleness: $out"
echo "$out" | grep -q '标题重复' || fail "session-start missed dup-title: $out"
echo "  OK session-start continuity (追踪 staleness + dup-title)"

# 目录发现只看推荐结构深度，且不进入 node_modules/隐藏目录。Bash/Python/共享 JS 核应一致。
DISCOVERY_ROOT="$TMP_DIR/discovery-root"
mkdir -p "$DISCOVERY_ROOT/shallow/追踪" \
  "$DISCOVERY_ROOT/node_modules/fake/追踪" \
  "$DISCOVERY_ROOT/.hidden/fake/追踪" \
  "$DISCOVERY_ROOT/a/b/c/d/e/deep/追踪"
python_discovered="$(python3 - "$HOOK_SRC" "$DISCOVERY_ROOT" <<'PY'
import importlib.util, sys
from pathlib import Path
spec = importlib.util.spec_from_file_location("story_codex_hook", sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
root = Path(sys.argv[2])
active = module.read_active_book(root)
all_books = "|".join(sorted(p.relative_to(root).as_posix() for p in module._discover_all_books(root)))
print(f"{active.relative_to(root).as_posix() if active else ''};{all_books}")
PY
)"
[ "$python_discovered" = "shallow;shallow" ] || fail "Codex discovery crossed depth/ignored dirs: $python_discovered"
node_discovered="$(node - "$HOOKS_SRC/../../templates/hooks/story_hook_core.js" "$DISCOVERY_ROOT" <<'JS'
const core = require(process.argv[2]);
const path = require("node:path");
const root = process.argv[3];
const active = core.discoverActiveBook(root);
const allBooks = core.discoverAllBooks(root).map((p) => path.relative(root, p).split(path.sep).join("/")).sort().join("|");
process.stdout.write(`${active ? path.relative(root, active).split(path.sep).join("/") : ""};${allBooks}`);
JS
)"
[ "$node_discovered" = "shallow;shallow" ] || fail "JS discovery crossed depth/ignored dirs: $node_discovered"
bash_discovered="$(CLAUDE_PROJECT_DIR="$DISCOVERY_ROOT" bash -s -- "$HOOKS_SRC/../../templates/hooks/lib/common.sh" "$DISCOVERY_ROOT" <<'SH'
source "$1"
root="$(project_root)"
active="$(discover_active_book)"
all_books="$(discover_all_books | while IFS= read -r p; do printf '%s\n' "${p#$root/}"; done | sort | paste -sd '|' -)"
printf '%s;%s' "${active#$root/}" "$all_books"
SH
)"
[ "$bash_discovered" = "shallow;shallow" ] || fail "Bash discovery crossed depth/ignored dirs: $bash_discovered"

# `.active-book` 不能通过目录 symlink 逃到项目根外；无效声明统一回落自动发现。
OUTSIDE_BOOK="$TMP_DIR/outside-book"
mkdir -p "$OUTSIDE_BOOK/追踪"
# Windows/MSYS 没有创建符号链接的权限时 ln -s 会静默退化成「复制目录」：逃逸场景根本没复现，
# 复制出来的 escape/追踪 还会被后面的深度断言当成一本书。必须确认真的拿到 symlink 才跑这段。
if ln -s "$OUTSIDE_BOOK" "$DISCOVERY_ROOT/escape" 2>/dev/null && [ -L "$DISCOVERY_ROOT/escape" ]; then
  printf '%s\n' 'escape' > "$DISCOVERY_ROOT/.active-book"
  python_active="$(python3 - "$HOOK_SRC" "$DISCOVERY_ROOT" <<'PY'
import importlib.util, sys
from pathlib import Path
spec=importlib.util.spec_from_file_location("h",sys.argv[1]);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
r=Path(sys.argv[2]); p=m.read_active_book(r); print(p.relative_to(r).as_posix() if p else "")
PY
)"
  node_active="$(node - "$HOOKS_SRC/../../templates/hooks/story_hook_core.js" "$DISCOVERY_ROOT" <<'JS'
const c=require(process.argv[2]),p=require('node:path'),r=process.argv[3],v=c.discoverActiveBook(r);process.stdout.write(v?p.relative(r,v).split(p.sep).join('/'):"");
JS
)"
  bash_active="$(CLAUDE_PROJECT_DIR="$DISCOVERY_ROOT" bash -s -- "$HOOKS_SRC/../../templates/hooks/lib/common.sh" <<'SH'
source "$1"; discover_active_book
SH
)"
  [ "$python_active" = "shallow" ] || fail "Python accepted out-of-root .active-book symlink: $python_active"
  [ "$node_active" = "shallow" ] || fail "JS accepted out-of-root .active-book symlink: $node_active"
  DISCOVERY_REAL="$(cd "$DISCOVERY_ROOT" && pwd -P)"
  [ "$bash_active" = "$DISCOVERY_REAL/shallow" ] || fail "Bash accepted out-of-root .active-book symlink: $bash_active"
  rm -f "$DISCOVERY_ROOT/.active-book"
  rm -f "$DISCOVERY_ROOT/escape"
else
  # ln -s 失败或退化成复制：清掉残留，避免污染下面的 maxdepth 4 发现断言。
  rm -rf "$DISCOVERY_ROOT/escape"
fi

# `find -maxdepth 4` 的边界：marker 本身在深度 4 可见，深度 5 不可见；三端不能 off-by-one。
mkdir -p "$DISCOVERY_ROOT/a/b/book/追踪" "$DISCOVERY_ROOT/a/b/c/book/追踪"
python_books="$(python3 - "$HOOK_SRC" "$DISCOVERY_ROOT" <<'PY'
import importlib.util, sys
from pathlib import Path
spec = importlib.util.spec_from_file_location("story_codex_hook", sys.argv[1])
module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
root = Path(sys.argv[2])
print("|".join(sorted(p.relative_to(root).as_posix() for p in module._discover_all_books(root))))
PY
)"
node_books="$(node - "$HOOKS_SRC/../../templates/hooks/story_hook_core.js" "$DISCOVERY_ROOT" <<'JS'
const core = require(process.argv[2]); const path = require("node:path"); const root = process.argv[3];
process.stdout.write(core.discoverAllBooks(root).map((p) => path.relative(root,p).split(path.sep).join("/")).sort().join("|"));
JS
)"
bash_books="$(CLAUDE_PROJECT_DIR="$DISCOVERY_ROOT" bash -s -- "$HOOKS_SRC/../../templates/hooks/lib/common.sh" "$DISCOVERY_ROOT" <<'SH'
source "$1"; root="$(project_root)"
discover_all_books | while IFS= read -r p; do printf '%s\n' "${p#$root/}"; done | sort | paste -sd '|' -
SH
)"
[ "$python_books" = "a/b/book|shallow" ] || fail "Python depth-4 discovery mismatch: $python_books"
[ "$node_books" = "a/b/book|shallow" ] || fail "JS depth-4 discovery mismatch: $node_books"
[ "$bash_books" = "a/b/book|shallow" ] || fail "Bash depth-4 discovery mismatch: $bash_books"
echo "  OK bounded directory discovery (depth 4, hidden/node_modules pruned, Bash/JS/Python parity)"

nested="$ROOT/nested/a/b"
mkdir -p "$nested"
out="$(cd "$TMP_DIR" && printf '{"cwd":"%s","tool_name":"Write","tool_input":{"file_path":"book/正文/第003章_嵌套.md","content":"正文"}}' "$nested" | python3 "$HOOK" pre-tool-prose-guard)"
assert_denied "$out" "cwd-based root resolution"

echo "  OK cwd-based root resolution"

# __file__ self-location (the Windows-critical resolver) on ALL platforms: with a bogus
# CODEX_PROJECT_DIR (env skipped) and an unrelated cwd, the hook must resolve root from its own
# .codex/hooks/ location. Discriminating: 细纲 exists at the true root, so a wrong root → deny;
# only __file__-derived root → allow. (The valid-env tests above let env win and never hit this.)
: > "$ROOT/book/大纲/细纲_第8章.md"
write_clean_state "$ROOT/book" 7
out="$(cd "$TMP_DIR" && CODEX_PROJECT_DIR="$TMP_DIR/does-not-exist" python3 "$HOOK" pre-tool-prose-guard <<'JSON'
{"tool_name":"Write","tool_input":{"file_path":"book/正文/第8章_x.md","content":"x"}}
JSON
)"
assert_empty "$out" "__file__ self-location resolves root when env is bogus and cwd unrelated"
rm -f "$ROOT/book/大纲/细纲_第8章.md"

echo "  OK __file__ self-location (all platforms)"

NON_GIT="$TMP_DIR/non-git-story-project"
NON_GIT_HOOK="$NON_GIT/.codex/hooks/story_codex_hook.py"
mkdir -p "$NON_GIT/.codex/hooks" "$NON_GIT/book/正文" "$NON_GIT/book/大纲" "$NON_GIT/nested/a/b"
cp "$HOOK_SRC" "$NON_GIT_HOOK"
cp "$HOOKS_SRC/run-story-hook.sh" "$HOOKS_SRC/run-story-hook.cmd" "$HOOKS_SRC/book-discovery-contract.json" "$NON_GIT/.codex/hooks/"
cp "$REPO_ROOT/skills/story-setup/references/codex/hooks/hooks.json" "$NON_GIT/.codex/hooks.json"
launcher_cmd="$(
  NON_GIT="$NON_GIT" python3 - <<'PY'
import json, os
from pathlib import Path
hooks = json.loads((Path(os.environ["NON_GIT"]) / ".codex/hooks.json").read_text(encoding="utf-8"))
print(hooks["hooks"]["PreToolUse"][0]["hooks"][0]["command"])
PY
)"
out="$(
  cd "$NON_GIT/nested/a/b"
  printf '{"tool_name":"Write","tool_input":{"file_path":"book/正文/第004章_非Git.md","content":"正文"}}' | eval "$launcher_cmd"
)"
assert_denied "$out" "non-git deployment launcher root search"

echo "  OK non-git deployment launcher root search"

# Root propagation: non-git project, outline PRESENT at the true root, triggered from a nested
# cwd → must ALLOW. The launcher resolves the root in shell; it must reach the Python hook
# (via CODEX_PROJECT_DIR and/or the hook self-locating from __file__) instead of Python falling
# back to the nested cwd and wrongly denying. This case also exercises Windows (Git Bash MSYS
# path passed to native Python), which is exactly where naive env/cwd propagation breaks.
: > "$NON_GIT/book/大纲/细纲_第4章.md"
write_clean_state "$NON_GIT/book" 3
out="$(cd "$NON_GIT/nested/a/b"; unset CODEX_PROJECT_DIR CLAUDE_PROJECT_DIR; printf '{"tool_name":"Write","tool_input":{"file_path":"book/正文/第004章_非Git.md","content":"正文"}}' | eval "$launcher_cmd")"
assert_empty "$out" "non-git nested cwd + outline present allows (root reaches Python hook)"
rm -f "$NON_GIT/book/大纲/细纲_第4章.md"

echo "  OK non-git nested root propagation"

case "$(uname -s 2>/dev/null || true)" in
  MINGW*|MSYS*|CYGWIN*)
    NON_GIT="$NON_GIT" python3 - <<'PY'
import json
import os
import subprocess
from pathlib import Path

root = Path(os.environ["NON_GIT"])
hooks = json.loads((root / ".codex/hooks.json").read_text(encoding="utf-8"))["hooks"]
command = hooks["PreToolUse"][0]["hooks"][0]["commandWindows"]
# bytes literals must be ASCII (b'中文' is a SyntaxError); build the str, then encode to UTF-8.
payload = '{"tool_name":"Write","tool_input":{"file_path":"book/正文/第004章_非Git.md","content":"正文"}}'.encode("utf-8")
completed = subprocess.run(
    command,
    cwd=root / "nested/a/b",
    input=payload,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    shell=True,
    timeout=20,
)
assert completed.returncode == 0, completed.stderr.decode("utf-8", "replace")
output = completed.stdout.decode("utf-8")
data = json.loads(output)
specific = data.get("hookSpecificOutput", {})
assert specific.get("permissionDecision") == "deny", output
PY
    echo "  OK commandWindows nested root + interpreter launcher"
    ;;
esac

# Missing deployment: a cwd whose ancestors have no .codex/hooks/story_codex_hook.py → the
# launcher must no-op (exit 0) silently, NOT run "//.codex/hooks/story_codex_hook.py" (which
# happens if it treats "/" as the project root after an exhausted upward search).
NO_DEPLOY="$TMP_DIR/no-deploy/x/y"
mkdir -p "$NO_DEPLOY"
out="$(cd "$NO_DEPLOY"; unset CODEX_PROJECT_DIR CLAUDE_PROJECT_DIR; printf '{"tool_name":"Write","tool_input":{"file_path":"book/正文/第1章.md","content":"正文"}}' | eval "$launcher_cmd" 2>&1)"
assert_empty "$out" "missing deployment launcher no-ops silently"
case "$out" in *//.codex*) fail "launcher executed //.codex/... on missing deployment: $out";; esac

echo "  OK missing-deployment launcher no-op"

# ── 书目发现契约：marker 距根最多 4 层；三端都忽略点目录/node_modules/符号链接。──
DISCOVERY_ROOT="$TMP_DIR/discovery-project"
mkdir -p "$DISCOVERY_ROOT/l1/book3/追踪" \
         "$DISCOVERY_ROOT/l1/l2/book4/正文" \
         "$DISCOVERY_ROOT/l1/l2/l3/book5/追踪" \
         "$DISCOVERY_ROOT/node_modules/pkg/book/追踪" \
         "$DISCOVERY_ROOT/.hidden/book/追踪" \
         "$DISCOVERY_ROOT/.git/book/追踪" \
         "$TMP_DIR/outside-book/追踪"
# Windows/MSYS 无 symlink 权限时 ln -s 会静默退化成复制目录：linkout 会变成含 book 的真实目录，
# 污染下面的 maxdepth 发现断言。必须用 [ -L ] 确认拿到真符号链接，退化时清掉残留并跳过依赖它的
# 逃逸用例（与本文件上方逃逸测试同一处理）。
if ln -s "$TMP_DIR/outside-book" "$DISCOVERY_ROOT/linkout" 2>/dev/null && [ -L "$DISCOVERY_ROOT/linkout" ]; then
  HAS_DISCOVERY_SYMLINK=1
else
  rm -rf "$DISCOVERY_ROOT/linkout"
  HAS_DISCOVERY_SYMLINK=0
fi

expected_books=$'l1/book3\nl1/l2/book4'
python_books="$(DISCOVERY_ROOT="$DISCOVERY_ROOT" HOOK="$HOOK" python3 - <<'PY'
import importlib.util, os
from pathlib import Path
spec = importlib.util.spec_from_file_location("story_codex_hook", os.environ["HOOK"])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
root = Path(os.environ["DISCOVERY_ROOT"])
print("\n".join(sorted(path.relative_to(root).as_posix() for path in module._discover_all_books(root))))
PY
)"
[ "${python_books//$'\r'/}" = "$expected_books" ] || fail "Python discovery violated depth/prune contract: $python_books"

js_books="$(DISCOVERY_ROOT="$DISCOVERY_ROOT" CORE="$REPO_ROOT/skills/story-setup/references/templates/hooks/story_hook_core.js" node - <<'NODE'
const path = require("path")
const core = require(process.env.CORE)
const root = process.env.DISCOVERY_ROOT
process.stdout.write(core.discoverAllBooks(root).map((book) => path.relative(root, book).split(path.sep).join("/")).sort().join("\n"))
NODE
)"
[ "$js_books" = "$expected_books" ] || fail "JS discovery violated depth/prune contract: $js_books"

bash_books="$(CLAUDE_PROJECT_DIR="$DISCOVERY_ROOT" COMMON="$REPO_ROOT/skills/story-setup/references/templates/hooks/lib/common.sh" bash -c 'source "$COMMON"; discover_all_books' \
  | while IFS= read -r book; do printf '%s\n' "${book#"$DISCOVERY_ROOT"/}"; done | sort)"
[ "$bash_books" = "$expected_books" ] || fail "Bash discovery violated depth/prune contract: $bash_books"

printf '../outside-book\n' > "$DISCOVERY_ROOT/.active-book"
active_book="$(DISCOVERY_ROOT="$DISCOVERY_ROOT" HOOK="$HOOK" python3 - <<'PY'
import importlib.util, os
from pathlib import Path
spec = importlib.util.spec_from_file_location("story_codex_hook", os.environ["HOOK"])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
root = Path(os.environ["DISCOVERY_ROOT"])
book = module.read_active_book(root)
print(book.relative_to(root).as_posix() if book else "")
PY
)"
[ "${active_book//$'\r'/}" = "l1/book3" ] || fail "out-of-root .active-book was accepted: $active_book"
if [ "$HAS_DISCOVERY_SYMLINK" = 1 ]; then
  printf 'linkout\n' > "$DISCOVERY_ROOT/.active-book"
  active_book="$(DISCOVERY_ROOT="$DISCOVERY_ROOT" HOOK="$HOOK" python3 - <<'PY'
import importlib.util, os
from pathlib import Path
spec = importlib.util.spec_from_file_location("story_codex_hook", os.environ["HOOK"])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
root = Path(os.environ["DISCOVERY_ROOT"])
book = module.read_active_book(root)
print(book.relative_to(root).as_posix() if book else "")
PY
)"
  [ "${active_book//$'\r'/}" = "l1/book3" ] || fail "symlink .active-book was accepted: $active_book"

  rm "$DISCOVERY_ROOT/linkout"
  ln -s "$DISCOVERY_ROOT/l1/l2/book4" "$DISCOVERY_ROOT/linkin"
  printf 'linkin\n' > "$DISCOVERY_ROOT/.active-book"
  bash_active_book="$(CLAUDE_PROJECT_DIR="$DISCOVERY_ROOT" COMMON="$REPO_ROOT/skills/story-setup/references/templates/hooks/lib/common.sh" bash -c 'source "$COMMON"; discover_active_book')"
  bash_active_book="${bash_active_book#"$DISCOVERY_ROOT"/}"
  [ "$bash_active_book" = "l1/book3" ] || fail "Bash accepted in-root symlink .active-book: $bash_active_book"
  js_active_book="$(DISCOVERY_ROOT="$DISCOVERY_ROOT" CORE="$REPO_ROOT/skills/story-setup/references/templates/hooks/story_hook_core.js" node - <<'NODE'
const path = require("path")
const core = require(process.env.CORE)
const root = process.env.DISCOVERY_ROOT
process.stdout.write(path.relative(root, core.discoverActiveBook(root)).split(path.sep).join("/"))
NODE
)"
  [ "$js_active_book" = "l1/book3" ] || fail "JS accepted in-root symlink .active-book: $js_active_book"
  active_book="$(DISCOVERY_ROOT="$DISCOVERY_ROOT" HOOK="$HOOK" python3 - <<'PY'
import importlib.util, os
from pathlib import Path
spec = importlib.util.spec_from_file_location("story_codex_hook", os.environ["HOOK"])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
root = Path(os.environ["DISCOVERY_ROOT"])
book = module.read_active_book(root)
print(book.relative_to(root).as_posix() if book else "")
PY
)"
  [ "${active_book//$'\r'/}" = "l1/book3" ] || fail "Python accepted in-root symlink .active-book: $active_book"
fi
echo "  OK bounded book discovery parity"

# 注：本 fork v25 起写正文守卫核（含 Codex story_codex_hook.py）整份采纳上游实现。上游用
# 内联 `re.search(r"target_cli:\s*(.*)")` 判定 codex，未提供 fork 早前的 `parse_target_cli`
# 严格逗号 token 校验，故此处不再断言该函数。若需恢复严格 token 判定，见 UPGRADING.md v25。
echo ""
echo "OK: Codex hook synthetic tests passed"
