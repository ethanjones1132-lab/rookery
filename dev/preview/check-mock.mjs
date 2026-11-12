import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { createMockBackend } from './mock-backend.js'
import { renderFlock } from '../flock/flock-synth.js'

const makeSynth = () => async project => {
  const flock = project.flock ? await renderFlock(project, project.flock) : null
  return {
    wav: new Uint8Array([82, 73, 70, 70, project.tracks.length]),
    audio_url: '/audio/mock',
    duration_samples: Math.round(project.bars * 4 * 60 / project.bpm * 44100),
    sample_rate: 44100,
    meters: Object.fromEntries(project.tracks.map(track => [track.id, { rms_db: -16, peak_db: -1.5 }])),
    master: { peak_db: -1.5, rms_db: -16, lufs_estimate: -14 },
    flock_events: flock?.events || {}, kick_onsets: flock?.kick_onsets || [], flock_active_combos: flock?.active_combos || []
  }
}

const events = []
const synthCalls = []
const catalogFetches = []
let result
const backend = createMockBackend({
  emit: (type, payload) => events.push({ type, payload }),
  fetchImpl: async path => {
    catalogFetches.push(path)
    const file = path.endsWith('/grooves.json') ? '../../skills/rookery/grooves.json' : '../../rookery/flock/birds.json'
    return { ok: true, json: async () => JSON.parse(await readFile(new URL(file, import.meta.url), 'utf8')) }
  },
  synth: async project => {
    synthCalls.push(structuredClone(project))
    return makeSynth()(project)
  }
})

async function expectStatus(promise, status) {
  await assert.rejects(promise, error => error.status === status && typeof error.message === 'string')
}

assert.deepEqual(await backend.handle('GET', '/projects'), [])
const flockCatalog = await backend.handle('GET', '/flock/catalog')
assert.equal(flockCatalog.templates.length, 5)
assert.equal(flockCatalog.birds.length, 12)
assert.deepEqual(catalogFetches, ['/rookery/flock/birds.json'])
await expectStatus(backend.handle('GET', '/project/missing'), 404)
await expectStatus(backend.handle('POST', '/render', { name: 'missing' }), 404)
await expectStatus(backend.handle('POST', '/edit', { name: 'missing', op: 'meta', bpm: 91 }), 404)
assert.equal((await backend.handle('GET', '/status')).version, 'mock-1')
const status = await backend.handle('GET', '/status')
assert.deepEqual(status.corvus, {
  found: true,
  path: 'C:\\Program Files\\Common Files\\VST3\\Corvus FX.vst3',
  params: [
    { name: 'Drive', min: 0, max: 1, default: 0.25, value: 0.25 },
    { name: 'Tone', min: 0, max: 1, default: 0.5, value: 0.5 },
    { name: 'Warmth', min: 0, max: 1, default: 0.5, value: 0.5 },
    { name: 'Width', min: 0, max: 1, default: 0.5, value: 0.5 },
    { name: 'Mix', min: 0, max: 1, default: 1, value: 1 }
  ]
})
assert.deepEqual(status.kits.factory, ['kick_punch', 'kick_deep', 'snare_snap', 'snare_snap_dry', 'clap_stack', 'hat_tight', 'hat_open_short', '808_round', 'kick_boom', '808', 'snare_crack', 'clap', 'hat_closed', 'hat_open', 'rim', 'perc'])

const initial = backend.newProject({ name: 'dusty-a', bpm: 90, bars: 4, swing: 0 })
assert.deepEqual(Object.keys(initial).sort(), ['agent_editing', 'project', 'render', 'rev'])
assert.equal(initial.rev, 0)
assert.equal((await backend.handle('GET', '/project/dusty-a?since=0')).changed, false)
assert.equal((await backend.handle('GET', '/projects'))[0].name, 'dusty-a')

const blankBeat = await backend.handle('POST', '/project', {})
assert.equal(blankBeat.project.name, 'beat-1')
assert.deepEqual(blankBeat.project.tracks.map(track => [track.id, track.source, new Set(track.steps)]), [
  ['kick', 'factory:kick_punch', new Set(['.'])],
  ['snare', 'factory:snare_snap', new Set(['.'])],
  ['hat', 'factory:hat_tight', new Set(['.'])]
])
await expectStatus(backend.handle('POST', '/project', { name: 'beat-1' }), 409)
await expectStatus(backend.handle('POST', '/project', { name: 'bad name' }), 422)
await expectStatus(backend.handle('POST', '/project', { from: 'no-such-project' }), 404)
const duplicate = await backend.handle('POST', '/project', { name: 'beat-copy', from: 'beat-1' })
assert.equal(duplicate.rev, 1)
result = await backend.handle('POST', '/edit', { name: 'beat-copy', op: 'steps', track: 'kick', steps: 'x' })
result = await backend.handle('POST', '/edit', { name: 'beat-copy', op: 'clear' })
assert.equal(result.diff[0].track, 'kick')
assert.deepEqual(result.diff[0].steps, Array.from({ length: 64 }, (_, i) => i))
assert.equal((await backend.handle('POST', '/undo', { name: 'beat-copy' })).project.tracks[0].steps, 'x'.repeat(64))
result = await backend.handle('POST', '/edit', { name: 'beat-copy', op: 'clear', track: 'kick' })
assert.equal(result.diff[0].field, 'steps')
await expectStatus(backend.handle('POST', '/edit', { name: 'beat-copy', op: 'clear', track: 'kick' }), 422)
const renamed = await backend.handle('POST', '/project/beat-copy/rename', { to: 'beat-renamed' })
assert.equal(renamed.project.name, 'beat-renamed')
await expectStatus(backend.handle('POST', '/project/absent/rename', { to: 'new-name' }), 404)
await expectStatus(backend.handle('POST', '/project/beat-1/rename', { to: 'bad name' }), 422)
await expectStatus(backend.handle('POST', '/project/beat-1/rename', { to: 'beat-renamed' }), 409)
assert.deepEqual(await backend.handle('DELETE', '/project/beat-1'), { deleted: 'beat-1' })
await expectStatus(backend.handle('DELETE', '/project/beat-1'), 404)
assert.deepEqual(events.filter(event => /\.project\.(created|renamed|deleted)$/.test(event.type)).slice(-4).map(event => event.type), [
  'plugin.rookery.project.created', 'plugin.rookery.project.created',
  'plugin.rookery.project.renamed', 'plugin.rookery.project.deleted'
])

result = await backend.handle('POST', '/edit', {
  name: 'dusty-a', rev: 0, op: 'track', action: 'add', id: 'kick', kind: 'drum', source: 'factory:kick_boom'
})
assert.equal(result.rev, 1)
assert.deepEqual(result.diff, [{ track: 'kick', field: 'track', action: 'add' }])
assert.equal(result.project.tracks[0].steps.length, 64)
assert.equal((await backend.handle('GET', '/project/dusty-a?since=0')).project.name, 'dusty-a')

const beforeStale = await backend.handle('GET', '/project/dusty-a')
const eventCountBeforeStale = events.length
await assert.rejects(backend.handle('POST', '/edit', {
  name: 'dusty-a', rev: 0, op: 'steps', track: 'kick', steps: 'x'
}), error => error.status === 409 && error.rev === 1)
assert.deepEqual(await backend.handle('GET', '/project/dusty-a'), beforeStale)
assert.equal(events.length, eventCountBeforeStale)

await expectStatus(backend.handle('POST', '/edit', {
  name: 'dusty-a', rev: 1, op: 'steps', track: 'kick', steps: 'x!'
}), 422)
assert.equal((await backend.handle('GET', '/project/dusty-a')).rev, 1)

result = await backend.handle('POST', '/edit', {
  name: 'dusty-a', rev: 1, op: 'steps', track: 'kick', steps: 'x..x'
})
const kickPattern = 'x..x'.repeat(16)
assert.equal(result.rev, 2)
assert.equal(result.project.tracks[0].steps, kickPattern)
assert.deepEqual(result.diff[0], {
  track: 'kick', field: 'steps', from: '.'.repeat(64), to: kickPattern,
  steps: Array.from({ length: 16 }, (_, bar) => [bar * 4, bar * 4 + 3]).flat()
})
assert.deepEqual(result.diff[0].steps, [...result.diff[0].steps].sort((a, b) => a - b))
let projectEvent = events.filter(event => event.type === 'plugin.rookery.project.updated').at(-1)
assert.equal(projectEvent.payload.source, 'user')
assert.equal(projectEvent.payload.rev, result.rev)
assert.deepEqual(projectEvent.payload.diff, result.diff)

result = await backend.handle('POST', '/edit', {
  name: 'dusty-a', rev: 2, op: 'track', action: 'add', id: 'snare', kind: 'snare', source: 'factory:snare_crack'
})
assert.equal(result.rev, 3)
const snarePattern = '....x.......x...'
result = await backend.handle('POST', '/edit', {
  name: 'dusty-a', rev: 3, op: 'steps', track: 'snare', steps: snarePattern,
  velocity: [0.9, 0.9, 0.9, 0.9, 1, 0.9, 0.9, 0.9, 0.9, 0.9, 0.9, 0.9, 1, 0.9, 0.9, 0.9]
})
assert.equal(result.rev, 4)
assert.deepEqual(result.diff.map(diff => diff.field), ['steps', 'velocity'])
assert.deepEqual(result.diff[1].steps, [4, 12, 20, 28, 36, 44, 52, 60])

result = await backend.handle('POST', '/edit', {
  name: 'dusty-a', rev: 4, op: 'track', action: 'set', id: 'kick', gain_db: -3, pan: 0.25, mute: true
})
assert.equal(result.rev, 5)
assert.deepEqual(result.diff.map(diff => diff.field), ['gain_db', 'pan', 'mute'])
await expectStatus(backend.handle('POST', '/edit', {
  name: 'dusty-a', rev: 5, op: 'track', action: 'remove', id: 'absent'
}), 422)

const fx = [
  { type: 'vst3', path: status.corvus.path, params: { Drive: 0.35, Warmth: 0.6 } },
  { type: 'limiter', ceiling_db: -1 }
]
result = await backend.handle('POST', '/edit', { name: 'dusty-a', rev: 5, op: 'mix', target: 'master', fx })
assert.equal(result.rev, 6)
assert.equal(result.diff[0].field, 'fx')
result = await backend.handle('POST', '/edit', {
  name: 'dusty-a', rev: 6, op: 'fx_param', target: 'master', index: 0, param: 'Drive', value: 0.42
})
assert.equal(result.rev, 7)
assert.equal(result.diff[0].field, 'fx')
assert.equal(result.project.master.fx[0].params.Drive, 0.42)
result = await backend.handle('POST', '/edit', { name: 'dusty-a', rev: 7, op: 'meta', bpm: 92, bars: 8, swing: 0.18 })
assert.equal(result.rev, 8)
assert.equal(result.project.bars, 8)
assert.equal(result.project.tracks[0].steps.length, 128)
assert.deepEqual(result.diff.map(diff => diff.field), ['bpm', 'bars', 'swing'])

result = await backend.handle('POST', '/edit', {
  name: 'dusty-a', rev: 8, op: 'flock', action: 'template', template: 'dusty_boom_bap'
})
assert.equal(result.project.flock.key, 'D')
assert.equal(result.project.flock.weather, 'dust')
assert.deepEqual(result.diff[0], {
  field: 'flock', change: 'template', slot: 0, bird: 'bramble', from: null,
  to: { bird: 'bramble', song: 'A', mute: false, solo: false, gain_db: 0, pan: 0 }
})
assert(result.diff.some(diff => diff.field === 'flock' && diff.change === 'weather'))
await backend.handle('POST', '/edit', { name: 'dusty-a', rev: 9, op: 'track', action: 'set', id: 'kick', mute: false })
const flockRender = await backend.handle('POST', '/render', { name: 'dusty-a' })
assert(Object.keys(flockRender.flock_events).length > 0)
assert(flockRender.flock_events.bramble.length > 0)
assert(flockRender.kick_onsets.length > 0)
assert.deepEqual(flockRender.flock_active_combos, [])
const perchedBird = (await backend.handle('GET', '/project/dusty-a')).project.flock.perches.find(Boolean).bird
result = await backend.handle('POST', '/edit', { name: 'dusty-a', rev: 10, op: 'flock', action: 'mix', bird: perchedBird, gain_db: 3, pan: -0.2 })
assert.equal(result.rev, 11)
assert.deepEqual(result.project.flock.perches.find(p => p?.bird === perchedBird) && {
  gain_db: result.project.flock.perches.find(p => p?.bird === perchedBird).gain_db,
  pan: result.project.flock.perches.find(p => p?.bird === perchedBird).pan
}, { gain_db: 3, pan: -0.2 })
assert.deepEqual(result.diff.map(d => d.change), ['mix'])
await expectStatus(backend.handle('POST', '/edit', { name: 'dusty-a', rev: 11, op: 'flock', action: 'mix', bird: perchedBird, gain_db: 13 }), 422)
const mixRender = await backend.handle('POST', '/render', { name: 'dusty-a' })
assert.equal(typeof mixRender.mix.centroid_hz, 'number')
assert.deepEqual(Object.keys(mixRender.mix.bands_pct), ['sub', 'low', 'mid', 'high', 'air'])
assert(mixRender.mix.centroid_hz > flockRender.mix.centroid_hz)
result = await backend.handle('POST', '/edit', { name: 'dusty-a', rev: 11, op: 'arrange', sections: [
  { id: 'intro', repeat: 2, mute: ['kick', 'bird:0'] }, { id: 'verse', repeat: 4, mute: [] }
] })
assert.equal(result.rev, 12)
assert.deepEqual(result.diff.map(diff => diff.field), ['arrangement'])
assert.deepEqual(result.project.arrangement.sections.map(section => section.id), ['intro', 'verse'])
assert.deepEqual(events.filter(event => event.type === 'plugin.rookery.project.updated').at(-1).payload.diff, result.diff)
await expectStatus(backend.handle('POST', '/edit', { name: 'dusty-a', rev: 12, op: 'arrange', sections: [
  { id: 'dup', repeat: 1, mute: [] }, { id: 'dup', repeat: 1, mute: [] }
] }), 422)
const songMock = await backend.handle('POST', '/render', { name: 'dusty-a', song: true })
assert.equal(songMock.song, true)
assert.deepEqual(songMock.sections.map(section => section.id), ['intro', 'verse'])
assert.equal(songMock.sections[0].start_s, 0)
assert.equal(songMock.sections[0].end_s, 16 * 4 * 60 / 92)
assert.equal(songMock.sections[1].end_s, 48 * 4 * 60 / 92)
assert.equal(songMock.duration_samples, Math.round(48 * 4 * 60 / 92 * 44100))
assert.equal(songMock.report.length_exact.pass, true)
result = await backend.handle('POST', '/edit', { name: 'dusty-a', rev: 12, op: 'track', action: 'remove', id: 'kick' })
assert.deepEqual(result.project.arrangement.sections[0].mute, ['bird:0'])
await expectStatus(backend.handle('POST', '/edit', { name: 'dusty-a', op: 'arrange', sections: Array.from({ length: 16 }, (_, index) => ({ id: `long${index}`, repeat: 8, mute: [] })) }), 422)

const batchProject = backend.newProject({ name: 'batch-check' })
const eventCountBeforeBatch = events.filter(event => event.type === 'plugin.rookery.project.updated').length
result = await backend.handle('POST', '/edit', { name: 'batch-check', rev: batchProject.rev, op: 'apply', ops: [
  { op: 'track', action: 'add', id: 'kick', kind: 'drum', source: 'factory:kick_boom' },
  { op: 'track', action: 'set', id: 'kick', gain_db: 3 },
  { op: 'groove', groove: 'pocket-88-clap-pocket' }
] })
assert.equal(result.rev, 1)
assert(result.diff.some(d => d.track === 'kick' && d.field === 'steps'))
assert.equal(events.filter(event => event.type === 'plugin.rookery.project.updated').length, eventCountBeforeBatch + 1)
assert.equal(events.filter(event => event.type === 'plugin.rookery.project.updated').at(-1).payload.diff.length, result.diff.length)
const batchRender = await backend.handle('POST', '/render', { name: 'batch-check' })
assert.equal(batchRender.meters.kick.rms_db, -13)

backend.setAgentEditing('dusty-a', true)
assert.equal((await backend.handle('GET', '/project/dusty-a')).agent_editing, true)
backend.setAgentEditing('dusty-a', false)
assert.equal((await backend.handle('GET', '/project/dusty-a')).agent_editing, false)
assert.deepEqual(events.filter(event => event.type === 'plugin.rookery.agent.editing').map(event => event.payload.editing), [true, false])

const undoProject = backend.newProject({ name: 'undo-check' })
await backend.handle('POST', '/edit', { name: 'undo-check', op: 'track', action: 'add', id: 'kick' })
await backend.handle('POST', '/edit', { name: 'undo-check', op: 'steps', track: 'kick', steps: 'x..x' })
await backend.agentEdit({ name: 'undo-check', op: 'track', action: 'set', id: 'kick', gain_db: -2 })
result = await backend.handle('POST', '/undo', { name: 'undo-check' })
assert.equal(result.rev, 4)
assert.equal(result.project.tracks[0].gain_db, 0)
assert.deepEqual(result.diff, [{ track: 'kick', field: 'gain_db', from: -2, to: 0 }])
let undoEvent = events.filter(event => event.type === 'plugin.rookery.project.updated').at(-1)
assert.equal(undoEvent.payload.source, 'agent')
assert.equal(undoEvent.payload.tool, 'rookery_undo')
result = await backend.handle('POST', '/undo', { name: 'undo-check' })
assert.equal(result.project.tracks[0].steps, '.'.repeat(64))
assert.deepEqual(result.diff, [{
  track: 'kick', field: 'steps', from: 'x..x'.repeat(16), to: '.'.repeat(64),
  steps: Array.from({ length: 16 }, (_, bar) => [bar * 4, bar * 4 + 3]).flat()
}])
const stepUndoEvent = events.filter(event => event.type === 'plugin.rookery.project.updated').at(-1)
assert.deepEqual(stepUndoEvent.payload.diff, result.diff)
result = await backend.handle('POST', '/undo', { name: 'undo-check' })
assert.equal(result.project.tracks.length, 0)
assert.deepEqual(result.diff, [{ track: 'kick', field: 'track', action: 'remove' }])
await expectStatus(backend.handle('POST', '/undo', { name: 'undo-check' }), 422)
assert.equal(undoProject.rev, 0)

async function buildAndRender(name, { bpm = 90, steps = snarePattern } = {}) {
  backend.newProject({ name, bpm, bars: 4, swing: 0 })
  await backend.handle('POST', '/edit', {
    name, op: 'track', action: 'add', id: 'snare', kind: 'snare', source: 'factory:snare_crack'
  })
  await backend.handle('POST', '/edit', { name, op: 'steps', track: 'snare', steps })
  return backend.handle('POST', '/render', { name })
}

const eventStart = events.length
const first = await buildAndRender('hash-a')
const second = await buildAndRender('hash-b')
const different = await buildAndRender('hash-c', { steps: '....x.......x..x' })
assert.equal(first.hash.length, 64)
assert.equal(first.hash, second.hash)
assert.notEqual(first.hash, different.hash)
assert.equal(first.wav_hash.length, 64)
assert.equal(first.wav_hash, second.wav_hash)
assert.equal(first.audio_url, '/audio/mock')
assert.deepEqual(first.report.length_exact, {
  pass: true, value: Math.round(4 * 4 * 60 / 90 * 44100), target: 'exactly 470400 samples'
})
assert.deepEqual(first.report.no_clipping, { pass: true, value: -1.5, target: '≤ −1.0 dBTP' })
assert.equal(first.report.loudness.pass, true)
assert.equal(first.report.not_silent.pass, true)
assert.deepEqual(first.report.seam_click, { pass: true, value: 0.6 })
assert.deepEqual(first.report.deterministic, { pass: true, value: first.hash.slice(0, 12) })
assert.equal(first.duration_samples, 470400)
assert.equal(first.sample_rate, 44100)
assert.deepEqual(first.meters.snare, { rms_db: -16, peak_db: -1.5 })
assert.deepEqual(events.slice(eventStart).filter(event => event.type.startsWith('plugin.rookery.render.')).map(event => event.type), [
  'plugin.rookery.render.started', 'plugin.rookery.render.done',
  'plugin.rookery.render.started', 'plugin.rookery.render.done',
  'plugin.rookery.render.started', 'plugin.rookery.render.done'
])
assert.deepEqual((await backend.handle('GET', `/audio/${first.hash}`)), {
  hash: first.hash, mime: 'audio/wav', b64: 'UklGRgE='
})
assert.equal(synthCalls.length, 7)

const failingEvents = []
const failingBackend = createMockBackend({
  emit: (type, payload) => failingEvents.push({ type, payload }),
  synth: async () => { throw new Error('synth failed') }
})
failingBackend.newProject({ name: 'fails' })
await assert.rejects(failingBackend.handle('POST', '/render', { name: 'fails' }), error => error.status === 500 && error.message === 'synth failed')
assert.deepEqual(failingEvents.filter(event => event.type.startsWith('plugin.rookery.render.')).map(event => event.type), [
  'plugin.rookery.render.started', 'plugin.rookery.render.failed'
])
await expectStatus(backend.handle('GET', '/audio/not-rendered'), 404)
await expectStatus(backend.handle('GET', '/not-a-route'), 404)

// ── lost push events: the page's polling fallback still sees the change ────
// The desktop half falls back to GET /project/<name>?since=<rev> every 1.5 s.
// Simulate a broken publisher by dropping everything the backend emitted.
const silentStart = events.length
const silent = backend.newProject({ name: 'silent', bpm: 80, bars: 4 })
assert.equal(silent.rev, 0)
const silentEdit = await backend.handle('POST', '/edit', { name: 'silent', rev: 0, op: 'meta', bpm: 81 })
events.splice(silentStart)  // every push dropped, as a detached UI sees it
assert.equal(events.filter(event => event.type === 'plugin.rookery.project.updated' && event.payload.name === 'silent').length, 0)
const afterPoll = await backend.handle('GET', '/project/silent?since=0')
assert.equal(afterPoll.changed, undefined)
assert.equal(afterPoll.rev, silentEdit.rev)
assert.equal(afterPoll.project.bpm, 81)
assert.equal((await backend.handle('GET', '/project/silent?since=1')).changed, false)

// ── page fallback helpers from the shipped desktop/plugin.js ───────────────
// Import the real file with only its two host modules stubbed. It has no
// module-scope side effects, so Node can load it as-is.
const sdkStub = `export const host={state:{},notify(){},navigate(){},onEvent(){return()=>{}},request:async()=>({})};export const ROUTES_AREA='routes',SIDEBAR_NAV_AREA='sidebar.nav',TOOL_MEDIA_RENDERER_AREA='toolMedia'`
const reactStub = `export const Component=class{};export const Fragment=Symbol('Fragment');export const createElement=()=>null;export const memo=x=>x;export const useCallback=f=>f;export const useEffect=()=>{};export const useLayoutEffect=()=>{};export const useMemo=f=>f();export const useRef=v=>({current:v});export const useState=v=>[v,()=>{}];export const useSyncExternalStore=(s,g)=>g()`
const dataModule = source => 'data:text/javascript;base64,' + Buffer.from(source).toString('base64')
const pageSource = (await readFile(new URL('../../desktop/plugin.js', import.meta.url), 'utf8'))
  .replace("from '@hermes/plugin-sdk'", `from '${dataModule(sdkStub)}'`)
  .replace("from 'react'", `from '${dataModule(reactStub)}'`)
const page = await import(dataModule(pageSource))
assert.equal(typeof page.startRevWatch, 'function')
assert.equal(typeof page.newlyCreatedProject, 'function')

// The rev watch polls only while visible, wakes at once on visibilitychange,
// and stops cleanly with the plugin.
const doc = { visibilityState: 'hidden' }
const polls = []
let timerTick = null, timerMs = null, cleared = 0
const listeners = new Map()
const stopWatch = page.startRevWatch({
  poll: () => polls.push('poll'),
  intervalMs: 1500,
  setInterval: (fn, ms) => { timerTick = fn; timerMs = ms; return () => { cleared++ } },
  addEventListener: (target, type, fn) => { assert.equal(target, doc); listeners.set(type, fn); return () => listeners.delete(type) },
  document: doc
})
assert.equal(timerMs, 1500)
timerTick()
assert.deepEqual(polls, []) // a hidden page does not poll
doc.visibilityState = 'visible'
listeners.get('visibilitychange')()
assert.deepEqual(polls, ['poll']) // becoming visible catches up immediately
timerTick()
assert.deepEqual(polls, ['poll', 'poll'])
stopWatch()
timerTick()
listeners.get('visibilitychange')?.()
assert.deepEqual(polls, ['poll', 'poll'])
assert.equal(cleared, 1)
assert.equal(listeners.has('visibilitychange'), false)

// A project that appeared while the page was detached is followed, like an
// agent-source project.updated event; an ambiguous pair is not.
assert.equal(page.newlyCreatedProject({ previous: [], current: null, list: [{ name: 'a' }] }), null)
assert.equal(page.newlyCreatedProject({ previous: ['a'], current: 'a', list: [{ name: 'b' }, { name: 'a' }] }), 'b')
assert.equal(page.newlyCreatedProject({ previous: ['a'], current: 'a', list: [{ name: 'b' }, { name: 'c' }, { name: 'a' }] }), null)
assert.equal(page.newlyCreatedProject({ previous: ['a'], current: 'a', list: [{ name: 'a' }] }), null)

// A local diff paints bpm/swing, but a bars change resizes every pattern on
// the server, so it must reload instead of leaving 4-bar steps under an 8-bar grid.
const localProject = { bpm: 90, bars: 4, swing: 0, steps_per_bar: 16, tracks: [{ id: 'kick', steps: 'x...'.repeat(16) }] }
assert.equal(page.applyDiffLocally(localProject, [{ field: 'bpm', from: 90, to: 95 }]).bpm, 95)
assert.equal(page.applyDiffLocally(localProject, [{ field: 'bars', from: 4, to: 8 }]), null)
assert.equal(page.applyDiffLocally(localProject, [{ track: 'kick', field: 'steps', from: 'x', to: 'x.' }]).tracks[0].steps, 'x.')

// Suggested starters ask for samples (a bed and a lead), and no page copy
// promises that the agent will build the user's Flock.
assert(page.PROMPTS.length >= 3)
for (const prompt of [...page.PROMPTS, ...page.EDIT_STARTERS]) {
  assert.doesNotMatch(prompt, /flock|bird|perch|wire|sing/i)
}
for (const prompt of page.PROMPTS) assert.match(prompt, /rhodes|flute|piano|bell|pluck|chord|lead|bed/i)

// Poll backoff grows and caps so a timing-out gateway is not hammered.
assert.deepEqual([0, 1, 2, 3, 4, 5, 12].map(page.retryDelay), [0, 2000, 5000, 10000, 20000, 30000, 30000])

// An edit queued for one project never lands on the project opened next.
assert.equal(page.editBelongsTo('dusty-a', 'dusty-a'), true)
assert.equal(page.editBelongsTo('dusty-a', 'dusty-b'), false)
assert.equal(page.editBelongsTo(null, 'dusty-a'), false)

// Loop renders surface mix notes and sample fit; song renders have neither.
const highlights = page.mixHighlights({
  mix_notes: ['kick is 2.5 LU over the reference', 'bed and lead sit in the same register'],
  fit: [{ a: 'bed', b: 'lead', register_overlap: 0.82, rhythm_overlap: 0.5 }]
})
assert.deepEqual(highlights.notes, ['kick is 2.5 LU over the reference', 'bed and lead sit in the same register'])
assert.deepEqual(highlights.pairs, [{ key: 'bed:lead', label: 'bed ↔ lead', detail: 'register 82% · rhythm 50%' }])
assert.deepEqual(page.mixHighlights({ song: true }), { notes: [], pairs: [] })

console.log('ok: routes, edit ops, validation, revs, undo, events, deterministic renders, audio, status and the lost-event fallback')
