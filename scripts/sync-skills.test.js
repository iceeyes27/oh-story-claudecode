'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const test = require('node:test');
const { CANONICAL_SHARED_FILES, checkShared, computeDiff } = require('./sync-skills.js');

function withTempDir(run) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'sync-skills-'));
  try { run(root); } finally { fs.rmSync(root, { recursive: true, force: true }); }
}

function write(root, rel, content = rel) {
  const target = path.join(root, rel);
  fs.mkdirSync(path.dirname(target), { recursive: true });
  fs.writeFileSync(target, content);
}

test('canonical shared layout passes only when every required file exists', () => {
  withTempDir((root) => {
    for (const rel of CANONICAL_SHARED_FILES) write(root, path.join('_shared', rel));
    assert.deepEqual(checkShared(root), []);

    fs.rmSync(path.join(root, '_shared', CANONICAL_SHARED_FILES[0]));
    assert.match(checkShared(root)[0], /缺少权威文件/);
  });
});

test('canonical shared layout rejects obsolete skill-local copies', () => {
  withTempDir((root) => {
    for (const rel of CANONICAL_SHARED_FILES) write(root, path.join('_shared', rel));
    write(root, 'story-write/references/banned-words.md');
    assert.ok(checkShared(root).some((item) => item.includes('旧版副本')));
  });
});

test('diff includes the canonical _shared tree', () => {
  withTempDir((root) => {
    const local = path.join(root, 'local');
    const remote = path.join(root, 'remote');
    write(local, '_shared/references/banned-words.md', 'new');
    write(remote, '_shared/references/banned-words.md', 'old');
    assert.deepEqual(computeDiff(local, remote).modified, ['_shared/references/banned-words.md']);
  });
});
