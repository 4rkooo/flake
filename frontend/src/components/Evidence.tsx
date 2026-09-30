import type { Compare, CompareRow, DemoEvent, Policy, RiskProfile, Rule, State, Version } from '../lib/types';
import { describeArgs } from './ApprovalCard';
import { displayName } from './Avatar';

export type EvidenceTab = 'inspector' | 'policy' | 'risk' | 'versions' | 'compare';
const TABS: { id: EvidenceTab; label: string }[] = [
  { id: 'inspector', label: 'Inspector' }, { id: 'policy', label: 'Policy' }, { id: 'risk', label: 'Risk table' }, { id: 'versions', label: 'Versions' }, { id: 'compare', label: 'Compare' },
];

const money = (x: unknown) => `$${Number(x ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const pct = (x: unknown) => `${Math.round(Number(x ?? 0) * 100)}%`;
const short = (id?: string | null) => (id ? id.split(':').pop() : '');
const time = (ts: string) => new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
const fmt = (v: unknown): string => (v === null || v === undefined ? '—' : Array.isArray(v) ? (v.length ? v.map(String).join(', ') : '[]') : typeof v === 'object' ? JSON.stringify(v) : String(v));

function Json({ value, open = false, label = 'Raw details' }: { value: unknown; open?: boolean; label?: string }) {
  return (
    <details className="tree" open={open}>
      <summary>{label}</summary>
      <pre className="json">{JSON.stringify(value, null, 2)}</pre>
    </details>
  );
}

function RuleCard({ rule, cls = '' }: { rule: Rule; cls?: string }) {
  return (
    <div className={`rule ${cls}`}>
      <div className="rt">{rule.id ? `${rule.id} · ` : ''}{rule.type}{rule.people?.length ? `: ${rule.people.map(displayName).join(', ')}` : ''}{rule.day_type ? ` (${rule.day_type})` : ''}{rule.amount != null ? ` ($${rule.amount})` : ''}</div>
      {rule.reason && <div className="rr">{rule.reason}</div>}
    </div>
  );
}

function flatten(obj: Record<string, unknown>, prefix = ''): [string, unknown][] {
  const out: [string, unknown][] = [];
  for (const [k, v] of Object.entries(obj ?? {})) {
    if (v && typeof v === 'object' && !Array.isArray(v)) out.push(...flatten(v as Record<string, unknown>, `${prefix}${k}.`));
    else out.push([`${prefix}${k}`, v]);
  }
  return out;
}

export function PolicyView({ policy, title }: { policy: Policy; title?: string }) {
  return (
    <div data-testid="policy-view">
      {title && <h3>{title}</h3>}
      <h3>Rules ({policy.rules.length})</h3>
      {policy.rules.length ? policy.rules.map((r, i) => <RuleCard key={r.id ?? i} rule={r} />) : <div className="muted small">none yet: v1 is probation</div>}
      <h3>Guardrails</h3>
      <table className="kv-table"><tbody>{Object.entries(policy.guardrails).map(([k, v]) => <tr key={k}><td>{k}</td><td>{k.endsWith('_usd') ? money(v) : String(v)}</td></tr>)}</tbody></table>
      <h3>Tool permissions</h3>
      <table className="kv-table"><tbody>{flatten(policy.tool_permissions).map(([k, v]) => <tr key={k}><td>{k}</td><td>{fmt(v)}</td></tr>)}</tbody></table>
      <h3>Context policy</h3>
      <table className="kv-table"><tbody>{Object.entries(policy.context_policy).map(([k, v]) => <tr key={k}><td>{k}</td><td>{fmt(v)}</td></tr>)}</tbody></table>
      {policy.model && <div className="muted small" style={{ marginTop: 6 }}>model: {policy.model}</div>}
    </div>
  );
}

export function RiskTable({ profiles }: { profiles: Record<string, RiskProfile> }) {
  const rows = Object.values(profiles);
  if (!rows.length) return <div className="empty">No risk profiles yet. Run the baseline reset.</div>;
  return (
    <table data-testid="risk-table">
      <thead><tr><th>Friend</th><th className="num">Plans</th><th className="num">Bails</th><th className="num">P(flake)</th><th className="num">90% upper</th><th className="num">Pays late</th><th className="num">Score</th></tr></thead>
      <tbody>
        {rows.map((p) => (
          <tr key={p.person}>
            <td>{displayName(p.person)}</td><td className="num">{p.flake.n}</td><td className="num">{p.flake.k}</td>
            <td className="num">{pct(p.flake.p_mean)}</td><td className="num">{pct(p.flake.p_upper90)}</td>
            <td className="num">{pct(p.pay_late.p_mean)} <span className="muted">({p.pay_late.k}/{p.pay_late.n})</span></td>
            <td className="num"><b>{p.flake_score}</b></td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function VersionsTable({ versions }: { versions: Version[] }) {
  if (!versions.length) return <div className="empty">No policy versions yet.</div>;
  return (
    <div data-testid="versions-table">
      <table>
        <thead><tr><th>Version</th><th>Status</th><th className="num">Rules</th><th className="num">Exposure cap</th><th className="num">Auto spend</th><th className="num">Backtest</th><th>Canary</th></tr></thead>
        <tbody>
          {versions.map((v) => {
            const bt = v.backtest as Record<string, unknown> | null;
            const c = v.canary as Record<string, unknown> | null;
            const delta = bt ? Number(bt.delta_usd) : null;
            return (
              <tr key={v._id}>
                <td>{short(v._id)} <span className="muted small">by {v.created_by}</span></td>
                <td><span className={`status-pill ${v.status}`}>{v.status}</span></td>
                <td className="num">{v.policy.rules.length}</td>
                <td className="num">{money(v.policy.guardrails.max_nonrefundable_exposure_usd)}</td>
                <td className="num">{money(v.policy.guardrails.max_auto_spend_usd)}</td>
                <td className="num">{delta == null ? '—' : <span className={`delta ${delta >= 0 ? 'pos' : 'neg'}`}>{delta >= 0 ? '+' : ''}{money(delta)}</span>}</td>
                <td>{c ? `${c.result}: ${money(c.realized_cost_usd)} vs ${money(c.expected_cost_usd)} on ${c.episode_id}` : '—'}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {versions.map((v) => (
        <details className="tree" key={v._id}>
          <summary>{short(v._id)}: rationale, constitution notes, policy</summary>
          <p className="small">{v.rationale}</p>
          {v.constitution_notes?.length ? <p className="small"><b>Constitution clamped:</b> {v.constitution_notes.join('; ')}</p> : <p className="small muted">Constitution: nothing to clamp.</p>}
          <PolicyView policy={v.policy} />
        </details>
      ))}
    </div>
  );
}

function CompareRows({ rows }: { rows: CompareRow[] }) {
  return (
    <table>
      <thead><tr><th>Setting</th><th>{'from'}</th><th></th><th>{'to'}</th></tr></thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.key} className={`compare-row ${r.changed ? 'changed' : ''}`}>
            <td>{r.key}</td><td>{fmt(r.from)}</td><td className="arrow">{r.changed ? '→' : '='}</td><td><b>{fmt(r.to)}</b></td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function PolicyCompare({ compare }: { compare: Compare }) {
  const bt = compare.backtest as Record<string, unknown> | null;
  return (
    <div data-testid="policy-compare">
      <h3>{short(compare.from.id)} <span className={`status-pill ${compare.from.status}`}>{compare.from.status}</span> → {short(compare.to.id)} <span className={`status-pill ${compare.to.status}`}>{compare.to.status}</span></h3>
      {compare.rationale && <p className="small">{compare.rationale}</p>}
      <h3>Rules</h3>
      {compare.rules.added.map((r, i) => <RuleCard key={`a${i}`} rule={r} cls="added" />)}
      {compare.rules.removed.map((r, i) => <RuleCard key={`r${i}`} rule={r} cls="removed" />)}
      {compare.rules.kept.map((r, i) => <RuleCard key={`k${i}`} rule={r} />)}
      {!compare.rules.added.length && !compare.rules.removed.length && !compare.rules.kept.length && <div className="muted small">no rules in either version</div>}
      <h3>Tool permissions</h3><CompareRows rows={compare.permissions} />
      <h3>Guardrails</h3><CompareRows rows={compare.guardrails} />
      <h3>Context settings</h3><CompareRows rows={compare.context} />
      {bt && <><h3>Backtest behind {short(compare.to.id)}</h3><div className="small">{String(bt.episodes)} plans: incumbent {money(bt.baseline_usd)} → proposed {money(bt.proposed_usd)}, delta <span className={`delta ${Number(bt.delta_usd) >= 0 ? 'pos' : 'neg'}`}>{Number(bt.delta_usd) >= 0 ? '+' : ''}{money(bt.delta_usd)}</span> → {String(bt.decision)}</div></>}
      {compare.constitution_notes.length > 0 && <><h3>Constitution</h3><ul className="small">{compare.constitution_notes.map((n) => <li key={n}>{n}</li>)}</ul></>}
      <Json value={compare.diff} label={`Flat diff (${compare.diff.length} lines)`} />
    </div>
  );
}

// ------------------------------------------------------------------ the inspector
function Kv({ rows }: { rows: [string, unknown][] }) {
  return <table className="kv-table"><tbody>{rows.map(([k, v]) => <tr key={k}><td>{k}</td><td>{fmt(v)}</td></tr>)}</tbody></table>;
}

function InspectorBody({ e }: { e: DemoEvent }) {
  const d = e.details as Record<string, any>;
  switch (e.kind) {
    case 'gate.decision':
      return (
        <>
          <Kv rows={[['decision', d.decision], ['tool', d.tool], ['reason', d.reason], ['rule', d.rule_id ?? 'none'], ['audit id', d.audit_id], ['policy version', e.version_id]]} />
          <div className="args" style={{ marginTop: 8 }}>
            <div><div className="label">Requested by the model</div><pre>{JSON.stringify(d.requested_args, null, 2)}</pre></div>
            <div><div className="label">{d.args_changed ? 'Final args (changed by the gate)' : 'Final args (unchanged)'}</div><pre>{JSON.stringify(d.final_args, null, 2)}</pre></div>
          </div>
        </>
      );
    case 'risk.profiles': {
      const profs = d.profiles as Record<string, RiskProfile>;
      return (<><div className="small muted">Beta({d.prior?.alpha}, {d.prior?.beta}) prior, credibility n/(n+{d.prior?.K}), rebuilt from {d.episodes} resolved plans.</div><RiskTable profiles={profs} /></>);
    }
    case 'risk.attendance':
      return <Kv rows={[['yes RSVPs', d.yes_people], ['show probabilities', (d.show_probs as number[]).map((p) => pct(p)).join(', ')], ['expected show-ups', Number(d.expected).toFixed(2)], [`P(at least ${d.min_people} show)`, pct(d.p_at_least_min)], ['Monte Carlo draws', d.sims]]} />;
    case 'backtest.run':
      return (
        <>
          <Kv rows={[['plans replayed', d.episodes], ['incumbent cost', money(d.baseline_usd)], ['proposed cost', money(d.proposed_usd)], ['delta', `${Number(d.delta_usd) >= 0 ? '+' : ''}${money(d.delta_usd)}`], ['decision', d.decision]]} />
          <h3>Per rule</h3>
          <table><thead><tr><th>Rule</th><th>People</th><th className="num">Marginal $</th><th>Extra</th></tr></thead><tbody>
            {(d.details ?? []).map((r: any, i: number) => <tr key={i}><td>{r.rule}</td><td>{(r.people ?? []).join(', ')}</td><td className="num"><span className={`delta ${r.delta_usd >= 0 ? 'pos' : 'neg'}`}>{money(r.delta_usd)}</span></td><td>{r.late_days_avoided != null ? `${r.late_days_avoided} late days avoided` : r.on_time_payments != null ? `${r.on_time_payments} on-time payments` : ''}</td></tr>)}
          </tbody></table>
          <h3>Per plan</h3>
          <table><thead><tr><th>Plan</th><th className="num">Share</th><th>Bailed</th><th className="num">Incumbent</th><th className="num">Candidate</th></tr></thead><tbody>
            {(d.per_episode ?? []).map((r: any) => <tr key={r._id}><td>{r.title ?? r._id}</td><td className="num">${r.share}</td><td>{(r.bailed ?? []).join(', ') || '—'}</td><td className="num">{money(r.incumbent_usd)}</td><td className="num">{money(r.candidate_usd)}</td></tr>)}
          </tbody></table>
        </>
      );
    case 'canary.evaluated':
      return (
        <>
          <Kv rows={[['result', d.result], ['canary', e.version_id], ['incumbent', d.incumbent], ['realized cost', money(d.realized_cost_usd)], ['expected under incumbent', money(d.expected_cost_usd)]]} />
          <h3>Expected cost, line by line</h3>
          <table><thead><tr><th>Friend</th><th>Under incumbent</th><th className="num">Rate</th><th className="num">Share</th><th className="num">Expected</th></tr></thead><tbody>
            {(d.breakdown ?? []).map((b: any) => <tr key={b.person}><td>{displayName(b.person)}</td><td>{b.refundable ? 'refundable premium' : 'non-refundable × P(flake)'}</td><td className="num">{pct(b.rate)}</td><td className="num">${b.share}</td><td className="num">{money(b.expected_usd)}</td></tr>)}
          </tbody></table>
        </>
      );
    case 'policy.loaded':
      return <PolicyView policy={d.policy} title={`${e.version_id} (${d.status})`} />;
    case 'version.created':
      return (<><p className="small">{d.rationale}</p>{d.constitution_notes?.length ? <p className="small"><b>Constitution clamped:</b> {d.constitution_notes.join('; ')}</p> : <p className="small muted">Constitution: nothing to clamp.</p>}<PolicyView policy={d.policy} /></>);
    case 'memory.similar':
      return (
        <>
          <Kv rows={[['method', d.method === 'vector_search' ? 'Atlas $vectorSearch on episodes.embedding' : 'recency fallback (vector search unavailable)'], ['k', d.k], ['error', d.error ?? 'none'], ['brief', d.brief]]} />
          <table><thead><tr><th>Plan</th><th className="num">Score</th><th>Summary</th></tr></thead><tbody>
            {(d.hits ?? []).map((h: any) => <tr key={h._id}><td>{h.title}</td><td className="num">{h.score == null ? '—' : Number(h.score).toFixed(3)}</td><td>{h.summary}</td></tr>)}
          </tbody></table>
        </>
      );
    case 'context.built':
      return (
        <>
          <h3>Risk table given to the model</h3>
          <table><thead><tr><th>Friend</th><th className="num">P(flake)</th><th className="num">upper</th><th className="num">n</th><th className="num">late</th></tr></thead><tbody>
            {Object.entries(d.risk ?? {}).map(([p, r]: [string, any]) => <tr key={p}><td>{displayName(p)}</td><td className="num">{pct(r.flake?.p_mean)}</td><td className="num">{pct(r.flake?.p_upper90)}</td><td className="num">{r.flake?.n}</td><td className="num">{pct(r.pay_late?.p_mean)}</td></tr>)}
          </tbody></table>
          <h3>Similar plans ({(d.similar ?? []).length})</h3>
          <ul className="small">{(d.similar ?? []).map((s: any) => <li key={s._id}>{s.title}{s.score != null ? ` (score ${Number(s.score).toFixed(3)})` : ''}: {s.summary}</li>)}</ul>
          <h3>Notes ({(d.notes ?? []).length})</h3>
          <ul className="small">{(d.notes ?? []).map((n: string, i: number) => <li key={i}>{n}</li>)}</ul>
          <Kv rows={[['context policy', JSON.stringify(d.context_policy)]]} />
        </>
      );
    case 'llm.turn':
      return (<><Kv rows={[['turn', d.turn], ['model call', d.cache === 'hit' ? 'cache hit (recorded response replayed)' : d.cache === 'miss' ? 'fresh API call' : d.cache === 'scripted' ? 'scripted model (offline rehearsal)' : 'fresh API call (cache off)'], ['tool calls', (d.tool_calls ?? []).length]]} />{(d.tool_calls ?? []).map((c: any, i: number) => <div key={i} className="rule"><div className="rt">{c.name}</div><pre className="json">{JSON.stringify(c.args, null, 2)}</pre></div>)}{d.content && <p className="small">{d.content}</p>}</>);
    case 'tool.result':
      return (<><Kv rows={[['tool', d.name], ['status', d.status], ['args', describeArgs(d.name, d.args ?? {})]]} /><div className="args" style={{ marginTop: 8 }}><div><div className="label">Arguments (as run)</div><pre>{JSON.stringify(d.args, null, 2)}</pre></div><div><div className="label">Result</div><pre>{typeof d.result === 'string' ? d.result : JSON.stringify(d.result, null, 2)}</pre></div></div></>);
    case 'sim.resolved': {
      const o = d.outcomes ?? {};
      return <Kv rows={[['plan', `${d.title} (${d.plan_id ?? e.plan_id})`], ['day type', d.day_type], ['showed', o.showed], ['bailed', o.bailed], ['scripted bails', d.scripted], ['paid late (days)', JSON.stringify(o.paid_late_days)], ['lost non-refundable', money(o.lost_nonrefundable_usd)], ['premiums paid', money(o.premium_paid_usd)], ['total cost', money(o.total_cost_usd)], ['booking', JSON.stringify(d.booking)]]} />;
    }
    case 'approval.requested':
      return <Kv rows={[['approval', d.approval_id], ['tool', d.tool], ['why the gate asks', d.reason], ['question to Alex', d.question], ['args', describeArgs(d.tool, d.args ?? {})]]} />;
    case 'policy.compared':
      return <PolicyCompare compare={d.compare as Compare} />;
    case 'retro.proposal':
    case 'proposal.pricing': {
      const p = d.proposal ?? d;
      return (<><p className="small">{p.rationale}</p>{(p.rules ?? []).map((r: Rule, i: number) => <RuleCard key={i} rule={r} />)}<Kv rows={Object.entries(p.guardrails ?? {})} />{p.auto_book_nonrefundable != null && <div className="small">auto non-refundable booking: {String(p.auto_book_nonrefundable)}</div>}</>);
    }
    case 'db.op':
      return <Kv rows={[['operation', d.op], ['collection', d.collection], ['ids', d.ids ?? d.result_ids], ['fields changed', d.fields], ['matched / modified', `${d.n ?? d.count ?? '—'} / ${d.n_modified ?? '—'}`], ['filter', d.filter ? JSON.stringify(d.filter) : undefined], ['stages', d.stages], ['vector search', d.vector_search ? JSON.stringify(d.vector_search) : undefined], ['results', d.results ? JSON.stringify(d.results) : undefined], ['duration', `${d.duration_ms} ms`]].filter(([, v]) => v !== undefined) as [string, unknown][]} />;
    default:
      return null;
  }
}

export function Inspector({ event }: { event: DemoEvent | null }) {
  if (!event) return <div className="empty">Select an event in the activity feed, or press Next Beat.</div>;
  return (
    <div data-testid="inspector" data-seq={event.seq}>
      <div className="inspect-head">
        <div className="summary">{event.summary}</div>
        <div className="ids">
          <span className="tag kind">{event.kind}</span>
          {event.node && <span className="tag">{event.node}</span>}
          <span className="tag">{event.status}</span>
          {event.plan_id && <span className="tag">{event.plan_id}</span>}
          {event.version_id && <span className="tag">{event.version_id}</span>}
          <span className="tag">{time(event.ts)}</span>
          <span className="tag">#{event.seq}</span>
        </div>
      </div>
      <InspectorBody e={event} />
      <Json value={event.details} />
    </div>
  );
}

interface Props { tab: EvidenceTab; setTab: (t: EvidenceTab) => void; event: DemoEvent | null; state: State | null }

export function Evidence({ tab, setTab, event, state }: Props) {
  const versions = state?.policy.versions ?? [];
  const compares = state?.compares ?? [];
  const effective = state?.policy.effective ?? null;
  return (
    <section className="evidence" data-testid="evidence">
      <div className="evidence-tabs" role="tablist">
        {TABS.map((t) => <button key={t.id} role="tab" aria-selected={tab === t.id} className={tab === t.id ? 'on' : ''} onClick={() => setTab(t.id)} data-testid={`tab-${t.id}`}>{t.label}</button>)}
      </div>
      <div className="evidence-body">
        {tab === 'inspector' && <Inspector event={event} />}
        {tab === 'policy' && (effective ? <><div className="small muted" style={{ marginBottom: 6 }}>Policy in force for the next plan: <b>{effective._id}</b> <span className={`status-pill ${effective.status}`}>{effective.status}</span></div><PolicyView policy={effective.policy} /><h3>Risk profiles</h3><RiskTable profiles={state!.risk_profiles} /></> : <div className="empty">No policy yet. Run the baseline reset.</div>)}
        {tab === 'risk' && <RiskTable profiles={state?.risk_profiles ?? {}} />}
        {tab === 'versions' && <VersionsTable versions={versions} />}
        {tab === 'compare' && (compares.length ? compares.map((c) => <PolicyCompare key={`${c.from.id}-${c.to.id}`} compare={c} />) : <div className="empty">Two versions are needed. Run the Retro first.</div>)}
      </div>
    </section>
  );
}
