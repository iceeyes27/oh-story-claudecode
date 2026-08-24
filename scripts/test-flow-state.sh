#!/bin/bash
# test-flow-state.sh — regression tests for story-write progressive disclosure state.
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
if [ -z "$REPO_ROOT" ]; then
  echo "Error: not in a git repository" >&2
  exit 1
fi

FLOW="$REPO_ROOT/skills/story-write/scripts/flow-state.js"
TMP_DIR="$(mktemp -d)"
cleanup() { rm -rf "$TMP_DIR"; }
trap cleanup EXIT

pass_count=0
fail_count=0

ok() {
  echo "PASS: $1"
  pass_count=$((pass_count + 1))
}

ko() {
  echo "FAIL: $1" >&2
  fail_count=$((fail_count + 1))
}

expect_exit() {
  local expected="$1" label="$2"
  shift 2
  set +e
  "$@" > "$TMP_DIR/last-stdout" 2> "$TMP_DIR/last-stderr"
  local actual=$?
  set -e
  if [ "$actual" -eq "$expected" ]; then
    ok "$label"
  else
    ko "$label (expected exit $expected, got $actual)"
    sed 's/^/  stdout: /' "$TMP_DIR/last-stdout" >&2 || true
    sed 's/^/  stderr: /' "$TMP_DIR/last-stderr" >&2 || true
  fi
}

expect_json_field() {
  local file="$1" expr="$2" label="$3"
  if node -e "const s=require('fs').readFileSync(process.argv[1],'utf8'); const data=JSON.parse(s); if (!($expr)) process.exit(1);" "$file"; then
    ok "$label"
  else
    ko "$label"
    sed 's/^/  json: /' "$file" >&2 || true
  fi
}

echo "Flow State Tests"
echo "==================================="

# --- 1. Long book missing setting is blocked at setting phase ---
BOOK="$TMP_DIR/long-missing-setting"
mkdir -p "$BOOK/追踪"
expect_exit 1 "missing setting blocks long flow" node "$FLOW" --dir "$BOOK" --json detect
cp "$TMP_DIR/last-stdout" "$TMP_DIR/long-missing.json"
expect_json_field "$TMP_DIR/long-missing.json" "data.current_phase === 'setting'" "missing setting phase detected"
expect_json_field "$TMP_DIR/long-missing.json" "data.missing_inputs.includes('题材定位')" "missing topic定位 recorded"

# --- 2. Long book with first outline is ready to write chapter 1 ---
BOOK="$TMP_DIR/long-ready"
mkdir -p "$BOOK/设定" "$BOOK/大纲" "$BOOK/追踪"
printf '# 题材定位\n' > "$BOOK/设定/题材定位.md"
printf '# 第001章细纲\n' > "$BOOK/大纲/细纲_第001章.md"
expect_exit 1 "missing tracking state blocks long writing" node "$FLOW" --dir "$BOOK" --json detect
cp "$TMP_DIR/last-stdout" "$TMP_DIR/long-no-tracking.json"
expect_json_field "$TMP_DIR/long-no-tracking.json" "data.next_action === 'init_tracking'" "missing tracking requests init"
expect_json_field "$TMP_DIR/long-no-tracking.json" "data.missing_inputs.includes('结构化追踪')" "missing tracking recorded"
printf '{}\n' > "$BOOK/追踪/_tracking-state.json"
node "$FLOW" --dir "$BOOK" --json detect > "$TMP_DIR/long-ready.json"
expect_json_field "$TMP_DIR/long-ready.json" "data.current_phase === 'chapter_writing'" "chapter writing phase detected"
expect_json_field "$TMP_DIR/long-ready.json" "data.current_chapter === 1" "first chapter selected"
expect_json_field "$TMP_DIR/long-ready.json" "data.next_action === 'write_chapter_skeleton'" "skeleton action selected"

# --- 2b. Skeleton and candidate are planning/review states, not completed chapters ---
mkdir -p "$BOOK/骨架" "$BOOK/候选"
printf '# 第001章骨架\n' > "$BOOK/骨架/第001章_开篇.md"
node "$FLOW" --dir "$BOOK" --json detect > "$TMP_DIR/long-skeleton-ready.json"
expect_json_field "$TMP_DIR/long-skeleton-ready.json" "data.current_chapter === 1" "skeleton does not advance formal chapter"
expect_json_field "$TMP_DIR/long-skeleton-ready.json" "data.current_stage === 'skeleton_ready'" "skeleton-ready stage detected"
expect_json_field "$TMP_DIR/long-skeleton-ready.json" "data.next_action === 'expand_chapter_skeleton'" "skeleton expansion action selected"

printf '# 第001章候选正文\n' > "$BOOK/候选/第001章_开篇.md"
node "$FLOW" --dir "$BOOK" --json detect > "$TMP_DIR/long-candidate-review.json"
expect_json_field "$TMP_DIR/long-candidate-review.json" "data.current_chapter === 1" "candidate does not advance formal chapter"
expect_json_field "$TMP_DIR/long-candidate-review.json" "data.current_stage === 'candidate_review'" "candidate review stage detected"
expect_json_field "$TMP_DIR/long-candidate-review.json" "data.next_action === 'review_candidate'" "candidate review action selected"
rm -rf "$BOOK/骨架" "$BOOK/候选"

# --- 3. Existing chapter advances to next chapter and requires matching outline ---
printf '# 正文\n' > "$BOOK/正文.tmp"
mkdir -p "$BOOK/正文"
printf '# 第001章\n' > "$BOOK/正文/第001章_开篇.md"
rm -f "$BOOK/大纲/细纲_第002章.md"
printf '# 普通笔记\n' > "$BOOK/大纲/第002章_普通笔记.md"
expect_exit 1 "missing next outline blocks chapter 2" node "$FLOW" --dir "$BOOK" --json detect
cp "$TMP_DIR/last-stdout" "$TMP_DIR/long-ch2-blocked.json"
expect_json_field "$TMP_DIR/long-ch2-blocked.json" "data.current_phase === 'outline'" "chapter 2 outline required"
expect_json_field "$TMP_DIR/long-ch2-blocked.json" "data.current_chapter === 2" "second chapter selected"
printf '# 第002章细纲\n' > "$BOOK/大纲/细纲_第002章.md"
node "$FLOW" --dir "$BOOK" --json detect > "$TMP_DIR/long-ch2-ready.json"
expect_json_field "$TMP_DIR/long-ch2-ready.json" "data.current_phase === 'chapter_writing'" "chapter 2 ready after outline"
expect_json_field "$TMP_DIR/long-ch2-ready.json" "data.artifacts.includes('正文/第001章_开篇.md')" "previous chapter artifact recorded"

# --- 3b. Volume subdirectories are scanned recursively; backups and non-chapter files are ignored ---
VOLUME_BOOK="$TMP_DIR/long-volume"
mkdir -p "$VOLUME_BOOK/设定" "$VOLUME_BOOK/大纲" "$VOLUME_BOOK/追踪" \
  "$VOLUME_BOOK/正文/第1卷_开篇" "$VOLUME_BOOK/正文/第2卷_转折"
printf '# 题材定位\n' > "$VOLUME_BOOK/设定/题材定位.md"
printf '{}\n' > "$VOLUME_BOOK/追踪/_tracking-state.json"
printf '# 第106章\n' > "$VOLUME_BOOK/正文/第2卷_转折/第106章_归队.md"
printf '# 第999章 原稿\n' > "$VOLUME_BOOK/正文/第2卷_转折/第999章_原稿_废稿.md"
mkdir -p "$VOLUME_BOOK/正文/候选"
printf '# 第999章 候选\n' > "$VOLUME_BOOK/正文/候选/第999章_不应计入.md"
printf '# 目录\n' > "$VOLUME_BOOK/正文/第2卷_转折/目录.md"
printf '# 第107章细纲\n' > "$VOLUME_BOOK/大纲/细纲_第107章.md"
node "$FLOW" --dir "$VOLUME_BOOK" --json detect > "$TMP_DIR/long-volume.json"
expect_json_field "$TMP_DIR/long-volume.json" "data.current_chapter === 107" "nested volume chapter advances flow state"
expect_json_field "$TMP_DIR/long-volume.json" "data.artifacts.includes('正文/第2卷_转折/第106章_归队.md')" "nested volume artifact recorded"

# --- 4. --write creates the persistent flow-state file; read returns it ---
node "$FLOW" --dir "$BOOK" --json --write detect > /dev/null
[ -f "$BOOK/追踪/写作流程状态.json" ] && ok "flow state file written" || ko "flow state file missing"
node "$FLOW" --dir "$BOOK" --json read > "$TMP_DIR/read.json"
expect_json_field "$TMP_DIR/read.json" "data.current_chapter === 2" "read returns persisted state"

# --- 5. update merges explicit fields and preserves schema version ---
node "$FLOW" --dir "$BOOK" --json update '{"current_stage":"validate","next_action":"quality_check"}' > "$TMP_DIR/update.json"
expect_json_field "$TMP_DIR/update.json" "data.current_stage === 'validate'" "update changes current stage"
expect_json_field "$TMP_DIR/update.json" "data.schema_version === 1" "schema version preserved"
node "$FLOW" --dir "$BOOK" --json update '{"next_action":"write_chapter"}' > /dev/null
node "$FLOW" --dir "$BOOK" --json update '{"current_stage":"legacy_state_check"}' > "$TMP_DIR/legacy-update.json"
expect_json_field "$TMP_DIR/legacy-update.json" "data.next_action === 'write_chapter'" "legacy write action remains readable during migration"
expect_exit 2 "update rejects unknown field" node "$FLOW" --dir "$BOOK" --json update '{"unexpected":true}'
expect_exit 2 "update rejects unsafe artifact path" node "$FLOW" --dir "$BOOK" --json update '{"artifacts":["../outside.md"]}'

# --- 6. Workspace .active-book is honored ---
WORKSPACE="$TMP_DIR/workspace"
mkdir -p "$WORKSPACE/book-a/设定" "$WORKSPACE/book-a/大纲"
printf 'book-a\n' > "$WORKSPACE/.active-book"
printf '# 题材定位\n' > "$WORKSPACE/book-a/设定/题材定位.md"
printf '# 第001章细纲\n' > "$WORKSPACE/book-a/大纲/细纲_第001章.md"
mkdir -p "$WORKSPACE/book-a/追踪"
printf '{}\n' > "$WORKSPACE/book-a/追踪/_tracking-state.json"
node "$FLOW" --dir "$WORKSPACE" --json detect > "$TMP_DIR/active.json"
expect_json_field "$TMP_DIR/active.json" "data.current_book === 'book-a'" ".active-book selected"
printf '..\\outside\n' > "$WORKSPACE/.active-book"
expect_exit 2 ".active-book parent traversal rejected" node "$FLOW" --dir "$WORKSPACE" --json detect
printf 'book-a/../book-a\n' > "$WORKSPACE/.active-book"
expect_exit 2 ".active-book internal parent traversal rejected" node "$FLOW" --dir "$WORKSPACE" --json detect
printf '%s\n' "$TMP_DIR/book-a" > "$WORKSPACE/.active-book"
expect_exit 2 ".active-book absolute path rejected" node "$FLOW" --dir "$WORKSPACE" --json detect

# --- 7. Short story routes to quality check when body exists ---
SHORT="$TMP_DIR/short"
mkdir -p "$SHORT"
printf '# 设定\n' > "$SHORT/设定.md"
printf '# 小节大纲\n' > "$SHORT/小节大纲.md"
printf '正文内容\n' > "$SHORT/正文.md"
node "$FLOW" --dir "$SHORT" --json detect > "$TMP_DIR/short.json"
expect_json_field "$TMP_DIR/short.json" "data.mode === 'short'" "short mode detected"
expect_json_field "$TMP_DIR/short.json" "data.current_phase === 'quality_check'" "short body routes to quality check"

# --- 8. Existing short body can still be checked when setup files are missing ---
SHORT_GAPS="$TMP_DIR/short-gaps"
mkdir -p "$SHORT_GAPS"
printf '正文内容\n' > "$SHORT_GAPS/正文.md"
node "$FLOW" --dir "$SHORT_GAPS" --json detect > "$TMP_DIR/short-gaps.json"
expect_json_field "$TMP_DIR/short-gaps.json" "data.current_phase === 'quality_check'" "short body with gaps still routes to quality check"
expect_json_field "$TMP_DIR/short-gaps.json" "data.current_stage === 'validate_with_gaps'" "short body gaps are visible"
expect_json_field "$TMP_DIR/short-gaps.json" "data.missing_inputs.includes('短篇设定') && data.missing_inputs.includes('小节大纲')" "short body gaps list missing inputs"

# --- 9. update validates next_action and Windows-style artifact boundaries ---
expect_exit 2 "update rejects unknown next_action" node "$FLOW" --dir "$BOOK" --json update '{"next_action":"invent_new_flow"}'
expect_exit 2 "update rejects internal parent artifact path" node "$FLOW" --dir "$BOOK" --json update '{"artifacts":["a/../b.md"]}'
expect_exit 2 "update rejects Windows drive-relative artifact path" node "$FLOW" --dir "$BOOK" --json update '{"artifacts":["C:foo.md"]}'

echo
echo "==================================="
echo "passed: $pass_count, failed: $fail_count"
if [ "$fail_count" -gt 0 ]; then
  exit 1
fi
echo "All flow state tests passed."
