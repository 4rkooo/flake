export type EventStatus = 'start' | 'ok' | 'info' | 'warn' | 'error';

export interface DemoEvent {
  seq: number;
  session: string;
  ts: string;
  kind: string;
  status: EventStatus;
  beat: number | null;
  beat_id: string | null;
  operation: string | null;
  node: string | null;
  summary: string;
  details: Record<string, unknown>;
  plan_id: string | null;
  version_id: string | null;
}

export interface Approval {
  id: string;
  question: string;
  tool: string | null;
  args: Record<string, unknown>;
  reason: string | null;
  plan_id: string | null;
  version_id: string | null;
  created_at: string;
  decision: 'approve' | 'decline' | 'cancelled' | null;
  answered_at: string | null;
}

export interface BeatInfo {
  index: number;
  id: string | null;
  title: string | null;
  operation: string | null;
  status: 'idle' | 'running' | 'done' | 'error' | 'cancelled';
  error: string | null;
  warning: string | null;
}

export interface BeatDef {
  index: number;
  id: string;
  title: string;
  operation: string;
  blurb: string;
}

export interface Rule {
  id?: string;
  type: string;
  people?: string[];
  day_type?: string | null;
  amount?: number | null;
  reason?: string;
}

export interface Policy {
  rules: Rule[];
  guardrails: Record<string, number>;
  tool_permissions: Record<string, unknown>;
  context_policy: Record<string, unknown>;
  model?: string;
}

export interface Version {
  _id: string;
  group_id: string;
  version: number;
  parent: string | null;
  status: string;
  created_by: string;
  created_at: string;
  rationale: string;
  policy: Policy;
  backtest: Record<string, unknown> | null;
  constitution_notes: string[];
  canary: Record<string, unknown> | null;
}

export interface Posterior {
  n: number;
  k: number;
  alpha: number;
  beta: number;
  p_mean: number;
  p_upper90: number;
  credibility: number;
}

export interface RiskProfile {
  _id: string;
  person: string;
  flake: Posterior;
  pay_late: Posterior;
  flake_score: number;
  by_day_type: Record<string, { n: number; k: number }>;
}

export interface Episode {
  _id: string;
  title?: string;
  kind?: string;
  day?: string;
  day_type?: string;
  cost_per_person_usd?: number;
  min_people?: number;
  version_id?: string | null;
  status: string;
  rsvps?: { person: string; rsvp: string }[];
  booking?: { non_refundable_for: string[]; refundable_for: string[]; deposit_usd: number; premium_usd: number } | null;
  money_requests?: { id: string; person: string; amount_usd: number; upfront: boolean }[];
  approvals?: { tool: string; at: string }[];
  outcomes?: {
    showed: string[];
    bailed: string[];
    paid_late_days: Record<string, number>;
    lost_nonrefundable_usd: number;
    premium_paid_usd: number;
    total_cost_usd: number;
  };
  summary?: string;
  incomplete_reason?: string | null;
  turns?: number;
}

export interface AuditRow {
  _id: string;
  episode_id: string;
  version_id: string;
  tool: string;
  requested_args: Record<string, unknown>;
  final_args: Record<string, unknown>;
  decision: string;
  rule_id: string | null;
  reason: string;
  ts: string;
}

export interface CompareRow {
  key: string;
  from: unknown;
  to: unknown;
  changed: boolean;
}

export interface Compare {
  from: { id: string; version: number; status: string };
  to: { id: string; version: number; status: string };
  rules: { added: Rule[]; removed: Rule[]; kept: Rule[] };
  permissions: CompareRow[];
  guardrails: CompareRow[];
  context: CompareRow[];
  model: { from: unknown; to: unknown; changed: boolean };
  diff: string[];
  rationale: string | null;
  backtest: Record<string, unknown> | null;
  constitution_notes: string[];
  canary: Record<string, unknown> | null;
}

export interface ChatLine {
  sender: string;
  text: string;
  plan_id: string | null;
  at: string;
}

export interface State {
  session: string;
  cursor: number;
  pace: number;
  needs_reset: boolean;
  busy: boolean;
  beat: BeatInfo;
  beats: BeatDef[];
  next_available: boolean;
  next_title: string | null;
  pending_approvals: Approval[];
  approvals: Approval[];
  group: { _id: string; name: string; organizer: string; members: string[] } | null;
  policy: { active: Version | null; canary: Version | null; effective: Version | null; versions: Version[] };
  risk_profiles: Record<string, RiskProfile>;
  episodes: Episode[];
  audit: AuditRow[];
  chat_log: ChatLine[];
  compares: Compare[];
  last_reset_at: string | null;
  events: DemoEvent[];
}
