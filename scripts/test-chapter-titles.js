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

test('question titles distinguish blocking forms from advisory suspense', () => {
  const prose = fs.mkdtempSync(path.join(os.tmpdir(), 'chapter-titles-'));
  try {
    writeChapter(prose, 1, '要签吗');
    writeChapter(prose, 20, '这水有多白');
    writeChapter(prose, 40, '改不改？');
    writeChapter(prose, 60, '谁签字');
    writeChapter(prose, 80, '红手印');

    const result = spawnSync(process.execPath, [CHECKER, '--dir', prose, '--json'], {
      encoding: 'utf8',
    });
    assert.equal(result.status, 0, result.stderr || result.stdout);

    const report = JSON.parse(result.stdout);
    const questions = report.findings.filter((finding) => finding.rule === '设问/疑问标题');
    const findingsFor = (title) => questions.filter((finding) => finding.title === title);

    for (const title of ['要签吗', '这水有多白', '改不改？']) {
      assert.ok(
        findingsFor(title).some((finding) => finding.severity === 'blocking'),
        `${title} should be blocking`,
      );
    }
    assert.deepEqual(
      findingsFor('谁签字').map((finding) => finding.severity),
      ['advisory'],
    );
    assert.deepEqual(findingsFor('红手印'), []);
  } finally {
    fs.rmSync(prose, { recursive: true, force: true });
  }
});
