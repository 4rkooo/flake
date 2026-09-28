// Unit tests for the event folds; run with `npm test` (Node's built-in runner, no extra deps).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { deriveDiagram, edgeId } from './derive.ts';
import type { DemoEvent, EventStatus } from './types.ts';

let seq = 0;
const ev = (kind: string, node: string | null, status: EventStatus = 'info'): DemoEvent => ({
  seq: ++seq, session: 's1', ts: '', kind, status, beat: 1, beat_id: 'taco', operation: 'plan', node,
  summary: kind, details: {}, plan_id: 'ep_006', version_id: 'taco-council:v1',
});
const POLICY_GATE = edgeId('policy', 'gate');

// the opening of a plan beat, in the order the coordinator journals it
const planOpening = () => [
  ev('beat.start', null, 'start'), ev('plan.start', null), ev('node.start', 'memory', 'start'),
  ev('policy.loaded', 'policy', 'ok'),
];

test('loading the policy lights policy -> gate', () => {
  const d = deriveDiagram(planOpening());
  assert.ok(d.litEdges.has(POLICY_GATE));
  assert.ok(d.traversed.has(POLICY_GATE));
});

test("policy -> gate stays lit through the gate's first check, then goes dark", () => {
  const events = [
    ...planOpening(), ev('context.built', 'memory', 'ok'), ev('node.end', 'memory', 'ok'),
    ev('node.start', 'agent', 'start'), ev('node.end', 'agent', 'ok'),
    ev('node.start', 'gate', 'start'), ev('gate.decision', 'gate', 'ok'),
  ];
  let d = deriveDiagram(events);
  assert.ok(d.litEdges.has(POLICY_GATE));
  assert.ok(d.litEdges.has(edgeId('agent', 'gate')));      // alongside the step in progress
  events.push(ev('node.end', 'gate', 'ok'), ev('node.start', 'tools', 'start'));
  d = deriveDiagram(events);
  assert.ok(!d.litEdges.has(POLICY_GATE));
  assert.ok(d.traversed.has(POLICY_GATE));
});

test('a beat ending turns policy -> gate off', () => {
  const d = deriveDiagram([...planOpening(), ev('beat.done', null, 'ok')]);
  assert.equal(d.litEdges.size, 0);
});
