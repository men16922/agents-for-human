import { test, expect } from '@playwright/test';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

const proposal = pathToFileURL(resolve('agents-for-human-propsal.html')).href;

test('proposal is offline, responsive, and keeps uncertain payment separate from delivery', async ({ page }) => {
  const errors: string[] = [];
  const external: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.route(/^https?:/, route => { external.push(route.request().url()); return route.abort(); });
  await page.goto(proposal);
  for (const width of [1440, 390, 320]) {
    await page.setViewportSize({ width, height: 900 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  }
  for (const img of await page.locator('img').all()) {
    await img.scrollIntoViewIfNeeded();
    await expect.poll(() => img.evaluate((node: HTMLImageElement) => node.complete && node.naturalWidth > 0)).toBe(true);
  }
  await page.locator('[data-step="2"]').click();
  await expect(page.locator('#payment-state')).toContainText('미확정');
  await expect(page.locator('#received')).toHaveText('0 / 9');
  await expect(page.locator('#balance')).toHaveText('120');
  await page.locator('[data-step="3"]').click();
  await expect(page.locator('#received')).toHaveText('9 / 9');
  await expect(page.locator('#scene-description')).toContainText('합성 예시');
  await page.locator('[data-step="0"]').click();
  await expect(page.locator('#balance')).toHaveText('500');
  await expect(page.locator('#received')).toHaveText('0 / 9');
  expect(errors).toEqual([]);
  expect(external).toEqual([]);
});

test('automatic scenes stop at the last frame and restart without duplicated timers', async ({ page }) => {
  await page.clock.install();
  await page.goto(proposal);
  await page.locator('#play-button').click();
  await page.clock.fastForward(5000);
  await expect(page.locator('[data-step="1"]')).toHaveAttribute('aria-pressed', 'true');
  await page.clock.fastForward(5000);
  await page.clock.fastForward(5000);
  await expect(page.locator('#play-button')).toHaveAttribute('aria-pressed', 'false');
  await expect(page.locator('[data-step="3"]')).toHaveAttribute('aria-pressed', 'true');
  await page.locator('#play-button').click();
  await expect(page.locator('[data-step="0"]')).toHaveAttribute('aria-pressed', 'true');
  await page.locator('[data-step="2"]').click();
  await page.clock.fastForward(20_000);
  await expect(page.locator('[data-step="2"]')).toHaveAttribute('aria-pressed', 'true');
  await expect(page.locator('#play-button')).toHaveAttribute('aria-pressed', 'false');
});

test('React shell confirms the actual local API and reports connection failure honestly', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('status')).toHaveText('Local API connected');
  await page.route('**/api/health', route => route.abort());
  await page.reload();
  await expect(page.getByRole('status')).toHaveText('Cannot connect to the local API.');
});
