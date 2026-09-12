import { test, expect } from '@playwright/test';

test('React shell confirms the actual local API and reports connection failure honestly', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('status')).toHaveText('Local API connected');
  await page.route('**/api/health', route => route.abort());
  await page.reload();
  await expect(page.getByRole('status')).toHaveText('Cannot connect to the local API.');
});
