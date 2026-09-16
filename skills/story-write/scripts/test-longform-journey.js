#!/usr/bin/env node
'use strict';
// Engineering fixtures only: simulated adoption/delivery is not human approval or reading evidence.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const {spawnSync} = require('node:child_process');
const tool = path.resolve(__dirname, '../../story-review/scripts/review-state.js');
const audit = path.join(__dirname, 'volume-audit.py');

test('15 simulated adopted chapters, 3 units, 2 volumes, deferred response and stale evidence', () => {
  const book = fs.mkdtempSync(path.join(os.tmpdir(), 'longform-journey-'));
  const put = (relative, body) => {const file = path.join(book, relative);fs.mkdirSync(path.dirname(file), {recursive:true});fs.writeFileSync(file,body);return file;};
  let revision = 0;
  const call = (command, input, expected=0, args=[]) => {
    const argv = [tool, 'longform', command, '--book', book, ...args];
    if (!['status','gate'].includes(command)) argv.push('--expected-revision', String(revision));
    if (input) argv.push('--input', put('input.json', JSON.stringify(input)));
    const run = spawnSync('node', argv, {encoding:'utf8'});
    assert.equal(run.status, expected, run.stderr || run.stdout);
    const output = JSON.parse(run.stdout);
    if (output.state_revision) revision=output.state_revision;
    return output;
  };
  const chapterPath = n => `正文/第${n <= 10 ? 1 : 2}卷/第${String(n).padStart(3,'0')}章_船票.md`;
  try {
    put('追踪/_tracking-state.json', JSON.stringify({last_committed_chapter:0}));
    for (const [volume, from, to, ranges] of [[1,1,10,[[1,5],[6,10]]],[2,11,15,[[11,15]]]]) {
      put(`大纲/卷纲_第${volume}卷.md`, `# 卷纲\n章节范围：第${from}-${to}章\n## 核心矛盾\n拿回船票。下一卷承接。\n` + ranges.map(([a,b],i)=>`### 剧情单元 L${volume}-${i+1}\n> 作用域：单元级 L${volume}-${i+1}\n章节范围：第${a}-${b}章\n`).join(''));
    }
    call('init', null, 0, ['--new-book']);
    for (let n=1;n<=15;n++) {
      assert.equal(call('gate',null,0,['--chapter',String(n)]).can_generate,true);
      put(chapterPath(n), `第${n}章工程夹具，模拟采用，不是小说或作者阅读结论。\n`);
      put('追踪/_tracking-state.json', JSON.stringify({last_committed_chapter:n}));
      if (![5,10,15].includes(n)) continue;
      const gate=call('gate',null,1,['--chapter',String(n+1)]);
      const cp=gate.checkpoints.find(c=>c.chapter===n);
      assert.equal(cp.status,'pending');
      if(n===15){assert.equal(cp.from,1);assert.equal(cp.reasons.length,2);}
      const prior=n===10 ? [1,2,3,4,5].map(chapterPath) : [];
      const started=call('start',{checkpoint_id:cp.id,reader:{id:'fixture-reader',session_id:'isolated-fixture',reader_type:'model'},independent:true,creative_participants:['fixture-writer'],reading_order:'chronological_then_comparison',prose_only:true,comparison:{reason:'Engineering full prior-unit comparison',paths:prior}});
      for (const row of [...started.required_files,...started.comparison_files]) {
        const delivered=call('read',{run_id:started.run_id,path:row.path});
        assert.equal(delivered.text,fs.readFileSync(path.join(book,row.path),'utf8'));
      }
      const evidence=[{path:started.required_files[0].path,line:1,quote:fs.readFileSync(path.join(book,started.required_files[0].path),'utf8').trim()}];
      const observations=Object.fromEntries(['understanding','fatigue','relationships','reward_expectation'].map(key=>[key,{assessment:'Engineering receipt fixture; no literary assessment.',evidence}]));
      const findings=n===5 ? [{id:'F1',disposition:'next_unit',reason:'Fixture exercises deferred handling',evidence}] : [];
      const responses=n===10 ? [{finding_id:'F1',disposition:'retain',reason:'Fixture response; not human acceptance'}] : [];
      call('finish',{run_id:started.run_id,observations,findings,responses});
      assert.equal(call('gate').can_complete,true);
    }
    for (const volume of [1,2]) {
      const result=spawnSync('python3',[audit,'--project',book,'--volume',String(volume),'--json'],{encoding:'utf8'});
      assert.equal(result.status,0,result.stderr||result.stdout);
      assert.equal(JSON.parse(result.stdout).metrics.audit_scope,'complete_volume');
    }
    fs.appendFileSync(path.join(book,chapterPath(3)),'changed fixture\n');
    const stale=call('gate',null,1);
    assert.equal(stale.checkpoints.filter(cp=>cp.status==='stale').length,3);
  } finally {fs.rmSync(book,{recursive:true,force:true});}
});
