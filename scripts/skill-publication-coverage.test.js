'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const ROOT = path.resolve(__dirname, '..');

function repositorySkills() {
  return fs.readdirSync(path.join(ROOT, 'skills'), { withFileTypes: true })
    .filter((entry) => entry.isDirectory())
    .map((entry) => entry.name)
    .filter((name) => fs.existsSync(path.join(ROOT, 'skills', name, 'SKILL.md')))
    .sort();
}

test('every repository skill is explicitly public or local-only', () => {
  const published = JSON.parse(
    fs.readFileSync(path.join(ROOT, 'scripts', 'platform-skill-set.json'), 'utf8')
  ).skills;
  const localOnly = JSON.parse(
    fs.readFileSync(path.join(ROOT, 'scripts', 'local-only-skill-set.json'), 'utf8')
  ).skills;
  const publicSet = new Set(published);
  const localSet = new Set(Object.keys(localOnly));

  assert.equal(publicSet.size, published.length, 'public skill list contains duplicates');
  for (const [name, reason] of Object.entries(localOnly)) {
    assert.ok(reason.trim(), `local-only skill is missing a reason: ${name}`);
    assert.ok(!publicSet.has(name), `skill is both public and local-only: ${name}`);
  }
  assert.deepEqual([...new Set([...publicSet, ...localSet])].sort(), repositorySkills());
});
