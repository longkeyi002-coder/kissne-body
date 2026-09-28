/* Offline browser behavior test. PLAYWRIGHT_MODULE and CHROMIUM_EXECUTABLE point to local dependencies. */
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright-core');
(async () => {
  const browser = await chromium.launch({executablePath:process.env.CHROMIUM_EXECUTABLE, headless:true, args:['--no-sandbox','--disable-gpu']});
  try {
    const page = await browser.newPage();
    const base = path.resolve(__dirname,'..');
    const errors=[];
    page.on('pageerror',e=>errors.push(e.message));
    await page.route('**/*',async route=>{
      const url=new URL(route.request().url());
      if(url.origin!=='http://kissne.test') return route.abort();
      if(url.pathname==='/') return route.fulfill({contentType:'text/html; charset=utf-8',body:'<html><head><meta charset="utf-8"></head><body><main id="test"></main></body></html>'});
      const file=path.resolve(base,'.'+url.pathname);
      if(!file.startsWith(base+path.sep)) return route.abort();
      try {await route.fulfill({body:await fs.readFile(file),contentType:'application/javascript; charset=utf-8'});}
      catch {await route.fulfill({status:404});}
    });
    await page.goto('http://kissne.test/');
    for(const file of ['core.js','assets/_manifest.js','assets/icons/sprite-data.js','assets.js','transport.js','chat-activity.js','screens-a.js'])
      await page.addScriptTag({url:'http://kissne.test/'+file});
    await page.evaluate(()=>{
      window.switchMode='uncommitted'; window.currentRoute={model:'old',provider:'google'};
      window.KissneTransport={
        hasToken:()=>true,
        bootstrap:async()=>({bound:true,conversation:{session_id:'s',session_key:'s'},history:[],pending_approvals:[]}),
        history:async()=>({messages:[],has_more:false}),poll:async()=>({events:[]}),ack:async()=>{},
        modelOptions:()=>new Promise(resolve=>setTimeout(()=>resolve({
          model:window.currentRoute.model,provider:window.currentRoute.provider,effort:'medium',efforts:['medium','high'],
          providers:[{slug:'google',name:'Google',models:['old']},{slug:'opencode-go',name:'OpenCode Go',models:['mimo-v2.6-flash']},{slug:'empty',name:'Empty',models:[]}]
        }),9000)),
        setModel:async(model,effort,provider)=>window.switchMode==='uncommitted'
          ? {ok:true,model:'old',provider:'google',effort:'medium'}
          : (window.currentRoute={model,provider}, {ok:true,model,provider,effort:'medium'})
      };
      const screen=window.KSN.screens.find(s=>s.id==='chat');
      const ctx={state:'empty',params:new URLSearchParams()};
      const root=document.getElementById('test');root.innerHTML=screen.render(ctx);
      window.cleanup=screen.mount(root,ctx);
    });
    await page.waitForFunction(()=>document.querySelector('[data-chat-menu="model"] .hsel__v').textContent==='old',null,{timeout:15000});
    await page.locator('[data-chat-menu="model"]').click();
    await page.locator('[data-provider-pick="empty"]').click();
    assert.equal(await page.locator('[data-hermes-provider="empty"]').count(),0);
    await page.locator('[data-provider-pick="opencode-go"]').click();
    await page.locator('[data-hermes-provider="opencode-go"]').click();
    await page.waitForSelector('.system-notice');
    assert.equal(await page.locator('[data-chat-menu="model"] .hsel__v').textContent(),'old');
    await page.evaluate(()=>window.switchMode='committed');
    await page.locator('[data-hermes-provider="opencode-go"]').click();
    await page.waitForFunction(()=>document.querySelector('[data-chat-menu="model"] .hsel__v').textContent==='mimo-v2.6-flash');
    assert.deepEqual(errors,[]);
    console.log('PASS: slow inventory succeeds; empty provider stays empty; uncommitted ack cannot change header; committed selection updates it');
    await page.evaluate(()=>{if(typeof window.cleanup==='function')window.cleanup();});
  } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
