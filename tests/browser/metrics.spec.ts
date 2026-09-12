import { test, expect } from '@playwright/test';
import { readFile } from 'node:fs/promises';
import { distribution, ObservationMetrics } from '../../web/src/metrics';
const event = (version = 1) => ({ event_id: `event-${version}`, event_type: 'state.observed', version,
  observed_at: 100.1, poll_started_at: 100, poll_elapsed_seconds: .1 });
const receive = (m: ObservationMetrics, version = 1, outcome: 'applied' | 'old' | 'duplicate' | 'reset_applied' = 'applied', publish: number | null = 100.4) => {
  m.count(outcome.startsWith('reset') ? 'snapshot' : 'observation');
  m.receive(event(version), version, publish, outcome, 0, 100500, 10, true);
};

test('nearest-rank percentiles and independent stage denominators use recorded timestamps', () => {
  expect(distribution([40, 10, 30, 20])).toEqual({ n: 4, p50: 20, p95: 40, max: 40, excluded: {} });
  const m = new ObservationMetrics('run');
  receive(m); m.rendered(1, 100520, 30, true);
  receive(m, 1, 'duplicate'); receive(m, 2, 'old');
  const s = m.summary();
  expect(s.poll.n).toBe(2);
  expect(s.publication.n).toBe(3);
  expect(s.publication.p50).toBeCloseTo(300);
  expect(s.transport.p95).toBeCloseTo(100);
  expect(s.render).toEqual({ n: 1, p50: 20, p95: 20, max: 20, excluded: { not_applied: 2 } });
  expect(s.observed_to_render.p50).toBeCloseTo(420);
  expect(s.poll_to_render.p50).toBeCloseTo(520);
});

test('superseded, hidden, reset timing and clock reversal never become zero-latency successes', () => {
  const m = new ObservationMetrics('run');
  receive(m, 1); receive(m, 2);
  m.rendered(2, 100520, 30, false);
  receive(m, 3, 'reset_applied', null); m.rendered(3, 100520, 30, true);
  receive(m, 4); m.rendered(4, 101520, 30, true);
  const s = m.summary();
  expect(s.render.n).toBe(2);
  expect(s.render.excluded).toEqual({ superseded: 1, hidden: 1 });
  expect(s.publication.excluded.missing_timing).toBe(1);
  expect(s.observed_to_render.n).toBe(1);
  expect(s.observed_to_render.excluded.clock_order).toBe(1);
  const inverted = new ObservationMetrics('run');
  inverted.count('observation');
  inverted.receive(event(), 1, 101, 'applied', 0, 100500, 10, true);
  inverted.rendered(1, 100520, 30, true);
  expect(inverted.summary().transport.excluded.clock_order).toBe(1);
  expect(inverted.summary().observed_to_render.n).toBe(0);
});

test('retained-window eviction and process restart totals are explicit', () => {
  const m = new ObservationMetrics('run', 2, 100);
  for (let i = 1; i <= 3; i++) { receive(m, i); m.rendered(i, 100520, 30, true); }
  m.server({ process_id: 'p1', attempted: 5, completed: 4, failed: 1, unchanged: 2, in_flight: false });
  m.server({ process_id: 'p1', attempted: 8, completed: 6, failed: 2, unchanged: 3, in_flight: false });
  m.server({ process_id: 'p2', attempted: 1, completed: 0, failed: 0, unchanged: 0, in_flight: true });
  m.server({ process_id: 'p2', attempted: 0, completed: 99, failed: 0, unchanged: 0, in_flight: false });
  const output = m.export(200);
  expect(output.counters.evicted).toBe(1);
  expect(output.retained).toBe(2);
  expect(output.summary.render.n).toBe(2);
  expect(output.server_periods).toHaveLength(2);
  expect(output.server_periods[0].first.attempted).toBe(5);
  expect(output.server_periods[0].last.attempted).toBe(8);
  expect(output.server_periods[1].last.attempted).toBe(1);
  expect(output.samples.map(s => s.version)).toEqual([2, 3]);
});

test('legacy timing stays missing and malformed event labels cannot add arbitrary counters', () => {
  const m = new ObservationMetrics('run');
  m.count('observation');
  m.receive({ event_id: 'old', event_type: 'snapshot.observed', version: 1, observed_at: 100 }, 1, 100.2, 'applied', 0, 100500, 10, true);
  m.rendered(1, 100520, 30, true);
  expect(m.summary().poll).toEqual({ n: 0, p50: null, p95: null, max: null, excluded: { missing_timing: 1 } });
  m.count('__proto__'); m.count('secret-event-name');
  expect(m.counters.unknown_frames).toBe(2);
  expect(JSON.stringify(m.export())).not.toContain('secret-event-name');
});

test('browser download records actual commit samples and batched exclusions', async ({ page }) => {
  const now = Date.now() / 1000;
  const snapshot = { run_id: 'metrics-fixture', tick: 1, clock_mode: 'fixture', goal: { items: { tent: 3 }, deadline_tick: 120, recipient: 'venue' }, inventory: { tent: 0 }, balance: { budget: 500, spent: 0, reserved: 0, available: 500 }, suppliers: ['A'] };
  const frames = [1, 2].map(version => `id: ${version}\nevent: observation\ndata: ${JSON.stringify({ cursor: version, published_at: now, event: { ...event(version), run_id: snapshot.run_id, observed_at: now - 2, poll_started_at: now - 2.1, snapshot } })}\n\n`).join('');
  await page.route('**/api/observer/config', r => r.fulfill({ json: { configured: true, run_id: snapshot.run_id, read_only: true, mode: 'live-observer' } }));
  await page.route('**/api/observer/events', r => r.fulfill({ contentType: 'text/event-stream', body: frames }));
  await page.goto('/');
  await expect(page.getByTestId('metric-n-render')).toHaveText('1');
  await page.getByLabel('Sample type').selectOption('delivery.observed');
  await expect(page.getByTestId('metric-n-render')).toHaveText('0');
  await page.getByLabel('Sample type').selectOption('state.observed');
  await expect(page.getByTestId('metric-n-render')).toHaveText('1');
  for (const width of [1440, 390, 320]) {
    await page.setViewportSize({ width, height: 1000 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  }
  const saved = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Download metrics JSON' }).click();
  const download = await saved, output = JSON.parse(await readFile((await download.path())!, 'utf8'));
  expect(output.counters.observation).toBe(2);
  expect(output.summary.render.n).toBe(1);
  expect(output.summary.render.excluded.superseded).toBe(1);
  expect(output.summary.publication.p50).toBeCloseTo(2000);
  expect(output.samples.every((s: {render_status: string}) => ['superseded', 'rendered'].includes(s.render_status))).toBe(true);
  expect(JSON.stringify(output)).not.toContain('observer_token');
});
