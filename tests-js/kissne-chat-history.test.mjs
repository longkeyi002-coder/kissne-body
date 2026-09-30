import fs from 'node:fs'
import { JSDOM } from 'jsdom'
import { afterEach, expect, test } from 'vitest'

const windows = []
afterEach(() => windows.splice(0).forEach(window => window.close()))

function fixture(history, options = {}) {
  const { window } = new JSDOM('<div id="root"></div>', {
    url: 'https://kissne.test/?native=1#/chat',
    runScripts: 'outside-only', pretendToBeVisual: true,
  })
  windows.push(window)
  const style = window.document.createElement('style')
  style.textContent = fs.readFileSync(new URL('../kissne-prototype/prototype/styles.css', import.meta.url), 'utf8')
  window.document.head.append(style)
  window.KissneTransport = {
    hasToken: () => true,
    ensureToken: async () => {},
    bootstrap: async () => options.bootstrap?.() || ({ bound: true, conversation: { session_id: 'room-a' }, history }),
    poll: async () => ({ events: options.poll?.() || [] }),
    modelOptions: async () => ({ providers: [], models: [], efforts: [] }),
    sendText: options.sendText || (async () => ({ turn_id: 'second' })),
    ack: async () => {},
    updateNotification: options.updateNotification || (() => {}),
  }
  // Execute the production screen and its dependencies; assertions target the rendered DOM.
  for (const file of ['core.js', 'assets.js', 'chat-lifecycle.js', 'chat-presentation.js', 'screens-a.js']) {
    window.eval(fs.readFileSync(new URL('../kissne-prototype/prototype/' + file, import.meta.url), 'utf8'))
  }
  const screen = window.KSN.screens.find(screen => screen.id === 'chat')
  const root = window.document.getElementById('root')
  const ctx = { state: 'normal', params: new window.URLSearchParams() }
  let dispose
  function reopen() {
    dispose?.()
    root.innerHTML = screen.render(ctx)
    dispose = screen.mount(root, ctx)
  }
  reopen()
  return { root, reopen, window }
}

function row(role, text, extra = {}) {
  return { role, text, turn_id: 'first', created_at: 1700000000, ...extra }
}

test('reopening keeps commentary once in its turn process, never in spoken bubbles', async () => {
  const history = [
    row('user', '第一句话', { message_ref: 'turn:first:user' }),
    row('assistant', '准备查一下资料', { presentation: 'commentary' }),
    row('assistant', '查好了'),
    row('user', '第二句话', { turn_id: 'second', message_ref: 'turn:second:user', created_at: 1700000001 }),
  ]
  const { root, reopen } = fixture(history)
  for (let opening = 0; opening < 2; opening++) {
    if (opening) reopen()
    await expect.poll(() => root.querySelector('[data-activity-turn="first"]')?.textContent).toContain('准备查一下资料')
    expect([...root.querySelectorAll('.msg--ai .bubble')].map(node => node.textContent).join('')).not.toContain('准备查一下资料')
    expect(root.textContent.split('准备查一下资料')).toHaveLength(2)
    const activity = root.querySelector('[data-activity-turn="first"]')
    const laterUser = [...root.querySelectorAll('.msg--me')].find(node => node.textContent.includes('第二句话'))
    expect(activity.compareDocumentPosition(laterUser) & 4).toBeTruthy()
  }
})

test('history commentary retains empty/control guards and sends tool transcripts to tools', async () => {
  const { root } = fixture([
    row('user', '查一下', { message_ref: 'turn:first:user' }),
    row('assistant', '   ', { presentation: 'commentary' }),
    row('assistant', 'Interrupting current task', { presentation: 'commentary' }),
    row('assistant', "I'll respond to your message shortly.", { presentation: 'commentary' }),
    row('assistant', "↪ Redirected current run. I'll adjust using your correction.", { presentation: 'commentary' }),
    row('assistant', 'terminal: 查询结果', { presentation: 'commentary', tool_call_id: 'search-call' }),
    row('assistant', '完成', { message_ref: 'turn:first:assistant' }),
  ])
  await expect.poll(() => root.querySelector('[data-tool-call-id="search-call"]')?.textContent).toContain('terminal: 查询结果')
  expect(root.querySelectorAll('.process-step--reasoning')).toHaveLength(0)
  expect(root.textContent).not.toContain('Interrupting current task')
  expect(root.textContent).not.toContain("I'll respond to your message shortly.")
  expect(root.textContent).not.toContain('Redirected current run')
  expect([...root.querySelectorAll('.msg--ai .bubble')].map(node => node.textContent).join('')).not.toContain('terminal:')
})

test('individual answer bubbles interleave with a new user message and retain that order on reopen', async () => {
  const answer = '第一句。第二句！！（动作。完整。）\n他说："晚点回来。"'
  const history = [row('user', '开始', { message_ref: 'turn:first:user', created_at: Date.now() / 1000 })]
  let sent = false
  const { root, reopen, window } = fixture(history, {
    poll: () => {
      if (sent) return []
      sent = true
      return [{ type: 'completed', turn_id: 'first', text: answer }]
    },
  })
  await expect.poll(() => root.querySelector('.msg--ai .bubble')?.textContent).toBe('第一句。')
  const userTime = Date.now() / 1000
  const input = root.querySelector('.composer__input')
  input.value = '中途这句'
  input.dispatchEvent(new window.KeyboardEvent('keydown', { key: 'Enter', bubbles: true }))
  await expect.poll(() => root.querySelectorAll('.msg--ai .bubble').length, { timeout: 4000 }).toBe(4)
  const spoken = () => [...root.querySelectorAll('[data-chat-message] .bubble')].map(node => node.textContent)
  const order = ['开始', '第一句。', '中途这句', '第二句！！', '（动作。完整。）', '他说："晚点回来。"']
  expect(spoken()).toEqual(order)
  history.push(row('assistant', answer, { message_ref: 'turn:first:assistant' }))
  history.push(row('user', '中途这句', { turn_id: 'second', message_ref: 'turn:second:user', created_at: userTime }))
  reopen()
  await expect.poll(spoken).toEqual(order)
})

test('idle and restored pending chats do not start a waiting animation', async () => {
  const { root, reopen } = fixture([], {
    bootstrap: () => ({ bound: true, conversation: { session_id: 'room-a' }, history: [], pending_turn_id: 'first' }),
  })
  for (let opening = 0; opening < 2; opening++) {
    if (opening) reopen()
    await expect.poll(() => root.querySelector('[data-turn-bridge]')).toBeTruthy()
    expect(root.querySelector('[data-turn-bridge]').hidden).toBe(true)
  }
})

test('only a local send starts waiting; first thinking event removes star and tail', async () => {
  const events = []
  const { root, window } = fixture([], { poll: () => events.splice(0) })
  await expect.poll(() => root.querySelector('[data-session-status]').hidden).toBe(true)
  expect(root.querySelector('[data-turn-bridge]:not([hidden])')).toBeNull()
  const input = root.querySelector('.composer__input')
  input.value = '开始'
  input.dispatchEvent(new window.KeyboardEvent('keydown', { key: 'Enter', bubbles: true }))
  await expect.poll(() => root.querySelector('[data-turn-bridge]:not([hidden])')).toBeTruthy()
  const bridge = root.querySelector('[data-turn-bridge]')
  const firstX = Number(bridge.querySelector('[data-wait-star]').getAttribute('transform').match(/translate\(([^ ]+)/)[1])
  await expect.poll(() => Number(bridge.querySelector('[data-wait-star]').getAttribute('transform').match(/translate\(([^ ]+)/)[1])).toBeLessThan(firstX)
  expect(bridge.querySelector('animateMotion')).toBeNull()
  events.push({ type: 'delta', presentation: 'reasoning', turn_id: 'second', text: '内部过程。' })
  await expect.poll(() => root.querySelector('.process-reasoning')?.textContent).toContain('内部过程。')
  expect(bridge.hidden).toBe(true)
  const stoppedPose = bridge.querySelector('[data-wait-star]').getAttribute('transform')
  events.push({ type: 'completed', turn_id: 'second', text: '<think>内部过程。</think>回答。' })
  await expect.poll(() => root.querySelector('.msg--ai .bubble')?.textContent).toBe('回答。')
  expect(bridge.querySelector('[data-wait-star]').getAttribute('transform')).toBe(stoppedPose)
  const process = root.querySelector('.process-reasoning')
  expect(window.getComputedStyle(process).borderLeftWidth).toBe('0px')
})

test('composer panels keep inside taps, close on outside taps and exclude each other', async () => {
  const { root, window } = fixture([])
  const plus = root.querySelector('[data-plus-toggle]')
  const plusPanel = root.querySelector('[data-plus-panel]')
  const sticker = root.querySelector('[data-sticker-toggle]')
  const stickerPanel = root.querySelector('.stkpanel')
  const tap = node => node.dispatchEvent(new window.Event('pointerdown', { bubbles: true }))
  plus.click()
  expect(plusPanel.hidden).toBe(false)
  tap(plusPanel)
  expect(plusPanel.hidden).toBe(false)
  sticker.click()
  expect(plusPanel.hidden).toBe(true)
  expect(stickerPanel.hidden).toBe(false)
  tap(stickerPanel)
  expect(stickerPanel.hidden).toBe(false)
  tap(root.querySelector('.chatbody'))
  expect(stickerPanel.hidden).toBe(true)
  plus.click()
  tap(window.document.body)
  expect(plusPanel.hidden).toBe(true)
  for (const selector of ['.composerwrap', '.quickbar']) {
    expect(window.getComputedStyle(root.querySelector(selector)).backgroundColor).toBe('rgba(0, 0, 0, 0)')
  }
  expect(window.getComputedStyle(root.querySelector('.composerwrap')).position).toBe('absolute')
  expect(window.getComputedStyle(root.querySelector('.chatstatus')).position).toBe('absolute')
})

test('a different room with identical answer text cannot inherit the previous room process', async () => {
  let room = 'room-a'
  let polled = false
  const { root, reopen } = fixture([], {
    bootstrap: () => ({ bound: true, conversation: { session_id: room }, history: room === 'room-a' ? [] : [
      { role: 'user', text: '另一个房间', created_at: 1700000000 },
      { role: 'assistant', text: '好的', created_at: 1700000001 },
    ] }),
    poll: () => {
      if (polled) return []
      polled = true
      return [
        { type: 'delta', presentation: 'reasoning', turn_id: 'a-turn', text: 'A房间私有过程' },
        { type: 'completed', turn_id: 'a-turn', text: '好的' },
      ]
    },
  })
  await expect.poll(() => root.textContent).toContain('A房间私有过程')
  await expect.poll(() => root.querySelector('.bubble')?.textContent).toBe('好的')
  room = 'room-b'
  reopen()
  await expect.poll(() => root.textContent).toContain('另一个房间')
  expect(root.textContent).not.toContain('A房间私有过程')
  expect(root.querySelectorAll('[data-activity-turn]')).toHaveLength(0)
})

test('sticker tool transcripts stay out of spoken bubbles and ordinary emoji remain', async () => {
  const { root } = fixture([
    row('user', '找表情', { message_ref: 'turn:first:user' }),
    row('assistant', '🎨 kissne_sticker_search: "早"', { presentation: 'commentary', tool_call_id: 'sticker-call' }),
    row('assistant', '🎨 kissne_sticker_search...', { presentation: 'commentary', tool_call_id: 'sticker-result' }),
    row('assistant', '早上好😊', { message_ref: 'turn:first:assistant' }),
  ])
  await expect.poll(() => root.querySelectorAll('.process-step--tool').length).toBe(2)
  expect(root.querySelectorAll('.process-step--reasoning')).toHaveLength(0)
  expect([...root.querySelectorAll('.msg--ai .bubble')].map(node => node.textContent)).toEqual(['早上好😊'])
  expect(root.querySelector('.activity-detail')?.textContent).not.toContain('🎨')
})

test('a reply arriving before send acknowledgement cannot restart waiting or the work notification', async () => {
  let accept
  const events = [], notifications = []
  const { root, window } = fixture([], {
    sendText: () => new Promise(resolve => { accept = resolve }),
    poll: () => events.splice(0),
    updateNotification: state => notifications.push(state),
  })
  const input = root.querySelector('.composer__input')
  input.value = '很快的回复'
  input.dispatchEvent(new window.KeyboardEvent('keydown', { key: 'Enter', bubbles: true }))
  await expect.poll(() => typeof accept).toBe('function')
  events.push({ type: 'completed', turn_id: 'second', text: '已经完成。' })
  await expect.poll(() => root.querySelector('.msg--ai .bubble')?.textContent).toBe('已经完成。')
  const beforeAck = notifications.length
  accept({ turn_id: 'second' })
  await expect.poll(() => Array.from({ length: window.localStorage.length }, (_, i) => window.localStorage.getItem(window.localStorage.key(i))).join('')).toContain('turn:second:user')
  expect(root.querySelector('.msg--me .bubble')?.textContent).toBe('很快的回复')
  expect(root.querySelector('[data-turn-bridge]:not([hidden])')).toBeNull()
  expect(root.querySelector('[data-live-stop]').hidden).toBe(true)
  expect(notifications.slice(beforeAck)).not.toContain('working')
})

test('events explicitly belonging to another session never appear in this chat', async () => {
  const events = [
    { type: 'delta', presentation: 'reasoning', session_id: 'room-b', turn_id: 'foreign', text: '别的会话过程' },
    { type: 'completed', session_id: 'room-b', turn_id: 'foreign', text: '别的会话回复' },
    { type: 'completed', session_id: 'room-a', turn_id: 'here', text: '本会话回复' },
  ]
  const { root } = fixture([], { poll: () => events.splice(0) })
  await expect.poll(() => root.querySelector('.msg--ai .bubble')?.textContent).toBe('本会话回复')
  expect(root.textContent).not.toContain('别的会话')
})
