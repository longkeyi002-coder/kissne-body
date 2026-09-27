import { defineConfig } from 'vitest/config'

export default defineConfig({
  test: {
    environment: 'node',
    /* 原型层的测试是 .test.js（transport/screens 的纯逻辑 seam），
       一起收进来，否则它们在 CI 里根本不跑。 */
    include: ['**/*.test.ts', '**/*.test.js'],
  },
})
