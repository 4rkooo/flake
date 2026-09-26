import type { State } from './types';

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? JSON.stringify(body);
    } catch {
      /* keep statusText */
    }
    throw new Error(detail);
  }
  return (await res.json()) as T;
}

export const api = {
  state: () => fetch('/api/state').then((r) => json<State>(r)),
  next: () => fetch('/api/next', { method: 'POST' }).then((r) => json<Record<string, unknown>>(r)),
  reset: () => fetch('/api/reset', { method: 'POST' }).then((r) => json<{ session: string }>(r)),
  answer: (id: string, decision: 'approve' | 'decline') =>
    fetch(`/api/approvals/${id}`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ decision }),
    }).then((r) => json<Record<string, unknown>>(r)),
  pace: (factor: number) =>
    fetch('/api/pace', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ factor }) })
      .then((r) => json<{ pace: number }>(r)),
  eventsUrl: (session: string, since: number) =>
    `/api/events?session=${encodeURIComponent(session)}&since=${since}`,
};
