#!/usr/bin/env node
/**
 * Upstream integration state machine.
 *
 * The current checkout is never stashed or merged. Every integration pins the
 * fork base and upstream target to full commit IDs, runs in a dedicated Git
 * worktree, and records review and validation evidence under the common Git
 * directory. The resulting branch is left for human review; this tool never
 * pushes and never merges the branch into the caller's current branch.
 */
'use strict';

const crypto = require('node:crypto');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');

const DEFAULT_ROOT = path.resolve(__dirname, '..');
const POLICY_NAME = 'scripts/upstream-integration.json';
const COMMANDS = new Set(['status', 'prepare', 'review', 'validate', 'promote', 'abort']);
const DECISIONS = Object.freeze({
  forbidden: new Set(['reject']),
  protected: new Set(['adopt', 'adapt', 'reject']),
  generated: new Set(['regenerate']),
  shared: new Set(['regenerate']),
  unified: new Set(['adapt', 'reject']),
  canonical: new Set(['merge']),
  unknown: new Set(),
});

class SyncError extends Error {
  constructor(message, code = 1) {
    super(message);
    this.name = 'SyncError';
    this.code = code;
  }
}

function normalizePath(value) {
  return String(value).replace(/\\/g, '/').replace(/^\.\//, '').replace(/\/$/, '');
}

function run(command, args, { cwd = DEFAULT_ROOT, allowFail = false, inherit = false, env } = {}) {
  const result = spawnSync(command, args, {
    cwd,
    encoding: 'utf8',
    stdio: inherit ? 'inherit' : 'pipe',
    env: env || process.env,
  });
  if (result.error && !allowFail) {
    throw new SyncError(`${command}: ${result.error.message}`);
  }
  if (result.status !== 0 && !allowFail) {
    throw new SyncError(
      `${command} ${args.join(' ')} failed:\n${result.stderr || result.stdout || ''}`.trimEnd(),
    );
  }
  return result;
}

function git(repoRoot, args, options = {}) {
  return run('git', args, { ...options, cwd: repoRoot });
}

function output(result) {
  return (result.stdout || '').trim();
}

function gitOutput(repoRoot, args) {
  return output(git(repoRoot, args));
}

function sha256(data) {
  return crypto.createHash('sha256').update(data).digest('hex');
}

function writeJsonAtomic(file, value) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  const temp = `${file}.${process.pid}.${crypto.randomBytes(4).toString('hex')}.tmp`;
  fs.writeFileSync(temp, `${JSON.stringify(value, null, 2)}\n`, 'utf8');
  fs.renameSync(temp, file);
}

function loadPolicy(file = path.join(DEFAULT_ROOT, POLICY_NAME)) {
  const raw = fs.readFileSync(file, 'utf8');
  const policy = JSON.parse(raw.replace(/^\uFEFF/, ''));
  if (policy.schema_version !== 1) throw new SyncError(`${file}: unsupported schema_version`);
  if (!policy.origin || !policy.upstream || !Array.isArray(policy.policy_priority)) {
    throw new SyncError(`${file}: origin, upstream and policy_priority are required`);
  }
  if (!Array.isArray(policy.unified_mappings) || !policy.policies) {
    throw new SyncError(`${file}: policies and unified_mappings are required`);
  }
  if (policy.policy_priority.at(-1) !== 'unknown') {
    throw new SyncError(`${file}: unknown must be the final policy priority`);
  }
  return { policy, raw, hash: sha256(raw) };
}

function ruleMatches(file, rule) {
  const normalized = normalizePath(file);
  if (typeof rule.path === 'string' && normalized === normalizePath(rule.path)) return true;
  if (typeof rule.prefix === 'string') {
    const prefix = normalizePath(rule.prefix);
    return normalized === prefix || normalized.startsWith(`${prefix}/`);
  }
  return false;
}

function mappedTargetFor(file, mappings) {
  const normalized = normalizePath(file);
  const mapping = mappings.find((entry) => {
    const source = normalizePath(entry.source);
    return normalized === source || normalized.startsWith(`${source}/`);
  });
  if (!mapping) return null;
  const source = normalizePath(mapping.source);
  return `${normalizePath(mapping.target)}${normalized.slice(source.length)}`;
}

function classifyPath(file, policy) {
  const normalized = normalizePath(file);
  for (const category of policy.policy_priority) {
    if (category === 'unknown') break;
    if (category === 'unified') {
      const target = mappedTargetFor(normalized, policy.unified_mappings);
      if (target) return { category, target, reason: 'Upstream split Skill must be ported to its unified target.' };
      continue;
    }
    const rule = (policy.policies[category] || []).find((entry) => ruleMatches(normalized, entry));
    if (rule) return { category, target: null, reason: rule.reason || null };
  }
  return { category: 'unknown', target: null, reason: 'No integration policy matches this path.' };
}

function parseNameStatus(text) {
  if (!text.trim()) return [];
  return text.trim().split(/\r?\n/).map((line) => {
    const fields = line.split('\t');
    const status = fields.shift();
    const paths = fields.map(normalizePath);
    return { status, paths };
  });
}

function defaultDecision(category) {
  return {
    forbidden: 'reject',
    generated: 'regenerate',
    shared: 'regenerate',
    canonical: 'merge',
  }[category] || null;
}

function classifyChanges(repoRoot, baseline, target, policy) {
  const rows = parseNameStatus(
    gitOutput(repoRoot, ['diff', '--name-status', `${baseline}..${target}`, '--']),
  );
  return rows.map(({ status, paths }) => {
    const classified = paths.map((file) => ({ file, ...classifyPath(file, policy) }));
    const priority = new Map(policy.policy_priority.map((category, index) => [category, index]));
    const governing = [...classified].sort(
      (left, right) => priority.get(left.category) - priority.get(right.category),
    )[0] || { category: 'unknown', target: null, reason: 'Change has no path.' };
    const id = sha256(`${status}\0${paths.join('\0')}`).slice(0, 16);
    return {
      id,
      status,
      paths,
      category: governing.category,
      target: governing.target,
      reason: governing.reason,
      decision: defaultDecision(governing.category),
      review_reason: null,
    };
  });
}

function resolveCommit(repoRoot, ref) {
  return gitOutput(repoRoot, ['rev-parse', '--verify', `${ref}^{commit}`]);
}

function isAncestor(repoRoot, ancestor, descendant) {
  return git(repoRoot, ['merge-base', '--is-ancestor', ancestor, descendant], { allowFail: true }).status === 0;
}

function gitCommonDir(repoRoot) {
  const raw = gitOutput(repoRoot, ['rev-parse', '--git-common-dir']);
  return path.resolve(repoRoot, raw);
}

function stateDirectory(repoRoot) {
  return path.join(gitCommonDir(repoRoot), 'upstream-sync');
}

function stateFile(repoRoot, id) {
  if (!/^[a-zA-Z0-9._-]+$/.test(id || '')) throw new SyncError(`invalid sync id: ${id}`, 2);
  return path.join(stateDirectory(repoRoot), `${id}.json`);
}

function loadState(repoRoot, id) {
  const file = stateFile(repoRoot, id);
  if (!fs.existsSync(file)) throw new SyncError(`sync state does not exist: ${id}`, 2);
  const state = JSON.parse(fs.readFileSync(file, 'utf8').replace(/^\uFEFF/, ''));
  return { file, state };
}

function saveState(repoRoot, state) {
  state.updated_at = new Date().toISOString();
  writeJsonAtomic(stateFile(repoRoot, state.id), state);
}

function parseArgs(argv) {
  const args = [...argv];
  let command = 'status';
  if (args[0] && !args[0].startsWith('-')) command = args.shift();
  if (!COMMANDS.has(command)) throw new SyncError(`unknown command: ${command}`, 2);
  const options = {
    command,
    repo: DEFAULT_ROOT,
    policy: null,
    id: null,
    originRemote: null,
    originBranch: null,
    upstreamRemote: null,
    upstreamBranch: null,
    originSha: null,
    upstreamSha: null,
    worktree: null,
    decisionFile: null,
    qualityProfile: null,
    message: null,
    fetch: true,
    json: false,
    help: false,
  };
  const valueOptions = new Map([
    ['--repo', 'repo'], ['--policy', 'policy'], ['--id', 'id'],
    ['--origin-remote', 'originRemote'], ['--origin-branch', 'originBranch'],
    ['--upstream-remote', 'upstreamRemote'], ['--upstream-branch', 'upstreamBranch'],
    ['--origin-sha', 'originSha'], ['--upstream-sha', 'upstreamSha'],
    ['--worktree', 'worktree'], ['--decision-file', 'decisionFile'],
    ['--quality-profile', 'qualityProfile'], ['--message', 'message'],
  ]);
  for (let index = 0; index < args.length; index += 1) {
    const arg = args[index];
    if (arg === '--no-fetch') options.fetch = false;
    else if (arg === '--json') options.json = true;
    else if (arg === '-h' || arg === '--help') options.help = true;
    else if (valueOptions.has(arg)) {
      const value = args[++index];
      if (!value || value.startsWith('--')) throw new SyncError(`${arg} requires a value`, 2);
      options[valueOptions.get(arg)] = value;
    } else {
      const match = arg.match(/^(--[^=]+)=(.*)$/);
      if (!match || !valueOptions.has(match[1]) || !match[2]) {
        throw new SyncError(`unknown argument: ${arg}`, 2);
      }
      options[valueOptions.get(match[1])] = match[2];
    }
  }
  options.repo = path.resolve(options.repo);
  options.policy = path.resolve(options.repo, options.policy || POLICY_NAME);
  if (options.worktree) options.worktree = path.resolve(options.worktree);
  if (options.decisionFile) options.decisionFile = path.resolve(options.decisionFile);
  return options;
}

function assertRemote(repoRoot, remote) {
  const fetchUrl = output(git(repoRoot, ['remote', 'get-url', remote], { allowFail: true }));
  if (!fetchUrl) throw new SyncError(`remote does not exist: ${remote}`);
  return fetchUrl;
}

function assertUpstreamNoPush(repoRoot, remote) {
  const pushUrl = output(git(repoRoot, ['remote', 'get-url', '--push', remote], { allowFail: true }));
  if (!/^(DISABLED|NO_PUSH|\/dev\/null)$/i.test(pushUrl)) {
    throw new SyncError(
      `upstream push URL must be disabled before prepare; run: git remote set-url --push ${remote} DISABLED`,
    );
  }
}

function fetchRemote(repoRoot, remote, branch) {
  git(repoRoot, ['fetch', remote, branch, '--prune'], { inherit: true });
}

function makeSyncId(target) {
  return `${target.slice(0, 12)}-${Date.now().toString(36)}`;
}

function ensureEmptyDestination(destination) {
  if (!fs.existsSync(destination)) return;
  const entries = fs.readdirSync(destination);
  if (entries.length) throw new SyncError(`worktree destination is not empty: ${destination}`);
  fs.rmdirSync(destination);
}

function conflictFiles(worktree) {
  return output(git(worktree, ['diff', '--name-only', '--diff-filter=U']))
    .split(/\r?\n/).filter(Boolean).map(normalizePath);
}

function trackedInWorktree(worktree, file) {
  return git(worktree, ['ls-files', '--error-unmatch', '--', file], { allowFail: true }).status === 0;
}

function removeRejectedPaths(worktree, changes, policy) {
  const removed = [];
  for (const change of changes) {
    if (!['forbidden', 'unified'].includes(change.category)) continue;
    for (const file of change.paths) {
      const classified = classifyPath(file, policy);
      if (!['forbidden', 'unified'].includes(classified.category)) continue;
      if (trackedInWorktree(worktree, file)) {
        git(worktree, ['rm', '-r', '-f', '--', file]);
        removed.push(file);
      }
    }
  }
  return removed;
}

function listStates(repoRoot) {
  const directory = stateDirectory(repoRoot);
  if (!fs.existsSync(directory)) return [];
  return fs.readdirSync(directory)
    .filter((name) => name.endsWith('.json'))
    .map((name) => {
      try {
        return JSON.parse(fs.readFileSync(path.join(directory, name), 'utf8'));
      } catch {
        return { id: name.slice(0, -5), phase: 'unreadable' };
      }
    })
    .sort((left, right) => String(right.updated_at || '').localeCompare(String(left.updated_at || '')));
}

function prepare(options) {
  const repoRoot = options.repo;
  const loaded = loadPolicy(options.policy);
  const { policy } = loaded;
  const originRemote = options.originRemote || policy.origin.remote;
  const originBranch = options.originBranch || policy.origin.branch;
  const upstreamRemote = options.upstreamRemote || policy.upstream.remote;
  const upstreamBranch = options.upstreamBranch || policy.upstream.branch;
  assertRemote(repoRoot, originRemote);
  assertRemote(repoRoot, upstreamRemote);
  if (originRemote === upstreamRemote) throw new SyncError('origin and upstream remotes must be different');
  assertUpstreamNoPush(repoRoot, upstreamRemote);
  if (options.fetch) {
    fetchRemote(repoRoot, originRemote, originBranch);
    fetchRemote(repoRoot, upstreamRemote, upstreamBranch);
  }
  const originRef = options.originSha || `${originRemote}/${originBranch}`;
  const upstreamRef = options.upstreamSha || `${upstreamRemote}/${upstreamBranch}`;
  const originBase = resolveCommit(repoRoot, originRef);
  const upstreamTarget = resolveCommit(repoRoot, upstreamRef);
  const baseline = resolveCommit(repoRoot, policy.upstream.baseline);
  if (!isAncestor(repoRoot, baseline, upstreamTarget)) {
    throw new SyncError(
      `configured upstream baseline ${baseline} is not an ancestor of target ${upstreamTarget}`,
    );
  }
  const mergeBase = gitOutput(repoRoot, ['merge-base', originBase, upstreamTarget]);
  const changes = classifyChanges(repoRoot, baseline, upstreamTarget, policy);
  const id = makeSyncId(upstreamTarget);
  const branch = `codex/sync-upstream-${upstreamTarget.slice(0, 12)}-${id.split('-').at(-1)}`;
  const worktree = options.worktree || path.join(
    os.tmpdir(), 'oh-story-upstream-sync', path.basename(repoRoot), id,
  );
  ensureEmptyDestination(worktree);
  fs.mkdirSync(path.dirname(worktree), { recursive: true });
  git(repoRoot, ['worktree', 'add', '-b', branch, worktree, originBase], { inherit: true });

  let merge;
  try {
    merge = git(worktree, ['merge', '--no-ff', '--no-commit', '--no-edit', upstreamTarget], {
      allowFail: true,
      inherit: true,
    });
    const removed = removeRejectedPaths(worktree, changes, policy);
    const conflicts = conflictFiles(worktree);
    const unknown = changes.filter((entry) => entry.category === 'unknown');
    const state = {
      schema_version: 1,
      id,
      phase: conflicts.length || unknown.length ? 'blocked' : 'prepared',
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      repo_root: fs.realpathSync(repoRoot),
      worktree: fs.realpathSync(worktree),
      branch,
      origin_remote: originRemote,
      origin_branch: originBranch,
      origin_base: originBase,
      upstream_remote: upstreamRemote,
      upstream_branch: upstreamBranch,
      previous_upstream_main: baseline,
      target_upstream_main: upstreamTarget,
      merge_base: mergeBase,
      policy_path: normalizePath(path.relative(repoRoot, options.policy)),
      policy_hash: loaded.hash,
      quality_profile: options.qualityProfile || policy.quality_profile || 'release',
      changes,
      automatically_removed: removed,
      conflicts,
      merge_exit_code: merge.status,
      validation: null,
      commit: null,
    };
    saveState(repoRoot, state);
    return state;
  } catch (error) {
    throw new SyncError(
      `prepare failed after creating ${worktree}; inspect that worktree or remove it with git worktree remove. ${error.message}`,
    );
  }
}

function review(options) {
  if (!options.id || !options.decisionFile) {
    throw new SyncError('review requires --id and --decision-file', 2);
  }
  const { state } = loadState(options.repo, options.id);
  if (['aborted', 'promoted'].includes(state.phase)) {
    throw new SyncError(`cannot review a ${state.phase} integration`);
  }
  const document = JSON.parse(fs.readFileSync(options.decisionFile, 'utf8').replace(/^\uFEFF/, ''));
  if (document.schema_version !== 1 || document.sync_id !== state.id || !Array.isArray(document.decisions)) {
    throw new SyncError('decision file needs schema_version=1, matching sync_id and decisions[]', 2);
  }
  const byId = new Map(document.decisions.map((entry) => [entry.id, entry]));
  for (const change of state.changes) {
    const supplied = byId.get(change.id);
    if (!supplied) continue;
    if (!DECISIONS[change.category].has(supplied.decision)) {
      throw new SyncError(`decision ${supplied.decision} is invalid for ${change.category}: ${change.id}`, 2);
    }
    if (!String(supplied.reason || '').trim()) {
      throw new SyncError(`decision reason is required: ${change.id}`, 2);
    }
    change.decision = supplied.decision;
    change.review_reason = String(supplied.reason).trim();
    if (supplied.target) change.target = normalizePath(supplied.target);
  }
  const pending = state.changes.filter((entry) => entry.decision === null);
  state.phase = pending.length || state.conflicts.length ? 'blocked' : 'reviewed';
  saveState(options.repo, state);
  return state;
}

function assertManagedWorktree(repoRoot, state) {
  if (!fs.existsSync(state.worktree)) throw new SyncError(`managed worktree is missing: ${state.worktree}`);
  const expected = fs.realpathSync(gitCommonDir(repoRoot));
  const actual = fs.realpathSync(gitCommonDir(state.worktree));
  if (expected !== actual) throw new SyncError('state worktree belongs to a different Git repository');
  const branch = gitOutput(state.worktree, ['branch', '--show-current']);
  if (branch !== state.branch || !branch.startsWith('codex/sync-upstream-')) {
    throw new SyncError(`managed worktree branch mismatch: ${branch}`);
  }
}

function policyForbiddenFiles(worktree, policy) {
  return gitOutput(worktree, ['ls-files']).split(/\r?\n/).filter(Boolean).filter((file) => {
    const category = classifyPath(file, policy).category;
    return category === 'forbidden' || category === 'unified';
  });
}

function validate(options) {
  if (!options.id) throw new SyncError('validate requires --id', 2);
  const { state } = loadState(options.repo, options.id);
  if (['aborted', 'promoted'].includes(state.phase)) {
    throw new SyncError(`cannot validate a ${state.phase} integration`);
  }
  assertManagedWorktree(options.repo, state);
  const conflicts = conflictFiles(state.worktree);
  if (conflicts.length) throw new SyncError(`unresolved conflicts:\n  ${conflicts.join('\n  ')}`);
  const pending = state.changes.filter((entry) => entry.decision === null);
  if (pending.length) throw new SyncError(`review decisions are missing for ${pending.length} change(s)`);
  const unknown = state.changes.filter((entry) => entry.category === 'unknown');
  if (unknown.length) throw new SyncError(`integration policy has ${unknown.length} unknown change(s)`);
  const loaded = loadPolicy(path.join(state.worktree, state.policy_path));
  if (state.final_policy_hash) {
    if (loaded.hash !== state.final_policy_hash) throw new SyncError('validated policy changed after validation');
  } else if (loaded.hash !== state.policy_hash) {
    throw new SyncError('integration policy changed after prepare; abort and prepare again');
  }
  if (!isAncestor(state.worktree, state.previous_upstream_main, state.target_upstream_main)) {
    throw new SyncError('upstream target no longer descends from the recorded baseline');
  }
  const mergeHead = resolveCommit(state.worktree, 'MERGE_HEAD');
  if (mergeHead !== state.target_upstream_main) throw new SyncError('MERGE_HEAD differs from pinned upstream target');
  const forbidden = policyForbiddenFiles(state.worktree, loaded.policy);
  if (forbidden.length) throw new SyncError(`forbidden or split paths remain:\n  ${forbidden.join('\n  ')}`);

  const policyPath = path.join(state.worktree, state.policy_path);
  const nextPolicy = loaded.policy;
  nextPolicy.upstream.baseline = state.target_upstream_main;
  writeJsonAtomic(policyPath, nextPolicy);
  git(state.worktree, ['add', '--', state.policy_path]);

  const reportDir = stateDirectory(options.repo);
  const reportPath = path.join(reportDir, `${state.id}.quality.json`);
  const qualityScript = path.join(state.worktree, 'scripts', 'quality-gate.mjs');
  if (!fs.existsSync(qualityScript)) throw new SyncError(`quality runner is missing: ${qualityScript}`);
  const quality = run(process.execPath, [
    qualityScript,
    '--profile', options.qualityProfile || state.quality_profile,
    '--json-out', reportPath,
  ], { cwd: state.worktree, allowFail: true, inherit: true });
  if (quality.status !== 0) throw new SyncError(`quality gate did not pass; report: ${reportPath}`);
  const qualityReport = JSON.parse(fs.readFileSync(reportPath, 'utf8'));
  if (qualityReport.status !== 'PASS') {
    throw new SyncError(`quality gate status is ${qualityReport.status}, expected PASS`);
  }
  const finalPolicy = loadPolicy(policyPath);
  state.final_policy_hash = finalPolicy.hash;
  state.validation = {
    status: 'PASS',
    profile: options.qualityProfile || state.quality_profile,
    report: reportPath,
    tree: gitOutput(state.worktree, ['write-tree']),
    validated_at: new Date().toISOString(),
  };
  state.phase = 'validated';
  saveState(options.repo, state);
  return state;
}

function promote(options) {
  if (!options.id) throw new SyncError('promote requires --id', 2);
  const { state } = loadState(options.repo, options.id);
  if (state.phase !== 'validated' || state.validation?.status !== 'PASS') {
    throw new SyncError('integration must have a current PASS validation before promote');
  }
  assertManagedWorktree(options.repo, state);
  const tree = gitOutput(state.worktree, ['write-tree']);
  if (tree !== state.validation.tree) throw new SyncError('worktree index changed after validation');
  fetchRemote(options.repo, state.origin_remote, state.origin_branch);
  const currentOrigin = resolveCommit(options.repo, `${state.origin_remote}/${state.origin_branch}`);
  if (currentOrigin !== state.origin_base) {
    throw new SyncError(`origin moved from ${state.origin_base} to ${currentOrigin}; prepare again`);
  }
  const message = options.message || `sync(upstream): integrate ${state.target_upstream_main.slice(0, 12)}`;
  git(state.worktree, ['commit', '-m', message], { inherit: true });
  const commit = resolveCommit(state.worktree, 'HEAD');
  const parents = gitOutput(state.worktree, ['rev-list', '--parents', '-n', '1', commit]).split(' ');
  if (parents.length < 3 || parents[2] !== state.target_upstream_main) {
    throw new SyncError(`created commit does not have pinned upstream as its second parent: ${commit}`);
  }
  state.phase = 'promoted';
  state.commit = commit;
  saveState(options.repo, state);
  return state;
}

function abort(options) {
  if (!options.id) throw new SyncError('abort requires --id', 2);
  const { state } = loadState(options.repo, options.id);
  if (state.phase === 'promoted') throw new SyncError('promoted integrations are retained for review and cannot be aborted');
  if (state.phase === 'aborted') return state;
  assertManagedWorktree(options.repo, state);
  git(options.repo, ['worktree', 'remove', '--force', state.worktree]);
  const branch = git(options.repo, ['branch', '-D', state.branch], { allowFail: true });
  if (branch.status !== 0) throw new SyncError(`failed to remove managed branch ${state.branch}`);
  state.phase = 'aborted';
  state.aborted_at = new Date().toISOString();
  saveState(options.repo, state);
  return state;
}

function printHelp() {
  process.stdout.write(`Usage: node scripts/sync-upstream.js <command> [options]\n\n` +
    `Commands:\n` +
    `  status                         List recorded integrations\n` +
    `  prepare [--origin-sha SHA] [--upstream-sha SHA] [--worktree PATH]\n` +
    `  review --id ID --decision-file FILE\n` +
    `  validate --id ID [--quality-profile release]\n` +
    `  promote --id ID [--message TEXT]\n` +
    `  abort --id ID\n\n` +
    `prepare fetches by default. All commands accept --repo and --policy.\n`);
}

function publicState(state) {
  return {
    id: state.id,
    phase: state.phase,
    branch: state.branch,
    worktree: state.worktree,
    origin_base: state.origin_base,
    target_upstream_main: state.target_upstream_main,
    conflicts: state.conflicts?.length || 0,
    pending_reviews: state.changes?.filter((entry) => entry.decision === null).length || 0,
    validation: state.validation?.status || null,
    commit: state.commit || null,
  };
}

function main(argv = process.argv.slice(2)) {
  const options = parseArgs(argv);
  if (options.help) return printHelp();
  let result;
  if (options.command === 'status') {
    result = options.id ? loadState(options.repo, options.id).state : listStates(options.repo);
  } else if (options.command === 'prepare') result = prepare(options);
  else if (options.command === 'review') result = review(options);
  else if (options.command === 'validate') result = validate(options);
  else if (options.command === 'promote') result = promote(options);
  else result = abort(options);
  const visible = Array.isArray(result) ? result.map(publicState) : publicState(result);
  process.stdout.write(`${JSON.stringify(visible, null, 2)}\n`);
}

if (require.main === module) {
  try {
    main();
  } catch (error) {
    const code = error instanceof SyncError ? error.code : 1;
    process.stderr.write(`[sync-upstream] ${error.message}\n`);
    process.exitCode = code;
  }
}

module.exports = {
  SyncError,
  abort,
  classifyChanges,
  classifyPath,
  isAncestor,
  loadPolicy,
  mappedTargetFor,
  parseArgs,
  parseNameStatus,
  prepare,
  promote,
  review,
  validate,
};
