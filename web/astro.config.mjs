import preact from '@astrojs/preact'
import tailwind from '@astrojs/tailwind'
import { defineConfig } from 'astro/config'

// 每日页只有一个静态页面 /daily/，日期从地址里读。线上由 nginx 把 /daily/<日期> 指到它，
// 看构建结果用 scripts/serve.mjs（astro preview 不带自定义插件）；astro dev 时由这个小插件做同样的事
const DAILY = /^\/daily\/\d{4}-\d{2}-\d{2}\/?(\?.*)?$/
const dailyRoute = {
  name: 'daily-route',
  configureServer(server) {
    server.middlewares.use((req, _res, next) => {
      if (req.url && DAILY.test(req.url)) req.url = '/daily/'
      next()
    })
  }
}

// 后端 API：本地开发时代理到 FastAPI（默认 7298 端口）
const api = process.env.API_URL ?? 'http://127.0.0.1:7298'

export default defineConfig({
  integrations: [preact(), tailwind({ applyBaseStyles: false })],
  build: { format: 'directory' },
  vite: {
    plugins: [dailyRoute],
    server: { proxy: { '/api': api } }
  }
})
