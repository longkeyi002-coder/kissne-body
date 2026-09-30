import { createRequire } from 'node:module'
import { expect, test } from 'vitest'
const require = createRequire(import.meta.url)
const { channels, delivery } = require('../kissne-prototype/prototype/chat-presentation.js')

test('explicit thinking tags never become answer text, including an unfinished thought', () => {
  expect(channels('<think>内部过程</think>正文')).toEqual({ reasoning: '内部过程', answer: '正文' })
  expect(channels('<analysis>仍在思考')).toEqual({ reasoning: '仍在思考', answer: '' })
  expect(channels('（普通动作。）😊')).toEqual({ reasoning: '', answer: '（普通动作。）😊' })
  const code = '```html\n<think>示例</think>\n```'
  expect(channels(code)).toEqual({ reasoning: '', answer: code })
})

test('delivery preserves arrived bubbles, cancels queued bubbles, and flushes on leaving', () => {
  const emitted = [], timers = new Map()
  let nextId = 0
  const queue = delivery(value => emitted.push(value), fn => { timers.set(++nextId, fn); return nextId }, id => timers.delete(id))
  queue.update(['第一句', '第二句'])
  expect(emitted).toEqual(['第一句'])
  queue.update(['第一句', '第二句', '第三句'])
  expect(emitted).toEqual(['第一句'])
  queue.stop(false)
  expect(timers.size).toBe(0)
  expect(emitted).toEqual(['第一句'])
  const resumed = delivery(value => emitted.push(value), fn => { timers.set(++nextId, fn); return nextId }, id => timers.delete(id), 1)
  resumed.update(['第一句', '第二句', '第三句'])
  resumed.stop(true)
  expect(emitted).toEqual(['第一句', '第二句', '第三句'])
  expect(timers.size).toBe(0)
})
