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
// The normal writer must not expand the former eight-document reference chain.
// Parse the declared complete-load set, verify every file, and cap its actual size.
const writerGate = long.match(/写手只完整读取 (.+?) 直到 EOF/)
assert(writerGate, 'long gate must declare the ordinary writer complete-load set')
const writerReferences = [...writerGate[1].matchAll(/`([^`]+\.md)`/g)].map((match) => match[1])
assert.deepStrictEqual(writerReferences, ['reader-first-writing.md', 'long-format.md'])
const writerCoreChars = writerReferences.reduce((sum, reference) => sum + [...read(`references/${reference}`)].length, 0)
assert(writerCoreChars <= 5000, `ordinary writer core grew beyond 5000 characters: ${writerCoreChars}`)
assert.match(skill, /长篇从[\s\S]*只读取该阶段执行段/)
assert.doesNotMatch(skill, /完整读取 `references\/long-mode\.md`/)
assert.match(long, /quality_profile: fanqie-long-v2/)
assert.match(long, /`writer_packet`/)
const optionalRoute = long.split(/\r?\n/).find((line) => line.includes('是按需技法')) || ''
for (const reference of ['writing-craft.md', 'long-chapter-hooks.md', 'long-suspense.md', 'long-reversal.md']) {
  assert(optionalRoute.includes(reference), `${reference} must remain an optional technique route`)
}
const readerCore = read('references/reader-first-writing.md')
assert.match(readerCore, /候选仍等待作者采用/)
assert.match(readerCore, /`rc-01`、`rc-02`、`rc-03`/)
assert.match(readerCore, /第 15 章[\s\S]*`arc-01`、`arc-02`/)
assert.match(readerCore, /NOT_EVALUATED/)
const format = read('references/long-format.md')
assert.match(format, /fanqie-long-v2[\s\S]*2200～2800[\s\S]*2500/)
assert.match(format, /正文标点计入/)
assert.match(format, /wordcount measure --file/)
assert.match(long, /字数验证[^\n]*wordcount measure[^\n]*事务与阅读凭证齐备后再跑完整/)
const writerTemplate = fs.readFileSync(path.join(repoRoot, 'skills/story-setup/references/templates/agents/narrative-writer.md'), 'utf8')
assert.doesNotMatch(writerTemplate, /不许两项并一句/)
assert.match(writerTemplate, /每个独立结果都要能在正文定位/)
for (const reference of ['long-mode.md', 'long-format.md', 'workflow-daily.md']) {
  const content = read(`references/${reference}`)
  assert.doesNotMatch(content, /90%|目标×1\.1|内部带 ±12%|用户带 ±15%|动作与反应承接一律带人名/,
    `${reference} reintroduced a conflicting ordinary-candidate rule`)
}
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

process.stdout.write(`reference-gates: unified source policy holds; ordinary writer core ${writerCoreChars} characters in ${writerReferences.length} files\n`)
