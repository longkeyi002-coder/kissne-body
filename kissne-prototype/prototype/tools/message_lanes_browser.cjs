/* Offline interaction test. Requires playwright-core and a Chromium executable.
 * PLAYWRIGHT_MODULE=/path/to/playwright-core CHROMIUM_EXECUTABLE=/path/to/chromium node tools/message_lanes_browser.cjs
 */
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright-core');
(async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_EXECUTABLE, headless: true, args: ['--no-sandbox', '--disable-gpu'] });
  try {
    const page = await browser.newPage({ viewport: { width: 412, height: 915 } });
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    const base = path.resolve(__dirname, '..');
    await page.route('**/*', async route => {
      const url = new URL(route.request().url());
      if (url.origin !== 'http://kissne.test') return route.abort();
      if (url.pathname === '/') return route.fulfill({contentType:'text/html', body:'<html><head><meta charset="utf-8"><link rel="stylesheet" href="styles.css"></head><body><main id="test"></main></body></html>'});
      const file = path.resolve(base, '.' + url.pathname);
      if (!file.startsWith(base + path.sep)) return route.abort();
      try { await route.fulfill({body:await fs.readFile(file),contentType:file.endsWith('.js')?'application/javascript; charset=utf-8':file.endsWith('.css')?'text/css':'image/svg+xml'}); }
      catch { await route.fulfill({status:404,body:''}); }
    });
    await page.goto('http://kissne.test/');
    for (const file of ['core.js','assets/_manifest.js','assets/icons/sprite-data.js','assets.js','transport.js','chat-activity.js','screens-a.js']) {
      await page.addScriptTag({url:'http://kissne.test/'+file});
    }
    await page.evaluate(() => {
      window.events = [];
      window.detailRequests = [];
      window.KissneTransport = {
        hasToken:()=>true,
        bootstrap:async()=>({bound:true,conversation:{session_id:'s',session_key:'s'},history:[],pending_approvals:[]}),
        history:async()=>({messages:[],has_more:false}),
        poll:async()=>({events:window.events.splice(0)}),ack:async()=>{},
        toolDetails:async(turn,call,field,offset)=>{window.detailRequests.push({turn,call,field,offset});return {text:'\n完整结尾🦊',offset,next_offset:null};}
      };
      const screen = window.KSN.screens.find(s=>s.id==='chat');
      const ctx = {state:'empty',params:new URLSearchParams()};
      const root = document.getElementById('test');
      root.innerHTML = screen.render(ctx);
      window.cleanup = screen.mount(root,ctx);
    });
    const emit = async events => page.evaluate(events=>window.events.push(...events),events);
    await emit([
      {type:'delta',turn_id:'t',presentation:'commentary',text:'正在检查接口'},
      {type:'delta',turn_id:'t',presentation:'reasoning',text:'实际思考内容'},
      {type:'delta',turn_id:'t',presentation:'tool_call',tool_call_id:'a',activity:{tool_name:'terminal',label:'运行相关检查',arguments:'if True:\n    print("🦊")',status:'running'}},
      {type:'delta',turn_id:'t',presentation:'tool_call',tool_call_id:'b',activity:{tool_name:'terminal',label:'读取日志',arguments:'cat log',status:'running'}},
      {type:'notice',text:'Session reset: model example'}
    ]);
    await page.waitForSelector('[data-activity-key="tool:a"]');
    assert.equal(await page.locator('[data-live-answer]').innerText(),'');
    assert.equal(await page.locator('[data-activity-key="tool:a"] .activity-detail').isVisible(),false);
    await page.locator('[data-activity-key="tool:a"] [data-activity-toggle]').click();
    assert.equal(await page.locator('[data-activity-key="tool:a"] pre').textContent(),'if True:\n    print("🦊")');
    await emit([{type:'delta',turn_id:'t',presentation:'tool_result',tool_call_id:'a',activity:{tool_name:'terminal',output:'🦊'.repeat(2000),result_truncated:true,detail_ref:{turn_id:'t',tool_call_id:'a'},status:'completed'}}]);
    await page.waitForSelector('[data-tool-more="result"]');
    assert.equal(await page.locator('[data-activity-key="tool:a"] .activity-detail').isVisible(),true);
    await page.locator('[data-tool-more="result"]').click();
    await page.waitForFunction(()=>window.detailRequests.length===1 && !document.querySelector('[data-tool-more="result"]'));
    assert.equal(await page.locator('[data-tool-field="result"]').textContent(),'🦊'.repeat(2000)+'\n完整结尾🦊');
    assert.equal(await page.evaluate(()=>window.detailRequests[0].offset),2000);
    await emit([{type:'cancelled',turn_id:'t'}]);
    await page.waitForFunction(()=>document.querySelector('[data-activity-key="tool:b"]').textContent.includes('已取消'));
    assert((await page.locator('[data-activity-key="tool:a"]').innerText()).includes('完成'));
    assert.equal(await page.locator('.system-notice summary').innerText(),'Hermes 系统消息');
    await emit([{type:'completed',turn_id:'t2',presentation:'assistant_text',text:'git status 是我给你的正文'}]);
    await page.waitForFunction(()=>Array.from(document.querySelectorAll('[data-live-answer]')).some(el=>el.textContent.includes('git status 是我给你的正文')));
    assert.equal(await page.locator('.activity-section--commentary').count(),1);
    assert.equal(await page.locator('.activity-section--reasoning').count(),1);
    await emit(Array.from({length:30},(_,i)=>({type:'delta',turn_id:'t3',presentation:'tool_call',tool_call_id:'many'+i,activity:{tool_name:'terminal',label:'检查 '+i,status:'running'}})).concat([{type:'completed',turn_id:'t3',presentation:'assistant_text',text:'没有收到这些工具的结果'}]));
    await page.waitForSelector('[data-activity-key="tool:many29"]');
    assert.equal(await page.locator('[data-activity-turn="t3"] .activity-item').count(),30);
    assert((await page.locator('[data-activity-key="tool:many0"]').innerText()).includes('未收到结果'));
    assert.deepEqual(errors,[]);
    console.log('PASS: real chat mount, lane separation, concurrent tools, code formatting, fold persistence, Unicode pagination, cancellation, system notice, final answer');
    await page.evaluate(()=>{if(typeof window.cleanup==='function')window.cleanup();});
  } finally { await browser.close(); }
})().catch(err=>{console.error(err);process.exitCode=1;});
