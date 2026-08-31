const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const skillsRoot = path.resolve(__dirname, '..', '..');
const deslop = fs.readFileSync(path.join(__dirname, '..', 'SKILL.md'), 'utf8');
const longMode = fs.readFileSync(path.join(skillsRoot, 'story-write', 'references', 'long-mode.md'), 'utf8');
const dialogue = fs.readFileSync(path.join(skillsRoot, 'story-write', 'references', 'dialogue-mastery.md'), 'utf8');
const antiAi = fs.readFileSync(path.join(skillsRoot, '_shared', 'references', 'anti-ai-writing.md'), 'utf8');

test('first necessary explanation is preserved before deletion gates', () => {
  assert.match(deslop, /首次说明人物动机、关系、能力来历或事件因果[\s\S]*不得删除/);
  assert.match(deslop, /前文已有的重复总结才删/);
  assert.match(longMode, /首次交代：删除前先查[\s\S]*重复解释才可删/);
  assert.match(antiAi, /首次交代闸[\s\S]*不算解释腔[\s\S]*重复说明才可删/);
});

test('dialogue keeps causal information while rejecting exposition monologues', () => {
  assert.match(dialogue, /禁止无压力的整段科普独白/);
  assert.match(dialogue, /首次且推动当前冲突的必要因果必须保留/);
  assert.match(dialogue, /不能只留空白让读者猜/);
});
