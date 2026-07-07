#!/bin/bash
# test-state-store.sh — regression tests for the structured state store (state-query.js):
# 分片路由、时点快照折叠、活跃/超期伏笔、矛盾检测（死亡后活动/未埋先收/重复回收/分片错位）。
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
if [ -z "$REPO_ROOT" ]; then
  echo "Error: not in a git repository" >&2
  exit 1
fi

SQ="$REPO_ROOT/skills/story-long-write/scripts/state-query.js"
TMP_DIR="$(mktemp -d)"
cleanup() { rm -rf "$TMP_DIR"; }
trap cleanup EXIT

BOOK="$TMP_DIR/book"
STORE="$BOOK/追踪/状态库"
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
  # expect_exit <expected-code> <label> <cmd...>
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

expect_grep() {
  # expect_grep <pattern> <file> <label>
  if grep -q "$1" "$2"; then
    ok "$3"
  else
    ko "$3 (pattern not found: $1)"
  fi
}

reset_book() {
  rm -rf "$BOOK"
  mkdir -p "$BOOK"
}

add() {
  node "$SQ" --dir "$BOOK" add "$1" > /dev/null
}

echo "State Store Tests"
echo "==================================="

# --- 1. add 分片路由：第 12 章进 001-050 片，第 51 章进 051-100 片 ---
reset_book
add '{"ch":12,"type":"状态","entity":"林岚","field":"位置","value":"营业厅"}'
add '{"ch":51,"type":"状态","entity":"林岚","field":"位置","value":"北城"}'
[ -f "$STORE/事件_第001-050章.jsonl" ] && ok "第 12 章事件进 001-050 分片" || ko "001-050 分片未创建"
[ -f "$STORE/事件_第051-100章.jsonl" ] && ok "第 51 章事件进 051-100 分片" || ko "051-100 分片未创建"

# --- 2. add 校验：缺必填字段 / 非法 type 拒绝 ---
expect_exit 2 "缺 value 的状态事件被拒绝" node "$SQ" --dir "$BOOK" add '{"ch":1,"type":"状态","entity":"林岚","field":"位置"}'
expect_exit 2 "非法 type 被拒绝" node "$SQ" --dir "$BOOK" add '{"ch":1,"type":"心情","entity":"林岚"}'

# --- 3. 时点快照折叠：同字段后值覆盖前值，但历史时点看历史值 ---
reset_book
add '{"ch":5,"type":"状态","entity":"林岚","field":"位置","value":"老宅"}'
add '{"ch":20,"type":"状态","entity":"林岚","field":"位置","value":"营业厅"}'
node "$SQ" --dir "$BOOK" snapshot 10 > "$TMP_DIR/snap10.md"
expect_grep "位置：老宅" "$TMP_DIR/snap10.md" "第 10 章快照看到历史值"
node "$SQ" --dir "$BOOK" snapshot 25 > "$TMP_DIR/snap25.md"
expect_grep "位置：营业厅" "$TMP_DIR/snap25.md" "第 25 章快照看到覆盖后的值"

# --- 4. 认知折叠 + --entity 过滤 ---
add '{"ch":8,"type":"认知","entity":"林岚","learns":"账单被人动过"}'
node "$SQ" --dir "$BOOK" snapshot 10 --entity 林岚 > "$TMP_DIR/snap-e.md"
expect_grep "账单被人动过" "$TMP_DIR/snap-e.md" "快照含已获知信息"

# --- 5. 跨分片折叠 ---
add '{"ch":60,"type":"状态","entity":"林岚","field":"位置","value":"南岭"}'
node "$SQ" --dir "$BOOK" snapshot 60 > "$TMP_DIR/snap60.md"
expect_grep "位置：南岭" "$TMP_DIR/snap60.md" "跨分片快照折叠正确"

# --- 6. 伏笔：活跃 / 回收后不再活跃 / 超期标记 ---
reset_book
add '{"ch":3,"type":"伏笔","op":"埋设","id":"F001","desc":"陌生号码警告","due":30}'
add '{"ch":4,"type":"伏笔","op":"埋设","id":"F002","desc":"旧照片","due":10}'
add '{"ch":9,"type":"伏笔","op":"回收","id":"F002"}'
node "$SQ" --dir "$BOOK" foreshadow 15 > "$TMP_DIR/fs15.md"
expect_grep "F001" "$TMP_DIR/fs15.md" "活跃伏笔在列"
if grep -q "F002" "$TMP_DIR/fs15.md"; then ko "已回收伏笔不应在活跃列表"; else ok "已回收伏笔不在活跃列表"; fi
node "$SQ" --dir "$BOOK" foreshadow 35 > "$TMP_DIR/fs35.md"
expect_grep "已超期" "$TMP_DIR/fs35.md" "超过预计回收章标记超期"

# --- 7. check：健康库 PASS ---
expect_exit 0 "健康库 check PASS" node "$SQ" --dir "$BOOK" check

# --- 8. 死亡后活动 → Dead_Entity_Active ---
reset_book
add '{"ch":30,"type":"状态","entity":"陈叔","field":"存活","value":"死亡"}'
add '{"ch":45,"type":"认知","entity":"陈叔","learns":"林岚在查他"}'
expect_exit 1 "死亡后活动 → FAIL" node "$SQ" --dir "$BOOK" check
node "$SQ" --dir "$BOOK" --json check > "$TMP_DIR/dead.json" || true
expect_grep "Dead_Entity_Active" "$TMP_DIR/dead.json" "错误码为 Dead_Entity_Active"

# --- 9. 复活解除死亡矛盾 ---
add '{"ch":40,"type":"状态","entity":"陈叔","field":"存活","value":"复活"}'
expect_exit 0 "复活事件解除死亡矛盾" node "$SQ" --dir "$BOOK" check

# --- 10. 未埋先收 → Foreshadow_Not_Planted ---
reset_book
add '{"ch":10,"type":"伏笔","op":"回收","id":"F009"}'
node "$SQ" --dir "$BOOK" --json check > "$TMP_DIR/np.json" || true
expect_grep "Foreshadow_Not_Planted" "$TMP_DIR/np.json" "未埋先收 → Foreshadow_Not_Planted"

# --- 11. 重复回收 → Foreshadow_After_Close ---
reset_book
add '{"ch":3,"type":"伏笔","op":"埋设","id":"F001","desc":"警告"}'
add '{"ch":9,"type":"伏笔","op":"回收","id":"F001"}'
add '{"ch":12,"type":"伏笔","op":"回收","id":"F001"}'
node "$SQ" --dir "$BOOK" --json check > "$TMP_DIR/dc.json" || true
expect_grep "Foreshadow_After_Close" "$TMP_DIR/dc.json" "重复回收 → Foreshadow_After_Close"

# --- 12. 分片错位 → Shard_Mismatch；坏行 → JSON_Invalid ---
reset_book
mkdir -p "$STORE"
printf '{"ch":80,"type":"状态","entity":"林岚","field":"位置","value":"北城"}\nnot json at all\n' > "$STORE/事件_第001-050章.jsonl"
node "$SQ" --dir "$BOOK" --json check > "$TMP_DIR/shard.json" || true
expect_grep "Shard_Mismatch" "$TMP_DIR/shard.json" "放错分片 → Shard_Mismatch"
expect_grep "JSON_Invalid" "$TMP_DIR/shard.json" "坏行 → JSON_Invalid"

# --- 13. 重复认知只警告不阻塞 ---
reset_book
add '{"ch":5,"type":"认知","entity":"林岚","learns":"账单被人动过"}'
add '{"ch":9,"type":"认知","entity":"林岚","learns":"账单被人动过"}'
expect_exit 0 "重复认知仅 warning，check 仍 PASS" node "$SQ" --dir "$BOOK" check
node "$SQ" --dir "$BOOK" --json check > "$TMP_DIR/kd.json"
expect_grep "Knowledge_Duplicate" "$TMP_DIR/kd.json" "警告码为 Knowledge_Duplicate"

# --- 14. --json 输出可解析 ---
node "$SQ" --dir "$BOOK" --json snapshot 10 > "$TMP_DIR/parse.json"
if node -e "JSON.parse(require('fs').readFileSync(process.argv[1], 'utf8'))" "$TMP_DIR/parse.json"; then
  ok "--json 输出为合法 JSON"
else
  ko "--json 输出不是合法 JSON"
fi

echo
echo "==================================="
echo "passed: $pass_count, failed: $fail_count"
if [ "$fail_count" -gt 0 ]; then
  exit 1
fi
echo "All state store tests passed."
