import { test, expect } from '@playwright/test';
import { relation } from '../../web/src/Evidence';
import { Projection, SSEDecoder, frameCursor } from '../../web/src/observation';

const run = 'browser-fixture';
const snap = (spent = 0, tent = 0, light = 0) => ({ run_id: run, tick: 12,
  clock_mode: 'fixture', goal: { items: { tent: 3, light: 6 }, deadline_tick: 120, recipient: 'venue' },
  inventory: { tent, light }, balance: { budget: 500, spent, reserved: 0, available: 500 - spent }, suppliers: ['A', 'B', 'C'] });
const delivery = (cursor: number, version: number, spent = 0, tent = 0, light = 0) => ({ cursor, published_at: Date.now() / 1000,
  event: { run_id: run, event_id: `event-${version}`, version, observed_at: Date.now() / 1000 - .05,
    event_type: 'state.observed', source: 'browser-fixture', snapshot: snap(spent, tent, light) } });
const frame = (type: string, data: unknown, id?: number) => `${id === undefined ? '' : `id: ${id}\n`}event: ${type}\ndata: ${JSON.stringify(data)}\n\n`;
const status = () => frame('status', { run_id: run, stale: false, last_poll: Date.now() / 1000, error: null });

test('incremental framing handles every split and multiline CRLF without early application', () => {
  const input = ': heartbeat\r\nid: 8\r\nevent: observation\r\ndata: {"x":\r\ndata: 1}\r\n\r\n';
  for (let split = 0; split <= input.length; split++) {
    const decoder = new SSEDecoder();
    const frames = [...decoder.push(input.slice(0, split)), ...decoder.push(input.slice(split))];
    expect(frames).toEqual([{ event: 'observation', id: '8', data: '{"x":\n1}' }]);
  }
  expect(() => new SSEDecoder().push('x'.repeat(1_048_577))).toThrow();
  expect(() => frameCursor({ event: 'observation', id: '9007199254740992', data: '{}' })).toThrow();
});

test('projection keeps newest ledger through duplicates, reordering and retention reset', () => {
  const p = new Projection(run), first = delivery(1, 1), latest = delivery(2, 2, 310, 3, 6);
  expect(p.apply(first)).toBe('applied');
  expect(p.apply(latest)).toBe('applied');
  expect(p.apply({ ...latest, cursor: 3 })).toBe('duplicate');
  expect(p.apply({ ...first, cursor: 4 })).toBe('duplicate');
  const old = delivery(5, 1); old.event.event_id = 'old-distinct';
  expect(p.apply(old)).toBe('old');
  p.reset({ run_id: run, reset: true, next_cursor: 10, snapshot_event: latest.event });
  expect(p.cursor).toBe(10);
  expect(p.snapshot).toEqual(snap(310, 3, 6));
  expect(() => p.reset({ run_id: run, reset: true, next_cursor: 9, snapshot_event: first.event })).toThrow();
  const conflict = structuredClone(latest); conflict.event.snapshot.balance.spent = 380; conflict.event.snapshot.balance.available = 120;
  expect(() => p.apply(conflict)).toThrow('EVENT_CONTENT_CONFLICT');
  conflict.event.event_id = 'different';
  expect(() => p.apply(conflict)).toThrow('OBSERVATION_VERSION_CONFLICT');
  conflict.event.run_id = 'another';
  expect(() => p.apply(conflict)).toThrow('RUN_SCOPE_DENIED');
  expect(p.snapshot).toEqual(snap(310, 3, 6));
});

test('evicted old fingerprints cannot roll back state and invalid balances do not advance cursor', () => {
  const p = new Projection(run), first = delivery(1, 1);
  p.apply(first);
  for (let n = 2; n <= 1002; n++) p.apply(delivery(n, n, 310, 3, 6));
  expect(p.apply({ ...first, cursor: 1003 })).toBe('old');
  const bad = delivery(1004, 1004); bad.event.snapshot.balance.available = 999;
  expect(() => p.apply(bad)).toThrow('INVALID_BALANCE');
  expect(p.cursor).toBe(1003);
  expect(p.snapshot).toEqual(snap(310, 3, 6));
});

test('observer renders snapshots, resumes cursor, deduplicates, and labels disconnected state', async ({ page }) => {
  const errors: string[] = [], requests: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.route('**/api/observer/config', route => route.fulfill({ json: { configured: true, run_id: run, read_only: true, mode: 'live-observer' } }));
  const first = delivery(1, 1), latest = delivery(2, 2, 310, 3, 6);
  await page.route('**/api/observer/events', async route => {
    const cursor = route.request().headers()['last-event-id']; requests.push(cursor);
    if (cursor === '0') await route.fulfill({ contentType: 'text/event-stream', body: frame('observation', first, 1) + frame('observation', latest, 2) + frame('observation', { ...latest, cursor: 3 }, 3) + frame('observation', { ...first, cursor: 4 }, 4) + status() });
    else await route.fulfill({ status: 503, body: 'fixture unavailable' });
  });
  await page.goto('/');
  await expect(page.getByTestId('spent')).toHaveText('310credits');
  await expect(page.getByTestId('inventory-tent')).toHaveText('3 / 3');
  await expect(page.getByTestId('inventory-light')).toHaveText('6 / 6');
  await expect(page.getByTestId('cursor')).toHaveText('4');
  await expect(page.getByText('Awaiting independent ledger verification')).toBeVisible();
  await expect(page.getByTestId('connection')).toHaveText('Disconnected');
  await expect(page.getByText('Showing the last received state.', { exact: false })).toBeVisible();
  await expect.poll(() => requests.includes('4')).toBe(true);
  for (const width of [1440, 390, 320]) {
    await page.setViewportSize({ width, height: 1000 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: `.local/cw06-browser/fixture-${width}.png`, fullPage: true });
  }
  await page.getByRole('button', { name: 'Reconnect' }).click();
  await expect(page.getByTestId('spent')).toHaveText('310credits');
  expect(errors).toEqual([]);
  expect(await page.locator('body').innerText()).not.toContain('observer_token');
});

test('retention recovery is applied and invalid cross-run events halt without changing the ledger', async ({ page }) => {
  await page.route('**/api/observer/config', route => route.fulfill({ json: { configured: true, run_id: run, read_only: true, mode: 'live-observer' } }));
  const latest = delivery(20, 7, 380, 3, 6), bad = delivery(21, 8);
  bad.event.run_id = 'other';
  let calls = 0;
  await page.route('**/api/observer/events', route => {
    calls++;
    return route.fulfill({ contentType: 'text/event-stream', body: frame('snapshot', { run_id: run, reset: true, next_cursor: 20, snapshot_event: latest.event }, 20) + frame('observation', bad, 21) });
  });
  await page.goto('/');
  await expect(page.getByTestId('connection')).toHaveText('Event validation failed');
  await expect(page.getByTestId('cursor')).toHaveText('20');
  await expect(page.getByTestId('spent')).toHaveText('380credits');
  await expect(page.getByText('Snapshot restored')).toBeVisible();
  const count = calls;
  await page.clock.install();
  await page.clock.fastForward(10_000);
  expect(calls).toBe(count);
});

test('unconfigured view has no fabricated balance, quantity or supplier', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByTestId('connection')).toHaveText('No observation source');
  await expect(page.getByTestId('spent')).toHaveText('—credits');
  await expect(page.getByTestId('received')).toHaveText('— / —');
  await expect(page.getByText('Supplier list unavailable')).toBeVisible();
});

test('historical verdict is qualified against run, goal, budget, tick and current ledger', async () => {
  const evidence = { status: 'VERIFIED' as const, reason: null, run_id: run, historical: true as const, checked_at: Date.now() / 1000,
    artifact: { run_id: run, goal: snap().goal, budget: 500, sha256: 'a'.repeat(64), bytes: 1000, captured_at_tick: 12 },
    verdict: { status: 'COMPLETE' as const, errors: [], spent: 310, reserved: 0, received_on_time: { tent: 3, light: 6 } } };
  expect(relation(evidence, snap(310, 3, 6), run)).toBe('matches');
  expect(relation(evidence, snap(310, 3, 6), 'other')).toBe('run');
  expect(relation(evidence, null, run)).toBe('unobserved');
  const goalChanged = snap(310, 3, 6); goalChanged.goal.items.tent = 4;
  expect(relation(evidence, goalChanged, run)).toBe('goal');
  const earlier = snap(310, 3, 6); earlier.tick = 11;
  expect(relation(evidence, earlier, run)).toBe('ahead');
  expect(relation(evidence, snap(380, 3, 6), run)).toBe('state');
});

test('evidence panel shows historical success then clears it on failed refresh', async ({ page }) => {
  await page.route('**/api/observer/config', route => route.fulfill({ json: { configured: true, run_id: run, read_only: true, mode: 'live-observer' } }));
  await page.route('**/api/observer/events', route => route.fulfill({ contentType: 'text/event-stream', body: frame('observation', delivery(1, 1, 310, 3, 6), 1) + status() }));
  let reject = false;
  await page.route('**/api/observer/evidence', route => route.fulfill({ json: reject ? { status: 'REJECTED', reason: 'EVIDENCE_HASH_MISMATCH', run_id: run, historical: true, checked_at: Date.now() / 1000, artifact: null, verdict: null } : {
    status: 'VERIFIED', reason: null, run_id: run, historical: true, checked_at: Date.now() / 1000,
    artifact: { run_id: run, goal: snap().goal, budget: 500, sha256: 'a'.repeat(64), bytes: 1000, captured_at_tick: 12 },
    verdict: { status: 'COMPLETE', errors: [], spent: 310, reserved: 0, received_on_time: { tent: 3, light: 6 } }, verifier: { name: 'verify_medusa', sha256: 'b'.repeat(64) },
  } }));
  await page.goto('/');
  await expect(page.getByTestId('evidence-result')).toContainText('Goal complete at evidence capture');
  await expect(page.getByTestId('evidence-result')).toContainText('Matches the last observed values');
  reject = true;
  await page.getByRole('button', { name: 'Reverify evidence' }).click();
  await expect(page.getByTestId('evidence-result')).toHaveText('The original file does not match the selected hash.');
  await expect(page.getByText('Awaiting independent ledger verification')).toBeVisible();
  await expect(page.getByTestId('spent')).toHaveText('310credits');
});

test('a past COMPLETE does not describe a different observed goal as verified', async ({ page }) => {
  await page.route('**/api/observer/config', route => route.fulfill({ json: { configured: true, run_id: run, read_only: true, mode: 'live-observer' } }));
  const current = delivery(1, 1, 310, 3, 6); current.event.snapshot.goal.items.tent = 4;
  await page.route('**/api/observer/events', route => route.fulfill({ contentType: 'text/event-stream', body: frame('observation', current, 1) }));
  await page.route('**/api/observer/evidence', route => route.fulfill({ json: {
    status: 'VERIFIED', reason: null, run_id: run, historical: true, checked_at: Date.now() / 1000,
    artifact: { run_id: run, goal: snap().goal, budget: 500, sha256: 'a'.repeat(64), bytes: 1000, captured_at_tick: 12 },
    verdict: { status: 'COMPLETE', errors: [], spent: 310, reserved: 0, received_on_time: { tent: 3, light: 6 } }, verifier: { name: 'verify_medusa', sha256: 'b'.repeat(64) },
  } }));
  await page.goto('/');
  await expect(page.getByTestId('evidence-result')).toContainText('The current goal or budget differs from the evidence.');
  await expect(page.getByText('Awaiting independent ledger verification')).toBeVisible();
});

test('catalog and orders render actual fields while unknown receipt never displays zero received', async ({ page }) => {
  await page.route('**/api/observer/config', route => route.fulfill({ json: { configured: true, run_id: run, read_only: true, mode: 'live-observer' } }));
  const observed = delivery(1, 1, 310, 3, 6);
  const commerce = { receipt_status: 'UNAVAILABLE', catalog: { source: 'medusa-store-sales-channel', status: 'PARTIAL', offers: [
    { supplier: 'A', item: 'tent', status: 'OBSERVED', stock: 0, unit_price: 60, currency: 'usd', inventory_managed: true, backorder: false },
    { supplier: 'B', item: 'light', status: 'UNAVAILABLE', stock: null, unit_price: null, currency: null, inventory_managed: null, backorder: null },
  ] }, orders: { status: 'PARTIAL', total: 1, truncated: false, items: [{ id: 'local-order', run_id: run, supplier: 'A', items: { tent: 3, light: 6 }, amount: 310, status: 'UNKNOWN', payment_status: 'UNKNOWN', created_tick: 2 }] } };
  await page.route('**/api/observer/events', route => route.fulfill({ contentType: 'text/event-stream', body: frame('observation', { ...observed, event: { ...observed.event, snapshot: { ...observed.event.snapshot, commerce } } }, 1) }));
  await page.goto('/');
  await expect(page.getByTestId('stock-A-tent')).toHaveText('0');
  await expect(page.getByTestId('stock-B-light')).toHaveText('Unknown');
  await expect(page.getByTestId('order-status')).toHaveText('Unknown');
  await expect(page.getByTestId('received')).toHaveText('— / 9');
  await expect(page.getByText('Receipt status unknown')).toBeVisible();
  for (const width of [1440, 390, 320]) {
    await page.setViewportSize({ width, height: 1000 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  }
});
