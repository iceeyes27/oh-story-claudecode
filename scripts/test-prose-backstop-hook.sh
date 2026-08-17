#!/bin/bash
# test-prose-backstop-hook.sh — regression tests for check-prose-after-write.sh
# 核心保证：① 绝不过度捕获非正文文件（代码/细纲/设定/大纲/游离正文）；② 真正文兜底触发；
# ③ 轻量内容网抓对硬信号（截断/拒绝语/工程词/复读），干净正文（排比+对话+悬念）静默。
# 过度捕获用路径门验证（不依赖解释器）；内容网用内嵌 python（与 parity 测试同源）。
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
[ -z "$REPO_ROOT" ] && { echo "Error: not in a git repository" >&2; exit 1; }
HOOK="$REPO_ROOT/skills/story-setup/references/templates/hooks/check-prose-after-write.sh"
[ -f "$HOOK" ] || { echo "FAIL: hook not found: $HOOK" >&2; exit 1; }

bash -n "$HOOK" || { echo "FAIL: hook has syntax errors" >&2; exit 1; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
# 真书结构：设定.md + 大纲/ + 正文/
mkdir -p "$TMP/某书/正文" "$TMP/某书/大纲" "$TMP/docs/正文" "$TMP/游离/正文"
printf '# 设定\n主角江晨。\n' > "$TMP/某书/设定.md"
printf '## 细纲（第1章）\n- 情节点序列：本章细纲，作为AI我无法继续。他握紧拳头。他握紧拳头。\n' > "$TMP/某书/大纲/细纲_第001章.md"
printf '# 大纲\n第1章 第2章 细纲 本章 下一章\n' > "$TMP/某书/大纲/大纲.md"
printf '# 卷纲\n本卷细纲。\n' > "$TMP/某书/大纲/卷纲_第1卷.md"
printf 'const x=1; // 细纲 本章 下一章 作为AI我无法继续 复读复读复读\n' > "$TMP/某书/x.js"
printf '## 正文\n按照细纲，作为AI我无法继续。\n' > "$TMP/docs/正文.md"   # 正文.md 但无 设定.md 兄弟
printf '## 第5章\n按照细纲，作为AI我无法继续。\n' > "$TMP/游离/正文/第005章.md" # 正文/第N章 但无书结构
printf '他' > "$TMP/某书/正文/第001章_截断.md"                            # 真正文，极短 → 落盘触发

run() { CLAUDE_PROJECT_DIR="$TMP" CLAUDE_TOOL_INPUT="{\"tool_input\":{\"file_path\":\"$1\"}}" bash "$HOOK" 2>/dev/null; }

fails=0
expect_silent() {
  local out; out="$(run "$1")"
  if [ -n "$out" ]; then echo "FAIL: over-capture on non-正文 file: $1" >&2; echo "$out" | head -2 >&2; fails=$((fails+1)); fi
}
expect_fire() {
  local out; out="$(run "$1")"
  if [ -z "$out" ]; then echo "FAIL: backstop did not fire on real 正文: $1" >&2; fails=$((fails+1)); fi
}

# ① 绝不捕获这些非正文文件（含工程词/复读/拒绝语文本，证明确实没被扫）
expect_silent "$TMP/某书/大纲/细纲_第001章.md"
expect_silent "$TMP/某书/大纲/大纲.md"
expect_silent "$TMP/某书/大纲/卷纲_第1卷.md"
expect_silent "$TMP/某书/x.js"
expect_silent "$TMP/某书/设定.md"
expect_silent "$TMP/docs/正文.md"
expect_silent "$TMP/游离/正文/第005章.md"
# ② 真正文（极短→落盘信号）必须触发
expect_fire "$TMP/某书/正文/第001章_截断.md"

# ③ 内容网：真正文里的硬信号必须被抓，且抓对类型；干净正文（排比+AI角色对话+悬念收尾）静默。
expect_fire_kw() {
  local out; out="$(run "$1")"
  if ! printf '%s' "$out" | grep -q "$2"; then
    echo "FAIL: 内容网未抓到「$2」: $1" >&2; printf '%s\n' "$out" | head -4 >&2; fails=$((fails+1))
  fi
}
# bash 字符串重复填充正文（不走 python stdout：Windows runner 上 python<3.15 的文本 stdout
# 是 cp1252，写中文会 UnicodeEncodeError；printf 直出脚本里的 UTF-8 字节字面量才稳）。
PAD() { local s='江晨握紧拳头慢慢走向门口心里盘算着接下来的每一步棋。'; printf '%s' "$s$s$s$s$s$s$s$s"; }
# 干净：长正文 + 排比 + AI 角色对话（「作为AI…」在引号内豁免）+ 悬念收尾标点 → 完全静默
{ printf '# 第10章 决战\n\n'; PAD; printf '\n要么生，要么死。\n要么战，要么逃。\n「作为AI管家，我陪你到最后。」\n他终于停下了脚步。\n'; } > "$TMP/某书/正文/第010章_决战.md"
expect_silent "$TMP/某书/正文/第010章_决战.md"
# 截断：结尾无标点
{ printf '# 第11章\n\n'; PAD; printf '\n他猛地冲过去一拳砸在'; } > "$TMP/某书/正文/第011章_截断.md"
expect_fire_kw "$TMP/某书/正文/第011章_截断.md" 截断
# 生成拒绝语 / AI 自指（叙述行，非对话）
{ printf '# 第12章\n\n'; PAD; printf '\n作为AI我无法继续创作这部分内容。\n'; } > "$TMP/某书/正文/第012章_拒绝.md"
expect_fire_kw "$TMP/某书/正文/第012章_拒绝.md" 元信息泄漏
# 工程词漏进正文
{ printf '# 第13章\n\n'; PAD; printf '\n按照本章细纲的情节点，他该出场了。\n他出场了。\n'; } > "$TMP/某书/正文/第013章_工程词.md"
expect_fire_kw "$TMP/某书/正文/第013章_工程词.md" 工程词
# 紧邻整行复读（≥8 可见字符）
{ printf '# 第14章\n\n'; PAD; printf '\n他握紧拳头一步步走过去缓缓逼近。\n他握紧拳头一步步走过去缓缓逼近。\n他停下了。\n'; } > "$TMP/某书/正文/第014章_复读.md"
expect_fire_kw "$TMP/某书/正文/第014章_复读.md" 复读

# ④ Bash 成功/失败事件都必须输出合法 additionalContext；失败命令可能已部分写入，
# 写后检查只能报告、不能宣称撤销。这里直接模拟宿主在命令执行后发出的事件。
run_payload() {
  printf '%s' "$1" | CLAUDE_PROJECT_DIR="$TMP" bash "$HOOK" 2>/dev/null
}
assert_hook_json() {
  local out="$1" expected="$2"
  HOOK_JSON="$out" EXPECTED_EVENT="$expected" node - <<'NODE' || return 1
const obj = JSON.parse(process.env.HOOK_JSON)
const hook = obj && obj.hookSpecificOutput
if (!hook || hook.hookEventName !== process.env.EXPECTED_EVENT || typeof hook.additionalContext !== "string" || !hook.additionalContext) process.exit(1)
NODE
}

success_payload="{\"hook_event_name\":\"PostToolUse\",\"tool_name\":\"Bash\",\"tool_input\":{\"command\":\"printf x > $TMP/某书/正文/第012章_拒绝.md\"}}"
success_out="$(run_payload "$success_payload")"
assert_hook_json "$success_out" PostToolUse || { echo "FAIL: post-Bash success output is not valid hook JSON" >&2; fails=$((fails+1)); }
printf '%s' "$success_out" | grep -q '元信息泄漏' || { echo "FAIL: post-Bash success missed prose findings" >&2; fails=$((fails+1)); }

failure_payload="{\"hook_event_name\":\"PostToolUseFailure\",\"tool_name\":\"Bash\",\"tool_input\":{\"command\":\"printf x > $TMP/某书/正文/第013章_工程词.md; false\"},\"error\":\"exit 1\"}"
failure_out="$(run_payload "$failure_payload")"
assert_hook_json "$failure_out" PostToolUseFailure || { echo "FAIL: post-Bash failure output is not valid hook JSON" >&2; fails=$((fails+1)); }
printf '%s' "$failure_out" | grep -q '命令失败但文件可能已改变' || { echo "FAIL: post-Bash failure missed partial-write warning" >&2; fails=$((fails+1)); }
printf '%s' "$failure_out" | grep -q '工程词' || { echo "FAIL: post-Bash failure missed prose findings" >&2; fails=$((fails+1)); }

# ⑤ Write/Edit/MultiEdit 的路径字段也必须走同一事件适配器。
for tool in Write Edit MultiEdit; do
  case "$tool" in
    MultiEdit) tool_input="{\"edits\":[{\"file_path\":\"$TMP/某书/正文/第011章_截断.md\"}]}" ;;
    *) tool_input="{\"file_path\":\"$TMP/某书/正文/第011章_截断.md\"}" ;;
  esac
  event_payload="{\"hook_event_name\":\"PostToolUse\",\"tool_name\":\"$tool\",\"tool_input\":$tool_input}"
  event_out="$(run_payload "$event_payload")"
  assert_hook_json "$event_out" PostToolUse || { echo "FAIL: post-$tool output is not valid hook JSON" >&2; fails=$((fails+1)); }
  printf '%s' "$event_out" | grep -q '截断' || { echo "FAIL: post-$tool missed prose findings" >&2; fails=$((fails+1)); }
done

if [ "$fails" -ne 0 ]; then
  echo "Prose backstop hook tests FAILED ($fails)." >&2
  exit 1
fi
echo "Prose backstop hook regression tests passed."
