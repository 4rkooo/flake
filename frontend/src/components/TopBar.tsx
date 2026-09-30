import { Bird, Gauge, Loader2, Play, RotateCcw, ShieldCheck, Wifi, WifiOff } from 'lucide-react';
import type { State } from '../lib/types';

interface Props {
  state: State | null;
  connected: boolean;
  onNext: () => void;
  onReset: () => void;
  onPace: (factor: number) => void;
}

// presentation pace: how long the worker holds each step on screen (1 = about a second per step)
const PACES: { label: string; value: number }[] = [
  { label: 'Slow', value: 2 }, { label: 'Normal', value: 1 }, { label: 'Fast', value: 0.5 }, { label: 'Instant', value: 0 },
];

const short = (id?: string | null) => (id ? id.split(':').pop() : null);

export function TopBar({ state, connected, onNext, onReset, onPace }: Props) {
  const beat = state?.beat;
  const started = beat && beat.index >= 0;
  const active = state?.policy.active;
  const canary = state?.policy.canary;
  const nextLabel = !state ? 'Connecting…' : state.next_title ? `Next Beat: ${state.next_title}` : 'Script finished';
  return (
    <header className="topbar" data-testid="topbar">
      <div className="brand">
        <span className="logo" aria-hidden>F</span>
        <span>Flake</span>
        <span className="brand-sub muted small">visual demo</span>
      </div>
      <div className="chips">
        <span className={`chip stage status-${beat?.status ?? 'idle'}`} data-testid="stage-chip">
          <span className="label">Stage</span>
          <b>{started ? `${beat!.index + 1}/${state!.beats.length} ${beat!.title}` : 'Not started'}</b>
          {started && <span className="muted">{beat!.status}</span>}
        </span>
        <span className="chip policy" data-testid="policy-chip" title={active?.rationale ?? ''}>
          <ShieldCheck size={13} />
          <span className="label">Policy</span>
          <b>{active ? `${short(active._id)} active` : 'none yet'}</b>
        </span>
        <span className={`chip canary ${canary ? '' : 'none'}`} data-testid="canary-chip">
          <Bird size={13} />
          <span className="label">Canary</span>
          <b>{canary ? `${short(canary._id)} on trial` : 'none'}</b>
        </span>
        <span className={`chip connection ${connected ? '' : 'off'}`} data-testid="connection-chip">
          {connected ? <Wifi size={13} /> : <WifiOff size={13} />}
          <span>{connected ? 'live' : 'reconnecting'}</span>
        </span>
      </div>
      <div className="spacer" />
      <div className="controls">
        <label className="chip pace" title="How long each step stays on screen. Normal: a plan beat takes about two minutes; Slow doubles it; Fast halves it.">
          <Gauge size={13} />
          <span className="label">Pace</span>
          <select value={String(PACES.find((p) => p.value === state?.pace)?.value ?? state?.pace ?? 1)} onChange={(e) => onPace(Number(e.target.value))} disabled={!state} data-testid="pace-select">
            {PACES.map((p) => <option key={p.label} value={p.value}>{p.label}</option>)}
            {state && !PACES.some((p) => p.value === state.pace) && <option value={state.pace}>{state.pace}x</option>}
          </select>
        </label>
        <button className="btn primary" onClick={onNext} disabled={!state || !state.next_available} data-testid="next-beat" title={nextLabel}>
          {state?.busy ? <Loader2 size={15} className="spin" /> : <Play size={15} />}
          <span className="btn-text">{state?.busy ? `Running ${beat?.title ?? ''}…` : nextLabel}</span>
        </button>
        <button className="btn danger" onClick={onReset} data-testid="reset-demo" title="Reset Demo: cancel pending work, clear the demo database, reseed history and v1">
          <RotateCcw size={15} />
          <span className="btn-text">Reset Demo</span>
        </button>
      </div>
    </header>
  );
}
