#!/usr/bin/env node
'use strict';

// The sole owner of cumulative reading status. It does not write story facts.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const os = require('node:os');
const { spawnSync } = require('node:child_process');
const { storage } = require('./review-state.js');
const SCHEMA = 1;
const POLICY = 'longform-reading-v1';
const FILE = '.story-review/longform-v1.json';
const DIMENSIONS = ['understanding', 'fatigue', 'relationships', 'reward_expectation'];
const DISPOSITIONS = ['retain', 'revise_prose', 'revise_design', 'next_unit'];
class LongformError extends Error {}
function need(ok, message) { if (!ok) throw new LongformError(message); }
function nonempty(value) { return typeof value === 'string' && value.trim().length > 0; }
function digest(value) { return crypto.createHash('sha256').update(typeof value === 'string' || Buffer.isBuffer(value) ? value : JSON.stringify(value)).digest('hex'); }
function positive(n) { return Number.isSafeInteger(n) && n > 0; }
function safe(book, relative) {
  need(nonempty(relative) && !path.isAbsolute(relative) && !relative.includes('\\') && !relative.split('/').includes('..'), 'unsafe project path');
  let current = path.resolve(book);
  for (const part of relative.split('/')) {
    current = path.join(current, part);
    if (fs.existsSync(current)) need(!fs.lstatSync(current).isSymbolicLink(), `symlink not allowed: ${relative}`);
  }
  return current;
}
function readState(book) {
  const file = safe(book, FILE);
  const exists = fs.existsSync(file);
  const state = storage.readJson(file, 'longform');
  if (!exists && state === null) return null;
  need(state && typeof state === 'object' && !Array.isArray(state), 'invalid longform state; existing file is not an object');
  need(state.schema_version === SCHEMA && state.policy_version === POLICY, 'unsupported longform version; explicit upgrade required');
  need(positive(state.state_revision) && positive(state.start_chapter), 'invalid longform revision/start');
  for (const name of ['records', 'runs']) need(state[name] && typeof state[name] === 'object' && !Array.isArray(state[name]), `invalid ${name}`);
  need(Array.isArray(state.authorizations), 'invalid authorizations');
  if (state.record_history !== undefined) need(Array.isArray(state.record_history), 'invalid record_history');
  if (state.deferred_findings !== undefined) {
    need(state.deferred_findings && typeof state.deferred_findings === 'object' && !Array.isArray(state.deferred_findings), 'invalid deferred_findings');
    for (const [id, row] of Object.entries(state.deferred_findings)) {
      need(nonempty(id) && row && positive(row.origin_chapter) && row.finding?.id === id
        && row.finding.disposition === 'next_unit', 'invalid deferred finding');
    }
  }
  return state;
}
function mutate(book, expected, build) {
  need(Number.isSafeInteger(expected) && expected >= 0, 'expected-revision required');
  const directory = safe(book, '.story-review');
  fs.mkdirSync(directory, { recursive: true });
  const claimFile = path.join(directory, `.longform-cas-${expected + 1}`);
  const claimId = crypto.randomUUID();
  const claim = { claim_id: claimId, target_revision: expected + 1, pid: process.pid, hostname: os.hostname() };
  try { fs.writeFileSync(claimFile, JSON.stringify(claim), { flag: 'wx', mode: 0o600 }); }
  catch (error) { if (error.code === 'EEXIST') throw new LongformError('longform claim conflict; inspect/release only after writer stopped'); throw error; }
  try {
    const state = readState(book);
    need((state?.state_revision || 0) === expected, 'longform revision conflict');
    const next = build(state);
    next.schema_version = SCHEMA;
    next.policy_version = POLICY;
    next.state_revision = expected + 1;
    next.updated_at = new Date().toISOString();
    storage.atomicWrite(safe(book, FILE), next, claimId);
    return next;
  } finally {
    if (storage.ownClaim(claimFile, claimId)) fs.unlinkSync(claimFile);
  }
}

// Same recursive semantics as flow-state, shared by both consumers now.
function chapterFiles(root, outline = false) {
  const files = [];
  if (!fs.existsSync(root)) return files;
  need(!fs.lstatSync(root).isSymbolicLink(), 'chapter root cannot be a symlink');
  function walk(dir) {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      if (entry.name.startsWith('.') || /^(?:候选|_?历史|原稿|归档|node_modules)$/.test(entry.name) || entry.name.startsWith("_原稿")) continue;
      const file = path.join(dir, entry.name);
      if (entry.isSymbolicLink()) continue;
      if (entry.isDirectory()) { if (!outline) walk(file); continue; }
      if (!entry.isFile() || /(?:_原稿(?:_|\.)|_历史_|_候选_)/.test(entry.name)) continue;
      const match = entry.name.match(outline ? /^细纲_第0*(\d+)章(?:[^\d].*)?\.md$/ : /^第0*(\d+)章.*\.md$/);
      if (match && positive(Number(match[1]))) files.push({ chapter: Number(match[1]), file });
    }
  }
  walk(root);
  return files.sort((a, b) => a.chapter - b.chapter || a.file.localeCompare(b.file));
}
function trackingFacts(book) {
  const tracking = storage.readJson(safe(book, '追踪/_tracking-state.json'), 'tracking');
  need(tracking && Number.isSafeInteger(tracking.last_committed_chapter) && tracking.last_committed_chapter >= 0, 'longform requires adopted tracking last_committed_chapter');
  const last = tracking.last_committed_chapter, imported = Object.hasOwn(tracking, 'imported_through_chapter') ? tracking.imported_through_chapter : 0;
  need(Number.isSafeInteger(imported) && imported >= 0 && imported <= last, 'invalid imported_through_chapter');
  const gaps = Object.hasOwn(tracking, 'chapter_gaps') ? tracking.chapter_gaps : [];
  need(Array.isArray(gaps), 'invalid chapter_gaps');
  const excluded = new Map();
  for (const gap of gaps) {
    need(gap && positive(gap.start_chapter) && positive(gap.end_chapter) && positive(gap.declared_at_chapter)
      && gap.start_chapter <= gap.end_chapter && gap.start_chapter > imported
      && gap.declared_at_chapter === gap.end_chapter + 1 && gap.declared_at_chapter <= last && nonempty(gap.reason), 'invalid chapter gap range, adoption point or reason');
    for (let n = gap.start_chapter; n <= gap.end_chapter; n++) {
      need(!excluded.has(n), 'overlapping chapter gaps');
      excluded.set(n, gap.reason);
    }
  }
  return { last, excluded };
}
function adopted(book) { return trackingFacts(book).last; }
function units(book) {
  let run;
  for (const python of ['python3', 'python']) {
    run = spawnSync(python, [path.join(__dirname, 'longform-units.py'), path.resolve(book)], {
      encoding: 'utf8', timeout: 15000, maxBuffer: 4 * 1024 * 1024, env: { ...process.env, PYTHONDONTWRITEBYTECODE: '1' },
    });
    if (run.error?.code !== 'ENOENT') break;
  }
  need(!run.error && run.status === 0, `unit discovery failed: ${run.error?.message || run.stderr}`);
  let rows;
  try { rows = JSON.parse(run.stdout); } catch { throw new LongformError('invalid unit discovery output'); }
  const seen = new Set();
  rows.sort((a, b) => a.from - b.from);
  for (const [i, row] of rows.entries()) {
    need(!seen.has(row.id), `duplicate unit ID: ${row.id}`);
    need(i === 0 || rows[i - 1].to < row.from, 'overlapping unit boundaries');
    seen.add(row.id);
  }
  return rows;
}
function checkpointPlan(book, state) {
  const { last, excluded } = trackingFacts(book);
  const rows = units(book);
  need(rows.some(row => row.from <= Math.max(last, state.start_chapter) && row.to >= Math.max(last, state.start_chapter)), 'adopted/start chapter lacks a unit boundary');
  for (let chapter = state.start_chapter; chapter <= last; chapter++) {
    need(excluded.has(chapter) || rows.some(row => row.from <= chapter && row.to >= chapter), `unplanned adopted chapter: ${chapter}`);
  }
  const points = new Map();
  function add(end, from, reason, unit) {
    if (end < state.start_chapter) return;
    const cp = points.get(end) || { id: `chapter-${end}`, chapter: end, from, reasons: [], units: [] };
    cp.from = Math.min(cp.from, from);
    cp.reasons.push(reason);
    if (!cp.units.some(row => row.id === unit.id)) cp.units.push(unit);
    points.set(end, cp);
  }
  for (const row of rows) {
    if (row.to < state.start_chapter) continue;
    add(row.to, row.from, `unit:${row.id}`, row);
    for (let n = Math.ceil(Math.max(row.from, state.start_chapter) / 15) * 15; n <= row.to; n += 15) {
      add(n, Math.max(1, n - 14), 'rolling15', row);
    }
  }
  const chapters = chapterFiles(safe(book, '正文'));
  const byNumber = new Map();
  for (const file of chapters) {
    need(!excluded.has(file.chapter), `chapter gap conflicts with existing prose: ${file.chapter}`);
    if (!byNumber.has(file.chapter)) byNumber.set(file.chapter, []);
    byNumber.get(file.chapter).push(file);
  }
  return [...points.values()].sort((a, b) => a.chapter - b.chapter).map(cp => {
    cp.units = rows.filter(row => row.from <= cp.chapter && row.to >= cp.from);
    const missing = [], duplicates = [], inputs = [], excludedChapters = [];
    if (cp.chapter <= last) for (let n = cp.from; n <= cp.chapter; n++) {
      if (excluded.has(n)) { excludedChapters.push({ chapter: n, reason: excluded.get(n) }); continue; }
      const matches = byNumber.get(n) || [];
      if (!matches.length) missing.push(n);
      else if (matches.length > 1) duplicates.push(n);
      else inputs.push({ chapter: n, path: path.relative(book, matches[0].file).split(path.sep).join('/'), sha256: digest(fs.readFileSync(matches[0].file)) });
    }
    const requirements = { policy_version: POLICY, start_chapter: state.start_chapter, id: cp.id, from: cp.from, chapter: cp.chapter, reasons: cp.reasons, units: cp.units, inputs, excluded: excludedChapters };
    return { ...cp, inputs, missing, duplicates, excluded: excludedChapters, due: cp.chapter <= last, requirement_sha256: digest(requirements) };
  });
}
function comparisonValid(book, files) {
  return Array.isArray(files) && files.every(row => {
    try { return digest(fs.readFileSync(safe(book, row.path))) === row.sha256; } catch { return false; }
  });
}
function statusOf(book, cp, state) {
  if (!cp.due) return 'not_due';
  const record = state.records[cp.id];
  if (!record) return 'pending';
  need(['reviewed', 'waived'].includes(record.status), 'invalid longform record status');
  if (record.requirement_sha256 !== cp.requirement_sha256 || !comparisonValid(book, record.comparison_files || [])) return 'stale';
  if (record.status === 'reviewed') {
    const run = state.runs[record.run_id];
    need(run && run.status === 'finished' && run.receipt_sha256 === digest(record.receipt), 'reviewed requires a finished, bound reading run');
    need(record.receipt.requirement_sha256 === cp.requirement_sha256, 'receipt requirement mismatch');
  }
  return record.status;
}
function gate(book, chapter) {
  const state = readState(book);
  if (!state) return { enabled: false, status: 'not_enabled', can_generate: true, can_complete: false, state_revision: 0, source: FILE, checkpoints: [] };
  const last = adopted(book);
  if (chapter !== undefined) need(positive(chapter) && chapter === last + 1, 'write gate requires next adopted chapter');
  const plan = checkpointPlan(book, state);
  const points = plan.map(cp => {
    const status = statusOf(book, cp, state);
    const next = plan.find(other => other.chapter > cp.chapter);
    const authorization = state.authorizations.find(a => a.checkpoint_id === cp.id && a.requirement_sha256 === cp.requirement_sha256 && a.kind === 'continue' && a.from_chapter <= last + 1 && a.through_chapter >= last + 1 && (!next || last < next.chapter));
    return { ...cp, status, authorized_continue: Boolean(authorization), failure_reason: Object.values(state.runs).filter(r => r.checkpoint_id === cp.id && r.status === 'failed').at(-1)?.failure_reason || null };
  });
  const unresolved = points.filter(cp => cp.due && !['reviewed', 'waived'].includes(cp.status));
  const blocked = unresolved.some(cp => cp.missing.length || cp.duplicates.length || !cp.authorized_continue);
  return { enabled: true, policy_version: POLICY, state_revision: state.state_revision, start_chapter: state.start_chapter, source: FILE,
    status: unresolved.length ? 'pending_reading' : 'ready', can_generate: !blocked, can_complete: !unresolved.length,
    checkpoints: points, unresolved: unresolved.map(cp => cp.id) };
}
function dueCheckpoint(book, state, id) {
  const cp = checkpointPlan(book, state).find(row => row.id === id);
  need(cp?.due, 'checkpoint is not due');
  need(!cp.missing.length && !cp.duplicates.length, 'required adopted prose missing or duplicated');
  return cp;
}
function initialize(book, expected, options) {
  return mutate(book, expected, current => {
    need(!current, 'longform policy already enabled; no silent reset');
    const last = adopted(book);
    if (options.new_book) need(last === 0 && chapterFiles(safe(book, '正文')).length === 0, 'new-book cannot enable an existing book');
    else need(positive(options.start_chapter) && nonempty(options.author_approval), 'existing book requires explicit start chapter and author approval');
    const next = { start_chapter: options.new_book ? 1 : options.start_chapter, activation: options.new_book ? 'new_book' : 'author_choice', author_approval: options.author_approval || null,
      records: {}, record_history: [], deferred_findings: {}, runs: {}, authorizations: [] };
    checkpointPlan(book, next);
    return next;
  });
}
function start(book, expected, input) {
  let runId;
  const state = mutate(book, expected, state => {
    need(state, 'longform not enabled');
    const cp = dueCheckpoint(book, state, input.checkpoint_id);
    const reader = input.reader;
    need(reader && nonempty(reader.id) && nonempty(reader.session_id) && ['model', 'human'].includes(reader.reader_type), 'reader identity/session/type required');
    need(input.independent === true && Array.isArray(input.creative_participants) && input.creative_participants.length && input.creative_participants.every(nonempty), 'independent reading needs declared creative participants');
    need(!input.creative_participants.includes(reader.id) && !input.creative_participants.includes(reader.session_id), 'reader participated in writing/planning');
    need(input.reading_order === 'chronological_then_comparison' && input.prose_only === true, 'reader must receive prose only, chronologically before comparison');
    const comparison = input.comparison;
    need(comparison && nonempty(comparison.reason) && Array.isArray(comparison.paths), 'comparison selection reason and paths required');
    need(new Set(comparison.paths).size === comparison.paths.length, 'duplicate comparison path');
    const available = chapterFiles(safe(book, '正文'));
    const comparisonFiles = comparison.paths.map(relative => {
      const matches = available.filter(file => path.relative(book, file.file).split(path.sep).join('/') === relative && file.chapter < cp.from);
      need(matches.length === 1, 'comparison must be earlier adopted prose, not future/design/context');
      return { chapter: matches[0].chapter, path: relative, sha256: digest(fs.readFileSync(safe(book, relative))) };
    }).sort((a, b) => a.chapter - b.chapter);
    if (!comparisonFiles.length) need(cp.from === 1 || comparison.insufficient_evidence === true, 'no earlier comparison: explicitly record insufficient evidence');
    runId = crypto.randomUUID();
    state.runs[runId] = { run_id: runId, checkpoint_id: cp.id, requirement_sha256: cp.requirement_sha256, reader, independent: true,
      creative_participants: input.creative_participants, status: 'reading', inputs: cp.inputs, comparison_files: comparisonFiles,
      comparison_reason: comparison.reason, insufficient_comparison: comparison.insufficient_evidence === true, delivered: [] };
    return state;
  });
  return { state_revision: state.state_revision, run_id: runId, required_files: state.runs[runId].inputs, comparison_files: state.runs[runId].comparison_files };
}
function currentRun(book, state, id) {
  const run = state?.runs[id];
  need(run && run.status === 'reading', 'active reading run required');
  const cp = dueCheckpoint(book, state, run.checkpoint_id);
  need(run.requirement_sha256 === cp.requirement_sha256 && comparisonValid(book, run.comparison_files), 'reading inputs changed; start a fresh run');
  return { run, cp };
}
function deliver(book, expected, input) {
  let text;
  const state = mutate(book, expected, state => {
    const { run } = currentRun(book, state, input.run_id);
    const sequence = [...run.inputs, ...run.comparison_files];
    const next = sequence[run.delivered.length];
    need(next && next.path === input.path, 'read required prose in chapter order, then comparison; do not skip files');
    text = fs.readFileSync(safe(book, next.path), 'utf8');
    need(digest(Buffer.from(text)) === next.sha256, 'prose changed before delivery');
    run.delivered.push({ ...next, delivery: 'whole_file', delivered_at: new Date().toISOString() });
    return state;
  });
  // No unit cards or author knowledge are returned to the reader.
  return { state_revision: state.state_revision, run_id: input.run_id, path: input.path, text };
}
function validateEvidence(book, run, rows) {
  need(Array.isArray(rows) && rows.length > 0, 'original prose evidence required');
  for (const row of rows) {
    need(run.delivered.some(file => file.path === row.path) && positive(row.line) && nonempty(row.quote), 'evidence must reference delivered prose with one-based line and quote');
    const lines = fs.readFileSync(safe(book, row.path), 'utf8').split(/\r?\n/);
    need(lines.slice(row.line - 1).join('\n').startsWith(row.quote), 'evidence quote does not match line');
  }
}
function deferredIndex(state) {
  if (state.deferred_findings !== undefined) return structuredClone(state.deferred_findings);
  const findings = new Map();
  for (const [checkpointId, record] of Object.entries(state.records).filter(([, r]) => r.status === 'reviewed').sort((a, b) => a[1].chapter - b[1].chapter)) {
    for (const response of record.receipt.responses || []) {
      if (response.disposition === 'next_unit' && findings.has(response.finding_id)) {
        findings.get(response.finding_id).last_response = response;
      }
      else findings.delete(response.finding_id);
    }
    for (const finding of record.receipt.findings) if (finding.disposition === 'next_unit') {
      findings.set(finding.id, { origin_chapter: record.chapter, origin_checkpoint_id: checkpointId, finding });
    }
  }
  return Object.fromEntries(findings);
}
function outstanding(state, before, inclusive = false) {
  return Object.entries(deferredIndex(state))
    .filter(([, row]) => inclusive ? row.origin_chapter <= before : row.origin_chapter < before)
    .sort((a, b) => a[1].origin_chapter - b[1].origin_chapter || a[0].localeCompare(b[0]))
    .map(([id]) => id);
}
function archiveRecord(state, checkpointId, supersededBy) {
  const previous = state.records[checkpointId];
  if (!previous) return;
  state.record_history = state.record_history || [];
  state.record_history.push({ checkpoint_id: checkpointId, ...previous, superseded_by: supersededBy, archived_at: new Date().toISOString() });
}
function finish(book, expected, input) {
  return mutate(book, expected, state => {
    const { run, cp } = currentRun(book, state, input.run_id);
    need(run.delivered.length === run.inputs.length + run.comparison_files.length, 'required reading range incomplete');
    need(input.observations && Object.keys(input.observations).sort().join() === [...DIMENSIONS].sort().join(), 'all four reading dimensions required');
    for (const value of Object.values(input.observations)) {
      need(nonempty(value.assessment), 'reading assessment required');
      validateEvidence(book, run, value.evidence);
    }
    need(Array.isArray(input.findings) && Array.isArray(input.responses), 'findings/responses arrays required (may be empty)');
    const deferred = deferredIndex(state);
    const owed = outstanding(state, cp.chapter, true);
    const ids = new Set();
    for (const item of input.findings) {
      need(nonempty(item.id) && !ids.has(item.id) && !owed.includes(item.id) && DISPOSITIONS.includes(item.disposition) && nonempty(item.reason), 'unique new finding ID, disposition and reason required');
      ids.add(item.id);
      validateEvidence(book, run, item.evidence);
    }
    need(new Set(input.responses.map(r => r.finding_id)).size === input.responses.length && input.responses.length === owed.length && owed.every(id => input.responses.some(r => r.finding_id === id)), 'deferred findings must each receive a response');
    for (const response of input.responses) {
      need(DISPOSITIONS.includes(response.disposition) && nonempty(response.reason), 'response disposition/reason required');
      if (response.disposition === 'next_unit') deferred[response.finding_id].last_response = { ...response, checkpoint_id: cp.id, chapter: cp.chapter };
      else delete deferred[response.finding_id];
    }
    for (const item of input.findings) if (item.disposition === 'next_unit') {
      deferred[item.id] = { origin_chapter: cp.chapter, origin_checkpoint_id: cp.id, finding: item };
    }
    const receipt = { schema_version: SCHEMA, policy_version: POLICY, requirement_sha256: cp.requirement_sha256,
      reader: run.reader, independent: run.independent, delivered: run.delivered, comparison_reason: run.comparison_reason,
      insufficient_comparison: run.insufficient_comparison, observations: input.observations, findings: input.findings, responses: input.responses };
    archiveRecord(state, cp.id, 'reviewed');
    state.deferred_findings = deferred;
    state.records[cp.id] = { status: 'reviewed', chapter: cp.chapter, run_id: run.run_id, requirement_sha256: cp.requirement_sha256, comparison_files: run.comparison_files, receipt };
    run.status = 'finished';
    run.receipt_sha256 = digest(receipt);
    return state;
  });
}
function failRun(book, expected, input) {
  return mutate(book, expected, state => {
    const run = state?.runs[input.run_id];
    need(run && run.status === 'reading' && nonempty(input.reason), 'active run and failure reason required');
    run.status = 'failed'; run.failure_reason = input.reason;
    return state;
  });
}
function authorize(book, expected, input) {
  return mutate(book, expected, state => {
    need(state && ['continue', 'waive'].includes(input.kind) && nonempty(input.author_approval) && nonempty(input.reason), 'explicit author approval, kind and reason required');
    const cp = dueCheckpoint(book, state, input.checkpoint_id);
    const authorization = { checkpoint_id: cp.id, requirement_sha256: cp.requirement_sha256, kind: input.kind, author_approval: input.author_approval, reason: input.reason };
    if (input.kind === 'continue') {
      const next = checkpointPlan(book, state).find(row => row.chapter > cp.chapter);
      const from = adopted(book) + 1;
      need(next && positive(input.through_chapter) && input.through_chapter >= from && input.through_chapter <= next.chapter, 'continue scope must end no later than next checkpoint; plan its boundary first');
      Object.assign(authorization, { from_chapter: from, through_chapter: input.through_chapter });
    } else {
      state.deferred_findings = deferredIndex(state);
      archiveRecord(state, cp.id, 'waived');
      state.records[cp.id] = { status: 'waived', chapter: cp.chapter, requirement_sha256: cp.requirement_sha256, comparison_files: [], authorization };
    }
    state.authorizations.push(authorization);
    return state;
  });
}
function main(argv) {
  try {
    const args = [...argv], command = args.shift(), values = {};
    const allowed = new Set(['book', 'expected-revision', 'input', 'chapter', 'start-chapter', 'author-approval', 'target-revision', 'claim-id']);
    while (args.length) {
      const arg = args.shift();
      if (['--new-book', '--complete', '--confirm-writer-stopped'].includes(arg)) { need(!values[arg.slice(2)], 'duplicate flag'); values[arg.slice(2)] = true; continue; }
      need(arg?.startsWith('--') && allowed.has(arg.slice(2)) && values[arg.slice(2)] === undefined && args.length, `invalid argument ${arg}`);
      values[arg.slice(2)] = args.shift();
    }
    need(nonempty(values.book), '--book required');
    const book = path.resolve(values.book);
    need(fs.existsSync(book), 'book not found');
    const expected = values['expected-revision'] === undefined ? NaN : Number(values['expected-revision']);
    let output;
    if (command === 'gate' || command === 'status') {
      output = gate(book, values.chapter === undefined ? undefined : Number(values.chapter));
    } else if (command === 'init') {
      output = initialize(book, expected, { new_book: values['new-book'], start_chapter: Number(values['start-chapter']), author_approval: values['author-approval'] });
    } else if (command === 'release-claim') {
      need(values['confirm-writer-stopped'], 'confirm writer stopped before releasing claim');
      const revision = Number(values['target-revision']);
      need(positive(revision), 'target-revision required');
      const file = safe(book, `.story-review/.longform-cas-${revision}`);
      const claim = storage.readJson(file, 'longform-claim');
      need(claim && claim.claim_id === values['claim-id'] && (readState(book)?.state_revision || 0) === revision - 1, 'claim/revision mismatch');
      fs.unlinkSync(file); output = { released: true };
    } else {
      need(nonempty(values.input), '--input JSON required');
      const input = storage.readJson(path.resolve(values.input), 'longform-input');
      need(input && typeof input === 'object', 'input object required');
      const commands = { start, read: deliver, finish, fail: failRun, authorize };
      need(Object.hasOwn(commands, command), 'unknown longform command');
      output = commands[command](book, expected, input);
    }
    process.stdout.write(JSON.stringify(output, null, 2) + '\n');
    if (command === 'gate' && !(values.complete ? output.can_complete : output.can_generate)) return 1;
    return 0;
  } catch (error) {
    process.stderr.write(`ERROR [longform] ${error.message}\n`);
    return 2;
  }
}
module.exports = { gate, initialize, start, deliver, finish, failRun, authorize, readState, chapterFiles, checkpointPlan, outstanding, main, FILE, POLICY };
if (require.main === module) process.exitCode = main(process.argv.slice(2));
