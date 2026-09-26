import { expect, type Page } from '@playwright/test';

export async function state(page: Page) {
  return (await page.request.get('/api/state')).json();
}

export async function waitIdle(page: Page, timeout = 90_000) {
  await expect.poll(async () => (await state(page)).busy, { timeout }).toBe(false);
}

/** Reset the fake server and wait for the baseline beat to finish. */
export async function resetAndWait(page: Page) {
  const r = await page.request.post('/api/reset');
  expect(r.ok()).toBeTruthy();
  await waitIdle(page);
  expect((await state(page)).beat.status).toBe('done');
}

/** Advance one beat through the API, approving every request as it appears. */
export async function runBeatApproving(page: Page) {
  const r = await page.request.post('/api/next');
  expect(r.ok()).toBeTruthy();
  await expect
    .poll(async () => {
      const s = await state(page);
      for (const a of s.pending_approvals) await page.request.post(`/api/approvals/${a.id}`, { data: { decision: 'approve' } });
      return s.busy;
    }, { timeout: 90_000 })
    .toBe(false);
}

export async function firstPendingApproval(page: Page) {
  await expect.poll(async () => (await state(page)).pending_approvals.length, { timeout: 60_000 }).toBeGreaterThan(0);
  return (await state(page)).pending_approvals[0];
}

/** No horizontal page scroll, and no scroll container wider than itself. */
export async function expectNoHorizontalOverflow(page: Page) {
  const bad = await page.evaluate(() => {
    const out: string[] = [];
    const doc = document.documentElement;
    if (doc.scrollWidth > doc.clientWidth + 1) out.push(`document ${doc.scrollWidth}>${doc.clientWidth}`);
    for (const sel of ['.chat-scroll', '.feed-scroll', '.evidence-body', '.topbar', '.main']) {
      const el = document.querySelector<HTMLElement>(sel);
      if (el && el.offsetParent !== null && el.scrollWidth > el.clientWidth + 1) out.push(`${sel} ${el.scrollWidth}>${el.clientWidth}`);
    }
    return out;
  });
  expect(bad, 'elements wider than their container').toEqual([]);
}

/** Visible siblings must not overlap and must sit inside the viewport. */
export async function expectNoOverlap(page: Page, selector: string) {
  const boxes = await page.evaluate((sel) => {
    const root = document.querySelector(sel);
    if (!root) return [];
    return [...root.children]
      .map((el) => el.getBoundingClientRect())
      .filter((b) => b.width > 0 && b.height > 0)
      .map((b) => ({ x: b.left, y: b.top, w: b.width, h: b.height }));
  }, selector);
  const vw = page.viewportSize()!.width;
  for (const b of boxes) {
    expect(b.x, `${selector} child starts inside the viewport`).toBeGreaterThanOrEqual(-1);
    expect(b.x + b.w, `${selector} child ends inside the viewport`).toBeLessThanOrEqual(vw + 1);
  }
  for (let i = 0; i < boxes.length; i++) {
    for (let j = i + 1; j < boxes.length; j++) {
      const a = boxes[i], b = boxes[j];
      const ix = Math.max(0, Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x));
      const iy = Math.max(0, Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y));
      expect(ix * iy, `${selector} children ${i} and ${j} overlap`).toBeLessThanOrEqual(4);
    }
  }
}
