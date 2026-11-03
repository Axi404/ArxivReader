// 本地看构建结果用的小服务器，路由和线上 nginx 一样：/daily/<日期> 都给 /daily/index.html，
// /api/ 转给后端（API_URL，比如 http://127.0.0.1:7298）。e2e 测试也用它。
import fs from 'node:fs'
import http from 'node:http'
import path from 'node:path'

const root = path.resolve(process.env.DIST ?? 'dist')
const port = Number(process.env.PORT ?? 4329)
const api = process.env.API_URL
const TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.woff2': 'font/woff2',
  '.json': 'application/json'
}

function proxy(req, res, url) {
  if (!api) {
    res.writeHead(502).end('no API_URL')
    return
  }
  const target = new URL(url.pathname + url.search, api)
  const upstream = http.request(target, { method: req.method, headers: { ...req.headers, host: target.host } }, (r) => {
    res.writeHead(r.statusCode ?? 502, r.headers)
    r.pipe(res)
  })
  upstream.on('error', () => res.writeHead(502).end('API unreachable'))
  req.pipe(upstream)
}

http
  .createServer((req, res) => {
    const url = new URL(req.url ?? '/', 'http://localhost')
    if (url.pathname.startsWith('/api/')) return proxy(req, res, url)
    let file = url.pathname
    if (/^\/daily\/\d{4}-\d{2}-\d{2}\/?$/.test(file)) file = '/daily/index.html'
    else if (file.endsWith('/')) file += 'index.html'
    const full = path.join(root, path.normalize(file))
    if (!full.startsWith(root)) return res.writeHead(403).end()
    fs.readFile(full, (err, buf) => {
      if (err) {
        const page = path.join(root, '404.html')
        const body = fs.existsSync(page) ? fs.readFileSync(page) : 'not found'
        return res.writeHead(404, { 'Content-Type': TYPES['.html'] }).end(body)
      }
      res.writeHead(200, { 'Content-Type': TYPES[path.extname(full)] ?? 'application/octet-stream' }).end(buf)
    })
  })
  .listen(port, '127.0.0.1', () => console.log(`http://127.0.0.1:${port}  (dist: ${root}, api: ${api ?? 'none'})`))
