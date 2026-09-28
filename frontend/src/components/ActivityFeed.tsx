import { useEffect, useMemo, useRef, useState } from 'react';
import type { DemoEvent } from '../lib/types';

type Filter = 'all' | 'decisions' | 'model' | 'memory' | 'database';
const FILTERS: { id: Filter; label: string }[] = [
  { id: 'all', label: 'All' }, { id: 'decisions', label: 'Decisions' }, { id: 'model', label: 'Model' }, { id: 'memory', label: 'Memory' }, { id: 'database', label: 'Database' },
];
const NODE_COLOR: Record<string, string> = {
  memory: 'var(--node-memory)', agent: 'var(--node-agent)', gate: 'var(--node-gate)', tools: 'var(--node-tools)', outcomes: 'var(--node-outcomes)',
  risk: 'var(--node-risk)', proposal: 'var(--node-proposal)', backtest: 'var(--node-backtest)', policy: 'var(--node-policy)',
};
const time = (ts: string) => new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });

export function matchesFilter(e: DemoEvent, f: Filter): boolean {
  if (e.kind === 'node.end') return false;
  if (f === 'all') return true;
  if (f === 'decisions') return /^(gate\.decision|approval\.|policy\.|version\.|canary\.|backtest\.run|retro\.|proposal\.|plan\.recorded|beat\.)/.test(e.kind);
  if (f === 'model') return /^(llm\.|proposal\.(worded|fallback))/.test(e.kind) || (e.kind === 'node.start' && e.node === 'agent');
  if (f === 'memory') return /^(memory\.|context\.built|checkpoint\.saved|episode\.created)/.test(e.kind);
  if (f === 'database') return /^(db\.|checkpoint\.saved|memory\.similar|memory\.notes)/.test(e.kind);
  return true;
}

export function eventTags(e: DemoEvent): { cls: string; text: string }[] {
  const tags: { cls: string; text: string }[] = [];
  const d = e.details as Record<string, any>;
  if (e.kind === 'llm.turn' || e.kind === 'proposal.worded') {
    const c = d.cache;
    tags.push(c === 'hit' ? { cls: 'cache', text: 'cache hit' } : c === 'scripted' ? { cls: 'cache', text: 'scripted' } : { cls: 'fresh', text: 'fresh call' });
  }
  if (e.kind === 'llm.cache') tags.push(d.hit ? { cls: 'cache', text: 'cache hit' } : { cls: 'fresh', text: 'fresh call' });
  if (e.kind === 'memory.similar') tags.push(d.method === 'vector_search' ? { cls: 'search', text: '$vectorSearch' } : { cls: 'fallback', text: 'vector-search fallback' });
  if (e.kind === 'memory.notes') tags.push(d.method === 'store_search' ? { cls: 'search', text: 'notes search' } : { cls: 'fallback', text: 'notes fallback' });
  if (e.kind === 'proposal.fallback') tags.push({ cls: 'fallback', text: 'deterministic fallback' });
  if (e.kind === 'gate.decision') tags.push({ cls: String(d.decision), text: String(d.decision).toUpperCase() });
  if (e.kind === 'db.op') tags.push({ cls: 'db', text: `${d.op} ${d.collection}` });
  if (e.kind === 'checkpoint.saved') tags.push({ cls: 'db', text: 'checkpoints' });
  if (e.version_id && /^(gate\.decision|policy\.loaded|version\.|canary\.evaluated)/.test(e.kind)) tags.push({ cls: 'kind', text: e.version_id.split(':').pop()! });
  return tags;
}

interface Props { events: DemoEvent[]; selectedSeq: number | null; live: boolean; onSelect: (seq: number) => void; onLive: () => void; active?: boolean }

export function ActivityFeed({ events, selectedSeq, live, onSelect, onLive, active = true }: Props) {
  const [filter, setFilter] = useState<Filter>('all');
  const scroller = useRef<HTMLDivElement>(null);
  const rows = useMemo(() => events.filter((e) => matchesFilter(e, filter)), [events, filter]);
  useEffect(() => {
    if (live && active && scroller.current) scroller.current.scrollTop = scroller.current.scrollHeight;
  }, [rows.length, live, active]);
  useEffect(() => {
    if (selectedSeq == null) return;
    // scoped to this panel's own scroller: Evidence.tsx's inspector root also renders
    // a data-seq attribute with the same value, so an unscoped document query can match it instead
    scroller.current?.querySelector<HTMLElement>(`[data-seq="${selectedSeq}"]`)?.scrollIntoView({ block: 'nearest' });
  }, [selectedSeq]);
  return (
    <section className="feed" data-testid="feed">
      <div className="feed-toolbar">
        <span className="title">Activity</span>
        {FILTERS.map((f) => <button key={f.id} className={`filter ${filter === f.id ? 'on' : ''}`} onClick={() => setFilter(f.id)}>{f.label}</button>)}
        <button className={`live-btn ${live ? 'on' : ''}`} onClick={onLive} data-testid="live-toggle" title="Follow execution"><span className="dot" />{live ? 'Live' : 'Back to live'}</button>
      </div>
      <div className="feed-scroll" ref={scroller}>
        {rows.length === 0 && <div className="empty">Nothing yet. Events appear here as each beat runs.</div>}
        <ul className="feed-list">
          {rows.map((e) => e.kind === 'beat.start' ? (
            <li key={e.seq} className="feed-beat" data-seq={e.seq}>{e.summary}</li>
          ) : (
            <li key={e.seq}>
              <button className={`feed-row ${selectedSeq === e.seq ? 'selected' : ''}`} onClick={() => onSelect(e.seq)} data-seq={e.seq} data-testid="feed-row" data-kind={e.kind} data-node={e.node ?? ''}>
                <span className="t">{time(e.ts)}</span>
                <span className={`dot ${e.status}`} />
                <span className="body">
                  <span className="summary">{e.summary}</span>
                  <span className="meta">
                    {e.node && <span className="tag node" style={{ '--node-color': NODE_COLOR[e.node] } as React.CSSProperties}>{e.node}</span>}
                    {eventTags(e).map((t, i) => <span key={i} className={`tag ${t.cls}`}>{t.text}</span>)}
                    {e.plan_id && <span className="tag">{e.plan_id}</span>}
                  </span>
                </span>
              </button>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
