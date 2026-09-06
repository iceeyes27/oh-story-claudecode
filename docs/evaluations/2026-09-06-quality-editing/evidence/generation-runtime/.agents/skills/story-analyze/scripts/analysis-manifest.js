#!/usr/bin/env node
"use strict"

const crypto = require("node:crypto")
const fs = require("node:fs")
const os = require("node:os")
const path = require("node:path")

const { validateProgress } = require("./chapter-boundary.js")

const SCHEMA_VERSION = 1
const STAGE_IDS = ["0", "1", "2", "3", "4", "5", "6"]
const STAGE_STATUSES = new Set(["pending", "running", "completed", "completed_with_errors", "failed"])
const ALIAS_KINDS = new Set(["proper_name", "nickname", "descriptor", "title"])
const RESOLVABLE_ALIAS_KINDS = new Set(["proper_name", "nickname"])
const DIRECTIONS = new Set(["undirected", "source_to_target"])
const RESERVED_KEYS = new Set(["__proto__", "constructor", "prototype"])

class AnalysisManifestError extends Error {
  constructor(code, message) {
    super(message)
    this.name = "AnalysisManifestError"
    this.code = code
  }
}

function fail(code, message) {
  throw new AnalysisManifestError(code, message)
}

function nowIso() {
  return new Date().toISOString()
}

function sha256(value) {
  return crypto.createHash("sha256").update(value).digest("hex")
}

function jsonSha256(value) {
  return sha256(JSON.stringify(value))
}

function compareCodePoints(left, right) {
  const leftPoints = Array.from(left, (character) => character.codePointAt(0))
  const rightPoints = Array.from(right, (character) => character.codePointAt(0))
  const length = Math.min(leftPoints.length, rightPoints.length)
  for (let index = 0; index < length; index += 1) {
    if (leftPoints[index] !== rightPoints[index]) return leftPoints[index] - rightPoints[index]
  }
  return leftPoints.length - rightPoints.length
}

function exactKeys(value, expected, code, label) {
  const actual = Object.keys(value).sort()
  const wanted = [...expected].sort()
  if (actual.length !== wanted.length || actual.some((item, index) => item !== wanted[index])) {
    fail(code, `${label} 字段必须恰好为 ${wanted.join(", ")}`)
  }
}

function requireObject(value, code, label) {
  if (!value || typeof value !== "object" || Array.isArray(value)) fail(code, `${label} 必须是对象`)
  return value
}

function requireString(value, code, label, maximum = 500) {
  if (typeof value !== "string" || !value.trim() || value.length > maximum) {
    fail(code, `${label} 必须是 1-${maximum} 字符的非空字符串`)
  }
  return value.trim()
}

function requireConfidence(value, code, label) {
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0 || value > 1) {
    fail(code, `${label} 必须是 0..1 之间的数字`)
  }
  return value
}

function requireSha(value, code, label) {
  if (typeof value !== "string" || !/^[a-f0-9]{64}$/.test(value)) fail(code, `${label} 必须是小写 SHA-256`)
  return value
}

function readJson(file, kind) {
  let text
  try {
    text = fs.readFileSync(file, "utf8")
  } catch (error) {
    if (error && error.code === "ENOENT") fail(`missing-${kind}`, `${file} 不存在`)
    fail(`unreadable-${kind}`, `无法读取 ${file}`)
  }
  try {
    return { value: JSON.parse(text), text }
  } catch {
    fail(`corrupt-${kind}`, `${file} 不是有效 JSON，禁止覆盖`)
  }
}

function normalizeRelativePath(value, code, label) {
  const shown = requireString(value, code, label, 500).replace(/\\/g, "/")
  if (shown.includes("\u0000")) fail(code, `${label} 含非法字符`)
  if (path.posix.isAbsolute(shown) || /^[A-Za-z]:\//.test(shown)) fail(code, `${label} 必须是相对路径`)
  const normalized = path.posix.normalize(shown)
  if (normalized === "." || normalized === ".." || normalized.startsWith("../")) {
    fail(code, `${label} 不得离开拆文输出目录`)
  }
  return normalized
}

function verifyCreateParent(base, target, code, label) {
  const resolvedBase = path.resolve(base)
  let existing = path.dirname(target)
  while (true) {
    try {
      fs.lstatSync(existing)
      break
    } catch (error) {
      if (!error || error.code !== "ENOENT") fail(code, `无法检查 ${label} 的父目录`)
      const parent = path.dirname(existing)
      if (parent === existing) fail(code, `${label} 的父目录不存在`)
      existing = parent
    }
  }
  let realBase
  let realParent
  let parentStat
  try {
    realBase = fs.realpathSync(resolvedBase)
    realParent = fs.realpathSync(existing)
    parentStat = fs.statSync(existing)
  } catch {
    fail(code, `无法解析 ${label} 的父目录`)
  }
  if (!parentStat.isDirectory()) fail(code, `${label} 的父路径必须是目录`)
  const relation = path.relative(realBase, realParent)
  if (relation === ".." || relation.startsWith(`..${path.sep}`) || path.isAbsolute(relation)) {
    fail(code, `${label} 的父目录不得离开拆文输出目录`)
  }
}

function containedFile(base, relativePath, options = {}) {
  const { code = "invalid-path", label = "路径", mustExist = true, rejectSymlink = true } = options
  const normalized = normalizeRelativePath(relativePath, code, label)
  const resolvedBase = path.resolve(base)
  const absolute = path.resolve(resolvedBase, ...normalized.split("/"))
  const relation = path.relative(resolvedBase, absolute)
  if (relation === ".." || relation.startsWith(`..${path.sep}`) || path.isAbsolute(relation)) {
    fail(code, `${label} 不得离开拆文输出目录`)
  }
  if (!mustExist) {
    verifyCreateParent(resolvedBase, absolute, code, label)
    return { absolute, relative: normalized }
  }
  let stat
  try {
    stat = fs.lstatSync(absolute)
  } catch {
    fail(code, `${label} 不存在：${normalized}`)
  }
  if (rejectSymlink && stat.isSymbolicLink()) fail(code, `${label} 不得是符号链接：${normalized}`)
  if (!stat.isFile()) fail(code, `${label} 必须是普通文件：${normalized}`)
  let realBase
  let realFile
  try {
    realBase = fs.realpathSync(resolvedBase)
    realFile = fs.realpathSync(absolute)
  } catch {
    fail(code, `无法解析 ${label} 的真实路径：${normalized}`)
  }
  const realRelation = path.relative(realBase, realFile)
  if (realRelation === ".." || realRelation.startsWith(`..${path.sep}`) || path.isAbsolute(realRelation)) {
    fail(code, `${label} 的真实路径不得离开拆文输出目录`)
  }
  return { absolute, relative: normalized }
}

function fsyncDirectory(directory) {
  let fd
  try {
    fd = fs.openSync(directory, "r")
    fs.fsyncSync(fd)
  } catch (error) {
    if (!error || !["EINVAL", "EPERM", "EISDIR"].includes(error.code)) throw error
  } finally {
    if (fd !== undefined) try { fs.closeSync(fd) } catch {}
  }
}

function writeTempJson(directory, prefix, document) {
  const temp = path.join(directory, `.${prefix}.${process.pid}.${crypto.randomUUID()}.tmp`)
  let fd
  try {
    fd = fs.openSync(temp, "wx", 0o600)
    fs.writeFileSync(fd, JSON.stringify(document, null, 2) + "\n", "utf8")
    fs.fsyncSync(fd)
    fs.closeSync(fd)
    fd = undefined
    return temp
  } catch (error) {
    if (fd !== undefined) try { fs.closeSync(fd) } catch {}
    if (fs.existsSync(temp)) try { fs.unlinkSync(temp) } catch {}
    throw error
  }
}

function createJsonExclusive(file, document) {
  const directory = path.dirname(file)
  fs.mkdirSync(directory, { recursive: true })
  const temp = writeTempJson(directory, path.basename(file), document)
  try {
    fs.linkSync(temp, file)
    fs.unlinkSync(temp)
    fsyncDirectory(directory)
  } catch (error) {
    if (fs.existsSync(temp)) try { fs.unlinkSync(temp) } catch {}
    if (error && error.code === "EEXIST") fail("file-exists", `${file} 已存在`)
    throw error
  }
}

function replaceJsonAtomically(file, document) {
  const directory = path.dirname(file)
  const temp = writeTempJson(directory, path.basename(file), document)
  try {
    fs.renameSync(temp, file)
    fsyncDirectory(directory)
  } finally {
    if (fs.existsSync(temp)) try { fs.unlinkSync(temp) } catch {}
  }
}

function boundaryDigest(chapters) {
  return jsonSha256(chapters.map((item) => ({
    chapter: item.chapter,
    title: item.title,
    start_line: item.start_line,
    word_count: item.word_count,
  })))
}

function chapterInputSha(sourceSha, chapter, startLine, endLine) {
  return jsonSha256({ source_sha256: sourceSha, chapter, start_line: startLine, end_line: endLine })
}

function progressProjection(progressFile) {
  let validated
  try {
    validated = validateProgress(progressFile)
  } catch (error) {
    fail("invalid-progress", error && error.message ? error.message : "_progress.md 校验失败")
  }
  const chapters = validated.chapters.map((item, index) => ({
    ...item,
    end_line: index + 1 < validated.chapters.length
      ? validated.chapters[index + 1].start_line - 1
      : validated.source.line_count,
  }))
  return { ...validated, chapters, boundary_sha256: boundaryDigest(validated.chapters) }
}

function stageRecord(status = "pending") {
  return { status, attempts: status === "completed" ? 1 : 0, started_at: null, completed_at: null, error: null }
}

function buildManifest(progressFile, manifestFile) {
  const progressPath = path.resolve(progressFile)
  const manifestPath = path.resolve(manifestFile)
  if (path.dirname(progressPath) !== path.dirname(manifestPath)) {
    fail("manifest-location", `_analysis-manifest.json 必须与 _progress.md 位于同一目录`)
  }
  const projection = progressProjection(progressPath)
  const createdAt = nowIso()
  const stages = Object.fromEntries(STAGE_IDS.map((id) => [id, stageRecord(id === "0" ? "completed" : "pending")]))
  stages["0"].started_at = createdAt
  stages["0"].completed_at = createdAt
  const chapters = {}
  for (const item of projection.chapters) {
    chapters[String(item.chapter)] = {
      input_sha256: chapterInputSha(projection.source.sha256, item.chapter, item.start_line, item.end_line),
      attempts: [],
    }
  }
  return {
    schema_version: SCHEMA_VERSION,
    manifest_revision: 1,
    created_at: createdAt,
    updated_at: createdAt,
    progress_path: path.basename(progressPath),
    source: { ...projection.source },
    chapter_boundary_sha256: projection.boundary_sha256,
    stages,
    stage2: { chapters },
    result_sets: [],
    head_revision: 0,
  }
}

function currentAttempt(chapterRecord) {
  return chapterRecord.attempts.length ? chapterRecord.attempts[chapterRecord.attempts.length - 1] : null
}

function chapterOutputPath(chapter) {
  return `章节/第${chapter}章_摘要.md`
}

function relationshipResultPath(revision) {
  return `_analysis/results/relationships-v${String(revision).padStart(4, "0")}.json`
}

function validateStageRecord(value, stage) {
  requireObject(value, "invalid-manifest", `stages.${stage}`)
  exactKeys(value, ["status", "attempts", "started_at", "completed_at", "error"], "invalid-manifest", `stages.${stage}`)
  if (!STAGE_STATUSES.has(value.status)) fail("invalid-manifest", `stages.${stage}.status 无效`)
  if (!Number.isInteger(value.attempts) || value.attempts < 0) fail("invalid-manifest", `stages.${stage}.attempts 无效`)
  for (const key of ["started_at", "completed_at", "error"]) {
    if (value[key] !== null && typeof value[key] !== "string") fail("invalid-manifest", `stages.${stage}.${key} 无效`)
  }
  if (new Set(["completed", "completed_with_errors"]).has(value.status) && !value.completed_at) {
    fail("invalid-manifest", `stages.${stage} 已完成但缺少 completed_at`)
  }
  if (new Set(["failed", "completed_with_errors"]).has(value.status) && !value.error) {
    fail("invalid-manifest", `stages.${stage} 状态要求 error 摘要`)
  }
}

function verifyLatestChapterOutput(base, chapter, chapterRecord) {
  const latest = currentAttempt(chapterRecord)
  if (!latest || latest.status !== "success") return
  const target = containedFile(base, latest.output.path, { code: "chapter-output-changed", label: `第 ${chapter} 章输出` })
  const actual = sha256(fs.readFileSync(target.absolute))
  if (actual !== latest.output.sha256) fail("chapter-output-changed", `第 ${chapter} 章输出 SHA-256 已变化`)
}

function validateChapterRecord(value, chapter, inputSha, base, options = {}) {
  const { verifyArtifacts = true } = options
  requireObject(value, "invalid-manifest", `stage2.chapters.${chapter}`)
  exactKeys(value, ["input_sha256", "attempts"], "invalid-manifest", `stage2.chapters.${chapter}`)
  if (value.input_sha256 !== inputSha) fail("chapter-input-changed", `第 ${chapter} 章输入指纹不匹配`)
  if (!Array.isArray(value.attempts)) fail("invalid-manifest", `第 ${chapter} 章 attempts 必须是数组`)
  value.attempts.forEach((attempt, index) => {
    requireObject(attempt, "invalid-manifest", `第 ${chapter} 章 attempt ${index + 1}`)
    if (attempt.status === "success") {
      exactKeys(attempt, ["attempt", "status", "at", "output"], "invalid-manifest", `第 ${chapter} 章成功尝试`)
      requireObject(attempt.output, "invalid-manifest", `第 ${chapter} 章输出`)
      exactKeys(attempt.output, ["path", "sha256"], "invalid-manifest", `第 ${chapter} 章输出`)
      const outputPath = normalizeRelativePath(attempt.output.path, "invalid-manifest", `第 ${chapter} 章输出路径`)
      if (outputPath !== chapterOutputPath(chapter)) {
        fail("invalid-manifest", `第 ${chapter} 章输出路径必须是 ${chapterOutputPath(chapter)}`)
      }
      requireSha(attempt.output.sha256, "invalid-manifest", `第 ${chapter} 章输出 SHA-256`)
    } else if (attempt.status === "failed") {
      exactKeys(attempt, ["attempt", "status", "at", "error"], "invalid-manifest", `第 ${chapter} 章失败尝试`)
      requireString(attempt.error, "invalid-manifest", `第 ${chapter} 章失败信息`)
    } else {
      fail("invalid-manifest", `第 ${chapter} 章尝试状态无效`)
    }
    if (attempt.attempt !== index + 1 || typeof attempt.at !== "string" || !attempt.at) {
      fail("invalid-manifest", `第 ${chapter} 章尝试序号或时间无效`)
    }
  })
  if (verifyArtifacts) verifyLatestChapterOutput(base, chapter, value)
}

function lineRangeEvidence(base, raw, options = {}) {
  const { verifyExpected = null } = options
  requireObject(raw, "invalid-evidence", "evidence")
  const allowed = verifyExpected
    ? ["path", "chapter", "start_line", "end_line", "file_sha256", "range_sha256"]
    : ["path", "chapter", "start_line", "end_line"]
  exactKeys(raw, allowed, "invalid-evidence", "evidence")
  if (!Number.isInteger(raw.chapter) || raw.chapter < 1) fail("invalid-evidence", "evidence.chapter 必须是正整数")
  if (!Number.isInteger(raw.start_line) || !Number.isInteger(raw.end_line) || raw.start_line < 1 || raw.end_line < raw.start_line) {
    fail("invalid-evidence", "evidence 行号必须是有效的 1-based 闭区间")
  }
  const target = containedFile(base, raw.path, { code: "invalid-evidence", label: "证据文件" })
  const bytes = fs.readFileSync(target.absolute)
  const text = bytes.toString("utf8")
  const lines = text.split(/\r\n|\n|\r/)
  if (raw.end_line > lines.length) fail("invalid-evidence", `证据结束行 ${raw.end_line} 超出文件行数 ${lines.length}`)
  const selected = lines.slice(raw.start_line - 1, raw.end_line).join("\n")
  if (!selected.trim()) fail("invalid-evidence", "证据区间不能为空")
  const normalized = {
    path: target.relative,
    chapter: raw.chapter,
    start_line: raw.start_line,
    end_line: raw.end_line,
    file_sha256: sha256(bytes),
    range_sha256: sha256(selected),
  }
  if (verifyExpected) {
    if (raw.file_sha256 !== normalized.file_sha256 || raw.range_sha256 !== normalized.range_sha256) {
      fail("evidence-changed", `证据已变化：${target.relative}:${raw.start_line}-${raw.end_line}`)
    }
  }
  return normalized
}

function validateResultDocument(document, resultMeta, manifest, base) {
  requireObject(document, "invalid-result", "关系结果")
  exactKeys(document, [
    "schema_version", "revision", "created_at", "source_sha256", "chapter_boundary_sha256",
    "payload_sha256", "entities", "relationships",
  ], "invalid-result", "关系结果")
  if (document.schema_version !== SCHEMA_VERSION || document.revision !== resultMeta.revision) fail("invalid-result", "关系结果 schema/revision 无效")
  if (typeof document.created_at !== "string" || document.created_at !== resultMeta.created_at) {
    fail("invalid-result", "关系结果 created_at 与清单不匹配")
  }
  if (document.source_sha256 !== manifest.source.sha256 || document.chapter_boundary_sha256 !== manifest.chapter_boundary_sha256) {
    fail("invalid-result", "关系结果来源指纹不匹配")
  }
  if (!Array.isArray(document.entities) || !Array.isArray(document.relationships)) fail("invalid-result", "关系结果实体和关系必须是数组")
  const payload = { entities: document.entities, relationships: document.relationships }
  if (jsonSha256(payload) !== document.payload_sha256 || document.payload_sha256 !== resultMeta.payload_sha256) {
    fail("result-changed", `关系结果 revision ${document.revision} 内容指纹不匹配`)
  }
  const normalized = normalizeRelationsDraft(payload, manifest, base, { verifyEvidence: true })
  if (JSON.stringify(normalized) !== JSON.stringify(payload)) {
    fail("invalid-result", `关系结果 revision ${document.revision} 不是规范化结构`)
  }
}

function validateResultSets(manifest, base, options = {}) {
  const { verifyArtifacts = true } = options
  if (!Array.isArray(manifest.result_sets)) fail("invalid-manifest", "result_sets 必须是数组")
  if (!Number.isInteger(manifest.head_revision) || manifest.head_revision < 0) fail("invalid-manifest", "head_revision 无效")
  if (manifest.result_sets.length !== manifest.head_revision) fail("invalid-manifest", "result_sets 数量必须等于 head_revision")
  manifest.result_sets.forEach((meta, index) => {
    requireObject(meta, "invalid-manifest", `result_sets.${index}`)
    exactKeys(meta, ["revision", "path", "sha256", "payload_sha256", "entity_count", "relationship_count", "created_at"], "invalid-manifest", `result_sets.${index}`)
    if (meta.revision !== index + 1) fail("invalid-manifest", "result revision 必须从 1 连续递增")
    requireSha(meta.sha256, "invalid-manifest", "result sha256")
    requireSha(meta.payload_sha256, "invalid-manifest", "result payload_sha256")
    const resultPath = normalizeRelativePath(meta.path, "invalid-manifest", `result_sets.${index}.path`)
    if (resultPath !== relationshipResultPath(meta.revision)) {
      fail("invalid-manifest", `result revision ${meta.revision} 路径不符合版本契约`)
    }
    if (typeof meta.created_at !== "string" || !meta.created_at) fail("invalid-manifest", "result created_at 无效")
    if (!Number.isInteger(meta.entity_count) || meta.entity_count < 0 || !Number.isInteger(meta.relationship_count) || meta.relationship_count < 0) {
      fail("invalid-manifest", "result 数量摘要无效")
    }
    if (!verifyArtifacts) return
    const target = containedFile(base, meta.path, { code: "result-changed", label: `关系结果 revision ${meta.revision}` })
    const bytes = fs.readFileSync(target.absolute)
    if (sha256(bytes) !== meta.sha256) fail("result-changed", `关系结果 revision ${meta.revision} 文件 SHA-256 已变化`)
    const parsed = readJson(target.absolute, "result").value
    validateResultDocument(parsed, meta, manifest, base)
    if (parsed.entities.length !== meta.entity_count || parsed.relationships.length !== meta.relationship_count) {
      fail("invalid-manifest", `关系结果 revision ${meta.revision} 数量摘要不匹配`)
    }
  })
}

function validateManifestDocument(manifest, manifestFile, options = {}) {
  const { verifyArtifacts = true } = options
  requireObject(manifest, "invalid-manifest", "分析清单")
  exactKeys(manifest, [
    "schema_version", "manifest_revision", "created_at", "updated_at", "progress_path", "source",
    "chapter_boundary_sha256", "stages", "stage2", "result_sets", "head_revision",
  ], "invalid-manifest", "分析清单")
  if (manifest.schema_version !== SCHEMA_VERSION) fail("old-schema", `只接受 schema_version=${SCHEMA_VERSION}`)
  if (!Number.isInteger(manifest.manifest_revision) || manifest.manifest_revision < 1) fail("invalid-manifest", "manifest_revision 无效")
  if (typeof manifest.created_at !== "string" || typeof manifest.updated_at !== "string") fail("invalid-manifest", "清单时间字段无效")
  requireSha(manifest.chapter_boundary_sha256, "invalid-manifest", "chapter_boundary_sha256")
  const base = path.dirname(path.resolve(manifestFile))
  const progressTarget = containedFile(base, manifest.progress_path, { code: "invalid-progress", label: "progress_path" })
  const projection = progressProjection(progressTarget.absolute)
  requireObject(manifest.source, "invalid-manifest", "source")
  exactKeys(manifest.source, ["path", "bytes", "sha256", "line_count"], "invalid-manifest", "source")
  if (
    manifest.source.path !== projection.source.path ||
    manifest.source.bytes !== projection.source.bytes ||
    manifest.source.sha256 !== projection.source.sha256 ||
    manifest.source.line_count !== projection.source.line_count ||
    manifest.chapter_boundary_sha256 !== projection.boundary_sha256
  ) fail("source-mismatch", "分析清单与当前 _progress.md 来源或章节边界不匹配")
  requireObject(manifest.stages, "invalid-manifest", "stages")
  exactKeys(manifest.stages, STAGE_IDS, "invalid-manifest", "stages")
  for (const stage of STAGE_IDS) validateStageRecord(manifest.stages[stage], stage)
  requireObject(manifest.stage2, "invalid-manifest", "stage2")
  exactKeys(manifest.stage2, ["chapters"], "invalid-manifest", "stage2")
  requireObject(manifest.stage2.chapters, "invalid-manifest", "stage2.chapters")
  const chapterKeys = projection.chapters.map((item) => String(item.chapter))
  exactKeys(manifest.stage2.chapters, chapterKeys, "invalid-manifest", "stage2.chapters")
  for (const item of projection.chapters) {
    const expectedInput = chapterInputSha(projection.source.sha256, item.chapter, item.start_line, item.end_line)
    validateChapterRecord(
      manifest.stage2.chapters[String(item.chapter)],
      item.chapter,
      expectedInput,
      base,
      { verifyArtifacts },
    )
  }
  validateStage2Completion(manifest)
  validateResultSets(manifest, base, { verifyArtifacts })
  return manifest
}

function readValidatedManifest(manifestFile, options = {}) {
  const manifestPath = path.resolve(manifestFile)
  const manifest = readJson(manifestPath, "manifest").value
  return validateManifestDocument(manifest, manifestPath, options)
}

function validateManifest(manifestFile) {
  return readValidatedManifest(manifestFile)
}

function initManifest(progressFile, manifestFile = null) {
  const progressPath = path.resolve(progressFile)
  const manifestPath = path.resolve(manifestFile || path.join(path.dirname(progressPath), "_analysis-manifest.json"))
  const expected = buildManifest(progressPath, manifestPath)
  if (fs.existsSync(manifestPath)) {
    const existing = validateManifest(manifestPath)
    if (existing.source.sha256 !== expected.source.sha256 || existing.chapter_boundary_sha256 !== expected.chapter_boundary_sha256) {
      fail("source-mismatch", "已有分析清单属于不同来源或章节边界")
    }
    return { created: false, manifest: existing, path: manifestPath }
  }
  createJsonExclusive(manifestPath, expected)
  return { created: true, manifest: expected, path: manifestPath }
}

function claimPath(manifestPath, targetRevision) {
  return path.join(path.dirname(manifestPath), `.analysis-manifest-cas-${targetRevision}`)
}

function ownClaim(file, claimId) {
  if (!fs.existsSync(file)) return false
  try { return readJson(file, "claim").value.claim_id === claimId } catch { return false }
}

function withManifestClaim(manifestFile, operation, options = {}) {
  const { verifyArtifacts = true } = options
  const manifestPath = path.resolve(manifestFile)
  const current = readValidatedManifest(manifestPath, { verifyArtifacts })
  const targetRevision = current.manifest_revision + 1
  const file = claimPath(manifestPath, targetRevision)
  const claimId = crypto.randomUUID()
  const claim = {
    schema_version: 1,
    target_revision: targetRevision,
    claim_id: claimId,
    pid: process.pid,
    hostname: os.hostname(),
    created_at: nowIso(),
  }
  try {
    createJsonExclusive(file, claim)
  } catch (error) {
    if (error instanceof AnalysisManifestError && error.code === "file-exists") {
      fail("claim-conflict", `manifest revision ${targetRevision} 已被其它写入者申领`)
    }
    throw error
  }
  try {
    const fresh = readValidatedManifest(manifestPath, { verifyArtifacts })
    if (fresh.manifest_revision !== current.manifest_revision) {
      fail("revision-conflict", `期望 manifest revision ${current.manifest_revision}，当前 ${fresh.manifest_revision}`)
    }
    return operation(fresh, { manifestPath, targetRevision, claimId, verifyArtifacts })
  } finally {
    if (ownClaim(file, claimId)) try { fs.unlinkSync(file) } catch {}
  }
}

function commitManifest(manifest, context) {
  manifest.manifest_revision = context.targetRevision
  manifest.updated_at = nowIso()
  validateManifestDocument(manifest, context.manifestPath, { verifyArtifacts: context.verifyArtifacts })
  replaceJsonAtomically(context.manifestPath, manifest)
  return manifest
}

function requireStage(value) {
  const stage = String(value)
  if (!STAGE_IDS.includes(stage)) fail("invalid-stage", "stage 必须是 0..6")
  return stage
}

function beginStage(manifestFile, stageValue) {
  const stage = requireStage(stageValue)
  return withManifestClaim(manifestFile, (manifest, context) => {
    const record = manifest.stages[stage]
    if (record.status === "completed" || record.status === "running") return { changed: false, manifest }
    record.status = "running"
    record.attempts += 1
    record.started_at = nowIso()
    record.completed_at = null
    record.error = null
    return { changed: true, manifest: commitManifest(manifest, context) }
  })
}

function recordChapter(manifestFile, chapterValue, status, options = {}) {
  const chapter = Number(chapterValue)
  if (!Number.isInteger(chapter) || chapter < 1) fail("invalid-chapter", "chapter 必须是正整数")
  if (!new Set(["success", "failed"]).has(status)) fail("invalid-status", "章节状态必须是 success/failed")
  return withManifestClaim(manifestFile, (manifest, context) => {
    if (manifest.stages["2"].status !== "running") fail("stage-not-running", "记录章节前必须 begin-stage 2")
    const record = manifest.stage2.chapters[String(chapter)]
    if (!record) fail("invalid-chapter", `章号 ${chapter} 不在章节边界表中`)
    const latest = currentAttempt(record)
    if (manifest.result_sets.length && latest && latest.status === "success" && status === "failed") {
      fail("chapter-result-locked", `关系结果已发布，第 ${chapter} 章不能改为失败`)
    }
    let attempt
    if (status === "success") {
      const base = path.dirname(context.manifestPath)
      const target = containedFile(base, options.output, { code: "invalid-output", label: "章节输出" })
      if (target.relative !== chapterOutputPath(chapter)) {
        fail("invalid-output", `第 ${chapter} 章输出路径必须是 ${chapterOutputPath(chapter)}`)
      }
      const output = { path: target.relative, sha256: sha256(fs.readFileSync(target.absolute)) }
      if (latest && latest.status === "success" && latest.output.path === output.path && latest.output.sha256 === output.sha256) {
        return { changed: false, manifest }
      }
      if (manifest.result_sets.length && latest && latest.status === "success") {
        fail("chapter-result-locked", `关系结果已发布，第 ${chapter} 章不能替换成功输出`)
      }
      attempt = { attempt: record.attempts.length + 1, status, at: nowIso(), output }
    } else {
      attempt = {
        attempt: record.attempts.length + 1,
        status,
        at: nowIso(),
        error: requireString(options.error, "invalid-error", "错误摘要"),
      }
    }
    record.attempts.push(attempt)
    return { changed: true, manifest: commitManifest(manifest, context) }
  }, { verifyArtifacts: false })
}

function stage2Summary(manifest) {
  const pending = []
  const failed = []
  const completed = []
  for (const chapter of Object.keys(manifest.stage2.chapters).map(Number).sort((a, b) => a - b)) {
    const latest = currentAttempt(manifest.stage2.chapters[String(chapter)])
    if (!latest) pending.push(chapter)
    else if (latest.status === "failed") failed.push(chapter)
    else completed.push(chapter)
  }
  return {
    stage: 2,
    status: manifest.stages["2"].status,
    pending_chapters: pending,
    failed_chapters: failed,
    completed_chapters: completed,
  }
}

function validateStage2Completion(manifest) {
  const record = manifest.stages["2"]
  const summary = stage2Summary(manifest)
  if (record.status === "completed" && (summary.pending_chapters.length || summary.failed_chapters.length)) {
    fail("invalid-manifest", "Stage 2 completed 但仍有待处理或失败章节")
  }
  if (record.status === "completed_with_errors") {
    if (summary.pending_chapters.length || !summary.failed_chapters.length) {
      fail("invalid-manifest", "Stage 2 completed_with_errors 必须没有待处理章节且至少有一个失败章节")
    }
    const expectedError = `失败章节: ${summary.failed_chapters.join(", ")}`
    if (record.error !== expectedError) fail("invalid-manifest", "Stage 2 部分失败摘要与逐章状态不匹配")
  }
}

function resumeStage2(manifestFile) {
  return stage2Summary(validateManifest(manifestFile))
}

function completeStage(manifestFile, stageValue, options = {}) {
  const stage = requireStage(stageValue)
  return withManifestClaim(manifestFile, (manifest, context) => {
    const record = manifest.stages[stage]
    if (record.status === "completed" || record.status === "completed_with_errors") {
      return { changed: false, manifest }
    }
    if (record.status !== "running") fail("stage-not-running", `Stage ${stage} 必须处于 running`)
    if (stage === "2") {
      const summary = stage2Summary(manifest)
      if (summary.pending_chapters.length) {
        fail("stage-incomplete", `Stage 2 仍有待处理 ${summary.pending_chapters.length} 章、失败 ${summary.failed_chapters.length} 章`)
      }
      if (summary.failed_chapters.length && !options.allowFailures) {
        fail("stage-incomplete", `Stage 2 仍有失败 ${summary.failed_chapters.length} 章；确认继续时使用 --allow-failures`)
      }
      if (summary.failed_chapters.length) {
        record.status = "completed_with_errors"
        record.completed_at = nowIso()
        record.error = `失败章节: ${summary.failed_chapters.join(", ")}`
        return { changed: true, manifest: commitManifest(manifest, context) }
      }
    }
    record.status = "completed"
    record.completed_at = nowIso()
    record.error = null
    return { changed: true, manifest: commitManifest(manifest, context) }
  })
}

function failStage(manifestFile, stageValue, errorMessage) {
  const stage = requireStage(stageValue)
  return withManifestClaim(manifestFile, (manifest, context) => {
    const record = manifest.stages[stage]
    if (record.status === "completed" || record.status === "completed_with_errors") {
      fail("stage-completed", `Stage ${stage} 已完成，不能标记失败`)
    }
    record.status = "failed"
    record.completed_at = null
    record.error = requireString(errorMessage, "invalid-error", "错误摘要")
    return { changed: true, manifest: commitManifest(manifest, context) }
  })
}

function validReference(value, label) {
  const normalized = requireString(value, "invalid-entity", label, 100)
  if (RESERVED_KEYS.has(normalized) || /[\u0000-\u001f/\\]/.test(normalized)) fail("invalid-entity", `${label} 含非法字符`)
  return normalized
}

function normalizeRelationsDraft(raw, manifest, base, options = {}) {
  const { verifyEvidence = false } = options
  requireObject(raw, "invalid-draft", "关系草稿")
  exactKeys(raw, ["entities", "relationships"], "invalid-draft", "关系草稿")
  if (!Array.isArray(raw.entities) || !raw.entities.length || !Array.isArray(raw.relationships)) {
    fail("invalid-draft", "关系草稿必须包含非空 entities 和 relationships 数组")
  }
  const references = new Map()
  const claimedReferences = new Set()
  const entities = []
  const claimReference = (key, entityId, kind, resolvable = true) => {
    if (claimedReferences.has(key)) fail("duplicate-reference", `${kind} 重复或与其它实体冲突：${key}`)
    claimedReferences.add(key)
    if (resolvable) references.set(key, entityId)
  }
  raw.entities.forEach((item) => {
    requireObject(item, "invalid-entity", "entity")
    exactKeys(item, ["id", "name", "type", "confidence", "aliases"], "invalid-entity", "entity")
    const id = validReference(item.id, "entity.id")
    const name = validReference(item.name, "entity.name")
    const type = requireString(item.type, "invalid-entity", "entity.type", 100)
    const confidence = requireConfidence(item.confidence, "invalid-confidence", "entity.confidence")
    if (!Array.isArray(item.aliases)) fail("invalid-alias", "entity.aliases 必须是数组")
    claimReference(id, id, "entity.id")
    if (name !== id) claimReference(name, id, "entity.name")
    const aliases = item.aliases.map((alias) => {
      requireObject(alias, "invalid-alias", "alias")
      exactKeys(alias, ["name", "kind", "confidence"], "invalid-alias", "alias")
      const aliasName = validReference(alias.name, "alias.name")
      if (!ALIAS_KINDS.has(alias.kind)) fail("invalid-alias", `alias.kind 无效：${alias.kind}`)
      const aliasConfidence = requireConfidence(alias.confidence, "invalid-confidence", "alias.confidence")
      claimReference(
        aliasName,
        id,
        "alias",
        RESOLVABLE_ALIAS_KINDS.has(alias.kind) && aliasConfidence >= 0.85,
      )
      return { name: aliasName, kind: alias.kind, confidence: aliasConfidence }
    }).sort((left, right) => compareCodePoints(left.name, right.name))
    entities.push({ id, name, type, confidence, aliases })
  })
  entities.sort((left, right) => compareCodePoints(left.id, right.id))
  const relationKeys = new Set()
  const relationships = raw.relationships.map((item) => {
    requireObject(item, "invalid-relationship", "relationship")
    exactKeys(item, ["source", "target", "type", "direction", "sentiment", "description", "confidence", "evidence"], "invalid-relationship", "relationship")
    const rawSource = validReference(item.source, "relationship.source")
    const rawTarget = validReference(item.target, "relationship.target")
    if (!references.has(rawSource) || !references.has(rawTarget)) fail("unknown-entity", `关系端点无法解析：${rawSource} / ${rawTarget}`)
    let source = references.get(rawSource)
    let target = references.get(rawTarget)
    if (!DIRECTIONS.has(item.direction)) fail("invalid-relationship", `relationship.direction 无效：${item.direction}`)
    if (item.direction === "undirected" && compareCodePoints(source, target) > 0) [source, target] = [target, source]
    if (source === target) fail("self-loop", `别名归一后形成自环：${source}`)
    const type = requireString(item.type, "invalid-relationship", "relationship.type", 100)
    const sentiment = requireString(item.sentiment, "invalid-relationship", "relationship.sentiment", 100)
    const description = requireString(item.description, "invalid-relationship", "relationship.description", 2000)
    const confidence = requireConfidence(item.confidence, "invalid-confidence", "relationship.confidence")
    if (!Array.isArray(item.evidence) || !item.evidence.length) fail("missing-evidence", "每条关系至少需要一条证据")
    const evidenceKeys = new Set()
    const evidence = item.evidence.map((entry) => {
      const normalized = lineRangeEvidence(base, entry, { verifyExpected: verifyEvidence })
      const chapterRecord = manifest.stage2.chapters[String(normalized.chapter)]
      const latest = chapterRecord && currentAttempt(chapterRecord)
      if (!latest || latest.status !== "success") {
        fail("invalid-evidence", `证据章号 ${normalized.chapter} 没有成功的 Stage 2 输出`)
      }
      if (latest.output.path !== normalized.path) {
        fail("invalid-evidence", `证据路径必须是第 ${normalized.chapter} 章的 Stage 2 输出 ${latest.output.path}`)
      }
      if (latest.output.sha256 !== normalized.file_sha256) {
        fail("evidence-changed", `证据文件与第 ${normalized.chapter} 章 Stage 2 输出指纹不匹配`)
      }
      const key = `${normalized.path}\u0000${normalized.start_line}\u0000${normalized.end_line}`
      if (evidenceKeys.has(key)) fail("duplicate-evidence", `关系证据重复：${normalized.path}:${normalized.start_line}-${normalized.end_line}`)
      evidenceKeys.add(key)
      return normalized
    }).sort((left, right) => left.chapter - right.chapter || compareCodePoints(left.path, right.path) || left.start_line - right.start_line)
    const key = `${source}\u0000${target}\u0000${type}\u0000${item.direction}`
    if (relationKeys.has(key)) fail("duplicate-relationship", `关系重复：${source} / ${target} / ${type}`)
    relationKeys.add(key)
    return { source, target, type, direction: item.direction, sentiment, description, confidence, evidence }
  }).sort((left, right) => (
    compareCodePoints(left.source, right.source) || compareCodePoints(left.target, right.target) ||
    compareCodePoints(left.type, right.type) || compareCodePoints(left.direction, right.direction)
  ))
  return { entities, relationships }
}

function publishRelations(manifestFile, draftFile) {
  const manifestPath = path.resolve(manifestFile)
  const base = path.dirname(manifestPath)
  const draftTarget = containedFile(base, path.relative(base, path.resolve(draftFile)).replace(/\\/g, "/"), { code: "invalid-draft", label: "关系草稿" })
  const rawDraft = readJson(draftTarget.absolute, "draft").value
  return withManifestClaim(manifestPath, (manifest, context) => {
    if (manifest.stages["4"].status !== "running") fail("stage-not-running", "发布关系结果前必须 begin-stage 4")
    const payload = normalizeRelationsDraft(rawDraft, manifest, base)
    const payloadSha = jsonSha256(payload)
    const head = manifest.result_sets[manifest.result_sets.length - 1]
    if (head && head.payload_sha256 === payloadSha) {
      return { deduplicated: true, revision: head.revision, path: head.path, manifest }
    }
    const revision = manifest.head_revision + 1
    const createdAt = nowIso()
    const document = {
      schema_version: SCHEMA_VERSION,
      revision,
      created_at: createdAt,
      source_sha256: manifest.source.sha256,
      chapter_boundary_sha256: manifest.chapter_boundary_sha256,
      payload_sha256: payloadSha,
      entities: payload.entities,
      relationships: payload.relationships,
    }
    const resultRelative = relationshipResultPath(revision)
    const resultTarget = containedFile(base, resultRelative, { code: "invalid-result", label: "关系结果", mustExist: false })
    createJsonExclusive(resultTarget.absolute, document)
    let committed = false
    try {
      const resultBytes = fs.readFileSync(resultTarget.absolute)
      manifest.result_sets.push({
        revision,
        path: resultRelative,
        sha256: sha256(resultBytes),
        payload_sha256: payloadSha,
        entity_count: payload.entities.length,
        relationship_count: payload.relationships.length,
        created_at: createdAt,
      })
      manifest.head_revision = revision
      commitManifest(manifest, context)
      committed = true
      return { deduplicated: false, revision, path: resultRelative, manifest }
    } finally {
      if (!committed && fs.existsSync(resultTarget.absolute)) try { fs.unlinkSync(resultTarget.absolute) } catch {}
    }
  })
}

function releaseClaim(manifestFile, targetRevision, claimId, confirmed) {
  if (!confirmed) fail("confirmation-required", "必须确认对应写入者已停止")
  const manifestPath = path.resolve(manifestFile)
  const manifest = validateManifest(manifestPath)
  if (!Number.isInteger(targetRevision) || targetRevision !== manifest.manifest_revision + 1) {
    fail("revision-conflict", `只能释放下一个 revision ${manifest.manifest_revision + 1} 的申领`)
  }
  const file = claimPath(manifestPath, targetRevision)
  const claim = readJson(file, "claim").value
  if (claim.claim_id !== claimId || claim.target_revision !== targetRevision) fail("claim-mismatch", "claim_id 或 target revision 不匹配")
  fs.unlinkSync(file)
  return { released: true, target_revision: targetRevision }
}

function parseArguments(argv) {
  const args = [...argv]
  const command = args.shift()
  const positionals = []
  const values = {}
  const flags = new Set()
  const allowedValues = new Set(["output", "error", "claim-id"])
  const allowedFlags = new Set(["allow-failures", "confirm-writer-stopped"])
  while (args.length) {
    const token = args.shift()
    if (!token.startsWith("--")) {
      positionals.push(token)
      continue
    }
    const key = token.slice(2)
    if (allowedFlags.has(key)) {
      if (flags.has(key)) fail("cli", `重复参数 ${token}`)
      flags.add(key)
      continue
    }
    if (!allowedValues.has(key) || Object.hasOwn(values, key)) fail("cli", `未知或重复参数 ${token}`)
    const value = args.shift()
    if (!value || value.startsWith("--")) fail("cli", `${token} 缺少值`)
    values[key] = value
  }
  return { command, positionals, values, flags }
}

function requirePositionals(positionals, minimum, maximum = minimum) {
  if (positionals.length < minimum || positionals.length > maximum) fail("cli", `位置参数数量必须是 ${minimum}${maximum === minimum ? "" : `-${maximum}`}`)
}

function main(argv) {
  try {
    const { command, positionals, values, flags } = parseArguments(argv)
    let output
    if (command === "init") {
      requirePositionals(positionals, 1, 2)
      output = initManifest(positionals[0], positionals[1])
    } else if (command === "validate") {
      requirePositionals(positionals, 1)
      output = validateManifest(positionals[0])
    } else if (command === "begin-stage") {
      requirePositionals(positionals, 2)
      output = beginStage(positionals[0], positionals[1])
    } else if (command === "record-chapter") {
      requirePositionals(positionals, 3)
      output = recordChapter(positionals[0], positionals[1], positionals[2], values)
    } else if (command === "resume") {
      requirePositionals(positionals, 1)
      output = resumeStage2(positionals[0])
    } else if (command === "complete-stage") {
      requirePositionals(positionals, 2)
      output = completeStage(positionals[0], positionals[1], { allowFailures: flags.has("allow-failures") })
    } else if (command === "fail-stage") {
      requirePositionals(positionals, 2)
      output = failStage(positionals[0], positionals[1], values.error)
    } else if (command === "publish-relations") {
      requirePositionals(positionals, 2)
      output = publishRelations(positionals[0], positionals[1])
    } else if (command === "release-claim") {
      requirePositionals(positionals, 2)
      output = releaseClaim(positionals[0], Number(positionals[1]), values["claim-id"], flags.has("confirm-writer-stopped"))
    } else {
      fail("cli", "命令必须是 init/validate/begin-stage/record-chapter/resume/complete-stage/fail-stage/publish-relations/release-claim")
    }
    process.stdout.write(JSON.stringify(output, null, 2) + "\n")
    return 0
  } catch (error) {
    if (error instanceof AnalysisManifestError) {
      process.stderr.write(`ERROR [${error.code}] ${error.message}\n`)
      return 1
    }
    throw error
  }
}

if (require.main === module) process.exitCode = main(process.argv.slice(2))

module.exports = {
  AnalysisManifestError,
  SCHEMA_VERSION,
  beginStage,
  completeStage,
  failStage,
  initManifest,
  normalizeRelationsDraft,
  publishRelations,
  recordChapter,
  releaseClaim,
  resumeStage2,
  validateManifest,
}
