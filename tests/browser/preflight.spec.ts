import { test, expect } from '@playwright/test';
import fixture from './fixtures/preflight.json';

test('impact report shows full denominator, recovery evidence and explicit decision; reload persists', async ({ page }) => {
  const report = { ...fixture, expires_at: Date.now() / 1000 + 900 };
  let decisions = 0; let brief: object | null = null;
  await page.route('**/api/preflights/**', async route => {
    if (route.request().method() === 'POST') {
      const body = route.request().postDataJSON();
      expect(body.action).toBe('accept');
      expect(body.plan_sha256).toBe(report.plans[1].plan.plan_sha256);
      expect(body.report_sha256).toBe(report.report_sha256);
      decisions++; brief = { decision: 'ACCEPTED_FOR_EXECUTION_REVIEW', external_orders_created: 0, brief_sha256: 'fixture' };
      return route.fulfill({ json: brief });
    }
    return route.fulfill({ json: { run_id: 'preview-browser', finalized: true, phase: 'FINISHED', status: 'REPORT_READY', report, decision: brief, usage: { model_calls: 4, recorded_micro_usd: 112 } } });
  });
  await page.goto('/?preflight=1&preview=preview-browser');
  await expect(page.getByRole('heading', { name: 'Supplier B meets the tested conditions.' })).toBeVisible();
  await expect(page.getByText('12 OF 12 RUNS VERIFIED', { exact: false })).toBeVisible();
  expect(decisions).toBe(0);
  await page.getByRole('button', { name: 'B: Payment reply lost', exact: true }).click();
  await expect(page.getByText('It did not create a second payment.', { exact: false })).toBeVisible();
  await page.getByRole('button', { name: 'Accept plan B & export brief', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Execution brief recorded.' })).toBeVisible();
  expect(decisions).toBe(1);
  await page.reload();
  await expect(page.getByRole('button', { name: 'Download decision brief ↓' })).toBeVisible();
  expect(decisions).toBe(1);
});

test('expired evidence cannot be accepted and mobile page has no overflow', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.route('**/api/preflights/**', route => route.fulfill({ json: {
    run_id: 'preview-browser', finalized: true, report: fixture, status: 'REPORT_READY', phase: 'FINISHED', usage: { model_calls: 4, recorded_micro_usd: 112 },
  } }));
  await page.goto('/?preflight=1&preview=preview-browser');
  await expect(page.getByRole('heading', { name: 'This report has expired.' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Accept plan B & export brief' })).toBeDisabled();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  await page.getByRole('button', { name: 'B: Payment reply lost', exact: true }).focus();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('region', { name: 'Selected simulation evidence' })).toBeVisible();
});

test('failed start retries the same admission request without changing shopper authority', async ({ page }) => {
  const ids: string[] = [];
  await page.route('**/api/preflights', async route => {
    const body = route.request().postDataJSON(); ids.push(body.request_id);
    expect(Object.keys(body).sort()).toEqual(['request_id', 'scenario']);
    if (ids.length === 1) return route.abort();
    return route.fulfill({ json: { run_id: 'preview-pending' }, status: 202 });
  });
  await page.route('**/api/preflights/preview-pending', route => route.fulfill({ json: {
    run_id: 'preview-pending', finalized: false, phase: 'PLANNING_AND_SIMULATING', status: 'RUNNING', usage: { model_calls: 1, recorded_micro_usd: 28 },
  } }));
  await page.goto('/?preflight=1');
  await page.getByRole('button', { name: 'Rehearse this request ↗' }).click();
  await expect(page.getByRole('alert')).toBeVisible();
  await page.getByRole('button', { name: 'Rehearse this request ↗' }).click();
  await expect(page.getByRole('heading', { name: 'Nova is planning and rehearsing' })).toBeVisible();
  expect(ids).toHaveLength(2); expect(ids[0]).toBe(ids[1]);
  await expect(page.getByRole('button', { name: 'Rehearsal in progress…' })).toBeDisabled();
});
