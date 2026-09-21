#!/usr/bin/env node
'use strict';

// Behavioral contracts for rule authority, ordinary prose, and external candidates.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const root = path.resolve(__dirname, '..');
const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'story-rule-scope-'));
const source = path.join(root, 'skills/_shared');
const shared = path.join(temp, 'shared');
fs.mkdirSync(path.join(shared, 'scripts'), { recursive: true });
fs.mkdirSync(path.join(shared, 'references'), { recursive: true });
const script = path.join(shared, 'scripts/check-ai-patterns.js');
const rules = path.join(shared, 'references/banned-words.md');
fs.copyFileSync(path.join(source, 'scripts/check-ai-patterns.js'), script);
const canonical = fs.readFileSync(path.join(source, 'references/banned-words.md'), 'utf8');
fs.writeFileSync(rules, canonical);
const chapter = path.join(temp, 'chapter.md');
let count = 0;
function scan(text, args = [], file = chapter) {
  fs.writeFileSync(file, text);
  const result = spawnSync(process.execPath, [script, '--json', '--fail-on=blocking', ...args, file], { cwd: temp, encoding: 'utf8' });
  assert.equal(result.error, undefined);
  assert.ok(result.stdout, result.stderr);
  return { status: result.status, findings: JSON.parse(result.stdout).findings };
}
function test(name, fn) { fn(); count++; process.stdout.write(`PASS ${name}\n`); }
function blocked(result, type) {
  assert.notEqual(result.status, 0);
  assert.ok(result.findings.some(x => x.type === type && x.severity === 'blocking'), JSON.stringify(result));
}
function machineData(change) {
  const match = canonical.match(/```story-rules\r?\n([\s\S]*?)\r?\n```/);
  const data = JSON.parse(match[1]);
  change(data);
  fs.writeFileSync(rules, canonical.replace(match[1], JSON.stringify(data)));
}
try {
  test('ordinary literal actions, temperature, smell, cleaning, and time have no findings', () => {
    for (const text of ['再等几分钟，水就开了。','她拦了一下，让孩子别碰断线。','车轮轻轻一颠，跨过门槛。','菜有淡淡的咸味。','冰冷的鱼。','风一吹，门就关上了。','屋里飘着一股腥味。','洗掉了地上的痕迹。','他把木板的棱角磨平了。','他心里发虚。']) {
      assert.deepEqual(scan(text), { status: 0, findings: [] }, text);
    }
  });
  test('isolated contextual patterns retain evidence, not automatic rejection', () => {
    for (const [text, type] of [
      ['他心头一震，眼中闪过悲伤。', 'banned-word-exact'],
      ['岁月把记忆冲走了。', 'banned-word-physical-clear'],
      ['他像没了骨架，只剩一层皮撑着。', 'banned-word-body-shell'],
      ['醒来的，成了他。', 'banned-word-dangling-identity'],
    ]) {
      const result = scan(text);
      assert.equal(result.status, 0, text);
      assert.ok(result.findings.some(x => x.type === type && x.category === 'contextual' && x.source), text);
    }
  });
  test('all four weak adverbs contribute to density while isolated use is safe', () => {
    for (const term of ['缓缓', '微微', '轻轻', '淡淡']) {
      const result = scan((`她${term}地念完纸上的字。\n`).repeat(9));
      assert.equal(result.status, 0);
      assert.ok(result.findings.some(x => x.type === 'cliche-density-tic' && x.category === 'density'), term);
      assert.ok(!result.findings.some(x => x.type === 'banned-word-exact'), term);
    }
  });
  test('repeated micro actions still identify a review window', () => {
    const result = scan('他转了下头，摸了下口袋，拍了下衣角，歪了下脖子，侧了下身，蹭了下鞋底。');
    assert.equal(result.status, 0);
    assert.ok(result.findings.some(x => x.type === 'micro-action-tic'));
  });
  test('quoted count mismatch blocks and matched count passes', () => {
    blocked(scan('“没钱。”这三个字把她拦住了。'), 'referential-count-mismatch');
    assert.equal(scan('“没钱。”这两个字把她拦住了。').status, 0);
    assert.equal(scan('“回来”，她想起早年的三个字。\n这两个字另有含义。').status, 0);
  });
  test('prose explanations and parenthetical examples are never parsed as tokens', () => {
    fs.writeFileSync(rules, canonical.replace('## 共享词形提示', '说明：新增的假词条（作者举例）、院子门口\n\n## 共享词形提示'));
    assert.deepEqual(scan('院子门口有泥。新增的假词条。'), { status: 0, findings: [] });
  });
  test('explicit malformed literal field fails rather than parsing parentheses', () => {
    machineData(x => x.contextual.push('淡淡（每千字三次）'));
    blocked(scan('屋里有人。'), 'rule-load-error');
  });
  test('missing, duplicate, invalid, and unsupported rule data fail closed', () => {
    for (const change of [x => x.schema_version = 99, x => x.contextual = [], x => x.density_patterns.push('('), x => x.density_patterns.push('a*')]) {
      machineData(change); blocked(scan('屋里有人。'), 'rule-load-error');
    }
    fs.writeFileSync(rules, canonical.replace('```story-rules', '```json'));
    blocked(scan('屋里有人。'), 'rule-load-error');
    fs.writeFileSync(rules, canonical + '\n```story-rules\n{}\n```\n');
    blocked(scan('屋里有人。'), 'rule-load-error');
    fs.unlinkSync(rules);
    blocked(scan('屋里有人。'), 'rule-load-error');
    fs.writeFileSync(rules, Buffer.concat([Buffer.from(canonical), Buffer.from([0xff])]));
    blocked(scan('屋里有人。'), 'rule-load-error');
  });
  test('invalid or unterminated regex fences fail instead of silently skipping', () => {
    for (const content of [canonical.replace('/认活路/', '/(/'), canonical.replace('/认活路/', '说明不是正则'), canonical.replace('```story-regex', '```story-regex\n/a*/')]) {
      fs.writeFileSync(rules, content); blocked(scan('屋里有人。'), 'rule-load-error');
    }
  });
  fs.writeFileSync(rules, canonical);
  const book = path.join(temp, 'book');
  const body = path.join(book, '正文');
  fs.mkdirSync(body, { recursive: true });
  const bookChapter = path.join(body, 'chapter.md');
  const preferences = path.join(book, '创作偏好.md');
  fs.writeFileSync(preferences, '# 作者要求\n本书叙述禁用“冰冷”。\n');
  const registry = path.join(book, '.deslop-author-rules.json');
  const authorRule = { id: 'author-ice', category: 'author', source: { path: '创作偏好.md', quote: '本书叙述禁用“冰冷”。' }, scope: { path: '.', surface: 'narration' }, match: { kind: 'literal', value: '冰冷' } };
  function register(edit = () => {}) {
    const rule = JSON.parse(JSON.stringify(authorRule)); edit(rule);
    fs.writeFileSync(registry, JSON.stringify({ schema_version: 1, rules: [rule] }));
  }
  test('author rule inherits from book, reports source, and respects narration surface', () => {
    register();
    const result = scan('冰冷的鱼。', [], bookChapter);
    blocked(result, 'author-ban');
    const finding = result.findings.find(x => x.type === 'author-ban');
    assert.equal(finding.category, 'author');
    assert.equal(finding.source.quote, authorRule.source.quote);
    assert.equal(finding.scope.path, fs.realpathSync(book));
    assert.equal(scan('“冰冷的鱼。”', [], bookChapter).status, 0);
    register(x => x.scope.surface = 'all');
    blocked(scan('“冰冷的鱼。”', [], bookChapter), 'author-ban');
  });
  test('author bans do not leak across books and cannot be waived by shared whitelist', () => {
    register();
    fs.writeFileSync(path.join(temp, '.deslop-whitelist'), '冰冷\n');
    blocked(scan('冰冷的鱼。', [], bookChapter), 'author-ban');
    assert.equal(scan('冰冷的鱼。').status, 0);
  });
  test('external candidate uses explicit book and planned chapter scope', () => {
    register(); blocked(scan('冰冷的鱼。', ['--book-dir', book]), 'author-ban');
    register(x => x.scope.path = '正文');
    blocked(scan('冰冷的鱼。', ['--book-dir', book]), 'rule-load-error');
    blocked(scan('冰冷的鱼。', ['--book-dir', book, '--target-file', path.join(body, 'new.md')]), 'author-ban');
    const outsideScope = path.join(book, '资料'); fs.mkdirSync(outsideScope);
    assert.equal(scan('冰冷的鱼。', ['--book-dir', book, '--target-file', path.join(outsideScope, 'new.md')]).status, 0);
    blocked(scan('冰冷的鱼。', ['--book-dir', book, '--target-file', chapter]), 'rule-load-error');
  });
  test('source mismatch, missing scope, wrong category, and path escape fail closed', () => {
    for (const edit of [x => x.source.quote = '作者从未说过的话', x => delete x.scope, x => x.category = 'system', x => x.source.path = '../chapter.md', x => x.scope.path = '..']) {
      register(edit); blocked(scan('屋里有人。', [], bookChapter), 'rule-load-error');
    }
    register(); fs.writeFileSync(registry, '{broken'); blocked(scan('屋里有人。', [], bookChapter), 'rule-load-error');
  });
  test('symlink escape in planned target and registry cannot broaden author authority', () => {
    register(); fs.symlinkSync(temp, path.join(book, 'outside'));
    blocked(scan('屋里有人。', ['--book-dir', book, '--target-file', path.join(book, 'outside/new.md')]), 'rule-load-error');
    fs.unlinkSync(registry); fs.symlinkSync(chapter, registry);
    blocked(scan('屋里有人。', [], bookChapter), 'rule-load-error');
  });
  test('unreadable input and broken UTF-8 return a machine-readable blocking error', () => {
    blocked(scan(Buffer.from([0xff, 0xfe])), 'input-read-error');
    const result = spawnSync(process.execPath, [script, '--json', path.join(temp, 'absent.md')], { encoding: 'utf8' });
    assert.equal(result.status, 2);
    assert.equal(JSON.parse(result.stdout).findings[0].type, 'input-read-error');
  });
  process.stdout.write(`${count} rule classification and scope tests passed.\n`);
} finally { fs.rmSync(temp, { recursive: true, force: true }); }
