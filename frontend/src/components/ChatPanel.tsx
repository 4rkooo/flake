import { useEffect, useRef } from 'react';
import { Receipt, Users } from 'lucide-react';
import type { ChatItem } from '../lib/derive';
import type { State } from '../lib/types';
import { ApprovalCard } from './ApprovalCard';
import { Avatar, displayName } from './Avatar';

const time = (ts: string) => new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
const money = (x: unknown) => `$${Number(x ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const names = (xs: unknown) => (Array.isArray(xs) && xs.length ? xs.map((x) => displayName(String(x))).join(', ') : 'nobody');

export function ChatPanel({ items, state, onAnswer, active = true, typing = false }: { items: ChatItem[]; state: State | null; onAnswer: (id: string, d: 'approve' | 'decline') => void; active?: boolean; typing?: boolean }) {
  const scroller = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = scroller.current;
    if (el && active) el.scrollTop = el.scrollHeight;
  }, [items.length, active, typing]);
  const members = state?.group?.members ?? ['sam', 'priya', 'jordan', 'maya'];
  const pendingIds = (state?.pending_approvals ?? []).map((a) => a.id);
  return (
    <>
      <div className="chat-header">
        <div className="avatar-stack" aria-hidden>
          <Avatar who="alex" />
          {members.map((m) => <Avatar key={m} who={m} />)}
          <Avatar who="flake" />
        </div>
        <div>
          <div className="title">{state?.group?.name ?? 'Taco Council'}</div>
          <div className="members">Alex (organizer), {members.map(displayName).join(', ')}, Flake</div>
        </div>
      </div>
      <div className="chat-scroll" ref={scroller} data-testid="chat-scroll">
        {items.length === 0 && <div className="sys">Press <b>Next Beat</b> to start. The first beat resets the demo database.</div>}
        {items.map((it) => {
          switch (it.type) {
            case 'bubble':
              return (
                <div key={it.key} className={`msg ${it.out ? 'out' : ''}`} data-testid="bubble" data-sender={it.sender}>
                  <span className="avatar"><Avatar who={it.sender} /></span>
                  <div className="bubble">
                    <div className="who" style={{ color: it.sender === 'flake' ? '#128c7e' : undefined }}>{displayName(it.sender)}{it.sender === 'flake' ? ' 🤖' : ''}</div>
                    <div className="text">{it.text}</div>
                    <span className="time">{time(it.ts)}</span>
                  </div>
                </div>
              );
            case 'system':
              return <div key={it.key} className={`sys ${it.tone}`} data-testid="system-line">{it.text}</div>;
            case 'rsvps':
              return (
                <div key={it.key} className="card" data-testid="rsvp-card">
                  <div className="card-title"><Users size={14} /> RSVPs</div>
                  <div className="rsvp-list">
                    {it.rsvps.map((r) => (
                      <div key={r.person} className="rsvp"><Avatar who={r.person} /><span>{displayName(r.person)}</span><span className={r.rsvp === 'yes' ? 'yes' : 'no'}>{r.rsvp === 'yes' ? 'in' : r.rsvp}</span></div>
                    ))}
                  </div>
                </div>
              );
            case 'receipt':
              return (
                <div key={it.key} className="card receipt" data-testid="receipt-card">
                  <div className="card-title"><Receipt size={14} /> Booking receipt {it.version_id && <span className="tag" style={{ marginLeft: 'auto' }}>under {it.version_id.split(':').pop()}</span>}</div>
                  <dl className="kv">
                    <dt>Non-refundable</dt><dd>{names(it.receipt.non_refundable_for)}</dd>
                    <dt>Refundable</dt><dd>{names(it.receipt.refundable_for)}</dd>
                    <dt>Deposit</dt><dd>{money(it.receipt.deposit_usd)}</dd>
                    <dt>Premium</dt><dd>{money(it.receipt.premium_usd)}</dd>
                  </dl>
                </div>
              );
            case 'approval':
              return <ApprovalCard key={it.key} approval={it.approval} pending={it.pending} onAnswer={onAnswer} />;
            default:
              return null;
          }
        })}
        {typing && (
          <div className="msg" data-testid="typing">
            <span className="avatar"><Avatar who="flake" /></span>
            <div className="bubble typing"><span className="dots"><i /><i /><i /></span> Flake is working on it</div>
          </div>
        )}
      </div>
      <div className="chat-footer">
        {pendingIds.length > 1 ? (
          <>
            <span>{pendingIds.length} requests are waiting for Alex.</span>
            <button className="btn small approve" style={{ marginLeft: 'auto' }} onClick={() => pendingIds.forEach((id) => onAnswer(id, 'approve'))} data-testid="approve-all">Approve all {pendingIds.length}</button>
          </>
        ) : (
          <span>Alex&rsquo;s requests come from the script. Approvals are answered live by the presenter.</span>
        )}
      </div>
    </>
  );
}
