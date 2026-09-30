import fs from 'node:fs'
import { JSDOM } from 'jsdom'
import { afterEach, expect, test } from 'vitest'

const windows = []
afterEach(() => windows.splice(0).forEach(window => window.close()))

function fixture(history) {
  const { window } = new JSDOM('<div id="root"></div>', {
    url: 'https://kissne.test/?native=1#/chat',
    runScripts: 'outside-only', pretendToBeVisual: true,
  })
  windows.push(window)
  window.KissneTransport = {
    hasToken: () => true,
    ensureToken: async () => {},
    bootstrap: async () => ({ bound: true, conversation: { session_id: 'room-a' }, history }),
    poll: async () => ({ events: [] }),
    modelOptions: async () => ({ providers: [], models: [], efforts: [] }),
  }
  // Execute the production screen and its dependencies; assertions target the rendered DOM.
  for (const file of ['core.js', 'assets.js', 'chat-lifecycle.js', 'screens-a.js']) {
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
  return { root, reopen }
}

function row(role, text, extra = {}) {
  return { role, text, turn_id: 'first', created_at: 1700000000, ...extra }
}

test('reopening keeps commentary once in its turn process, never in spoken bubbles', async () => {
  const history = [
    row('user', '第一句话', { message_ref: 'turn:first:user' }),
    row('assistant', '准备查一下资料', { presentation: 'commentary' }),
    row('assistant', '查好了', { message_ref: 'turn:first:assistant' }),
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
    row('assistant', 'terminal: 查询结果', { presentation: 'commentary', tool_call_id: 'search-call' }),
    row('assistant', '完成', { message_ref: 'turn:first:assistant' }),
  ])
  await expect.poll(() => root.querySelector('[data-tool-call-id="search-call"]')?.textContent).toContain('terminal: 查询结果')
  expect(root.querySelectorAll('.process-step--reasoning')).toHaveLength(0)
  expect(root.textContent).not.toContain('Interrupting current task')
  expect(root.textContent).not.toContain("I'll respond to your message shortly.")
  expect([...root.querySelectorAll('.msg--ai .bubble')].map(node => node.textContent).join('')).not.toContain('terminal:')
})
