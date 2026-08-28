import assert from 'node:assert/strict';
import test from 'node:test';
import { aggregateStatus } from './quality-gate.mjs';

test('all required checks must pass', () => {
  assert.equal(aggregateStatus([{ status: 'PASS' }, { status: 'PASS' }]), 'PASS');
  assert.equal(aggregateStatus([{ status: 'PASS' }, { status: 'SKIP' }]), 'BLOCKED');
  assert.equal(aggregateStatus([{ status: 'PASS' }, { status: 'BLOCKED' }]), 'BLOCKED');
  assert.equal(aggregateStatus([{ status: 'BLOCKED' }, { status: 'FAIL' }]), 'FAIL');
});
