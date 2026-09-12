/** Record real UI interactions in visible, installed Google Chrome. No API mocks. */
import { chromium } from '@playwright/test';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
const directory = process.argv[2];
if (!directory?.startsWith('.local/')) throw Error('Use a new ignored capture directory');
await mkdir(directory, {recursive:false});
const outputs=JSON.parse(await readFile('.local/serverless-deploy/outputs.json','utf8'));
const browser=await chromium.launch({channel:'chrome', headless:false, args:['--window-size=1660,1100']});
const context=await browser.newContext({viewport:{width:1600,height:1000},deviceScaleFactor:1,recordVideo:{dir:directory,size:{width:1600,height:1000}}});
const page=await context.newPage();const started=Date.now();const marks=[],snapshots=[],errors=[];
const mark=(name,extra={})=>{const record={name,seconds:(Date.now()-started)/1000,...extra};marks.push(record);console.log(JSON.stringify(record));};
page.on('pageerror',e=>errors.push(e.message));
page.on('response',async r=>{if(r.url().includes('/api/experiments/')&&r.status()===200){try{snapshots.push({seconds:(Date.now()-started)/1000,body:await r.json()});}catch{}}});
await page.goto(outputs.Url,{waitUntil:'networkidle'});
// A visible cursor is a recording annotation only; application state/data are untouched.
await page.evaluate(()=>{const cursor=document.createElement('div');cursor.id='recording-cursor';cursor.style.cssText='position:fixed;width:22px;height:22px;border:2px solid #b78c30;border-radius:50%;background:#f5cc6638;pointer-events:none;z-index:99999;left:-40px;top:-40px;transform:translate(-50%,-50%)';document.body.append(cursor);addEventListener('mousemove',e=>{cursor.style.left=e.clientX+'px';cursor.style.top=e.clientY+'px'});addEventListener('mousedown',()=>{cursor.style.background='#f5cc66bb'});addEventListener('mouseup',()=>{cursor.style.background='#f5cc6638'});});
async function point(locator){const b=await locator.boundingBox();if(!b)throw Error('Missing visible target');await page.mouse.move(b.x+b.width/2,b.y+b.height/2,{steps:22});}
mark('overview');await page.screenshot({path:join(directory,'overview.png')});await page.waitForTimeout(3500);
for(const method of ['B0','B1','B2','B3']){const button=page.getByRole('button',{name:new RegExp('^'+method)});await point(button);await button.click();mark('select-'+method);await page.waitForTimeout(2300);}
await point(page.getByLabel('Live condition'));await page.getByLabel('Live condition').selectOption('stock-change');mark('condition-selected');await page.waitForTimeout(3500);
await point(page.getByRole('button',{name:'Run experiment →'}));mark('start-click');await page.getByRole('button',{name:'Run experiment →'}).click();await page.waitForURL(/run=rehearsal-/);const runId=new URL(page.url()).searchParams.get('run');mark('run-created',{run_id:runId});await writeFile(join(directory,'run.json'),JSON.stringify({run_id:runId,url:page.url(),method:'B3',scenario:'stock-change'},null,2));
await page.waitForTimeout(2500);await page.locator('.cloud-runbar').evaluate(e=>e.scrollIntoView({block:'start',behavior:'smooth'}));await page.mouse.move(25,450,{steps:20});mark('live-world');
let final,phase;
for(let i=0;i<430;i++){await page.waitForTimeout(1000);final=snapshots.at(-1)?.body;const next=final?.runtime?.phase;if(next!==phase){phase=next;mark('phase-'+next);await page.screenshot({path:join(directory,'phase-'+next+'.png')});}if(final?.finalized)break;}
if(!final?.finalized)throw Error('Run did not finalize within capture bound; do not automatically retry');
mark('finalized',{status:final.verification?.verdict?.status});await page.screenshot({path:join(directory,'result.png'),fullPage:true});await page.waitForTimeout(10000);
await point(page.locator('.cloud-verdict'));mark('inspect-verdict');await page.waitForTimeout(5000);
await page.locator('.cloud-bottom').evaluate(e=>e.scrollIntoView({block:'end',behavior:'smooth'}));mark('inspect-timeline');await page.waitForTimeout(12000);
mark('reload');await page.reload({waitUntil:'networkidle'});await page.waitForTimeout(2500);await page.locator('.cloud-runbar').evaluate(e=>e.scrollIntoView({block:'start',behavior:'smooth'}));await page.waitForTimeout(7000);mark('recovered');const recovered=snapshots.at(-1)?.body;await page.screenshot({path:join(directory,'recovered.png')});
await writeFile(join(directory,'browser-report.json'),JSON.stringify({browser:'Google Chrome',headless:false,viewport:{width:1600,height:1000},url:page.url(),run_id:runId,marks,snapshots,final,recovered,errors,passed:errors.length===0&&final.finalized&&recovered?.run_id===runId},null,2));
const video=page.video();await context.close();await video.saveAs(join(directory,'chrome-demo.webm'));await browser.close();console.log('Capture complete: '+directory);
