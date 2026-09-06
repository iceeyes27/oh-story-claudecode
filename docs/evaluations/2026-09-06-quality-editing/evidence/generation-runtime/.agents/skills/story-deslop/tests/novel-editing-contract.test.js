const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const skillsRoot = path.resolve(__dirname, '..', '..');
const read = (relative) => fs.readFileSync(path.join(skillsRoot, relative), 'utf8');
const deslop = read('story-deslop/SKILL.md');
const novel = deslop.split('## 小说去 AI 味模式（mode = novel）')[1]
  .split('## 通用说人话模式（mode = general）')[0];
const review = read('story-review/SKILL.md');
const generic = read('story-review/references/quality-rubric.md');
const checklist = read('story-review/references/review-quality.md');
const shared = read('_shared/references/anti-ai-writing.md');
const prosePolicy = read('story-write/references/prose-policy.md');
const platforms = ['fanqie', 'qidian', 'zhihu'].map((name) =>
  read(`story-review/references/rubrics/${name}.md`));

// Retired decision rules, not ordinary mentions of the words or symbols.
// Keep this guard scoped to the novel editing consumers: general-mode scope,
// translation and explicitly authored book rules have different contracts.
const retired = [
  /量化与主观冲突时，以量化结果为准/,
  /任一指标达重度即按重度处理/,
  /重度：完整三遍\s*\+\s*重点段落重写/,
  /正文(?:产物)?不保留\s*`……`\s*\/\s*`——`/,
  /正文（含对话）不残留\s*`……`\s*\/\s*`——`/,
  /AI 写的心理描写特征：直接陈述情绪/,
  /severity=blocking 的类别（`not-is-comparison`/,
  /每章提及或使用金手指/,
  /每段有情绪变化/,
  /(?:完读|追读|跳失)[^\n]*[<>]\s*\d+%/,
];
const retiredHits = (text) => retired.filter((rule) => rule.test(text));

test('novel editor and all reviewer entry points reject retired global policies', () => {
  for (const [name, text] of Object.entries({ novel, review, generic, checklist, shared, ...platforms })) {
    assert.deepEqual(retiredHits(text), [], `${name} reintroduced a global rewrite rule`);
  }
});

test('the consumer guard detects representative old rules instead of silently passing', () => {
  for (const fixture of [
    '量化与主观冲突时，以量化结果为准',
    '任一指标达重度即按重度处理；重度：完整三遍 + 重点段落重写',
    '正文产物不保留 `……` / `——`',
    'AI 写的心理描写特征：直接陈述情绪',
    'severity=blocking 的类别（`not-is-comparison` / `em-dash`）',
    '| 金手指使用 | 每章提及或使用金手指 |',
    '| 完读率预估 | 预估完读 >40% |',
  ]) {
    assert(retiredHits(fixture).length > 0, `guard missed mutation: ${fixture}`);
  }
});

test('ordinary editing preserves context and stops after a bounded reading-driven pass', () => {
  assert.match(novel, /首轮只选 1～2 个最高阅读损失/);
  assert.match(novel, /普通编辑是一轮局部修订加一轮回读/);
  assert.match(novel, /本轮目标已解决即停止/);
  assert.match(novel, /恢复该处原文/);
  assert.match(novel, /实际输出的 `severity`、来源、作用域/);
  assert.match(novel, /作者明确禁令遵守已验证的来源与作用域/);
  assert.match(novel, /规则加载失败先排查规则输入/);
  assert.match(novel, /normalize-punctuation\.js --check/);
  assert.match(novel, /只检测请求只做 Phase 1–2，不修改/);
  assert.match(novel, /必要心理可直写|直写情绪不是默认缺陷/);
  assert.match(shared, /普通编辑首轮只处理 1～2 个最高阅读损失/);
  assert.match(shared, /研究 P0\/P1 继续服从冻结协议与不可变边界/);
  assert.match(prosePolicy, /普通编辑的 `PRESERVED_WITH_FUNCTION`[\s\S]*不为保留原句启动研究 A\/B/);
  assert.match(prosePolicy, /只有显式研究协议要求比较时[\s\S]*按冻结方案验证盲化 A\/B 不劣/);
});

test('platform and generic rubrics require applicability before judging chapter shape', () => {
  for (const text of [generic, checklist, review, ...platforms]) {
    assert.match(text, /本书承诺/);
    assert.match(text, /N\/A/);
    assert.match(text, /1～2 个最高阅读损失/);
  }
  assert.match(generic, /未发生的高潮、关系跃迁、任务卡点或伏笔操作记 `N\/A`/);
  assert.match(review, /所有模式先读取 `story-review\/references\/quality-rubric\.md`/);
  assert.match(review, /不重建固定比例或风格禁令/);
});
