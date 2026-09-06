const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const skillsRoot = path.resolve(__dirname, '..', '..');
const sourceRoot = path.dirname(skillsRoot);
const skillRoot = path.resolve(__dirname, '..');
const skill = fs.readFileSync(path.join(skillRoot, 'SKILL.md'), 'utf8');
const index = fs.readFileSync(path.join(skillRoot, 'references', 'general-ai-trace-index.md'), 'utf8');
const guide = fs.readFileSync(path.join(skillRoot, 'references', 'general-ai-trace-guide.md'), 'utf8');
const translation = fs.readFileSync(path.join(skillRoot, 'references', 'translation-guardrails.md'), 'utf8');
const packagePath = path.join(sourceRoot, 'package.json');
const isSourceRepository = fs.existsSync(path.join(sourceRoot, 'scripts', 'platform-skill-set.json'));

function githubSlug(heading) {
  return heading
    .trim()
    .toLowerCase()
    .replace(/[^\p{Letter}\p{Number}\s-]/gu, '')
    .replace(/\s+/g, '-')
    .replace(/-+/g, '-');
}

function getSection(markdown, startHeading, endHeading) {
  const start = markdown.indexOf(startHeading);
  const end = markdown.indexOf(endHeading, start + startHeading.length);
  assert.notEqual(start, -1, `missing section: ${startHeading}`);
  assert.notEqual(end, -1, `missing section boundary: ${endHeading}`);
  return markdown.slice(start, end);
}

test('general mode exposes one explicit route for rewrite, review, and translation', () => {
  assert.match(skill, /`rewrite`[\s\S]*`review`[\s\S]*`translation`/);
  assert.match(skill, /外文、中英混排、代码或 Markdown 本身不触发 `translation`/);
  assert.match(skill, /翻译和去 AI 味时，先翻译，再在原结构内做 `minimal \+ in-place`/);
  assert.match(skill, /references\/general-ai-trace-index\.md/);
  assert.match(skill, /references\/general-ai-trace-guide\.md/);
  assert.match(skill, /references\/translation-guardrails\.md/);
});

test('general route boundaries stay consistent and load only task-relevant references', () => {
  const sharedRules = getSection(skill, '### 共享判断（两种模式都适用）', '---');
  const generalUsage = getSection(skill, '### When to use', '### Task routing');
  const routing = getSection(skill, '### Task routing', '### Core stance');
  const rewriteRow = routing.split('\n').find((line) => line.startsWith('| `rewrite`'));
  const reviewRow = routing.split('\n').find((line) => line.startsWith('| `review`'));
  const translationRow = routing.split('\n').find((line) => line.startsWith('| `translation`'));

  assert.match(sharedRules, /明确要求翻译其中的自然语言说明/);
  assert.match(generalUsage, /仅当用户明确要求翻译其中的自然语言说明时进入 `translation`/);
  assert.match(rewriteRow, /general-ai-trace-index\.md/);
  assert.doesNotMatch(rewriteRow, /general-ai-trace-guide\.md/);
  assert.match(reviewRow, /general-ai-trace-index\.md/);
  assert.match(reviewRow, /general-ai-trace-guide\.md/);
  assert.ok(reviewRow.indexOf('general-ai-trace-index.md') < reviewRow.indexOf('general-ai-trace-guide.md'));
  assert.match(translationRow, /translation-guardrails\.md/);
  assert.doesNotMatch(translationRow, /general-ai-trace-(?:index|guide)\.md/);
});

test('review is ranked and contextual instead of a mandatory-clear scanner', () => {
  assert.match(index, /advisory/);
  assert.match(index, /不要求把所有命中项清零/);
  assert.match(index, /Top 5-10/);
  assert.match(guide, /问题族的出现不等于必须修改，更不要求清零/);
  assert.match(guide, /一次出现通常只算线索/);
  assert.match(skill, /`review` 只报告最重要的 Top 5-10 个问题/);
});

test('every guide fragment in the index resolves to an actual heading', () => {
  const headingSlugs = new Set(
    [...guide.matchAll(/^#{1,6}\s+(.+)$/gm)].map((match) => githubSlug(match[1])),
  );
  const fragments = [...index.matchAll(/general-ai-trace-guide\.md#([^)]+)/g)]
    .map((match) => decodeURIComponent(match[1]));

  assert.ok(fragments.length >= 10, 'index should route every documented problem family');
  for (const fragment of fragments) {
    assert.ok(headingSlugs.has(fragment), `unresolved guide fragment: ${fragment}`);
  }
});

test('translation preserves protected values, information, and document structure', () => {
  for (const contract of [
    /链接文字，但链接目标必须保持精确/,
    /表格列数、分隔行、行顺序和单元格对应关系/,
    /否定、条件、例外、因果、时态和可能性强弱/,
    /责任主体、动作主体、来源归属和引用关系/,
    /信息守恒回读/,
    /结构回读/,
    /只输出目标语言文本/,
  ]) {
    assert.match(translation, contract);
  }
});

test('novel mode and shared scanner contracts remain present', () => {
  assert.match(skill, /## 小说去 AI 味模式（mode = novel）/);
  assert.match(skill, /\.\.\/_shared\/references\/banned-words\.md/);
  assert.match(skill, /\.\.\/_shared\/scripts\/check-ai-patterns\.js/);
  assert.match(skill, /7 Gate/);
});

test('the repository contract suite includes the general-mode test', {
  skip: !isSourceRepository && 'source repository metadata is not installed with Skills',
}, () => {
  const packageJson = JSON.parse(fs.readFileSync(packagePath, 'utf8'));
  assert.match(
    packageJson.scripts['test:contracts'],
    /skills\/story-deslop\/tests\/general-mode-contract\.test\.js/,
  );
  assert.match(
    packageJson.scripts['test:contracts'],
    /skills\/story\/tests\/composite-check-contract\.test\.js/,
  );
});
