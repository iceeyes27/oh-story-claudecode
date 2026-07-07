#!/bin/bash
# test-longform-stability.sh — regression tests for the longform stability toolchain
# (stability-audit.js + handoff-pack.js): 契约 beat 关键词、禁词、漂移门控、
# 角色不变量 POV 感知扫描、Gate PASS 才交接、跨章继承关键词。
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
if [ -z "$REPO_ROOT" ]; then
  echo "Error: not in a git repository" >&2
  exit 1
fi

AUDIT="$REPO_ROOT/skills/story-long-write/scripts/stability-audit.js"
PACK="$REPO_ROOT/skills/story-long-write/scripts/handoff-pack.js"
ARCHIVE="$REPO_ROOT/skills/story-long-write/scripts/archive-stability.js"
TMP_DIR="$(mktemp -d)"
cleanup() { rm -rf "$TMP_DIR"; }
trap cleanup EXIT

BOOK="$TMP_DIR/book"
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

build_fixture() {
  rm -rf "$BOOK"
  mkdir -p "$BOOK/正文" "$BOOK/大纲" "$BOOK/追踪/漂移门控" "$BOOK/设定/角色不变量"

  cat > "$BOOK/大纲/细纲_第001章.md" <<'EOF'
## 细纲（第 1 章）

#### 结尾设定和钩子
- 结尾设定：林岚攥着账单站在门口
- 章尾钩子：陌生号码发来一句警告

#### 稳定性契约

##### 必须交付
| 序号 | 情节点 | 功能 | 关键词组 |
|---|---|---|---|
| B1 | 林岚发现账单异常 | 冲突 | 账单、4800 |
| B2 | 陌生短信警告 | 伏笔 | 别查了 |

##### 禁止事项
- 不得提前透露：陈叔是幕后人
EOF

  cat > "$BOOK/正文/第001章_账单风波.md" <<'EOF'
# 第001章 账单风波

林岚翻开账单，4800元的转出记录刺进眼里。手机亮起，陌生号码只有三个字：别查了。

## POV：林岚

她不知道钱去了哪里。

## POV：沈岚

沈岚握着陈叔的转账记录，指尖发凉。
EOF

  cat > "$BOOK/追踪/漂移门控/第001章.md" <<'EOF'
## Plot Drift Gate：第 1 章

### 结论
- Gate: PASS

### Beat 核对
- B1：已交付 — 林岚翻开账单
- B2：已交付 — 陌生短信

### State Delta（本章改变了什么）
- 林岚：从不知情到发现账单异常

### 下一章继承关键词
- 继承关键词：账单、别查了
EOF

  cat > "$BOOK/设定/角色不变量/林岚.md" <<'EOF'
## 角色不变量：林岚

### 行为红线
- 不会：跪下求饶

### 认知边界
- 不能提前知道：陈叔的转账记录
EOF

  cat > "$BOOK/追踪/伏笔.md" <<'EOF'
# 伏笔追踪

## 伏笔状态表

| ID | 伏笔内容 | 埋设章节 | 预计回收章节 | 状态 | 重要度 |
|----|---------|---------|-------------|------|--------|
| F001 | 陌生号码警告 | 第001章 | 第005章 | 已埋 | 高 |
| F002 | 旧照片 | 第001章 | 第003章 | 已回收 | 中 |
EOF
}

add_chapter2() {
  cat > "$BOOK/大纲/细纲_第002章.md" <<'EOF'
#### 稳定性契约

##### 必须交付
| 序号 | 情节点 | 功能 | 关键词组 |
|---|---|---|---|
| B1 | 林岚追查号码归属 | 推进 | 号码、营业厅 |

##### 禁止事项
- 不得提前透露：陈叔是幕后人
EOF

  cat > "$BOOK/正文/第002章_追查.md" <<'EOF'
# 第002章 追查

账单还压在包底，那句别查了像根刺。林岚去营业厅查号码归属。
EOF

  cat > "$BOOK/追踪/漂移门控/第002章.md" <<'EOF'
### 结论
- Gate: PASS

### Beat 核对
- B1：已交付

### State Delta（本章改变了什么）
- 林岚：拿到号码归属线索

### 下一章继承关键词
- 继承关键词：营业厅
EOF
}

echo "Longform Stability Toolchain Tests"
echo "==================================="

# --- 1. 健康单章：全 PASS ---
build_fixture
expect_exit 0 "单章全 PASS" node "$AUDIT" --dir "$BOOK" 1 1

# --- 2. POV 隔离：禁知词只在他人 POV 出现，不判泄漏（fixture 1 已含此场景，由测试 1 隐式覆盖）
#        把禁知词放进角色本人 POV → Knowledge_Leak ---
printf '\n## POV：林岚\n\n林岚盯着陈叔的转账记录发呆。\n' >> "$BOOK/正文/第001章_账单风波.md"
expect_exit 1 "本人 POV 出现禁知词 → FAIL" node "$AUDIT" --dir "$BOOK" 1 1
node "$AUDIT" --dir "$BOOK" --json 1 1 > "$TMP_DIR/leak.json" 2>/dev/null || true
expect_grep "Knowledge_Leak" "$TMP_DIR/leak.json" "泄漏错误码为 Knowledge_Leak"

# --- 3. 行为红线命中 → Motivation_Drift ---
build_fixture
printf '\n## POV：林岚\n\n她几乎要跪下求饶。\n' >> "$BOOK/正文/第001章_账单风波.md"
node "$AUDIT" --dir "$BOOK" --json 1 1 > "$TMP_DIR/redline.json" 2>/dev/null || true
expect_grep "Motivation_Drift" "$TMP_DIR/redline.json" "红线错误码为 Motivation_Drift"

# --- 4. beat 关键词缺失 → Beat_Missing ---
build_fixture
node - "$BOOK/正文/第001章_账单风波.md" <<'EOF'
const fs = require('fs');
const f = process.argv[2];
fs.writeFileSync(f, fs.readFileSync(f, 'utf8').replace(/别查了/g, '别问了'), 'utf8');
EOF
node "$AUDIT" --dir "$BOOK" --json 1 1 > "$TMP_DIR/beat.json" 2>/dev/null || true
expect_grep "Beat_Missing" "$TMP_DIR/beat.json" "beat 关键词缺失 → Beat_Missing"

# --- 5. 禁词提前出现 → Foreshadow_Early_Payoff ---
build_fixture
printf '\n有人低声说：陈叔是幕后人。\n' >> "$BOOK/正文/第001章_账单风波.md"
node "$AUDIT" --dir "$BOOK" --json 1 1 > "$TMP_DIR/forbid.json" 2>/dev/null || true
expect_grep "Foreshadow_Early_Payoff" "$TMP_DIR/forbid.json" "禁词提前出现 → Foreshadow_Early_Payoff"

# --- 6. 细纲缺稳定性契约 → Contract_Missing ---
build_fixture
printf '## 细纲（第 1 章）\n- 核心事件：账单风波\n' > "$BOOK/大纲/细纲_第001章.md"
node "$AUDIT" --dir "$BOOK" --json 1 1 > "$TMP_DIR/contract.json" 2>/dev/null || true
expect_grep "Contract_Missing" "$TMP_DIR/contract.json" "缺契约 → Contract_Missing"

# --- 7. 门控缺失 / 门控 FAIL ---
build_fixture
rm "$BOOK/追踪/漂移门控/第001章.md"
node "$AUDIT" --dir "$BOOK" --json 1 1 > "$TMP_DIR/gate.json" 2>/dev/null || true
expect_grep "Gate_Missing" "$TMP_DIR/gate.json" "门控缺失 → Gate_Missing"

# --- 8. 交接包：Gate PASS 才生成 + 内容完整 ---
build_fixture
expect_exit 0 "门控 PASS 时交接包生成成功" node "$PACK" --dir "$BOOK" --write 1
PACK_FILE="$BOOK/追踪/交接包/第001章_to_第002章.md"
[ -f "$PACK_FILE" ] && ok "交接包已落盘" || ko "交接包未落盘"
expect_grep "继承关键词：账单、别查了" "$PACK_FILE" "交接包含继承关键词"
expect_grep "F001" "$PACK_FILE" "交接包含活跃伏笔（已埋）"
if grep -q "F002" "$PACK_FILE"; then ko "已回收伏笔不应进交接包"; else ok "已回收伏笔未进交接包"; fi
expect_grep "设定/角色不变量/林岚.md" "$PACK_FILE" "交接包含出场角色不变量指引"

# --- 9. 门控 FAIL 时交接包拒绝生成 ---
node - "$BOOK/追踪/漂移门控/第001章.md" <<'EOF'
const fs = require('fs');
const f = process.argv[2];
fs.writeFileSync(f, fs.readFileSync(f, 'utf8').replace('Gate: PASS', 'Gate: FAIL'), 'utf8');
EOF
expect_exit 1 "门控 FAIL → 交接包拒绝生成" node "$PACK" --dir "$BOOK" --write 1

# --- 10. 批量审计：跨章继承 PASS + 报告落盘 ---
build_fixture
node "$PACK" --dir "$BOOK" --write 1 > /dev/null
add_chapter2
expect_exit 0 "批量审计（含跨章继承）PASS" node "$AUDIT" --dir "$BOOK" --write 1 2
REPORT="$BOOK/追踪/稳定性审计/日更_第001章_to_第002章.md"
[ -f "$REPORT" ] && ok "审计报告已落盘" || ko "审计报告未落盘"
expect_grep "Audit: PASS" "$REPORT" "报告结论 PASS"

# --- 11. 继承关键词未在下一章出现 → Continuity_Missing ---
printf '# 第002章 追查\n\n林岚去营业厅查号码归属。\n' > "$BOOK/正文/第002章_追查.md"
node "$AUDIT" --dir "$BOOK" --json 1 2 > "$TMP_DIR/cont.json" 2>/dev/null || true
expect_grep "Continuity_Missing" "$TMP_DIR/cont.json" "继承断裂 → Continuity_Missing"

# --- 12. 交接包缺失 → Handoff_Missing ---
rm "$BOOK/追踪/交接包/第001章_to_第002章.md"
node "$AUDIT" --dir "$BOOK" --json 1 2 > "$TMP_DIR/handoff.json" 2>/dev/null || true
expect_grep "Handoff_Missing" "$TMP_DIR/handoff.json" "交接包缺失 → Handoff_Missing"

# --- 13. JSON 输出可解析 ---
build_fixture
node "$AUDIT" --dir "$BOOK" --json 1 1 > "$TMP_DIR/parse.json"
if node -e "JSON.parse(require('fs').readFileSync(process.argv[1], 'utf8'))" "$TMP_DIR/parse.json"; then
  ok "--json 输出为合法 JSON"
else
  ko "--json 输出不是合法 JSON"
fi

# --- 14. 归档：dry-run 不移动 / 窗口外移动 / 验收透明回退 ---
build_fixture
node "$PACK" --dir "$BOOK" --write 1 > /dev/null
add_chapter2
node "$PACK" --dir "$BOOK" --write 2 > /dev/null
node "$AUDIT" --dir "$BOOK" --write 1 2 > /dev/null
# 造第 3-12 章正文/门控占位，把最新章号推到 12
for i in $(seq 3 12); do
  id="$(printf '%03d' "$i")"
  printf '# 第%s章 占位\n\n正文。\n' "$id" > "$BOOK/正文/第${id}章_占位.md"
  printf '### 结论\n- Gate: PASS\n\n### State Delta\n- 无\n\n### 下一章继承关键词\n- 继承关键词：占位\n' > "$BOOK/追踪/漂移门控/第${id}章.md"
done
node "$ARCHIVE" --dir "$BOOK" --keep 3 --dry-run > /dev/null
[ -f "$BOOK/追踪/漂移门控/第001章.md" ] && ok "dry-run 不移动文件" || ko "dry-run 移动了文件"
# 实际归档：latest=12，keep=3 → 活跃窗口从第 10 章起
node "$ARCHIVE" --dir "$BOOK" --keep 3 > "$TMP_DIR/archive.out"
if [ -f "$BOOK/追踪/归档/漂移门控/第001章.md" ] && [ ! -f "$BOOK/追踪/漂移门控/第001章.md" ]; then
  ok "窗口外门控已归档"
else
  ko "窗口外门控未归档"
fi
[ -f "$BOOK/追踪/漂移门控/第012章.md" ] && ok "窗口内门控保持活跃" || ko "窗口内门控被误归档"
[ -f "$BOOK/追踪/归档/交接包/第001章_to_第002章.md" ] && ok "窗口外交接包已归档" || ko "窗口外交接包未归档"
[ -f "$BOOK/追踪/归档/稳定性审计/日更_第001章_to_第002章.md" ] && ok "窗口外审计报告已归档" || ko "窗口外审计报告未归档"
# 归档后验收老章节：门控/交接包全在归档，透明回退应 PASS
expect_exit 0 "归档后审计透明回退 PASS" node "$AUDIT" --dir "$BOOK" 1 2
expect_exit 0 "归档门控可供 handoff-pack 回退读取" node "$PACK" --dir "$BOOK" 1

echo
echo "==================================="
echo "passed: $pass_count, failed: $fail_count"
if [ "$fail_count" -gt 0 ]; then
  exit 1
fi
echo "All longform stability tests passed."
