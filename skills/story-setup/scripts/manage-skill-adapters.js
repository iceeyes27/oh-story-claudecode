#!/usr/bin/env node
'use strict';

const crypto = require('crypto');
const fs = require('fs');
const path = require('path');

const VERSION = 1;
const PLATFORM_DIRS = Object.freeze({
  claude: '.claude/skills',
  codex: '.codex/skills',
  opencode: '.opencode/skills',
  zcode: '.zcode/skills',
  workbuddy: '.workbuddy/skills',
  codebuddy: '.codebuddy/skills',
  cursor: '.cursor/skills',
  devin: '.devin/skills',
});
const FALLBACK_MARKER = '.skill-adapter.json';
const MANIFEST_PATH = '.agents/skill-adapters.json';

function die(message, code = 2) {
  process.stderr.write(`skill-adapters: ${message}\n`);
  process.exit(code);
}

function parseArgs(argv) {
  const options = {
    command: null,
    root: path.resolve(__dirname, '..', '..', '..', '..'),
    platforms: null,
    mode: 'auto',
    replaceManagedCopies: false,
    json: false,
  };
  for (const arg of argv) {
    if (!options.command && ['install', 'check', 'repair', 'remove'].includes(arg)) {
      options.command = arg;
    } else if (arg.startsWith('--root=')) {
      options.root = path.resolve(arg.slice('--root='.length));
    } else if (arg.startsWith('--platform=')) {
      const value = arg.slice('--platform='.length);
      options.platforms = value === 'all' ? Object.keys(PLATFORM_DIRS) : value.split(',').filter(Boolean);
    } else if (arg.startsWith('--mode=')) {
      options.mode = arg.slice('--mode='.length);
    } else if (arg === '--replace-managed-copies') {
      options.replaceManagedCopies = true;
    } else if (arg === '--json') {
      options.json = true;
    } else if (arg === '-h' || arg === '--help') {
      process.stdout.write(`Usage: manage-skill-adapters.js <install|check|repair|remove> [options]\n\n` +
        `Options:\n` +
        `  --root=<project>       Project root (default: inferred from this script)\n` +
        `  --platform=<list|all>  ${Object.keys(PLATFORM_DIRS).join(',')}\n` +
        `  --mode=<mode>          auto, symlink, junction, or fallback\n` +
        `  --replace-managed-copies  Migrate same-name generated/legacy copies\n` +
        `  --json                 Machine-readable output\n`);
      process.exit(0);
    } else {
      die(`unknown argument: ${arg}`);
    }
  }
  if (!options.command) die('missing command (install, check, repair, or remove)');
  if (!['auto', 'symlink', 'junction', 'fallback'].includes(options.mode)) die(`invalid mode: ${options.mode}`);
  if (options.platforms) {
    for (const platform of options.platforms) {
      if (!PLATFORM_DIRS[platform]) die(`unsupported platform: ${platform}`);
    }
  }
  return options;
}

function canonicalRoot(root) {
  return path.join(root, '.agents', 'skills');
}

function listSkills(root) {
  const base = canonicalRoot(root);
  if (!fs.existsSync(base)) throw new Error(`canonical skill root is missing: ${base}`);
  return fs.readdirSync(base, { withFileTypes: true })
    .filter((entry) => entry.isDirectory())
    .map((entry) => entry.name)
    .filter((name) => name === '_shared' || fs.existsSync(path.join(base, name, 'SKILL.md')))
    .sort();
}

function detectPlatforms(root) {
  const found = Object.entries(PLATFORM_DIRS)
    .filter(([, relative]) => fs.existsSync(path.join(root, path.dirname(relative))))
    .map(([name]) => name);
  if (found.length) return found;
  return ['claude', 'codex'];
}

function walkFiles(base, relative = '') {
  const directory = path.join(base, relative);
  const files = [];
  for (const entry of fs.readdirSync(directory, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name))) {
    const child = path.join(relative, entry.name);
    if (entry.isDirectory()) files.push(...walkFiles(base, child));
    else if (entry.isFile()) files.push(child);
    else if (entry.isSymbolicLink()) files.push(child);
  }
  return files;
}

function hashTree(base, ignored = new Set()) {
  const hash = crypto.createHash('sha256');
  for (const relative of walkFiles(base)) {
    if (ignored.has(relative)) continue;
    const full = path.join(base, relative);
    const stat = fs.lstatSync(full);
    hash.update(relative.replaceAll(path.sep, '/'));
    hash.update('\0');
    if (stat.isSymbolicLink()) hash.update(`link:${fs.readlinkSync(full)}`);
    else hash.update(fs.readFileSync(full));
    hash.update('\0');
  }
  return hash.digest('hex');
}

function readSkillName(skillDir) {
  try {
    const head = fs.readFileSync(path.join(skillDir, 'SKILL.md'), 'utf8').slice(0, 4096);
    const match = head.match(/^name:\s*["']?([^\s"']+)/m);
    return match ? match[1] : null;
  } catch (_) {
    return null;
  }
}

function isManagedOrdinaryCopy(target, source, skillName) {
  if (skillName === '_shared') {
    return fs.existsSync(path.join(target, 'references')) && fs.existsSync(path.join(target, 'scripts')) &&
      walkFiles(target).every((relative) => fs.existsSync(path.join(source, relative)));
  }
  if (!fs.existsSync(path.join(target, 'SKILL.md')) || readSkillName(target) !== skillName) return false;
  // Legacy generated copies may be stale or incomplete, but must not contain
  // platform-only files that would be lost during migration.
  return walkFiles(target).every((relative) => fs.existsSync(path.join(source, relative)));
}

function adapterMode(requested) {
  if (requested !== 'auto') return requested;
  return process.platform === 'win32' ? 'junction' : 'symlink';
}

function removeWritableTree(target) {
  if (!fs.existsSync(target) && !fs.lstatSync(target, { throwIfNoEntry: false })) return;
  try {
    fs.chmodSync(target, 0o755);
    if (fs.lstatSync(target).isDirectory() && !fs.lstatSync(target).isSymbolicLink()) {
      for (const relative of walkFiles(target)) {
        try { fs.chmodSync(path.join(target, relative), 0o644); } catch (_) { /* best effort */ }
      }
    }
  } catch (_) { /* Windows/read-only cleanup is best effort */ }
  fs.rmSync(target, { recursive: true, force: true });
}

function makeFallback(source, target, skillName) {
  fs.cpSync(source, target, { recursive: true, dereference: true });
  const sourceHash = hashTree(source);
  fs.writeFileSync(path.join(target, FALLBACK_MARKER), `${JSON.stringify({
    schema: VERSION,
    generated: true,
    skill: skillName,
    source: path.relative(target, source),
    sourceHash,
  }, null, 2)}\n`);
  for (const relative of walkFiles(target)) {
    try { fs.chmodSync(path.join(target, relative), 0o444); } catch (_) { /* advisory on Windows */ }
  }
  try { fs.chmodSync(target, 0o555); } catch (_) { /* advisory on Windows */ }
}

function makeAdapter(source, target, mode, skillName) {
  if (mode === 'fallback') {
    makeFallback(source, target, skillName);
    return;
  }
  const linkTarget = mode === 'junction' ? source : path.relative(path.dirname(target), source);
  fs.symlinkSync(linkTarget, target, mode === 'junction' ? 'junction' : 'dir');
}

function installOne(source, target, skillName, mode, allowReplace) {
  const existing = fs.lstatSync(target, { throwIfNoEntry: false });
  if (existing) {
    const state = inspectOne(source, target, skillName);
    if (state.ok) return { changed: false, mode: state.mode };
    if (existing.isSymbolicLink() || fs.existsSync(path.join(target, FALLBACK_MARKER))) {
      // Broken/incorrect generated adapters are safe to repair.
    } else if (!(allowReplace && existing.isDirectory() && isManagedOrdinaryCopy(target, source, skillName))) {
      throw new Error(`${target}: refusing to replace non-managed content (${state.reason})`);
    }
  }

  fs.mkdirSync(path.dirname(target), { recursive: true });
  const nonce = `${process.pid}-${Date.now()}`;
  const staged = `${target}.adapter-new-${nonce}`;
  const backup = `${target}.adapter-old-${nonce}`;
  removeWritableTree(staged);
  removeWritableTree(backup);
  makeAdapter(source, staged, mode, skillName);
  try {
    if (existing) fs.renameSync(target, backup);
    fs.renameSync(staged, target);
    removeWritableTree(backup);
  } catch (error) {
    removeWritableTree(staged);
    if (!fs.existsSync(target) && fs.existsSync(backup)) fs.renameSync(backup, target);
    throw error;
  }
  return { changed: true, mode };
}

function inspectOne(source, target, skillName) {
  const stat = fs.lstatSync(target, { throwIfNoEntry: false });
  if (!stat) return { ok: false, mode: 'missing', reason: 'missing adapter' };
  if (stat.isSymbolicLink()) {
    try {
      const actual = fs.realpathSync(target);
      const expected = fs.realpathSync(source);
      return actual === expected
        ? { ok: true, mode: process.platform === 'win32' ? 'junction' : 'symlink' }
        : { ok: false, mode: 'link', reason: `wrong target: ${actual}` };
    } catch (error) {
      return { ok: false, mode: 'link', reason: `broken link: ${error.message}` };
    }
  }
  if (!stat.isDirectory()) return { ok: false, mode: 'ordinary', reason: 'adapter is not a directory' };
  const markerPath = path.join(target, FALLBACK_MARKER);
  if (!fs.existsSync(markerPath)) return { ok: false, mode: 'ordinary', reason: 'ordinary copy can drift' };
  try {
    const marker = JSON.parse(fs.readFileSync(markerPath, 'utf8'));
    if (!marker.generated || marker.skill !== skillName) return { ok: false, mode: 'fallback', reason: 'invalid fallback marker' };
    const expected = hashTree(source);
    const actual = hashTree(target, new Set([FALLBACK_MARKER]));
    if (marker.sourceHash !== expected) return { ok: false, mode: 'fallback', reason: 'fallback manifest source hash is stale' };
    if (actual !== expected) return { ok: false, mode: 'fallback', reason: 'fallback content drifted' };
    return { ok: true, mode: 'fallback' };
  } catch (error) {
    return { ok: false, mode: 'fallback', reason: `invalid fallback: ${error.message}` };
  }
}

function writeManifest(root, platforms, entries) {
  const destination = path.join(root, MANIFEST_PATH);
  fs.mkdirSync(path.dirname(destination), { recursive: true });
  fs.writeFileSync(destination, `${JSON.stringify({
    schema: VERSION,
    canonicalRoot: '.agents/skills',
    generatedAt: new Date().toISOString(),
    platforms,
    entries,
  }, null, 2)}\n`);
}

function validateManifest(root, platforms, skills) {
  const destination = path.join(root, MANIFEST_PATH);
  try {
    const manifest = JSON.parse(fs.readFileSync(destination, 'utf8'));
    if (manifest.schema !== VERSION) throw new Error(`unsupported schema: ${manifest.schema}`);
    if (manifest.canonicalRoot !== '.agents/skills') throw new Error(`wrong canonicalRoot: ${manifest.canonicalRoot}`);
    const entries = new Map((manifest.entries || []).map((entry) => [`${entry.platform}\0${entry.skill}`, entry]));
    const expected = new Set(platforms.flatMap((platform) => skills.map((skill) => `${platform}\0${skill}`)));
    for (const key of entries.keys()) {
      const [platform] = key.split('\0');
      if (platforms.includes(platform) && !expected.has(key)) throw new Error(`unexpected manifest entry: ${key.replace('\0', '/')}`);
    }
    for (const platform of platforms) {
      for (const skill of skills) {
        const entry = entries.get(`${platform}\0${skill}`);
        if (!entry) throw new Error(`missing manifest entry: ${platform}/${skill}`);
        const actual = hashTree(path.join(canonicalRoot(root), skill));
        if (entry.sourceHash !== actual) throw new Error(`stale source hash: ${platform}/${skill}`);
      }
    }
    return { ok: true, mode: 'manifest', target: MANIFEST_PATH };
  } catch (error) {
    return { ok: false, mode: 'manifest', target: MANIFEST_PATH, reason: error.message };
  }
}

function setupVersion(root) {
  try {
    const text = fs.readFileSync(path.join(canonicalRoot(root), 'story-setup', 'SKILL.md'), 'utf8').slice(0, 2048);
    return text.match(/^version:\s*([^\s]+)/m)?.[1] || 'unknown';
  } catch (_) {
    return 'unknown';
  }
}

function execute(options) {
  const skills = listSkills(options.root);
  const platforms = options.platforms || detectPlatforms(options.root);
  const mode = adapterMode(options.mode);
  const results = [];

  for (const platform of platforms) {
    const platformRoot = path.join(options.root, PLATFORM_DIRS[platform]);
    for (const skillName of skills) {
      const source = path.join(canonicalRoot(options.root), skillName);
      const target = path.join(platformRoot, skillName);
      if (options.command === 'check') {
        const state = inspectOne(source, target, skillName);
        results.push({ platform, skill: skillName, target: path.relative(options.root, target), ...state });
      } else if (options.command === 'remove') {
        const state = inspectOne(source, target, skillName);
        if (state.ok || fs.lstatSync(target, { throwIfNoEntry: false })?.isSymbolicLink()) {
          removeWritableTree(target);
          results.push({ platform, skill: skillName, target: path.relative(options.root, target), ok: true, removed: true });
        }
      } else {
        const installed = installOne(source, target, skillName, mode,
          options.replaceManagedCopies || options.command === 'repair');
        results.push({ platform, skill: skillName, target: path.relative(options.root, target), ok: true, ...installed });
      }
    }
  }

  if (options.command === 'check') results.push(validateManifest(options.root, platforms, skills));

  if (options.command === 'install' || options.command === 'repair') {
    writeManifest(options.root, platforms, results.map(({ platform, skill, target, mode: resultMode }) => ({
      platform, skill, target, mode: resultMode, sourceHash: hashTree(path.join(canonicalRoot(options.root), skill)),
    })));
  }
  const failures = results.filter((result) => result.ok === false);
  const payload = { command: options.command, root: options.root, canonicalRoot: canonicalRoot(options.root), setupVersion: setupVersion(options.root), mode, results, failures: failures.length };
  if (options.json) process.stdout.write(`${JSON.stringify(payload, null, 2)}\n`);
  else {
    process.stdout.write(`skill-adapters ${options.command}: ${results.length - failures.length}/${results.length} OK; canonical=${canonicalRoot(options.root)}; story-setup=${payload.setupVersion}\n`);
    for (const failure of failures) process.stderr.write(`  FAIL ${failure.target}: ${failure.reason}\n`);
  }
  return failures.length ? 1 : 0;
}

try {
  process.exitCode = execute(parseArgs(process.argv.slice(2)));
} catch (error) {
  die(error.message, 1);
}
