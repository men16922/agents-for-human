/** Actual local API/SSE and a concurrently running SDK buyer. No route interception. */
import { chromium, expect } from '@playwright/test';
import { writeFile, access } from 'node:fs/promises';
import { join } from 'node:path';

const directory = process.argv[2];
const recording = process.env.REHEARSAL_RECORD_VIDEO === '1';
const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({ viewport: { width: recording ? 1600 : 1440, height: recording ? 900 : 1050 },
  ...(recording ? { recordVideo: { dir: join(directory, 'raw-video'), size: { width: 1600, height: 900 } } } : {}) });
const recordingStartedAt = Date.now() / 1000;
const page = await context.newPage();
const requests = [], errors = [], responses = [];
page.on('pageerror', error => errors.push(error.message));
page.on('request', request => {
  if (request.url().includes('/api/')) requests.push({ url: request.url(), method: request.method(), hasAuthorization: 'authorization' in request.headers() });
});
page.on('response', async response => {
  if (response.url().endsWith('/api/observer/execution')) {
    try { responses.push({ at: Date.now() / 1000, value: await response.json() }); } catch { /* captured by UI */ }
  }
});
const save = (name, value) => writeFile(join(directory, name + '.json'), JSON.stringify(value, null, 2) + '\n');
const state = async () => ({
  at: Date.now() / 1000,
  ...Object.fromEntries(await Promise.all(['connection', 'cursor', 'spent', 'reserved', 'inventory-tent', 'inventory-light'].map(async key => [key, await page.getByTestId(key).innerText()]))),
  execution: await page.getByTestId('execution-result').innerText(),
});
try {
  await page.goto('http://127.0.0.1:15173');
  await expect(page.getByTestId('connection')).toHaveText('Live connection', { timeout: 20_000 });
  await expect(page.getByTestId('stock-A-tent')).toHaveText('10');
  await expect(page.getByTestId('spent')).toHaveText('0credits');
  if (recording) await page.screenshot({ path: join(directory, 'initial-frame.png') });
  await save('initial', await state());
  const panel = page.getByRole('region', { name: 'Executor reaction record' });
  await expect(panel.getByText('Provisional record · completion unconfirmed')).toBeVisible({ timeout: 15_000 });
  await expect(panel.getByTestId('reaction-counts')).toHaveText('0 / 0');
  await save('provisional', await state());
  await expect(page.getByTestId('stock-A-tent')).toHaveText('0', { timeout: 20_000 });
  await save('stock-change', await state());
  await expect(panel.getByText('Observation changed after decision')).toBeVisible({ timeout: 20_000 });
  await expect(panel.getByText('Provisional record · completion unconfirmed')).toBeVisible();
  await panel.screenshot({ path: join(directory, 'live-blocked.png') });
  await save('blocked', await state());
  await expect(page.getByTestId('spent')).toHaveText('380credits', { timeout: 30_000 });
  await expect(page.getByTestId('inventory-tent')).toHaveText('3 / 3', { timeout: 25_000 });
  await expect(page.getByTestId('inventory-light')).toHaveText('6 / 6');
  await expect(page.getByTestId('reserved')).toHaveText('0credits');
  await expect(page.getByTestId('order-status')).toHaveText('Delivery confirmed');
  await expect(page.getByText('Awaiting independent ledger verification')).toBeVisible();
  await expect(panel.getByText('Sealed record · file integrity verified')).toBeVisible({ timeout: 15_000 });
  const execution = await (await page.request.get('http://127.0.0.1:15173/api/observer/execution')).json();
  expect(execution.status).toBe('SEALED');
  expect(execution.execution.audit.blocked_effects).toBe(1);
  expect(execution.transaction_verified).toBe(false);
  await save('ready-export', { ...await state(), summary: execution });
  await expect.poll(async () => { try { await access(join(directory, 'evidence-selection.json')); return true; } catch { return false; } }, { timeout: 20_000 }).toBe(true);
  await page.getByRole('button', { name: 'Reverify evidence' }).click();
  await expect(page.getByTestId('evidence-result')).toContainText('Goal complete at evidence capture');
  await expect(page.getByTestId('evidence-result')).toContainText('Matches the current observed values.', { timeout: 10_000 });
  const evidence = await (await page.request.get('http://127.0.0.1:15173/api/observer/evidence')).json();
  expect(evidence.status).toBe('VERIFIED');
  expect(evidence.verdict.status).toBe('COMPLETE');
  expect(evidence.verdict.spent).toBe(380);
  expect(evidence.run_id).toBe(execution.run_id);
  if (recording) await page.getByRole('region', { name: 'Independent evidence' }).scrollIntoViewIfNeeded();
  for (const width of recording ? [1600] : [1440, 390]) {
    if (!recording) await page.setViewportSize({ width, height: 1050 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: join(directory, `live-${width}.png`), fullPage: !recording });
  }
  expect(requests.every(r => r.method === 'GET' && !r.hasAuthorization)).toBe(true);
  expect(errors).toEqual([]);
  expect(responses.some(r => r.value.status === 'PROVISIONAL')).toBe(true);
  expect(responses.some(r => r.value.status === 'SEALED')).toBe(true);
  await save('browser-report', { passed: true, scope: 'live-sdk-medusa-sse-execution-and-independent-evidence', final: await state(), execution, evidence, requests, errors, responses });
  if (recording) await new Promise(resolve => setTimeout(resolve, 2000));
} catch (error) {
  await save('browser-error', { message: String(error), requests, errors, responses });
  throw error;
} finally {
  await context.close();
  if (recording) {
    await page.video().saveAs(join(directory, 'live-capture.webm'));
    await save('video-record', { scope: 'continuous-local-sdk-medusa-browser-capture', recorded: true,
      recording_started_at: recordingStartedAt, recording_finished_at: Date.now() / 1000,
      viewport: { width: 1600, height: 900 }, source: 'live-capture.webm', real_model_calls: 0 });
  }
  await browser.close();
}
