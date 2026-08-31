'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const test = require('node:test');

const ROOT = path.resolve(__dirname, '..');
const CHECKER = path.join(ROOT, 'skills/_shared/scripts/check-chapter-titles.js');

function writeChapter(root, chapter, title) {
  const filename = `第${String(chapter).padStart(3, '0')}章_${title}.md`;
  fs.writeFileSync(path.join(root, filename), `# ${title}\n\n正文。\n`, 'utf8');
}

function scan(prose, profile = 'fanqie') {
  const result = spawnSync(process.execPath, [CHECKER, '--dir', prose, '--profile', profile, '--json'], {
    encoding: 'utf8',
  });
  assert.equal(result.status, 0, result.stderr || result.stdout);
  return JSON.parse(result.stdout);
}

test('question titles distinguish market questions from slogan questions by profile', () => {
  const prose = fs.mkdtempSync(path.join(os.tmpdir(), 'chapter-titles-'));
  try {
    writeChapter(prose, 1, '要签吗');
    writeChapter(prose, 20, '这水有多白');
    writeChapter(prose, 40, '改不改？');
    writeChapter(prose, 60, '谁签字');
    writeChapter(prose, 80, '红手印');
    writeChapter(prose, 100, '你也配？');
    writeChapter(prose, 120, '谁敢拦我？');
    writeChapter(prose, 140, '谁偷走了谁的心');
    writeChapter(prose, 160, '谁拿了谁的钱');
    writeChapter(prose, 180, '谁知道谁能力最强');
    writeChapter(prose, 200, '谁知道谁有奖学金');
    writeChapter(prose, 220, '谁知道谁能拿第一');
    writeChapter(prose, 240, '谁来判断谁敢说真话');

    const report = scan(prose);
    const questions = report.findings.filter((finding) => finding.rule === '设问/疑问标题');
    const findingsFor = (title) => questions.filter((finding) => finding.title === title);
    const allFindingsFor = (title) => report.findings.filter((finding) => finding.title === title);

    for (const title of ['要签吗', '改不改？']) assert.ok(findingsFor(title).every((finding) => finding.severity === 'advisory'));
    assert.ok(findingsFor('这水有多白').some((finding) => finding.severity === 'blocking'));
    assert.deepEqual(
      findingsFor('谁签字').map((finding) => finding.severity),
      ['advisory'],
    );
    assert.deepEqual(findingsFor('红手印'), []);
    for (const title of ['你也配？', '谁敢拦我？']) {
      assert.ok(findingsFor(title).some((finding) => finding.severity === 'blocking'));
    }
    for (const title of ['谁偷走了谁的心', '谁拿了谁的钱', '谁知道谁能力最强', '谁知道谁有奖学金', '谁知道谁能拿第一', '谁来判断谁敢说真话']) {
      assert.ok(allFindingsFor(title).some((finding) => finding.severity === 'advisory'));
      assert.ok(allFindingsFor(title).every((finding) => finding.severity !== 'blocking'));
    }

    const terse = scan(prose, 'terse');
    for (const title of ['要签吗', '这水有多白', '改不改？']) {
      assert.ok(terse.findings.some((finding) => finding.title === title && finding.severity === 'blocking'));
    }
  } finally {
    fs.rmSync(prose, { recursive: true, force: true });
  }
});

test('fanqie relaxes length and common role overlap but terse keeps the legacy gate', () => {
  const prose = fs.mkdtempSync(path.join(os.tmpdir(), 'chapter-title-profile-'));
  try {
    writeChapter(prose, 1, '军报记者来采访了！');
    writeChapter(prose, 2, '和钟记者多联系就是工作');
    const fanqie = scan(prose);
    assert.equal(fanqie.findings.filter((finding) => finding.severity === 'blocking').length, 0);
    assert.ok(fanqie.findings.some((finding) => finding.rule === '标题过长' && finding.severity === 'advisory'));
    assert.ok(fanqie.findings.some((finding) => finding.rule === '相邻章节核心词撞车' && finding.severity === 'advisory'));

    const terse = scan(prose, 'terse');
    assert.ok(terse.findings.filter((finding) => finding.severity === 'blocking').length >= 3);
  } finally {
    fs.rmSync(prose, {recursive: true, force: true});
  }
});

test('AI summary clauses and exact repeats remain blocking in every profile', () => {
  const prose = fs.mkdtempSync(path.join(os.tmpdir(), 'chapter-title-pathology-'));
  try {
    writeChapter(prose, 1, '刚出事就递来的笔');
    writeChapter(prose, 5, '红手印');
    writeChapter(prose, 6, '红手印');
    writeChapter(prose, 20, '那行无需重点巡视是谁划掉的');
    writeChapter(prose, 30, '谁设考核谁可停单');
    writeChapter(prose, 40, '谁抓现行谁有奖');
    writeChapter(prose, 50, '谁设规则谁可改');
    writeChapter(prose, 60, '谁设权限谁有权查');
    writeChapter(prose, 70, '谁抓现行谁有奖？');
    for (const profile of ['fanqie', 'terse']) {
      const report = scan(prose, profile);
      for (const title of ['刚出事就递来的笔', '红手印', '那行无需重点巡视是谁划掉的', '谁设考核谁可停单', '谁抓现行谁有奖', '谁设规则谁可改', '谁设权限谁有权查', '谁抓现行谁有奖？']) {
        assert.ok(report.findings.some((finding) => finding.title === title && finding.severity === 'blocking'), `${profile}: ${title}`);
      }
    }
  } finally {
    fs.rmSync(prose, {recursive: true, force: true});
  }
});

test('demo baseline is 0 blocking in fanqie and 13 in terse', () => {
  const demo = path.join(ROOT, 'demo/长篇/让你管账号，你高燃混剪炸全网/正文');
  const fanqie = scan(demo);
  const terse = scan(demo, 'terse');
  assert.equal(fanqie.findings.filter((finding) => finding.severity === 'blocking').length, 0);
  assert.equal(terse.findings.filter((finding) => finding.severity === 'blocking').length, 13);
});
