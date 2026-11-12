// Rookery preview server. Dev only, no dependencies, binds to 127.0.0.1.
//   node dev/preview/server.mjs            → http://127.0.0.1:5178
// Serves the repo (so the real desktop/plugin.js loads unmodified), mounts the
// installed Hermes Desktop's compiled stylesheet read-only at /hermes/assets/
// (referenced, never copied into the repo), and pushes a reload over SSE when
// desktop/ or dev/preview/ changes.
import { createServer } from 'node:http'
import { readFile, readdir, stat } from 'node:fs/promises'
import { watch } from 'node:fs'
import { extname, join, normalize, resolve, sep } from 'node:path'
import { fileURLToPath } from 'node:url'

const PORT = Number(process.env.ROOKERY_PREVIEW_PORT || 5178)
const ROOT = resolve(fileURLToPath(new URL('../..', import.meta.url)))
const HERMES_HOME = process.env.HERMES_HOME || join(process.env.LOCALAPPDATA || '', 'hermes')
const HERMES_ASSETS = join(HERMES_HOME, 'hermes-agent', 'apps', 'desktop', 'dist', 'assets')

const TYPES = {
  '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8',
  '.json': 'application/json', '.svg': 'image/svg+xml', '.png': 'image/png',
  '.wav': 'audio/wav', '.woff2': 'font/woff2', '.woff': 'font/woff', '.ttf': 'font/ttf'
}

const clients = new Set()

function inside(base, rel) {
  const full = normalize(join(base, rel))
  return full === base || full.startsWith(base + sep) ? full : null
}

async function send(res, file) {
  try {
    const s = await stat(file)
    if (!s.isFile()) throw new Error('not a file')
    res.writeHead(200, { 'content-type': TYPES[extname(file)] || 'application/octet-stream', 'cache-control': 'no-store' })
    res.end(await readFile(file))
  } catch {
    console.log(`404 ${file}`)
    res.writeHead(404, { 'content-type': 'text/plain' }).end('not found')
  }
}

async function mainCss() {
  const names = await readdir(HERMES_ASSETS).catch(() => [])
  return names.filter(n => n.endsWith('.css'))
}

createServer(async (req, res) => {
  const url = new URL(req.url, 'http://x')
  const p = decodeURIComponent(url.pathname)

  if (p === '/__reload') {
    res.writeHead(200, { 'content-type': 'text/event-stream', 'cache-control': 'no-store', connection: 'keep-alive' })
    res.write(': hi\n\n')
    clients.add(res)
    req.on('close', () => clients.delete(res))
    return
  }
  if (p === '/hermes/styles.json') {
    res.writeHead(200, { 'content-type': 'application/json', 'cache-control': 'no-store' })
    return res.end(JSON.stringify(await mainCss()))
  }
  if (p.startsWith('/hermes/assets/')) {
    const f = inside(HERMES_ASSETS, p.slice('/hermes/assets/'.length))
    return f ? send(res, f) : res.writeHead(403).end()
  }
  if (p === '/' || p === '/index.html') return send(res, join(ROOT, 'dev', 'preview', 'index.html'))

  const f = inside(ROOT, p.slice(1))
  // Never serve dotfiles (.env, .git, .crew) from the repo.
  if (!f || p.split('/').some(seg => seg.startsWith('.'))) return res.writeHead(403).end()
  return send(res, f)
}).listen(PORT, '127.0.0.1', () => {
  console.log(`rookery preview → http://127.0.0.1:${PORT}`)
  console.log(`hermes styles   → ${HERMES_ASSETS}`)
})

let timer = null
for (const dir of ['desktop', join('dev', 'preview')]) {
  try {
    watch(join(ROOT, dir), { recursive: true }, () => {
      clearTimeout(timer)
      timer = setTimeout(() => { for (const c of clients) c.write('data: reload\n\n') }, 80)
    })
  } catch { /* dir not there yet */ }
}
