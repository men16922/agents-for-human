import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests/browser',
  timeout: 30_000,
  workers: 1,
  use: { browserName: 'chromium', headless: true, baseURL: 'http://127.0.0.1:15173' },
  reporter: 'list',
  webServer: [
    { command: 'scripts/dev/with-env.sh uv run --offline --no-sync uvicorn rehearsal.api:app --host 127.0.0.1 --port 18000', url: 'http://127.0.0.1:18000/health', reuseExistingServer: false },
    { command: 'scripts/dev/with-env.sh npm run dev:web', url: 'http://127.0.0.1:15173', reuseExistingServer: false },
  ],
});
