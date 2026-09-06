#!/usr/bin/env node
'use strict';

const assert = require('assert');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawnSync } = require('child_process');
const test = require('node:test');

const SCRIPT = path.resolve(__dirname, '..', 'scripts', 'manage-skill-adapters.js');

function fixture() {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'skill-adapters-'));
  const skill = path.join(root, '.agents', 'skills', 'story-test');
  fs.mkdirSync(skill, { recursive: true });
  fs.writeFileSync(path.join(skill, 'SKILL.md'), '---\nname: story-test\n---\nsource\n');
  const shared = path.join(root, '.agents', 'skills', '_shared');
  fs.mkdirSync(path.join(shared, 'references'), { recursive: true });
  fs.mkdirSync(path.join(shared, 'scripts'), { recursive: true });
  fs.writeFileSync(path.join(shared, 'references', 'rules.md'), 'shared\n');
  return root;
}

function run(root, ...args) {
  return spawnSync(process.execPath, [SCRIPT, ...args, `--root=${root}`, '--json'], { encoding: 'utf8' });
}

function runFrom(root, ...args) {
  return spawnSync(process.execPath, [SCRIPT, ...args, '--json'], { cwd: root, encoding: 'utf8' });
}

function cleanup(root) {
  if (!fs.existsSync(root)) return;
  for (const entry of fs.readdirSync(root, { recursive: true })) {
    try { fs.chmodSync(path.join(root, entry), 0o755); } catch (_) { /* symlink or already removed */ }
  }
  fs.rmSync(root, { recursive: true, force: true });
}

test('fresh install links managed skills and preserves custom skills', (t) => {
  const root = fixture();
  t.after(() => cleanup(root));
  const custom = path.join(root, '.claude', 'skills', 'custom', 'SKILL.md');
  fs.mkdirSync(path.dirname(custom), { recursive: true });
  fs.writeFileSync(custom, 'custom\n');
  const result = run(root, 'install', '--platform=claude', '--mode=symlink');
  assert.equal(result.status, 0, result.stderr);
  assert.equal(fs.realpathSync(path.join(root, '.claude', 'skills', 'story-test')),
    fs.realpathSync(path.join(root, '.agents', 'skills', 'story-test')));
  assert.equal(fs.realpathSync(path.join(root, '.claude', 'skills', '_shared')),
    fs.realpathSync(path.join(root, '.agents', 'skills', '_shared')));
  assert.equal(fs.readFileSync(custom, 'utf8'), 'custom\n');
  assert.equal(run(root, 'check', '--platform=claude').status, 0);
});

test('default root inference works from the project root', (t) => {
  const root = fixture();
  t.after(() => cleanup(root));
  assert.equal(run(root, 'install', '--platform=claude', '--mode=symlink').status, 0);
  const result = runFrom(root, 'check', '--platform=claude');
  assert.equal(result.status, 0, result.stderr);
});

test('upgrade replaces a recognized legacy copy only with explicit consent', (t) => {
  const root = fixture();
  t.after(() => cleanup(root));
  const legacy = path.join(root, '.codex', 'skills', 'story-test');
  fs.mkdirSync(legacy, { recursive: true });
  fs.writeFileSync(path.join(legacy, 'SKILL.md'), '---\nname: story-test\n---\nstale\n');
  assert.notEqual(run(root, 'install', '--platform=codex', '--mode=symlink').status, 0);
  const migrated = run(root, 'install', '--platform=codex', '--mode=symlink', '--replace-managed-copies');
  assert.equal(migrated.status, 0, migrated.stderr);
  assert.equal(fs.realpathSync(legacy), fs.realpathSync(path.join(root, '.agents', 'skills', 'story-test')));
});

test('upgrade refuses a same-name directory with platform-only files', (t) => {
  const root = fixture();
  t.after(() => cleanup(root));
  const target = path.join(root, '.codex', 'skills', 'story-test');
  fs.mkdirSync(target, { recursive: true });
  fs.writeFileSync(path.join(target, 'SKILL.md'), '---\nname: story-test\n---\nstale\n');
  fs.writeFileSync(path.join(target, 'user-notes.md'), 'keep me\n');
  const result = run(root, 'install', '--platform=codex', '--mode=symlink', '--replace-managed-copies');
  assert.notEqual(result.status, 0);
  assert.equal(fs.readFileSync(path.join(target, 'user-notes.md'), 'utf8'), 'keep me\n');
});

test('junction backend resolves to canonical source', (t) => {
  const root = fixture();
  t.after(() => cleanup(root));
  const result = run(root, 'install', '--platform=zcode', '--mode=junction');
  assert.equal(result.status, 0, result.stderr);
  assert.equal(run(root, 'check', '--platform=zcode').status, 0);
});

test('fallback detects content drift and stale source hashes', (t) => {
  const root = fixture();
  t.after(() => cleanup(root));
  const result = run(root, 'install', '--platform=opencode', '--mode=fallback');
  assert.equal(result.status, 0, result.stderr);
  const targetFile = path.join(root, '.opencode', 'skills', 'story-test', 'SKILL.md');
  fs.chmodSync(targetFile, 0o644);
  fs.appendFileSync(targetFile, 'drift\n');
  assert.notEqual(run(root, 'check', '--platform=opencode').status, 0);
  assert.equal(run(root, 'repair', '--platform=opencode', '--mode=fallback').status, 0);
  const sourceFile = path.join(root, '.agents', 'skills', 'story-test', 'SKILL.md');
  fs.appendFileSync(sourceFile, 'new source\n');
  assert.notEqual(run(root, 'check', '--platform=opencode').status, 0);
});

test('check reports an ordinary copy and a broken link', (t) => {
  const root = fixture();
  t.after(() => cleanup(root));
  const ordinary = path.join(root, '.claude', 'skills', 'story-test');
  fs.mkdirSync(ordinary, { recursive: true });
  fs.writeFileSync(path.join(ordinary, 'SKILL.md'), '---\nname: story-test\n---\ncopy\n');
  assert.notEqual(run(root, 'check', '--platform=claude').status, 0);
  fs.rmSync(ordinary, { recursive: true, force: true });
  fs.symlinkSync('../../missing', ordinary, 'dir');
  assert.notEqual(run(root, 'check', '--platform=claude').status, 0);
});
