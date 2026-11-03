import { defineConfig } from 'vitest/config'

// 只跑 tests/unit；tests/e2e 是 Playwright 的
export default defineConfig({
  test: { include: ['tests/unit/**/*.test.ts'] }
})
