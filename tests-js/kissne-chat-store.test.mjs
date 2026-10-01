import { createRequire } from 'node:module'
import { IDBFactory } from 'fake-indexeddb'
import { expect, test } from 'vitest'
const { create } = createRequire(import.meta.url)('../kissne-prototype/prototype/chat-history-store.js')
test('Chinese substring indexing survives reopen, deduplicates updates and isolates accounts', async () => {
  const factory = new IDBFactory()
  let store = create(factory)
  const row = { role: 'assistant', text: '小羊，特别开心', turn_id: 'one', message_ref: 'turn:one:assistant', created_at: 1 }
  await store.put('a', [row, { ...row, turn_id: 'hidden', presentation: 'reasoning' }])
  await store.put('b', [{ ...row, text: '另一个账号的小羊' }])
  await store.close(); store = create(factory)
  expect((await store.search('a', '羊，特别')).map(row => row.text)).toEqual([row.text])
  expect(await store.search('a', '羊')).toHaveLength(1)
  expect(await store.search('b', '特别')).toEqual([])
  await store.put('a', [{ ...row, message_ref: 'canonical:1', text: '小羊醒了' }])
  expect((await store.search('a', '小羊')).map(row => row.message_ref)).toEqual(['canonical:1'])
  expect(await store.search('a', '开心')).toEqual([]); await store.close()
})
