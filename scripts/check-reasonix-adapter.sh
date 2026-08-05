#!/usr/bin/env bash
# Deterministic checks for the Reasonix native plugin manifest (issue #204/#252).
# Reasonix (DeepSeek-Reasonix CLI) reads a root reasonix-plugin.json and scans project
# skill roots. This guard covers the global manifest; project-level `story-setup`
# deployment is skills-only (target_cli=reasonix, skills + AGENTS.md, no hooks/custom
# agents -> solo/direct fallback) and is guarded by check-story-setup-deployment.sh.
# Reasonix hooks and custom agents remain later phases. Live `reasonix doctor
# capabilities` needs the CLI and is not in CI.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

fail() { echo "FAIL: $*" >&2; exit 1; }

echo "Reasonix adapter check"
echo "======================"
echo "Repo: $REPO_ROOT"

[ -f reasonix-plugin.json ] || fail "reasonix-plugin.json missing"
python3 -m json.tool reasonix-plugin.json >/dev/null || fail "reasonix-plugin.json is not valid JSON"

python3 - <<'PY'
import json, re
from pathlib import Path

manifest = json.loads(Path('reasonix-plugin.json').read_text())
skill_set = json.loads(Path('scripts/platform-skill-set.json').read_text(encoding='utf-8'))
published = skill_set.get('skills', [])
assert published and len(published) == len(set(published)), 'platform skill set must contain unique skill names'
assert re.fullmatch(r'[a-z0-9][a-z0-9._-]{0,127}', manifest.get('name', '')), f"bad name: {manifest.get('name')!r}"
assert manifest['name'] == 'oh-story', manifest['name']
assert manifest['skills'] == 'skills', manifest.get('skills')
assert isinstance(manifest.get('description'), str) and manifest['description'], 'description required'
version = Path('skills/story/VERSION').read_text().strip()
assert manifest['version'] == version, f"version {manifest['version']!r} must match skills/story/VERSION {version!r}"
# The manifest promises the complete repository skill directory; keep it honest.
skills = sorted(Path('skills').glob('*/SKILL.md'))
assert skills, 'no skills found under manifest directory'
missing = sorted(name for name in published if not (Path('skills') / name / 'SKILL.md').is_file())
assert not missing, f'platform skill set references missing skills: {missing}'

setup = Path('skills/story-setup/SKILL.md').read_text(encoding='utf-8')
reasonix_section = setup.split('### Reasonix skills-only 部署算法', 1)[1].split('## 通用 Web AI', 1)[0]
assert 'scripts/platform-skill-set.json' in reasonix_section, 'Reasonix deployment must consume the public skill set'
assert 'skills/_shared/' in reasonix_section, 'Reasonix deployment must include the shared runtime assets'

agents = Path('skills/story-setup/references/reasonix/AGENTS.md.tmpl').read_text(encoding='utf-8')
assert f'{len(published)} 个公开 Skill' in agents, 'Reasonix template public Skill count drifted'
PY
echo "  OK reasonix-plugin.json (schema + version pin + public set + repository Skills)"
echo ""
echo "OK: Reasonix adapter checks passed"
