import { afterEach, beforeEach, expect, test, vi } from 'vitest';

/* screens-a.js 是 IIFE，只在加载时通过 globalThis.window.KSN 取组件工厂；
   给它一份最小垫片就能在 node 里拿到 globalThis.window.KissneReplyQuote（引用/复制的唯一 seam）。 */
function knStub() {
  const noop = () => '';
  return {
    registerScreen() {},
    ph: noop, btn: noop, icon: noop, chip: noop, appbar: noop, card: noop,
    field: noop, tabbar: noop, modal: noop, note: noop, sectionTitle: noop,
    listRow: noop, banner: noop, kv: noop,
    esc: (value) => String(value == null ? '' : value)
  };
}

async function replyQuote() {
  vi.resetModules();
  globalThis.window = { KSN: knStub() };
  await import('../kissne-prototype/prototype/screens-a.js');
  return globalThis.window.KissneReplyQuote;
}

/* 气泡只需要 getAttribute，用最小替身避免依赖真实 DOM。 */
function fakeBubble(attrs) {
  return { getAttribute: (name) => (name in attrs ? attrs[name] : null) };
}

beforeEach(() => {
  delete globalThis.window;
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.resetModules();
});

test('fromBubble extracts ref/role/text and returns null without a ref', async () => {
  const quote = await replyQuote();
  expect(quote.fromBubble(fakeBubble({
    'data-message-ref': 'turn:t1:user',
    'data-message-role': 'user',
    'data-message-text': '  晚饭吃什么  '
  }))).toEqual({ ref: 'turn:t1:user', role: 'user', text: '晚饭吃什么' });

  /* 没有 data-message-ref（服务端还没确认 / 系统行）时不可引用 */
  expect(quote.fromBubble(fakeBubble({ 'data-message-role': 'assistant', 'data-message-text': '在的' }))).toBeNull();
  expect(quote.fromBubble(fakeBubble({ 'data-message-ref': '', 'data-message-text': '在的' }))).toBeNull();
  expect(quote.fromBubble(null)).toBeNull();
});

test('fromBubble treats anything but user as the assistant', async () => {
  const quote = await replyQuote();
  expect(quote.fromBubble(fakeBubble({ 'data-message-ref': 'turn:t2:assistant', 'data-message-role': 'assistant' })).role)
    .toBe('assistant');
  expect(quote.fromBubble(fakeBubble({ 'data-message-ref': 'turn:t2:assistant' })).role).toBe('assistant');
  expect(quote.roleOf('user')).toBe('user');
  expect(quote.roleOf('me')).toBe('assistant');
});

test('clip folds whitespace and cuts only past the limit', async () => {
  const quote = await replyQuote();
  expect(quote.clip('  多行\n文本  ', 40)).toBe('多行 文本');

  const exact = 'a'.repeat(40);
  expect(quote.clip(exact, 40)).toBe(exact);
  expect(quote.clip('a'.repeat(41), 40)).toBe('a'.repeat(40) + '…');
  expect(quote.clip('a'.repeat(40), 40).includes('…')).toBe(false);

  expect(quote.clip('a'.repeat(quote.CLIP + 1))).toBe('a'.repeat(quote.CLIP) + '…');
  expect(quote.clip(null)).toBe('');
  expect(quote.clip('   ')).toBe('');
});

test('pending quote is set, replaced, cleared and broadcast to painters', async () => {
  const quote = await replyQuote();
  const painted = [];
  const off = quote.onPaint(() => painted.push(quote.pending() && quote.pending().ref));

  expect(quote.pending()).toBeNull();

  quote.set({ ref: 'turn:t1:user', role: 'user', text: '晚饭吃什么' });
  expect(quote.pending()).toEqual({ ref: 'turn:t1:user', role: 'user', text: '晚饭吃什么' });

  /* 再长按另一条：直接替换 */
  quote.set({ ref: 'turn:t2:assistant', role: 'assistant', text: '在想' });
  expect(quote.pending()).toEqual({ ref: 'turn:t2:assistant', role: 'assistant', text: '在想' });
  expect(painted).toEqual(['turn:t1:user', 'turn:t2:assistant']);

  quote.clear();
  expect(quote.pending()).toBeNull();

  /* 没有 ref 的东西清掉待引用，而不是留一条发不出去的引用 */
  quote.set({ ref: 'turn:t1:user', role: 'user', text: 'x' });
  expect(quote.set({ role: 'user', text: '没有 ref' })).toBeNull();
  expect(quote.pending()).toBeNull();

  off();
  quote.set({ ref: 'turn:t3:user', role: 'user', text: 'y' });
  /* 订阅退掉之后不再回调；此前每一次 set/clear 都回调过（含上面那次重新点引用） */
  expect(painted).toEqual(['turn:t1:user', 'turn:t2:assistant', null, 'turn:t1:user', null]);
});

test('sendText gets reply_to = the pending ref, and an empty string when idle', async () => {
  const quote = await replyQuote();
  const calls = [];
  const transport = {
    sendText(text, messageId, replyTo) {
      calls.push([text, messageId, replyTo]);
      return Promise.resolve({ turn_id: 't9' });
    }
  };

  quote.set({ ref: 'turn:t1:user', role: 'user', text: '晚饭吃什么' });
  await quote.sendWithQuote(transport, '吃面', 'mid-1', quote.pending());
  quote.clear();
  await quote.sendWithQuote(transport, '随便', 'mid-2', quote.pending());

  expect(calls).toEqual([
    ['吃面', 'mid-1', 'turn:t1:user'],
    ['随便', 'mid-2', '']
  ]);

  expect(quote.sendArgs('x', 'mid-3', quote.pending())).toEqual({ text: 'x', messageId: 'mid-3', replyTo: '' });
  expect(quote.sendArgs('x', 'mid-4', { ref: 'turn:t5:assistant' }).replyTo)
    .toBe('turn:t5:assistant');
  expect(quote.sendArgs(null, 'mid-5', null).text).toBe('');
});

test('copyText uses the async clipboard and reports failure instead of throwing', async () => {
  const quote = await replyQuote();
  const written = [];
  vi.stubGlobal('navigator', {
    clipboard: { writeText(value) { written.push(value); return Promise.resolve(); } }
  });
  await expect(quote.copyText('原文')).resolves.toBe(true);
  expect(written).toEqual(['原文']);

  /* 异步剪贴板拒绝 -> 退化到 execCommand；node 里没有 document，只能失败 */
  vi.stubGlobal('navigator', {
    clipboard: { writeText() { return Promise.reject(new Error('denied')); } }
  });
  await expect(quote.copyText('原文')).resolves.toBe(false);

  /* 完全没有 clipboard：也不抛 */
  vi.stubGlobal('navigator', {});
  await expect(quote.copyText('原文')).resolves.toBe(false);
});
