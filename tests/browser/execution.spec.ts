import { test, expect } from '@playwright/test';
import { spawn, type ChildProcess } from 'node:child_process';
import { createHash } from 'node:crypto';
import { cpSync, mkdirSync, readFileSync, writeFileSync, rmSync } from 'node:fs';
import { resolve } from 'node:path';
import { createServer } from 'node:net';
import { parseExecution } from '../../web/src/Execution';

const retained = resolve('tests/fixtures/executions/changed-B1-r1/execution');
const root = resolve('.local/cw06-execution-browser');
const dir = `${root}/execution`;
const spec = JSON.parse(readFileSync(`${retained}/spec.json`, 'utf8'));
const run = spec.run_id;
const rows = readFileSync(`${retained}/observations.jsonl`, 'utf8').trim().split('\n').map(line => JSON.parse(line));
const snapshot = rows.filter(row => row.kind === 'decision_basis').at(-1).value.snapshot;
let child: ChildProcess | undefined;
let startupError = '';
const hash = (file: string) => createHash('sha256').update(readFileSync(file)).digest('hex');

test.beforeAll(async ({ request }) => {
  // Refuse to reuse another listener; this server only reads a disposable record copy.
  const probe = createServer();
  await new Promise<void>((ok, fail) => { probe.once('error', fail); probe.listen(18002, '127.0.0.1', ok); });
  await new Promise<void>((ok, fail) => probe.close(error => error ? fail(error) : ok()));
  mkdirSync(root, { recursive: true });
  writeFileSync(`${root}/observer.json`, JSON.stringify({ run_id: run, observer_token: 'browser-fixture-token-only' }), { mode: 0o600 });
  writeFileSync(`${root}/selection.json`, JSON.stringify({ run_id: run, expected_goal: spec.expected_goal, expected_budget: spec.expected_budget, execution_path: 'execution', spec_sha256: hash(`${retained}/spec.json`) }));
  child = spawn('scripts/dev/with-env.sh', ['uv', 'run', '--offline', '--no-sync', 'uvicorn', 'rehearsal.api:app', '--host', '127.0.0.1', '--port', '18002'], {
    env: { ...process.env, REHEARSAL_OBSERVER_CONFIG: `${root}/observer.json`, REHEARSAL_EXECUTION_CONFIG: `${root}/selection.json`, REHEARSAL_EVIDENCE_CONFIG: '' },
    stdio: ['ignore', 'ignore', 'pipe'],
  });
  child.stderr?.on('data', data => { startupError += data.toString(); });
  await expect.poll(async () => {
    if (child?.exitCode !== null) throw Error(startupError);
    try { return (await request.get('http://127.0.0.1:18002/observer/config')).json(); } catch { return null; }
  }).toMatchObject({ run_id: run, read_only: true });
});
test.afterAll(async () => {
  if (child && child.exitCode === null) {
    const exited = new Promise<void>(ok => child!.once('exit', () => ok()));
    child.kill('SIGTERM');
    await exited;
  }
});
test.beforeEach(async ({ page }) => {
  rmSync(dir, { recursive: true, force: true });
  cpSync(retained, dir, { recursive: true });
  await page.route('**/api/observer/execution', async route => {
    const response = await route.fetch({ url: 'http://127.0.0.1:18002/observer/execution' });
    await route.fulfill({ response });
  });
  await page.route('**/api/observer/config', route => route.fulfill({ json: { configured: true, run_id: run, read_only: true, mode: 'live-observer' } }));
  await page.route('**/api/observer/events', route => route.fulfill({ contentType: 'text/event-stream', body:
    `id: 27\nevent: snapshot\ndata: ${JSON.stringify({ run_id: run, reset: true, next_cursor: 27, snapshot_event: { run_id: run, event_id: 'retained-final', version: 27, observed_at: rows.at(-1).at, event_type: 'state.observed', source: 'retained-sdk-medusa', snapshot } })}\n\n` }));
});

test('actual API replays retained Medusa reactions in desktop and narrow screens', async ({ page }) => {
  const errors: string[] = [], writes: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('request', request => { if (request.method() !== 'GET') writes.push(request.method()); });
  await page.goto('/');
  const panel = page.getByRole('region', { name: 'Executor reaction record' });
  await expect(panel.getByText('Sealed record · file integrity verified')).toBeVisible();
  await expect(panel.getByTestId('reaction-counts')).toHaveText('5 / 1');
  await expect(panel.getByText('Observation changed after decision')).toBeVisible();
  await expect(panel.getByText('tick 29', { exact: true })).toHaveCount(2);
  await expect(page.getByText('Awaiting independent ledger verification')).toBeVisible();
  for (const width of [1440, 390, 320]) {
    await page.setViewportSize({ width, height: 1000 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await panel.screenshot({ path: `${root}/reaction-${width}.png` });
  }
  expect(errors).toEqual([]); expect(writes).toEqual([]);
  expect(await panel.innerText()).not.toMatch(/browser-fixture-token|final_response|execution_path/);
});

test('unsealed records stay provisional and a later seal is detected by polling', async ({ page }) => {
  rmSync(`${dir}/execution-manifest.json`);
  const prefix = (kind: string) => rows.slice(0, rows.findIndex(row => row.kind === kind) + 1).map(row => JSON.stringify(row) + '\n').join('');
  writeFileSync(`${dir}/observations.jsonl`, prefix('decision_basis') + '{"kind":');
  await page.goto('/');
  const panel = page.getByTestId('execution-result');
  await expect(panel.getByText('Provisional record · completion unconfirmed')).toBeVisible();
  await expect(panel.getByText('The unfinished final line is excluded from the summary.')).toBeVisible();
  await expect(panel.getByText('This does not establish whether the execution is still running.', { exact: false })).toBeVisible();
  await expect(panel.getByTestId('reaction-counts')).toHaveText('0 / 0');
  writeFileSync(`${dir}/observations.jsonl`, prefix('effect_blocked') + '{"kind":');
  await expect(panel.getByTestId('reaction-counts')).toHaveText('0 / 1');
  await panel.screenshot({ path: `${root}/provisional.png` });
  cpSync(retained, dir, { recursive: true });
  await expect(panel.getByText('Sealed record · file integrity verified')).toBeVisible();
  await expect(panel.getByTestId('reaction-counts')).toHaveText('5 / 1');
});

test('tampering, run mismatch and failed refresh clear previous reaction counts', async ({ page }) => {
  await page.goto('/');
  const panel = page.getByTestId('execution-result');
  await expect(panel.getByTestId('reaction-counts')).toBeVisible();
  writeFileSync(`${dir}/report.json`, readFileSync(`${dir}/report.json`, 'utf8') + '\n');
  await expect(panel.getByText('Execution scope or record validation failed.')).toBeVisible();
  await expect(panel.getByTestId('reaction-counts')).toHaveCount(0);
  cpSync(retained, dir, { recursive: true });
  await page.route('**/api/observer/execution', async route => {
    const response = await route.fetch({ url: 'http://127.0.0.1:18002/observer/execution' });
    await route.fulfill({ json: { ...await response.json(), run_id: 'other' } });
  });
  await expect(panel.getByText('Cannot match this record to the observed run, goal and budget.')).toBeVisible();
  await page.route('**/api/observer/execution', route => route.fulfill({ status: 503, body: 'unavailable' }));
  await expect(panel.getByText('Cannot verify the execution record. Previous results are hidden.')).toBeVisible();
});

test('sealed limit stops show a reason without promoting transaction success', async ({ page }) => {
  const report = JSON.parse(readFileSync(`${dir}/report.json`, 'utf8'));
  report.runtime_status = 'LIMITED'; report.stop_reason = 'OBSERVATION_REPLAN_LIMIT';
  writeFileSync(`${dir}/report.json`, JSON.stringify(report));
  const seal = JSON.parse(readFileSync(`${dir}/execution-manifest.json`, 'utf8'));
  seal.report_sha256 = hash(`${dir}/report.json`);
  writeFileSync(`${dir}/execution-manifest.json`, JSON.stringify(seal));
  await page.goto('/');
  await expect(page.getByText('Stopped at a limit', { exact: true })).toBeVisible();
  await expect(page.getByText('Replanning limit reached', { exact: true })).toBeVisible();
  await expect(page.getByText('Awaiting independent ledger verification')).toBeVisible();
});

test('browser schema rejects success escalation and invalid counters', async ({ request }) => {
  const data = await (await request.get('http://127.0.0.1:18002/observer/execution')).json();
  expect(() => parseExecution(data)).not.toThrow();
  expect(() => parseExecution({ ...data, model_efficacy_verified: true })).toThrow();
  expect(() => parseExecution({ ...data, status: 'PROVISIONAL' })).toThrow();
  data.execution.audit.replans = true;
  expect(() => parseExecution(data)).toThrow();
});

test('a stalled refresh times out and removes the previous sealed summary', async ({ page }) => {
  await page.goto('/');
  const panel = page.getByTestId('execution-result');
  await expect(panel.getByTestId('reaction-counts')).toBeVisible();
  const pending: (() => void)[] = [];
  await page.route('**/api/observer/execution', async route => {
    await new Promise<void>(ok => pending.push(ok));
    await route.abort().catch(() => {});
  });
  try {
    await expect(panel.getByText('Cannot verify the execution record. Previous results are hidden.')).toBeVisible({ timeout: 10_000 });
    await expect(panel.getByTestId('reaction-counts')).toHaveCount(0);
  } finally { pending.forEach(release => release()); }
});
