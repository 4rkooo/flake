import { useEffect, useMemo, useState } from 'react';
import { Bot, MessageSquare, ShieldAlert } from 'lucide-react';
import { ActivityFeed } from './components/ActivityFeed';
import { AgentDiagram } from './components/AgentDiagram';
import { ChatPanel } from './components/ChatPanel';
import { Evidence, type EvidenceTab } from './components/Evidence';
import { TopBar } from './components/TopBar';
import { describeArgs } from './components/ApprovalCard';
import { deriveChat, deriveDiagram } from './lib/derive';
import { useDemo } from './lib/useDemo';

const NOISE = new Set(['node.end', 'node.start', 'db.op', 'checkpoint.saved', 'llm.cache', 'llm.cache.stored']);

export default function App() {
  const demo = useDemo();
  const [pane, setPane] = useState<'chat' | 'agent'>('chat');
  const [tab, setTab] = useState<EvidenceTab>('inspector');
  const chat = useMemo(() => deriveChat(demo.events, demo.state), [demo.events, demo.state]);
  const diagram = useMemo(() => deriveDiagram(demo.events), [demo.events]);
  const latest = demo.events[demo.events.length - 1];
  const selected = useMemo(() => {
    if (demo.selectedSeq != null) return demo.events.find((e) => e.seq === demo.selectedSeq) ?? null;
    for (let i = demo.events.length - 1; i >= 0; i--) if (!NOISE.has(demo.events[i].kind)) return demo.events[i];
    return null;
  }, [demo.events, demo.selectedSeq]);

  // while following live, land on the evidence the current beat is about
  useEffect(() => {
    if (!demo.live || !latest) return;
    if (latest.kind === 'reset.done') setTab('policy');
    else if (latest.kind === 'policy.compared') setTab('compare');
    else if (latest.kind === 'retro.done' || latest.kind === 'canary.evaluated') setTab('versions');
    else if (latest.kind === 'plan.start' || latest.kind === 'risk.profiles') setTab('inspector');
  }, [latest, demo.live]);

  const pending = demo.state?.pending_approvals ?? [];
  const selectNode = (id: string) => {
    for (let i = demo.events.length - 1; i >= 0; i--) {
      const e = demo.events[i];
      if (e.node === id && e.kind !== 'node.end') { demo.select(e.seq); setTab('inspector'); return; }
    }
  };
  return (
    <div className="app">
      <TopBar state={demo.state} connected={demo.connected} onNext={demo.next} onReset={demo.reset} onPace={demo.setPace} />
      <nav className="mobile-tabs" aria-label="Panels">
        <button className={pane === 'chat' ? 'on' : ''} onClick={() => setPane('chat')} data-testid="tab-chat"><MessageSquare size={15} /> Chat {pending.length > 0 && <span className="badge">{pending.length}</span>}</button>
        <button className={pane === 'agent' ? 'on' : ''} onClick={() => setPane('agent')} data-testid="tab-agent"><Bot size={15} /> Agent</button>
      </nav>
      <div className="main">
        <section className={`chat-pane ${pane === 'chat' ? 'on' : ''}`} data-testid="chat-pane">
          <ChatPanel items={chat} state={demo.state} onAnswer={demo.answer} inFlight={demo.inFlight} active={pane === 'chat'} typing={!!demo.state?.busy && demo.state.beat.operation === 'plan' && pending.length === 0} />
        </section>
        <section className={`agent-pane ${pane === 'agent' ? 'on' : ''}`} data-testid="agent-pane">
          {pending.length > 0 && (
            <div className="banner" data-testid="approval-banner">
              <ShieldAlert size={16} />
              <span>Alex&rsquo;s approval needed: <b>{pending[0].tool}</b> {pending[0].args && Object.keys(pending[0].args).length ? `(${describeArgs(pending[0].tool, pending[0].args)})` : ''}</span>
              <span className="actions">
                <button className="btn small approve" disabled={demo.inFlight.has(pending[0].id)} onClick={() => demo.answer(pending[0].id, 'approve')} data-testid="banner-approve">Approve</button>
                <button className="btn small decline" disabled={demo.inFlight.has(pending[0].id)} onClick={() => demo.answer(pending[0].id, 'decline')} data-testid="banner-decline">Decline</button>
                {pending.length > 1 && (
                  <button className="btn small" onClick={() => pending.forEach((a) => demo.answer(a.id, 'approve'))} data-testid="banner-approve-all">Approve all {pending.length}</button>
                )}
              </span>
            </div>
          )}
          <AgentDiagram diagram={diagram} selectedNode={selected?.node ?? null} onSelectNode={selectNode} />
          <div className="below">
            <ActivityFeed events={demo.events} selectedSeq={demo.selectedSeq} live={demo.live} onSelect={(seq) => { demo.select(seq); setTab('inspector'); }} onLive={demo.goLive} active={pane === 'agent'} />
            <Evidence tab={tab} setTab={setTab} event={selected} state={demo.state} />
          </div>
        </section>
      </div>
      {demo.toast && <div className="toast" role="status">{demo.toast}</div>}
    </div>
  );
}
