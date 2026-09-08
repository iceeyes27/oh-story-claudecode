import assert from 'node:assert/strict';
import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';
import { aggregateStatus } from './quality-gate.mjs';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const SCRIPTS = join(ROOT, 'scripts');

test('all required checks must pass', () => {
  assert.equal(aggregateStatus([{ status: 'PASS' }, { status: 'PASS' }]), 'PASS');
  assert.equal(aggregateStatus([{ status: 'PASS' }, { status: 'SKIP' }]), 'BLOCKED');
  assert.equal(aggregateStatus([{ status: 'PASS' }, { status: 'BLOCKED' }]), 'BLOCKED');
  assert.equal(aggregateStatus([{ status: 'BLOCKED' }, { status: 'FAIL' }]), 'FAIL');
});

test('external E2E checks remain runnable without becoming local release requirements', () => {
  const gate = JSON.parse(readFileSync(join(SCRIPTS, 'quality-gate.json'), 'utf8'));
  for (const name of ['codex-cli-e2e', 'dashboard-e2e']) {
    assert.ok(gate.checks[name], `external check must remain registered: ${name}`);
    assert.ok(gate.profiles.external.includes(name), `external check must be runnable: ${name}`);
    for (const profile of ['fast', 'affected', 'release']) {
      assert.ok(!gate.profiles[profile].includes(name), `${profile} must not require ${name}`);
    }
  }
  for (const name of ['opencode-adapter', 'opencode-cli-e2e']) {
    assert.ok(!gate.checks[name], `removed platform check must not remain registered: ${name}`);
    assert.ok(Object.values(gate.profiles).every((names) => !names.includes(name)));
  }
});

function collectScriptRefs(text) {
  const refs = new Set();
  const live = text.split(/\r?\n/).filter((line) => {
    const trimmed = line.trim();
    return trimmed && !trimmed.startsWith('#') && !trimmed.startsWith('//');
  }).join('\n');
  for (const pattern of [
    /scripts\/(test-[A-Za-z0-9._-]+)/g,
    /(?:^|[\s"'`=])(test-[A-Za-z0-9._-]+\.(?:sh|py|js|mjs))/gm,
  ]) {
    for (const match of live.matchAll(pattern)) refs.add(match[1]);
  }
  return refs;
}

test('every scripts/test-* file is reachable from a quality-gate profile', () => {
  const gate = JSON.parse(readFileSync(join(SCRIPTS, 'quality-gate.json'), 'utf8'));
  const pkg = JSON.parse(readFileSync(join(ROOT, 'package.json'), 'utf8'));
  const tests = readdirSync(SCRIPTS).filter((name) => name.startsWith('test-'));
  const reachable = new Set();
  const queue = [];
  const enqueue = (name) => {
    if (!name || reachable.has(name)) return;
    reachable.add(name);
    queue.push(name);
  };

  for (const names of Object.values(gate.profiles)) {
    for (const checkName of names) {
      const check = gate.checks[checkName];
      assert.ok(check, `missing check: ${checkName}`);
      for (const arg of check.args || []) {
        if (typeof arg !== 'string') continue;
        if (arg.startsWith('scripts/')) enqueue(arg.slice('scripts/'.length));
        const script = pkg.scripts?.[arg];
        if (script) {
          for (const ref of collectScriptRefs(script)) enqueue(ref);
        }
      }
    }
  }

  const seenFiles = new Set();
  while (queue.length) {
    const name = queue.shift();
    const path = join(SCRIPTS, name);
    if (seenFiles.has(path) || !existsSync(path)) continue;
    seenFiles.add(path);
    for (const ref of collectScriptRefs(readFileSync(path, 'utf8'))) {
      if (existsSync(join(SCRIPTS, ref))) enqueue(ref);
    }
  }

  const orphans = tests.filter((name) => !reachable.has(name)).sort();
  assert.deepEqual(orphans, [], `unreachable test-* files: ${orphans.join(', ')}`);
});
