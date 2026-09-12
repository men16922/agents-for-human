/** Two separate Chromium processes; real HTTP/SSE with per-context offline faults. */
import { chromium, expect } from '@playwright/test';
import { writeFile, readFile, access } from 'node:fs/promises';
import { join } from 'node:path';
const directory = process.argv[2], browsers = [], pages = [], contexts = [];
const requests = [[], []], errors = [[], []];
const save = async (name, value) => writeFile(join(directory, name + '.json'), JSON.stringify(value, null, 2) + '\n');
const waitFile = async name => {
  await expect.poll(async () => { try { await access(join(directory, name + '.json')); return true; } catch { return false; } }, { timeout: 45_000 }).toBe(true);
  return JSON.parse(await readFile(join(directory, name + '.json'), 'utf8'));
};
const state = page => page.evaluate(() => {
  const keys = ['cursor', 'tick', 'budget', 'spent', 'reserved', 'available', 'inventory-tent', 'inventory-light', 'order-status', 'order-payment', ...['A', 'B', 'C'].flatMap(s => ['tent', 'light'].map(i => `stock-${s}-${i}`))];
  return { ...Object.fromEntries(keys.map(k => [k, document.querySelector(`[data-testid="${k}"]`)?.textContent ?? null])),
    revision: document.querySelector('.revision')?.textContent, run: document.querySelector('.run-id')?.textContent,
    commerce: document.querySelector('.commerce-grid')?.textContent };
});
const converge = async () => {
  let pair;
  await expect.poll(async () => {
    pair = await Promise.all(pages.map(state));
    return JSON.stringify(pair[0]) === JSON.stringify(pair[1]);
  }, { timeout: 15_000 }).toBe(true);
  return pair;
};
const pause = async () => {
  await contexts[1].setOffline(true);
  // Explicit reconnect aborts the existing stream; offline config fetch then fails.
  await pages[1].getByRole('button', { name: 'Reconnect' }).click();
  await expect(pages[1].getByTestId('connection')).toHaveText('Disconnected');
  return state(pages[1]);
};
const resume = async () => {
  await contexts[1].setOffline(false);
  await pages[1].getByRole('button', { name: 'Reconnect' }).click();
  await expect(pages[1].getByTestId('connection')).toHaveText('Live connection');
};
try {
  for (let i = 0; i < 2; i++) {
    const browser = await chromium.launch({ headless: true }); browsers.push(browser);
    const context = await browser.newContext({ viewport: { width: 1440, height: 1050 } }); contexts.push(context);
    const page = await context.newPage(); pages.push(page);
    page.on('pageerror', error => errors[i].push(error.message));
    page.on('request', r => { if (r.url().includes('/api/observer/')) requests[i].push({ url: r.url(), cursor: r.headers()['last-event-id'] ?? null, hasAuthorization: 'authorization' in r.headers() }); });
    await page.goto('http://127.0.0.1:15173');
    await expect(page.getByTestId('stock-A-tent')).toHaveText('10', { timeout: 20_000 });
  }
  await save('initial', { states: await converge(), browser_processes: 2 });
  const short = await pause(); await save('short-offline', short);
  await expect(pages[0].getByTestId('stock-A-tent')).toHaveText('0', { timeout: 20_000 });
  expect(await state(pages[1])).toEqual(short);
  await save('short-diverged', { states: await Promise.all(pages.map(state)) });
  await resume();
  await expect(pages[1].getByTestId('stock-A-tent')).toHaveText('0');
  await expect(pages[1].getByText('Snapshot restored')).toHaveCount(0);
  expect(requests[1].some(r => r.cursor === short.cursor)).toBe(true);
  await save('short-recovered', { states: await converge(), resume_cursor: short.cursor });
  const long = await pause(); await save('long-offline', long);
  await expect(pages[0].getByTestId('inventory-light')).toHaveText('6 / 6', { timeout: 35_000 });
  const retention = await waitFile('retention-ready');
  expect(retention.reset).toBe(true);
  expect(retention.retained_after).toBeGreaterThan(Number(long.cursor));
  expect(await state(pages[1])).toEqual(long);
  expect(Number((await state(pages[0])).tick.split(' / ')[0])).toBeGreaterThan(Number(long.tick.split(' / ')[0]));
  await save('long-diverged', { states: await Promise.all(pages.map(state)), retained_after: retention.retained_after });
  await resume();
  await expect(pages[1].getByText('Snapshot restored')).toBeVisible();
  await expect(pages[1].getByTestId('inventory-light')).toHaveText('6 / 6');
  await expect(pages[1].getByTestId('spent')).toHaveText('380credits');
  await expect(pages[1].getByTestId('order-payment')).toHaveText('Settled');
  await expect(pages[1].getByTestId('stock-B-tent')).toHaveText('7');
  await expect(pages[1].getByTestId('stock-B-light')).toHaveText('4');
  const final = await converge();
  expect(requests[1].some(r => r.cursor === long.cursor)).toBe(true);
  const metrics = [];
  for (const [i, page] of pages.entries()) {
    await page.screenshot({ path: join(directory, `consumer-${i}.png`), fullPage: true });
    const pending = page.waitForEvent('download');
    await page.getByRole('button', { name: 'Download metrics JSON' }).click();
    await (await pending).saveAs(join(directory, `latency-${i}.json`));
    metrics.push(JSON.parse(await readFile(join(directory, `latency-${i}.json`), 'utf8')));
    expect(errors[i]).toEqual([]);
    expect(requests[i].every(r => !r.hasAuthorization)).toBe(true);
  }
  expect(metrics[0].counters.snapshot).toBe(0);
  expect(metrics[0].counters.disconnects).toBe(0);
  expect(metrics[1].counters.reset_applied).toBeGreaterThanOrEqual(1);
  expect(metrics[1].counters.reset_skipped_cursors).toBeGreaterThan(8);
  expect(metrics[1].counters.invalid).toBe(0);
  await save('convergence-browser', { passed: true, scope: 'two-local-chromium-processes-real-medusa-sse',
    short_resume_cursor: short.cursor, long_resume_cursor: long.cursor, final, requests, errors,
    counters: metrics.map(m => m.counters), limits: ['same host and engine', 'offline plus explicit reconnect abort', 'retention is deliberately 8', 'no model execution'] });
} catch (error) {
  await save('convergence-error', { message: String(error), requests, errors }); throw error;
} finally { for (const b of browsers.reverse()) await b.close(); }
