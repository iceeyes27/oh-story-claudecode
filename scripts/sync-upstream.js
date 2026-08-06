#!/usr/bin/env node
/**
 * Safely merge upstream while preserving this fork's unified-skill layout.
 *
 * Known modify/delete conflicts under split upstream skill directories are
 * resolved by keeping the fork-side deletion. The existing drift guard then
 * requires every upstream change to be ported into its unified target before
 * the merge may be committed.
 */
'use strict';

const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');

const ROOT = path.resolve(__dirname, '..');
const MAP_PATH = path.join(ROOT, 'scripts', 'unified-skill-upstream-map.json');

function fail(message, code = 1) {
  process.stderr.write(`[sync-upstream] ${message}\n`);
  process.exit(code);
}

function run(command, args, options = {}) {
  const result = spawnSync(command, args, {
    cwd: ROOT,
    encoding: 'utf8',
    stdio: options.inherit ? 'inherit' : 'pipe',
  });
  if (result.error && !options.allowFail) fail(`${command}: ${result.error.message}`);
  if (result.status !== 0 && !options.allowFail) {
    fail(`${command} ${args.join(' ')} failed:\n${result.stderr || result.stdout || ''}`);
  }
  return result;
}

function git(args, options = {}) {
  return run('git', args, options);
}

function loadMappings(file = MAP_PATH) {
  const parsed = JSON.parse(fs.readFileSync(file, 'utf8'));
  if (!Array.isArray(parsed.mappings)) throw new Error(`${file}: mappings must be an array`);
  return parsed.mappings.map(({ source, target }) => ({
    source: String(source).replace(/\\/g, '/').replace(/\/$/, ''),
    target: String(target).replace(/\\/g, '/').replace(/\/$/, ''),
  }));
}

function mappedTargetFor(file, mappings) {
  const normalized = file.replace(/\\/g, '/');
  const mapping = mappings.find(({ source }) => normalized === source || normalized.startsWith(`${source}/`));
  return mapping ? `${mapping.target}${normalized.slice(mapping.source.length)}` : null;
}

function output(result) {
  return (result.stdout || '').trim();
}

function findPython() {
  for (const candidate of ['python3', 'python', 'py']) {
    const args = candidate === 'py' ? ['-3', '--version'] : ['--version'];
    const result = run(candidate, args, { allowFail: true });
    if (!result.error && result.status === 0) return { command: candidate, prefix: candidate === 'py' ? ['-3'] : [] };
  }
  fail('Python 3 is required for the unified-skill drift guard.');
}

function parseArgs(argv) {
  const options = { remote: 'upstream', branch: 'main', commit: false, check: true };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === '--remote') options.remote = argv[++i];
    else if (arg === '--branch') options.branch = argv[++i];
    else if (arg === '--commit') options.commit = true;
    else if (arg === '--no-check') options.check = false;
    else if (arg === '-h' || arg === '--help') options.help = true;
    else fail(`unknown argument: ${arg}`, 2);
  }
  if (!options.remote || !options.branch) fail('--remote and --branch require values', 2);
  return options;
}

function printHelp() {
  process.stdout.write(
    'Usage: node scripts/sync-upstream.js [--remote upstream] [--branch main] [--commit] [--no-check]\n\n' +
    'Default behavior fetches and merges without committing. Known split-skill conflicts are\n' +
    'resolved from scripts/unified-skill-upstream-map.json. Remaining semantic conflicts and\n' +
    'unported mapped changes stop the workflow with the merge left open for inspection.\n'
  );
}

function main() {
  const options = parseArgs(process.argv.slice(2));
  if (options.help) return printHelp();

  if (output(git(['status', '--porcelain']))) {
    fail('working tree must be clean before syncing upstream');
  }
  const remoteUrl = output(git(['remote', 'get-url', options.remote], { allowFail: true }));
  if (!remoteUrl) fail(`remote does not exist: ${options.remote}`);

  git(['fetch', options.remote, '--prune'], { inherit: true });
  const upstreamRef = `${options.remote}/${options.branch}`;
  if (git(['merge-base', '--is-ancestor', upstreamRef, 'HEAD'], { allowFail: true }).status === 0) {
    process.stdout.write(`[sync-upstream] already contains ${upstreamRef}\n`);
    return;
  }

  const merge = git(['merge', '--no-ff', '--no-commit', '--no-edit', upstreamRef], { allowFail: true, inherit: true });
  const mappings = loadMappings();
  const initialConflicts = output(git(['diff', '--name-only', '--diff-filter=U'])).split('\n').filter(Boolean);
  for (const file of initialConflicts) {
    const target = mappedTargetFor(file, mappings);
    if (!target) continue;
    git(['rm', '-f', '--', file], { inherit: true });
    process.stdout.write(`[sync-upstream] resolved legacy source deletion: ${file} -> port to ${target}\n`);
  }

  const remaining = output(git(['diff', '--name-only', '--diff-filter=U'])).split('\n').filter(Boolean);
  if (remaining.length) {
    fail(`semantic conflicts remain; resolve them and rerun the checks:\n  ${remaining.join('\n  ')}\nUse git merge --abort to cancel.`);
  }
  if (merge.status !== 0 && initialConflicts.length === 0) {
    fail('merge failed without producing resolvable file conflicts; inspect Git output above');
  }

  const python = findPython();
  const drift = run(python.command, [
    ...python.prefix,
    path.join(ROOT, 'scripts', 'check-unified-skill-upstream-drift.py'),
    `--upstream-ref=${upstreamRef}`,
  ], { allowFail: true, inherit: true });
  if (drift.status !== 0) {
    fail('mapped upstream changes must be ported to their unified targets before committing; the merge remains open');
  }

  if (options.check) {
    run(process.execPath, ['--test', 'scripts/sync-skills.test.js', 'scripts/sync-upstream.test.js', 'scripts/skill-publication-coverage.test.js'], { inherit: true });
    run('bash', ['scripts/check-story-setup-deployment.sh'], { inherit: true });
    run('bash', ['scripts/check-codex-adapter.sh'], { inherit: true });
    run('bash', ['scripts/check-opencode-adapter.sh'], { inherit: true });
  }

  if (options.commit) {
    git(['commit', '-m', `sync(upstream): merge ${upstreamRef}`], { inherit: true });
    process.stdout.write(`[sync-upstream] committed ${upstreamRef}\n`);
  } else {
    process.stdout.write(`[sync-upstream] ${upstreamRef} is merged and checked; review the staged merge, then git commit\n`);
  }
}

if (require.main === module) main();

module.exports = { loadMappings, mappedTargetFor, parseArgs };
