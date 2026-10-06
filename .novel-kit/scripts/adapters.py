"""Generate local Agent adapters from shared sources; refuse unreviewed overwrites."""
import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

from novel import atomic, inside, Invalid, locked, require

MANIFEST = '.novel-kit/adapters.json'
MATCHER = 'Write|Edit|MultiEdit|NotebookEdit|apply_patch'
SKILLS = ('new-book', 'import-book', 'plan-chapter', 'write-scene', 'revise', 'fiction-scene-polishing')
ROLES = ('scene-writer', 'copy-editor', 'consistency-checker', 'character-reviewer',
         'prose-reviewer', 'structure-reviewer', 'chapter-extractor', 'adjudicator')
# Claude-only model policy. 'quality' pins the writer, blind copy-editor and adjudicator to the strongest
# tier; 'inherit' leaves every role on the session model. Codex and generic always inherit.
MODEL_POLICIES = ('quality', 'inherit')
CLAUDE_MODELS = {'quality': {'strong': 'opus', 'standard': 'sonnet'}, 'inherit': {}}


def source_contract(root, agents):
    paths = ['AGENTS.md', 'novel.py', 'novel', 'novel.cmd',
             '.novel-kit/workflows/adoption.md', '.novel-kit/workflows/review-loop.md',
             '.novel-kit/workflows/progressive-disclosure.md',
             '.novel-kit/scripts/novel.py', '.novel-kit/scripts/prose_check.py', '.novel-kit/scripts/beats.py', '.novel-kit/scripts/py.sh', '.novel-kit/scripts/py.cmd',
             '.novel-kit/hooks/scene_gate.py', '.novel-kit/hooks/scene_gate.sh', '.novel-kit/hooks/scene_gate.cmd']
    paths += ['.agents/skills/'+name+'/SKILL.md' for name in SKILLS]
    paths += ['.novel-kit/roles/'+name+'.md' for name in ROLES]
    if 'claude' in agents:
        paths.append('CLAUDE.md')
    for name in paths:
        require(inside(root, name).is_file(), '共用來源缺失：'+name)


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8')


def read_json(path, default):
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default


def sha(data):
    return hashlib.sha256(data).hexdigest()


def metadata(path):
    text = path.read_text(encoding='utf-8')
    front, body = text.split('---', 2)[1:]
    values = dict(line.split(':', 1) for line in front.strip().splitlines())
    return {k: v.strip() for k, v in values.items()}, body.strip()


def hook_config(root, agent, platform):
    hook = root / '.novel-kit/hooks/scene_gate.sh'
    windows = str(root / '.novel-kit/hooks/scene_gate.cmd')
    # Encode only our fixed launcher expression, never a payload or user command.
    # This avoids nested cmd/PowerShell quoting for Unicode, spaces and apostrophes.
    script = ("$ErrorActionPreference='Stop'; "
              "[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false); "
              "try { & '" + windows.replace("'", "''") + "'; if ($LASTEXITCODE -eq 0) { exit 0 }; exit 2 } "
              "catch { [Console]::Error.WriteLine('novel-kit hook launcher failed'); exit 2 }")
    win_args = ['-NoProfile', '-NonInteractive', '-EncodedCommand', base64.b64encode(script.encode('utf-16le')).decode('ascii')]
    if agent == 'claude':
        if platform == 'windows':
            item = {'type': 'command', 'command': 'powershell.exe', 'args': win_args, 'timeout': 30}
        else:
            item = {'type': 'command', 'command': '/bin/bash', 'args': [str(hook)], 'timeout': 30}
    else:
        item = {'type': 'command', 'command': 'bash ' + shlex.quote(str(hook)),
                'commandWindows': 'powershell.exe ' + ' '.join(win_args), 'timeout': 30}
    return {'matcher': MATCHER, 'hooks': [item]}


def merge_hook_config(existing, generated):
    # Preserve all settings and third-party hooks; replace only this kit's command.
    doc = json.loads(json.dumps(existing))
    groups = doc.setdefault('hooks', {}).setdefault('PreToolUse', [])
    kept = []
    for group in groups:
        hooks = [h for h in group.get('hooks', []) if not (
            'scene_gate.' in json.dumps(h) and ('.novel-kit' in json.dumps(h) or '.claude' in json.dumps(h)))]
        if hooks:
            kept.append({**group, 'hooks': hooks})
    doc['hooks']['PreToolUse'] = [*kept, generated]
    return doc


def outputs(root, agents, platform, models='quality'):
    result = {}
    for path in sorted((root/'.agents/skills').glob('*/SKILL.md')):
        if 'claude' in agents:
            result['.claude/skills/' + path.parent.name + '/SKILL.md'] = path.read_bytes()
    for path in sorted((root/'.novel-kit/roles').glob('*.md')):
        meta, body = metadata(path)
        if 'claude' in agents:
            tools = 'Read, Write, Edit, Glob, Grep' if meta['name'] == 'scene-writer' else 'Read, Glob, Grep'
            model = CLAUDE_MODELS[models].get(meta.get('tier', 'standard'))
            text = ('---\nname: '+meta['name']+'\ndescription: '+meta['description']+'\ntools: '+tools+
                    ('\nmodel: '+model if model else '')+
                    '\n---\n\n<!-- Generated from .novel-kit/roles; edit the shared source. -->\n\n'+body+'\n')
            result['.claude/agents/'+path.name] = text.encode('utf-8')
        if 'codex' in agents:
            # JSON basic strings are valid TOML basic strings; no TOML dependency on 3.9.
            lines = ['# Generated from .novel-kit/roles; edit the shared source.']
            for key, value in [('name', meta['name']), ('description', meta['description']),
                               ('developer_instructions', body)]:
                lines.append(key+' = '+json.dumps(value, ensure_ascii=False))
            if meta['name'] != 'scene-writer':
                lines.append('sandbox_mode = "read-only"')
            result['.codex/agents/'+path.stem+'.toml'] = ('\n'.join(lines)+'\n').encode('utf-8')
    for agent, target in [('claude', '.claude/settings.local.json'), ('codex', '.codex/hooks.json')]:
        if agent in agents:
            existing = read_json(inside(root, target), {})
            result[target] = encoded(merge_hook_config(existing, hook_config(root, agent, platform)))
    return result


def synchronize(root, agents, check=False, replace=False, models=None):
    source_contract(root, agents)
    platform = 'windows' if os.name == 'nt' else 'posix'
    manifest = read_json(inside(root, MANIFEST), {'files': {}})
    # An explicit choice is remembered; check/doctor reuse it instead of the default.
    models = models or manifest.get('models', 'quality')
    require(models in MODEL_POLICIES, '未知的模型策略：'+str(models))
    desired = outputs(root, agents, platform, models)
    updates, conflicts = [], []
    for name, content in desired.items():
        path = inside(root, name)
        current = path.read_bytes() if path.exists() else None
        if current == content:
            continue
        updates.append((name, content, current))
        if current is not None and manifest['files'].get(name) != sha(current):
            conflicts.append(name)
    if check:
        return [name for name, _, _ in updates]
    require(not conflicts or replace, '適配檔已有自訂或未知內容；先檢視差異，再用 --replace 備份並更新：'+', '.join(conflicts))
    # Preflight all destinations before writing any output. Unknown files stay untouched.
    backup = '.novel-kit/adapter-backups/' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    for name, _, current in updates:
        if current is not None:
            atomic(inside(root, backup+'/'+name), current)
    for name, content, _ in updates:
        atomic(inside(root, name), content)
    manifest['files'].update({name: sha(content) for name, content in desired.items()})
    manifest['platform'] = platform
    manifest['models'] = models
    atomic(inside(root, MANIFEST), encoded(manifest))
    return [name for name, _, _ in updates]


def source_drift(root, agents, models=None):
    """Check deterministic adapters without creating machine-local deployment files."""
    source_contract(root, agents)
    manifest = read_json(inside(root, MANIFEST), {'files': {}})
    models = models or manifest.get('models', 'quality')
    require(models in MODEL_POLICIES, '未知的模型策略：'+str(models))
    desired = outputs(root, agents, 'windows' if os.name == 'nt' else 'posix', models)
    prefixes = ('.claude/skills/', '.claude/agents/', '.codex/agents/')
    return [name for name, content in desired.items() if name.startswith(prefixes)
            and (not inside(root, name).is_file() or inside(root, name).read_bytes() != content)]


def doctor(root, agents):
    errors = synchronize(root, agents, check=True)
    if errors:
        print('需要 setup 或修復適配檔：'+', '.join(errors))
        return 2
    require(sys.version_info >= (3, 9), '需要 Python 3.9+')
    for agent, target in [('claude', '.claude/settings.local.json'), ('codex', '.codex/hooks.json')]:
        if agent not in agents:
            continue
        item = hook_config(root, agent, 'windows' if os.name == 'nt' else 'posix')['hooks'][0]
        if agent == 'claude':
            command = [item['command'], *item['args']]
        elif os.name == 'nt':
            command = item['commandWindows'].split()
        else:
            command = ['/bin/sh', '-c', item['command']]
        for path, code in [('正文/novel-kit-doctor.md', 2), ('設定/novel-kit-doctor.md', 0)]:
            if agent == 'codex':
                tool, data = 'apply_patch', {'command': '*** Begin Patch\n*** Add File: '+str(root/path)+'\n+test\n*** End Patch'}
            else:
                tool, data = 'Write', {'file_path': str(root/path)}
            payload = encoded({'tool_name': tool, 'cwd': str(root), 'tool_input': data})
            env = {k: v for k, v in os.environ.items() if k not in {'NOVEL_KIT_ROOT', 'CLAUDE_PROJECT_DIR'}}
            result = subprocess.run(command, input=payload, capture_output=True, cwd=root, env=env, timeout=30)
            require(result.returncode == code, agent+' Hook 自檢失敗：'+result.stderr.decode('utf-8', 'replace'))
        print(agent+': 配置一致；啟動命令允許設定、拒絕正式正文（未寫入檔案）')
    print('共享技能與規則：.agents/skills、AGENTS.md；Agent 內的載入與 Hook 信任仍需實際會話確認。')
    return 0


def main(root, argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['setup', 'doctor'])
    parser.add_argument('--agent', choices=['all', 'claude', 'codex', 'generic'], default='all')
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--check-sources', action='store_true',
                        help='只读核对确定性技能和角色副本，不要求首次部署的本机配置。')
    parser.add_argument('--replace', action='store_true', help='Back up and replace only the listed conflicting adapters.')
    parser.add_argument('--models', choices=MODEL_POLICIES,
                        help='Claude 角色模型策略：quality（预设，写手与 copy-editor 用 opus，其余 sonnet）或 inherit（全部继承会话）。')
    args = parser.parse_args(argv)
    agents = {'claude', 'codex'} if args.agent == 'all' else set() if args.agent == 'generic' else {args.agent}
    try:
        with locked(root):
            if args.command == 'doctor':
                require(not args.check_sources, '--check-sources 只用于 setup')
                return doctor(root, agents)
            if args.check_sources:
                require(not args.replace, '只读核对不能同时替换适配文件')
                differences = source_drift(root, agents, args.models)
                print('来源副本差异：'+(', '.join(differences) or '无差异'))
                return 2 if differences else 0
            changed = synchronize(root, agents, check=args.check, replace=args.replace, models=args.models)
        print(('待更新：' if args.check else '已更新：') + (', '.join(changed) or '無差異'))
        if not args.check:
            print('共用入口就緒；搬動目錄或切換作業系統後重新 setup。')
            if agents:
                print('請重啟所選 Agent，核對專案規則與技能已載入。')
            if 'codex' in agents:
                print('Codex 需在 /hooks 檢視並信任本地 Hook。')
        return 2 if args.check and changed else 0
    except (Invalid, OSError, ValueError, TypeError, KeyError, subprocess.TimeoutExpired) as e:
        print('【適配】'+str(e), file=sys.stderr)
        return 2
