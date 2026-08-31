#!/usr/bin/env node
/** Verify the unified story-write Reference Gate and mode-specific routes. */

'use strict'

const assert = require('assert')
const fs = require('fs')
const path = require('path')

const repoRoot = path.resolve(__dirname, '..')
const skillRoot = path.join(repoRoot, 'skills/story-write')
const read = (relative) => fs.readFileSync(path.join(skillRoot, relative), 'utf8')

const skill = read('SKILL.md')
const gateLine = skill.split(/\r?\n/).findIndex((line) => line.includes('阶段 Reference Gate')) + 1
assert(gateLine > 0 && gateLine <= 20, `unified Reference Gate must stay in first screen, got line ${gateLine}`)
assert.match(skill, /只读本文件/)
assert.match(skill, /`rg` 检索或局部摘读都不算完成门禁/)
assert.match(skill, /long-mode\.md.*short-mode\.md/)

const long = read('references/long-mode.md')
assert.match(long, /长篇 Reference Gate/)
assert.match(long, /不得先写正文再补读/)
assert.match(long, /Constraint Lock/)
assert.match(long, /references 只提供技法，不得覆盖这些项目事实/)
for (const reference of [
  'workflow-setup.md', 'candidate-workflow.md', 'workflow-daily.md', 'workflow-revision.md',
  'long-format.md', 'writing-craft.md', 'long-chapter-quality.md', 'long-chapter-hooks.md',
  'long-suspense.md', 'long-reversal.md',
]) {
  assert(long.includes(reference), `long gate must route ${reference}`)
}

const short = read('references/short-mode.md')
assert.match(short, /短篇 Reference Gate/)
assert.match(short, /任一必需路径缺失或不可读即停止/)
for (const reference of [
  'short-format.md', 'short-craft.md', 'short-prose-quality.md', 'short-genre-formulas.md',
  'short-reversal.md', 'short-suspense.md', 'check-phase2-contract.js', 'check-delivery-contract.js',
]) {
  assert(short.includes(reference), `short gate must route ${reference}`)
}

process.stdout.write('reference-gates: unified source policy holds\n')
