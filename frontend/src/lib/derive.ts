import type { Approval, DemoEvent, State } from './types';

// ---------------------------------------------------------------- diagram
export interface NodeDef { id: string; label: string; sub: string; loop: 'planning' | 'learning' }
export const NODES: NodeDef[] = [
  { id: 'memory', label: 'Memory', sub: 'episodes · notes · vector search', loop: 'planning' },
  { id: 'agent', label: 'Agent', sub: 'the model decides', loop: 'planning' },
  { id: 'gate', label: 'Gate', sub: 'policy enforcement point', loop: 'planning' },
  { id: 'tools', label: 'Tools', sub: 'propose · poll · book · money', loop: 'planning' },
  { id: 'outcomes', label: 'Outcomes', sub: 'who showed, who paid', loop: 'learning' },
  { id: 'risk', label: 'Risk profiles', sub: 'Beta-Binomial per friend', loop: 'learning' },
  { id: 'proposal', label: 'Proposal', sub: 'pricing model + underwriter', loop: 'learning' },
  { id: 'backtest', label: 'Backtest', sub: 'replay over past plans', loop: 'learning' },
  { id: 'policy', label: 'Policy', sub: 'versions · canary · rollback', loop: 'learning' },
];
export const EDGES: [string, string][] = [
  ['memory', 'agent'], ['agent', 'gate'], ['gate', 'tools'], ['tools', 'agent'],
  ['outcomes', 'risk'], ['risk', 'proposal'], ['proposal', 'backtest'], ['backtest', 'policy'], ['policy', 'gate'],
  ['tools', 'outcomes'],
];
export const edgeId = (a: string, b: string) => `${a}->${b}`;
const EDGE_SET = new Set(EDGES.map(([a, b]) => edgeId(a, b)));
const POLICY_GATE = edgeId('policy', 'gate');

export interface NodeActivity { count: number; last: DemoEvent | null; status: 'idle' | 'active' | 'ok' | 'warn' | 'error' }
export interface DiagramState {
  nodes: Record<string, NodeActivity>;
  litEdges: Set<string>;
  traversed: Set<string>;
  activeNode: string | null;
}

export function deriveDiagram(events: DemoEvent[]): DiagramState {
  const nodes: Record<string, NodeActivity> = {};
  for (const n of NODES) nodes[n.id] = { count: 0, last: null, status: 'idle' };
  const traversed = new Set<string>();
  let lit = new Set<string>();
  let current: string | null = null;
  let running = false;
  // policy -> gate is lit apart from the step-by-step edge: from policy.loaded until the gate's
  // first check has used it, so the moves in between (memory, agent) cannot switch it off
  let policyLit = false;
  for (const e of events) {
    if (e.kind === 'beat.start') {
      traversed.clear();
      lit = new Set();
      current = null;
      running = true;
      policyLit = false;
    }
    if (e.kind === 'beat.done' || e.kind === 'beat.error' || e.kind === 'beat.cancelled') {
      running = false;
      lit = new Set();
      policyLit = false;
      if (current) nodes[current].status = nodes[current].status === 'active' ? 'ok' : nodes[current].status;
      current = null;
    }
    if (e.kind === 'policy.loaded') {
      policyLit = true;
      traversed.add(POLICY_GATE);
    }
    if (!e.node || !nodes[e.node]) continue;
    if (e.kind === 'node.end') {
      if (e.node === 'gate') policyLit = false;
      if (nodes[e.node].status === 'active') nodes[e.node].status = 'ok';
      continue;
    }
    const n = nodes[e.node];
    n.count += 1;
    n.last = e;
    if (e.node !== current) {
      if (current && nodes[current].status === 'active') nodes[current].status = 'ok';
      if (current && EDGE_SET.has(edgeId(current, e.node))) {
        traversed.add(edgeId(current, e.node));
        lit = new Set([edgeId(current, e.node)]);
      } else {
        lit = new Set();
      }
      current = e.node;
    }
    n.status = e.status === 'error' ? 'error' : e.status === 'warn' ? 'warn' : running ? 'active' : 'ok';
  }
  if (policyLit) lit = new Set([...lit, POLICY_GATE]);
  return { nodes, litEdges: lit, traversed, activeNode: running ? current : null };
}

// ---------------------------------------------------------------- chat
export type ChatItem =
  | { key: string; type: 'bubble'; sender: string; text: string; ts: string; out: boolean }
  | { key: string; type: 'system'; text: string; ts: string; tone: 'info' | 'ok' | 'warn' | 'error' }
  | { key: string; type: 'rsvps'; ts: string; rsvps: { person: string; rsvp: string }[] }
  | { key: string; type: 'receipt'; ts: string; receipt: Record<string, unknown>; plan_id: string | null; version_id: string | null }
  | { key: string; type: 'approval'; ts: string; approval: Approval; pending: boolean };

const money = (x: unknown) => `$${Number(x ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const cap = (s: string) => (s ? s[0].toUpperCase() + s.slice(1) : s);
const list = (xs: unknown) => (Array.isArray(xs) && xs.length ? xs.map((x) => cap(String(x))).join(', ') : 'nobody');
const BAIL_LINES = [
  'Ugh, something came up. I can’t make it after all 😬',
  'So sorry, have to bail tonight.',
  'Can’t do it anymore, sorry everyone!',
];

export function deriveChat(events: DemoEvent[], state: State | null): ChatItem[] {
  const items: ChatItem[] = [];
  const approvalsById = new Map<string, Approval>();
  for (const a of state?.approvals ?? []) approvalsById.set(a.id, a);
  let bail = 0;
  for (const e of events) {
    const d = e.details as Record<string, any>;
    switch (e.kind) {
      case 'beat.start':
        if (d.beat?.operation === 'plan' && d.beat?.brief) {
          items.push({ key: `b${e.seq}`, type: 'bubble', sender: 'alex', text: d.beat.brief, ts: e.ts, out: true });
        } else if (d.beat?.operation === 'tick') {
          items.push({ key: `b${e.seq}`, type: 'system', text: `⏳ ${d.days ?? 7} days pass…`, ts: e.ts, tone: 'info' });
        }
        break;
      case 'chat.message':
        items.push({ key: `c${e.seq}`, type: 'bubble', sender: String(d.sender ?? 'flake'), text: String(d.text ?? ''), ts: e.ts, out: d.sender === 'alex' });
        break;
      case 'tool.result':
        if (d.name === 'poll_rsvps' && Array.isArray(d.result)) {
          items.push({ key: `r${e.seq}`, type: 'rsvps', ts: e.ts, rsvps: d.result });
        } else if (d.name === 'book' && d.result && typeof d.result === 'object' && e.status !== 'error') {
          items.push({ key: `k${e.seq}`, type: 'receipt', ts: e.ts, receipt: d.result, plan_id: e.plan_id, version_id: e.version_id });
        }
        break;
      case 'approval.requested': {
        const id = String(d.approval_id);
        const live = approvalsById.get(id);
        const approval: Approval = live ?? {
          id, question: String(d.question ?? ''), tool: d.tool ?? null, args: d.args ?? {}, reason: d.reason ?? null,
          plan_id: e.plan_id, version_id: e.version_id, created_at: e.ts, decision: null, answered_at: null,
        };
        items.push({ key: `a${id}`, type: 'approval', ts: e.ts, approval, pending: approval.decision === null });
        break;
      }
      case 'approval.resolved':
        items.push({
          key: `ar${e.seq}`, type: 'bubble', sender: 'alex', out: true, ts: e.ts,
          text: d.decision === 'approve' ? `Yes, go ahead with ${d.tool ?? 'it'} 👍` : `No, hold off on ${d.tool ?? 'that'}.`,
        });
        break;
      case 'sim.resolved': {
        const o = d.outcomes ?? {};
        for (const p of o.bailed ?? []) {
          items.push({ key: `s${e.seq}${p}`, type: 'bubble', sender: String(p), text: BAIL_LINES[bail++ % BAIL_LINES.length], ts: e.ts, out: false });
        }
        const late = Object.entries(o.paid_late_days ?? {}).filter(([, v]) => Number(v) > 0).map(([p, v]) => `${cap(p)} paid ${v} days late`);
        const cost = `${d.title}: ${list(o.bailed)} bailed · cost ${money(o.total_cost_usd)} (lost ${money(o.lost_nonrefundable_usd)} non-refundable, ${money(o.premium_paid_usd)} premiums)`;
        items.push({ key: `so${e.seq}`, type: 'system', text: late.length ? `${cost} · ${late.join(', ')}` : cost, ts: e.ts, tone: Number(o.lost_nonrefundable_usd) > 0 ? 'warn' : 'ok' });
        break;
      }
      case 'plan.end':
        if (!d.booking) items.push({ key: `pe${e.seq}`, type: 'system', text: `No booking was made: ${d.incomplete_reason ?? 'unknown reason'}`, ts: e.ts, tone: 'warn' });
        break;
      case 'retro.done':
        items.push({ key: `rd${e.seq}`, type: 'system', text: `Retro: policy ${e.version_id?.split(':').pop()} is ${d.status} (backtest ${Number(d.delta_usd) >= 0 ? '+' : ''}${money(d.delta_usd)})`, ts: e.ts, tone: d.status === 'canary' ? 'ok' : 'warn' });
        break;
      case 'canary.evaluated':
        items.push({ key: `ce${e.seq}`, type: 'system', text: `Policy ${e.version_id?.split(':').pop()} ${d.result === 'promoted' ? 'promoted ✅' : 'rolled back ↩'}: realized ${money(d.realized_cost_usd)} vs expected ${money(d.expected_cost_usd)}`, ts: e.ts, tone: d.result === 'promoted' ? 'ok' : 'warn' });
        break;
      case 'reset.done':
        items.push({ key: `rs${e.seq}`, type: 'system', text: `Demo reset · ${d.episodes} past plans and policy v1 (probation) restored`, ts: e.ts, tone: 'info' });
        break;
      case 'beat.error':
        items.push({ key: `be${e.seq}`, type: 'system', text: e.summary, ts: e.ts, tone: 'error' });
        break;
      default:
        break;
    }
  }
  return items;
}

export const PEOPLE_COLORS: Record<string, string> = {
  alex: '#2563eb', sam: '#dc2626', priya: '#16a34a', jordan: '#d97706', maya: '#7c3aed', flake: '#128c7e',
};
