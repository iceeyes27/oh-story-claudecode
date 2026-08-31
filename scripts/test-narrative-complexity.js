'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const ROOT = path.resolve(__dirname, '..');
const read = (relative) => fs.readFileSync(path.join(ROOT, relative), 'utf8');

test('new books default to plain narrative while legacy books remain regular', () => {
  const protocol = read('skills/story-write/references/artifact-protocols.md');
  const reference = read('skills/story-write/references/narrative-complexity.md');
  const longMode = read('skills/story-write/references/long-mode.md');
  assert.match(protocol, /叙事复杂度：平直/);
  assert.match(protocol, /标题档位：fanqie/);
  assert.match(reference, /已有项目缺少 `叙事复杂度` 字段时按 `常规`/);
  assert.match(longMode, /旧书缺字段取常规/);
});

test('plain mode writes causality directly and does not require a hidden ending', () => {
  const reference = read('skills/story-write/references/narrative-complexity.md');
  const writer = read('skills/story-setup/references/templates/agents/narrative-writer.md');
  assert.match(reference, /前因 → 选择\/动作 → 结果/);
  assert.match(reference, /章尾可以明写下一步行动/);
  assert.match(reference, /不强制卡掉关键信息/);
  assert.match(writer, /narrative_complexity=平直[\s\S]*章尾可明写下一步/);
});

test('title profile keeps pathological forms blocking in both modes', () => {
  const reference = read('skills/story-write/references/narrative-complexity.md');
  assert.match(reference, /AI 偏正摘要句、口号式设问、精确\/近似复读仍 blocking/);
  assert.match(reference, /terse.*旧严格门禁/);
});
