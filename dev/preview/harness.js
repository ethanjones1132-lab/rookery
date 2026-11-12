// Fake Hermes Desktop chrome around the real desktop/plugin.js.
// Sidebar = SIDEBAR_NAV_AREA rows, main = ROUTES_AREA page, right = a scripted
// "agent" that edits through the same backend + event path the gateway uses.
import * as React from 'react'
import { createRoot } from 'react-dom/client'
import { jsx, jsxs } from 'react/jsx-runtime'
import { __harness, useValue, ROUTES_AREA, SIDEBAR_NAV_AREA, TOOL_MEDIA_RENDERER_AREA } from '@hermes/plugin-sdk'
import { createMockBackend } from './mock-backend.js'
import { synthLoop } from './mock-audio.js'
import { renderFlock } from '../flock/flock-synth.js'
import { SCENES } from './agent-script.js'
import plugin from '/desktop/plugin.js'

const backend = createMockBackend({ emit: __harness.emit, synth: async project => {
  const audio = await synthLoop(project)
  const flock = await renderFlock(project, project.flock || {
    key: 'D', scale: 'dorian', progression: ['i', 'iv', 'VII', 'III'], weather: 'clear',
    perches: Array(6).fill(null), seen: [], unlocked: []
  })
  return { ...audio, flock_events: flock.events, kick_onsets: flock.kick_onsets, flock_active_combos: flock.active_combos }
} })
__harness.setBackend(backend)
plugin.register(__harness.createContext(plugin.id))

// ── mock gateway: the in-page chat talks to this exactly as it talks to Hermes ──
// prompt.submit picks a scripted scene, then streams real-shaped events:
// message.start → tool.start/complete per call → message.delta words → message.complete.
const SID = 'rk-preview'
const pause = ms => new Promise(r => setTimeout(r, ms))
// Kept across reloads, like the real session store, so resume repaints history.
const history = JSON.parse(sessionStorage.getItem('rk-preview-history') || '[]')
const keep = () => { try { sessionStorage.setItem('rk-preview-history', JSON.stringify(history)) } catch {} }
let turnToken = 0, built = false
function pickScene(text) {
  const t = text.toLowerCase()
  const by = id => SCENES.find(s => s.id === id)
  if (/flock|birds|melodic/.test(t)) return by('add-the-flock')
  if (/undo/.test(t)) return by('undo-swing')
  if (/what changed|changed\?/.test(t)) return by('what-changed')
  if (/corvus|warm|master/.test(t)) return by('corvus-warm')
  if (/same prompt|new project|again/.test(t)) return by('same-prompt-new-project')
  if (/snare|swing|harder|dust|fill|hat|808|half/.test(t) && built) return by('snare-and-swing')
  return by('build-boom-bap')
}
async function runPrompt(raw) {
  const token = ++turnToken
  const live = () => token === turnToken
  const emit = (type, payload) => { if (live()) __harness.emitGateway(type, SID, payload) }
  const text = raw.replace(/^\[Rookery: [^\]]+\]\n?/, '')
  history.push({ role: 'user', text: raw })
  const scene = pickScene(text)
  if (scene.id === 'build-boom-bap' || scene.id === 'add-the-flock') built = true
  emit('message.start', {})
  await pause(650)
  let openTool = null, n = 0
  const closeTool = () => { if (openTool) { emit('tool.complete', { tool_id: openTool }); openTool = null } }
  let reply = ''
  const say = async (msg, kind) => {
    if (!live()) throw new Error('interrupted')
    if (kind === 'tool') {
      closeTool()
      const name = msg.split('(')[0]
      openTool = `t${++n}`
      emit('tool.start', { tool_id: openTool, name, context: msg.slice(name.length + 1, -1) })
      history.push({ role: 'tool', name, context: msg.slice(name.length + 1, -1) })
      return
    }
    closeTool()
    reply += (reply ? '\n\n' : '') + msg
    for (const w of msg.split(/(\s+)/)) { emit('message.delta', { text: w }); await pause(18) }
  }
  try {
    await scene.run({ ...backend }, (msg, kind = 'agent') => { pendingSay = pendingSay.then(() => say(msg, kind)).catch(() => {}); return pendingSay })
    await pendingSay
    closeTool()
    history.push({ role: 'assistant', text: reply }); keep()
    emit('message.complete', { text: reply, status: 'complete' })
  } catch (e) {
    if (live()) emit('message.complete', { text: `Error: ${e?.message || e}`, status: 'error' })
  } finally { pendingSay = Promise.resolve() }
}
let pendingSay = Promise.resolve()
__harness.setGateway(async (method, params) => {
  await pause(50)
  switch (method) {
    case 'session.create': return { session_id: SID, stored_session_id: `stored-${SID}` }
    case 'model.options': return { providers: [
      { slug: 'openrouter', name: 'OpenRouter', models: ['deepseek/deepseek-v4.1-flash-1017', 'deepseek/deepseek-v4-flash-0731', 'anthropic/claude-sonnet-5-5', 'openai/gpt-6-luna'],
        pricing: { 'deepseek/deepseek-v4.1-flash-1017': { input: '$0.14', output: '$0.28' }, 'anthropic/claude-sonnet-5-5': { input: '$3.00', output: '$15.00' } } },
      { slug: 'opencode-go', name: 'OpenCode Go', models: ['step-5-preview-free', 'glm-5.1'], pricing: { 'step-5-preview-free': { free: true } } },
      { slug: 'nvidia-nim', name: 'NVIDIA NIM', models: ['deepseek-ai/deepseek-v4.1-flash'] }
    ] }
    case 'session.resume': return { session_id: SID, messages: history }
    case 'prompt.submit': runPrompt(String(params.text || '')); return { accepted: true }
    case 'session.interrupt': {
      turnToken++
      __harness.emitGateway('message.complete', SID, { text: '', status: 'interrupted' })
      return { ok: true }
    }
  }
  throw new Error(`preview gateway: ${method} is not mocked`)
})

// Builds the rookery_render tool result the way contract §4b specifies, so the
// plugin's TOOL_MEDIA_RENDERER_AREA card can be previewed in the fake transcript.
async function renderResult(name, rendered) {
  const { project } = await backend.handle('GET', `/project/${encodeURIComponent(name)}`)
  return {
    name, rev: rendered.rev, hash: rendered.hash, path: `renders/${rendered.hash}.wav`,
    bpm: project.bpm, bars: project.bars, swing: project.swing, duration_samples: rendered.duration_samples,
    report: rendered.report,
    meters: rendered.meters, mix: rendered.mix,
    tracks: project.tracks.map(t => ({ id: t.id, steps: t.steps, velocity: t.velocity, mute: t.mute }))
  }
}

function ToolCard({ result, audioUrl }) {
  const items = useValue(__harness.registry)
  const card = items.find(c => c.area === TOOL_MEDIA_RENDERER_AREA && c.data?.tools?.includes('rookery_render'))
  const fallback = jsx('audio', { controls: true, src: audioUrl, style: { width: '100%' } })
  if (!card) return fallback
  const file = { path: result.path, name: `${result.name}.wav`, kind: 'audio', mime: 'audio/wav', resolveUrl: async () => audioUrl }
  return card.data.render({ file, args: { name: result.name }, result: JSON.stringify(result), toolName: 'rookery_render', toolCallId: result.hash, sessionId: 'preview-session', fallback })
}

function Chat() {
  const [log, setLog] = React.useState([])
  const [busy, setBusy] = React.useState(false)
  const push = m => setLog(l => [...l, m])
  // the scripted agent's backend, with renders echoed into the transcript as tool cards
  const api = React.useMemo(() => ({
    ...backend,
    async handle(method, path, body) {
      const r = await backend.handle(method, path, body)
      if (method === 'POST' && path === '/render') push({ who: 'card', result: await renderResult(body.name, r), audioUrl: r.audio_url })
      return r
    }
  }), [])
  async function play(scene) {
    setBusy(true)
    push({ who: 'user', text: scene.user })
    try {
      await scene.run(api, (text, kind = 'agent') => push({ who: kind, text }))
    } catch (error) {
      push({ who: 'agent', text: `Preview error: ${error?.message || error}` })
    } finally {
      setBusy(false)
    }
  }
  return jsxs('aside', {
    className: 'hx-chat',
    children: [
      jsx('div', { className: 'hx-chat-log', children: log.map((m, i) => m.who === 'card'
        ? jsx('div', { className: 'hx-card', children: jsx(ToolCard, { result: m.result, audioUrl: m.audioUrl }) }, i)
        : jsx('div', { className: `hx-msg ${m.who}`, children: m.text }, i)) }),
      jsxs('div', {
        className: 'hx-chat-bar',
        children: [
          jsx('div', { className: 'hx-tag', children: 'Preview · scripted agent' }),
          ...SCENES.map(scene => jsx('button', {
            className: 'hx-btn', disabled: busy, onClick: () => play(scene), children: `\u{25B6}  ${scene.label}`
          }, scene.id)),
          jsx('button', { className: 'hx-btn', disabled: busy, onClick: () => location.reload(), children: '↻  Reset' })
        ]
      })
    ]
  })
}
function Shell() {
  const items = useValue(__harness.registry)
  const path = useValue(__harness.route)
  const navs = items.filter(c => c.area === SIDEBAR_NAV_AREA)
  const page = items.find(c => c.area === ROUTES_AREA && c.data?.path === path)
  return jsxs('div', {
    className: 'hx-shell',
    children: [
      jsxs('nav', {
        className: 'hx-side',
        children: [
          jsx('div', { className: 'hx-brand', children: 'Hermes' }),
          ...navs.map(n => jsxs('div', {
            className: 'hx-nav', 'aria-current': n.data.path === path ? 'page' : undefined,
            onClick: () => __harness.route.set(n.data.path),
            children: [jsx('span', { className: `codicon codicon-${n.data.codicon}` }), n.data.label]
          }, n.id))
        ]
      }),
      jsx('main', { className: 'hx-main', children: page ? page.render() : jsx('div', { className: 'hx-err', children: `no route for ${path}` }) }),
      location.search.includes('card') && jsx(Chat, {})
    ]
  })
}

createRoot(document.getElementById('app')).render(jsx(Shell, {}))
