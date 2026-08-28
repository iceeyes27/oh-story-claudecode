#!/usr/bin/env node
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const root = resolve(import.meta.dirname, '..');
const capabilities = JSON.parse(readFileSync(resolve(root, 'scripts/platform-capabilities.json'), 'utf8').replace(/^\uFEFF/, ''));
const catalog = JSON.parse(readFileSync(resolve(root, capabilities.skill_catalog), 'utf8').replace(/^\uFEFF/, ''));
const allowedAgent = new Set(['supported', 'runtime_probe_required', 'unsupported']);
const allowedFallback = new Set(['solo', 'inline', 'direct', 'skills_only']);
const findings = [];

if (capabilities.schema_version !== 1) findings.push('schema_version must be 1');
if (!Array.isArray(catalog.skills) || new Set(catalog.skills).size !== catalog.skills.length) {
  findings.push('skill catalog must contain unique skills');
}
for (const [name, platform] of Object.entries(capabilities.platforms || {})) {
  if (!platform.skill_root) findings.push(`${name}: skill_root is required`);
  if (typeof platform.commands !== 'boolean') findings.push(`${name}: commands must be boolean`);
  if (!Array.isArray(platform.hooks)) findings.push(`${name}: hooks must be an array`);
  if (!allowedAgent.has(platform.custom_agents)) findings.push(`${name}: custom_agents is invalid`);
  if (!Array.isArray(platform.activation) || platform.activation.length === 0) findings.push(`${name}: activation is required`);
  if (!allowedFallback.has(platform.fallback)) findings.push(`${name}: fallback is invalid`);
}
for (const required of ['claude', 'opencode', 'codex', 'zcode', 'openclaw', 'reasonix', 'generic']) {
  if (!capabilities.platforms?.[required]) findings.push(`missing platform: ${required}`);
}
if (findings.length) {
  process.stderr.write(`${findings.map((item) => `FAIL: ${item}`).join('\n')}\n`);
  process.exit(1);
}
process.stdout.write(`PASS: ${Object.keys(capabilities.platforms).length} platform contracts; ${catalog.skills.length} public skills\n`);
