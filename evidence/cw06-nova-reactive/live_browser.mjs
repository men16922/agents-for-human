import { chromium, expect } from '@playwright/test';
import {writeFile,access} from 'node:fs/promises';
import {join} from 'node:path';
const dir=process.argv[2];const save=(name,value)=>writeFile(join(dir,name+'.json'),JSON.stringify(value,null,2)+'\n');
const browser=await chromium.launch({headless:true});const ctx=await browser.newContext({viewport:{width:1600,height:1000},recordVideo:{dir:join(dir,'raw-video'),size:{width:1600,height:1000}}});const page=await ctx.newPage();const errors=[],requests=[],states=[];const start=Date.now()/1000;
page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(r.url().includes('/api/'))requests.push({url:r.url(),method:r.method(),auth:'authorization' in r.headers()});});
page.on('response',async r=>{if(r.url().endsWith('/api/observer/execution'))try{states.push({at:Date.now()/1000,value:await r.json()});}catch{}});
try{
 await page.goto('http://127.0.0.1:15173');await expect(page.getByTestId('connection')).toHaveText('실시간 연결',{timeout:20000});await page.screenshot({path:join(dir,'initial.png')});await save('initial',{at:Date.now()/1000,stock:await page.getByTestId('stock-A-tent').innerText()});
 await expect.poll(async()=>{try{await access(join(dir,'finished.json'));return true;}catch{return false;}},{timeout:150000}).toBe(true);
 await expect(page.getByRole('region',{name:'실행자 반응 기록'}).getByText('종료 기록 · 파일 무결성 확인')).toBeVisible({timeout:15000});
 await page.getByRole('button',{name:'증거 다시 검증'}).click();await expect.poll(async()=>{const r=await(await page.request.get('http://127.0.0.1:15173/api/observer/evidence')).json();return r.status;},{timeout:15000}).toBe('VERIFIED');
 const execution=await(await page.request.get('http://127.0.0.1:15173/api/observer/execution')).json();const evidence=await(await page.request.get('http://127.0.0.1:15173/api/observer/evidence')).json();
 expect(execution.status).toBe('SEALED');expect(['COMPLETE','INCOMPLETE']).toContain(evidence.verdict.status);expect(evidence.run_id).toBe(execution.run_id);expect(requests.every(r=>r.method==='GET'&&!r.auth)).toBe(true);expect(errors).toEqual([]);expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await page.getByRole('region',{name:'독립 증빙'}).scrollIntoViewIfNeeded();await page.screenshot({path:join(dir,'final.png')});await save('browser-report',{passed:true,scope:'actual-nova-medusa-ui',execution,evidence,states,requests,errors});await page.waitForTimeout(3000);
}catch(e){await save('browser-error',{message:String(e),errors,states});throw e;}finally{await ctx.close();await page.video().saveAs(join(dir,'nova-live.webm'));await save('video-record',{scope:'continuous-actual-nova-medusa-browser-capture',started_at:start,finished_at:Date.now()/1000,video:'nova-live.webm'});await browser.close();}
