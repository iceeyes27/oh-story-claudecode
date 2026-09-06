#!/usr/bin/env node
"use strict"

const crypto = require("node:crypto")
const fs = require("node:fs")
const os = require("node:os")
const path = require("node:path")

const SCHEMA_VERSION = 1

class ReviewStateError extends Error {
  constructor(code, message) {
    super(message)
    this.name = "ReviewStateError"
    this.code = code
  }
}

function fail(code, message) { throw new ReviewStateError(code, message) }
function stateDir(book) { return path.join(path.resolve(book), ".story-review") }
function latestPath(book) { return path.join(stateDir(book), "latest.json") }

function readJson(file, kind) {
  let text
  try { text = fs.readFileSync(file, "utf8") } catch (error) {
    if (error && error.code === "ENOENT") return null
    fail(`unreadable-${kind}`, `无法读取 ${file}`)
  }
  try { return JSON.parse(text) } catch { fail(`corrupt-${kind}`, `${file} 不是有效 JSON，禁止覆盖`) }
}

function validateState(state) {
  if (!state || typeof state !== "object" || Array.isArray(state)) fail("invalid-state", "状态必须是对象")
  if (state.schema_version !== SCHEMA_VERSION) fail("old-schema", `只接受 schema_version=${SCHEMA_VERSION}`)
  if (!Number.isInteger(state.state_revision) || state.state_revision < 1) fail("invalid-state", "state_revision 无效")
  if (!state.review_id || !["full", "lean"].includes(state.effective_mode)) fail("invalid-state", "review_id/effective_mode 无效")
  if (!["active", "completed"].includes(state.status)) fail("invalid-state", "status 无效")
  for (const key of ["completed_batches", "open_findings", "affected_reviewed_ranges"]) {
    if (!Array.isArray(state[key])) fail("invalid-state", `${key} 必须是数组`)
  }
  return state
}

function readState(book, required = false) {
  const state = readJson(latestPath(book), "state")
  if (!state) {
    if (required) fail("missing-state", "尚无 .story-review/latest.json")
    return null
  }
  return validateState(state)
}

function normalizeBatch(batch) {
  if (!batch || typeof batch !== "object" || Array.isArray(batch)) fail("invalid-batch", "批次必须是对象")
  if (typeof batch.batch_id !== "string" || !batch.batch_id.trim()) fail("invalid-batch", "batch_id 缺失")
  if (typeof batch.range !== "string" || !batch.range.trim()) fail("invalid-batch", "range 缺失")
  if (!Array.isArray(batch.input_files) || !batch.input_files.length) fail("invalid-batch", "input_files 缺失")
  const inputFiles = batch.input_files.map((item) => {
    if (!item || typeof item.path !== "string" || !item.path || !/^[a-f0-9]{64}$/i.test(item.sha256 || "")) {
      fail("invalid-batch", "input_files 必须包含 path 与 64 位 sha256")
    }
    return { path: item.path, sha256: item.sha256.toLowerCase() }
  }).sort((a, b) => a.path.localeCompare(b.path))
  const findings = Array.isArray(batch.open_findings) ? batch.open_findings.map((item) => {
    if (!item || typeof item.finding_id !== "string" || !item.finding_id) fail("invalid-batch", "finding_id 缺失")
    return { ...item, batch_id: batch.batch_id }
  }) : []
  const ranges = Array.isArray(batch.affected_reviewed_ranges) ? batch.affected_reviewed_ranges.map(String) : []
  const inputDigest = crypto.createHash("sha256").update(JSON.stringify(inputFiles)).digest("hex")
  return { batch_id: batch.batch_id, range: batch.range, input_files: inputFiles, input_digest: inputDigest, open_findings: findings, affected_reviewed_ranges: ranges }
}

function claimPath(book, targetRevision) { return path.join(stateDir(book), `.cas-${targetRevision}`) }

function ownClaim(file, claimId) {
  const claim = readJson(file, "claim")
  return claim && claim.claim_id === claimId
}

function atomicWrite(file, document, claimId) {
  const temp = path.join(path.dirname(file), `.latest.${claimId}.tmp`)
  let fd
  try {
    fd = fs.openSync(temp, "wx", 0o600)
    fs.writeFileSync(fd, JSON.stringify(document, null, 2) + "\n", "utf8")
    fs.fsyncSync(fd)
    fs.closeSync(fd)
    fd = undefined
    fs.renameSync(temp, file)
  } finally {
    if (fd !== undefined) try { fs.closeSync(fd) } catch {}
    if (fs.existsSync(temp)) try { fs.unlinkSync(temp) } catch {}
  }
}

function compareAndSwap(book, expectedRevision, reviewId, build) {
  if (!Number.isInteger(expectedRevision) || expectedRevision < 0) fail("invalid-revision", "expected_state_revision 无效")
  const directory = stateDir(book)
  fs.mkdirSync(directory, { recursive: true })
  const targetRevision = expectedRevision + 1
  const file = claimPath(book, targetRevision)
  const claimId = crypto.randomUUID()
  const claim = { schema_version: 1, target_revision: targetRevision, review_id: reviewId, pid: process.pid, hostname: os.hostname(), created_at: new Date().toISOString(), claim_id: claimId }
  try {
    fs.writeFileSync(file, JSON.stringify(claim, null, 2) + "\n", { encoding: "utf8", flag: "wx", mode: 0o600 })
  } catch (error) {
    if (error && error.code === "EEXIST") fail("claim-conflict", `revision ${targetRevision} 已被申领`)
    throw error
  }
  try {
    const current = readState(book, false)
    const actualRevision = current ? current.state_revision : 0
    if (actualRevision !== expectedRevision) fail("revision-conflict", `期望 revision ${expectedRevision}，当前 ${actualRevision}`)
    const next = build(current)
    next.schema_version = SCHEMA_VERSION
    next.state_revision = targetRevision
    next.updated_at = new Date().toISOString()
    atomicWrite(latestPath(book), next, claimId)
    return next
  } finally {
    if (fs.existsSync(file) && ownClaim(file, claimId)) try { fs.unlinkSync(file) } catch {}
  }
}

function initReview(book, mode, reviewId, batchInput) {
  if (!["full", "lean"].includes(mode)) fail("readonly-mode", "只有 full/lean 可写状态；solo/显式只读只能 status")
  if (!reviewId) fail("invalid-review", "review_id 缺失")
  const batch = normalizeBatch(batchInput)
  const current = readState(book, false)
  if (current && current.status === "active") {
    if (current.review_id !== reviewId) fail("active-review", `未完成 review_id=${current.review_id}，不得被 ${reviewId} 覆盖`)
    if (current.effective_mode !== mode) fail("mode-mismatch", `当前 review 使用 ${current.effective_mode}，不得改为 ${mode}`)
    return current
  }
  const expected = current ? current.state_revision : 0
  return compareAndSwap(book, expected, reviewId, () => ({
    review_id: reviewId,
    effective_mode: mode,
    status: "active",
    book_path: ".",
    current_batch: { batch_id: batch.batch_id, range: batch.range, input_files: batch.input_files, input_digest: batch.input_digest },
    completed_batches: [],
    open_findings: [],
    affected_reviewed_ranges: [],
  }))
}

function updateReview(book, reviewId, expectedRevision, batchInput) {
  const batch = normalizeBatch(batchInput)
  const current = readState(book, true)
  if (current.review_id !== reviewId || current.status !== "active") fail("review-mismatch", "只能更新当前 active review")
  const applied = current.completed_batches.find((item) => item.batch_id === batch.batch_id && item.input_digest === batch.input_digest && item.result_digest === resultDigest(batch))
  if (applied) return current
  return compareAndSwap(book, expectedRevision, reviewId, (fresh) => {
    if (!fresh || fresh.review_id !== reviewId || fresh.status !== "active") fail("review-mismatch", "申领后 active review 已变化")
    const previous = fresh.completed_batches.find((item) => item.batch_id === batch.batch_id)
    const inputChanged = previous && previous.input_digest !== batch.input_digest
    const incomingHashes = new Map(batch.input_files.map((item) => [item.path, item.sha256]))
    const batchesNeedingRevalidation = new Set(fresh.completed_batches.filter((item) => {
      if (item.batch_id === batch.batch_id) return inputChanged
      return item.input_files.some((oldInput) => incomingHashes.has(oldInput.path) && incomingHashes.get(oldInput.path) !== oldInput.sha256)
    }).map((item) => item.batch_id))
    const findings = new Map(fresh.open_findings.map((item) => [item.finding_id, { ...item }]))
    for (const item of findings.values()) if (batchesNeedingRevalidation.has(item.batch_id)) item.needs_revalidation = true
    for (const item of batch.open_findings) findings.set(item.finding_id, { ...item, needs_revalidation: false })
    const summary = { batch_id: batch.batch_id, range: batch.range, input_files: batch.input_files, input_digest: batch.input_digest, result_digest: resultDigest(batch) }
    const completed = fresh.completed_batches.filter((item) => item.batch_id !== batch.batch_id)
    completed.push(summary)
    return {
      ...fresh,
      current_batch: summary,
      completed_batches: completed,
      open_findings: [...findings.values()],
      affected_reviewed_ranges: [...new Set([...fresh.affected_reviewed_ranges, ...batch.affected_reviewed_ranges])],
    }
  })
}

function resultDigest(batch) {
  return crypto.createHash("sha256").update(JSON.stringify({ findings: batch.open_findings, ranges: batch.affected_reviewed_ranges })).digest("hex")
}

function completeReview(book, reviewId, expectedRevision) {
  const current = readState(book, true)
  if (current.review_id !== reviewId || current.status !== "active") fail("review-mismatch", "只能完成当前 active review")
  return compareAndSwap(book, expectedRevision, reviewId, (fresh) => ({ ...fresh, status: "completed" }))
}

function resetReview(book, mode, reviewId, expectedRevision, batchInput, confirmed) {
  if (!confirmed) fail("confirmation-required", "必须确认放弃当前 active review")
  if (!["full", "lean"].includes(mode) || !reviewId) fail("invalid-review", "reset 需要 full/lean 与 review_id")
  const batch = normalizeBatch(batchInput)
  return compareAndSwap(book, expectedRevision, reviewId, () => ({
    review_id: reviewId,
    effective_mode: mode,
    status: "active",
    book_path: ".",
    current_batch: { batch_id: batch.batch_id, range: batch.range, input_files: batch.input_files, input_digest: batch.input_digest },
    completed_batches: [],
    open_findings: [],
    affected_reviewed_ranges: [],
  }))
}

function statusReview(book) {
  const state = readState(book, false)
  let claims = []
  try {
    claims = fs.readdirSync(stateDir(book)).filter((name) => /^\.cas-\d+$/.test(name)).map((name) => {
      const claim = readJson(path.join(stateDir(book), name), "claim")
      return claim ? { file: name, ...claim } : { file: name, corrupt: true }
    })
  } catch (error) {
    if (!error || error.code !== "ENOENT") throw error
  }
  return { exists: Boolean(state), state, claims }
}

function releaseClaim(book, targetRevision, claimId, confirmed) {
  if (!confirmed) fail("confirmation-required", "必须确认对应写入者已停止")
  const file = claimPath(book, targetRevision)
  const claim = readJson(file, "claim")
  if (!claim || claim.claim_id !== claimId || claim.target_revision !== targetRevision) fail("claim-mismatch", "claim_id 或 target revision 不匹配")
  const current = readState(book, false)
  const revision = current ? current.state_revision : 0
  if (revision !== targetRevision - 1) fail("revision-conflict", `latest revision ${revision} 与申领前置 ${targetRevision - 1} 不一致`)
  fs.unlinkSync(file)
  return { released: true, target_revision: targetRevision }
}

function parseCli(argv) {
  const command = argv.shift()
  const values = {}
  const flags = new Set()
  const allowed = new Set(["book", "mode", "review-id", "expected-revision", "batch", "target-revision", "claim-id"])
  while (argv.length) {
    const token = argv.shift()
    if (token === "--confirm-writer-stopped" || token === "--confirm-abandon-active") { if (flags.has(token)) fail("cli", `重复参数 ${token}`); flags.add(token); continue }
    if (!token || !token.startsWith("--")) fail("cli", `意外位置参数 ${token || ""}`)
    const key = token.slice(2)
    if (!allowed.has(key) || Object.hasOwn(values, key)) fail("cli", `未知或重复参数 ${token}`)
    const value = argv.shift()
    if (!value || value.startsWith("--")) fail("cli", `${token} 缺少值`)
    values[key] = value
  }
  return { command, values, flags }
}

function readBatch(file) { const value = readJson(path.resolve(file), "batch"); if (!value) fail("missing-batch", `批次文件不存在：${file}`); return value }

function main(argv) {
  try {
    const { command, values, flags } = parseCli([...argv])
    if (!values.book) fail("cli", "缺少 --book")
    let output
    if (command === "status") output = statusReview(values.book)
    else if (command === "init") output = initReview(values.book, values.mode, values["review-id"], readBatch(values.batch))
    else if (command === "update") output = updateReview(values.book, values["review-id"], Number(values["expected-revision"]), readBatch(values.batch))
    else if (command === "complete") output = completeReview(values.book, values["review-id"], Number(values["expected-revision"]))
    else if (command === "reset") output = resetReview(values.book, values.mode, values["review-id"], Number(values["expected-revision"]), readBatch(values.batch), flags.has("--confirm-abandon-active"))
    else if (command === "release-claim") output = releaseClaim(values.book, Number(values["target-revision"]), values["claim-id"], flags.has("--confirm-writer-stopped"))
    else fail("cli", "命令必须是 status/init/update/complete/reset/release-claim")
    process.stdout.write(JSON.stringify(output, null, 2) + "\n")
    return 0
  } catch (error) {
    if (error instanceof ReviewStateError) { process.stderr.write(`ERROR [${error.code}] ${error.message}\n`); return 1 }
    throw error
  }
}

if (require.main === module) process.exitCode = main(process.argv.slice(2))

module.exports = { ReviewStateError, SCHEMA_VERSION, completeReview, initReview, normalizeBatch, releaseClaim, resetReview, statusReview, updateReview }
