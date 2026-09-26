import { expect, test } from '@playwright/test';
import { expectNoHorizontalOverflow, expectNoOverlap, firstPendingApproval, resetAndWait, runBeatApproving, state, waitIdle } from './helpers';

test.describe('desktop', () => {
  test.skip(({ isMobile }) => !!isMobile, 'desktop layout only');

  test('chat beside the diagram, first two beats with clickable approvals', async ({ page }) => {
    await resetAndWait(page);
    await page.goto('/');
    await expect(page.getByTestId('topbar')).toBeVisible();
    await expect(page.getByTestId('chat-pane')).toBeVisible();
    await expect(page.getByTestId('diagram')).toBeVisible();
    await expect(page.getByTestId('feed')).toBeVisible();
    await expect(page.getByTestId('evidence')).toBeVisible();
    await expectNoHorizontalOverflow(page);
    await expectNoOverlap(page, '.topbar');
    await expectNoOverlap(page, '.topbar .chips');

    // the baseline is loaded: policy chip, versions, risk table on the Policy tab
    await expect(page.getByTestId('policy-chip')).toContainText('v1 active');
    await expect(page.getByTestId('stage-chip')).toContainText('Reset / baseline');
    await page.getByTestId('tab-policy').click();
    await expect(page.getByTestId('policy-view')).toContainText('max_nonrefundable_exposure_usd');
    await expect(page.getByTestId('risk-table')).toContainText('Sam');

    // Taco Tuesday: the booking is held until Alex approves
    await page.getByTestId('next-beat').click();
    const approve = page.getByTestId('approve').first();
    await expect(approve).toBeVisible({ timeout: 60_000 });
    await expect(page.getByTestId('receipt-card')).toHaveCount(0);
    await expect(page.getByTestId('approval-card').first()).toContainText('book');
    await expect(page.getByTestId('next-beat')).toBeDisabled();
    await approve.click();
    const moneyCard = page.getByTestId('approval-card').filter({ hasText: 'request_money' }).first(); // the first money request
    await expect(moneyCard).toBeVisible({ timeout: 60_000 });
    await moneyCard.getByTestId('approve').click();
    await expect(page.getByTestId('receipt-card')).toBeVisible({ timeout: 60_000 });
    await expect(page.getByTestId('stage-chip')).toContainText('done', { timeout: 60_000 });
    await expect(page.getByTestId('bubble').filter({ hasText: 'Taco Tuesday' }).first()).toBeVisible();
    expect(Number(await page.getByTestId('node-gate').getAttribute('data-count'))).toBeGreaterThan(0);
    expect(Number(await page.getByTestId('node-tools').getAttribute('data-count'))).toBeGreaterThan(0);
    await expectNoHorizontalOverflow(page);
    await expect(page.getByTestId('next-beat')).toBeEnabled();
    // the presenter can change the pace live; the server keeps it
    await page.getByTestId('pace-select').selectOption('0.5');
    await expect.poll(async () => (await state(page)).pace).toBe(0.5);
    await page.getByTestId('pace-select').selectOption('0');
    await expect.poll(async () => (await state(page)).pace).toBe(0);
  });

  test('selecting an event highlights its node and opens the inspector; Live returns', async ({ page }) => {
    await resetAndWait(page);
    await runBeatApproving(page); // Taco Tuesday through the API
    await page.goto('/');
    await expect(page.getByTestId('feed-row').first()).toBeVisible();
    const row = page.getByTestId('feed-row').filter({ hasText: 'Gate ASK' }).first();
    await row.click();
    await expect(page.getByTestId('inspector')).toContainText('Requested by the model');
    await expect(page.getByTestId('inspector')).toContainText('taco-council:v1');
    await expect(page.getByTestId('node-gate')).toHaveAttribute('data-selected', 'true');
    await expect(page.getByTestId('live-toggle')).toContainText('Back to live');
    await page.getByTestId('live-toggle').click();
    await expect(page.getByTestId('live-toggle')).toContainText('Live');
    await expect(page.getByTestId('node-gate')).toHaveAttribute('data-selected', 'false');
    // clicking a node selects its latest event
    await page.getByTestId('node-memory').click();
    await expect(page.getByTestId('node-memory')).toHaveAttribute('data-selected', 'true');
    await expect(page.getByTestId('inspector')).toBeVisible();
  });

  test('reload rebuilds the view from the journal; reset gives a fresh session', async ({ page }) => {
    await resetAndWait(page);
    await runBeatApproving(page);
    await page.goto('/');
    await expect.poll(() => page.getByTestId('feed-row').count()).toBeGreaterThan(10);
    const rowsBefore = await page.getByTestId('feed-row').count();
    await page.reload();
    await expect.poll(() => page.getByTestId('feed-row').count()).toBe(rowsBefore);   // replayed from the journal, nothing rerun
    await expect(page.getByTestId('receipt-card')).toBeVisible();
    const before = (await state(page)).session;
    await page.getByTestId('reset-demo').click();
    await waitIdle(page);
    expect((await state(page)).session).not.toBe(before);
    await expect(page.getByTestId('receipt-card')).toHaveCount(0);
    await expect(page.getByTestId('system-line').filter({ hasText: 'Demo reset' })).toBeVisible();
  });
});

test.describe('narrow', () => {
  test.skip(({ isMobile }) => !isMobile, 'narrow layout only');

  test('tabs switch panes while controls and approvals stay reachable', async ({ page }) => {
    await resetAndWait(page);
    await page.goto('/');
    await expect(page.getByTestId('tab-chat')).toBeVisible();
    await expect(page.getByTestId('next-beat')).toBeVisible();
    await expect(page.getByTestId('reset-demo')).toBeVisible();
    await expect(page.getByTestId('chat-pane')).toBeVisible();
    await expect(page.getByTestId('agent-pane')).toBeHidden();
    await expectNoHorizontalOverflow(page);
    await expectNoOverlap(page, '.topbar');

    await page.request.post('/api/next'); // Taco Tuesday
    const ap = await firstPendingApproval(page);
    await expect(page.getByTestId('tab-chat')).toContainText('1');
    await page.getByTestId('tab-agent').click();
    await expect(page.getByTestId('agent-pane')).toBeVisible();
    await expect(page.getByTestId('chat-pane')).toBeHidden();
    await expect(page.getByTestId('diagram')).toBeVisible();
    await expect(page.getByTestId('approval-banner')).toBeVisible();
    await expect(page.getByTestId('approval-banner')).toContainText(ap.tool);
    await expectNoHorizontalOverflow(page);
    await page.getByTestId('banner-approve').click();
    await expect(page.getByTestId('approval-banner')).toContainText('request_money', { timeout: 60_000 });
    await page.getByTestId('tab-chat').click();
    await expect(page.getByTestId('approve').first()).toBeVisible();
    await page.getByTestId('approve').first().click();
    await expect(page.getByTestId('receipt-card')).toBeVisible({ timeout: 60_000 });
    await expectNoHorizontalOverflow(page);
    // the diagram stays inside the narrow viewport
    await page.getByTestId('tab-agent').click();
    const box = await page.getByTestId('diagram').boundingBox();
    expect(box).not.toBeNull();
    expect(box!.x + box!.width).toBeLessThanOrEqual(page.viewportSize()!.width + 1);
    for (const id of ['memory', 'agent', 'gate', 'tools', 'policy']) {
      const nb = await page.getByTestId(`node-${id}`).boundingBox();
      expect(nb, `node ${id} rendered`).not.toBeNull();
      expect(nb!.x + nb!.width, `node ${id} inside the viewport`).toBeLessThanOrEqual(page.viewportSize()!.width + 1);
    }
  });
});
