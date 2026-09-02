#!/usr/bin/env node
import { spawn } from 'node:child_process';
import { createHash } from 'node:crypto';
import { mkdir, readFile, rename, writeFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
let pythonRuntime = null;

function parseArgs(argv) {
  const options = { profile: 'fast', jsonOut: null };
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === '--profile') options.profile = argv[++index];
    else if (arg.startsWith('--profile=')) options.profile = arg.slice(10);
    else if (arg === '--json-out') options.jsonOut = resolve(argv[++index]);
    else if (arg.startsWith('--json-out=')) options.jsonOut = resolve(arg.slice(11));
    else if (arg === '-h' || arg === '--help') options.help = true;
    else throw new Error(`unknown argument: ${arg}`);
  }
  return options;
}

function probe(command, args) {
  return new Promise((accept) => {
    const child = spawn(command, args, { cwd: root, shell: false, windowsHide: true, stdio: 'ignore' });
    child.on('error', () => accept(false));
    child.on('close', (code) => accept(code === 0));
  });
}

async function resolveRuntime(command, args) {
  if (process.platform === 'win32' && (command === 'npm' || command === 'npx')) {
    return {
      command: process.env.ComSpec || 'cmd.exe',
      args: ['/d', '/s', '/c', `${command}.cmd`, ...args],
    };
  }
  if (command !== 'python') return { command, args };
  if (!pythonRuntime) {
    for (const candidate of [
      { command: 'python3', prefix: [] },
      { command: 'python', prefix: [] },
      { command: 'py', prefix: ['-3'] },
    ]) {
      if (await probe(candidate.command, [...candidate.prefix, '--version'])) {
        pythonRuntime = candidate;
        break;
      }
    }
  }
  if (!pythonRuntime) return { command: '__python_unavailable__', args };
  return { command: pythonRuntime.command, args: [...pythonRuntime.prefix, ...args] };
}

async function runCheck(check) {
  const runtime = await resolveRuntime(check.command, check.args || []);
  return new Promise((accept) => {
    const started = Date.now();
    let stdout = '';
    let stderr = '';
    let settled = false;
    const child = spawn(runtime.command, runtime.args, {
      cwd: root,
      shell: false,
      windowsHide: true,
      stdio: ['ignore', 'pipe', 'pipe'],
    });
    child.stdout?.on('data', (chunk) => { stdout += chunk; process.stdout.write(chunk); });
    child.stderr?.on('data', (chunk) => { stderr += chunk; process.stderr.write(chunk); });
    child.on('error', (error) => {
      if (settled) return;
      settled = true;
      accept({ status: 'BLOCKED', exit_code: null, duration_ms: Date.now() - started, stdout, stderr: `${stderr}${error.message}` });
    });
    child.on('close', (code) => {
      if (settled) return;
      settled = true;
      const combined = `${stdout}\n${stderr}`;
      const blocked = (check.blocked_patterns || []).some((pattern) => combined.includes(pattern));
      const tests = Number(combined.match(/(?:^|\n)# tests (\d+)/)?.[1] || 0);
      const passed = Number(combined.match(/(?:^|\n)# pass (\d+)/)?.[1] || 0);
      const skippedCount = Number(combined.match(/(?:^|\n)# skipped (\d+)/)?.[1] || 0);
      const skipped = code === 0 && (
        /(^|\n)\s*(SKIP|SKIPPED)\s*[:：]/i.test(combined) ||
        (tests > 0 && passed === 0 && skippedCount > 0)
      );
      accept({
        status: blocked ? 'BLOCKED' : (code === 0 ? (skipped ? 'SKIP' : 'PASS') : 'FAIL'),
        exit_code: code,
        duration_ms: Date.now() - started,
        stdout,
        stderr,
        executed_command: [runtime.command, ...runtime.args],
      });
    });
  });
}

async function writeAtomic(file, payload) {
  await mkdir(dirname(file), { recursive: true });
  const temporary = `${file}.${process.pid}.tmp`;
  await writeFile(temporary, payload, 'utf8');
  await rename(temporary, file);
}

export function aggregateStatus(results) {
  return results.every((result) => result.status === 'PASS') ? 'PASS'
    : results.some((result) => result.status === 'FAIL') ? 'FAIL' : 'BLOCKED';
}

export async function execute(argv = process.argv.slice(2)) {
  const options = parseArgs(argv);
  if (options.help) {
    process.stdout.write('Usage: node scripts/quality-gate.mjs --profile <fast|affected|release> [--json-out FILE]\n');
    return 0;
  }
  const raw = await readFile(resolve(root, 'scripts/quality-gate.json'), 'utf8');
  const config = JSON.parse(raw.replace(/^\uFEFF/, ''));
  const names = config.profiles?.[options.profile];
  if (!Array.isArray(names)) throw new Error(`unknown quality profile: ${options.profile}`);
  const results = [];
  for (const name of names) {
    const check = config.checks?.[name];
    if (!check) throw new Error(`profile references missing check: ${name}`);
    process.stdout.write(`\n[quality] ${name}\n`);
    const result = await runCheck(check);
    results.push({ name, command: result.executed_command, ...result });
  }
  const status = aggregateStatus(results);
  const report = {
    schema_version: 1,
    profile: options.profile,
    status,
    config_sha256: createHash('sha256').update(raw).digest('hex'),
    generated_at: new Date().toISOString(),
    results,
  };
  if (options.jsonOut) await writeAtomic(options.jsonOut, `${JSON.stringify(report, null, 2)}\n`);
  process.stdout.write(`\n[quality] ${options.profile}: ${status} (${results.filter((result) => result.status === 'PASS').length}/${results.length} PASS)\n`);
  return status === 'PASS' ? 0 : 1;
}

if (import.meta.url === `file://${process.argv[1]?.replaceAll('\\', '/')}` || process.argv[1]?.endsWith('quality-gate.mjs')) {
  try {
    process.exitCode = await execute();
  } catch (error) {
    process.stderr.write(`[quality] ${error.message}\n`);
    process.exitCode = 2;
  }
}
