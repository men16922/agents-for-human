/** Measure actual DOM transitions in the live observer. No intercepted responses. */
import { chromium, expect } from '@playwright/test';
import { readFile, writeFile, rename } from 'node:fs/promises';
import { join } from 'node:path';

const directory = process.argv[2];
const plan = JSON.parse(await readFile(join(directory, 'plan.json'), 'utf8'));
const save = async (name, value) => {
  const path = join(directory, `${name}.json`);
  await writeFile(path + '.tmp', JSON.stringify(value, null, 2) + '\n');
  await rename(path + '.tmp', path);
};
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 1050 } });
const errors = [], requests = [], rows = [];
page.on('pageerror', error => errors.push(error.message));
page.on('request', request => {
  if (request.url().includes('/api/')) requests.push({ url: request.url(), method: request.method(), hasAuthorization: 'authorization' in request.headers() });
});
try {
  await page.goto('http://127.0.0.1:15173');
  await expect(page.getByTestId('connection')).toHaveText('Live connection', { timeout: 20_000 });
  await expect(page.getByTestId('stock-A-tent')).toHaveText('10');
  await page.getByTestId('stock-A-tent').scrollIntoViewIfNeeded();
  for (const trial of plan.trials) {
    // The probe is armed before the driver may issue the real stock mutation.
    await page.evaluate(({ id, quantity }) => {
      const read = () => ({ stock: document.querySelector('[data-testid="stock-A-tent"]').textContent,
        cursor: Number(document.querySelector('[data-testid="cursor"]').textContent),
        version: Number(document.querySelector('.revision').textContent.match(/^v(\d+)/)[1]),
        wall_ms: Date.now(), mono_ms: performance.now(), visible: !document.hidden });
      const probe = { id, quantity, armed: read(), first: null, painted: null, done: false };
      window.__stockLatency = probe;
      const observer = new MutationObserver(() => {
        const current = read();
        if (current.stock.trim() !== String(quantity) || probe.first) return;
        probe.first = current;
        observer.disconnect();
        requestAnimationFrame(() => requestAnimationFrame(() => { probe.painted = read(); probe.done = true; }));
      });
      observer.observe(document.querySelector('main'), { subtree: true, childList: true, characterData: true });
      window.__stopStockLatency = () => observer.disconnect();
    }, trial);
    await save(`armed-${trial.id}`, await page.evaluate(() => window.__stockLatency.armed));
    let status = 'RENDERED';
    try { await page.waitForFunction(() => window.__stockLatency.done, undefined, { timeout: 8000 }); }
    catch { status = 'TIMEOUT'; }
    const probe = await page.evaluate(() => { window.__stopStockLatency(); return window.__stockLatency; });
    const row = { ...probe, status };
    rows.push(row);
    await save(`render-${trial.id}`, row);
  }
  await page.screenshot({ path: join(directory, 'final.png'), fullPage: true });
  const downloadPromise = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Download metrics JSON' }).click();
  await (await downloadPromise).saveAs(join(directory, 'latency.json'));
  expect(errors).toEqual([]);
  expect(requests.every(r => r.method === 'GET' && !r.hasAuthorization)).toBe(true);
  await save('browser-report', { passed: true, rows, requests, errors });
} catch (error) {
  await save('browser-error', { message: String(error), rows, requests, errors });
  throw error;
} finally { await browser.close(); }
