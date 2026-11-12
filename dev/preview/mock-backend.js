// In-memory backend for the preview harness. It follows docs/contract.md and
// stays independent of the Desktop SDK so Node can exercise the public routes.

const CORVUS_PATH = 'C:\\Program Files\\Common Files\\VST3\\Corvus FX.vst3'
const FACTORY_KITS = ['kick_punch', 'kick_deep', 'snare_snap', 'snare_snap_dry', 'clap_stack', 'hat_tight', 'hat_open_short', '808_round', 'kick_boom', '808', 'snare_crack', 'clap', 'hat_closed', 'hat_open', 'rim', 'perc']
const TRACK_FIELDS = ['kind', 'source', 'gain_db', 'pan', 'mute', 'solo', 'pitch', 'notes', 'slices'] // contract v0.1 ratified
const DEFAULT_FLOCK = { key: 'D', scale: 'dorian', progression: ['i', 'iv', 'VII', 'III'], weather: 'clear', perches: Array(6).fill(null), seen: [], unlocked: [] }

const clone = value => structuredClone(value)
const flockValueEqual = (a, b) => JSON.stringify(a) === JSON.stringify(b)
const loopLength = project => project.bars * project.steps_per_bar
function plausibleMix(project) {
  const lead = (project.flock?.perches || []).filter(Boolean).reduce((sum, perch) => sum + Math.max(-24, Math.min(12, perch.gain_db || 0)), 0)
  const trackGain = project.tracks.reduce((sum, track) => sum + (track.gain_db || 0), 0)
  const mid = Math.max(12, Math.min(58, 34 + lead * 0.55 + trackGain * 0.2))
  const bands = { sub: 22, low: 20, mid, high: 16, air: 10 }
  const total = Object.values(bands).reduce((a, b) => a + b, 0)
  return { correlation: 0.74, width: 0.62, lr_balance_db: 0.2, crest_db: 8.4,
    centroid_hz: Math.round(920 + lead * 32 + trackGain * 8), bands_pct: Object.fromEntries(Object.entries(bands).map(([key, value]) => [key, Math.round(value * 100 / total)])) }
}

function error(status, message, extra = {}) {
  return Object.assign(new Error(message), { status, ...extra })
}

function invalid(message) {
  throw error(422, message)
}

function expand(values, length) {
  return Array.from({ length }, (_, index) => values[index % values.length])
}

function expandSteps(steps, length) {
  return expand([...steps], length).join('')
}

function changedIndexes(from, to) {
  const indexes = []
  for (let index = 0; index < to.length; index++) {
    if (from[index] !== to[index]) indexes.push(index)
  }
  return indexes
}

function defaultTrack(id, options, length) {
  const track = {
    id,
    kind: options.kind ?? 'drum',
    source: options.source ?? 'factory:kick_boom',
    gain_db: options.gain_db ?? 0,
    pan: options.pan ?? 0,
    mute: options.mute ?? false,
    solo: options.solo ?? false,
    pitch: options.pitch ?? 0,
    steps: '.'.repeat(length),
    velocity: Array(length).fill(options.kind === 'snare' || id === 'snare' ? 0.9 : 1),
    fx: []
  }
  if (options.notes !== undefined) track.notes = structuredClone(options.notes)
  if (options.slices !== undefined) track.slices = options.slices
  return track
}

function canonicalize(value) {
  if (Array.isArray(value)) return value.map(canonicalize)
  if (value && typeof value === 'object') {
    return Object.fromEntries(
      Object.keys(value).filter(key => key !== 'name').sort().map(key => [key, canonicalize(value[key])])
    )
  }
  return value
}

async function sha256(text) {
  if (!globalThis.crypto?.subtle) throw new Error('crypto.subtle is unavailable')
  const bytes = new TextEncoder().encode(text)
  const digest = await globalThis.crypto.subtle.digest('SHA-256', bytes)
  return [...new Uint8Array(digest)].map(byte => byte.toString(16).padStart(2, '0')).join('')
}

async function sha256Bytes(bytes) {
  if (!globalThis.crypto?.subtle) throw new Error('crypto.subtle is unavailable')
  const digest = await globalThis.crypto.subtle.digest('SHA-256', bytes)
  return [...new Uint8Array(digest)].map(byte => byte.toString(16).padStart(2, '0')).join('')
}

function toBase64(bytes) {
  if (typeof Buffer !== 'undefined') return Buffer.from(bytes).toString('base64')
  let binary = ''
  const chunkSize = 0x8000
  for (let offset = 0; offset < bytes.length; offset += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + chunkSize))
  }
  return btoa(binary)
}

function invertDiff(diff) {
  if (diff.field === 'track') {
    return { ...diff, action: diff.action === 'add' ? 'remove' : 'add' }
  }
  return { ...diff, from: clone(diff.to), to: clone(diff.from) }
}

export function createMockBackend({ emit = () => {}, synth, fetchImpl = globalThis.fetch } = {}) {
  const projects = new Map()
  const audioByHash = new Map()
  const editingByName = new Map()
  let logicalTime = 0
  let catalogRequest = null
  const renderAudio = typeof synth === 'function'
    ? synth
    : async () => { throw new Error('mock synth is not configured') }

  async function flockCatalog() {
    if (!catalogRequest) catalogRequest = (async () => {
      if (typeof fetchImpl !== 'function') throw error(500, 'flock catalog fetch is unavailable')
      const response = await fetchImpl('/rookery/flock/birds.json')
      if (!response?.ok) throw error(response?.status || 500, 'could not load /rookery/flock/birds.json')
      return response.json()
    })()
    return clone(await catalogRequest)
  }

  function emitEvent(name, payload) {
    emit(`plugin.rookery.${name}`, payload)
  }

  function timestamp() {
    logicalTime = Math.max(Date.now(), logicalTime + 1)
    return new Date(logicalTime).toISOString()
  }

  function getState(name) {
    return projects.get(name)
  }

  function requireProject(name) {
    const state = getState(name)
    if (!state) throw error(404, `no project "${name}"`)
    return state
  }

  function activeFlockCombos(flock, catalog) {
    const entries = flock.perches.map((perch, slot) => ({ perch, slot })).filter(entry => entry.perch && !entry.perch.mute)
    const solos = entries.filter(entry => entry.perch.solo)
    const audible = solos.length ? solos : entries
    const ids = new Set(audible.map(entry => entry.perch.bird))
    const roles = new Set(audible.map(entry => catalog.birds.find(bird => bird.id === entry.perch.bird)?.role || (entry.perch.bird === 'corvus' ? 'crown' : '')))
    const family = catalog.scales[flock.scale]?.family
    return catalog.combos.filter(combo => {
      const requires = combo.requires || {}
      return (requires.birds || []).every(id => ids.has(id)) && (requires.roles || []).every(role => roles.has(role)) &&
        (!requires.scale_family || requires.scale_family === family) && (!requires.weather || requires.weather === flock.weather)
    }).map(combo => combo.id)
  }

  function validateFlock(value, catalog) {
    if (!value || typeof value !== 'object' || Array.isArray(value)) invalid('flock must be an object')
    const flatKeys = { Db: 'C#', Eb: 'D#', Gb: 'F#', Ab: 'G#', Bb: 'A#' }
    const keys = new Set(['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'])
    const key = flatKeys[value.key] || value.key
    if (!keys.has(key)) invalid('key must be a supported sharp/flat spelling from C through B')
    if (!catalog.scales[value.scale]) invalid('scale must be one of the six catalog scales')
    if (!Array.isArray(value.progression) || value.progression.length < 1 || value.progression.length > 8 ||
        value.progression.some(chord => !Object.hasOwn(catalog.chordTables.romanDegrees, chord))) invalid('progression must contain 1 to 8 recognized Roman-numeral chords')
    if (!['clear', 'dust', 'rain', 'wind'].includes(value.weather)) invalid('weather must be clear, dust, rain, or wind')
    if (!Array.isArray(value.perches) || ![6, 7].includes(value.perches.length)) invalid('perches must contain exactly 6 or 7 slots')
    const birds = new Map([...catalog.birds, catalog.corvus].map(bird => [bird.id, bird]))
    const ordinary = new Set(catalog.birds.map(bird => bird.id))
    const perches = value.perches.map((perch, slot) => {
      if (perch == null) return null
      if (!perch || typeof perch !== 'object' || typeof perch.bird !== 'string' || !birds.has(perch.bird)) invalid(`unknown bird at perch ${slot}`)
      if (perch.bird === 'corvus' ? slot !== 6 : slot === 6) invalid('Corvus may only occupy slot 6')
      if (!['A', 'B', 'C', 'D'].includes(perch.song || 'A')) invalid('song must be A, B, C, or D')
      if (perch.bird === 'corvus' && (perch.song || 'A') !== 'A') invalid('Corvus sings only song A')
      if (typeof (perch.mute ?? false) !== 'boolean' || typeof (perch.solo ?? false) !== 'boolean') invalid('mute and solo must be booleans')
      const gain = perch.gain_db ?? 0, pan = perch.pan ?? 0
      if (!Number.isFinite(gain) || gain < -24 || gain > 12) invalid('gain_db must be between -24 and 12')
      if (!Number.isFinite(pan) || pan < -1 || pan > 1) invalid('pan must be between -1 and 1')
      return { bird: perch.bird, song: perch.song || 'A', mute: perch.mute ?? false, solo: perch.solo ?? false, gain_db: gain, pan }
    })
    if (perches[6] == null && perches.length === 7) perches.pop()
    const seenBirds = new Set(), roleCounts = new Map()
    for (let slot = 0; slot < perches.length; slot++) {
      const perch = perches[slot]
      if (!perch) continue
      if (seenBirds.has(perch.bird)) invalid(`bird ${perch.bird} cannot occupy more than one slot`)
      seenBirds.add(perch.bird)
      if (perch.bird !== 'corvus') {
        const role = birds.get(perch.bird).role
        roleCounts.set(role, (roleCounts.get(role) || 0) + 1)
        if (roleCounts.get(role) > 2) invalid(`at most two birds may occupy the ${role} role`)
      }
    }
    const seen = value.seen || []
    const unlocked = value.unlocked || []
    if (!Array.isArray(seen) || seen.some(id => !ordinary.has(id)) || new Set(seen).size !== seen.length) invalid('seen must contain unique ordinary bird IDs')
    const comboIds = new Set(catalog.combos.map(combo => combo.id))
    if (!Array.isArray(unlocked) || unlocked.some(id => !comboIds.has(id)) || new Set(unlocked).size !== unlocked.length) invalid('unlocked must contain unique combo IDs')
    const required = new Set(catalog.secretUnlock.seenRequired)
    if (seenBirds.has('corvus') && [...required].some(id => !seen.includes(id))) invalid('Corvus requires all ordinary birds to have been seen')
    return { key, scale: value.scale, progression: [...value.progression], weather: value.weather, perches, seen: [...seen], unlocked: [...unlocked] }
  }

  function flockSongDAllowed(flock, birdId, catalog) {
    return activeFlockCombos(flock, catalog).some(id => {
      const combo = catalog.combos.find(item => item.id === id)
      return combo?.bonus?.song_overrides?.[birdId] === 'D'
    })
  }

  function applyFlockEdit(beforeValue, args, catalog) {
    const before = beforeValue == null ? clone(DEFAULT_FLOCK) : validateFlock(beforeValue, catalog)
    const previouslySeen = new Set(before.seen)
    if (!args || typeof args !== 'object' || Array.isArray(args) || typeof args.action !== 'string') invalid('flock edit requires an action')
    const schemas = {
      template: ['action', 'template'], perch: ['action', 'bird', 'slot', 'song'], unperch: ['action', 'bird', 'slot'],
      song: ['action', 'bird', 'song'], mute: ['action', 'bird', 'on'], solo: ['action', 'bird', 'on'], mix: ['action', 'bird', 'gain_db', 'pan'],
      harmony: ['action', 'key', 'scale', 'progression'], weather: ['action', 'weather']
    }
    const allowed = schemas[args.action]
    if (!allowed) invalid(`unknown flock action: ${args.action}`)
    if (Object.keys(args).some(key => !allowed.includes(key))) invalid(`unknown arguments for flock action ${args.action}`)
    const result = clone(before)
    const perches = result.perches
    if (args.action === 'template') {
      if (Object.keys(args).length !== 2) invalid('template action requires only template')
      const template = catalog.templates.find(item => args.template === item.id || args.template === item.name)
      if (!template) invalid(`unknown flock template: ${args.template}`)
      const roleOrder = ['bass', 'keys', 'pad', 'lead', 'arp', 'call']
      const byId = new Map(catalog.birds.map(bird => [bird.id, bird]))
      const landing = [...template.birds].sort((a, b) => roleOrder.indexOf(byId.get(a.bird)?.role) - roleOrder.indexOf(byId.get(b.bird)?.role) || a.bird.localeCompare(b.bird))
      const next = Array(6).fill(null)
      landing.forEach((item, slot) => { next[slot] = { bird: item.bird, song: item.song, mute: false, solo: false } })
      Object.assign(result, { key: template.key, scale: template.scale, progression: clone(template.progression), weather: template.weather,
        perches: next.concat(perches.length === 7 ? [clone(perches[6])] : []) })
    } else if (args.action === 'harmony') {
      if (Object.keys(args).length < 2) invalid('harmony requires at least one harmony field')
      if (Object.hasOwn(args, 'key')) result.key = args.key
      if (Object.hasOwn(args, 'scale')) result.scale = args.scale
      if (Object.hasOwn(args, 'progression')) result.progression = clone(args.progression)
    } else if (args.action === 'weather') {
      if (Object.keys(args).length !== 2) invalid('weather action requires weather')
      result.weather = args.weather
    } else {
      const birdId = args.bird
      const currentSlot = perches.findIndex(perch => perch?.bird === birdId)
      if (args.action === 'perch') {
        if (typeof birdId !== 'string' || !catalog.birds.some(bird => bird.id === birdId) && birdId !== 'corvus') invalid(`unknown bird: ${birdId}`)
        const song = args.song ?? 'A'
        if (!['A', 'B', 'C', 'D'].includes(song)) invalid('song must be A, B, C, or D')
        let slot = args.slot
        if (slot == null) slot = currentSlot >= 0 ? currentSlot : birdId === 'corvus' && perches.length === 6 ? 6 : perches.slice(0, 6).findIndex(perch => !perch)
        const appendsCorvus = birdId === 'corvus' && slot === 6 && perches.length === 6
        if (!Number.isInteger(slot) || !(slot >= 0 && slot < perches.length || appendsCorvus)) invalid('slot must identify an available zero-based perch')
        if (birdId === 'corvus' ? slot !== 6 : slot === 6) invalid('Corvus may only occupy slot 6')
        if (slot < perches.length && perches[slot] && perches[slot].bird !== birdId) invalid(`slot ${slot} is occupied; unperch its bird first`)
        if (appendsCorvus) perches.push(null)
        if (currentSlot >= 0) {
          const prior = perches[currentSlot]
          if (currentSlot !== slot) perches[currentSlot] = null
          perches[slot] = { bird: birdId, song: Object.hasOwn(args, 'song') ? song : prior.song, mute: prior.mute, solo: prior.solo }
        } else perches[slot] = { bird: birdId, song, mute: false, solo: false }
      } else if (args.action === 'unperch') {
        if (Object.hasOwn(args, 'bird') === Object.hasOwn(args, 'slot')) invalid('unperch requires exactly one of bird or slot')
        const slot = Object.hasOwn(args, 'slot') ? args.slot : currentSlot
        if (!Number.isInteger(slot) || slot < 0 || slot >= perches.length) invalid('slot must be a valid zero-based perch')
        if (Object.hasOwn(args, 'bird') && currentSlot < 0) invalid(`bird is not perched: ${birdId}`)
        perches[slot] = null
      } else {
        if (currentSlot < 0) invalid(`bird is not perched: ${birdId}`)
        if (args.action === 'song') {
          if (!['A', 'B', 'C', 'D'].includes(args.song)) invalid('song must be A, B, C, or D')
          perches[currentSlot].song = args.song
        } else if (args.action === 'mix') {
          const fields = ['gain_db', 'pan'].filter(field => Object.hasOwn(args, field))
          if (!fields.length) invalid('mix requires gain_db and/or pan')
          for (const field of fields) {
            const value = args[field]
            if (!Number.isFinite(value) || field === 'gain_db' && (value < -24 || value > 12) || field === 'pan' && (value < -1 || value > 1)) invalid(`${field} is out of range`)
            perches[currentSlot][field] = value
          }
        } else {
          if (typeof args.on !== 'boolean') invalid('on must be a boolean')
          perches[currentSlot][args.action] = args.on
        }
      }
    }
    const explicitD = args.action === 'song' || args.action === 'perch' && args.song === 'D'
    const dSingers = new Set(result.perches.filter(perch => perch?.song === 'D').map(perch => perch.bird))
    if (!explicitD) result.perches.forEach(perch => { if (perch?.song === 'D') perch.song = 'A' })
    let checked = validateFlock(result, catalog)
    if (!explicitD) for (const perch of checked.perches) if (perch && dSingers.has(perch.bird) && flockSongDAllowed(checked, perch.bird, catalog)) perch.song = 'D'
    checked.seen = [...new Set([...checked.seen, ...checked.perches.filter(perch => perch && catalog.birds.some(bird => bird.id === perch.bird)).map(perch => perch.bird)])].sort()
    checked.unlocked = [...new Set([...checked.unlocked, ...activeFlockCombos(checked, catalog)])].sort()
    const required = new Set(catalog.secretUnlock.seenRequired)
    if ([...required].every(id => checked.seen.includes(id)) && ![...required].every(id => previouslySeen.has(id)) && checked.perches.length === 6) {
      checked.perches.push({ bird: 'corvus', song: 'A', mute: false, solo: false })
    }
    return validateFlock(checked, catalog)
  }

  function flockDiffs(beforeValue, afterValue, change, catalog) {
    const before = beforeValue == null ? clone(DEFAULT_FLOCK) : validateFlock(beforeValue, catalog)
    const after = afterValue == null ? clone(DEFAULT_FLOCK) : validateFlock(afterValue, catalog)
    const diffs = []
    if (change === 'template') {
      const roleOrder = ['bass', 'keys', 'pad', 'lead', 'arp', 'call', 'crown']
      const birds = new Map([...catalog.birds, catalog.corvus].map(bird => [bird.id, bird]))
      const indexes = Array.from({ length: Math.max(before.perches.length, after.perches.length) }, (_, i) => i)
        .filter(i => !flockValueEqual(before.perches[i] ?? null, after.perches[i] ?? null))
        .sort((a, b) => {
          const pa = after.perches[a] || before.perches[a], pb = after.perches[b] || before.perches[b]
          return roleOrder.indexOf(birds.get(pa.bird)?.role) - roleOrder.indexOf(birds.get(pb.bird)?.role) || a - b
        })
      for (const slot of indexes) {
        const from = before.perches[slot] ?? null, to = after.perches[slot] ?? null
        diffs.push({ field: 'flock', change: 'template', slot, bird: (to || from).bird, from: clone(from), to: clone(to) })
      }
    } else {
      for (let slot = 0; slot < Math.max(before.perches.length, after.perches.length); slot++) {
        const from = before.perches[slot] ?? null, to = after.perches[slot] ?? null
        if (flockValueEqual(from, to)) continue
        const changes = from == null ? ['perch'] : to == null ? ['unperch'] : from.bird === to.bird
          ? (() => {
            const changed = ['song', 'mute', 'solo', 'gain_db', 'pan'].filter(field => from[field] !== to[field])
            return changed.length && changed.every(field => field === 'gain_db' || field === 'pan') ? ['mix'] : changed
          })() : ['perch']
        for (const field of changes.length ? changes : ['perch']) diffs.push({ field: 'flock', change: field, slot, bird: (to || from).bird, from: clone(from), to: clone(to) })
      }
    }
    if (before.key !== after.key || before.scale !== after.scale || !flockValueEqual(before.progression, after.progression)) {
      const harmony = fields => Object.fromEntries(fields.map(field => [field, clone(after[field])]))
      diffs.push({ field: 'flock', change: 'harmony', from: Object.fromEntries(['key', 'scale', 'progression'].map(k => [k, clone(before[k])])), to: harmony(['key', 'scale', 'progression']) })
    }
    if (before.weather !== after.weather) diffs.push({ field: 'flock', change: 'weather', from: before.weather, to: after.weather })
    return diffs
  }

  function projectView(state) {
    return {
      project: clone(state.project),
      rev: state.rev,
      render: state.render == null ? null : clone(state.render),
      agent_editing: state.agent_editing
    }
  }

  function createProject({ name, bpm = 90, bars = 4, swing = 0 } = {}) {
    if (typeof name !== 'string' || !name.trim()) invalid('name must be a non-empty string')
    validateMeta({ bpm, bars, swing })
    const project = {
      schema: 'rookery.project/1',
      name,
      bpm,
      bars,
      steps_per_bar: 16,
      swing,
      seed: 1337,
      tracks: [],
      master: { fx: [{ type: 'compressor' }, { type: 'limiter', ceiling_db: -1 }] }
    }
    const state = {
      project,
      rev: 0,
      render: null,
      agent_editing: editingByName.get(name) ?? false,
      history: [],
      updated_at: timestamp()
    }
    projects.set(name, state)
    emitEvent('project.updated', { name, rev: state.rev, source: 'agent', tool: 'rookery_new', diff: [] })
    return projectView(state)
  }

  function lifecycleProject(options = {}) {
    let { name, bpm = 90, bars = 4, swing = 0, from } = options
    if (name === undefined) {
      let index = 1
      while (projects.has(`beat-${index}`)) index++
      name = `beat-${index}`
    }
    if (typeof name !== 'string' || !/^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$/.test(name) || name.endsWith('.') || /^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)/i.test(name)) invalid('name must be a simple 1-64 character name')
    if (projects.has(name)) throw error(409, `project already exists: ${name}`)
    if (Object.hasOwn(options, 'from') && typeof from !== 'string') invalid('from must be a project name')
    let project
    if (from !== undefined) {
      const source = requireProject(from)
      project = clone(source.project)
      project.name = name
    } else {
      validateMeta({ bpm, bars, swing })
      const length = bars * 16
      project = {
        schema: 'rookery.project/1', name, bpm, bars, steps_per_bar: 16, swing, seed: 1337,
        tracks: [
          defaultTrack('kick', { source: 'factory:kick_punch' }, length),
          defaultTrack('snare', { source: 'factory:snare_snap' }, length),
          defaultTrack('hat', { source: 'factory:hat_tight' }, length)
        ], master: { fx: [] }
      }
    }
    const state = { project, rev: 1, render: null, agent_editing: false, history: [], updated_at: timestamp() }
    projects.set(name, state)
    emitEvent('project.created', { name, ...(from ? { from } : {}) })
    return projectView(state)
  }

  function validateMeta(values) {
    if (!Number.isFinite(values.bpm) || values.bpm < 30 || values.bpm > 300) {
      invalid('bpm must be between 30 and 300')
    }
    if (![4, 8].includes(values.bars)) invalid('bars must be 4 or 8')
    if (!Number.isFinite(values.swing) || values.swing < 0 || values.swing > 1) {
      invalid('swing must be between 0 and 1')
    }
  }

  function updateWrite(state, body, source, before, diff, { recordHistory = true } = {}) {
    if (recordHistory) state.history.push({ before, diff: clone(diff) })
    state.rev += 1
    state.render = null
    state.updated_at = timestamp()
    emitEvent('project.updated', {
      name: state.project.name,
      rev: state.rev,
      source,
      tool: body.tool ?? null,
      diff: clone(diff)
    })
    return { project: clone(state.project), rev: state.rev, diff: clone(diff) }
  }

  async function applyEdit(state, body, source, checkRev, { deferCommit = false } = {}) {
    if (!body || typeof body !== 'object' || Array.isArray(body)) invalid('edit body must be an object')
    if (typeof body.name !== 'string' || !body.name) invalid('name is required')
    if (checkRev && body.rev != null && body.rev !== state.rev) {
      throw error(409, 'stale rev', { rev: state.rev })
    }

    const before = clone(state.project)
    const project = clone(state.project)
    const diff = []
    const length = loopLength(project)

    if (body.op === 'clear') {
      if (Object.keys(body).some(key => !['name', 'rev', 'op', 'track'].includes(key))) invalid('clear accepts only an optional track')
      const targets = body.track == null ? project.tracks : project.tracks.filter(track => track.id === body.track)
      if (body.track != null && !targets.length) throw error(404, `track not found: ${body.track}`)
      for (const track of targets) {
        const next = '.'.repeat(length)
        const indexes = changedIndexes(track.steps, next)
        if (indexes.length) { diff.push({ track: track.id, field: 'steps', from: track.steps, to: next, steps: indexes }); track.steps = next }
      }
      if (!diff.length) invalid('nothing to clear')
    } else if (body.op === 'steps') {
      const track = project.tracks.find(candidate => candidate.id === body.track)
      if (!track) invalid(`unknown track "${body.track}"`)
      if (typeof body.steps !== 'string' || !/^[x.0-9]+$/.test(body.steps)) {
        invalid('steps may only contain x, . and digits')
      }
      const nextSteps = expandSteps(body.steps, length)
      const stepIndexes = changedIndexes(track.steps, nextSteps)
      if (stepIndexes.length) {
        diff.push({ track: track.id, field: 'steps', from: track.steps, to: nextSteps, steps: stepIndexes })
        track.steps = nextSteps
      }

      if (body.velocity !== undefined) {
        if (!Array.isArray(body.velocity) || body.velocity.length === 0 ||
            body.velocity.some(value => !Number.isFinite(value) || value < 0 || value > 1)) {
          invalid('velocity must be a non-empty array of numbers from 0 to 1')
        }
        const nextVelocity = expand(body.velocity, length)
        const velocityIndexes = changedIndexes(track.velocity, nextVelocity)
        if (velocityIndexes.length) {
          diff.push({ track: track.id, field: 'velocity', from: clone(track.velocity), to: nextVelocity, steps: velocityIndexes })
          track.velocity = nextVelocity
        }
      }
    } else if (body.op === 'track') {
      if (typeof body.id !== 'string' || !body.id.trim()) invalid('track id must be a non-empty string')
      const index = project.tracks.findIndex(track => track.id === body.id)
      if (body.action === 'add') {
        if (index >= 0) invalid(`track "${body.id}" already exists`)
        for (const key of TRACK_FIELDS) {
          if (body[key] !== undefined) validateTrackField(key, body[key])
        }
        project.tracks.push(defaultTrack(body.id, body, length))
        diff.push({ track: body.id, field: 'track', action: 'add' })
      } else if (body.action === 'remove') {
        if (index < 0) invalid(`unknown track "${body.id}"`)
        project.tracks.splice(index, 1)
        diff.push({ track: body.id, field: 'track', action: 'remove' })
      } else if (body.action === 'set') {
        if (index < 0) invalid(`unknown track "${body.id}"`)
        const track = project.tracks[index]
        const fields = TRACK_FIELDS.filter(key => Object.hasOwn(body, key))
        if (!fields.length) invalid('track set requires at least one track field')
        for (const key of fields) {
          validateTrackField(key, body[key])
          if (key === 'kind' && body[key] !== track[key]) {
            invalid('track kind cannot be changed after creation')
          }
          if (body[key] !== track[key]) {
            diff.push({ track: track.id, field: key, from: clone(track[key]), to: clone(body[key]) })
            track[key] = body[key]
          }
        }
      } else {
        invalid('track action must be add, remove or set')
      }
    } else if (body.op === 'mix') {
      if (!Array.isArray(body.fx)) invalid('fx must be an array')
      const target = body.target
      const chain = target === 'master'
        ? project.master?.fx
        : project.tracks.find(track => track.id === target)?.fx
      if (!chain) invalid(`unknown mix target "${target}"`)
      const nextFx = clone(body.fx)
      if (target === 'master') project.master.fx = nextFx
      else project.tracks.find(track => track.id === target).fx = nextFx
      diff.push({ track: target, field: 'fx', from: clone(chain), to: clone(nextFx) })
    } else if (body.op === 'meta') {
      const nextMeta = {
        bpm: body.bpm ?? project.bpm,
        bars: body.bars ?? project.bars,
        swing: body.swing ?? project.swing
      }
      validateMeta(nextMeta)
      for (const key of ['bpm', 'bars', 'swing']) {
        if (Object.hasOwn(body, key) && body[key] !== project[key]) {
          diff.push({ field: key, from: project[key], to: body[key] })
          project[key] = body[key]
        }
      }
      if (project.bars !== before.bars) {
        const nextLength = loopLength(project)
        for (const track of project.tracks) {
          track.steps = expandSteps(track.steps, nextLength)
          track.velocity = expand(track.velocity, nextLength)
        }
      }
    } else if (body.op === 'arrange') {
      if (Object.keys(body).some(key => !['name', 'rev', 'op', 'sections', 'tool'].includes(key))) invalid('arrange accepts only sections')
      if (body.sections !== null) {
        if (!Array.isArray(body.sections) || body.sections.length < 1 || body.sections.length > 16) invalid('sections must contain 1 to 16 items')
        const ids = new Set(), trackIds = new Set(project.tracks.map(track => track.id))
        const perches = project.flock?.perches || []
        const loopSeconds = project.bars * 4 * 60 / project.bpm
        const sections = body.sections.map(section => {
          if (!section || typeof section !== 'object' || Array.isArray(section) || Object.keys(section).some(key => !['id', 'repeat', 'mute'].includes(key))) invalid('each section must contain id, repeat and mute')
          if (typeof section.id !== 'string' || !/^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$/.test(section.id) || ids.has(section.id)) invalid('section id must be a unique track-style id')
          ids.add(section.id)
          if (!Number.isInteger(section.repeat) || section.repeat < 1 || section.repeat > 8) invalid('repeat must be an integer from 1 to 8')
          if (!Array.isArray(section.mute)) invalid('mute must be an array')
          const muteSeen = new Set()
          for (const item of section.mute) {
            if (typeof item !== 'string' || muteSeen.has(item)) invalid('mute entries must be unique track or bird ids')
            muteSeen.add(item)
            if (/^bird:\d+$/.test(item)) {
              const slot = Number(item.slice(5))
              if (slot > 6 || !perches[slot]) invalid(`unknown mute target: ${item}`)
            } else if (!trackIds.has(item)) invalid(`unknown mute target: ${item}`)
          }
          return { id: section.id, repeat: section.repeat, mute: [...section.mute] }
        })
        const songSeconds = sections.reduce((sum, section) => sum + section.repeat * loopSeconds, 0)
        if (songSeconds > 180) invalid(`song length ${songSeconds.toFixed(1)} s exceeds the 180 s limit`)
        project.arrangement = { sections }
      } else delete project.arrangement
      diff.push({ field: 'arrangement', from: clone(before.arrangement ?? null), to: clone(project.arrangement ?? null) })
    } else if (body.op === 'fx_param') {
      const target = body.target
      const chain = target === 'master'
        ? project.master?.fx
        : project.tracks.find(track => track.id === target)?.fx
      if (!chain) invalid(`unknown FX target "${target}"`)
      if (!Number.isInteger(body.index) || body.index < 0 || body.index >= chain.length) {
        invalid('fx index is out of range')
      }
      if (typeof body.param !== 'string' || !body.param) invalid('param must be a non-empty string')
      if (!Number.isFinite(body.value)) invalid('fx value must be a number')
      const fx = chain[body.index]
      if (!fx.params || !Object.hasOwn(fx.params, body.param)) invalid(`unknown FX param "${body.param}"`)
      const from = clone(chain)
      fx.params[body.param] = body.value
      diff.push({ track: target, field: 'fx', from, to: clone(chain) })
    } else if (body.op === 'flock') {
      const catalog = await flockCatalog()
      const beforeFlock = project.flock ?? null
      const args = Object.fromEntries(Object.entries(body).filter(([key]) => !['name', 'rev', 'op', 'tool'].includes(key)))
      project.flock = applyFlockEdit(beforeFlock, args, catalog)
      diff.push(...flockDiffs(beforeFlock, project.flock, args.action, catalog))
    } else if (body.op === 'groove') {
      const groove = body.groove
      if (typeof groove !== 'string' || !groove) invalid('groove must be a non-empty string')
      let grooves
      try {
        const response = await fetchImpl('/skills/rookery/grooves.json')
        if (!response?.ok) throw new Error('missing grooves')
        grooves = await response.json()
      } catch {
        grooves = { boom_bap: { kick: 'x...x...x...x...', snare: '....x.......x...' }, four_on_floor: { kick: 'x...x...x...x...', hat: 'x.x.x.x.x.x.x.x.' } }
      }
      const template = (grooves.templates || []).find(item => item.id === groove || item.name === groove)
      const pattern = grooves[groove] || grooves.grooves?.[groove] || template?.tracks
      if (!pattern || typeof pattern !== 'object') invalid(`unknown groove "${groove}"`)
      for (const [id, steps] of Object.entries(pattern)) {
        const track = project.tracks.find(item => item.id === id)
        if (!track || !steps || typeof steps.steps !== 'string' && typeof steps !== 'string') continue
        const next = expandSteps(typeof steps === 'string' ? steps : steps.steps, length)
        const indexes = changedIndexes(track.steps, next)
        if (indexes.length) { diff.push({ track: id, field: 'steps', from: track.steps, to: next, steps: indexes }); track.steps = next }
        if (Array.isArray(steps.velocity)) {
          const velocity = expand(steps.velocity, length)
          if (!flockValueEqual(track.velocity, velocity)) { diff.push({ track: id, field: 'velocity', from: clone(track.velocity), to: velocity, steps: changedIndexes(track.velocity, velocity) }); track.velocity = velocity }
        }
      }
      if (!diff.length) invalid('groove made no changes')
    } else if (body.op === 'rookery_apply') {
      // Alias retained for callers that wrap their operations in the batch op.
      invalid('rookery_apply requires the apply route')
    } else {
      invalid(`unknown op "${body.op}"`)
    }

    if (project.arrangement?.sections && body.op !== 'arrange') {
      const trackIds = new Set(project.tracks.map(track => track.id))
      const perches = project.flock?.perches || []
      const cleaned = project.arrangement.sections.map(section => ({ ...section, mute: section.mute.filter(item => item.startsWith('bird:') ? !!perches[Number(item.slice(5))] : trackIds.has(item)) }))
      if (!flockValueEqual(cleaned, project.arrangement.sections)) {
        const from = clone(project.arrangement)
        project.arrangement = { sections: cleaned }
        diff.push({ field: 'arrangement', from, to: clone(project.arrangement) })
      }
    }
    state.project = project
    if (deferCommit) return { project: clone(project), diff: clone(diff) }
    return updateWrite(state, body, source, before, diff)
  }

  async function applyBatch(state, body, source, checkRev) {
    if (!Array.isArray(body.ops) || !body.ops.length) invalid('ops must be a non-empty array')
    if (checkRev && body.rev != null && body.rev !== state.rev) throw error(409, 'stale rev', { rev: state.rev })
    const working = { project: clone(state.project), rev: state.rev, history: [] }
    const diff = []
    for (const op of body.ops) {
      if (!op || typeof op !== 'object' || Array.isArray(op) || !op.op) invalid('each batch op must be an edit object')
      const result = await applyEdit(working, { ...op, name: state.project.name }, source, false, { deferCommit: true })
      diff.push(...result.diff)
    }
    if (!diff.length) invalid('batch made no changes')
    state.project = working.project
    return updateWrite(state, { ...body, tool: body.tool || 'rookery_apply' }, source, null, diff)
  }

  function validateTrackField(field, value) {
    if (field === 'kind' || field === 'source') {
      if (typeof value !== 'string' || !value) invalid(`${field} must be a non-empty string`)
      return
    }
    if (field === 'notes') {
      const ok = Array.isArray(value) && value.every(n => n && Number.isInteger(n.step) && n.step >= 0 && Number.isFinite(n.len) && n.len > 0 && (typeof n.pitch === 'string' || Number.isFinite(n.pitch)))
      if (!ok) invalid('notes must be a list of {step, len, pitch}')
      return
    }
    if (field === 'slices') {
      if (!Number.isInteger(value) || value < 1 || value > 64) invalid('slices must be an integer from 1 to 64')
      return
    }
    if (field === 'mute' || field === 'solo') {
      if (typeof value !== 'boolean') invalid(`${field} must be a boolean`)
      return
    }
    if (!Number.isFinite(value)) invalid(`${field} must be a number`)
    if (field === 'pan' && (value < -1 || value > 1)) invalid('pan must be between -1 and 1')
  }

  function undo(body = {}) {
    if (!body || typeof body !== 'object' || Array.isArray(body)) invalid('undo body must be an object')
    if (typeof body.name !== 'string' || !body.name) invalid('name is required')
    const state = requireProject(body.name)
    const count = body.steps ?? 1
    if (!Number.isInteger(count) || count < 1) invalid('undo steps must be a positive integer')
    if (state.history.length < count) throw error(422, 'nothing to undo')

    const removed = state.history.splice(state.history.length - count, count)
    const target = removed[0].before
    const reverseDiff = removed.toReversed().flatMap(entry => entry.diff.toReversed().map(invertDiff))
    const internal = { tool: 'rookery_undo' }
    state.project = clone(target)
    return updateWrite(state, internal, 'agent', null, reverseDiff, { recordHistory: false })
  }

  async function render(name, song = false) {
    const state = requireProject(name)
    const project = clone(state.project)
    const rev = state.rev
    if (song && !project.arrangement?.sections) invalid('this project has no arrangement; add one with the arrange op')
    const sections = song ? project.arrangement.sections : null
    const loopSeconds = project.bars * 4 * 60 / project.bpm
    const songSeconds = song ? sections.reduce((sum, section) => sum + section.repeat * loopSeconds, 0) : loopSeconds
    const hashProject = clone(project)
    if (!song) delete hashProject.arrangement
    const hashInput = `${JSON.stringify(canonicalize(hashProject))}|mock-1${song ? '|song' : ''}`
    emitEvent('render.started', { name, rev })
    try {
      const result = await renderAudio(clone(project))
      const hash = await sha256(hashInput)
      const durationSamples = song ? Math.round(songSeconds * (result.sample_rate ?? 44100)) : result.duration_samples
      const sampleRate = result.sample_rate ?? 44100
      const expectedSamples = song ? durationSamples : Math.round(project.bars * 4 * 60 / project.bpm * sampleRate)
      const meters = Object.fromEntries(Object.entries(result.meters ?? Object.fromEntries(project.tracks.map(track => [track.id, { rms_db: -22, peak_db: -6 }]))).map(([id, meter]) => {
        const gain = project.tracks.find(track => track.id === id)?.gain_db || 0
        return [id, { ...meter, rms_db: Math.max(-60, Math.min(0, (meter.rms_db ?? -22) + gain)), peak_db: Math.max(-60, Math.min(0, (meter.peak_db ?? -6) + gain)) }]
      }))
      const master = result.master ?? {}
      const peakDb = master.peak_db
      const rmsDb = master.rms_db
      const lufs = master.lufs_estimate
      const lengthPass = durationSamples === expectedSamples
      const clippingPass = Number.isFinite(peakDb) && peakDb <= -1
      const silentPass = Number.isFinite(rmsDb) && rmsDb > -50
      const loudnessPass = Number.isFinite(lufs) && Math.abs(lufs - (-14)) <= 2
      const report = {
        length_exact: {
          pass: lengthPass,
          value: durationSamples,
          target: `exactly ${expectedSamples} samples`,
          ...(lengthPass ? {} : { hint: 'render at the exact loop length for the selected BPM and bars' })
        },
        no_clipping: {
          pass: clippingPass,
          value: peakDb,
          target: '≤ −1.0 dBTP',
          ...(clippingPass ? {} : { hint: 'lower the master or track gain until the peak is at or below −1.0 dBTP' })
        },
        loudness: {
          pass: loudnessPass,
          value: lufs,
          target: '−14 ± 2 LUFS',
          ...(loudnessPass ? {} : { hint: 'adjust the master gain toward −14 LUFS' })
        },
        seam_click: { pass: true, value: 0.6 },
        not_silent: {
          pass: silentPass,
          value: rmsDb,
          target: '> −50 dBFS',
          ...(silentPass ? {} : { hint: 'add audible hits or raise the track gain above −50 dBFS' })
        },
        deterministic: { pass: true, value: hash.slice(0, 12) }
      }
      const renderView = {
        hash,
        rev,
        audio_url: result.audio_url,
        report,
        meters: clone(meters),
        mix: clone(result.mix ?? plausibleMix(project)),
        duration_samples: durationSamples,
        sample_rate: sampleRate,
        flock_events: clone(result.flock_events ?? {}),
        kick_onsets: clone(result.kick_onsets ?? []),
        flock_active_combos: clone(result.flock_active_combos ?? [])
      }
      if (song) {
        renderView.song = true
        let start = 0
        renderView.sections = sections.map(section => {
          const timing = { id: section.id, start_s: start, end_s: start + section.repeat * loopSeconds }
          start = timing.end_s
          return timing
        })
        if (result.wav && result.wav.length >= 44 && String.fromCharCode(...result.wav.subarray(0, 4)) === 'RIFF') {
          const source = result.wav, targetSamples = durationSamples, blockAlign = new DataView(source.buffer, source.byteOffset, source.byteLength).getUint16(32, true)
          const pcmLength = targetSamples * blockAlign
          const wav = new Uint8Array(44 + pcmLength)
          wav.set(source.subarray(0, 44))
          for (let offset = 0; offset < pcmLength; offset += source.length - 44) wav.set(source.subarray(44, 44 + Math.min(source.length - 44, pcmLength - offset)), 44 + offset)
          const header = new DataView(wav.buffer)
          header.setUint32(4, 36 + pcmLength, true); header.setUint32(40, pcmLength, true)
          if (typeof Blob !== 'undefined' && typeof URL?.createObjectURL === 'function') renderView.audio_url = URL.createObjectURL(new Blob([wav], { type: 'audio/wav' }))
          result.wav = wav
        }
      }
      if (!song) {
        renderView.balance = clone(result.balance ?? {})
        renderView.mix_notes = clone(result.mix_notes ?? [])
        renderView.fit = clone(result.fit ?? [])
        renderView.ref = result.ref ?? 'none'
      }
      renderView.wav_hash = result.wav ? await sha256Bytes(result.wav) : hash
      if (state.rev === rev) state.render = renderView
      if (result.wav != null) audioByHash.set(hash, result.wav)
      emitEvent('render.done', { name, rev, hash, report: clone(report) })
      return clone(renderView)
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : String(cause)
      emitEvent('render.failed', { name, rev, message })
      throw error(500, message)
    }
  }

  function status() {
    const params = [
      { name: 'Drive', min: 0, max: 1, default: 0.25, value: 0.25 },
      { name: 'Tone', min: 0, max: 1, default: 0.5, value: 0.5 },
      { name: 'Warmth', min: 0, max: 1, default: 0.5, value: 0.5 },
      { name: 'Width', min: 0, max: 1, default: 0.5, value: 0.5 },
      { name: 'Mix', min: 0, max: 1, default: 1, value: 1 }
    ]
    return {
      version: 'mock-1',
      corvus: { found: true, path: CORVUS_PATH, params },
      kits: { factory: [...FACTORY_KITS], user_dir: null, user: [] }
    }
  }

  function listProjects() {
    return [...projects.values()]
      .sort((left, right) => right.updated_at.localeCompare(left.updated_at))
      .map(state => ({
        name: state.project.name,
        rev: state.rev,
        updated_at: state.updated_at,
        bpm: state.project.bpm,
        bars: state.project.bars
      }))
  }

  async function handle(method, path, body) {
    const url = new URL(path, 'http://rookery.local')
    if (method === 'GET' && url.pathname === '/projects') return listProjects()
    if (method === 'GET' && url.pathname === '/status') return status()
    if (method === 'GET' && url.pathname === '/flock/catalog') return flockCatalog()

    if (method === 'POST' && url.pathname === '/project') {
      if (!body || typeof body !== 'object' || Array.isArray(body) || Object.keys(body).some(key => !['name', 'bpm', 'bars', 'swing', 'from'].includes(key))) invalid('project create accepts name, bpm, bars, swing, and from')
      return lifecycleProject(body)
    }

    const renameMatch = url.pathname.match(/^\/project\/([^/]+)\/rename$/)
    if (method === 'POST' && renameMatch) {
      const from = decodeURIComponent(renameMatch[1])
      if (!body || typeof body !== 'object' || Array.isArray(body) || Object.keys(body).length !== 1 || typeof body.to !== 'string') invalid('rename requires a JSON object with to')
      const state = requireProject(from)
      const to = body.to
      if (!/^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$/.test(to) || to.endsWith('.') || /^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)/i.test(to)) invalid('to must be a simple 1-64 character name')
      if (projects.has(to)) throw error(409, `project already exists: ${to}`)
      projects.delete(from); state.project.name = to
      for (const entry of state.history) entry.before.name = to
      projects.set(to, state)
      emitEvent('project.renamed', { from, to })
      return projectView(state)
    }
    const deleteMatch = url.pathname.match(/^\/project\/([^/]+)$/)
    if (method === 'DELETE' && deleteMatch) {
      const name = decodeURIComponent(deleteMatch[1])
      requireProject(name); projects.delete(name); emitEvent('project.deleted', { name })
      return { deleted: name }
    }

    const projectMatch = url.pathname.match(/^\/project\/([^/]+)$/)
    if (method === 'GET' && projectMatch) {
      const name = decodeURIComponent(projectMatch[1])
      const state = requireProject(name)
      const since = url.searchParams.get('since')
      if (since != null && Number(since) === state.rev) return { changed: false, rev: state.rev }
      return projectView(state)
    }

    if (method === 'POST' && url.pathname === '/edit') {
      if (!body || typeof body.name !== 'string') invalid('name is required')
      if (body.op === 'apply' || body.op === 'rookery_apply') return applyBatch(requireProject(body.name), body, 'user', true)
      return applyEdit(requireProject(body.name), body, 'user', true)
    }
    if (method === 'POST' && url.pathname === '/undo') return undo(body)
    if (method === 'POST' && url.pathname === '/render') {
      if (!body || typeof body.name !== 'string') invalid('name is required')
      return render(body.name, body.song === true)
    }

    const audioMatch = url.pathname.match(/^\/audio\/([^/]+)$/)
    if (method === 'GET' && audioMatch) {
      const hash = decodeURIComponent(audioMatch[1])
      const wav = audioByHash.get(hash)
      if (!wav) throw error(404, 'not found')
      return { hash, mime: 'audio/wav', b64: toBase64(wav) }
    }
    throw error(404, `mock: no route ${method} ${url.pathname}`)
  }

  return {
    handle,
    newProject: createProject,
    agentEdit(body) {
      if (!body || typeof body.name !== 'string') invalid('name is required')
      return applyEdit(requireProject(body.name), body, 'agent', false)
    },
    setAgentEditing(name, editing) {
      editingByName.set(name, Boolean(editing))
      const state = getState(name)
      if (state) state.agent_editing = Boolean(editing)
      emitEvent('agent.editing', { name, editing: Boolean(editing) })
    }
  }
}
