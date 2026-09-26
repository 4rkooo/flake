import { useEffect, useState } from 'react';
import { Loader2, ShieldAlert } from 'lucide-react';
import type { Approval } from '../lib/types';

const money = (x: unknown) => `$${Number(x ?? 0).toLocaleString()}`;
const cap = (s: unknown) => (typeof s === 'string' && s ? s[0].toUpperCase() + s.slice(1) : String(s));

export function describeArgs(tool: string | null, args: Record<string, unknown>): string {
  if (tool === 'book') {
    const nr = (args.non_refundable_for as string[] | undefined) ?? [];
    const r = (args.refundable_for as string[] | undefined) ?? [];
    return `non-refundable for ${nr.length ? nr.map(cap).join(', ') : 'nobody'}; refundable for ${r.length ? r.map(cap).join(', ') : 'nobody'}`;
  }
  if (tool === 'request_money') {
    return `${money(args.amount_usd)} from ${cap(args.person)}${args.upfront ? ' as an upfront deposit' : ''}`;
  }
  const entries = Object.entries(args ?? {}).filter(([k]) => k !== 'plan_id');
  return entries.map(([k, v]) => `${k}: ${JSON.stringify(v)}`).join(', ');
}

export function ApprovalCard({ approval, pending, onAnswer }: { approval: Approval; pending: boolean; onAnswer: (id: string, d: 'approve' | 'decline') => void }) {
  const tool = approval.tool ?? 'this action';
  // lock the buttons on the first click: the server answers once, and the state refresh confirms it
  const [sent, setSent] = useState<'approve' | 'decline' | null>(null);
  useEffect(() => { if (!pending) setSent(null); }, [pending]);
  const answer = (d: 'approve' | 'decline') => { if (sent) return; setSent(d); onAnswer(approval.id, d); };
  return (
    <div className={`card approval ${pending ? '' : 'decided'}`} data-testid="approval-card" data-approval-id={approval.id} data-pending={pending}>
      <div className="card-title">
        <ShieldAlert size={14} /> Flake needs Alex&rsquo;s approval
        {approval.version_id && <span className="tag" style={{ marginLeft: 'auto' }}>{approval.version_id.split(':').pop()}</span>}
      </div>
      <div className="question">
        Approve <b>{tool}</b>{approval.args && Object.keys(approval.args).length ? `: ${describeArgs(approval.tool, approval.args)}` : ''}?
      </div>
      {approval.reason && <div className="reason">Why the gate asks: {approval.reason}</div>}
      {pending ? (
        <div className="actions">
          {sent ? (
            <span className="decision"><Loader2 size={13} className="spin" /> {sent === 'approve' ? 'Approving…' : 'Declining…'}</span>
          ) : (
            <>
              <button className="btn approve" onClick={() => answer('approve')} data-testid="approve">Approve</button>
              <button className="btn decline" onClick={() => answer('decline')} data-testid="decline">Decline</button>
            </>
          )}
        </div>
      ) : (
        <div className={`decision ${approval.decision ?? ''}`}>
          {approval.decision === 'approve' ? 'Approved ✓' : approval.decision === 'decline' ? 'Declined ✕' : 'Cancelled by reset'}
        </div>
      )}
    </div>
  );
}
