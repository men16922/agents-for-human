/** Actual local API/SSE and a concurrently running SDK buyer. No route interception. */
import { chromium, expect } from '@playwright/test';
import { writeFile, access } from 'node:fs/promises';
import { join } from 'node:path';

const directory = process.argv[2];
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 1050 } });
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
  await expect(page.getByTestId('connection')).toHaveText('실시간 연결', { timeout: 20_000 });
  await expect(page.getByTestId('stock-A-tent')).toHaveText('10');
  await expect(page.getByTestId('spent')).toHaveText('0크레딧');
  await save('initial', await state());
  const panel = page.getByRole('region', { name: '실행자 반응 기록' });
  await expect(panel.getByText('임시 기록 · 종료 미확인')).toBeVisible({ timeout: 15_000 });
  await expect(panel.getByTestId('reaction-counts')).toHaveText('0회 / 0회');
  await save('provisional', await state());
  await expect(page.getByTestId('stock-A-tent')).toHaveText('0', { timeout: 20_000 });
  await save('stock-change', await state());
  await expect(panel.getByText('판단 이후 관측 변경')).toBeVisible({ timeout: 20_000 });
  await expect(panel.getByText('임시 기록 · 종료 미확인')).toBeVisible();
  await panel.screenshot({ path: join(directory, 'live-blocked.png') });
  await save('blocked', await state());
  await expect(page.getByTestId('spent')).toHaveText('380크레딧', { timeout: 30_000 });
  await expect(page.getByTestId('inventory-tent')).toHaveText('3 / 3', { timeout: 25_000 });
  await expect(page.getByTestId('inventory-light')).toHaveText('6 / 6');
  await expect(page.getByTestId('reserved')).toHaveText('0크레딧');
  await expect(page.getByTestId('order-status')).toHaveText('납품 확인');
  await expect(page.getByText('독립 원장 검증 전')).toBeVisible();
  await expect(panel.getByText('종료 기록 · 파일 무결성 확인')).toBeVisible({ timeout: 15_000 });
  const execution = await (await page.request.get('http://127.0.0.1:15173/api/observer/execution')).json();
  expect(execution.status).toBe('SEALED');
  expect(execution.execution.audit.blocked_effects).toBe(1);
  expect(execution.transaction_verified).toBe(false);
  await save('ready-export', { ...await state(), summary: execution });
  await expect.poll(async () => { try { await access(join(directory, 'evidence-selection.json')); return true; } catch { return false; } }, { timeout: 20_000 }).toBe(true);
  await page.getByRole('button', { name: '증거 다시 검증' }).click();
  await expect(page.getByTestId('evidence-result')).toContainText('증거 시점 목표 완료');
  await expect(page.getByTestId('evidence-result')).toContainText('현재 관측 값과 일치합니다.', { timeout: 10_000 });
  const evidence = await (await page.request.get('http://127.0.0.1:15173/api/observer/evidence')).json();
  expect(evidence.status).toBe('VERIFIED');
  expect(evidence.verdict.status).toBe('COMPLETE');
  expect(evidence.verdict.spent).toBe(380);
  expect(evidence.run_id).toBe(execution.run_id);
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 1050 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: join(directory, `live-${width}.png`), fullPage: true });
  }
  expect(requests.every(r => r.method === 'GET' && !r.hasAuthorization)).toBe(true);
  expect(errors).toEqual([]);
  expect(responses.some(r => r.value.status === 'PROVISIONAL')).toBe(true);
  expect(responses.some(r => r.value.status === 'SEALED')).toBe(true);
  await save('browser-report', { passed: true, scope: 'live-sdk-medusa-sse-execution-and-independent-evidence', final: await state(), execution, evidence, requests, errors, responses });
} catch (error) {
  await save('browser-error', { message: String(error), requests, errors, responses });
  throw error;
} finally { await browser.close(); }
