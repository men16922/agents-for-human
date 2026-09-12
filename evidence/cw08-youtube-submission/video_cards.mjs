/** Render editorial cards from a local, evidence-derived storyboard. No product simulation. */
import { chromium } from '@playwright/test';
import { readFile, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
const directory = process.argv[2];
const story = JSON.parse(await readFile(join(directory, 'storyboard.json'), 'utf8'));
const esc = value => String(value).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;');
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
const checks = [];
try {
  for (const [index, scene] of story.scenes.entries()) {
    const shot = scene.image ? `data:image/png;base64,${(await readFile(scene.image)).toString('base64')}` : null;
    const body = scene.table ? `<table><thead><tr>${scene.table[0].map(v => `<th>${esc(v)}</th>`).join('')}</tr></thead><tbody>${scene.table.slice(1).map(row => `<tr>${row.map(v => `<td>${esc(v)}</td>`).join('')}</tr>`).join('')}</tbody></table>` : `<div class="facts">${scene.facts.map(([label, value]) => `<article><small>${esc(label)}</small><strong>${esc(value)}</strong></article>`).join('')}</div>`;
    await page.setContent(`<!doctype html><html lang="en"><meta charset="utf-8"><style>
      *{box-sizing:border-box}body{margin:0;width:1920px;height:1080px;background:#101c2c;color:#f2f6ec;font-family:Arial,sans-serif;padding:68px 88px}
      header{color:#d9fca6;font-size:23px;letter-spacing:3px;text-transform:uppercase;display:flex;justify-content:space-between}
      h1{font-size:66px;line-height:1.12;max-width:1670px;margin:46px 0 24px}p{font-size:31px;line-height:1.5;max-width:1580px;color:#d1daca;margin:0 0 40px}
      .facts{display:flex;gap:24px}article{background:#1c2c40;border:1px solid #3c5164;border-radius:16px;padding:36px;flex:1;min-height:230px}small{display:block;font-size:24px;color:#b4c8ac;margin-bottom:24px}strong{display:block;font-size:43px;line-height:1.3;overflow-wrap:anywhere}
      footer{position:absolute;left:88px;right:88px;bottom:42px;font-size:23px;line-height:1.5;color:#b4c2ca;border-top:1px solid #405269;padding-top:20px}.note{font-size:28px;color:#d9fca6;margin-top:28px}.shot{width:1080px;height:608px;object-fit:contain;float:right;margin-left:35px}.with-shot .facts{display:block;width:530px}.with-shot article{min-height:130px;margin-bottom:14px;padding:22px}.with-shot strong{font-size:34px}.with-shot small{margin-bottom:8px;font-size:22px}
      table{border-collapse:collapse;width:100%;font-size:31px;margin-top:24px}th,td{text-align:left;padding:20px 26px;border-bottom:1px solid #465a70}th{color:#d9fca6;font-size:25px}
      .live{padding:0}.live header{height:120px;padding:22px 52px;display:block;letter-spacing:0;font-size:38px;text-transform:none;background:#101c2c}.live header small{font-size:23px;margin:10px 0 0}.live footer{bottom:8px;padding-top:10px;font-size:22px;left:52px;right:52px}
      </style><body class="${scene.live ? 'live' : ''}">${scene.live ? `<header>${esc(scene.title)}<small>${esc(scene.liveLabel ?? 'RECORDED LOCAL RUN · SCRIPTED SDK BUYER · SYNTHETIC CREDITS · ORIGINAL SPEED')}</small></header><footer>${esc(scene.source)}</footer>` : `<header><span>rehearsal / ${esc(scene.tag)}</span><span>${esc(story.edition ?? "Local draft")} · ${index + 1} / ${story.scenes.length}</span></header><h1>${esc(scene.title)}</h1><p>${esc(scene.subtitle)}</p><section class="${shot ? 'with-shot' : ''}">${shot ? `<img class="shot" src="${shot}" alt="Actual initial browser frame">` : ''}${body}</section><div class="note">${esc(scene.note)}</div><footer>${esc(scene.source)}</footer>`}</body></html>`);
    await page.evaluate(() => document.fonts.ready);
    const bounds = await page.evaluate(() => ({ width: document.documentElement.scrollWidth, height: document.documentElement.scrollHeight }));
    if (bounds.width !== 1920 || bounds.height !== 1080) throw Error(`Card ${index} overflows: ${JSON.stringify(bounds)}`);
    await page.screenshot({ path: join(directory, `card-${index}.png`) });
    if (scene.live) {
      await page.locator('header').evaluate(node => { node.textContent = 'CAPTURE FINISHED — final frame held for explanation'; });
      await page.screenshot({ path: join(directory, 'hold-label.png'), clip: { x: 0, y: 0, width: 1920, height: 120 } });
    }
    checks.push({ index, ...bounds });
  }
  await writeFile(join(directory, 'card-checks.json'), JSON.stringify(checks, null, 2) + '\n');
} finally { await browser.close(); }
