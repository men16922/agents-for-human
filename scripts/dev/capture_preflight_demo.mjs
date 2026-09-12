/** A real visible Chrome preflight; one paid admission, no API mocks or commerce writes. */
import { chromium } from '@playwright/test';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
const directory=process.argv[2];
if(!directory?.startsWith('.local/'))throw Error('Use a fresh ignored capture directory');
await mkdir(directory,{recursive:false});
const outputs=JSON.parse(await readFile('.local/serverless-deploy/outputs.json','utf8'));
const browser=await chromium.launch({channel:'chrome',headless:false,args:['--window-size=1660,1100']});
const context=await browser.newContext({viewport:{width:1600,height:1000},recordVideo:{dir:directory,size:{width:1600,height:1000}}});
const page=await context.newPage();const started=Date.now(),marks=[],snapshots=[],errors=[];
const mark=(name,extra={})=>{const m={name,seconds:(Date.now()-started)/1000,...extra};marks.push(m);console.log(JSON.stringify(m));};
page.on('pageerror',e=>errors.push(e.message));
page.on('response',async r=>{if(/\/api\/preflights\/preview-[^/]+$/.test(r.url())&&r.status()===200){try{snapshots.push({seconds:(Date.now()-started)/1000,body:await r.json()});}catch{}}});
await page.goto(outputs.Url,{waitUntil:'networkidle'});
await page.getByRole('heading',{name:'See the impact. Then decide.'}).waitFor();
await page.evaluate(()=>{const c=document.createElement('div');c.style.cssText='position:fixed;width:22px;height:22px;border:2px solid #b78c30;border-radius:50%;background:#f5cc6638;pointer-events:none;z-index:99999;left:-40px;top:-40px;transform:translate(-50%,-50%)';document.body.append(c);addEventListener('mousemove',e=>{c.style.left=e.clientX+'px';c.style.top=e.clientY+'px'});});
async function point(l){await l.scrollIntoViewIfNeeded();const b=await l.boundingBox();if(!b)throw Error('Missing target');await page.mouse.move(b.x+b.width/2,b.y+b.height/2,{steps:22});}
async function shot(name,fullPage=false){await page.screenshot({path:join(directory,name+'.png'),fullPage});}
async function scroll(l){await l.evaluate(e=>e.scrollIntoView({block:'start',behavior:'smooth'}));await page.waitForTimeout(1200);}
mark('overview');await shot('overview');await page.waitForTimeout(6000);
await point(page.getByRole('button',{name:'Rehearse this request ↗'}));mark('start-click');await page.getByRole('button',{name:'Rehearse this request ↗'}).click();
await page.waitForURL(/preview=preview-/);const runId=new URL(page.url()).searchParams.get('preview');mark('run-created',{run_id:runId});await writeFile(join(directory,'run.json'),JSON.stringify({run_id:runId,url:page.url()},null,2));
await scroll(page.locator('.pf-progress'));mark('planning');let final,phase;
for(let i=0;i<360;i++){await page.waitForTimeout(1000);final=snapshots.at(-1)?.body;if(final?.phase!==phase){phase=final?.phase;mark('phase-'+phase);await shot('phase-'+phase);}if(final?.finalized)break;}
if(!final?.finalized||final.report?.status!=='REPORT_READY')throw Error('Report not ready; inspect this admitted run, do not automatically retry');
mark('report-ready');await scroll(page.locator('.pf-report-head'));await shot('result');await page.waitForTimeout(12000);
await scroll(page.locator('.pf-matrix'));mark('matrix');await shot('matrix');await page.waitForTimeout(7000);
await point(page.getByRole('button',{name:'A: A loses tent stock',exact:true}));await page.getByRole('button',{name:'A: A loses tent stock',exact:true}).click();await scroll(page.locator('.pf-detail'));mark('stock-detail');await shot('stock-detail');await page.waitForTimeout(8000);
await point(page.getByRole('button',{name:'B: Payment reply lost',exact:true}));await page.getByRole('button',{name:'B: Payment reply lost',exact:true}).click();await scroll(page.locator('.pf-detail'));mark('payment-detail');await shot('payment-detail');await page.waitForTimeout(11000);
await scroll(page.locator('.pf-decision'));mark('before-decision');await shot('decision-before');await page.waitForTimeout(7000);
await point(page.getByRole('button',{name:'Accept plan B & export brief',exact:true}));await page.getByRole('button',{name:'Accept plan B & export brief',exact:true}).click();await page.getByRole('heading',{name:'Execution brief recorded.'}).waitFor();mark('accepted');await shot('decision-after');await page.waitForTimeout(7000);
const d=page.waitForEvent('download');await page.getByRole('button',{name:'Download decision brief ↓'}).click();await(await d).saveAs(join(directory,'decision-brief.json'));
const e=page.waitForEvent('download');await page.getByRole('button',{name:'Download report, journals & tool trace ↓'}).click();await(await e).saveAs(join(directory,'impact-evidence.json'));mark('evidence-downloaded');
await page.reload({waitUntil:'networkidle'});await page.getByRole('heading',{name:'Execution brief recorded.'}).waitFor();await scroll(page.locator('.pf-decision'));mark('recovered');await page.waitForTimeout(6000);await shot('recovered');const recovered=snapshots.at(-1)?.body;
await page.getByText('What this evidence does—and does not—show',{exact:true}).click();await scroll(page.locator('.pf-evidence'));mark('limitations');await shot('limitations');await page.waitForTimeout(8000);
await writeFile(join(directory,'browser-report.json'),JSON.stringify({browser:'Google Chrome',headless:false,viewport:{width:1600,height:1000},url:page.url(),run_id:runId,marks,snapshots,final,recovered,errors,passed:errors.length===0&&final.finalized&&recovered?.decision?.decision==='ACCEPTED_FOR_EXECUTION_REVIEW'},null,2));
const video=page.video();await context.close();await video.saveAs(join(directory,'chrome-demo.webm'));await browser.close();console.log('Capture complete: '+directory);
