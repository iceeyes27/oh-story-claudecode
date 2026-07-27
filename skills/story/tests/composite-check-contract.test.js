const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const skillPath = path.resolve(__dirname, '..', 'SKILL.md');
const agentsPath = path.resolve(__dirname, '..', '..', '..', '..', 'AGENTS.md');

test('generic novel check requires all four stages and separate conclusions', () => {
  const skill = fs.readFileSync(skillPath, 'utf8');
  const agents = fs.readFileSync(agentsPath, 'utf8');
  const stages = [
    '`story-review`',
    '`story-deslop`（mode=novel）',
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
  assert.match(skill, /复合检查完成：4\/4/);
  assert.match(skill, /不得静默跳过/);
  assert.match(agents, /只有四个阶段全部完成后才能报告 `复合检查完成：4\/4`/);
});
