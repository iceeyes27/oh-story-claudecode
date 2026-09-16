#!/usr/bin/env node
'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const { spawnSync } = require('node:child_process');
const runtime = require('./longform-review.js');
const CLI = path.join(__dirname, 'review-state.js');
const WRITE = path.resolve(__dirname, '../../story-write/scripts');
function put(book, name, value) {
  const file = path.join(book, name); fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, typeof value === 'string' ? value : JSON.stringify(value)); return file;
}
function fixture(t, spans = [[1, 3], [4, 6]], last = 3) {
  const book = fs.mkdtempSync(path.join(os.tmpdir(), 'longform-unit-'));
  t.after(() => fs.rmSync(book, { recursive: true, force: true }));
  put(book, '设定/题材定位.md', '- 主对标书：无\n');
  setUnits(book, spans); setLast(book, last);
  for (let n = 1; n <= last; n++) prose(book, n);
  for (let n = 1; n <= Math.max(last + 1, ...spans.map(s => s[1])); n++) put(book, `大纲/细纲_第${n}章_测试.md`, `### 第 ${n} 章：测试\n`);
  put(book, '追踪/上下文.md', ['当前位置', '长期约束', '核心角色状态', '活跃伏笔', '近三章速记', '下一章承诺', '连贯性风险'].map(h => `## ${h}\n无\n`).join('\n'));
  return book;
}
function setUnits(book, spans) { put(book, '大纲/卷纲_第1卷.md', spans.map(([a, b], i) => `### 剧情单元 U${i + 1}\n> 作用域：单元级 U${i + 1}\n- 章节范围：第${a}-${b}章\n`).join('\n')); }
function setLast(book, last) { put(book, '追踪/_tracking-state.json', { last_committed_chapter: last }); }
function prose(book, n) { return put(book, `正文/卷一/第${n}章_测试.md`, `# 第${n}章 测试\n测试锚点${n}\n`); }
function invoke(book, command, input, flags = [], expectedStatus = 0) {
  const args = [CLI, 'longform', command, '--book', book, ...flags];
  if (input !== undefined) args.push('--input', put(book, 'input.json', input), '--expected-revision', String(runtime.readState(book)?.state_revision || 0));
  const run = spawnSync(process.execPath, args, { encoding: 'utf8', env: { ...process.env, PYTHONDONTWRITEBYTECODE: '1' } });
  assert.equal(run.status, expectedStatus, `${command}: ${run.stderr}\n${run.stdout}`);
  return run.stdout.trim() ? JSON.parse(run.stdout) : null;
}
function enable(book, start = 1) { return invoke(book, 'init', undefined, ['--start-chapter', String(start), '--author-approval', '从这里启用', '--expected-revision', '0']); }
function start(book, id = 'chapter-3', changes = {}) {
  return invoke(book, 'start', { checkpoint_id: id, reader: { id: 'reader-A', session_id: 'fresh-session', reader_type: 'model' }, independent: true,
    creative_participants: ['writer-A', 'planner-A'], reading_order: 'chronological_then_comparison', prose_only: true,
    comparison: { paths: [], reason: '第一单元或尚无足够比较证据', insufficient_evidence: true }, ...changes });
}
function deliverAll(book, run) { for (const file of [...run.required_files, ...run.comparison_files]) invoke(book, 'read', { run_id: run.run_id, path: file.path }); }
function finishInput(run, changes = {}) {
  const file = run.required_files[0];
  const evidence = [{ path: file.path, line: 2, quote: `测试锚点${file.chapter}` }];
  return { run_id: run.run_id, observations: Object.fromEntries(['understanding', 'fatigue', 'relationships', 'reward_expectation'].map(k => [k, { assessment: '未发现问题；模型观察', evidence }])), findings: [], responses: [], ...changes };
}
function flow(book, command = 'detect', patch, expected = 0) {
  const args = [path.join(WRITE, 'flow-state.js'), command, '--dir', book, '--json']; if (patch) args.push(JSON.stringify(patch));
  const run = spawnSync(process.execPath, args, { encoding: 'utf8' }); assert.equal(run.status, expected, run.stderr); return run.stdout ? JSON.parse(run.stdout) : null;
}

test('shared chapter inventory fixture excludes hidden/history/original directories', t => {
  const rows = JSON.parse(fs.readFileSync(path.join(WRITE, 'chapter-inventory-fixtures.json'))).cases;
  for (const row of rows) {
    const book = fixture(t, [[1, 3]], 0);
    for (const file of row.files) put(book, file, 'fixture');
    assert.deepEqual(runtime.chapterFiles(path.join(book, '正文')).map(f => f.chapter), row.chapters);
  }
});
test('outline variants are accepted and ambiguity is never guessed', t => {
  const book = fixture(t, [[1, 3]], 0);
  assert.equal(flow(book).next_action, 'write_chapter_skeleton');
  put(book, '大纲/细纲_第001章.md', 'duplicate');
  flow(book, 'detect', undefined, 2);
});
test('old book stays disabled and no state file is created', t => {
  const book = fixture(t);
  const gate = invoke(book, 'gate'); assert.equal(gate.status, 'not_enabled');
  assert.equal(fs.existsSync(path.join(book, '.story-review')), false);
  invoke(book, 'init', undefined, ['--new-book', '--expected-revision', '0'], 2);
  assert.equal(fs.existsSync(path.join(book, runtime.FILE)), false);
});
test('null/false/array/primitive/corrupt policy is not a missing policy', t => {
  const book = fixture(t);
  for (const raw of ['null', 'false', '0', '[]', '""', '{']) {
    put(book, runtime.FILE, raw);
    invoke(book, 'gate', undefined, [], 2);
    assert.equal(fs.readFileSync(path.join(book, runtime.FILE), 'utf8'), raw);
  }
});
test('new book initializes after unit planning, old book requires explicit start', t => {
  const book = fixture(t, [[1, 3]], 0);
  invoke(book, 'init', undefined, ['--new-book', '--expected-revision', '0']);
  assert.equal(runtime.readState(book).start_chapter, 1);
  assert.equal(runtime.gate(book).can_generate, true);
});
test('unplanned adopted gap 4-6 cannot vanish between units', t => {
  const book = fixture(t, [[1, 3], [7, 10]], 10);
  invoke(book, 'init', undefined, ['--start-chapter', '1', '--author-approval', '启用', '--expected-revision', '0'], 2);
  setUnits(book, [[1, 3], [4, 10]]); enable(book);
  setUnits(book, [[1, 3], [7, 10]]);
  invoke(book, 'gate', undefined, [], 2);
});
test('global 15 point exists inside short 11-20 unit; endpoints deduplicate full ranges', t => {
  const book = fixture(t, [[1, 10], [11, 20], [21, 30]], 30); enable(book);
  const points = runtime.gate(book).checkpoints;
  assert.deepEqual(points.map(cp => cp.chapter), [10, 15, 20, 30]);
  assert.equal(points.find(cp => cp.chapter === 15).from, 1);
  const end = points.find(cp => cp.chapter === 30);
  assert.equal(end.from, 16); assert.deepEqual(end.reasons, ['unit:U3', 'rolling15']);
});
test('mid-unit enable reads whole first ending unit without retrospective checkpoints', t => {
  const book = fixture(t, [[1, 10], [11, 20]], 20); enable(book, 17);
  const points = runtime.gate(book).checkpoints;
  assert.deepEqual(points.map(cp => cp.chapter), [20]); assert.equal(points[0].from, 11);
});
test('required missing or duplicate prose blocks even authorization', t => {
  const book = fixture(t); enable(book);
  fs.unlinkSync(path.join(book, '正文/卷一/第2章_测试.md'));
  assert.deepEqual(runtime.gate(book).checkpoints[0].missing, [2]);
  invoke(book, 'authorize', { checkpoint_id: 'chapter-3', kind: 'waive', author_approval: '豁免', reason: '测试' }, [], 2);
  prose(book, 2); put(book, '正文/第002章_重复.md', 'duplicate');
  assert.deepEqual(runtime.gate(book).checkpoints[0].duplicates, [2]);
});
test('reader independence, order, future/design exclusion and complete range enforced', t => {
  const book = fixture(t); enable(book);
  const input = { checkpoint_id: 'chapter-3', reader: { id: 'writer-A', session_id: 's', reader_type: 'model' }, independent: true, creative_participants: ['writer-A'], reading_order: 'chronological_then_comparison', prose_only: true, comparison: { reason: '无', paths: [] } };
  invoke(book, 'start', input, [], 2);
  input.reader.id = 'reader'; input.comparison.paths = ['大纲/卷纲_第1卷.md']; invoke(book, 'start', input, [], 2);
  const run = start(book);
  invoke(book, 'read', { run_id: run.run_id, path: run.required_files[1].path }, [], 2);
  invoke(book, 'finish', finishInput(run), [], 2);
  deliverAll(book, run);
  const bad = finishInput(run); bad.observations.fatigue.evidence[0].line = 999;
  invoke(book, 'finish', bad, [], 2);
  invoke(book, 'finish', finishInput(run)); assert.equal(runtime.gate(book).checkpoints[0].status, 'reviewed');
});
test('timeout/failure retains pending; failed run cannot finish', t => {
  const book = fixture(t); enable(book); const run = start(book);
  invoke(book, 'fail', { run_id: run.run_id, reason: 'reader timeout' });
  const cp = runtime.gate(book).checkpoints[0]; assert.equal(cp.status, 'pending'); assert.equal(cp.failure_reason, 'reader timeout');
  invoke(book, 'finish', finishInput(run), [], 2);
});
test('rereview of the same checkpoint must answer its prior deferred finding', t => {
  const book = fixture(t); enable(book);
  const first = start(book); deliverAll(book, first);
  const file = first.required_files[0];
  const evidence = [{ path: file.path, line: 2, quote: `测试锚点${file.chapter}` }];
  invoke(book, 'finish', finishInput(first, { findings: [{ id: 'F-same', disposition: 'next_unit', reason: '下一单元复核', evidence }] }));
  assert.deepEqual(runtime.outstanding(runtime.readState(book), 3, true), ['F-same']);

  const reread = start(book); deliverAll(book, reread);
  invoke(book, 'finish', finishInput(reread), [], 2);
  invoke(book, 'finish', finishInput(reread, { responses: [{ finding_id: 'F-same', disposition: 'retain', reason: '复读后确认保留' }] }));
  const state = runtime.readState(book);
  assert.deepEqual(runtime.outstanding(state, 4), []);
  assert.equal(state.record_history.length, 1);
  assert.equal(state.record_history[0].receipt.findings[0].id, 'F-same');
});
test('waiving a checkpoint preserves its old deferred finding for the next review', t => {
  const book = fixture(t); enable(book);
  const first = start(book); deliverAll(book, first);
  const file = first.required_files[0];
  const evidence = [{ path: file.path, line: 2, quote: `测试锚点${file.chapter}` }];
  invoke(book, 'finish', finishInput(first, { findings: [{ id: 'F-waive', disposition: 'next_unit', reason: '后续核验', evidence }] }));
  invoke(book, 'authorize', { checkpoint_id: 'chapter-3', kind: 'waive', author_approval: '只豁免本次阅读', reason: '继续写作' });
  assert.deepEqual(runtime.outstanding(runtime.readState(book), 4), ['F-waive']);

  for (let n = 4; n <= 6; n++) prose(book, n);
  setLast(book, 6);
  const next = start(book, 'chapter-6'); deliverAll(book, next);
  invoke(book, 'finish', finishInput(next), [], 2);
  invoke(book, 'finish', finishInput(next, { responses: [{ finding_id: 'F-waive', disposition: 'revise_design', reason: '已转为下一单元设计动作' }] }));
  const state = runtime.readState(book);
  assert.deepEqual(runtime.outstanding(state, 7), []);
  assert.equal(state.record_history[0].receipt.findings[0].id, 'F-waive');
});
test('reviewed prose and boundary edits become stale; version mismatch fails closed', t => {
  const book = fixture(t); enable(book); const run = start(book); deliverAll(book, run); invoke(book, 'finish', finishInput(run));
  fs.appendFileSync(path.join(book, run.required_files[0].path), 'changed');
  assert.equal(runtime.gate(book).checkpoints[0].status, 'stale');
  prose(book, 1); setUnits(book, [[1, 2], [3, 6]]);
  assert.equal(runtime.gate(book).checkpoints[0].status, 'pending');
  const state = runtime.readState(book); state.policy_version = 'unknown'; put(book, runtime.FILE, state);
  invoke(book, 'gate', undefined, [], 2);
});
test('continue preserves pending, expires at next checkpoint, waived is not reviewed', t => {
  const book = fixture(t); enable(book);
  invoke(book, 'authorize', { checkpoint_id: 'chapter-3', kind: 'continue', author_approval: '先写到6', reason: '稍后审', through_chapter: 6 });
  assert.equal(runtime.gate(book).can_generate, true); assert.equal(runtime.gate(book).can_complete, false);
  for (let n = 4; n <= 6; n++) prose(book, n); setLast(book, 6);
  assert.equal(runtime.gate(book).can_generate, false);
  invoke(book, 'authorize', { checkpoint_id: 'chapter-3', kind: 'waive', author_approval: '豁免此点', reason: '作者已选择' });
  assert.equal(runtime.gate(book).checkpoints[0].status, 'waived');
});
test('flow detect/update/read and writer enforce same pending gate, including prefilled done', t => {
  const book = fixture(t); enable(book);
  const pending = flow(book, 'detect', undefined, 1); assert.equal(pending.current_stage, 'pending_reading');
  flow(book, 'update', { execution_status: 'done' }, 2);
  invoke(book, 'authorize', { checkpoint_id: 'chapter-3', kind: 'continue', author_approval: '继续', reason: '稍后补审', through_chapter: 6 });
  put(book, '追踪/写作流程状态.json', { ...pending, current_stage: 'done', execution_status: 'done' });
  const read = flow(book, 'read'); assert.equal(read.current_stage, 'pending_reading'); assert.notEqual(read.execution_status, 'done');
  const continuation = runtime.readState(book); continuation.authorizations = []; put(book, runtime.FILE, continuation);
  const writer = spawnSync('python3', [path.join(WRITE, 'build_writer_prompt.py'), '--project', book, '--chapter', '4'], { encoding: 'utf8', env: { ...process.env, PYTHONDONTWRITEBYTECODE: '1' } });
  assert.equal(writer.status, 2); assert.match(writer.stderr, /连读写前门/);
});
test('ordinary latest and CAS remain independent; revision conflicts preserve evidence', t => {
  const book = fixture(t); put(book, '.story-review/latest.json', 'ordinary sentinel'); enable(book);
  invoke(book, 'init', undefined, ['--new-book', '--expected-revision', '0'], 2);
  assert.equal(fs.readFileSync(path.join(book, '.story-review/latest.json'), 'utf8'), 'ordinary sentinel');
  const before = fs.readFileSync(path.join(book, runtime.FILE), 'utf8');
  const input = { checkpoint_id: 'chapter-3', kind: 'waive', author_approval: '豁免', reason: '测试' };
  const run = spawnSync(process.execPath, [CLI, 'longform', 'authorize', '--book', book, '--input', put(book, 'input.json', input), '--expected-revision', '0'], { encoding: 'utf8' });
  assert.equal(run.status, 2); assert.equal(fs.readFileSync(path.join(book, runtime.FILE), 'utf8'), before);
  assert.deepEqual(fs.readdirSync(path.join(book, '.story-review')).filter(f => f.startsWith('.longform-cas')), []);
});

test('declared unwritten gap is excluded, undeclared missing and invalid gap fail', t => {
  const book = fixture(t, [[1, 3]], 3);
  fs.unlinkSync(path.join(book, '正文/卷一/第2章_测试.md'));
  const gap = { start_chapter: 2, end_chapter: 2, declared_at_chapter: 3, reason: '作者确认未写跳号' };
  put(book, '追踪/_tracking-state.json', { last_committed_chapter: 3, chapter_gaps: [gap] }); enable(book);
  const cp = runtime.gate(book).checkpoints[0];
  assert.deepEqual(cp.missing, []); assert.deepEqual(cp.inputs.map(row => row.chapter), [1, 3]);
  assert.deepEqual(cp.excluded, [{ chapter: 2, reason: gap.reason }]);
  const run = start(book); deliverAll(book, run); invoke(book, 'finish', finishInput(run));
  assert.equal(runtime.gate(book).can_complete, true);
  setLast(book, 3); assert.deepEqual(runtime.gate(book).checkpoints[0].missing, [2]);
  for (const gaps of [[{ ...gap, reason: '' }], [{ ...gap, declared_at_chapter: 4 }], [gap, gap], null]) {
    put(book, '追踪/_tracking-state.json', { last_committed_chapter: 3, chapter_gaps: gaps }); invoke(book, 'gate', undefined, [], 2);
  }
  put(book, '追踪/_tracking-state.json', { last_committed_chapter: 3, imported_through_chapter: 2, chapter_gaps: [gap] }); invoke(book, 'gate', undefined, [], 2);
  put(book, '追踪/_tracking-state.json', { last_committed_chapter: 3, chapter_gaps: [gap] }); prose(book, 2); invoke(book, 'gate', undefined, [], 2);
});
test('declared jump can bridge unit range gap but cannot hide an adopted chapter', t => {
  const book = fixture(t, [[1, 3], [7, 10]], 10);
  for (let n = 4; n <= 6; n++) fs.unlinkSync(path.join(book, `正文/卷一/第${n}章_测试.md`));
  const state = { last_committed_chapter: 10, chapter_gaps: [{ start_chapter: 4, end_chapter: 6, declared_at_chapter: 7, reason: '作者跳号' }] };
  put(book, '追踪/_tracking-state.json', state); enable(book);
  assert.equal(runtime.gate(book).checkpoints.length, 2);
  state.chapter_gaps = []; put(book, '追踪/_tracking-state.json', state); invoke(book, 'gate', undefined, [], 2);
});

test('authorized numbering gaps are excluded, not read, and cannot hide actual prose', t => {
  const book = fixture(t);
  const facts = {last_committed_chapter:3,imported_through_chapter:0,chapter_gaps:[{start_chapter:2,end_chapter:2,declared_at_chapter:3,reason:'Author-declared skipped number'}]};
  fs.unlinkSync(path.join(book,'正文/卷一/第2章_测试.md'));
  put(book,'追踪/_tracking-state.json',facts);enable(book);
  const cp=runtime.gate(book).checkpoints[0];
  assert.deepEqual(cp.missing,[]);assert.deepEqual(cp.inputs.map(x=>x.chapter),[1,3]);
  assert.deepEqual(cp.excluded,[{chapter:2,reason:'Author-declared skipped number'}]);
  const run=start(book);deliverAll(book,run);invoke(book,'finish',finishInput(run));
  assert.equal(runtime.gate(book).can_complete,true);
  prose(book,2);assert.throws(()=>runtime.gate(book),/gap conflicts/);
});

test('invalid gap cannot replace a missing adopted chapter or imported fact', t => {
  const book=fixture(t);enable(book);
  for(const gap of [
    {start_chapter:2,end_chapter:2,declared_at_chapter:3,reason:''},
    {start_chapter:2,end_chapter:2,declared_at_chapter:2,reason:'bad declaration'},
  ]) {
    put(book,'追踪/_tracking-state.json',{last_committed_chapter:3,chapter_gaps:[gap]});
    invoke(book,'gate',undefined,[],2);
  }
  put(book,'追踪/_tracking-state.json',{last_committed_chapter:3,imported_through_chapter:2,chapter_gaps:[{start_chapter:2,end_chapter:2,declared_at_chapter:3,reason:'cannot erase imported chapter'}]});
  invoke(book,'gate',undefined,[],2);
});
