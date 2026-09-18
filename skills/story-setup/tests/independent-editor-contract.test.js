const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const root = path.resolve(__dirname, '..');
const read = (p) => fs.readFileSync(path.join(root, p), 'utf8').replaceAll('\r\n', '\n');

test('editor generated roles share the canonical specification and read-only scope', () => {
  const files = ['references/templates/agents/copy-editor.md', 'references/codex/agents/copy-editor.toml', 'references/antigravity/agents/copy-editor/agent.md'];
  for (const file of files) {
    const value = read(file);
    assert.match(value, /name\s*[:=]\s*"?copy-editor/);
    assert.match(value, /\.agents\/skills\/story-write\/references\/copy-editor-specification\.md/);
    assert.match(value, /独立新会话/);
    assert.match(value, /NOT_EVALUATED/);
    assert.match(value, /合理省略/);
    assert.doesNotMatch(value, /画不出物理画面.*必修|必须给出具体坐标/);
  }
  assert.match(read(files[0]), /tools: \[Read, Glob, Grep\]/);
  assert.match(read(files[1]), /sandbox_mode = "read-only"/);
  const anti = read(files[2]);
  assert.doesNotMatch(anti.slice(0, anti.indexOf('\n---', 4)), /write_to_file|replace_file_content|run_command/);
});

test('full preflight includes editor while solo cannot grant independent completion', () => {
  const review = fs.readFileSync(path.join(root, '../story-review/SKILL.md'), 'utf8');
  assert.match(review, /全部 5 个 Agent/);
  assert.match(review, /full 必需：[^\n]*copy-editor\.md/);
  assert.match(review, /没有成功完成独立编辑时记 `Editor Review: NOT_EVALUATED`/);
  assert.match(review, /copy-editor: APPROVE/);
});

test('legacy same-name editor without protocol marker is not current coverage', () => {
  const review = fs.readFileSync(path.join(root, '../story-review/SKILL.md'), 'utf8');
  assert.match(review, /full 的同名文件还必须同时包含 `Review Protocol: independent-editor-v1`/);
  assert.match(review, /缺任一项即旧版或不完整角色，不能算当前独立编辑覆盖/);
  assert.match(review, /名称存在或 bundle 版本相同不能代替本项/);
  for (const file of ['references/templates/agents/copy-editor.md', 'references/codex/agents/copy-editor.toml', 'references/antigravity/agents/copy-editor/agent.md']) {
    assert.match(read(file), /Review Protocol: independent-editor-v1/);
  }
});

test('lean requires only architecture and consistency, and editor excludes author rubric', () => {
  const review = fs.readFileSync(path.join(root, '../story-review/SKILL.md'), 'utf8');
  const lean = review.split('\n').find((line) => line.includes('lean 必需：'));
  assert.deepEqual([...lean.matchAll(/`([a-z-]+)\.md`/g)].map((match) => match[1]), ['story-architect', 'consistency-checker']);
  assert.match(review, /仅向实际执行的作者视角角色（story-architect、character-designer、narrative-writer、consistency-checker）注入/);
  assert.match(review, /copy-editor 明确排除，不接收本书承诺、章节设计功能或作者答案/);
  assert.doesNotMatch(review, /把“审查基准包摘要”直接写进每个 Agent prompt/);
});

test('completed sessions do not imply capacity release and fresh execution is bounded', () => {
  const review = fs.readFileSync(path.join(root, '../story-review/SKILL.md'), 'utf8');
  assert.match(review, /完成不等于释放会话/);
  assert.match(review, /close\/release 工具时，保存结果后显式释放/);
  assert.match(review, /无历史隔离调用（例如 CLI 新会话）/);
  assert.match(review, /记录工具来源、调用身份、实际输入及结果/);
  assert.match(review, /不再启动外部子会话，禁止无限外部递归/);
  assert.match(review, /两者都不可用时停止重试/);
  assert.match(review, /保留已完成独立审读的真实状态与证据/);
  assert.match(review, /平台限制不降低完成条件/);
});


test('aggregate fallback preserves completed independent editor evidence', () => {
  const review = fs.readFileSync(path.join(root, '../story-review/SKILL.md'), 'utf8');
  assert.match(review, /总体模式与单角色状态分别记录/);
  assert.match(review, /复合编辑项按自身实际执行结果记 `PASS`\/`FAIL`/);
  assert.match(review, /总体降级不清除已完成结果/);
  assert.doesNotMatch(review, /lean\/solo 或编辑未成功执行时一律/);
  const modeLines = review.split('\n').filter((line) => line.startsWith('- `/story-review') && /full|lean/.test(line));
  assert.equal(modeLines.length, 2);
  assert.ok(modeLines.every((line) => line.includes('容量限制先按 Phase 2 有限调度处理')));
});

test('quality process marker and evidence-led reader/editor behavior reach both entrypoints', () => {
  for (const file of ['references/templates/agents/copy-editor.md', 'references/codex/agents/copy-editor.toml', 'references/antigravity/agents/copy-editor/agent.md']) {
    assert.match(read(file), /Review Process: review-quality-v2/);
    assert.match(read(file), /有据体验缺陷/);
  }
  const writer = fs.readFileSync(path.join(root, '../story-write/SKILL.md'), 'utf8');
  const review = fs.readFileSync(path.join(root, '../story-review/SKILL.md'), 'utf8');
  const router = fs.readFileSync(path.join(root, '../story/SKILL.md'), 'utf8');
  for (const value of [writer, review]) {
    assert.match(value, /Review Process: review-quality-v2/);
    assert.match(value, /review-process\.md/);
    assert.match(value, /第二次无改善停止自动改/);
  }
  assert.match(writer, /这些反应返回后才进行七问回查/);
  assert.match(writer, /必须另派无旧稿及问题答案的新读者只读新版/);
  assert.match(router, /检查仅报告，不写 review_process 或候选凭证/);
});
