'use strict';

const assert = require('node:assert/strict');
const test = require('node:test');
const { loadMappings, mappedTargetFor, parseArgs } = require('./sync-upstream.js');

test('mapped split-skill conflicts resolve to unified targets', () => {
  const mappings = loadMappings();
  assert.equal(
    mappedTargetFor('skills/story-long-analyze/SKILL.md', mappings),
    'skills/story-analyze/SKILL.md'
  );
  assert.equal(
    mappedTargetFor('skills/story-short-write/references/example.md', mappings),
    'skills/story-write/references/example.md'
  );
  assert.equal(mappedTargetFor('skills/story-setup/SKILL.md', mappings), null);
});

test('sync options are conservative by default', () => {
  assert.deepEqual(parseArgs([]), {
    remote: 'upstream',
    branch: 'main',
    commit: false,
    check: true,
  });
});
