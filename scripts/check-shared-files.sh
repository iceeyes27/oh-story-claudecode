#!/bin/bash
# check-shared-files.sh — 检查跨 skill 同名文件内容一致性
# 扫描所有 skill 的 references/ 与 scripts/ 目录，找出同名文件并比较内容
# 兼容 bash 3+（macOS）
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

SKILLS_DIR="$REPO_ROOT/skills"
if [ ! -d "$SKILLS_DIR" ]; then
  echo "Error: skills/ not found at $SKILLS_DIR"
  exit 1
fi

GIT_BIN="git"
GIT_REPO_ROOT="$REPO_ROOT"
if command -v wslpath >/dev/null 2>&1 && command -v git.exe >/dev/null 2>&1; then
  GIT_BIN="git.exe"
  GIT_REPO_ROOT="$(wslpath -w "$REPO_ROOT")"
fi

# Known intentional differences (basename): these files are expected to differ
# - output-templates.md: each skill owns output schemas
# - material-decomposition.md: long/short analyze use different decomposition pipelines
# - quality-checklist.md: per-skill copies are intentionally skill-specific (analyze's
#   copy points to material-decomposition.md; write's covers long+short sections)
# - 5 genre files: story-analyze prepends a "## 用作拆文标尺时" analyst-lens
#   header (consumed as a reference standard for source-story evaluation, not a writer
#   playbook). Writer skills don't get the header. Wholesale-ignored here because their
#   non-analyst copies have not all been confirmed byte-identical.
#   genre-writing-formulas.md graduated to ANALYST_DIVERGENT_NAMES: its writer copies
#   are byte-identical and now guarded.
# - AGENTS.md.tmpl / hooks.json: CLI-specific project templates differ deliberately
#   and are validated by each CLI adapter check.
IGNORE_NAMES="output-templates.md material-decomposition.md quality-checklist.md \
genre-catalog.md genre-core-mechanics.md genre-readers.md \
genre-writing-techniques.md \
hooks-suspense.md \
AGENTS.md.tmpl hooks.json agent.md"

# Analyst-divergent (basename): the story-analyze copy intentionally prepends the
# "## 用作拆文标尺时" analyst-lens header, so it is dropped from the comparison set; all
# OTHER copies (writer skills + agent-references) must still stay byte-identical. Stricter
# than a wholesale ignore — it still guards writer↔writer drift.
ANALYST_DIVERGENT_NAMES="character-basics.md character-design-methods.md character-relations.md genre-writing-formulas.md"

# Genre-style-divergent (basename): the story-write copy under references/genre-styles/
# is a short-form writer style pack, a different artifact from the long-form
# references/genre-prose-cards/ card of the same basename (story-write + its story-setup
# deployment mirror). Drop the genre-styles copy from the comparison; the prose-card copies
# must still stay byte-identical. Stricter than a wholesale ignore.
GENRE_STYLE_DIVERGENT_NAMES="双男主.md"

# Longform-divergent (basename): story-write's copy carries a long-form-only
# section (长篇循环情绪引擎) that references reader-contract-and-progression.md, which
# exists only under story-write; syncing it to the agent-references copy would
# create a dangling reference. Drop the story-write copy from the comparison;
# the agent-references copies must still stay byte-identical.
LONGFORM_DIVERGENT_NAMES="emotional-methods.md"

mismatches=0
checked=0

echo "Shared File Consistency Check"
echo "=============================="

# Only inspect repository content plus non-ignored additions. Runtime state such
# as **/.omc/ may live below references/ on a developer machine, but it is not a
# skill asset and must not make this guard disagree with a clean CI checkout.
list_asset_files() {
  local asset_dir="$1"
  "$GIT_BIN" -C "$GIT_REPO_ROOT" ls-files -z --cached --others --exclude-standard -- skills |
    while IFS= read -r -d '' rel_path; do
      [ -f "$REPO_ROOT/$rel_path" ] || continue
      case "$rel_path" in
        skills/*/"$asset_dir"/*) printf '%s\n' "$REPO_ROOT/$rel_path" ;;
      esac
    done
}

REFERENCE_FILES="$(list_asset_files references)"
PYTHON_BIN=""
for candidate in python3 python py; do
  if "$candidate" -c "" >/dev/null 2>&1; then
    PYTHON_BIN="$candidate"
    break
  fi
done
if [ -z "$PYTHON_BIN" ]; then
  echo "FAIL: Python 3 is required (tried python3, python, and py)" >&2
  exit 1
fi
"$PYTHON_BIN" "$REPO_ROOT/scripts/sync-shared-assets.py" check

list_reference_basenames() {
  local path
  while IFS= read -r path; do
    case "$path" in
      */.gitkeep|*/opencode/*) ;;
      *) printf '%s\n' "${path##*/}" ;;
    esac
  done <<< "$REFERENCE_FILES"
}

# Find all reference basenames that appear in 2+ skills
dup_names="$(list_reference_basenames | sort | uniq -d)"

for base in $dup_names; do
  # Skip known intentional differences
  skip=false
  for ignore in $IGNORE_NAMES; do
    if [ "$base" = "$ignore" ]; then
      skip=true
      break
    fi
  done
  if [ "$skip" = true ]; then
    continue
  fi
  # Collect all paths for this basename
  paths=()
  while IFS= read -r fpath; do
    [ -z "$fpath" ] && continue
    [ "${fpath##*/}" = "$base" ] && paths+=("$fpath")
  done <<< "$REFERENCE_FILES"

  # trellis-meta has three intentionally distinct, nested overview documents
  # (customization, local architecture, and platform files).  They share a
  # basename but are not mirrored assets.  Restrict the exception to that one
  # Skill so unrelated overview.md copies remain guarded.
  if [ "$base" = "overview.md" ]; then
    trellis_only=true
    for p in ${paths[@]+"${paths[@]}"}; do
      case "$p" in
        */skills/trellis-meta/*) ;;
        *) trellis_only=false; break ;;
      esac
    done
    if [ "$trellis_only" = true ]; then
      continue
    fi
  fi

  # Analyst-divergent basenames: drop the story-analyze copy (intentional
  # analyst-lens fork); the remaining copies must still be byte-identical.
  case " $ANALYST_DIVERGENT_NAMES " in
    *" $base "*)
      filtered=()
      for p in ${paths[@]+"${paths[@]}"}; do
        case "$p" in
          */story-analyze/*) ;;
          *) filtered+=("$p") ;;
        esac
      done
      paths=(${filtered[@]+"${filtered[@]}"})
      ;;
  esac

  # Genre-style-divergent basenames: drop the short-form references/genre-styles/ copy
  # (a different artifact from the long-form genre-prose-cards/ card); the remaining
  # prose-card copies must still be byte-identical.
  case " $GENRE_STYLE_DIVERGENT_NAMES " in
    *" $base "*)
      filtered=()
      for p in ${paths[@]+"${paths[@]}"}; do
        case "$p" in
          */genre-styles/*) ;;
          *) filtered+=("$p") ;;
        esac
      done
      paths=(${filtered[@]+"${filtered[@]}"})
      ;;
  esac

  # Longform-divergent basenames: drop the story-write copy (intentional
  # long-form-only fork); the remaining copies must still be byte-identical.
  case " $LONGFORM_DIVERGENT_NAMES " in
    *" $base "*)
      filtered=()
      for p in ${paths[@]+"${paths[@]}"}; do
        case "$p" in
          */story-write/*) ;;
          *) filtered+=("$p") ;;
        esac
      done
      paths=(${filtered[@]+"${filtered[@]}"})
      ;;
  esac

  if [ ${#paths[@]} -lt 2 ]; then
    continue
  fi

  checked=$((checked + 1))
  ref_path="${paths[0]}"
  ref_skill="$(echo "$ref_path" | sed "s|$SKILLS_DIR/||" | cut -d'/' -f1)"
  all_match=true

  for ((i = 1; i < ${#paths[@]}; i++)); do
    if ! diff -q "$ref_path" "${paths[$i]}" >/dev/null 2>&1; then
      skill_name="$(echo "${paths[$i]}" | sed "s|$SKILLS_DIR/||" | cut -d'/' -f1)"
      if [ "$all_match" = true ]; then
        echo ""
        echo "MISMATCH: $base"
        echo "  Reference: $ref_skill"
      fi
      echo "  Differs in: $skill_name"
      all_match=false
      mismatches=$((mismatches + 1))
    fi
  done
done

echo ""
echo "=============================="
echo "Reference groups checked: $checked | Mismatches: $mismatches"

if [ "$mismatches" -gt 0 ]; then
  echo ""
  echo "NOTE: Some mismatches may be intentional (skill-specific customizations)."
  echo "      Review each case before syncing."
  exit 1
fi

echo "All shared files are consistent."
