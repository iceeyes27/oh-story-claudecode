#!/usr/bin/env node
'use strict';

const assert = require('assert');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawnSync } = require('child_process');
const test = require('node:test');

const ROOT = path.resolve(__dirname, '..', '..', '..', '..');
const SHARED = path.join(ROOT, '.agents', 'skills', '_shared');

test('shared prose rules and scanners have one canonical entity', () => {
  const names = new Set([
    'banned-words.md', 'anti-ai-writing.md', 'check-ai-patterns.js',
    'check-degeneration.js', 'normalize-punctuation.js',
  ]);
  const found = [];
  function walk(directory) {
    for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
      const full = path.join(directory, entry.name);
      if (entry.isDirectory()) walk(full);
      else if (names.has(entry.name)) {
        found.push(path.relative(path.join(ROOT, '.agents', 'skills'), full).split(path.sep).join('/'));
      }
    }
  }
  walk(path.join(ROOT, '.agents', 'skills'));
  assert.deepEqual(found.sort(), [
    '_shared/references/anti-ai-writing.md',
    '_shared/references/banned-words.md',
    '_shared/scripts/check-ai-patterns.js',
    '_shared/scripts/check-degeneration.js',
    '_shared/scripts/normalize-punctuation.js',
  ]);
});

test('AI scanner fails closed when the canonical banned-word file is missing', (t) => {
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'shared-rules-'));
  t.after(() => fs.rmSync(temp, { recursive: true, force: true }));
  const scripts = path.join(temp, '_shared', 'scripts');
  fs.mkdirSync(scripts, { recursive: true });
  fs.copyFileSync(path.join(SHARED, 'scripts', 'check-ai-patterns.js'), path.join(scripts, 'check-ai-patterns.js'));
  const prose = path.join(temp, 'chapter.md');
  fs.writeFileSync(prose, '普通正文。\n');
  const result = spawnSync(process.execPath, [path.join(scripts, 'check-ai-patterns.js'), '--json', '--fail-on=blocking', prose], { encoding: 'utf8' });
  assert.equal(result.status, 1);
  const payload = JSON.parse(result.stdout);
  assert(payload.findings.some((finding) => finding.type === 'rule-load-error' && finding.severity === 'blocking'));
});

test('AI scanner flushes complete JSON before returning a blocking exit code', (t) => {
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'scanner-json-flush-'));
  t.after(() => fs.rmSync(temp, { recursive: true, force: true }));
  const files = [];
  for (let index = 0; index < 240; index += 1) {
    const prose = path.join(temp, `chapter-${index}.md`);
    fs.writeFileSync(prose, `第${index}段——这里故意触发 blocking。\n`, 'utf8');
    files.push(prose);
  }
  const scanner = path.join(SHARED, 'scripts', 'check-ai-patterns.js');
  const result = spawnSync(process.execPath, [scanner, '--check', '--json', '--fail-on=blocking', ...files], {
    encoding: 'utf8',
    maxBuffer: 20 * 1024 * 1024,
  });
  assert.equal(result.status, 1, result.stderr);
  const payload = JSON.parse(result.stdout);
  assert.equal(payload.findings.filter((finding) => finding.type === 'em-dash').length, files.length);
});

test('canonical agent templates reference the .agents bundle only', () => {
  const roots = [
    path.join(ROOT, '.agents', 'skills', 'story-setup', 'references', 'templates', 'agents'),
    path.join(ROOT, '.agents', 'skills', 'story-setup', 'references', 'codex', 'agents'),
    path.join(ROOT, '.agents', 'skills', 'story-setup', 'references', 'opencode', 'agents'),
  ];
  const stale = [];
  for (const directory of roots) {
    for (const entry of fs.readdirSync(directory)) {
      if (!/\.(md|toml)$/.test(entry)) continue;
      const file = path.join(directory, entry);
      const text = fs.readFileSync(file, 'utf8');
      if (/\.(?:claude|codex|opencode|zcode)\/skills\/story-setup\/references\/agent-references\//.test(text)) {
        stale.push(path.relative(ROOT, file));
      }
    }
  }
  assert.deepEqual(stale, []);
});

test('story consumers do not call removed skill-local prose scanners', () => {
  const files = [
    path.join(ROOT, '.agents', 'skills', 'story-write', 'SKILL.md'),
    path.join(ROOT, '.agents', 'skills', 'story-write', 'references', 'workflow-daily.md'),
    path.join(ROOT, '.agents', 'skills', 'story-write', 'references', 'writing-workflow.md'),
    path.join(ROOT, '.agents', 'skills', 'story-setup', 'UPGRADING.md'),
  ];
  for (const file of files) {
    const text = fs.readFileSync(file, 'utf8');
    assert.doesNotMatch(text, /node scripts\/(?:check-ai-patterns|check-degeneration|normalize-punctuation)\.js/);
  }
});
