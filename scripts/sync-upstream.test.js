'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { execFileSync } = require('node:child_process');
const test = require('node:test');
const {
  abort,
  classifyPath,
  isAncestor,
  loadPolicy,
  mappedTargetFor,
  parseArgs,
  prepare,
  review,
} = require('./sync-upstream.js');

const ROOT = path.resolve(__dirname, '..');

function git(cwd, ...args) {
  return execFileSync('git', args, { cwd, encoding: 'utf8' }).trim();
}

function write(file, content) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, content, 'utf8');
}

test('policy priority preserves fork boundaries and unified targets', () => {
  const { policy } = loadPolicy(path.join(ROOT, 'scripts', 'upstream-integration.json'));
  assert.equal(classifyPath('.github/workflows/cross-platform.yml', policy).category, 'forbidden');
  assert.equal(classifyPath('.trellis/tasks/example/prd.md', policy).category, 'protected');
  assert.equal(classifyPath('skills/_shared/scripts/check-ai-patterns.js', policy).category, 'shared');
  assert.equal(classifyPath('skills/story-long-write/SKILL.md', policy).category, 'unified');
  assert.equal(
    mappedTargetFor('skills/story-short-write/references/example.md', policy.unified_mappings),
    'skills/story-write/references/example.md',
  );
  assert.equal(classifyPath('unexpected/new-root.txt', policy).category, 'unknown');
});

test('CLI defaults to a read-only status command', () => {
  const options = parseArgs([]);
  assert.equal(options.command, 'status');
  assert.equal(options.fetch, true);
  assert.equal(options.repo, ROOT);
  assert.equal(options.policy, path.join(ROOT, 'scripts', 'upstream-integration.json'));
});

test('ancestor check distinguishes forward and reverse baselines', () => {
  const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'oh-story-sync-ancestor-'));
  try {
    git(temporary, 'init', '-q');
    git(temporary, 'config', 'user.email', 'test@example.com');
    git(temporary, 'config', 'user.name', 'Sync Test');
    write(path.join(temporary, 'a.txt'), 'a\n');
    git(temporary, 'add', 'a.txt');
    git(temporary, 'commit', '-qm', 'base');
    const base = git(temporary, 'rev-parse', 'HEAD');
    write(path.join(temporary, 'a.txt'), 'b\n');
    git(temporary, 'commit', '-qam', 'target');
    const target = git(temporary, 'rev-parse', 'HEAD');
    assert.equal(isAncestor(temporary, base, target), true);
    assert.equal(isAncestor(temporary, target, base), false);
  } finally {
    fs.rmSync(temporary, { recursive: true, force: true });
  }
});

test('prepare uses a dedicated worktree and leaves dirty caller files untouched', () => {
  const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'oh-story-sync-prepare-'));
  const repo = path.join(temporary, 'repo');
  const managed = path.join(temporary, 'managed-worktree');
  fs.mkdirSync(repo);
  let state;
  try {
    git(repo, 'init', '-q');
    git(repo, 'config', 'user.email', 'test@example.com');
    git(repo, 'config', 'user.name', 'Sync Test');
    write(path.join(repo, 'README.md'), 'base\n');
    write(path.join(repo, 'scripts', 'quality-gate.mjs'), 'process.exit(0);\n');
    git(repo, 'add', '.');
    git(repo, 'commit', '-qm', 'base');
    const base = git(repo, 'rev-parse', 'HEAD');
    git(repo, 'checkout', '-qb', 'upstream-sim');
    write(path.join(repo, 'skills', 'story-long-write', 'SKILL.md'), 'upstream split\n');
    git(repo, 'add', '.');
    git(repo, 'commit', '-qm', 'upstream change');
    const target = git(repo, 'rev-parse', 'HEAD');
    git(repo, 'checkout', '-q', 'master');
    git(repo, 'remote', 'add', 'origin', repo);
    git(repo, 'remote', 'add', 'upstream', repo);
    git(repo, 'remote', 'set-url', '--push', 'upstream', 'DISABLED');

    const policy = {
      schema_version: 1,
      origin: { remote: 'origin', branch: 'master' },
      upstream: { remote: 'upstream', branch: 'upstream-sim', baseline: base },
      quality_profile: 'release',
      policy_priority: ['forbidden', 'protected', 'generated', 'shared', 'unified', 'canonical', 'unknown'],
      policies: {
        forbidden: [{ prefix: '.github/workflows/' }],
        protected: [{ path: 'scripts/upstream-integration.json' }],
        generated: [],
        shared: [],
        canonical: [{ prefix: 'scripts/' }, { path: 'README.md' }],
      },
      unified_mappings: [{ source: 'skills/story-long-write', target: 'skills/story-write' }],
    };
    const policyPath = path.join(repo, 'scripts', 'upstream-integration.json');
    write(policyPath, `${JSON.stringify(policy, null, 2)}\n`);
    write(path.join(repo, 'caller-wip.txt'), 'must remain\n');

    const options = parseArgs([
      'prepare', '--repo', repo, '--policy', policyPath, '--no-fetch',
      '--origin-sha', base, '--upstream-sha', target, '--worktree', managed,
    ]);
    state = prepare(options);
    assert.equal(state.phase, 'prepared');
    assert.equal(fs.readFileSync(path.join(repo, 'caller-wip.txt'), 'utf8'), 'must remain\n');
    assert.equal(fs.existsSync(path.join(managed, 'skills', 'story-long-write')), false);
    assert.equal(state.changes.filter((entry) => entry.category === 'unified').length, 1);

    const decisionPath = path.join(temporary, 'decisions.json');
    write(decisionPath, `${JSON.stringify({
      schema_version: 1,
      sync_id: state.id,
      decisions: state.changes
        .filter((entry) => entry.category === 'unified')
        .map((entry) => ({ id: entry.id, decision: 'adapt', reason: 'Ported into the unified Skill.' })),
    }, null, 2)}\n`);
    state = review(parseArgs(['review', '--repo', repo, '--id', state.id, '--decision-file', decisionPath]));
    assert.equal(state.phase, 'reviewed');
    state = abort(parseArgs(['abort', '--repo', repo, '--id', state.id]));
    assert.equal(state.phase, 'aborted');
    assert.equal(fs.existsSync(managed), false);
    assert.equal(fs.existsSync(path.join(repo, 'caller-wip.txt')), true);
  } finally {
    if (state && state.phase !== 'aborted' && fs.existsSync(managed)) {
      try { abort(parseArgs(['abort', '--repo', repo, '--id', state.id])); } catch {}
    }
    fs.rmSync(temporary, { recursive: true, force: true });
  }
});
