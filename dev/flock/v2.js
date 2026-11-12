// Demo app for the shipping FlockPanel: Luna's verified synth renders the loop,
// Web Audio plays it gaplessly, new renders swap in at the next bar line.
import { createElement as h, useEffect, useMemo, useRef, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { birds, combos, corvus, templates } from './birds.js'
import { defaultBoomBapProject, renderFlock } from './flock-synth.js'
import { FlockPanel } from './panel.js'

const catalog = { birds, combos, corvus, templates }
const EMPTY = { key: 'D', scale: 'dorian', progression: ['i', 'iv', 'VII', 'III'], weather: 'dust', perches: Array(6).fill(null), seen: [], unlocked: [], templateId: '' }
const ROLE_ORDER = ['bass', 'keys', 'pad', 'lead', 'arp', 'call']

class Player {
  constructor() { this.ac = null; this.src = null; this.gain = null; this.buf = null; this.t0 = 0; this.playing = false; this.bar = 1 }
  ctx() { if (!this.ac) this.ac = new AudioContext(); return this.ac }
  toBuffer(r) {
    const b = this.ctx().createBuffer(2, r.duration_samples, r.sample_rate)
    b.copyToChannel(r.left, 0); b.copyToChannel(r.right, 1)
    return b
  }
  position() { return this.playing && this.buf ? (this.ctx().currentTime - this.t0) % this.buf.duration : -1 }
  start(buf, offset, when) {
    const ac = this.ctx(), src = ac.createBufferSource(), g = ac.createGain()
    src.buffer = buf; src.loop = true; src.connect(g).connect(ac.destination)
    g.gain.setValueAtTime(0, when); g.gain.linearRampToValueAtTime(1, when + 0.012)
    src.start(when, offset)
    return { src, g }
  }
  // Swap a fresh render in at the next bar line, with a 12 ms crossfade.
  swap(r) {
    const buf = this.toBuffer(r)
    if (!this.playing) { this.buf = buf; return }
    const ac = this.ctx(), pos = this.position(), bar = this.bar
    const nextBar = Math.ceil((pos + 0.02) / bar) * bar
    const when = ac.currentTime + (nextBar - pos)
    const old = { src: this.src, g: this.gain }
    old.g.gain.setValueAtTime(1, when); old.g.gain.linearRampToValueAtTime(0, when + 0.012)
    old.src.stop(when + 0.02)
    const n = this.start(buf, nextBar % buf.duration, when)
    this.src = n.src; this.gain = n.g; this.buf = buf
    this.t0 = when - (nextBar % buf.duration)
  }
  async play() {
    if (!this.buf) return
    const ac = this.ctx(); if (ac.state === 'suspended') await ac.resume()
    const when = ac.currentTime + 0.02, n = this.start(this.buf, 0, when)
    this.src = n.src; this.gain = n.g; this.t0 = when; this.playing = true
  }
  stop() { try { this.src?.stop() } catch {} this.playing = false }
}

const CSS = `
.v2{max-width:1240px;margin:0 auto;padding:22px 26px 40px;display:flex;flex-direction:column;gap:16px}
.v2-bar{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.v2-bar h1{font-size:16px;margin:0 12px 0 0;font-weight:650}
.v2-bar button{font:inherit;font-size:12.5px;padding:7px 12px;border-radius:8px;border:0;background:var(--ui-bg-quaternary);color:var(--ui-text-primary);cursor:pointer}
.v2-bar button:hover{background:var(--ui-control-hover-background)}
.v2-bar button[data-primary="true"]{background:var(--ui-accent);color:var(--dt-primary-foreground)}
.v2-bar span{margin-left:auto;font-size:11.5px;color:var(--ui-text-quaternary)}
.v2-note{font-size:11.5px;color:var(--ui-text-quaternary)}
`

function App() {
  const [flock, setFlock] = useState(EMPTY)
  const [render, setRender] = useState(null)
  const [playing, setPlaying] = useState(false)
  const [status, setStatus] = useState('')
  const player = useMemo(() => new Player(), [])
  const project = defaultBoomBapProject
  player.bar = (4 * 60) / project.bpm
  const job = useRef(0)

  // re-render the loop whenever the flock changes (debounced), swap at the bar line
  useEffect(() => {
    const id = ++job.current
    const t = setTimeout(async () => {
      const t0 = performance.now()
      const r = await renderFlock(project, flock)
      if (id !== job.current) return
      player.swap(r)
      setRender(r)
      setStatus(`rendered in ${Math.round(performance.now() - t0)} ms · peak ${r.master?.peak_db?.toFixed?.(1) ?? '?'} dB`)
      const found = new Set(flock.unlocked || [])
      const fresh = (r.active_combos || []).filter(c => !found.has(c))
      if (fresh.length) setFlock(f => ({ ...f, unlocked: [...new Set([...(f.unlocked || []), ...fresh])] }))
    }, 120)
    return () => clearTimeout(t)
  }, [JSON.stringify({ ...flock, unlocked: undefined, seen: undefined })])

  const onChange = (next, meta) => { if (meta?.action !== 'wireTap') setFlock(next); else setStatus('♪ the wire twangs') }

  // "Agent picks": birds land one by one, in role order, 250 ms apart
  const agentPicks = id => {
    const t = templates.find(x => x.id === id) || templates[0]
    const order = [...t.birds].sort((a, b) => ROLE_ORDER.indexOf(birds.find(x => x.id === a.bird)?.role) - ROLE_ORDER.indexOf(birds.find(x => x.id === b.bird)?.role))
    setFlock(f => ({ ...f, key: t.key, scale: t.scale, progression: [...t.progression], weather: t.weather, templateId: t.id, perches: Array(6).fill(null) }))
    order.forEach((e, i) => setTimeout(() => setFlock(f => {
      const perches = [...f.perches]; perches[i] = { ...e, mute: false, solo: false }
      return { ...f, perches, seen: [...new Set([...(f.seen || []), e.bird])] }
    }), 300 + i * 250))
  }

  const toggle = async () => {
    if (player.playing) { player.stop(); setPlaying(false) } else { await player.play(); setPlaying(true) }
  }

  return h('div', { className: 'v2' },
    h('style', null, CSS),
    h('div', { className: 'v2-bar' },
      h('h1', null, 'The Flock'),
      h('button', { 'data-primary': true, onClick: () => agentPicks('dusty_boom_bap') }, 'Hermes picks: Dusty Boom Bap'),
      h('button', { onClick: () => agentPicks('trap_night') }, 'Trap Night'),
      h('button', { onClick: () => agentPicks('lo_fi_study') }, 'Lo-Fi Study'),
      h('button', { onClick: toggle }, playing ? '■ Stop' : '▶ Play'),
      h('button', { onClick: () => setFlock(EMPTY) }, 'Reset'),
      h('span', null, status)),
    h(FlockPanel, { catalog, flock, render, playing, getPosition: () => player.position(), onChange, bpm: project.bpm }),
    h('div', { className: 'v2-note' }, 'Click a bird to change its song · hover for mute / solo / send home · roster cards perch and unperch · Tap the wire four times in time.'))
}

createRoot(document.getElementById('app')).render(h(App))
