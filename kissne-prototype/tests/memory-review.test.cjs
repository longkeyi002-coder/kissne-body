const test=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const path=require('node:path');

test('candidate tab loads Lifemem only and review submits the selected record',async()=>{
  const screens=[];const calls=[];const listeners={};
  const host={innerHTML:''}, notice={hidden:true,textContent:''};
  const fields={summary:{value:'记住，我喜欢绿色'},subject:{value:'user'},scope:{value:'reality'},category:{value:'preference'}};
  const root={querySelector(selector){if(selector==='[data-memory-list]')return host;if(selector==='[data-memory-notice]')return notice;const match=selector.match(/data-review-(\w+)/);return match?fields[match[1]]:null;},addEventListener(event,fn){(listeners[event]??=[]).push(fn)},removeEventListener(){}};
  const K={registerScreen:s=>screens.push(s),esc:s=>String(s??'').replaceAll('<','&lt;'),icon:()=>'',chip:s=>s,appbar:()=>''};
  const context={window:{KSN:K,KissneTransport:{ensureToken:async()=>{},memoryTimeline:async()=>({items:[]}),memoryCandidates:async()=>({items:[{id:7,summary:'记住，我喜欢绿色',quote:'记住，我喜欢绿色',status:'candidate',category:'preference',subject:'user',scope:'reality'}]}),adminMemory:()=>{throw Error('must not read builtin')},reviewMemory:async p=>calls.push(p)}},location:{hash:'#/memory'},setTimeout,clearTimeout,console};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../prototype/screens-b.js'),'utf8'),context);
  const screen=screens.find(s=>s.id==='memory');screen.mount(root,{state:'list'});
  await new Promise(resolve=>setImmediate(resolve));
  const mode={getAttribute:()=> 'candidate'};
  for(const fn of listeners.click)await fn({target:{closest:q=>q==='[data-memory-mode]'?mode:null},preventDefault(){}});
  await new Promise(resolve=>setImmediate(resolve));
  assert.match(host.innerHTML,/绿色/);
  const detail=screen.render({state:'detail',params:new URLSearchParams('id=7')});
  assert.match(detail,/data-memory-review="approve"/);assert.match(detail,/归属主体/);
  const button={disabled:false,getAttribute:name=>name==='data-id'?'7':'approve'};
  for(const fn of listeners.click)await fn({target:{closest:q=>q==='[data-memory-review]'?button:null},preventDefault(){}});
  assert.equal(calls.length,1);assert.equal(calls[0].id,7);assert.equal(calls[0].updates.scope,'reality');
  assert.equal(context.location.hash,'#/memory');
});
