import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from './api';
import type { DemoEvent, State } from './types';

// events that change the database view: refetch the state snapshot when one arrives
const REFRESH_KINDS = new Set([
  'beat.start', 'beat.done', 'beat.error', 'beat.cancelled', 'reset.done', 'reset.step',
  'approval.requested', 'approval.resolved', 'version.created', 'version.status', 'plan.recorded',
  'sim.resolved', 'canary.evaluated', 'policy.compared', 'risk.profiles', 'episode.created', 'tool.result',
]);

function mergeEvents(a: DemoEvent[], b: DemoEvent[]): DemoEvent[] {
  if (!a.length) return b;
  if (!b.length) return a;
  const bySeq = new Map<number, DemoEvent>();
  for (const e of a) bySeq.set(e.seq, e);
  for (const e of b) bySeq.set(e.seq, e);
  return [...bySeq.values()].sort((x, y) => x.seq - y.seq);
}

export function useDemo() {
  const [state, setState] = useState<State | null>(null);
  const [events, setEvents] = useState<DemoEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [selectedSeq, setSelectedSeq] = useState<number | null>(null);
  const [live, setLive] = useState(true);
  const sessionRef = useRef<string | null>(null);
  const lastSeqRef = useRef(0);
  const esRef = useRef<EventSource | null>(null);
  const timerRef = useRef<number | undefined>(undefined);
  const [inFlight, setInFlight] = useState<Set<string>>(new Set());

  const refresh = useCallback(async () => {
    try {
      const s = await api.state();
      if (sessionRef.current && s.session !== sessionRef.current) {
        // the server was reset (or restarted) behind our back: start over
        setEvents(s.events);
        setSelectedSeq(null);
        setLive(true);
      } else {
        setEvents((prev) => mergeEvents(prev, s.events));
      }
      sessionRef.current = s.session;
      lastSeqRef.current = Math.max(lastSeqRef.current, s.cursor);
      setState(s);
    } catch (e) {
      setToast(`Cannot reach the demo server: ${(e as Error).message}`);
    }
  }, []);

  const scheduleRefresh = useCallback(() => {
    window.clearTimeout(timerRef.current);
    timerRef.current = window.setTimeout(refresh, 150);
  }, [refresh]);

  useEffect(() => {
    let closed = false;
    (async () => {
      await refresh();
      if (closed || !sessionRef.current) return;
      const es = new EventSource(api.eventsUrl(sessionRef.current, lastSeqRef.current));
      esRef.current = es;
      es.addEventListener('hello', (e) => {
        setConnected(true);
        const d = JSON.parse((e as MessageEvent).data) as { session: string };
        if (d.session !== sessionRef.current) {
          sessionRef.current = d.session;
          lastSeqRef.current = 0;
          setEvents([]);
          setSelectedSeq(null);
          setLive(true);
          scheduleRefresh();
        }
      });
      es.addEventListener('flake', (e) => {
        const ev = JSON.parse((e as MessageEvent).data) as DemoEvent;
        if (ev.session !== sessionRef.current) {
          sessionRef.current = ev.session;
          setEvents([]);
          setSelectedSeq(null);
          setLive(true);
          scheduleRefresh();
        }
        lastSeqRef.current = ev.seq;
        setEvents((prev) => (prev.length && prev[prev.length - 1].seq >= ev.seq ? mergeEvents(prev, [ev]) : [...prev, ev]));
        if (REFRESH_KINDS.has(ev.kind)) scheduleRefresh();
      });
      es.onerror = () => setConnected(false);
    })();
    return () => {
      closed = true;
      esRef.current?.close();
      window.clearTimeout(timerRef.current);
    };
  }, [refresh, scheduleRefresh]);

  // while an operation runs, poll the snapshot too (approvals, beat status) in case a burst was missed
  useEffect(() => {
    if (!state?.busy) return;
    const id = window.setInterval(refresh, 4000);
    return () => window.clearInterval(id);
  }, [state?.busy, refresh]);

  useEffect(() => {
    if (!toast) return;
    const id = window.setTimeout(() => setToast(null), 4000);
    return () => window.clearTimeout(id);
  }, [toast]);

  const act = useCallback(
    async (fn: () => Promise<unknown>) => {
      try {
        await fn();
        scheduleRefresh();
        return true;
      } catch (e) {
        // concatenate rather than overwrite: concurrent failures (e.g. "Approve all")
        // would otherwise silently clobber each other's toast message
        setToast((prev) => (prev ? `${prev}\n${(e as Error).message}` : (e as Error).message));
        return false;
      }
    },
    [scheduleRefresh],
  );

  const answer = useCallback(
    async (id: string, decision: 'approve' | 'decline') => {
      if (inFlight.has(id)) return false;
      setInFlight((s) => new Set(s).add(id));
      const ok = await act(() => api.answer(id, decision));
      setInFlight((s) => {
        const n = new Set(s);
        n.delete(id);
        return n;
      });
      return ok;
    },
    [act, inFlight],
  );

  return {
    state,
    events,
    connected,
    toast,
    selectedSeq,
    live,
    inFlight,
    next: () => act(api.next),
    reset: () => act(api.reset),
    answer,
    setPace: (factor: number) => act(() => api.pace(factor)),
    select: (seq: number | null) => {
      setSelectedSeq(seq);
      setLive(false);
    },
    goLive: () => {
      setSelectedSeq(null);
      setLive(true);
    },
  };
}
