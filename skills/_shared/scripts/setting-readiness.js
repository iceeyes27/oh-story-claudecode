'use strict';

// Mechanical receipt validation, not a semantic verdict on the settings.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const REVIEW_PATH = '设定/_设定审查.json';
const DIMENSIONS = ['rules', 'resources', 'characters', 'information', 'progression', 'closure'];

function sources(root) {
  const result = {};
  function walk(dir) {
    for (const item of fs.readdirSync(dir, { withFileTypes: true })) {
      if (item.name.startsWith('.')) continue;
      const file = path.join(dir, item.name);
      if (item.isDirectory()) walk(file);
      else if (item.isFile() && item.name.endsWith('.md')) {
        result[path.relative(root, file).split(path.sep).join('/')] = crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
      }
    }
  }
  walk(path.join(root, '设定'));
  return result;
}

function checkReadiness(root, chapter) {
  const findings = [];
  const add = (check, message) => findings.push({ severity: 'blocking', check: `readiness.${check}`, message, where: REVIEW_PATH });
  let review;
  try { review = JSON.parse(fs.readFileSync(path.join(root, REVIEW_PATH), 'utf8')); }
  catch { add('missing', '缺少或无法读取设定完善性审查记录；先执行 setting-payoff.md 的完善性关卡'); return findings; }
  const nonempty = value => typeof value === 'string' && value.trim().length > 0;
  if (!review || review.schema !== 'setting-readiness/v1' || !nonempty(review.reviewer)) {
    add('schema', '审查记录必须使用 setting-readiness/v1 并标明实际复核方'); return findings;
  }
  const current = sources(root);
  const recorded = review.sources;
  if (!recorded || typeof recorded !== 'object' || Array.isArray(recorded) ||
      Object.keys(current).length !== Object.keys(recorded).length ||
      Object.entries(current).some(([file, hash]) => recorded[file] !== hash)) {
    add('stale', '设定新增、删除或变更，审查记录已过期；复核影响面后更新 sources，禁止只刷新哈希');
  }
  const checks = review.checks;
  if (!Array.isArray(checks)) { add('checks', '审查记录缺少 checks'); return findings; }
  for (const id of DIMENSIONS) {
    const matches = checks.filter(item => item && item.id === id);
    if (matches.length !== 1) { add('dimension', `${id} 必须有且只有一条审查结论`); continue; }
    const item = matches[0];
    if (!['ready', 'open', 'not_applicable'].includes(item.status) || !nonempty(item.reason)) {
      add('conclusion', `${id} 须写 ready/open/not_applicable 和具体理由`);
    }
    if (item.status === 'open' && (!Array.isArray(review.issues) || !review.issues.some(issue => issue && issue.dimension === id))) {
      add('issue-missing', `${id} 尚有缺口，必须登记 issues 和返回阶段`);
    }
  }
  if (!Array.isArray(review.issues)) { add('issues', 'issues 必须是数组，无问题时写 []'); return findings; }
  for (const issue of review.issues) {
    if (!issue || !DIMENSIONS.includes(issue.dimension) || !nonempty(issue.problem) ||
        !nonempty(issue.next_action) || !['settings', 'outline', 'prose'].includes(issue.return_to) ||
        !['blocking', 'advisory'].includes(issue.severity) ||
        !Number.isInteger(issue.from_chapter) || issue.from_chapter < 1 ||
        !(issue.to_chapter === null || (Number.isInteger(issue.to_chapter) && issue.to_chapter >= issue.from_chapter))) {
      add('issue-schema', '每个缺口须有问题、严重度、受影响章节 from_chapter/to_chapter（null 表示以后全部）、返回阶段和下一步');
      continue;
    }
    const affected = chapter == null || (chapter >= issue.from_chapter && (issue.to_chapter === null || chapter <= issue.to_chapter));
    if (issue.severity === 'blocking' && affected) add('unresolved', `${issue.problem}；返回 ${issue.return_to}：${issue.next_action}`);
  }
  return findings;
}

module.exports = { checkReadiness, sources, DIMENSIONS };
