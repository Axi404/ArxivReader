import { defineConfig, devices } from '@playwright/test'

// 先 astro build，再用 scripts/serve.mjs 按线上的路由发 dist/；/api 在测试里拦下来，不用起后端
const PORT = 4331
const desktop = { width: 1440, height: 900 }

export default defineConfig({
  testDir: 'tests/e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  reporter: process.env.CI ? 'github' : 'list',
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    // 默认按“减少动态效果”跑，目录跳转是瞬时的；平滑滚动另有专门的测试
    reducedMotion: 'reduce',
    trace: 'retain-on-failure'
  },
  projects: [
    // 用本机装的 Chrome，不另下浏览器
    { name: 'chrome', use: { ...devices['Desktop Chrome'], channel: 'chrome', viewport: desktop } },
    { name: 'webkit', use: { ...devices['Desktop Safari'], viewport: desktop } }
  ],
  webServer: {
    command: 'node scripts/serve.mjs',
    env: { PORT: String(PORT) },
    url: `http://127.0.0.1:${PORT}/`,
    reuseExistingServer: !process.env.CI
  }
})
