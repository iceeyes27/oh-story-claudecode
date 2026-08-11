#!/usr/bin/env node
"use strict"

const assert = require("node:assert/strict")
const crypto = require("node:crypto")
const fs = require("node:fs")
const os = require("node:os")
const path = require("node:path")
const test = require("node:test")

const state = require("../skills/story-review/scripts/review-state.js")

function book() { return fs.mkdtempSync(path.join(os.tmpdir(), "story-review-state-")) }
function input(pathname, text) { return { path: pathname, sha256: crypto.createHash("sha256").update(text).digest("hex") } }
function batch(id = "b1", text = "v1", findings = []) {
  return { batch_id: id, range: "第1-10章", input_files: [input("正文/第001章.md", text)], open_findings: findings, affected_reviewed_ranges: ["第1-10章"] }
}
function expectCode(fn, code) { assert.throws(fn, (error) => error instanceof state.ReviewStateError && error.code === code) }

test("full 新建、同 review 恢复且不增 revision", () => {
  const root = book()
  const first = state.initReview(root, "full", "r1", batch())
  assert.equal(first.state_revision, 1)
  assert.equal(first.status, "active")
  const resumed = state.initReview(root, "full", "r1", batch())
  assert.equal(resumed.state_revision, 1)
})

test("active review 不得被其他 review_id 覆盖", () => {
  const root = book()
  state.initReview(root, "lean", "r1", batch())
  expectCode(() => state.initReview(root, "lean", "r2", batch()), "active-review")
  expectCode(() => state.initReview(root, "full", "r1", batch()), "mode-mismatch")
})

test("显式 reset 要求确认与 expected revision", () => {
  const root = book()
  state.initReview(root, "full", "r1", batch())
  expectCode(() => state.resetReview(root, "lean", "r2", 1, batch("b2"), false), "confirmation-required")
  const reset = state.resetReview(root, "lean", "r2", 1, batch("b2"), true)
  assert.equal(reset.review_id, "r2")
  assert.equal(reset.state_revision, 2)
})

test("批次更新、幂等重跑和完成后新任务", () => {
  const root = book()
  state.initReview(root, "full", "r1", batch())
  const updated = state.updateReview(root, "r1", 1, batch("b1", "v1", [{ finding_id: "f1", severity: "S2" }]))
  assert.equal(updated.state_revision, 2)
  assert.equal(updated.completed_batches.length, 1)
  const retry = state.updateReview(root, "r1", 1, batch("b1", "v1", [{ finding_id: "f1", severity: "S2" }]))
  assert.equal(retry.state_revision, 2)
  const completed = state.completeReview(root, "r1", 2)
  assert.equal(completed.status, "completed")
  const next = state.initReview(root, "lean", "r2", batch("b2"))
  assert.equal(next.review_id, "r2")
  assert.equal(next.state_revision, 4)
})

test("revision 冲突不覆盖状态且清理自己的 claim", () => {
  const root = book()
  state.initReview(root, "full", "r1", batch())
  expectCode(() => state.updateReview(root, "r1", 0, batch("b2")), "revision-conflict")
  assert.equal(state.statusReview(root).state.state_revision, 1)
  assert.deepEqual(state.statusReview(root).claims, [])
})

test("已存在目标 revision 申领立即冲突", () => {
  const root = book()
  const dir = path.join(root, ".story-review")
  fs.mkdirSync(dir)
  fs.writeFileSync(path.join(dir, ".cas-1"), JSON.stringify({ schema_version: 1, target_revision: 1, review_id: "other", claim_id: "other" }))
  expectCode(() => state.initReview(root, "full", "r1", batch()), "claim-conflict")
  assert.equal(fs.existsSync(path.join(dir, "latest.json")), false)
})

test("输入摘要变化将旧开放项标为 needs_revalidation", () => {
  const root = book()
  state.initReview(root, "full", "r1", batch())
  state.updateReview(root, "r1", 1, batch("b1", "v1", [{ finding_id: "f1", evidence: "old" }]))
  const changed = state.updateReview(root, "r1", 2, batch("b1", "v2", []))
  assert.equal(changed.open_findings.find((item) => item.finding_id === "f1").needs_revalidation, true)
})

test("同一输入文件重新分批且内容变化时旧开放项也需复核", () => {
  const root = book()
  state.initReview(root, "full", "r1", batch())
  state.updateReview(root, "r1", 1, batch("b1", "v1", [{ finding_id: "f1", evidence: "old" }]))
  const changed = state.updateReview(root, "r1", 2, batch("b2", "v2", []))
  assert.equal(changed.open_findings.find((item) => item.finding_id === "f1").needs_revalidation, true)
})

test("损坏 latest.json 明确失败且不覆盖", () => {
  const root = book()
  fs.mkdirSync(path.join(root, ".story-review"))
  fs.writeFileSync(path.join(root, ".story-review", "latest.json"), "{broken")
  expectCode(() => state.initReview(root, "full", "r1", batch()), "corrupt-state")
  assert.equal(fs.readFileSync(path.join(root, ".story-review", "latest.json"), "utf8"), "{broken")
})

test("solo/显式只读只查状态，不创建任何目录或文件", () => {
  for (const mode of ["solo", "readonly"]) {
    const root = book()
    assert.deepEqual(state.statusReview(root), { exists: false, state: null, claims: [] })
    expectCode(() => state.initReview(root, mode, "r1", batch()), "readonly-mode")
    assert.equal(fs.existsSync(path.join(root, ".story-review")), false)
  }
})

test("异常申领可报告，release 必须匹配 claim/revision/确认", () => {
  const root = book()
  state.initReview(root, "full", "r1", batch())
  const file = path.join(root, ".story-review", ".cas-2")
  fs.writeFileSync(file, JSON.stringify({ schema_version: 1, target_revision: 2, review_id: "r1", claim_id: "claim-x" }))
  assert.equal(state.statusReview(root).claims[0].claim_id, "claim-x")
  expectCode(() => state.releaseClaim(root, 2, "claim-x", false), "confirmation-required")
  expectCode(() => state.releaseClaim(root, 2, "wrong", true), "claim-mismatch")
  assert.deepEqual(state.releaseClaim(root, 2, "claim-x", true), { released: true, target_revision: 2 })
  assert.equal(fs.existsSync(file), false)
})
