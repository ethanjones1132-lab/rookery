// The Wire: Rookery's melodic layer UI (React, desktop/plugin.js house style).
// Data in, events out: the flock lives in project.json; this component only draws it
// and reports user intent through onChange(nextFlock, meta). Beaks open on rendered
// note events and the wire shivers on rendered kick onsets: the animation tells the truth.
//
//   <FlockPanel catalog flock render playing getPosition onChange bpm />
//     catalog: { birds, corvus, templates, combos }   (dev/flock/birds.js today, GET /flock/catalog later)
//     render:  { events: {birdId: [{t, len, midi, vel}]}, kick_onsets: [t], active_combos: [id] } | null
import { createElement as h, useEffect, useMemo, useRef, useState } from 'react'
import { Bird, BIRD_CSS } from '../flock-art/birds-art.js'

const ROLES = ['bass', 'keys', 'pad', 'lead', 'arp', 'call']
const KEYS = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
const SCALES = ['minor', 'dorian', 'major', 'mixolydian', 'minor_pent', 'phrygian']
const CHORDS = ['i', 'ii', 'III', 'iv', 'v', 'VI', 'VII', 'I', 'IV', 'V', 'vi']
const WEATHER = [['clear', 'Clear'], ['dust', 'Dust'], ['rain', 'Rain'], ['wind', 'Wind']]
const SONGS = ['A', 'B', 'C']
const artId = id => (id === 'wren_not' ? 'wrennot' : id)
const STAGE_H = 236, WIRE_Y = 168, SAG = 14, PAD = 46, BIRD = 92

const scaleFamily = s => (['major', 'mixolydian'].includes(s) ? 'major' : 'minor')
function comboProgress(combo, flock, roleOf) {
  const perched = (flock.perches || []).filter(Boolean)
  const ids = new Set(perched.map(p => p.bird))
  const r = combo.requires || {}
  let missing = 0
  for (const b of r.birds || []) if (!ids.has(b)) missing++
  if (r.roles) {
    const roles = new Set(perched.map(p => roleOf(p.bird)))
    for (const role of r.roles) if (!roles.has(role)) missing++
  }
  if (r.scale_family && scaleFamily(flock.scale) !== r.scale_family) missing++
  if (r.weather && flock.weather !== r.weather) missing++
  return missing
}

// ── styles (tokens only) ──────────────────────────────────────────────────
const CSS = BIRD_CSS + `
.fkp{display:flex;flex-direction:column;gap:12px;color:var(--ui-text-primary);font-variant-numeric:tabular-nums}
.fkp button{font:inherit;color:inherit;background:none;border:0;padding:0;cursor:pointer}
.fkp button:focus-visible,.fkp select:focus-visible{outline:2px solid var(--ui-accent);outline-offset:2px;border-radius:6px}
.fkp-head{display:flex;align-items:center;gap:14px;flex-wrap:wrap;min-height:30px}
.fkp-title{font-size:13px;font-weight:650;letter-spacing:.01em;display:flex;align-items:center;gap:8px}
.fkp-title i{width:7px;height:7px;background:var(--ui-accent);box-shadow:0 0 8px var(--ui-accent)}
.fkp-ctl{display:flex;align-items:center;gap:6px;font-size:11px;color:var(--ui-text-quaternary);text-transform:uppercase;letter-spacing:.06em}
.fkp-sel{appearance:none;font:inherit;font-size:12px;text-transform:none;letter-spacing:0;color:var(--ui-text-primary);background:var(--ui-bg-quaternary);border:0;border-radius:6px;padding:4px 22px 4px 8px;cursor:pointer;
  background-image:linear-gradient(45deg,transparent 50%,var(--ui-text-tertiary) 50%),linear-gradient(135deg,var(--ui-text-tertiary) 50%,transparent 50%);
  background-position:calc(100% - 11px) 52%,calc(100% - 7px) 52%;background-size:4px 4px;background-repeat:no-repeat}
.fkp-sel:hover{background-color:var(--ui-control-hover-background)}
.fkp-sel option{background:var(--ui-bg-elevated);color:var(--ui-text-primary)}
.fkp-chips{display:flex;gap:2px;background:var(--ui-bg-quaternary);border-radius:6px;padding:2px}
.fkp-chips button{font-size:12px;text-transform:none;letter-spacing:0;padding:2px 8px;border-radius:4px;color:var(--ui-text-secondary)}
.fkp-chips button:hover{background:var(--ui-control-hover-background)}
.fkp-chips button[aria-pressed="true"]{background:var(--ui-bg-editor);color:var(--ui-text-primary);box-shadow:0 0 0 1px var(--ui-stroke-tertiary)}
.fkp-meter{margin-left:auto;display:flex;align-items:center;gap:8px;font-size:11px;color:var(--ui-text-quaternary);text-transform:uppercase;letter-spacing:.06em;position:relative}
.fkp-dots{display:flex;gap:5px}
.fkp-dot{width:8px;height:8px;background:var(--ui-bg-tertiary);box-shadow:inset 0 0 0 1px var(--ui-stroke-secondary)}
.fkp-dot[data-found="true"]{background:var(--ui-accent);box-shadow:0 0 6px var(--ui-accent)}
.fkp-dot[data-near="true"]{animation:fkp-near 1.1s steps(2) infinite}
.fkp-hint{position:absolute;right:0;top:calc(100% + 8px);z-index:20;width:280px;padding:10px 12px;border-radius:8px;background:var(--ui-bg-elevated);box-shadow:var(--shadow-nous,none);border:1px solid var(--stroke-nous,var(--ui-stroke-tertiary));text-transform:none;letter-spacing:0;color:var(--ui-text-secondary);font-size:12px;line-height:1.45}
.fkp-hint b{display:block;color:var(--ui-text-primary);font-weight:600;margin-bottom:2px}

.fkp-stage{position:relative;height:${STAGE_H}px;border-radius:12px;overflow:hidden;isolation:isolate;
  background:linear-gradient(180deg,color-mix(in srgb,var(--ui-accent) 7%,var(--ui-bg-editor)) 0%,var(--ui-bg-editor) 78%),var(--ui-bg-editor)}
.fkp-stage[data-combo="night_shift"]{background:linear-gradient(180deg,color-mix(in srgb,var(--ui-purple) 14%,var(--ui-bg-editor)) 0%,color-mix(in srgb,var(--ui-bg-editor) 92%,var(--ui-text-primary)) 100%)}
.fkp-star{position:absolute;width:2px;height:2px;background:var(--ui-text-primary);opacity:.16}
.fkp-star[data-tw="true"]{animation:fkp-twinkle 3.2s steps(2) infinite}
.fkp-moon{position:absolute;right:56px;top:22px;width:22px;height:22px;background:color-mix(in srgb,var(--ui-text-primary) 80%,transparent);
  clip-path:polygon(30% 0,70% 0,70% 10%,90% 10%,90% 30%,100% 30%,100% 70%,90% 70%,90% 90%,70% 90%,70% 100%,30% 100%,30% 90%,10% 90%,10% 70%,0 70%,0 30%,10% 30%,10% 10%,30% 10%);opacity:0;transition:opacity .6s}
.fkp-stage[data-combo="night_shift"] .fkp-moon{opacity:1}
.fkp-wx{position:absolute;inset:0;pointer-events:none}
.fkp-wx i{position:absolute;background:var(--ui-text-primary)}
.fkp-wx[data-kind="dust"] i{width:2px;height:2px;opacity:.22;animation:fkp-dust 7s steps(14) infinite}
.fkp-wx[data-kind="rain"] i{width:1px;height:7px;opacity:.28;animation:fkp-rain .9s steps(6) infinite}
.fkp-wx[data-kind="wind"] i{width:9px;height:1px;opacity:.18;animation:fkp-wind 2.4s steps(8) infinite}
.fkp-wire{position:absolute;inset:0;width:100%;height:100%;pointer-events:none}
.fkp-wire path{fill:none;stroke:color-mix(in srgb,var(--ui-text-primary) 42%,transparent);stroke-width:1.5}
.fkp-post{fill:color-mix(in srgb,var(--ui-text-primary) 22%,var(--ui-bg-editor))}
.fkp-post-cap{fill:color-mix(in srgb,var(--ui-text-primary) 34%,var(--ui-bg-editor))}
.fkp-tap{position:absolute;left:${PAD}px;right:${PAD}px;top:${WIRE_Y - 10}px;height:22px;cursor:pointer}
.fkp-perch{position:absolute;transform:translate(-50%,-100%);display:flex;flex-direction:column;align-items:center}
.fkp-empty{position:absolute;transform:translate(-50%,-50%);width:26px;height:26px;border-radius:6px;display:grid;place-items:center;color:var(--ui-text-quaternary);font-size:14px;line-height:1;border:1px dashed color-mix(in srgb,var(--ui-text-primary) 18%,transparent)}
.fkp-empty:hover{color:var(--ui-text-secondary);border-color:var(--ui-accent)}
.fkp-tools{position:absolute;left:50%;top:-24px;transform:translateX(-50%);display:flex;gap:3px;align-items:center;opacity:0;transition:opacity .1s;white-space:nowrap}
.fkp-perch:hover .fkp-tools,.fkp-perch:focus-within .fkp-tools,.fkp-tools[data-on="true"]{opacity:1;transition:none}
.fkp-tools button{min-width:20px;height:20px;padding:0 5px;border-radius:4px;font-size:10.5px;font-weight:650;color:var(--ui-text-tertiary);background:var(--ui-bg-quaternary)}
.fkp-tools button:hover{color:var(--ui-text-primary)}
.fkp-tools button[data-k="m"][aria-pressed="true"]{background:color-mix(in srgb,var(--ui-orange) 28%,transparent);color:var(--ui-orange)}
.fkp-tools button[data-k="s"][aria-pressed="true"]{background:color-mix(in srgb,var(--ui-yellow) 28%,transparent);color:var(--ui-yellow)}
.fkp-tools .fkp-x{color:var(--ui-text-quaternary)}
.fkp-name{position:absolute;left:50%;top:calc(100% + 9px);transform:translateX(-50%);font-size:11px;color:var(--ui-text-quaternary);white-space:nowrap}
.fkp-name b{color:var(--ui-text-secondary);font-weight:600}
.fkp-badge{position:absolute;left:58%;top:-6px;font-size:10px;font-weight:700;padding:1px 5px;border-radius:4px;background:var(--ui-bg-elevated);color:var(--ui-text-secondary);box-shadow:0 0 0 1px var(--ui-stroke-tertiary);animation:fkp-pop .9s steps(3) both}
.fkp-banner{position:absolute;left:50%;top:16px;transform:translateX(-50%);z-index:5;display:flex;flex-direction:column;align-items:center;gap:2px;padding:7px 14px;border-radius:8px;
  background:color-mix(in srgb,var(--ui-bg-elevated) 88%,transparent);box-shadow:0 0 0 1px color-mix(in srgb,var(--ui-accent) 40%,transparent),0 0 24px color-mix(in srgb,var(--ui-accent) 25%,transparent);animation:fkp-banner 3.2s steps(1) both}
.fkp-banner b{font-size:13px;letter-spacing:.04em;text-transform:uppercase;color:var(--ui-accent)}
.fkp-banner span{font-size:11.5px;color:var(--ui-text-secondary)}
.fkp-swarm{position:absolute;inset:0;pointer-events:none;z-index:4}
.fkp-swarm i{position:absolute;left:50%;top:60%;width:4px;height:3px;background:var(--ui-text-primary);opacity:0;animation:fkp-swarm 2.6s steps(16) both;animation-delay:calc(var(--i) * 18ms)}
.fkp-swarm i:nth-child(3n){background:var(--ui-accent)}

.fkp-roster{display:flex;flex-wrap:wrap;gap:6px}
.fkp-card{display:flex;align-items:center;gap:8px;padding:5px 10px 5px 4px;border-radius:9px;background:color-mix(in srgb,var(--ui-base) 3.5%,transparent);min-width:128px;text-align:left;position:relative}
.fkp-card:hover{background:color-mix(in srgb,var(--ui-base) 6%,transparent)}
.fkp-card[data-on="true"]{box-shadow:inset 0 0 0 1px color-mix(in srgb,var(--ui-accent) 55%,transparent);background:color-mix(in srgb,var(--ui-accent) 8%,transparent)}
.fkp-card .fkp-pic{width:46px;height:42px;overflow:hidden;display:flex;align-items:flex-start;justify-content:center}
.fkp-card .fkp-pic .fkb{pointer-events:none;margin-top:-4px}
.fkp-card b{display:block;font-size:12px;font-weight:600}
.fkp-card span{display:block;font-size:10.5px;color:var(--ui-text-quaternary);text-transform:uppercase;letter-spacing:.05em}
.fkp-card[data-new="true"]::after{content:'';position:absolute;right:6px;top:6px;width:4px;height:4px;background:var(--ui-accent)}
.fkp-card[data-secret="true"]{border:1px dashed color-mix(in srgb,var(--ui-text-primary) 18%,transparent);background:none;color:var(--ui-text-quaternary);cursor:default}
.fkp-role{width:1px;align-self:stretch;background:var(--ui-stroke-tertiary);margin:2px 3px}

@keyframes fkp-near{50%{background:color-mix(in srgb,var(--ui-accent) 55%,var(--ui-bg-tertiary))}}
@keyframes fkp-twinkle{50%{opacity:.4}}
@keyframes fkp-dust{0%{transform:translate(0,0)}100%{transform:translate(28px,-14px);opacity:0}}
@keyframes fkp-rain{0%{transform:translate(0,-10px)}100%{transform:translate(-6px,${STAGE_H}px)}}
@keyframes fkp-wind{0%{transform:translateX(-30px);opacity:0}30%{opacity:.2}100%{transform:translateX(160px);opacity:0}}
@keyframes fkp-pop{0%{transform:translateY(4px);opacity:0}30%,80%{transform:none;opacity:1}100%{opacity:0}}
@keyframes fkp-banner{0%{opacity:0}6%,88%{opacity:1}100%{opacity:0}}
@keyframes fkp-swarm{0%{opacity:0;transform:translate(0,0)}10%{opacity:.85}
  50%{transform:translate(calc(cos(var(--a)) * var(--r) * 1px),calc(sin(var(--a)) * var(--r) * .45px - 40px))}
  100%{opacity:0;transform:translate(calc(cos(var(--a) + 2rad) * var(--r) * 1.6px),calc(sin(var(--a) + 2rad) * var(--r) * .6px - 90px))}}
@media (prefers-reduced-motion:reduce){.fkp *{animation:none!important}.fkp-swarm{display:none}.fkp-banner{opacity:1}}
`

// ── the stage ─────────────────────────────────────────────────────────────
function useWidth(ref) {
  const [w, setW] = useState(900)
  useEffect(() => {
    if (!ref.current) return
    const ro = new ResizeObserver(() => setW(ref.current.clientWidth))
    ro.observe(ref.current)
    return () => ro.disconnect()
  }, [])
  return w
}

const wirePath = (w, amp) => {
  let d = ''
  for (let x = PAD; x <= w - PAD; x += 6) {
    const u = (x - PAD) / (w - 2 * PAD)
    const y = WIRE_Y + SAG * (1 - Math.pow(2 * u - 1, 2)) + amp * Math.sin(u * Math.PI)
    d += (d ? 'L' : 'M') + x.toFixed(1) + ' ' + y.toFixed(2)
  }
  return d
}
const wireYAt = (x, w) => { const u = (x - PAD) / (w - 2 * PAD); return WIRE_Y + SAG * (1 - Math.pow(2 * u - 1, 2)) }

export function FlockPanel({ catalog, flock, render, playing, getPosition, onChange, bpm = 90 }) {
  const stage = useRef(null), wire = useRef(null), birdEls = useRef({})
  const w = useWidth(stage)
  const [hint, setHint] = useState(null)
  const [banner, setBanner] = useState(null)
  const [badges, setBadges] = useState({}) // slot -> nonce for the song badge
  const [anims, setAnims] = useState({})   // slot -> 'land' | 'leave'
  const prev = useRef(flock.perches)
  const shownCombos = useRef(new Set())
  const taps = useRef([])
  const timers = useRef([])

  const byId = useMemo(() => Object.fromEntries([...catalog.birds, catalog.corvus].map(b => [b.id, b])), [catalog])
  const perches = flock.perches || []
  const corvusUnlocked = (catalog.birds || []).every(b => (flock.seen || []).includes(b.id))
  const slots = corvusUnlocked ? 7 : 6
  const xs = Array.from({ length: slots }, (_, i) => PAD + 64 + (i * (w - 2 * PAD - 128)) / (slots - 1))

  // landing / leaving: diff perches against the previous render
  useEffect(() => {
    const before = prev.current || [], next = perches
    const add = {}
    let order = 0
    for (let i = 0; i < Math.max(before.length, next.length); i++) {
      if (next[i] && (!before[i] || before[i].bird !== next[i].bird)) add[i] = { kind: 'land', delay: order++ * 250 }
    }
    prev.current = next
    if (!Object.keys(add).length) return
    setAnims(a => ({ ...a, ...add }))
    // One timer per landing, never cancelled by the next landing (birds arrive 250 ms apart).
    timers.current.push(setTimeout(() => setAnims(a => { const c = { ...a }; for (const k of Object.keys(add)) if (c[k] === add[k]) delete c[k]; return c }), 720 + order * 250))
  }, [perches.map(p => p?.bird || '-').join(',')])
  useEffect(() => () => timers.current.forEach(clearTimeout), [])

  // combo banner when a new murmuration activates in the render
  useEffect(() => {
    const active = render?.active_combos || []
    const fresh = active.find(id => !shownCombos.current.has(id))
    for (const id of active) shownCombos.current.add(id)
    for (const id of [...shownCombos.current]) if (!active.includes(id)) shownCombos.current.delete(id)
    if (!fresh) return
    const combo = catalog.combos.find(c => c.id === fresh)
    setBanner({ id: fresh, name: combo?.name || fresh, line: fresh === 'parliament' ? 'Parliament is in session.' : combo?.bonus?.visual?.replace(/_/g, ' ') || 'A new arrangement takes flight.', nonce: Date.now() })
    const nonce = Date.now()
    timers.current.push(setTimeout(() => setBanner(b => (b && b.id === fresh ? null : b)), 3200))
  }, [(render?.active_combos || []).join(',')])

  // one rAF: beaks on rendered notes, wire shiver on rendered kicks
  useEffect(() => {
    let raf = 0
    const tick = () => {
      const t = playing && getPosition ? getPosition() : -1
      let amp = 0
      if (t >= 0 && render) {
        for (const k of render.kick_onsets || []) { const dt = t - k; if (dt >= 0 && dt < 0.45) amp += 1.8 * Math.exp(-dt * 10) * Math.sin(dt * 64) }
        for (const p of perches) {
          if (!p) continue
          const el = birdEls.current[p.bird]
          if (!el) continue
          let v = 0
          if (!p.mute) for (const n of render.events?.[p.bird] || []) {
            if (t >= n.t && t < n.t + Math.max(n.len, 0.08)) { v = Math.max(v, (n.vel ?? 0.8) * (1 - 0.45 * (t - n.t) / Math.max(n.len, 0.08))); }
          }
          el.style.setProperty('--beak', v.toFixed(3))
        }
      } else for (const el of Object.values(birdEls.current)) el?.style.setProperty('--beak', '0')
      if (wire.current) wire.current.setAttribute('d', wirePath(w, amp))
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [playing, render, w, perches.map(p => (p ? p.bird + p.mute : '-')).join(',')])

  // ── edits (all through onChange) ──
  const setPerches = (next, meta) => {
    const seen = new Set(flock.seen || [])
    next.forEach(p => p && seen.add(p.bird))
    onChange({ ...flock, perches: next, seen: [...seen] }, meta)
  }
  const perchBird = (id, slot) => {
    const bird = byId[id]
    const next = [...perches]; while (next.length < 6) next.push(null)
    const already = next.findIndex(p => p?.bird === id)
    if (already >= 0) { next[already] = null; return setPerches(next, { action: 'unperch', bird: id, slot: already }) }
    let target = slot ?? next.findIndex(p => !p)
    if (target < 0) target = next.findIndex(p => byId[p.bird]?.role === bird.role) // full wire: swap within the role
    if (target < 0) target = next.length - 1
    next[target] = { bird: id, song: 'A', mute: false, solo: false }
    setPerches(next, { action: 'perch', bird: id, slot: target })
  }
  const patch = (slot, change, meta) => { const next = [...perches]; next[slot] = { ...next[slot], ...change }; setPerches(next, meta) }
  const cycleSong = slot => {
    const p = perches[slot]
    const song = SONGS[(SONGS.indexOf(p.song) + 1) % SONGS.length]
    patch(slot, { song }, { action: 'song', bird: p.bird, slot })
    setBadges(b => ({ ...b, [slot]: Date.now() }))
  }
  const applyTemplate = id => {
    const t = catalog.templates.find(x => x.id === id)
    if (!t) return
    const next = Array(6).fill(null)
    t.birds.forEach((e, i) => { next[i] = { ...e, mute: false, solo: false } })
    const seen = new Set(flock.seen || []); next.forEach(p => p && seen.add(p.bird))
    onChange({ ...flock, key: t.key, scale: t.scale, progression: [...t.progression], weather: t.weather, templateId: t.id, perches: next, seen: [...seen] }, { action: 'template', template: t.id })
  }
  // easter egg: tap the bare wire four times in time
  const tapWire = () => {
    const now = performance.now()
    taps.current = [...taps.current.filter(x => now - x < 3000), now]
    if (taps.current.length >= 4) { taps.current = []; onChange(flock, { action: 'wireTap' }) }
  }
  const onKey = (e, slot) => {
    const p = perches[slot]
    if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') {
      e.preventDefault()
      const nxt = (slot + (e.key === 'ArrowRight' ? 1 : -1) + slots) % slots
      stage.current.querySelector(`[data-slot="${nxt}"]`)?.focus()
    }
    if (!p) return
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); cycleSong(slot) }
    if (e.key === 'm' || e.key === 'M') patch(slot, { mute: !p.mute }, { action: 'mute', bird: p.bird, slot })
    if (e.key === 's' || e.key === 'S') patch(slot, { solo: !p.solo }, { action: 'solo', bird: p.bird, slot })
    if (e.key === 'Delete' || e.key === 'Backspace') { const next = [...perches]; next[slot] = null; setPerches(next, { action: 'unperch', bird: p.bird, slot }) }
  }

  const anySolo = perches.some(p => p?.solo && !p?.mute)
  const combos = catalog.combos || []
  const near = combos.find(c => !(flock.unlocked || []).includes(c.id) && comboProgress(c, flock, id => byId[id]?.role) === 1)

  return h('section', { className: 'fkp', 'aria-label': 'The Wire, melodic flock' },
    h('style', null, CSS),
    h('div', { className: 'fkp-head' },
      h('div', { className: 'fkp-title' }, h('i'), 'The Wire'),
      h('label', { className: 'fkp-ctl' }, 'Key',
        h('select', { className: 'fkp-sel', value: flock.key, onChange: e => onChange({ ...flock, key: e.target.value }, { action: 'harmony' }) }, KEYS.map(k => h('option', { key: k, value: k }, k)))),
      h('label', { className: 'fkp-ctl' }, 'Scale',
        h('select', { className: 'fkp-sel', value: flock.scale, onChange: e => onChange({ ...flock, scale: e.target.value }, { action: 'harmony' }) }, SCALES.map(s => h('option', { key: s, value: s }, s.replace('_', ' '))))),
      h('div', { className: 'fkp-ctl' }, 'Chords',
        h('div', { className: 'fkp-chips' }, (flock.progression || []).map((c, i) => h('button', {
          key: i, title: 'Click to change this bar\'s chord', 'aria-label': `Bar ${i + 1} chord ${c}`,
          onClick: () => { const p = [...flock.progression]; p[i] = CHORDS[(CHORDS.indexOf(c) + 1) % CHORDS.length]; onChange({ ...flock, progression: p }, { action: 'harmony' }) }
        }, c)))),
      h('div', { className: 'fkp-ctl' }, 'Sky',
        h('div', { className: 'fkp-chips', role: 'group', 'aria-label': 'Weather' }, WEATHER.map(([id, label]) => h('button', { key: id, 'aria-pressed': flock.weather === id, onClick: () => onChange({ ...flock, weather: id }, { action: 'weather' }) }, label)))),
      h('label', { className: 'fkp-ctl' }, 'Flock',
        h('select', { className: 'fkp-sel', value: flock.templateId || '', onChange: e => applyTemplate(e.target.value) },
          h('option', { value: '' }, 'Custom'), catalog.templates.map(t => h('option', { key: t.id, value: t.id }, t.name)))),
      h('div', { className: 'fkp-meter', onMouseEnter: () => setHint(true), onMouseLeave: () => setHint(null) },
        'Murmurations',
        h('div', { className: 'fkp-dots' }, combos.map(c => h('i', { key: c.id, className: 'fkp-dot', 'data-found': (flock.unlocked || []).includes(c.id), 'data-near': near?.id === c.id }))),
        hint && h('div', { className: 'fkp-hint', role: 'tooltip' },
          h('b', null, `${(flock.unlocked || []).length} of ${combos.length} found`),
          near ? near.riddle : 'Keep mixing. Some birds sing differently together.'))),
    h('div', { className: 'fkp-stage', ref: stage, 'data-combo': (render?.active_combos || []).includes('night_shift') ? 'night_shift' : undefined },
      Array.from({ length: 34 }, (_, i) => h('i', { key: 's' + i, className: 'fkp-star', 'data-tw': i % 5 === 0, style: { left: `${(i * 37.3) % 100}%`, top: `${(i * 23.7) % 58}%`, animationDelay: `${(i % 7) * 0.4}s` } })),
      h('i', { className: 'fkp-moon' }),
      flock.weather !== 'clear' && h('div', { className: 'fkp-wx', 'data-kind': flock.weather, 'aria-hidden': true },
        Array.from({ length: flock.weather === 'rain' ? 46 : 24 }, (_, i) => h('i', { key: i, style: { left: `${(i * 29.1) % 100}%`, top: `${(i * 41.3) % 92}%`, animationDelay: `${-(i * 0.37) % 7}s` } }))),
      h('svg', { className: 'fkp-wire', viewBox: `0 0 ${w} ${STAGE_H}`, preserveAspectRatio: 'none', 'aria-hidden': true },
        h('rect', { className: 'fkp-post', x: PAD - 4, y: WIRE_Y - 8, width: 6, height: STAGE_H }),
        h('rect', { className: 'fkp-post-cap', x: PAD - 7, y: WIRE_Y - 10, width: 12, height: 4 }),
        h('rect', { className: 'fkp-post', x: w - PAD - 2, y: WIRE_Y - 8, width: 6, height: STAGE_H }),
        h('rect', { className: 'fkp-post-cap', x: w - PAD - 5, y: WIRE_Y - 10, width: 12, height: 4 }),
        h('path', { ref: wire, d: wirePath(w, 0) })),
      h('div', { className: 'fkp-tap', onClick: tapWire, title: 'The wire' }),
      banner && h('div', { key: banner.nonce, className: 'fkp-swarm', 'aria-hidden': true },
        Array.from({ length: 40 }, (_, i) => h('i', { key: i, style: { '--i': i, '--a': `${(i * 137.5) % 360}deg`, '--r': 60 + (i * 53) % 220 } }))),
      banner && h('div', { key: 'b' + banner.nonce, className: 'fkp-banner', role: 'status' }, h('b', null, banner.name), h('span', null, banner.line)),
      xs.map((x, slot) => {
        const p = perches[slot]
        const y = wireYAt(x, w)
        if (!p) {
          if (slot === 6) return h('button', { key: slot, 'data-slot': slot, className: 'fkp-empty', style: { left: x, top: y - 14 }, title: 'A seventh perch has appeared…', onClick: () => perchBird('corvus', 6) }, '♛')
          return h('button', { key: slot, 'data-slot': slot, className: 'fkp-empty', style: { left: x, top: y - 14 }, 'aria-label': `Empty perch ${slot + 1}`, onKeyDown: e => onKey(e, slot), onClick: () => {
            const unseen = catalog.birds.find(b => !perches.some(q => q?.bird === b.id) && !perches.some(q => q && byId[q.bird]?.role === b.role))
            if (unseen) perchBird(unseen.id, slot)
          } }, '+')
        }
        const bird = byId[p.bird]
        const anim = anims[slot]
        const state = p.mute ? 'muted' : anySolo && !p.solo ? 'dim' : playing ? 'singing' : 'idle'
        return h('div', { key: `${slot}:${p.bird}`, className: 'fkp-perch', style: { left: x, top: y + BIRD / 32, '--land-delay': `${anim?.delay || 0}ms` } },
          h('div', { ref: el => { if (el) birdEls.current[p.bird] = el.firstChild }, onKeyDown: e => onKey(e, slot) },
            h(Bird, { id: artId(p.bird), size: BIRD, bpm, state, anim: anim?.kind || null, onClick: () => cycleSong(slot), label: `${bird?.name || p.bird}, ${bird?.role}, song ${p.song}${p.mute ? ', muted' : ''}. Click to change the song.` })),
          badges[slot] && h('span', { key: badges[slot], className: 'fkp-badge' }, p.song),
          h('div', { className: 'fkp-tools' },
            h('button', { 'data-k': 'm', 'aria-pressed': !!p.mute, 'aria-label': `Mute ${bird?.name}`, onClick: () => patch(slot, { mute: !p.mute }, { action: 'mute', bird: p.bird, slot }) }, 'M'),
            h('button', { 'data-k': 's', 'aria-pressed': !!p.solo, 'aria-label': `Solo ${bird?.name}`, onClick: () => patch(slot, { solo: !p.solo }, { action: 'solo', bird: p.bird, slot }) }, 'S'),
            h('button', { 'aria-label': `Song ${p.song} of ${bird?.name}, click for the next`, onClick: () => cycleSong(slot) }, p.song),
            h('button', { className: 'fkp-x', 'aria-label': `Send ${bird?.name} home`, onClick: () => { const next = [...perches]; next[slot] = null; setPerches(next, { action: 'unperch', bird: p.bird, slot }) } }, '×')),
          h('div', { className: 'fkp-name' }, h('b', null, bird?.name), ` · ${bird?.role}`))
      })),
    h('div', { className: 'fkp-roster', role: 'list', 'aria-label': 'The flock' },
      ROLES.flatMap((role, ri) => {
        const cards = catalog.birds.filter(b => b.role === role).map(b => h('button', {
          key: b.id, role: 'listitem', className: 'fkp-card', 'data-on': perches.some(p => p?.bird === b.id), 'data-new': !(flock.seen || []).includes(b.id),
          onClick: () => perchBird(b.id), 'aria-label': `${b.name}, ${role}${perches.some(p => p?.bird === b.id) ? ', on the wire' : ''}`
        }, h('div', { className: 'fkp-pic' }, h(Bird, { id: artId(b.id), size: 46, bpm, state: 'idle' })), h('div', null, h('b', null, b.name), h('span', null, role))))
        return ri ? [h('i', { key: 'sep' + role, className: 'fkp-role' }), ...cards] : cards
      }),
      h('i', { key: 'sep-secret', className: 'fkp-role' }),
      corvusUnlocked
        ? h('button', { key: 'corvus', className: 'fkp-card', 'data-on': perches.some(p => p?.bird === 'corvus'), onClick: () => perchBird('corvus', 6) }, h('div', { className: 'fkp-pic' }, h(Bird, { id: 'corvus', size: 46, bpm, state: 'idle' })), h('div', null, h('b', null, 'Corvus'), h('span', null, 'crown')))
        : h('div', { key: 'secret', className: 'fkp-card', 'data-secret': true, title: 'Every bird has to sing on the wire first.' }, h('div', { className: 'fkp-pic', style: { display: 'grid', placeItems: 'center', fontSize: 16 } }, '?'), h('div', null, h('b', null, 'Secret'), h('span', null, `${(flock.seen || []).length} of 12 seen`))))
  )
}
