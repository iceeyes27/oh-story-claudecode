#!/usr/bin/env bash
# Regression test for the Reasonix AGENTS route-name contract.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/ohstory-reasonix-check.XXXXXX")"
trap 'rm -rf "$TMP_DIR"' EXIT

cp -R "$REPO_ROOT/scripts" "$TMP_DIR/scripts"
cp -R "$REPO_ROOT/skills" "$TMP_DIR/skills"
cp "$REPO_ROOT/reasonix-plugin.json" "$TMP_DIR/reasonix-plugin.json"

bash "$TMP_DIR/scripts/check-reasonix-adapter.sh" >/dev/null

sed -i 's/公开清单中的 oh-story Skill/固定数量的 oh-story Skill/' \
  "$TMP_DIR/skills/story-setup/references/reasonix/AGENTS.md.tmpl"

if bash "$TMP_DIR/scripts/check-reasonix-adapter.sh" >"$TMP_DIR/catalog-output.txt" 2>&1; then
  echo "FAIL: fixed-count Reasonix catalog wording was accepted" >&2
  exit 1
fi

grep -q 'catalog-driven public Skill set' "$TMP_DIR/catalog-output.txt" \
  || { echo "FAIL: Reasonix catalog failure lacked an actionable message" >&2; exit 1; }

cp "$REPO_ROOT/skills/story-setup/references/reasonix/AGENTS.md.tmpl" \
  "$TMP_DIR/skills/story-setup/references/reasonix/AGENTS.md.tmpl"

sed -i 's/| story-write（mode=long） |/| story-long-write |/' \
  "$TMP_DIR/skills/story-setup/references/reasonix/AGENTS.md.tmpl"

if bash "$TMP_DIR/scripts/check-reasonix-adapter.sh" >"$TMP_DIR/output.txt" 2>&1; then
  echo "FAIL: stale Reasonix route name was accepted" >&2
  exit 1
fi

grep -q 'Reasonix route names must match platform skill set' "$TMP_DIR/output.txt" \
  || { echo "FAIL: stale route failure lacked an actionable message" >&2; exit 1; }

echo "PASS: Reasonix route-name contract rejects obsolete split Skill names"
