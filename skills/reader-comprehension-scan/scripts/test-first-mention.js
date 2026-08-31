#!/usr/bin/env node
/**
 * test-first-mention.js — check-first-mention.js 回归测试（node 原生 assert）
 * 用法: node test-first-mention.js
 */
'use strict';
const assert = require('node:assert/strict');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { execFileSync } = require('node:child_process');

const SCRIPT = path.resolve(__dirname, '..', '..', '_shared', 'scripts', 'check-first-mention.js');
const { analyze, hasAnchor } = require(SCRIPT);

function makeBook(chapters) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'fm-'));
  const textDir = path.join(dir, '正文');
  fs.mkdirSync(textDir);
  for (const c of chapters) {
    const fn = `第${String(c.num).padStart(3, '0')}章_${c.title || '测'}.md`;
    fs.writeFileSync(path.join(textDir, fn), c.body, 'utf8');
  }
  return dir;
}

function chapterObjs(dir) {
  const { collectChapters, resolveTextDir } = require(SCRIPT);
  return collectChapters(resolveTextDir(dir));
}

let pass = 0;
function ok(name, fn) {
  try { fn(); console.log(`  [PASS] ${name}`); pass++; }
  catch (e) { console.error(`  [FAIL] ${name}\n         ${e.message}`); process.exitCode = 1; }
}

// 1) 首现有交代 → 不报
ok('首现有身份交代不报', () => {
  const dir = makeBook([
    { num: 1, body: '周薄森是文工团的副团长。\n江晨向周薄森报到。\n周薄森点点头。\n周薄森安排了任务。' },
    { num: 2, body: '江晨又去找周薄森。\n周薄森不在。\n周薄森的办公室空着。' },
  ]);
  const findings = analyze(chapterObjs(dir));
  const hit = findings.find((f) => f.token === '周薄森');
  assert.equal(hit, undefined, '周薄森首现处有「是…副团长」应放过');
});

// 2) 首现零交代（且仅本章内出现）→ advisory
ok('首现零交代仅本章内为 advisory', () => {
  const dir = makeBook([
    { num: 1, body: '天枢阁的人来了。\n天枢阁的人走了。\n天枢阁的人又来。' },
  ]);
  const findings = analyze(chapterObjs(dir));
  const hit = findings.find((f) => f.token === '天枢阁');
  assert.ok(hit, '天枢阁应被候选');
  assert.equal(hit.severity, 'advisory', '仅首章出现应为 advisory');
});

// 3) 首现零交代 + 跨 ≥2 章再引用 → blocking
ok('首现零交代跨章回扣升 blocking', () => {
  const dir = makeBook([
    { num: 1, body: '玄冥令出现了。\n玄冥令闪着光。\n玄冥令很重要。' },
    { num: 2, body: '无关内容。\n随便写点。' },
    { num: 3, body: '他又想起玄冥令。\n玄冥令还在。' },
    { num: 4, body: '玄冥令的秘密。\n玄冥令啊玄冥令。' },
  ]);
  const findings = analyze(chapterObjs(dir));
  const hit = findings.find((f) => f.token === '玄冥令');
  assert.ok(hit, '玄冥令应被候选');
  assert.equal(hit.severity, 'blocking', '首现零交代且第3/4章回扣应 blocking');
});

// 4) 书名号实体首现零交代也进候选（不需达频率阈值）
ok('书名号实体低频也进候选', () => {
  const dir = makeBook([
    { num: 1, body: '他放起了《幽灵进行曲》。\n很好听。' },
  ]);
  const findings = analyze(chapterObjs(dir));
  const hit = findings.find((f) => f.token === '幽灵进行曲');
  assert.ok(hit, '书名号实体应进候选，即使只出现一次');
});

// 5) 退出码：正常样例（有交代）blocking=0 → exit 0
ok('CLI 正常样例退出码 0', () => {
  const dir = makeBook([
    { num: 1, body: '周薄森是副团长。\n江晨报到。\n周薄森安排工作。' },
  ]);
  const out = execFileSync('node', [SCRIPT, dir, '--json'], { encoding: 'utf8' });
  const res = JSON.parse(out);
  assert.equal(res.blocking, 0);
});

// 6) CLI blocking 样例退出码 1
ok('CLI blocking 样例退出码 1', () => {
  const dir = makeBook([
    { num: 1, body: '玄冥令出现了。\n玄冥令闪光。\n玄冥令重要。' },
    { num: 2, body: '过渡。\n过渡。' },
    { num: 3, body: '玄冥令又来。\n玄冥令还在。' },
  ]);
  let code = 0;
  try { execFileSync('node', [SCRIPT, dir], { encoding: 'utf8' }); }
  catch (e) { code = e.status; }
  assert.equal(code, 1);
});

// 7) 参数缺失退出码 2
ok('缺参数退出码 2', () => {
  let code = 0;
  try { execFileSync('node', [SCRIPT], { encoding: 'utf8', stdio: 'pipe' }); }
  catch (e) { code = e.status; }
  assert.equal(code, 2);
});

// 8) 不存在目录退出码 2
ok('不存在目录退出码 2', () => {
  let code = 0;
  try { execFileSync('node', [SCRIPT, path.join(os.tmpdir(), 'nope-' + Date.now())], { encoding: 'utf8', stdio: 'pipe' }); }
  catch (e) { code = e.status; }
  assert.equal(code, 2);
});

// 9) 量词前缀切分残留不进候选（「获得了一个系统」不得报「个系统」）
ok('量词前缀切分残留不进候选', () => {
  const dir = makeBook([
    { num: 1, body: '自己获得了一个系统？\n有了这个系统，一切都好办。\n他打开了那个系统。' },
    { num: 2, body: '过渡内容。\n随便写点。' },
    { num: 3, body: '他又想起一个系统。\n还是那个系统。' },
  ]);
  const findings = analyze(chapterObjs(dir));
  assert.equal(findings.find((f) => f.token === '个系统'), undefined, '「个系统」是量词粘连残留，不得作为候选');
});

// 10) 数词开头的真专名仍要报（不能被量词过滤误杀）
ok('数词开头的专名不被量词过滤误杀', () => {
  const dir = makeBook([
    { num: 1, body: '三清殿的钟响了。\n三清殿很安静。\n三清殿的门开着。' },
    { num: 2, body: '过渡。\n过渡。' },
    { num: 3, body: '他回到三清殿。\n三清殿依旧。' },
  ]);
  const findings = analyze(chapterObjs(dir));
  assert.ok(findings.find((f) => f.token === '三清殿'), '「三清殿」是真专名，不能被量词/数词过滤误杀');
});

// 11) 声明为现实世界已知实体后不再报
ok('已知实体清单可排除真实歌曲', () => {
  const dir = makeBook([
    { num: 1, body: '他放起了《如愿》。\n很好听。' },
    { num: 2, body: '过渡。\n过渡。' },
    { num: 3, body: '《如愿》又响起。\n还是《如愿》。' },
  ]);
  const before = analyze(chapterObjs(dir));
  assert.ok(before.find((f) => f.token === '如愿'), '未声明时应进候选');
  const after = analyze(chapterObjs(dir), { known: new Set(['如愿']) });
  assert.equal(after.find((f) => f.token === '如愿'), undefined, '声明为已知实体后不得再报');
});

// 12) 正文/_已知实体.txt 自动生效，注释与空行忽略
ok('正文/_已知实体.txt 自动生效', () => {
  const dir = makeBook([
    { num: 1, body: '他放起了《如愿》。\n很好听。' },
    { num: 2, body: '过渡。\n过渡。' },
    { num: 3, body: '《如愿》又响起。\n还是《如愿》。' },
  ]);
  fs.writeFileSync(path.join(dir, '正文', '_已知实体.txt'), '# 真实歌曲\n\n如愿\n', 'utf8');
  const out = execFileSync('node', [SCRIPT, dir, '--json'], { encoding: 'utf8' });
  const res = JSON.parse(out);
  assert.equal(res.knownEntities, 1, '注释与空行不计入实体数');
  assert.equal(res.findings.find((f) => f.token === '如愿'), undefined, '自动读取的清单应生效');
});

// hasAnchor 单元
ok('hasAnchor 识别判断句/职务/来历', () => {
  assert.ok(hasAnchor('他是团长'));
  assert.ok(hasAnchor('毕业于军艺'));
  assert.ok(hasAnchor('记者小王'));
  assert.ok(!hasAnchor('他走了过去说话'));
});

console.log(`\n共通过 ${pass} 项。`);
if (process.exitCode) { console.error('测试未全绿。'); }
else console.log('测试全绿。');
