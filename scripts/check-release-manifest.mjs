#!/usr/bin/env node
import { createHash } from 'node:crypto';
import { readFileSync, renameSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';

const root = resolve(import.meta.dirname, '..');
const manifestPath = resolve(root, 'scripts/release-manifest.json');

function digest(file) {
  return createHash('sha256').update(readFileSync(resolve(root, file))).digest('hex');
}

export function collectReleaseManifest(manifest) {
  const sourceFields = [
    'fork_version_source', 'current_contract', 'upstream_policy', 'platform_capabilities',
    'public_skill_catalog', 'shared_asset_manifest', 'quality_gate',
  ];
  const hashes = Object.fromEntries(sourceFields.map((field) => [manifest[field], digest(manifest[field])]));
  const policy = JSON.parse(readFileSync(resolve(root, manifest.upstream_policy), 'utf8').replace(/^\uFEFF/, ''));
  const catalog = JSON.parse(readFileSync(resolve(root, manifest.public_skill_catalog), 'utf8').replace(/^\uFEFF/, ''));
  const current = JSON.parse(readFileSync(resolve(root, manifest.current_contract), 'utf8').replace(/^\uFEFF/, ''));
  const quality = JSON.parse(readFileSync(resolve(root, manifest.quality_gate), 'utf8').replace(/^\uFEFF/, ''));
  if (!/^[0-9a-f]{40}$/.test(policy.upstream?.baseline || '')) throw new Error('upstream baseline must be a full SHA');
  if (!Array.isArray(catalog.skills) || catalog.skills.length === 0) throw new Error('public skill catalog is empty');
  if (!quality.profiles?.[manifest.quality_profile]) throw new Error('release quality profile is missing');
  return {
    ...manifest,
    identity: {
      fork_version: readFileSync(resolve(root, manifest.fork_version_source), 'utf8').trim(),
      setup_skill_version: current.setup_skill_version,
      agents_version: current.agents_version,
      upstream_baseline: policy.upstream.baseline,
      public_skill_count: catalog.skills.length,
    },
    source_hashes: hashes,
  };
}

const write = process.argv.includes('--write');
try {
  const manifest = JSON.parse(readFileSync(manifestPath, 'utf8').replace(/^\uFEFF/, ''));
  if (manifest.schema_version !== 1) throw new Error('schema_version must be 1');
  const expected = collectReleaseManifest(manifest);
  if (write) {
    const temporary = `${manifestPath}.${process.pid}.tmp`;
    writeFileSync(temporary, `${JSON.stringify(expected, null, 2)}\n`, 'utf8');
    renameSync(temporary, manifestPath);
  } else if (JSON.stringify(manifest.source_hashes) !== JSON.stringify(expected.source_hashes)
      || JSON.stringify(manifest.identity) !== JSON.stringify(expected.identity)) {
    throw new Error('release manifest is stale; run node scripts/check-release-manifest.mjs --write');
  }
  process.stdout.write(`PASS: release identity ${expected.identity.fork_version}; upstream ${expected.identity.upstream_baseline.slice(0, 12)}\n`);
} catch (error) {
  process.stderr.write(`FAIL: ${error.message}\n`);
  process.exitCode = 1;
}
