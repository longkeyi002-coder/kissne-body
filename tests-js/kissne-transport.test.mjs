import fs from 'node:fs'
import { JSDOM } from 'jsdom'
import { expect, test } from 'vitest'
test('native write deadline covers network timeouts and idle polls never POST unchanged ACKs', async () => {
  const { window } = new JSDOM('', { runScripts: 'outside-only' }), timers = [], requests = []
  window.setTimeout = (callback, ms) => { const timer = { callback, ms }; timers.push(timer); return timer }
  window.clearTimeout = timer => timers.splice(timers.indexOf(timer), 1)
  window.KissneNativeTransport = { getBase: () => 'https://kissne.test', getCursor: () => 42, request: (...args) => requests.push(args) }
  window.eval(fs.readFileSync(new URL('../kissne-prototype/prototype/transport.js', import.meta.url), 'utf8'))
  const accepted = window.KissneTransport.sendText('hello', 'stable-id')
  expect(timers[0].ms).toBeGreaterThan(40000)
  window.KissneNativeBridge.resolve(requests[0][0], true, JSON.stringify({ turn_id: 'accepted' }))
  expect(await accepted).toEqual({ turn_id: 'accepted' })
  await window.KissneTransport.ack(42); await window.KissneTransport.ack(41)
  expect(requests).toHaveLength(1); window.close()
})
