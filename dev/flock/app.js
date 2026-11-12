import { birds, combos, templates } from './birds.js'
import { defaultBoomBapProject, detectActiveCombos, renderFlock } from './flock-synth.js'
import { FlockPanel } from './flock-ui.js'

const STORAGE_KEY = 'rookery.flock.project.v1'
const roleOrder = ['bass', 'keys', 'pad', 'lead', 'arp', 'call']
const wait = ms => new Promise(resolve => setTimeout(resolve, ms))

function defaults() {
  return {
    project: { name: 'Dusty Boom Bap', ...defaultBoomBapProject, seed: 1337 },
    flock: { key: 'D', scale: 'dorian', progression: ['i', 'iv', 'VII', 'III'], weather: 'dust', perches: Array(6).fill(null), seen: [], unlocked: [], templateId: 'dusty_boom_bap' }
  }
}

function loadState() {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || 'null')
    if (saved?.project && saved?.flock) return saved
  } catch {}
  return defaults()
}

let { project, flock } = loadState()
let renderResult = null
let renderBusy = false
let renderDirty = false
let stateVersion = 0
let renderRequestedAt = 0
let audio = null
let playing = false
let uiMotions = []
const motionTimers = new Map()
let agentSequence = 0
let renderError = ''
const root = document.querySelector('#app')
const panelHost = document.querySelector('#flock-panel')
const statusNode = document.querySelector('#flock-status')
const templateSelect = document.querySelector('#dev-template')
const playButton = document.querySelector('#dev-play')
const pickButton = document.querySelector('#dev-pick')
const resetButton = document.querySelector('#dev-reset')

function persist() {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify({ project, flock })) } catch {}
}

function makeAudioBuffer(result) {
  const context = audio.context()
  const sampleRate = result.sample_rate || 44100
  const buffer = context.createBuffer(2, result.left.length, sampleRate)
  buffer.copyToChannel(result.left, 0)
  buffer.copyToChannel(result.right, 1)
  return buffer
}

class LoopPlayer {
  constructor() {
    this.ac = null
    this.buffer = null
    this.primary = null
    this.pending = null
    this.sources = new Set()
    this.playing = false
  }
  context() {
    if (!this.ac) this.ac = new (window.AudioContext || window.webkitAudioContext)()
    return this.ac
  }
  startSource(buffer, startAt, offset, gainValue = 1) {
    const ac = this.context()
    const source = ac.createBufferSource()
    const gain = ac.createGain()
    source.buffer = buffer
    source.loop = true
    gain.gain.setValueAtTime(gainValue, startAt)
    source.connect(gain); gain.connect(ac.destination)
    source.start(startAt, offset)
    this.sources.add(source)
    source.addEventListener('ended', () => { this.sources.delete(source); try { source.disconnect(); gain.disconnect() } catch {} })
    return { source, gain, buffer, startAt, offset }
  }
  activatePending() {
    if (this.pending && this.context().currentTime >= this.pending.when) {
      this.primary = this.pending.next
      this.buffer = this.primary.buffer
      this.pending = null
    }
  }
  position() {
    if (!this.playing || !this.primary) return 0
    this.activatePending()
    const ac = this.context()
    const source = this.primary
    return ((ac.currentTime - source.startAt + source.offset) % source.buffer.duration + source.buffer.duration) % source.buffer.duration
  }
  async play() {
    if (!this.buffer) return
    const ac = this.context()
    if (ac.state === 'suspended') await ac.resume()
    this.stopSources()
    this.primary = this.startSource(this.buffer, ac.currentTime, 0)
    this.playing = true
  }
  setBuffer(buffer, projectAtRequest, requestedAt) {
    this.buffer = buffer
    if (!this.playing || !this.primary) return
    const ac = this.context()
    const now = ac.currentTime
    const position = this.position()
    if (this.pending) {
      try { this.pending.next.source.stop() } catch {}
      const old = this.pending.old
      old.gain.gain.cancelScheduledValues(now)
      old.gain.gain.setValueAtTime(old.gain.gain.value, now)
      old.gain.gain.linearRampToValueAtTime(1, now + 0.015)
      try { old.source.stop(now + 3600) } catch {}
      this.pending = null
    }
    const current = this.primary
    current.gain.gain.cancelScheduledValues(now)
    current.gain.gain.setValueAtTime(current.gain.gain.value, now)
    const oldDuration = current.buffer.duration
    const newDuration = buffer.duration
    const barSeconds = 240 / Math.max(1, Number(projectAtRequest.bpm) || 120)
    const tookTooLong = performance.now() - requestedAt > barSeconds * 1000
    let delta = tookTooLong ? oldDuration - position : (barSeconds - (position % barSeconds)) % barSeconds
    if (tookTooLong && delta < 0.002) delta = oldDuration
    const when = now + Math.max(0, delta)
    const fade = Math.min(0.18, newDuration * 0.12)
    const next = this.startSource(buffer, when, 0, 0)
    next.gain.gain.setValueAtTime(0, when)
    next.gain.gain.linearRampToValueAtTime(1, when + fade)
    current.gain.gain.linearRampToValueAtTime(0, when + fade)
    try { current.source.stop(when + fade + 0.025) } catch {}
    this.pending = { when, next, old: current }
  }
  stopSources() {
    for (const source of this.sources) { try { source.stop() } catch {} }
    this.sources.clear()
    this.primary = null
    this.pending = null
  }
  stop() { this.stopSources(); this.playing = false }
  dispose() { this.stop(); this.ac?.close().catch(() => {}); this.ac = null }
}

function playWireTap(key) {
  if (!audio) audio = new LoopPlayer()
  const ac = audio.context()
  if (ac.state === 'suspended') ac.resume().catch(() => {})
  const pitch = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'].indexOf(key)
  const oscillator = ac.createOscillator(), gain = ac.createGain()
  oscillator.type = 'sine'
  oscillator.frequency.setValueAtTime(440 * 2 ** (((36 + Math.max(0, pitch)) - 69) / 12), ac.currentTime)
  gain.gain.setValueAtTime(0.0001, ac.currentTime)
  gain.gain.exponentialRampToValueAtTime(0.14, ac.currentTime + 0.012)
  gain.gain.exponentialRampToValueAtTime(0.0001, ac.currentTime + 0.32)
  oscillator.connect(gain); gain.connect(ac.destination)
  oscillator.start(); oscillator.stop(ac.currentTime + 0.34)
}

function destroyPanel() {
  const old = panelHost.firstElementChild
  old?._flockDestroy?.()
}

function renderUi() {
  const activeElement = document.activeElement
  const focusKey = activeElement?.getAttribute?.('data-slot-focus')
  const uiKey = activeElement?.getAttribute?.('data-ui-key')
  destroyPanel()
  const panel = FlockPanel({
    project, flock, playing, getPosition: () => audio?.position() || 0,
    render: renderResult ? { ...renderResult, rendering: renderBusy, error: renderError } : { rendering: renderBusy, error: renderError },
    motion: uiMotions,
    onChange: handleFlockChange
  })
  panelHost.replaceChildren(panel)
  if (uiKey) panel.querySelector(`[data-ui-key="${uiKey}"]`)?.focus()
  else if (focusKey != null) panel.querySelector(`[data-slot-focus="${focusKey}"]`)?.focus()
  playButton.textContent = playing ? 'Stop' : 'Play'
  playButton.setAttribute('aria-pressed', String(playing))
  playButton.disabled = !renderResult && !playing
  templateSelect.value = flock.templateId || 'dusty_boom_bap'
  if (statusNode) statusNode.textContent = renderError || (renderBusy ? 'Tuning up…' : renderResult ? `${renderResult.master?.rms_db?.toFixed(1) || '0.0'} dB RMS` : 'Preparing the flock…')
}

function markMotion(kind, meta = {}) {
  const item = { kind, birdId: meta.birdId, bird: meta.bird, slot: meta.slot, birdPerch: meta.birdPerch, fromX: meta.fromX, fromY: meta.fromY }
  const prior = motionTimers.get(item.birdId)
  if (prior) clearTimeout(prior)
  uiMotions = [...uiMotions.filter(motion => motion.birdId !== item.birdId), item]
  const timer = setTimeout(() => {
    uiMotions = uiMotions.filter(motion => motion !== item)
    motionTimers.delete(item.birdId)
    renderUi()
  }, kind === 'land' ? 720 : kind === 'leave' ? 380 : 260)
  motionTimers.set(item.birdId, timer)
}

function applyRenderCombos(result) {
  const discovered = new Set(flock.unlocked || [])
  const discoveryDates = { ...(flock.discoveryDates || {}) }
  let changed = false
  for (const id of result.active_combos || []) {
    if (!discovered.has(id)) { discovered.add(id); discoveryDates[id] = new Date().toLocaleDateString(); changed = true }
  }
  if (changed) {
    flock = { ...flock, unlocked: [...discovered], discoveryDates }
    persist()
  }
}

async function renderLatest() {
  if (renderBusy) { renderDirty = true; return }
  renderBusy = true
  renderError = ''
  const requestedVersion = stateVersion
  const projectSnapshot = structuredClone(project)
  const flockSnapshot = structuredClone(flock)
  renderRequestedAt = performance.now()
  renderUi()
  try {
    const result = await renderFlock(projectSnapshot, flockSnapshot)
    if (requestedVersion !== stateVersion) { renderDirty = true; return }
    renderResult = result
    applyRenderCombos(result)
    if (!audio) audio = new LoopPlayer()
    audio.setBuffer(makeAudioBuffer(result), projectSnapshot, renderRequestedAt)
  } catch (error) {
    if (requestedVersion === stateVersion) renderError = error?.message || String(error)
  } finally {
    renderBusy = false
    renderUi()
    if (renderDirty) { renderDirty = false; renderLatest() }
  }
}

function handleFlockChange(nextFlock, meta = {}) {
  if (meta.action === 'wireTap') { playWireTap(nextFlock.key); return }
  if (nextFlock !== flock) flock = structuredClone(nextFlock)
  if (meta.projectPatch) project = { ...project, ...meta.projectPatch }
  if (meta.action === 'land' || meta.action === 'leave' || meta.action === 'song') markMotion(meta.action, meta)
  stateVersion++
  persist()
  renderUi()
  renderLatest()
}

function templateProjectPatch(template) {
  if (template.id === 'dusty_boom_bap') return { bpm: 90, bars: 4 }
  if (template.id === 'trap_night') return { bpm: 140, bars: 8 }
  if (template.id === 'lo_fi_study') return { bpm: 72, bars: 4 }
  if (template.id === 'late_house') return { bpm: 124, bars: 4 }
  if (template.id === 'sunday_soul') return { bpm: 84, bars: 4 }
  return {}
}

function selectTemplate(templateId) {
  const template = templates.find(item => item.id === templateId)
  if (!template) return
  const perches = Array(6).fill(null)
  const seen = new Set(flock.seen || [])
  template.birds.forEach((entry, index) => { perches[index] = { ...entry, mute: false, solo: false }; seen.add(entry.bird) })
  flock = { ...flock, key: template.key, scale: template.scale, progression: [...template.progression], weather: template.weather, templateId, perches, seen: [...seen] }
  project = { ...project, ...templateProjectPatch(template) }
  stateVersion++
  persist(); renderUi(); renderLatest()
}

async function agentPicks() {
  const template = templates.find(item => item.id === templateSelect.value) || templates[0]
  const sequence = ++agentSequence
  const seen = new Set(flock.seen || [])
  const order = [...template.birds].sort((a, b) => roleOrder.indexOf(birds.find(bird => bird.id === a.bird)?.role) - roleOrder.indexOf(birds.find(bird => bird.id === b.bird)?.role))
  flock = { ...flock, key: template.key, scale: template.scale, progression: [...template.progression], weather: template.weather, templateId: template.id, perches: Array(6).fill(null) }
  project = { ...project, ...templateProjectPatch(template) }
  stateVersion++
  persist(); renderUi(); renderLatest()
  for (const entry of order) {
    await wait(250)
    if (sequence !== agentSequence) return
    const slot = flock.perches.findIndex(perch => !perch)
    if (slot < 0) break
    const perches = [...flock.perches]
    perches[slot] = { ...entry, mute: false, solo: false }
    seen.add(entry.bird)
    flock = { ...flock, perches, seen: [...seen] }
    markMotion('land', { birdId: entry.bird, slot })
    stateVersion++
    persist(); renderUi(); renderLatest()
  }
}

function reset() {
  agentSequence++
  for (const timer of motionTimers.values()) clearTimeout(timer)
  motionTimers.clear(); uiMotions = []
  if (audio?.playing) audio.stop()
  playing = false
  renderResult = null
  renderError = ''
  ;({ project, flock } = defaults())
  templateSelect.value = flock.templateId
  stateVersion++
  persist(); renderUi(); renderLatest()
}

templateSelect.replaceChildren(...templates.map(item => {
  const option = document.createElement('option')
  option.value = item.id
  option.textContent = item.name
  return option
}))
templateSelect.value = flock.templateId || 'dusty_boom_bap'
templateSelect.addEventListener('change', () => selectTemplate(templateSelect.value))
pickButton.addEventListener('click', agentPicks)
resetButton.addEventListener('click', reset)
playButton.addEventListener('click', async () => {
  if (!audio) return
  try {
    if (playing) audio.stop()
    else await audio.play()
    playing = audio.playing
    renderUi()
  } catch (error) {
    renderError = error?.message || String(error)
    renderUi()
  }
})
renderUi()
renderLatest()

window.addEventListener('beforeunload', () => { destroyPanel(); audio?.dispose() }, { once: true })
