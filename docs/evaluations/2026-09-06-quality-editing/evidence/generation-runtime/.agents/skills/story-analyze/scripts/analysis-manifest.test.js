"use strict"

const assert = require("node:assert/strict")
const crypto = require("node:crypto")
const fs = require("node:fs")
const os = require("node:os")
const path = require("node:path")
const test = require("node:test")

const manifestApi = require("./analysis-manifest.js")

function hash(value) {
  return crypto.createHash("sha256").update(value).digest("hex")
}

function fixture() {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "story-analysis-manifest-"))
  fs.mkdirSync(path.join(root, "原文"))
  fs.mkdirSync(path.join(root, "章节"))
  fs.mkdirSync(path.join(root, "_analysis"))
  const source = "第一章 开端\n正文一\n第二章 转折\n正文二\n第三章 收束\n正文三\n"
  const sourceFile = path.join(root, "原文", "原文.txt")
  fs.writeFileSync(sourceFile, source)
  const bytes = Buffer.from(source)
  const progress = [
    "# 深度拆解进度：测试",
    "- schema_version: 3",
    "- source_path: 原文/原文.txt",
    `- source_bytes: ${bytes.length}`,
    `- source_sha256: ${hash(bytes)}`,
    "## 章节边界（Stage 0 章节边界子步骤产物，唯一权威）",
    "| 章号 | 标题 | 起始行 | 字数 |",
    "|------|------|--------|------|",
    "| 1 | 开端 | 1 | 100 |",
    "| 2 | 转折 | 3 | 120 |",
    "| 3 | 收束 | 5 | 90 |",
    "## 分块进度",
  ].join("\n")
  const progressFile = path.join(root, "_progress.md")
  const manifestFile = path.join(root, "_analysis-manifest.json")
  fs.writeFileSync(progressFile, progress)
  for (let chapter = 1; chapter <= 3; chapter += 1) {
    fs.writeFileSync(
      path.join(root, "章节", `第${chapter}章_摘要.md`),
      [`# 第${chapter}章`, `林雷与德林相遇，关系发生变化 ${chapter}。`, "后续证据。", ""].join("\n"),
    )
  }
  return { root, sourceFile, progressFile, manifestFile }
}

function expectCode(fn, code) {
  assert.throws(fn, (error) => error instanceof manifestApi.AnalysisManifestError && error.code === code)
}

function readJson(file) {
  return JSON.parse(fs.readFileSync(file, "utf8"))
}

function writeJson(file, value) {
  fs.writeFileSync(file, JSON.stringify(value, null, 2) + "\n")
}

function init(item = fixture()) {
  manifestApi.initManifest(item.progressFile, item.manifestFile)
  return item
}

function successfulStage2(item) {
  manifestApi.beginStage(item.manifestFile, 2)
  for (let chapter = 1; chapter <= 3; chapter += 1) {
    manifestApi.recordChapter(
      item.manifestFile,
      chapter,
      "success",
      { output: `章节/第${chapter}章_摘要.md` },
    )
  }
  manifestApi.completeStage(item.manifestFile, 2)
}

function beginRelations(item = init()) {
  successfulStage2(item)
  manifestApi.beginStage(item.manifestFile, 4)
  return item
}

function draft(overrides = {}) {
  const base = {
    entities: [
      {
        id: "delin",
        name: "德林",
        type: "supporting",
        confidence: 0.98,
        aliases: [],
      },
      {
        id: "linlei",
        name: "林雷",
        type: "protagonist",
        confidence: 0.99,
        aliases: [
          { name: "龙血战士", kind: "nickname", confidence: 0.9 },
          { name: "少年", kind: "descriptor", confidence: 0.99 },
        ],
      },
    ],
    relationships: [
      {
        source: "龙血战士",
        target: "delin",
        type: "师徒",
        direction: "undirected",
        sentiment: "正面",
        description: "德林指导林雷修炼。",
        confidence: 0.94,
        evidence: [
          { path: "章节/第1章_摘要.md", chapter: 1, start_line: 2, end_line: 3 },
        ],
      },
    ],
  }
  return { ...base, ...overrides }
}

function writeDraft(item, value = draft()) {
  const file = path.join(item.root, "_analysis", "relations-draft.json")
  writeJson(file, value)
  return file
}

test("init 绑定来源与章节边界，重复执行保持历史", () => {
  const item = fixture()
  const first = manifestApi.initManifest(item.progressFile, item.manifestFile)
  assert.equal(first.created, true)
  assert.equal(first.manifest.schema_version, 1)
  assert.equal(first.manifest.manifest_revision, 1)
  assert.equal(Object.keys(first.manifest.stage2.chapters).length, 3)
  const second = manifestApi.initManifest(item.progressFile, item.manifestFile)
  assert.equal(second.created, false)
  assert.equal(second.manifest.manifest_revision, 1)
  assert.equal(manifestApi.validateManifest(item.manifestFile).source.sha256, hash(fs.readFileSync(item.sourceFile)))
})

test("manifest 必须与 progress 同目录", () => {
  const item = fixture()
  const external = fs.mkdtempSync(path.join(os.tmpdir(), "story-analysis-external-"))
  expectCode(() => manifestApi.initManifest(item.progressFile, path.join(external, "manifest.json")), "manifest-location")
})

test("原文或章节边界变化后拒绝继续", () => {
  const sourceChanged = init()
  fs.appendFileSync(sourceChanged.sourceFile, "新增\n")
  expectCode(() => manifestApi.validateManifest(sourceChanged.manifestFile), "invalid-progress")

  const boundaryChanged = init()
  const text = fs.readFileSync(boundaryChanged.progressFile, "utf8").replace("| 2 | 转折 | 3 | 120 |", "| 2 | 转折 | 4 | 120 |")
  fs.writeFileSync(boundaryChanged.progressFile, text)
  expectCode(() => manifestApi.validateManifest(boundaryChanged.manifestFile), "source-mismatch")
})

test("Stage 2 完成态必须与逐章尝试一致", () => {
  const item = init()
  const manifest = readJson(item.manifestFile)
  manifest.stages["2"].status = "completed"
  manifest.stages["2"].completed_at = new Date().toISOString()
  writeJson(item.manifestFile, manifest)
  expectCode(() => manifestApi.validateManifest(item.manifestFile), "invalid-manifest")
})

test("Stage 2 记录失败、重试、恢复集合与输出指纹", () => {
  const item = init()
  manifestApi.beginStage(item.manifestFile, 2)
  manifestApi.recordChapter(item.manifestFile, 1, "success", { output: "章节/第1章_摘要.md" })
  const afterFirst = readJson(item.manifestFile)
  const revisionAfterFirst = afterFirst.manifest_revision
  manifestApi.recordChapter(item.manifestFile, 1, "success", { output: "章节/第1章_摘要.md" })
  assert.equal(readJson(item.manifestFile).manifest_revision, revisionAfterFirst)
  manifestApi.recordChapter(item.manifestFile, 2, "failed", { error: "模型超时" })
  assert.deepEqual(manifestApi.resumeStage2(item.manifestFile), {
    stage: 2,
    status: "running",
    pending_chapters: [3],
    failed_chapters: [2],
    completed_chapters: [1],
  })
  expectCode(() => manifestApi.completeStage(item.manifestFile, 2), "stage-incomplete")
  manifestApi.recordChapter(item.manifestFile, 2, "success", { output: "章节/第2章_摘要.md" })
  manifestApi.recordChapter(item.manifestFile, 3, "success", { output: "章节/第3章_摘要.md" })
  const completed = manifestApi.completeStage(item.manifestFile, 2)
  assert.equal(completed.manifest.stages["2"].status, "completed")
  assert.equal(completed.manifest.stage2.chapters["2"].attempts.length, 2)
  fs.appendFileSync(path.join(item.root, "章节", "第2章_摘要.md"), "篡改")
  expectCode(() => manifestApi.validateManifest(item.manifestFile), "chapter-output-changed")
})

test("Stage 2 可显式保留失败章节并在后续恢复重试", () => {
  const item = init()
  manifestApi.beginStage(item.manifestFile, 2)
  manifestApi.recordChapter(item.manifestFile, 1, "success", { output: "章节/第1章_摘要.md" })
  manifestApi.recordChapter(item.manifestFile, 2, "failed", { error: "模型超时" })
  manifestApi.recordChapter(item.manifestFile, 3, "success", { output: "章节/第3章_摘要.md" })

  expectCode(() => manifestApi.completeStage(item.manifestFile, 2), "stage-incomplete")
  const partial = manifestApi.completeStage(item.manifestFile, 2, { allowFailures: true })
  assert.equal(partial.manifest.stages["2"].status, "completed_with_errors")
  assert.equal(partial.manifest.stages["2"].error, "失败章节: 2")
  assert.deepEqual(manifestApi.resumeStage2(item.manifestFile).failed_chapters, [2])

  const partialRevision = readJson(item.manifestFile).manifest_revision
  const repeated = manifestApi.completeStage(item.manifestFile, 2)
  assert.equal(repeated.changed, false)
  assert.equal(readJson(item.manifestFile).manifest_revision, partialRevision)
  expectCode(() => manifestApi.failStage(item.manifestFile, 2, "不能覆盖部分完成态"), "stage-completed")

  const resumed = manifestApi.beginStage(item.manifestFile, 2)
  assert.equal(resumed.manifest.stages["2"].status, "running")
  manifestApi.recordChapter(item.manifestFile, 2, "success", { output: "章节/第2章_摘要.md" })
  const completed = manifestApi.completeStage(item.manifestFile, 2)
  assert.equal(completed.manifest.stages["2"].status, "completed")
  assert.equal(completed.manifest.stages["2"].error, null)
})

test("章节记录要求 Stage 2 running，Stage 完成与失败转换受限", () => {
  const item = init()
  expectCode(
    () => manifestApi.recordChapter(item.manifestFile, 1, "failed", { error: "未开始" }),
    "stage-not-running",
  )
  manifestApi.beginStage(item.manifestFile, 3)
  manifestApi.failStage(item.manifestFile, 3, "聚合失败")
  assert.equal(readJson(item.manifestFile).stages["3"].status, "failed")
  manifestApi.beginStage(item.manifestFile, 3)
  manifestApi.completeStage(item.manifestFile, 3)
  expectCode(() => manifestApi.failStage(item.manifestFile, 3, "不能覆盖"), "stage-completed")
})

test("Stage 2 成功输出必须使用对应章节的固定路径", () => {
  const item = init()
  manifestApi.beginStage(item.manifestFile, 2)
  expectCode(
    () => manifestApi.recordChapter(item.manifestFile, 2, "success", { output: "章节/第1章_摘要.md" }),
    "invalid-output",
  )
  assert.equal(readJson(item.manifestFile).stage2.chapters["2"].attempts.length, 0)
})

test("逐章记录跳过旧产物重读，深度操作仍检测旧输出变化", () => {
  const item = init()
  manifestApi.beginStage(item.manifestFile, 2)
  manifestApi.recordChapter(item.manifestFile, 1, "success", { output: "章节/第1章_摘要.md" })
  fs.appendFileSync(path.join(item.root, "章节", "第1章_摘要.md"), "变化")
  manifestApi.recordChapter(item.manifestFile, 2, "success", { output: "章节/第2章_摘要.md" })
  assert.equal(readJson(item.manifestFile).stage2.chapters["2"].attempts.length, 1)
  expectCode(() => manifestApi.resumeStage2(item.manifestFile), "chapter-output-changed")
  expectCode(() => manifestApi.completeStage(item.manifestFile, 2), "chapter-output-changed")
})

test("并发申领阻止相同 manifest revision 被覆盖", () => {
  const item = init()
  const claim = path.join(item.root, ".analysis-manifest-cas-2")
  writeJson(claim, { schema_version: 1, target_revision: 2, claim_id: "other" })
  expectCode(() => manifestApi.beginStage(item.manifestFile, 1), "claim-conflict")
  assert.equal(readJson(item.manifestFile).manifest_revision, 1)
})

test("关系发布执行别名归一、无向端点规范化、证据指纹和内容去重", () => {
  const item = init()
  successfulStage2(item)
  manifestApi.beginStage(item.manifestFile, 4)
  const draftFile = writeDraft(item)
  const first = manifestApi.publishRelations(item.manifestFile, draftFile)
  assert.equal(first.deduplicated, false)
  assert.equal(first.revision, 1)
  const result = readJson(path.join(item.root, first.path))
  assert.equal(result.relationships[0].source, "delin")
  assert.equal(result.relationships[0].target, "linlei")
  assert.match(result.relationships[0].evidence[0].file_sha256, /^[a-f0-9]{64}$/)
  assert.match(result.relationships[0].evidence[0].range_sha256, /^[a-f0-9]{64}$/)
  const revisionAfterFirst = readJson(item.manifestFile).manifest_revision
  const same = manifestApi.publishRelations(item.manifestFile, draftFile)
  assert.equal(same.deduplicated, true)
  assert.equal(same.revision, 1)
  assert.equal(readJson(item.manifestFile).manifest_revision, revisionAfterFirst)

  const changed = draft()
  changed.relationships[0].description = "德林持续指导林雷修炼。"
  writeJson(draftFile, changed)
  const second = manifestApi.publishRelations(item.manifestFile, draftFile)
  assert.equal(second.revision, 2)
  assert.equal(readJson(item.manifestFile).head_revision, 2)
  assert.equal(manifestApi.validateManifest(item.manifestFile).result_sets.length, 2)
})

test("有向关系保留方向", () => {
  const item = beginRelations()
  const value = draft()
  value.relationships[0].source = "linlei"
  value.relationships[0].target = "delin"
  value.relationships[0].direction = "source_to_target"
  const published = manifestApi.publishRelations(item.manifestFile, writeDraft(item, value))
  const result = readJson(path.join(item.root, published.path))
  assert.equal(result.relationships[0].source, "linlei")
  assert.equal(result.relationships[0].target, "delin")
})

test("低置信或描述性别名不能解析为关系端点", () => {
  for (const alias of [
    { name: "低置信外号", kind: "nickname", confidence: 0.84 },
    { name: "少年", kind: "descriptor", confidence: 0.99 },
  ]) {
    const item = beginRelations()
    const value = draft()
    value.entities[1].aliases = [alias]
    value.relationships[0].source = alias.name
    expectCode(() => manifestApi.publishRelations(item.manifestFile, writeDraft(item, value)), "unknown-entity")
    assert.equal(fs.existsSync(path.join(item.root, "_analysis", "results")), false)
  }
})

test("别名归一后的自环与重复关系明确失败", () => {
  const selfLoopItem = beginRelations()
  const selfLoop = draft()
  selfLoop.relationships[0].target = "linlei"
  expectCode(() => manifestApi.publishRelations(selfLoopItem.manifestFile, writeDraft(selfLoopItem, selfLoop)), "self-loop")

  const duplicateItem = beginRelations()
  const duplicate = draft()
  duplicate.relationships.push({ ...duplicate.relationships[0], source: "linlei", target: "delin" })
  expectCode(() => manifestApi.publishRelations(duplicateItem.manifestFile, writeDraft(duplicateItem, duplicate)), "duplicate-relationship")
})

test("重复实体引用、非法置信度和缺失证据明确失败", () => {
  const duplicateItem = beginRelations()
  const duplicate = draft()
  duplicate.entities[1].aliases.push({ name: "德林", kind: "nickname", confidence: 0.9 })
  expectCode(() => manifestApi.publishRelations(duplicateItem.manifestFile, writeDraft(duplicateItem, duplicate)), "duplicate-reference")

  const lowAliasItem = beginRelations()
  const lowAlias = draft()
  lowAlias.entities[0].aliases = [{ name: "老人", kind: "descriptor", confidence: 0.7 }]
  lowAlias.entities[1].aliases = [{ name: "老人", kind: "title", confidence: 0.6 }]
  expectCode(() => manifestApi.publishRelations(lowAliasItem.manifestFile, writeDraft(lowAliasItem, lowAlias)), "duplicate-reference")

  const confidenceItem = beginRelations()
  const confidence = draft()
  confidence.relationships[0].confidence = 1.1
  expectCode(() => manifestApi.publishRelations(confidenceItem.manifestFile, writeDraft(confidenceItem, confidence)), "invalid-confidence")

  const evidenceItem = beginRelations()
  const noEvidence = draft()
  noEvidence.relationships[0].evidence = []
  expectCode(() => manifestApi.publishRelations(evidenceItem.manifestFile, writeDraft(evidenceItem, noEvidence)), "missing-evidence")
})

test("证据越界、空区间和目录逃出明确失败", () => {
  const cases = [
    { evidence: { path: "章节/第1章_摘要.md", chapter: 1, start_line: 99, end_line: 99 }, code: "invalid-evidence" },
    { evidence: { path: "章节/第1章_摘要.md", chapter: 1, start_line: 4, end_line: 4 }, code: "invalid-evidence" },
    { evidence: { path: "../外部.md", chapter: 1, start_line: 1, end_line: 1 }, code: "invalid-evidence" },
  ]
  for (const entry of cases) {
    const item = beginRelations()
    const value = draft()
    value.relationships[0].evidence = [entry.evidence]
    expectCode(() => manifestApi.publishRelations(item.manifestFile, writeDraft(item, value)), entry.code)
  }
})

test("证据符号链接不得指向目录外", (t) => {
  const item = beginRelations()
  const external = path.join(fs.mkdtempSync(path.join(os.tmpdir(), "story-evidence-external-")), "external.md")
  fs.writeFileSync(external, "外部证据\n")
  const link = path.join(item.root, "章节", "链接.md")
  try {
    fs.symlinkSync(external, link, "file")
  } catch (error) {
    if (error && ["EPERM", "EACCES"].includes(error.code)) return t.skip("当前系统不允许创建文件符号链接")
    throw error
  }
  const value = draft()
  value.relationships[0].evidence = [{ path: "章节/链接.md", chapter: 1, start_line: 1, end_line: 1 }]
  expectCode(() => manifestApi.publishRelations(item.manifestFile, writeDraft(item, value)), "invalid-evidence")
})

test("关系证据必须匹配同章的 Stage 2 摘要", () => {
  const item = beginRelations()
  const value = draft()
  value.relationships[0].evidence = [
    { path: "章节/第2章_摘要.md", chapter: 1, start_line: 2, end_line: 3 },
  ]
  expectCode(() => manifestApi.publishRelations(item.manifestFile, writeDraft(item, value)), "invalid-evidence")
})

test("关系结果目录不得通过符号链接或 junction 写到拆文目录外", (t) => {
  const item = beginRelations()
  const draftFile = writeDraft(item)
  const external = fs.mkdtempSync(path.join(os.tmpdir(), "story-results-external-"))
  const results = path.join(item.root, "_analysis", "results")
  try {
    fs.symlinkSync(external, results, process.platform === "win32" ? "junction" : "dir")
  } catch (error) {
    if (error && ["EPERM", "EACCES"].includes(error.code)) return t.skip("当前系统不允许创建目录链接")
    throw error
  }
  expectCode(() => manifestApi.publishRelations(item.manifestFile, draftFile), "invalid-result")
  assert.deepEqual(fs.readdirSync(external), [])
})

test("已发布结果即使重算哈希也必须通过结构重验证", () => {
  const item = beginRelations()
  const published = manifestApi.publishRelations(item.manifestFile, writeDraft(item))
  const resultFile = path.join(item.root, published.path)
  const result = readJson(resultFile)
  result.entities[0].aliases.push({ name: "非法别名", kind: "other", confidence: 0.9 })
  result.payload_sha256 = hash(JSON.stringify({ entities: result.entities, relationships: result.relationships }))
  writeJson(resultFile, result)
  const manifest = readJson(item.manifestFile)
  manifest.result_sets[0].payload_sha256 = result.payload_sha256
  manifest.result_sets[0].sha256 = hash(fs.readFileSync(resultFile))
  writeJson(item.manifestFile, manifest)
  expectCode(() => manifestApi.validateManifest(item.manifestFile), "invalid-alias")
})

test("结果元数据路径必须匹配连续修订文件名", () => {
  const item = beginRelations()
  const published = manifestApi.publishRelations(item.manifestFile, writeDraft(item))
  const alternate = path.join(item.root, "_analysis", "results", "renamed.json")
  fs.copyFileSync(path.join(item.root, published.path), alternate)
  const manifest = readJson(item.manifestFile)
  manifest.result_sets[0].path = "_analysis/results/renamed.json"
  writeJson(item.manifestFile, manifest)
  expectCode(() => manifestApi.validateManifest(item.manifestFile), "invalid-manifest")
})

test("关系结果发布后冻结成功章节，但允许失败章节恢复成功", () => {
  const locked = init()
  manifestApi.beginStage(locked.manifestFile, 2)
  for (let chapter = 1; chapter <= 3; chapter += 1) {
    manifestApi.recordChapter(
      locked.manifestFile,
      chapter,
      "success",
      { output: `章节/第${chapter}章_摘要.md` },
    )
  }
  manifestApi.beginStage(locked.manifestFile, 4)
  manifestApi.publishRelations(locked.manifestFile, writeDraft(locked))
  expectCode(
    () => manifestApi.recordChapter(locked.manifestFile, 1, "failed", { error: "不能使证据失效" }),
    "chapter-result-locked",
  )
  fs.appendFileSync(path.join(locked.root, "章节", "第1章_摘要.md"), "替换内容")
  expectCode(
    () => manifestApi.recordChapter(locked.manifestFile, 1, "success", { output: "章节/第1章_摘要.md" }),
    "chapter-result-locked",
  )

  const retry = init()
  manifestApi.beginStage(retry.manifestFile, 2)
  manifestApi.recordChapter(retry.manifestFile, 1, "success", { output: "章节/第1章_摘要.md" })
  manifestApi.recordChapter(retry.manifestFile, 2, "success", { output: "章节/第2章_摘要.md" })
  manifestApi.recordChapter(retry.manifestFile, 3, "failed", { error: "首次失败" })
  manifestApi.completeStage(retry.manifestFile, 2, { allowFailures: true })
  manifestApi.beginStage(retry.manifestFile, 4)
  manifestApi.publishRelations(retry.manifestFile, writeDraft(retry))
  manifestApi.beginStage(retry.manifestFile, 2)
  manifestApi.recordChapter(retry.manifestFile, 3, "success", { output: "章节/第3章_摘要.md" })
  assert.equal(readJson(retry.manifestFile).stage2.chapters["3"].attempts.at(-1).status, "success")
  assert.equal(manifestApi.validateManifest(retry.manifestFile).result_sets.length, 1)
})

test("关系规范化使用与 locale 无关的代码点顺序", () => {
  const item = beginRelations()
  const value = draft()
  value.entities = [
    { id: "😀", name: "😀", type: "supporting", confidence: 0.9, aliases: [] },
    { id: "\uE000", name: "\uE000", type: "supporting", confidence: 0.9, aliases: [] },
    { id: "ä", name: "ä", type: "supporting", confidence: 0.9, aliases: [] },
    { id: "z", name: "z", type: "protagonist", confidence: 0.9, aliases: [] },
  ]
  value.relationships[0].source = "😀"
  value.relationships[0].target = "\uE000"
  const published = manifestApi.publishRelations(item.manifestFile, writeDraft(item, value))
  const result = readJson(path.join(item.root, published.path))
  assert.deepEqual(result.entities.map((entity) => entity.id), ["z", "ä", "\uE000", "😀"])
  assert.equal(result.relationships[0].source, "\uE000")
  assert.equal(result.relationships[0].target, "😀")
})

test("已发布结果或证据被修改后验证失败", () => {
  const resultItem = beginRelations()
  const published = manifestApi.publishRelations(resultItem.manifestFile, writeDraft(resultItem))
  fs.appendFileSync(path.join(resultItem.root, published.path), " ")
  expectCode(() => manifestApi.validateManifest(resultItem.manifestFile), "result-changed")

  const evidenceItem = beginRelations()
  manifestApi.publishRelations(evidenceItem.manifestFile, writeDraft(evidenceItem))
  const evidenceFile = path.join(evidenceItem.root, "章节", "第1章_摘要.md")
  fs.appendFileSync(evidenceFile, "证据变化\n")
  const manifest = readJson(evidenceItem.manifestFile)
  manifest.stage2.chapters["1"].attempts.at(-1).output.sha256 = hash(fs.readFileSync(evidenceFile))
  writeJson(evidenceItem.manifestFile, manifest)
  expectCode(() => manifestApi.validateManifest(evidenceItem.manifestFile), "evidence-changed")
})

test("异常申领只能在确认写入者停止后释放", () => {
  const item = init()
  const claim = path.join(item.root, ".analysis-manifest-cas-2")
  writeJson(claim, { schema_version: 1, target_revision: 2, claim_id: "claim-x" })
  expectCode(() => manifestApi.releaseClaim(item.manifestFile, 2, "claim-x", false), "confirmation-required")
  expectCode(() => manifestApi.releaseClaim(item.manifestFile, 2, "wrong", true), "claim-mismatch")
  assert.deepEqual(manifestApi.releaseClaim(item.manifestFile, 2, "claim-x", true), { released: true, target_revision: 2 })
  assert.equal(fs.existsSync(claim), false)
})
