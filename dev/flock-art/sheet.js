// Rig sheet: the hero wire (a full Parliament singing over a fake 90 BPM loop)
// and the cast grid. Dev only, for judging the art and motion.
import { createElement as h, useEffect, useRef, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { Bird, BIRD_CSS, CAST, CAST_BY_ID } from './birds-art.js'

const BPM = 90, STEP = 60 / BPM / 4, BARS = 4, LOOP = BARS * 16 * STEP
// Fake note patterns per role (16th steps within a bar: [onset, length, velocity]).
// Only for judging the beaks; real events come from the render.
const PATTERNS = {
  bass: [[0, 3, 1], [6, 2, 0.8], [10, 4, 0.9]],
  keys: [[0, 6, 0.8], [8, 6, 0.7]],
  pad: [[0, 16, 0.55]],
  lead: [[0, 2, 1], [3, 1, 0.7], [6, 2, 0.9], [8, 1, 0.6], [10, 2, 0.9], [13, 2, 0.8]],
  arp: [[0, 1, 0.8], [2, 1, 0.6], [4, 1, 0.8], [6, 1, 0.6], [8, 1, 0.8], [10, 1, 0.6], [12, 1, 0.8], [14, 1, 0.6]],
  call: [[4, 4, 1], [12, 3, 0.9]],
  crown: [[0, 2, 0.6], [8, 2, 0.6]]
}
const KICKS = [0, 10] // steps per bar (boom bap)

function beakAt(role, t) {
  const bar = Math.floor(t / (16 * STEP)), inBar = t - bar * 16 * STEP
  if (role === 'call' && bar % 2 === 0) return 0 // the singer answers on bars 2 and 4
  let v = 0
  for (const [on, len, vel] of PATTERNS[role] || []) {
    const a = on * STEP, b = (on + len) * STEP
    if (inBar >= a && inBar < b) v = Math.max(v, vel * (1 - 0.55 * Math.min(1, (inBar - a) / (b - a || 1))) * Math.min(1, (inBar - a) / 0.03))
    else if (inBar >= b && inBar < b + 0.06) v = Math.max(v, vel * 0.45 * (1 - (inBar - b) / 0.06))
  }
  return v
}

const CSS = BIRD_CSS + `
.rs{max-width:1240px;margin:0 auto;padding:28px 28px 64px;display:flex;flex-direction:column;gap:28px}
.rs-head{display:flex;align-items:flex-end;gap:16px;flex-wrap:wrap}
.rs-head h1{margin:0;font-size:20px;font-weight:650;letter-spacing:-.01em}
.rs-head p{margin:0;color:var(--ui-text-tertiary);max-width:620px;line-height:1.5}
.rs-bar{margin-left:auto;display:flex;gap:8px;flex-wrap:wrap}
.rs-bar button{font:inherit;font-size:12.5px;padding:7px 12px;border-radius:8px;border:0;background:var(--ui-bg-quaternary);color:var(--ui-text-primary);cursor:pointer}
.rs-bar button:hover{background:var(--ui-control-hover-background)}
.rs-bar button[aria-pressed="true"]{background:var(--ui-accent);color:var(--dt-primary-foreground)}
.stage{position:relative;height:300px;border-radius:16px;overflow:hidden;
  background:
    radial-gradient(120% 90% at 50% 125%, color-mix(in srgb,var(--ui-accent) 13%,transparent), transparent 62%),
    radial-gradient(60% 50% at 82% 8%, color-mix(in srgb,var(--ui-text-primary) 5%,transparent), transparent 70%),
    color-mix(in srgb,var(--ui-base) 2.5%,transparent)}
.stage-wire{position:absolute;inset:0;width:100%;height:100%;pointer-events:none}
.stage-wire path{fill:none;stroke:color-mix(in srgb,var(--ui-text-primary) 46%,transparent);stroke-width:1.6}
.stage-wire .post{stroke:color-mix(in srgb,var(--ui-text-primary) 30%,transparent);stroke-width:5;stroke-linecap:round}
.perch{position:absolute;transform:translate(-50%,-100%)}
.perch .tag{position:absolute;left:50%;top:calc(100% + 22px);transform:translateX(-50%);white-space:nowrap;font-size:11px;color:var(--ui-text-quaternary);text-align:center;line-height:1.35}
.perch .tag b{display:block;color:var(--ui-text-secondary);font-weight:600;font-size:12px}
.stars i{position:absolute;width:2px;height:2px;border-radius:50%;background:var(--ui-text-primary);opacity:.18}
.cast{display:grid;grid-template-columns:repeat(auto-fill,minmax(176px,1fr));gap:14px}
.card{position:relative;display:flex;flex-direction:column;align-items:center;gap:8px;padding:18px 14px 14px;border-radius:14px;background:color-mix(in srgb,var(--ui-base) 3%,transparent)}
.card:hover{background:color-mix(in srgb,var(--ui-base) 5%,transparent)}
.card .ground{width:70%;height:1.5px;border-radius:2px;background:color-mix(in srgb,var(--ui-text-primary) 30%,transparent);margin-top:-9px}
.card h3{margin:4px 0 0;font-size:13.5px;font-weight:650}
.card .meta{display:flex;gap:6px;align-items:center;font-size:11px;color:var(--ui-text-quaternary)}
.card .chip{padding:1px 7px;border-radius:999px;font-size:10.5px;color:var(--ui-text-secondary);background:var(--ui-bg-quaternary)}
.card .dot{width:7px;height:7px;border-radius:50%;background:var(--c)}
.card p{margin:0;text-align:center;color:var(--ui-text-tertiary);font-size:11.5px;line-height:1.45;min-height:34px}
.card[data-secret="true"]{background:none;box-shadow:inset 0 0 0 1px dashed}
.card[data-secret="true"]{outline:1px dashed color-mix(in srgb,var(--ui-text-primary) 22%,transparent);outline-offset:-1px}
.legend{color:var(--ui-text-quaternary);font-size:11.5px}
.closeups{display:flex;gap:24px;flex-wrap:wrap}
.cu{padding:20px 24px 14px;border-radius:14px;background:color-mix(in srgb,var(--ui-base) 3%,transparent)}
.cu .fkb{--beak:inherit}
`

const PARLIAMENT = ['bramble', 'quill', 'hush', 'jinx', 'tick', 'echo']

function Stage({ singing, states, landKey, landing, onBird }) {
  const box = useRef(null), wire = useRef(null), birds = useRef({})
  const [w, setW] = useState(1180)
  useEffect(() => {
    const ro = new ResizeObserver(() => setW(box.current.clientWidth))
    ro.observe(box.current)
    return () => ro.disconnect()
  }, [])
  const H = 300, Y0 = 172, SAG = 16, pad = 40
  const xs = PARLIAMENT.map((_, i) => pad + 70 + (i * (w - 2 * pad - 140)) / (PARLIAMENT.length - 1))
  const yAt = x => Y0 + SAG * (1 - Math.pow((2 * (x - pad)) / (w - 2 * pad) - 1, 2))
  const pathFor = amp => {
    let d = ''
    for (let x = pad; x <= w - pad; x += 8) {
      const u = (x - pad) / (w - 2 * pad)
      d += (d ? ' L' : 'M') + x.toFixed(1) + ' ' + (yAt(x) + amp * Math.sin(u * Math.PI)).toFixed(2)
    }
    return d
  }
  useEffect(() => {
    let raf = 0
    const t0 = performance.now()
    const tick = () => {
      const t = ((performance.now() - t0) / 1000) % LOOP
      // wire vibration from kick onsets (damped sine)
      let amp = 0
      if (singing) {
        const bar = Math.floor(t / (16 * STEP)), inBar = t - bar * 16 * STEP
        for (const k of KICKS) { const dt = inBar - k * STEP; if (dt >= 0 && dt < 0.5) amp += 2.2 * Math.exp(-dt * 9) * Math.sin(dt * 60) }
      }
      if (wire.current) wire.current.setAttribute('d', pathFor(amp))
      for (const id of PARLIAMENT) {
        const el = birds.current[id]
        if (!el) continue
        const st = states[id] || 'idle'
        el.style.setProperty('--beak', singing && st === 'singing' ? beakAt(CAST_BY_ID[id].role, t).toFixed(3) : '0')
      }
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [singing, states, w])
  return h('div', { className: 'stage', ref: box },
    h('div', { className: 'stars', 'aria-hidden': true },
      Array.from({ length: 26 }, (_, i) => h('i', { key: i, style: { left: `${(i * 37.7) % 100}%`, top: `${(i * 53.3) % 46}%`, opacity: 0.08 + ((i * 7) % 10) / 60 } }))),
    h('svg', { className: 'stage-wire', viewBox: `0 0 ${w} ${H}`, preserveAspectRatio: 'none', 'aria-hidden': true },
      h('line', { className: 'post', x1: pad, y1: Y0 - 6, x2: pad, y2: H }),
      h('line', { className: 'post', x1: w - pad, y1: Y0 - 6, x2: w - pad, y2: H }),
      h('path', { ref: wire, d: pathFor(0) })),
    PARLIAMENT.map((id, i) => {
      const b = CAST_BY_ID[id], x = xs[i], y = yAt(x) + 104 / 32
      return h('div', { key: id + ':' + landKey, className: 'perch', style: { left: x, top: y } },
        h('div', { ref: el => { if (el) birds.current[id] = el.firstChild }, style: { '--land-delay': `${i * 250}ms` } },
          h(Bird, { id, size: 104, bpm: BPM, state: states[id] || 'idle', anim: landing ? 'land' : null, onClick: () => onBird(id) })),
        h('div', { className: 'tag' }, h('b', null, b.name), `${b.role} · ${(states[id] || 'idle')}`))
    })
  )
}

function App() {
  const [singing, setSinging] = useState(true)
  const [states, setStates] = useState(Object.fromEntries(PARLIAMENT.map(id => [id, 'singing'])))
  const [landKey, setLandKey] = useState(0)
  const [solo, setSolo] = useState(null)
  const cycle = id => setStates(s => ({ ...s, [id]: s[id] === 'singing' ? 'muted' : s[id] === 'muted' ? 'idle' : 'singing' }))
  const shown = solo ? Object.fromEntries(PARLIAMENT.map(id => [id, id === solo ? 'singing' : 'dim'])) : states
  // Land the birds one by one, 250 ms apart, in role order (the agent-picks moment).
  const [landing, setLanding] = useState(false)
  const timer = useRef(0)
  const land = () => { setLandKey(k => k + 1); setLanding(true); clearTimeout(timer.current); timer.current = setTimeout(() => setLanding(false), 250 * PARLIAMENT.length + 800) }
  return h('div', { className: 'rs' },
    h('style', null, CSS),
    h('div', { className: 'rs-head' },
      h('div', null,
        h('h1', null, 'The Flock: rig sheet'),
        h('p', null, 'A full Parliament on the wire, singing over a fake 90 BPM loop. Beaks open on each note, the wire shivers on the kicks. Click a bird to cycle singing → muted → idle.')),
      h('div', { className: 'rs-bar' },
        h('button', { onClick: land }, 'Land them'),
        h('button', { 'aria-pressed': singing, onClick: () => setSinging(s => !s) }, singing ? 'Stop singing' : 'Sing'),
        h('button', { 'aria-pressed': !!solo, onClick: () => setSolo(s => (s ? null : 'quill')) }, solo ? 'Unsolo' : 'Solo Quill'),
        )),
    h(Stage, { singing, states: shown, landKey, landing, onBird: cycle }),
    h('div', { className: 'legend' }, 'Close-ups · 240 px. Glint mid-caw (beak driven by --beak), Hush dozing, Corvus with the crown.'),
    h('div', { className: 'closeups' },
      h('div', { className: 'cu', style: { '--beak': 1 } }, h(Bird, { id: 'glint', size: 240, state: 'idle' })),
      h('div', { className: 'cu' }, h(Bird, { id: 'hush', size: 240, state: 'idle' })),
      h('div', { className: 'cu' }, h(Bird, { id: 'corvus', size: 240, state: 'idle' }))),
    h('div', { className: 'legend' }, 'The cast · twelve voices and a secret.'),
    h('div', { className: 'cast' }, CAST.map(b => h('div', { key: b.id, className: 'card', 'data-secret': !!b.secret },
      h(Bird, { id: b.id, size: 112, bpm: BPM, state: 'idle' }),
      h('div', { className: 'ground' }),
      h('h3', null, b.name),
      h('div', { className: 'meta' }, h('span', { className: 'dot', style: { '--c': b.accent } }), b.species, h('span', { className: 'chip' }, b.role)),
      h('p', null, b.persona))))
  )
}

createRoot(document.getElementById('app')).render(h(App))
