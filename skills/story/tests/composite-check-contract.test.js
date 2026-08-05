const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

// story/SKILL.md is the authoritative router contract. A deployed project's
// AGENTS.md is generated/user-owned state and must not make this source test
// depend on another checkout.
const repoRoot = path.resolve(__dirname, '..', '..', '..');
const skillPath = path.resolve(__dirname, '..', 'SKILL.md');
const skillSetPath = path.join(repoRoot, 'scripts', 'platform-skill-set.json');

test('generic novel check requires all seven stages and separate conclusions', () => {
  const skill = fs.readFileSync(skillPath, 'utf8');
  const stages = [
    '`story-review`',
    '`ai-flavor-scan`',
    '`story-deslop`（mode=novel）',
    '`dialogue-naturalness-scan`',
    '`jargon-verb-scan`',
    '`story-deslop`（mode=general）',
    '`humanizer`',
  ];

  let previous = -1;
  for (const stage of stages) {
    const position = skill.indexOf(stage, previous + 1);
    assert.notEqual(position, -1, `missing composite-check stage: ${stage}`);
    assert.ok(position > previous, `stage is out of order: ${stage}`);
    previous = position;
  }

  assert.match(skill, /检查这本小说/);
  assert.match(skill, /每完成一个阶段，立即输出该阶段的独立结论/);
  assert.match(skill, /复合检查完成：7\/7/);
  assert.match(skill, /不得静默跳过/);
});

test('every composite-check dependency is in the installable public skill set', () => {
  const published = new Set(
    JSON.parse(fs.readFileSync(skillSetPath, 'utf8')).skills
  );
  const dependencies = [
    'story-review',
    'ai-flavor-scan',
    'story-deslop',
    'dialogue-naturalness-scan',
    'jargon-verb-scan',
    'humanizer',
  ];

  for (const dependency of dependencies) {
    assert.ok(published.has(dependency), `unpublished composite-check dependency: ${dependency}`);
    assert.ok(
      fs.existsSync(path.join(repoRoot, 'skills', dependency, 'SKILL.md')),
      `published composite-check dependency is missing SKILL.md: ${dependency}`
    );
  }
});

test('story-deslop file-mode pollution dependency is publicly installable', () => {
  const published = new Set(JSON.parse(fs.readFileSync(skillSetPath, 'utf8')).skills);
  const deslop = fs.readFileSync(path.join(repoRoot, 'skills', 'story-deslop', 'SKILL.md'), 'utf8');
  assert.match(deslop, /调用 `batch-pollution-detector` Skill/);
  assert.ok(published.has('batch-pollution-detector'));
  assert.ok(fs.existsSync(path.join(repoRoot, 'skills', 'batch-pollution-detector', 'SKILL.md')));
});
