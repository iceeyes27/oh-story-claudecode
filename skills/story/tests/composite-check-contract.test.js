const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

// story/SKILL.md is the authoritative router contract. A deployed project's
// AGENTS.md is generated/user-owned state and must not make this source test
// depend on another checkout.
const skillsRoot = path.resolve(__dirname, '..', '..');
const sourceRoot = path.dirname(skillsRoot);
const skillPath = path.resolve(__dirname, '..', 'SKILL.md');
const manifestPath = path.resolve(__dirname, '..', 'references', 'composite-check-manifest.json');
const skillSetPath = path.join(sourceRoot, 'scripts', 'platform-skill-set.json');

const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
const skill = fs.readFileSync(skillPath, 'utf8');

function allItems() {
  return manifest.stages.flatMap((stage) => stage.filters);
}

function requiredIds() {
  return allItems().filter((item) => item.required).map((item) => item.id);
}

function coverageComplete(records) {
  const required = new Set(requiredIds());
  const seen = new Set();
  for (const record of records) {
    if (!required.has(record.id) || seen.has(record.id)) return false;
    if (!manifest.status.includes(record.status)) return false;
    if (record.status === 'SKIPPED' && !/^not applicable:/i.test(String(record.reason || '').trim())) return false;
    if (record.status === 'BLOCKED') return false;
    seen.add(record.id);
  }
  return seen.size === required.size;
}

function sourcePath(executor) {
  return String(executor).split('#', 1)[0];
}

function skillBundlePath(relative) {
  const normalized = sourcePath(relative).replaceAll('\\', '/');
  const insideSkills = normalized.startsWith('skills/') ? normalized.slice('skills/'.length) : normalized;
  return path.join(skillsRoot, ...insideSkills.split('/'));
}

function publishedSkills() {
  if (fs.existsSync(skillSetPath)) {
    return new Set(JSON.parse(fs.readFileSync(skillSetPath, 'utf8')).skills);
  }
  return new Set(
    fs.readdirSync(skillsRoot, {withFileTypes: true})
      .filter((entry) => entry.isDirectory() && fs.existsSync(path.join(skillsRoot, entry.name, 'SKILL.md')))
      .map((entry) => entry.name),
  );
}

test('generic novel check requires all eight stages and the manifest contract', () => {
  const expectedStages = [
    ['review', 'story-review'],
    ['ai-flavor', 'ai-flavor-scan'],
    ['novel-deslop', 'story-deslop'],
    ['dialogue-naturalness', 'dialogue-naturalness-scan'],
    ['jargon-verb', 'jargon-verb-scan'],
    ['legal-domain-veracity', 'legal-domain-veracity-scan'],
    ['general-deslop', 'story-deslop'],
    ['humanizer', 'humanizer'],
  ];

  assert.equal(manifest.stages.length, 8);
  assert.deepEqual(manifest.skipPolicy, {allowedOnlyWhen: 'not-applicable', requiresReason: true});
  assert.deepEqual(
    manifest.stages.map((stage) => [stage.id, stage.route]),
    expectedStages,
  );
  assert.deepEqual(manifest.stages.map((stage) => stage.order), [1, 2, 3, 4, 5, 6, 7, 8]);
  assert.equal(new Set(allItems().map((item) => item.id)).size, allItems().length);
  assert.ok(allItems().length >= 90, 'manifest must enumerate internal checks, not only seven routes');

  for (const item of allItems()) {
    assert.equal(typeof item.id, 'string');
    assert.equal(typeof item.label, 'string');
    assert.equal(typeof item.executor, 'string');
    assert.equal(typeof item.scope, 'string');
    assert.equal(item.required, true);
    assert.equal(typeof item.report, 'string');
    assert.ok(fs.existsSync(skillBundlePath(item.executor)), `missing executor: ${item.executor}`);
  }

  assert.match(skill, /composite-check-manifest\.json/);
  assert.match(skill, /ai-flavor-scan.*正文十层/s);
  assert.match(skill, /每个必检项都有状态/);
  assert.match(skill, /复合检查完成：8\/8，过滤项 M\/M/);
  assert.match(skill, /不得静默跳过/);
});

test('AI flavor manifest preserves all ten layers and five semantic mismatch checks', () => {
  const stage = manifest.stages.find((item) => item.id === 'ai-flavor');
  const ids = new Set(stage.filters.map((item) => item.id));
  for (const id of [
    'ai-01-banned-words',
    'ai-02-rhetoric-library',
    'ai-03-fused-metaphor',
    'ai-04-empty-summary',
    'ai-04e-narration-slogan',
    'ai-05-jargon-single-character',
    'ai-06-coined-collocation',
    'ai-07-telegraphic-writing',
    'ai-08a-physical-attribute',
    'ai-08b-force-result',
    'ai-08c-object-feeling',
    'ai-08d-abstract-object',
    'ai-08e-state-ownership',
    'ai-09-persona-cliche',
    'ai-10-chapter-title',
  ]) {
    assert.ok(ids.has(id), `missing AI flavor filter: ${id}`);
  }
});

test('every composite-check dependency is in the installable public skill set', () => {
  const published = publishedSkills();
  const dependencies = new Set(manifest.stages.flatMap((stage) => stage.dependencies));

  for (const dependency of dependencies) {
    assert.ok(published.has(dependency), `unpublished composite-check dependency: ${dependency}`);
    assert.ok(
      fs.existsSync(path.join(skillsRoot, dependency, 'SKILL.md')),
      `published composite-check dependency is missing SKILL.md: ${dependency}`,
    );
  }
});

test('story-deslop file-mode pollution dependency is publicly installable and counted', () => {
  const published = publishedSkills();
  const deslop = fs.readFileSync(path.join(skillsRoot, 'story-deslop', 'SKILL.md'), 'utf8');
  const novelStage = manifest.stages.find((stage) => stage.id === 'novel-deslop');
  assert.match(deslop, /调用 `batch-pollution-detector` Skill/);
  assert.ok(published.has('batch-pollution-detector'));
  assert.ok(fs.existsSync(path.join(skillsRoot, 'batch-pollution-detector', 'SKILL.md')));
  assert.ok(novelStage.dependencies.includes('batch-pollution-detector'));
  assert.ok(novelStage.filters.some((item) => item.id === 'deslop-pollution-duplicates'));
  assert.ok(novelStage.filters.some((item) => item.id === 'deslop-pollution-balance'));
});

test('a finding does not stop later filters, but a missing or blocked item cannot complete', () => {
  const ids = requiredIds();
  const recordsWithFinding = ids.map((id, index) => ({
    id,
    status: index === 0 ? 'FAIL' : 'PASS',
    scope: 'fixture',
    findings: index === 0 ? 1 : 0,
  }));
  assert.equal(coverageComplete(recordsWithFinding), true);
  assert.equal(coverageComplete(recordsWithFinding.slice(1)), false);
  assert.equal(
    coverageComplete(recordsWithFinding.map((record, index) => index === 1 ? {...record, status: 'BLOCKED'} : record)),
    false,
  );
});

test('skip requires a reason and trigger precedence keeps version checks separate', () => {
  const ids = requiredIds();
  const records = ids.map((id) => ({id, status: 'PASS', scope: 'fixture', findings: 0}));
  records[0] = {...records[0], status: 'SKIPPED'};
  assert.equal(coverageComplete(records), false);
  records[0].reason = 'not applicable: no multi-batch state';
  assert.equal(coverageComplete(records), true);

  assert.ok(manifest.triggers.full.includes('检查'));
  assert.ok(manifest.triggers.explicitSingleItem.includes('检查 AI 味'));
  assert.ok(manifest.triggers.excludedVersionCheck.includes('检查更新'));
  assert.ok(!manifest.triggers.full.includes('检查更新'));
});

test('runtime hooks use the unified story-write entry and expose the post-event route', () => {
  const runtimeFiles = [
    'skills/story-setup/references/templates/hooks/story_hook_cli.js',
    'skills/story-setup/references/templates/hooks/story_hook_core.js',
    'skills/story-setup/references/templates/hooks/guard-outline-before-prose.sh',
    'skills/story-setup/references/codex/hooks/story_codex_hook.py',
  ];
  for (const relative of runtimeFiles) {
    const text = fs.readFileSync(skillBundlePath(relative), 'utf8');
    assert.doesNotMatch(text, /story-(?:long|short)-write/);
  }
  assert.match(fs.readFileSync(skillBundlePath(runtimeFiles[0]), 'utf8'), /prose-after-event/);
});
