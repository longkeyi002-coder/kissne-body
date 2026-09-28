/* Offline browser test: slow history/list reads must not block chat or cross sessions. */
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright-core');

(async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_EXECUTABLE, headless: true, args: ['--no-sandbox', '--disable-gpu'] });
  try {
    const page = await browser.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    const base = path.resolve(__dirname, '..');
    await page.route('**/*', async route => {
      const url = new URL(route.request().url());
      if (url.origin !== 'http://kissne.test') return route.abort();
      if (url.pathname === '/') return route.fulfill({ contentType:'text/html; charset=utf-8', body:'<html><head><meta charset="utf-8"></head><body><main id="test"></main></body></html>' });
      const file = path.resolve(base, '.' + url.pathname);
      if (!file.startsWith(base + path.sep)) return route.abort();
      try { await route.fulfill({ body:await fs.readFile(file), contentType:'application/javascript; charset=utf-8' }); }
      catch { await route.fulfill({ status:404 }); }
    });
    await page.goto('http://kissne.test/');
    for (const file of ['core.js','assets/_manifest.js','assets/icons/sprite-data.js','assets.js','transport.js','chat-activity.js','screens-a.js']) {
      await page.addScriptTag({ url:'http://kissne.test/' + file });
    }
    await page.evaluate(() => {
      window.activeSession = 'old';
      window.pollCount = 0;
      window.historyCalls = [];
      window.events = [];
      window.oldHistory = new Promise(resolve => { window.resolveOldHistory = resolve; });
      window.newHistory = new Promise(resolve => { window.resolveNewHistory = resolve; });
      window.sessionRefresh = new Promise(resolve => { window.resolveSessionRefresh = resolve; });
      window.KissneSessionIndex = { loaded:true, sessions:[
        { id:'old', key:'old', title:'旧会话', active:true },
        { id:'new', key:'new', title:'新会话', active:false }
      ] };
      window.KissneRefreshSessions = () => window.sessionRefresh;
      window.KissneTransport = {
        hasToken:()=>true,
        bootstrap:async()=>({bound:true,conversation:{session_id:window.activeSession,session_key:window.activeSession},
          history:[{role:'user',text:window.activeSession === 'old' ? '旧会话最新消息' : '新会话最新消息',message_ref:window.activeSession + ':1'}],pending_approvals:[]}),
        history:()=>{window.historyCalls.push(window.activeSession);return window.activeSession === 'old' ? window.oldHistory : window.newHistory;},
        poll:async()=>{window.pollCount++;return {events:window.events.splice(0)};}, ack:async()=>{},
        selectSession:async(_key,id)=>{window.activeSession=id;return {conversation:{session_id:id}};},
        modelOptions:async()=>{const e=new Error('not found');e.status=404;throw e;}
      };
      const screen = window.KSN.screens.find(s=>s.id==='chat');
      const ctx = { state:'empty', params:new URLSearchParams() };
      const root = document.getElementById('test');
      root.innerHTML = screen.render(ctx);
      window.cleanup = screen.mount(root,ctx);
    });
    await page.waitForFunction(() => document.querySelector('[data-chat-menu="model"] .hsel__v').textContent === '读取失败');
    await page.locator('[data-chat-menu="model"]').click();
    assert((await page.locator('.modelpick__foot').textContent()).includes('HTTP 404'));
    await page.waitForFunction(() => document.querySelector('#test').textContent.includes('旧会话最新消息') && window.pollCount > 0);
    await page.waitForFunction(() => window.historyCalls.includes('old'));
    await page.locator('[data-session-drawer-open]').click();
    await page.locator('[data-session-id="new"] [data-session-select]').click();
    await page.waitForFunction(() => document.querySelector('#test').textContent.includes('新会话最新消息')
      && !document.querySelector('#test').textContent.includes('正在切换会话'));
    await page.waitForFunction(() => window.historyCalls.includes('new'));
    await page.evaluate(() => window.events.push({type:'pending',turn_id:'turn-new'}));
    await page.waitForFunction(() => document.querySelector('#test').textContent.includes('正在看你刚才说的话'));
    await page.evaluate(() => window.resolveNewHistory({ messages:[{role:'user',text:'新会话完整历史',message_ref:'new:1'}],has_more:false }));
    await page.waitForTimeout(50);
    assert.equal(await page.getByText('新会话完整历史').count(),0);
    await page.evaluate(() => window.events.push({type:'completed',turn_id:'turn-new',text:'新会话回答'}));
    await page.waitForFunction(() => document.querySelector('#test').textContent.includes('新会话完整历史')
      && document.querySelector('#test').textContent.includes('新会话回答'));
    await page.evaluate(() => window.resolveOldHistory({ messages:[{role:'user',text:'旧会话迟到消息',message_ref:'old:2'}],has_more:false }));
    await page.waitForTimeout(100);
    assert.equal(await page.getByText('旧会话迟到消息').count(),0);
    assert.equal(await page.getByText('新会话完整历史').count(),1);
    assert.deepEqual(errors,[]);
    console.log('PASS: bootstrap renders before history; polling runs; session switch ignores slow list and stale history; model 404 is visible');
    await page.evaluate(() => { if (typeof window.cleanup === 'function') window.cleanup(); });
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode=1; });
