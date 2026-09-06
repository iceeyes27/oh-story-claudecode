#!/usr/bin/env node
'use strict';

const assert = require('assert');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawnSync } = require('child_process');

const ROOT = path.resolve(__dirname, '..');
const TOOL = path.join(ROOT, 'skills/story-write/scripts/check-chapter-skeleton.js');
const SKILL = path.join(ROOT, 'skills/story-write/references/long-mode.md');
const WORKFLOW = path.join(ROOT, 'skills/story-write/references/chapter-skeleton-workflow.md');
const CANDIDATE_WORKFLOW = path.join(ROOT, 'skills/story-write/references/candidate-workflow.md');
const TEMP = fs.mkdtempSync(path.join(os.tmpdir(), 'chapter-skeleton-test-'));

function scene(number, budget, overrides = {}) {
  const values = {
    '时空与人物': `地点 ${number}；主角、对手`,
    '场景目标': `完成目标 ${number}`,
    '阻力': `阻力 ${number}`,
    '动作链': `动作 A -> 动作 B -> 动作 C`,
    '结果变化': `结果 ${number}`,
    '情绪转折': `受阻 -> 主动 ${number}`,
    '信息/伏笔': `推进 F00${number}`,
    '台词意图与潜台词': `主角追问信息，对手回避责任`,
    '正文字数预算': `${budget} 字`,
    ...overrides,
  };
  return `## 场景 ${number}\n\n${Object.entries(values).map(([key, value]) => `- ${key}：${value}`).join('\n')}\n`;
}

function skeleton({ scenes = [800, 800, 900], target = 2500, coverage = null } = {}) {
  const sceneText = scenes.map((budget, index) => scene(index + 1, budget)).join('\n');
  const coverageText = coverage || scenes.map((_, index) => `- [x] O${index + 1} 语义点 ${index + 1} -> 场景 ${index + 1}`).join('\n');
  return `# 第001章 测试章\n\n## 章节契约\n\n- 来源细纲：大纲/细纲_第001章.md\n- 最终正文字数目标：${target} 字\n- 目标情绪：受阻转主动\n- 读者获得：取得具体证据\n- 禁止提前释放：幕后身份\n- 开场动作：材料被退回\n- 章尾钩子：发现异常编号\n\n${sceneText}\n## 细纲覆盖\n\n${coverageText}\n\n## 扩写约束\n\n- 人物声线：主角少解释，多追问\n- 事实红线：不能确认幕后身份\n- 允许自由发挥：非关键动作\n`;
}

function run(args, expected) {
  const result = spawnSync(process.execPath, [TOOL, ...args], { encoding: 'utf8' });
  assert.strictEqual(result.status, expected, `expected ${expected}, got ${result.status}\nstdout=${result.stdout}\nstderr=${result.stderr}`);
  return result;
}

function write(name, content) {
  const file = path.join(TEMP, name);
  fs.writeFileSync(file, content, 'utf8');
  return file;
}

try {
  const skillText = fs.readFileSync(SKILL, 'utf8');
  const workflowText = fs.readFileSync(WORKFLOW, 'utf8');
  const candidateText = fs.readFileSync(CANDIDATE_WORKFLOW, 'utf8');
  assert(skillText.includes('**默认分支是章节骨架**'));
  assert(skillText.includes('references/chapter-skeleton-workflow.md'));
  for (const trigger of ['写第 N 章', '续写', '继续写', '日更']) {
    assert(workflowText.includes(`“${trigger}”`), `missing default skeleton trigger: ${trigger}`);
  }
  assert(candidateText.includes('书根 `候选/`'));
  assert(candidateText.includes('不能证明文风自然或没有 AI 痕迹'));
  assert(!`${skillText}\n${workflowText}\n${candidateText}`.includes('正文/候选/'));

  const valid = write('第001章_测试章.md', skeleton());
  const validResult = run([valid, '--json'], 0);
  const validJson = JSON.parse(validResult.stdout);
  assert.strictEqual(validJson.blocking, 0);
  assert.strictEqual(validJson.files, 1);

  const missingField = write('第002章_缺字段.md', skeleton().replace('- 阻力：阻力 2\n', ''));
  const missingResult = JSON.parse(run([missingField, '--json'], 1).stdout);
  assert(missingResult.results[0].blocking.some((item) => item.code === 'missing-scene-field'));

  const missingExpansionField = write('第008章_扩写约束缺字段.md', skeleton().replace('- 事实红线：不能确认幕后身份\n', ''));
  const expansionResult = JSON.parse(run([missingExpansionField, '--json'], 1).stdout);
  assert(expansionResult.results[0].blocking.some((item) => item.code === 'missing-expansion-field'));

  for (const budgets of [[2500], [1200, 1300], [800, 800, 900], [300, 300, 300, 400, 400, 400, 400]]) {
    const file = write(`第003章_${budgets.length}场.md`, skeleton({ scenes: budgets }));
    const result = JSON.parse(run([file, '--json'], 0).stdout);
    assert.strictEqual(result.blocking, 0, `${budgets.length} scenes should be valid`);
  }

  const noScenes = write('第003章_无场景.md', skeleton({ scenes: [] }));
  const countResult = JSON.parse(run([noScenes, '--json'], 1).stdout);
  assert(countResult.results[0].blocking.some((item) => item.code === 'scene-count'));

  const badSceneNumber = write('第010章_场景编号错误.md', skeleton().replace('## 场景 2', '## 场景 4'));
  const sceneNumberResult = JSON.parse(run([badSceneNumber, '--json'], 1).stdout);
  assert(sceneNumberResult.results[0].blocking.some((item) => item.code === 'scene-sequence'));
  assert(sceneNumberResult.results[0].blocking.some((item) => item.code === 'invalid-coverage-scene'));

  const duplicateScene = write('第011章_场景编号重复.md', skeleton().replace('## 场景 2', '## 场景 1'));
  const duplicateSceneResult = JSON.parse(run([duplicateScene, '--json'], 1).stdout);
  assert(duplicateSceneResult.results[0].blocking.some((item) => item.code === 'duplicate-scene'));

  const budgetMismatch = write('第004章_预算错误.md', skeleton({ scenes: [700, 800, 900] }));
  const budgetResult = JSON.parse(run([budgetMismatch, '--json'], 1).stdout);
  assert(budgetResult.results[0].blocking.some((item) => item.code === 'budget-mismatch'));

  const unchecked = write('第005章_覆盖欠缺.md', skeleton({ coverage: '- [x] O1 语义点 1 -> 场景 1\n- [ ] O2 语义点 2 -> 场景 2\n- [x] O3 语义点 3 -> 场景 3' }));
  const coverageResult = JSON.parse(run([unchecked, '--json'], 1).stdout);
  assert(coverageResult.results[0].blocking.some((item) => item.code === 'unchecked-coverage'));

  const duplicated = write('第006章_覆盖重复.md', skeleton({ coverage: '- [x] O1 语义点 1 -> 场景 1\n- [x] O1 语义点 2 -> 场景 2\n- [x] O3 语义点 3 -> 场景 3' }));
  const duplicateResult = JSON.parse(run([duplicated, '--json'], 1).stdout);
  assert(duplicateResult.results[0].blocking.some((item) => item.code === 'duplicate-coverage-id'));

  const nonContiguous = write('第009章_覆盖编号断档.md', skeleton({ coverage: '- [x] O1 语义点 1 -> 场景 1\n- [x] O3 语义点 2 -> 场景 2\n- [x] O4 语义点 3 -> 场景 3' }));
  const sequenceResult = JSON.parse(run([nonContiguous, '--json'], 1).stdout);
  assert(sequenceResult.results[0].blocking.some((item) => item.code === 'coverage-sequence'));

  const dialogue = write('第007章_台词提示.md', skeleton().replace('主角追问信息，对手回避责任', '主角说：“把回执给我。”，对手回避责任'));
  const advisoryResult = JSON.parse(run([dialogue, '--json'], 0).stdout);
  assert(advisoryResult.results[0].advisory.some((item) => item.code === 'possible-finished-dialogue'));

  const directoryResult = JSON.parse(run(['--dir', TEMP, '--from', '1', '--to', '1', '--json'], 0).stdout);
  assert.strictEqual(directoryResult.files, 1);

  const invalidName = write('错误名称.md', skeleton());
  const filenameResult = JSON.parse(run([invalidName, '--json'], 1).stdout);
  assert(filenameResult.results[0].blocking.some((item) => item.code === 'filename'));

  run([path.join(TEMP, '不存在.md')], 2);
  run([], 2);
  process.stdout.write('OK: chapter skeleton validator regressions passed\n');
} finally {
  fs.rmSync(TEMP, { recursive: true, force: true });
}
