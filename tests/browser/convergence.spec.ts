import { test, expect, type Page } from '@playwright/test';

test('independent consumers recover their own cursors and an invalid run cannot contaminate the peer', async ({ browser }) => {
  const contexts = await Promise.all([browser.newContext(), browser.newContext()]);
  const pages = await Promise.all(contexts.map(c => c.newPage()));
  const run = 'two-consumers', cursors: string[][] = [[], []];
  let version = 1, blocked = false, invalid = false;
  const snapshot = (v: number) => ({ run_id: run, tick: v, clock_mode: 'fixture',
    goal: { items: { tent: 3 }, deadline_tick: 120, recipient: 'venue' }, suppliers: ['A'],
    inventory: { tent: v >= 3 ? 3 : 0 }, balance: { budget: 500, spent: v >= 3 ? 310 : 0, reserved: 0, available: v >= 3 ? 190 : 500 } });
  const frame = (kind: string, data: unknown, cursor: number) => `id: ${cursor}\nevent: ${kind}\ndata: ${JSON.stringify(data)}\n\n`;
  const reconnect = (p: Page) => p.getByRole('button', { name: 'Reconnect' }).click();
  try {
    for (const [i, page] of pages.entries()) {
      await page.route('**/api/observer/config', r => r.fulfill({ json: { configured: true, run_id: run, read_only: true, mode: 'live-observer' } }));
      await page.route('**/api/observer/events', r => {
        const cursor = r.request().headers()['last-event-id']; cursors[i].push(cursor);
        if (i === 1 && blocked) return r.fulfill({ status: 503, body: 'isolated consumer' });
        const event = { event_id: `event-${version}`, run_id: invalid && i === 0 ? 'other-run' : run,
          version, event_type: 'state.observed', observed_at: Date.now() / 1000, snapshot: snapshot(version) };
        const reset = version === 10 && i === 1 && Number(cursor) < 8;
        return r.fulfill({ contentType: 'text/event-stream', body: reset
          ? frame('snapshot', { run_id: run, reset: true, next_cursor: version, snapshot_event: event }, version)
          : frame('observation', { cursor: version, published_at: Date.now() / 1000, event }, version) });
      });
      await page.goto('/');
      await expect(page.getByTestId('cursor')).toHaveText('1');
    }
    blocked = true; version = 2;
    await reconnect(pages[0]); await reconnect(pages[1]);
    await expect(pages[0].getByTestId('cursor')).toHaveText('2');
    await expect(pages[1].getByTestId('cursor')).toHaveText('1');
    blocked = false; await reconnect(pages[1]);
    await expect(pages[1].getByTestId('cursor')).toHaveText('2');
    expect(cursors[1]).toContain('1');
    await expect(pages[1].getByText('Snapshot restored')).toHaveCount(0);
    blocked = true; version = 10;
    await reconnect(pages[1]); await reconnect(pages[0]);
    await expect(pages[0].getByTestId('spent')).toHaveText('310credits');
    await expect(pages[1].getByTestId('spent')).toHaveText('0credits');
    blocked = false; await reconnect(pages[1]);
    await expect(pages[1].getByText('Snapshot restored')).toBeVisible();
    for (const p of pages) {
      await expect(p.getByTestId('cursor')).toHaveText('10');
      await expect(p.getByTestId('spent')).toHaveText('310credits');
      await expect(p.getByTestId('inventory-tent')).toHaveText('3 / 3');
    }
    expect(cursors[0]).toContain('2'); expect(cursors[1]).toContain('2');
    invalid = true; version = 11; await reconnect(pages[0]);
    await expect(pages[0].getByTestId('connection')).toHaveText('Event validation failed');
    await expect(pages[0].getByTestId('cursor')).toHaveText('10');
    await reconnect(pages[1]);
    await expect(pages[1].getByTestId('cursor')).toHaveText('11');
    await expect(pages[1].getByTestId('spent')).toHaveText('310credits');
  } finally { await Promise.all(contexts.map(c => c.close())); }
});
