#!/usr/bin/env node
/**
 * sync-skills.js — 写作项目 ⇄ skill 仓库 双向同步工具（零依赖 Node）
 *
 * 权威工作副本在写作项目（如 wozaiyuenan）的 `.agents/skills/`，本仓库 `skills/` 是
 * 分发源。写作中改了 skill 之后用本工具把改动推回远程仓库；多机/上游方向用 pull。
 *
 * 用法（在写作项目根目录运行）：
 *   node <本仓库>/scripts/sync-skills.js status            # 对比差异（新增/修改/删除/远程领先）
 *   node <本仓库>/scripts/sync-skills.js push [-m "msg"]   # 本地 → fork 克隆 → commit → push
 *   node <本仓库>/scripts/sync-skills.js pull              # fork 克隆 → 本地（冲突逐个确认）
 *   可选 --branch <name>（默认 main）、--fork <path>（默认取状态文件或 D:\code\oh-story-claudecode）
 *
 * 安全序列（push）：
 *   fetch → 远程分支头 ≠ 上次同步点则中止（先 pull）→ 共享文件字节校验（不一致拒推）
 *   → 复制改动 → git add/commit/push → 更新 .skills-sync-state.json
 *
 * 状态文件：写作项目根 `.skills-sync-state.json`（应加入 .gitignore）
 * 忽略同步：_skillhub_meta.json、__pycache__、.DS_Store
 */
'use strict';
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const { spawnSync } = require('child_process');

const SKILLS = ['_shared', 'browser-cdp', 'humanizer', 'story', 'story-analyze', 'story-cover',
  'story-deslop', 'story-import', 'story-review', 'story-scan', 'story-setup', 'story-write'];
const IGNORE_BASENAMES = new Set(['_skillhub_meta.json', '.DS_Store']);
const IGNORE_DIRS = new Set(['__pycache__']);
const STATE_FILE = '.skills-sync-state.json';
const DEFAULT_FORK = 'D:\\code\\oh-story-claudecode';

// v0.8+ 将反 AI 规则与扫描器集中到 _shared。旧版副本布局仍支持检查，便于迁移。
const CANONICAL_SHARED_FILES = [
  'references/anti-ai-writing.md',
  'references/banned-words.md',
  'references/deslop-whitelist',
  'scripts/check-ai-patterns.js',
  'scripts/check-degeneration.js',
  'scripts/normalize-punctuation.js',
];
const LEGACY_SHARED_SETS = [
  { name: 'banned-words.md', copies: [
    'story-analyze/references/banned-words.md',
    'story-deslop/references/banned-words.md',
    'story-review/references/banned-words.md',
    'story-write/references/banned-words.md',
    'story-setup/references/agent-references/banned-words.md'] },
  { name: 'check-ai-patterns.js', copies: [
    'story-deslop/scripts/check-ai-patterns.js',
    'story-review/scripts/check-ai-patterns.js',
    'story-write/scripts/check-ai-patterns.js'] },
];

function die(msg) { console.error('[sync-skills] ' + msg); process.exit(1); }
function info(msg) { console.log('[sync-skills] ' + msg); }

function git(forkPath, args, opts) {
  const r = spawnSync('git', args, { cwd: forkPath, encoding: 'utf8', ...opts });
  if (r.status !== 0 && !(opts && opts.allowFail)) {
    die('git ' + args.join(' ') + ' 失败：\n' + (r.stderr || r.stdout));
  }
  return (r.stdout || '').trim();
}

function loadState(projRoot) {
  const p = path.join(projRoot, STATE_FILE);
  if (fs.existsSync(p)) {
    try { return JSON.parse(fs.readFileSync(p, 'utf8')); } catch (e) { die(STATE_FILE + ' 解析失败：' + e.message); }
  }
  return null;
}
function saveState(projRoot, state) {
  fs.writeFileSync(path.join(projRoot, STATE_FILE), JSON.stringify(state, null, 2) + '\n');
}

function listFiles(root) {
  const out = new Map(); // rel -> abs
  if (!fs.existsSync(root)) return out;
  const walk = (dir, rel) => {
    for (const ent of fs.readdirSync(dir, { withFileTypes: true })) {
      if (IGNORE_DIRS.has(ent.name)) continue;
      const abs = path.join(dir, ent.name);
      const r = rel ? rel + '/' + ent.name : ent.name;
      if (ent.isDirectory()) walk(abs, r);
      else if (ent.isFile() && !IGNORE_BASENAMES.has(ent.name)) out.set(r, abs);
    }
  };
  walk(root, '');
  return out;
}

function hashFile(p) {
  return crypto.createHash('md5').update(fs.readFileSync(p)).digest('hex');
}

function computeDiff(localSkills, forkSkills) {
  const added = [], modified = [], deleted = [];
  for (const skill of SKILLS) {
    const l = listFiles(path.join(localSkills, skill));
    const f = listFiles(path.join(forkSkills, skill));
    for (const [rel, abs] of l) {
      const fAbs = f.get(rel);
      if (!fAbs) added.push(skill + '/' + rel);
      else if (hashFile(abs) !== hashFile(fAbs)) modified.push(skill + '/' + rel);
    }
    for (const rel of f.keys()) {
      if (!l.has(rel)) deleted.push(skill + '/' + rel);
    }
  }
  return { added, modified, deleted };
}

function checkShared(localSkills) {
  const bad = [];
  const canonicalRoot = path.join(localSkills, '_shared');
  if (fs.existsSync(canonicalRoot)) {
    for (const rel of CANONICAL_SHARED_FILES) {
      if (!fs.existsSync(path.join(canonicalRoot, rel))) {
        bad.push('_shared: 缺少权威文件 ' + rel);
      }
    }
    for (const set of LEGACY_SHARED_SETS) {
      for (const rel of set.copies) {
        if (fs.existsSync(path.join(localSkills, rel))) {
          bad.push(set.name + ': 发现应移除的旧版副本 ' + rel);
        }
      }
    }
    return bad;
  }

  for (const set of LEGACY_SHARED_SETS) {
    const hashes = new Map();
    for (const rel of set.copies) {
      const p = path.join(localSkills, rel);
      if (!fs.existsSync(p)) { bad.push(set.name + ': 缺失副本 ' + rel); continue; }
      const h = hashFile(p);
      if (!hashes.has(h)) hashes.set(h, []);
      hashes.get(h).push(rel);
    }
    if (hashes.size > 1) {
      bad.push(set.name + ': ' + hashes.size + ' 个不同版本 — ' +
        [...hashes.values()].map(v => v.join(', ')).join(' ≠ '));
    }
  }
  return bad;
}

function resolvePaths(argv) {
  const projRoot = process.cwd();
  const canonicalSkills = path.join(projRoot, '.agents', 'skills');
  const legacySkills = path.join(projRoot, '.claude', 'skills');
  const localSkills = fs.existsSync(canonicalSkills) ? canonicalSkills : legacySkills;
  if (!fs.existsSync(localSkills)) {
    die('当前目录不是写作项目根（缺 .agents/skills/；旧项目也未找到 .claude/skills/）。请在写作项目根目录运行。');
  }
  const state = loadState(projRoot) || {};
  const forkPath = argv.fork || state.forkPath || DEFAULT_FORK;
  const branch = argv.branch || state.branch || 'main';
  if (!fs.existsSync(path.join(forkPath, '.git'))) {
    die('fork 克隆不存在：' + forkPath + '\n重建：git clone git@github.com:iceeyes27/oh-story-claudecode.git "' + forkPath + '" && cd "' + forkPath + '" && git remote add upstream https://github.com/worldwonderer/oh-story-claudecode.git');
  }
  return { projRoot, localSkills, forkSkills: path.join(forkPath, 'skills'), forkPath, branch, state };
}

function parseArgv() {
  const a = { _: [] };
  const args = process.argv.slice(2);
  for (let i = 0; i < args.length; i++) {
    if (args[i] === '-m') a.message = args[++i];
    else if (args[i] === '--branch') a.branch = args[++i];
    else if (args[i] === '--fork') a.fork = args[++i];
    else if (args[i] === '--json') a.json = true;
    else a._.push(args[i]);
  }
  return a;
}

function copyFile(src, dst) {
  fs.mkdirSync(path.dirname(dst), { recursive: true });
  fs.copyFileSync(src, dst);
}

function main() {
  const argv = parseArgv();
  const cmd = argv._[0];
  if (!['status', 'push', 'pull'].includes(cmd)) {
    console.log('用法: node sync-skills.js <status|push|pull> [-m msg] [--branch name] [--fork path] [--json]');
    process.exit(cmd ? 1 : 0);
  }
  const ctx = resolvePaths(argv);

  git(ctx.forkPath, ['fetch', 'origin']);
  const localHead = git(ctx.forkPath, ['rev-parse', ctx.branch]);
  const remoteHead = git(ctx.forkPath, ['rev-parse', 'origin/' + ctx.branch]);
  const dirty = git(ctx.forkPath, ['status', '--porcelain']);
  const diff = computeDiff(ctx.localSkills, ctx.forkSkills);
  const remoteAhead = remoteHead !== localHead ? remoteHead : null;
  const lastSynced = ctx.state.lastSyncedCommit || null;

  if (cmd === 'status') {
    if (argv.json) {
      console.log(JSON.stringify({ ...diff, remoteHead, localForkHead: localHead, remoteAhead: !!remoteAhead, forkDirty: !!dirty, lastSynced }, null, 2));
      return;
    }
    info('fork 克隆: ' + ctx.forkPath + ' @ ' + ctx.branch + ' (' + localHead.slice(0, 7) + ')');
    if (remoteAhead) info('⚠ 远程领先本地克隆（origin/' + ctx.branch + ' = ' + remoteHead.slice(0, 7) + '），push 前需先在克隆里 git pull');
    if (dirty) info('⚠ fork 克隆工作区不干净（有未提交改动）');
    const p = (t, arr) => { if (arr.length) { console.log('\n' + t + ' (' + arr.length + '):'); arr.forEach(x => console.log('  ' + x)); } };
    p('本地新增', diff.added); p('本地修改', diff.modified); p('本地删除', diff.deleted);
    if (!diff.added.length && !diff.modified.length && !diff.deleted.length) info('本地与 fork 克隆无差异。');
    const sharedBad = checkShared(ctx.localSkills);
    if (sharedBad.length) { console.log('\n共享文件不一致:'); sharedBad.forEach(x => console.log('  ' + x)); }
    return;
  }

  if (cmd === 'push') {
    if (dirty) die('fork 克隆工作区不干净，先在 ' + ctx.forkPath + ' 处理未提交改动。');
    if (remoteAhead) die('远程 origin/' + ctx.branch + ' 领先本地克隆。先在克隆里 git pull（或运行本工具 pull 同步回本地）再 push。');
    if (lastSynced && localHead !== lastSynced) {
      info('提示：fork 克隆头 ' + localHead.slice(0, 7) + ' ≠ 上次同步点 ' + lastSynced.slice(0, 7) + '（可能有仓库侧独立提交，属正常）');
    }
    const sharedBad = checkShared(ctx.localSkills);
    if (sharedBad.length) die('共享文件字节不一致，拒绝推送：\n  ' + sharedBad.join('\n  ') + '\n先把副本同步一致（改哪份就把它 cp 到其余副本）。');
    const total = diff.added.length + diff.modified.length + diff.deleted.length;
    if (!total) { info('无改动可推送。'); return; }
    for (const rel of [...diff.added, ...diff.modified]) {
      copyFile(path.join(ctx.localSkills, rel), path.join(ctx.forkSkills, rel));
    }
    for (const rel of diff.deleted) {
      fs.rmSync(path.join(ctx.forkSkills, rel), { force: true });
    }
    git(ctx.forkPath, ['add', '-A', 'skills/']);
    const msg = argv.message || ('sync(skills): ' + total + ' files from writing project');
    git(ctx.forkPath, ['commit', '-m', msg]);
    git(ctx.forkPath, ['push', 'origin', ctx.branch]);
    const newHead = git(ctx.forkPath, ['rev-parse', ctx.branch]);
    saveState(ctx.projRoot, { forkPath: ctx.forkPath, branch: ctx.branch, lastSyncedCommit: newHead, lastSyncedAt: new Date().toISOString() });
    info('已推送 ' + total + ' 个文件到 origin/' + ctx.branch + ' (' + newHead.slice(0, 7) + ')');
    return;
  }

  if (cmd === 'pull') {
    if (remoteAhead) {
      info('远程领先，先更新 fork 克隆…');
      if (dirty) die('fork 克隆工作区不干净，无法 pull。');
      git(ctx.forkPath, ['pull', '--ff-only', 'origin', ctx.branch]);
    }
    const diff2 = computeDiff(ctx.localSkills, ctx.forkSkills);
    // pull 方向：fork 有而本地无 = 本地应新增；fork 与本地不同 = 需确认
    const toAdd = diff2.deleted;       // 本地缺的
    const conflict = diff2.modified;   // 双方都有但不同
    const localOnly = diff2.added;     // 本地多出（不动）
    if (!toAdd.length && !conflict.length) { info('本地已是最新。'); return; }
    for (const rel of toAdd) {
      copyFile(path.join(ctx.forkSkills, rel), path.join(ctx.localSkills, rel));
      console.log('  + ' + rel);
    }
    if (conflict.length) {
      console.log('\n以下文件本地与 fork 都有改动，未覆盖（需人工比对后决定，或本地改完用 push 反推）:');
      conflict.forEach(x => console.log('  ! ' + x));
    }
    const newHead = git(ctx.forkPath, ['rev-parse', ctx.branch]);
    saveState(ctx.projRoot, { forkPath: ctx.forkPath, branch: ctx.branch, lastSyncedCommit: newHead, lastSyncedAt: new Date().toISOString() });
    info('pull 完成：新增 ' + toAdd.length + '，冲突待人工 ' + conflict.length + '，本地独有 ' + localOnly.length);
    return;
  }
}

if (require.main === module) main();

module.exports = { CANONICAL_SHARED_FILES, LEGACY_SHARED_SETS, checkShared, computeDiff, resolvePaths };
