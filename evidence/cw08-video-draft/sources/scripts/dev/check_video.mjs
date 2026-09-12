/** Local MP4 playback, seeking and sidecar-caption verification. */
import { chromium, expect } from '@playwright/test';
import { createServer } from 'node:http';
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { join } from 'node:path';
const directory = process.argv[2];
const video = await readFile(join(directory, 'rehearsal-draft.mp4'));
const captions = await readFile(join(directory, 'captions.vtt'));
const html = '<!doctype html><html lang="en"><meta charset="utf-8"><style>body{margin:24px;background:#101c2c;color:white;font:18px Arial}video{width:1056px;height:594px;display:block}p{margin:18px 0}</style><body><video muted controls preload="auto"><source src="/video" type="video/mp4"><track default kind="subtitles" src="/captions" srclang="en" label="English"></video><p>LOCAL DRAFT · Scripted SDK fixture + local Medusa · No real-model efficacy claim</p></body></html>';
const server = createServer((request, response) => {
  if (request.url === '/') { response.writeHead(200, { 'Content-Type': 'text/html' }); response.end(html); return; }
  if (request.url === '/captions') { response.writeHead(200, { 'Content-Type': 'text/vtt' }); response.end(captions); return; }
  if (request.url !== '/video') { response.writeHead(404); response.end(); return; }
  const range = /^bytes=(\d+)-(\d*)$/.exec(request.headers.range ?? '');
  const start = range ? Number(range[1]) : 0, end = range?.[2] ? Math.min(Number(range[2]), video.length - 1) : video.length - 1;
  response.writeHead(range ? 206 : 200, { 'Content-Type': 'video/mp4', 'Accept-Ranges': 'bytes',
    'Content-Length': end - start + 1, ...(range ? { 'Content-Range': `bytes ${start}-${end}/${video.length}` } : {}) });
  response.end(video.subarray(start, end + 1));
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 1104, height: 730 } });
  const errors = []; page.on('pageerror', error => errors.push(error.message));
  await page.goto(`http://127.0.0.1:${server.address().port}`);
  const metadata = await page.locator('video').evaluate(async v => {
    if (v.readyState < 1) await new Promise(resolve => v.addEventListener('loadedmetadata', resolve, { once: true }));
    await v.play();
    return { duration: v.duration, width: v.videoWidth, height: v.videoHeight };
  });
  expect(Math.abs(metadata.duration - 285)).toBeLessThan(.2);
  expect(metadata.width).toBe(1920); expect(metadata.height).toBe(1080);
  await expect.poll(() => page.locator('video').evaluate(v => v.currentTime)).toBeGreaterThan(.5);
  await page.locator('video').evaluate(v => v.pause());
  await expect.poll(() => page.locator('video').evaluate(v => v.textTracks[0]?.cues?.length ?? 0)).toBeGreaterThan(20);
  await mkdir(join(directory, 'qa'), { recursive: true });
  for (const second of [5, 35, 75, 123, 145, 185, 230, 273]) {
    await page.locator('video').evaluate(async (v, t) => {
      const seeked = new Promise(resolve => v.addEventListener('seeked', resolve, { once: true }));
      v.currentTime = t; await seeked;
    }, second);
    await page.screenshot({ path: join(directory, 'qa', `playback-${second}.png`) });
  }
  const track = await page.locator('video').evaluate(v => ({ cues: v.textTracks[0].cues.length, mode: v.textTracks[0].mode, error: v.error?.code ?? null }));
  expect(track.error).toBeNull(); expect(errors).toEqual([]);
  await writeFile(join(directory, 'playback-check.json'), JSON.stringify({ passed: true, metadata, track, errors, seeks: [5, 35, 75, 123, 145, 185, 230, 273] }, null, 2) + '\n');
  console.log('PASS: Chromium playback, eight seeks and English captions');
} finally { await browser.close(); await new Promise(resolve => server.close(resolve)); }
