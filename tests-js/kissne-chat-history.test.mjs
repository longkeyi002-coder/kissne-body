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
  options.setup?.(window)
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
    cancel: options.cancel || (async () => ({})),
    search: options.search, searchLocal: options.searchLocal, respondClarify: options.respondClarify,
    selectSession: options.selectSession, history: options.history,
    updateNotification: options.updateNotification || (() => {}),
  }
  // Execute the production screen and its dependencies; assertions target the rendered DOM.
  for (const file of ['core.js', 'assets.js', 'chat-lifecycle.js', 'chat-presentation.js', 'expression-filter.js', 'browser-transfer.js', 'screens-a.js']) {
    window.eval(fs.readFileSync(new URL('../kissne-prototype/prototype/' + file, import.meta.url), 'utf8'))
  }
  const screen = window.KSN.screens.find(screen => screen.id === 'chat')
  const root = window.document.getElementById('root')
  const ctx = { state: options.state || 'normal', params: new window.URLSearchParams(options.params) }
  let dispose
  function reopen(state, params) {
    dispose?.()
    if (state) ctx.state = state
    if (params) ctx.params = new window.URLSearchParams(params)
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

test('failure keeps text only in composer and explicit retry reuses its original id after reopening', async () => {
  const calls = []
  const { root, window, reopen } = fixture([], { sendText: async (text, id) => {
    calls.push({ text, id }); if (calls.length === 1) throw new Error('network timeout')
    return { turn_id: 'retry-turn', duplicate: true }
  } })
  await new Promise(resolve => setTimeout(resolve, 30))
  let input = root.querySelector('.composer__input'); input.value = '这条未确认送达'
  input.dispatchEvent(new window.KeyboardEvent('keydown', { key: 'Enter', bubbles: true }))
  await expect.poll(() => input.value, { timeout: 3000 }).toBe('这条未确认送达')
  expect(root.querySelectorAll('.msg--me .bubble')).toHaveLength(0)
  await new Promise(resolve => setTimeout(resolve, 700)); expect(calls).toHaveLength(1)
  reopen(); await expect.poll(() => root.querySelector('.composer__input').value).toBe('这条未确认送达')
  expect(root.querySelectorAll('.msg--me .bubble')).toHaveLength(0)
  input = root.querySelector('.composer__input'); input.dispatchEvent(new window.KeyboardEvent('keydown', { key: 'Enter', bubbles: true }))
  await expect.poll(() => calls.length).toBe(2); expect(calls[1]).toEqual(calls[0]); expect(input.value).toBe('')
})

test('local results appear first and stale remote responses cannot repopulate a cleared search', async () => {
  let finishRemote
  const { root, window } = fixture([], { state: 'search', searchLocal: async () => ({ results: [row('assistant', '本地关键词', { message_ref: 'local:1' })] }), search: () => new Promise(resolve => { finishRemote = resolve }) })
  const input = root.querySelector('.srchbox__in'); input.value = '关键词'; input.dispatchEvent(new window.Event('input'))
  await expect.poll(() => root.querySelector('.srch__row')?.textContent).toContain('本地关键词')
  await expect.poll(() => typeof finishRemote).toBe('function'); input.value = ''; input.dispatchEvent(new window.Event('input'))
  finishRemote({ results: [row('assistant', '不应重新出现', { message_ref: 'remote:1' })] })
  await new Promise(resolve => setTimeout(resolve, 20)); expect(root.querySelectorAll('.srch__row')).toHaveLength(0)
})

test('expired choice cards submit exact request ids and never emit approval slash commands', async () => {
  let delivered = false
  const responses = [], sent = []
  const { root } = fixture([], { poll: () => delivered ? [] : (delivered = true, [{ type: 'clarify_required', clarify_id: 'real-request', question: '现在重启还是稍后？', choices: ['现在重启', '稍后'] }]), respondClarify: async (...args) => { responses.push(args); const error = new Error('expired'); error.status = 404; throw error }, sendText: async (...args) => { sent.push(args); return {} } })
  await expect.poll(() => root.querySelector('[data-clarify-id]')).toBeTruthy(); root.querySelector('[data-clarify-options] button').click()
  await expect.poll(() => root.querySelector('[data-clarify-status]').textContent).toBe('请求已结束')
  expect(responses).toEqual([['real-request', '1', false]]); expect(sent).toEqual([])
  expect([...root.querySelectorAll('[data-clarify-id] button')].every(button => button.disabled)).toBe(true)
})

test('browser results require preview confirmation and retain their source', async () => {
  const sent = []
  const { root, window } = fixture([], { sendText: async text => { sent.push(text); return { turn_id: 'return-turn' } } })
  await new Promise(resolve => setTimeout(resolve, 30))
  window.dispatchEvent(new window.CustomEvent('kissne-browser-return', { detail: { text: '外部 AI 的回答', source_title: 'GPT', source_url: 'https://chatgpt.com/c/example', session_id: 'room-a' } }))
  expect(root.querySelector('[data-browser-return] textarea').value).toBe('外部 AI 的回答'); expect(sent).toEqual([])
  root.querySelector('[data-browser-send]').click(); await expect.poll(() => sent.length).toBe(1)
  expect(sent[0]).toContain('https://chatgpt.com/c/example'); expect(window.KissneBrowserTransfer.pending()).toBeNull()
})

test('active reasoning and tools expand, then collapse into one finished process record', async () => {
  let events = [], submitted = false
  const { root, window } = fixture([], { poll: () => { const out = events; events = []; return out }, sendText: async () => { submitted = true; return { turn_id: 'live' } } })
  await new Promise(resolve => setTimeout(resolve, 30))
  const input = root.querySelector('.composer__input'); input.value = '查一下'; input.dispatchEvent(new window.KeyboardEvent('keydown', { key: 'Enter', bubbles: true }))
  await expect.poll(() => submitted).toBe(true)
  events = [{ type: 'reasoning', turn_id: 'live', text: '正在思考' }, { type: 'tool_call', turn_id: 'live', tool_call_id: 'search', tool_name: 'web_search', text: '查网页' }]
  await expect.poll(() => root.querySelector('.process-reasoning')?.hidden, { timeout: 4000 }).toBe(false)
  expect(root.querySelector('[data-turn-bridge]').hidden).toBe(true)
  await expect.poll(() => root.querySelector('.process-step--tool .activity-detail')?.hidden).toBe(false)
  events = [{ type: 'delta', turn_id: 'live', text: '查到了。' }, { type: 'completed', turn_id: 'live', text: '查到了。' }]
  await expect.poll(() => root.querySelector('[data-activity-steps]')?.hidden, { timeout: 4000 }).toBe(true)
  expect(root.querySelectorAll('[data-activity-summary]')).toHaveLength(1)
  expect(root.querySelector('[data-activity-summary]').textContent).toContain('处理完成')
})

test('bold text never creates an empty bubble, including after reopening', async () => {
  const { root, reopen } = fixture([row('user', '加粗', { message_ref: 'turn:first:user' }), row('assistant', '**加粗句。**', { message_ref: 'turn:first:assistant' })])
  for (let i = 0; i < 2; i++) { if (i) reopen(); await expect.poll(() => root.querySelector('.msg--ai strong')?.textContent).toBe('加粗句。'); expect(root.querySelectorAll('.msg--ai .bubble')).toHaveLength(1) }
})

test('optional template removal keeps user quotes and formatted facts intact', async () => {
  const { root, window } = fixture([row('user', '当然可以！\n这是我的原话', { message_ref: 'turn:first:user' }), row('assistant', '当然可以！\n**事实：今天下雨。**\n希望这些信息对你有所帮助。', { message_ref: 'turn:first:assistant' })])
  await expect.poll(() => root.querySelector('.msg--ai strong')?.textContent).toBe('事实：今天下雨。')
  expect(root.querySelector('.msg--me').textContent).toContain('当然可以！'); expect(root.querySelector('.msg--ai').textContent).not.toContain('当然可以！')
  const html = '当然可以！\n<code>保留代码</code>'; expect(window.KissneExpressionFilter.html(html)).toBe(html)
  window.KissneExpressionFilter.setEnabled(false); expect(window.KissneExpressionFilter.html('当然可以！\n原文')).toBe('当然可以！\n原文')
})

test('a failed request settling after reopening removes its bubble and preserves newly typed text', async () => {
  let rejectSend
  const { root, window, reopen } = fixture([], { sendText: () => new Promise((resolve, reject) => { rejectSend = reject }) })
  await new Promise(resolve => setTimeout(resolve, 30))
  let input = root.querySelector('.composer__input'); input.value = '未确认的第一句'
  input.dispatchEvent(new window.KeyboardEvent('keydown', { key: 'Enter', bubbles: true }))
  await expect.poll(() => typeof rejectSend).toBe('function')
  reopen(); await new Promise(resolve => setTimeout(resolve, 30))
  input = root.querySelector('.composer__input'); input.value = '后来输入的第二句'
  input.dispatchEvent(new window.Event('input'))
  rejectSend(new Error('connection lost'))
  await expect.poll(() => root.querySelectorAll('.msg--me .bubble').length).toBe(0)
  expect(input.value).toBe('未确认的第一句 后来输入的第二句')
  reopen(); await expect.poll(() => root.querySelector('.composer__input').value).toBe('未确认的第一句 后来输入的第二句')
})

test('finishing an older turn cannot remove the status of a newer pending turn', async () => {
  const notices = [], events = []
  const { root } = fixture([], { poll: () => events.splice(0), updateNotification: state => notices.push(state) })
  await new Promise(resolve => setTimeout(resolve, 30)); notices.length = 0
  events.push({ type: 'pending', turn_id: 'old' }, { type: 'pending', turn_id: 'new' }, { type: 'completed', turn_id: 'old', text: '旧回复结束' })
  await expect.poll(() => root.textContent).toContain('旧回复结束')
  expect(notices.at(-1)).toBe('working')
  events.push({ type: 'completed', turn_id: 'new', text: '新回复结束' })
  await expect.poll(() => notices.at(-1)).toBe('ready')
})


test('a cross-room search hit opens its real conversation without copying it into the current room', async () => {
  let room = 'room-a'
  const selections = []
  const target = row('assistant', 'B房间的搜索命中', { session_id: 'room-b', message_ref: 'room-b:8', turn_id: '', created_at: 1700000008 })
  const { root, window, reopen } = fixture([], {
    state: 'search',
    searchLocal: async () => ({ results: [target] }), search: async () => ({ results: [] }),
    bootstrap: () => ({ bound: true, conversation: { session_id: room }, history: room === 'room-a' ? [row('user', 'A房间原消息')] : [] }),
    selectSession: async (key, id) => { selections.push(id); room = id },
    history: async (limit, before, id) => { expect(id).toBe('room-b'); return { messages: [row('user', 'B房间上下文', { session_id: id, turn_id: '', message_ref: 'room-b:7' })] } },
  })
  const input = root.querySelector('.srchbox__in'); input.value = '搜索命中'; input.dispatchEvent(new window.Event('input'))
  await expect.poll(() => root.querySelector('.srch__row')).toBeTruthy()
  expect(root.querySelector('.srch__row').getAttribute('data-nav')).toContain('jump_session=room-b')
  reopen('normal', { jump_ref: target.message_ref, jump_session: 'room-b' })
  await expect.poll(() => selections).toEqual(['room-b'])
  await expect.poll(() => root.querySelector('.chatbody').textContent).toContain(target.text)
  expect(root.querySelector('.chatbody').textContent).toContain('B房间上下文')
  expect(root.querySelector('.chatbody').textContent).not.toContain('A房间原消息')
  expect(root.querySelector('.is-hit')?.textContent).toContain(target.text)
})

test('retrying an unconfirmed send already restored from server history leaves one user bubble', async () => {
  const history = []
  let attempt = 0
  const { root, window, reopen } = fixture(history, { sendText: async text => {
    if (++attempt === 1) {
      history.push(row('user', text, { turn_id: 'already-accepted', message_ref: 'turn:already-accepted:user' }))
      throw new Error('reply lost after server accepted')
    }
    return { duplicate: true, turn_id: 'already-accepted' }
  } })
  await new Promise(resolve => setTimeout(resolve, 30))
  let input = root.querySelector('.composer__input'); input.value = '这条服务器已收到'
  input.dispatchEvent(new window.KeyboardEvent('keydown', { key: 'Enter', bubbles: true }))
  await expect.poll(() => input.value).toBe('这条服务器已收到')
  reopen(); await expect.poll(() => root.querySelectorAll('.msg--me .bubble').length).toBe(1)
  input = root.querySelector('.composer__input'); input.dispatchEvent(new window.KeyboardEvent('keydown', { key: 'Enter', bubbles: true }))
  await expect.poll(() => attempt).toBe(2)
  await expect.poll(() => root.querySelectorAll('.msg--me .bubble').length).toBe(1)
  expect(root.querySelector('.msg--me .bubble').textContent).toBe('这条服务器已收到')
})

test('an accepted request settling after reopening clears only its restored pending draft', async () => {
  let acceptSend
  const { root, window, reopen } = fixture([], { sendText: () => new Promise(resolve => { acceptSend = resolve }) })
  await new Promise(resolve => setTimeout(resolve, 30))
  let input = root.querySelector('.composer__input'); input.value = '等待确认这句'
  input.dispatchEvent(new window.KeyboardEvent('keydown', { key: 'Enter', bubbles: true }))
  await expect.poll(() => typeof acceptSend).toBe('function')
  reopen(); await expect.poll(() => root.querySelector('.composer__input').value).toBe('等待确认这句')
  acceptSend({ turn_id: 'confirmed' })
  await expect.poll(() => root.querySelector('.composer__input').value).toBe('')
  expect(root.querySelectorAll('.msg--me .bubble')).toHaveLength(1)
})
