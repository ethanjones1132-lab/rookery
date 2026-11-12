// Deterministic flock renderer. No browser APIs and no unseeded entropy live here.
import { synthLoop } from '../preview/mock-audio.js'
import { birds, chordTables, comboSongs, combos, registers, scales } from './birds.js'

const NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
const ROLE_MIX = {
  bass: { gainDb: -4, pan: 0 }, keys: { gainDb: -9, pan: -0.25 },
  pad: { gainDb: -13, pan: -0.6 }, lead: { gainDb: -8, pan: 0.15 },
  arp: { gainDb: -11, pan: 0.35 }, call: { gainDb: -8, pan: -0.1 }
}
const TARGET_PEAK = 10 ** (-1 / 20)
const clamp = (value, min, max) => Math.max(min, Math.min(max, value))

function seedValue(seed, salt = '') {
  let h = (0x811c9dc5 ^ 0x51f15e) >>> 0
  const text = `${seed ?? 0}:${salt}`
  for (let i = 0; i < text.length; i++) h = Math.imul(h ^ text.charCodeAt(i), 0x01000193) >>> 0
  return h >>> 0
}

function mulberry32(seed) {
  let state = seed >>> 0
  return () => {
    state = (state + 0x6d2b79f5) >>> 0
    let t = state
    t = Math.imul(t ^ (t >>> 15), t | 1)
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

function keyPitch(key) {
  const aliases = { Db: 'C#', Eb: 'D#', Gb: 'F#', Ab: 'G#', Bb: 'A#' }
  const name = aliases[key] || key
  const value = NOTE_NAMES.indexOf(name)
  return value < 0 ? 0 : value
}

function progressionDegree(chord) {
  return chordTables.romanDegrees[chord] ?? 0
}

function getPerches(flock) {
  return (Array.isArray(flock?.perches) ? flock.perches : []).map((perch, slot) => perch ? { ...perch, slot } : null)
}

export function detectActiveCombos(flock) {
  const perches = getPerches(flock).filter(Boolean)
  const present = new Set(perches.map(perch => perch.bird))
  const roles = new Set(perches.map(perch => birds.find(bird => bird.id === perch.bird)?.role).filter(Boolean))
  const family = scales[flock?.scale]?.family
  return combos.filter(combo => {
    const requirements = combo.requires
    if (requirements.birds && !requirements.birds.every(id => present.has(id))) return false
    if (requirements.roles && !requirements.roles.every(role => roles.has(role))) return false
    if (requirements.scale_family && requirements.scale_family !== family) return false
    if (requirements.weather && requirements.weather !== flock?.weather) return false
    return true
  }).map(combo => combo.id)
}

export function isCorvusUnlocked(flock) {
  const seen = new Set(flock?.seen || [])
  return birds.every(bird => seen.has(bird.id))
}

function foldToRegister(note, role) {
  const [low, high] = registers[role]
  const candidates = []
  for (let value = low; value <= high; value++) if ((value % 12 + 12) % 12 === (note % 12 + 12) % 12) candidates.push(value)
  return candidates.length ? candidates.reduce((best, value) => Math.abs(value - note) < Math.abs(best - note) ? value : best) : clamp(note, low, high)
}

function chordRootAndScale(flock, bar) {
  const progression = Array.isArray(flock.progression) && flock.progression.length ? flock.progression : ['I']
  const chord = progression[bar % progression.length]
  const scale = scales[flock.scale] || scales.minor
  return { chord, scale, rootDegree: progressionDegree(chord) % scale.semitones.length }
}

function resolveMidi(flock, role, bar, event) {
  const { scale, rootDegree } = chordRootAndScale(flock, bar)
  let degree = ((rootDegree + event.deg) % scale.semitones.length + scale.semitones.length) % scale.semitones.length
  if (event.step % 4 === 0 && !event.harmony && ![0, 2, 4].includes(event.deg)) {
    const choices = [0, 2, 4]
    event = { ...event, deg: choices.reduce((best, candidate) => Math.abs(candidate - event.deg) < Math.abs(best - event.deg) ? candidate : best) }
    degree = (rootDegree + event.deg) % scale.semitones.length
  }
  const note = 60 + keyPitch(flock.key) + scale.semitones[degree] + 12 * (event.oct || 0)
  if (role === 'call') {
    const [low, high] = registers.call
    const tones = [0, 2, 4].map(tone => (keyPitch(flock.key) + scale.semitones[(rootDegree + tone) % scale.semitones.length]) % 12)
    const legal = []
    for (let midi = low; midi <= high; midi++) if (tones.includes(midi % 12)) legal.push(midi)
    if (legal.length) return legal.reduce((best, value) => Math.abs(value - note) < Math.abs(best - note) ? value : best)
  }
  return foldToRegister(note, role)
}

function isMutedByMix(perch, anySolo) {
  return !!perch.mute || (anySolo && !perch.solo)
}

function patternFor(bird, song, activeCombos) {
  const requested = song || 'A'
  if (requested === 'D') return comboSongs[bird.id]?.D || bird.songs.A
  return bird.songs[requested] || bird.songs.A
}

function effectiveSong(bird, song, activeCombos) {
  const override = combos.find(combo => activeCombos.includes(combo.id) && combo.bonus?.song_overrides?.[bird.id])?.bonus?.song_overrides?.[bird.id]
  return override || (song === 'D' ? 'A' : song || 'A')
}

export function buildNoteEvents(project, flock) {
  const bars = Math.max(1, Number(project.bars) || 1)
  const bpm = Math.max(1, Number(project.bpm) || 120)
  const stepsPerBar = Math.max(1, Number(project.steps_per_bar) || 16)
  const barSeconds = 240 / bpm
  const stepSeconds = barSeconds / stepsPerBar
  const sampleRate = Number(project.sample_rate) || 44100
  const totalSamples = Math.round(bars * barSeconds * sampleRate)
  const activeCombos = detectActiveCombos(flock)
  const perches = getPerches(flock).filter(Boolean)
  const anySolo = perches.some(perch => perch.solo && !perch.mute)
  const events = {}
  const roleCounts = new Map()
  const humanize = clamp(project.humanize == null ? 0.004 : Number(project.humanize), 0, 0.006)
  const swing = clamp(Number(project.swing) || 0, 0, 0.5)

  for (const perch of perches) {
    const bird = birds.find(item => item.id === perch.bird)
    if (!bird) continue
    const muted = isMutedByMix(perch, anySolo)
    const appliedSong = effectiveSong(bird, perch.song, activeCombos)
    const pattern = patternFor(bird, appliedSong, activeCombos)
    const rng = mulberry32(seedValue(project.seed, `${bird.id}:${appliedSong}`))
    const notes = []
    for (let bar = 0; bar < bars; bar++) {
      if (activeCombos.includes('back_and_forth')) {
        if (bird.id === 'echo' && bar % 2 === 1) continue
        if (bird.id === 'wren_not' && bar % 2 === 0) continue
      }
      if (activeCombos.includes('two_basses')) {
        if (bird.id === 'bramble' && bar % 2 === 1) continue
        if (bird.id === 'cinder' && bar % 2 === 0) continue
      }
      const chord = chordRootAndScale(flock, bar).chord
      for (const sourceEvent of pattern) {
        if (sourceEvent.bar != null && sourceEvent.bar !== bar % 4) continue
        const step = Math.round(sourceEvent.step * stepsPerBar / 16)
        const globalStep = bar * stepsPerBar + step
        if (globalStep >= bars * stepsPerBar) continue
        const baseSample = Math.round(globalStep * totalSamples / (bars * stepsPerBar))
        const nextSample = Math.round((globalStep + 1) * totalSamples / (bars * stepsPerBar))
        const swingSamples = globalStep % 2 ? Math.round(swing * (nextSample - baseSample) * 0.5) : 0
        const humanizeSamples = (rng() * 2 - 1) * humanize * sampleRate
        const t = clamp((baseSample + swingSamples + humanizeSamples) / sampleRate, 0, bars * barSeconds - 1 / sampleRate)
        const len = Math.max(stepSeconds * 0.5, sourceEvent.len * stepsPerBar / 16 * stepSeconds)
        const midi = resolveMidi(flock, bird.role, bar, { ...sourceEvent, step })
        const vel = clamp(sourceEvent.vel * (0.98 + rng() * 0.04), 0.08, 1)
        const baseEvent = { t, len, midi, vel, muted, song: appliedSong, chord }
        notes.push(baseEvent)

        // Keys and pads voice a compact chord. The seventh is automatic in the
        // three lo-fi modes named in the design, with all tones resolved in-scale.
        if (bird.role === 'keys' || bird.role === 'pad') {
          const additions = [2, 4]
          if (chordTables.extensions.seventhModes.includes(flock.scale)) additions.push(6)
          for (const deg of additions) {
            if (deg === sourceEvent.deg) continue
            notes.push({ ...baseEvent, midi: resolveMidi(flock, bird.role, bar, { ...sourceEvent, deg, harmony: true }), vel: vel * (deg === 6 ? 0.22 : 0.3), harmony: true })
          }
        }
      }
    }

    // Parliament adds a quiet diatonic third below the lead as a call voice.
    if (bird.role === 'lead' && activeCombos.includes('parliament')) {
      for (const note of [...notes]) {
        const pitchClass = (note.midi - keyPitch(flock.key) + 12) % 12
        const scale = scales[flock.scale] || scales.minor
        const degree = scale.semitones.indexOf(pitchClass)
        if (degree < 0) continue
        const third = scale.semitones[(degree - 2 + scale.semitones.length) % scale.semitones.length]
        const delta = ((third - pitchClass + 12) % 12) - 12
        const harmonyMidi = note.midi + delta
        if (harmonyMidi >= registers.lead[0] && harmonyMidi <= registers.lead[1]) {
          notes.push({ ...note, midi: harmonyMidi, vel: note.vel * 0.24, harmony: true, layer: 'parliament_chorus' })
        }
      }
    }

    // Last-bar low accent for the two-bass discovery, kept within the bass range.
    if (bird.role === 'bass' && activeCombos.includes('two_basses')) {
      const lastBarStart = (bars - 1) * barSeconds
      const rootNote = notes.find(note => !note.harmony && note.t >= lastBarStart && note.midi - 12 >= registers.bass[0])
      if (rootNote && rootNote.midi - 12 >= registers.bass[0]) {
        notes.push({ ...rootNote, midi: rootNote.midi - 12, t: lastBarStart + barSeconds * 0.55, len: barSeconds * 0.42, vel: rootNote.vel * 0.45, layer: 'sub_octave_drop' })
      }
    }

    const roleIndex = roleCounts.get(bird.role) || 0
    roleCounts.set(bird.role, roleIndex + 1)
    const mix = ROLE_MIX[bird.role]
    const trim = clamp(Number(perch.trim_db) || 0, -6, 6)
    const gainDb = mix.gainDb + trim - (roleIndex ? 2 : 0)
    const pan = bird.role === 'pad' ? 0 : roleIndex ? -mix.pan : mix.pan
    for (const note of notes) Object.assign(note, { birdId: bird.id, role: bird.role, voice: bird.voice, gainDb, pan })
    events[bird.id] = notes.sort((a, b) => a.t - b.t || a.midi - b.midi)
  }

  return events
}

export const defaultBoomBapProject = {
  bpm: 90, bars: 4, steps_per_bar: 16, swing: 0.12, seed: 'flock-default',
  tracks: [
    { id: 'kick', source: 'factory:kick_boom', steps: 'x...x...x...x...', velocity: [1], gain_db: 0, pan: 0 },
    { id: 'snare', source: 'factory:snare_crack', steps: '....x.......x...', velocity: [0.85], gain_db: -2, pan: 0 },
    { id: 'hat', source: 'factory:hat_closed', steps: 'x.x.x.x.x.x.x.x.', velocity: [0.52], gain_db: -6, pan: 0.12 }
  ]
}

function drumProject(project) {
  return { ...project, tracks: Array.isArray(project.tracks) && project.tracks.length ? project.tracks : defaultBoomBapProject.tracks }
}

function drumKickOnsets(project, durationSamples, sampleRate) {
  const tracks = project.tracks || []
  const anySolo = tracks.some(track => track.solo)
  const bars = Math.max(1, Number(project.bars) || 1)
  const steps = bars * 16
  const swing = clamp(Number(project.swing) || 0, 0, 0.5)
  const onsets = []
  for (const track of tracks) {
    if (track.mute || (anySolo && !track.solo)) continue
    const source = String(track.source || '').replace(/^factory:/, '')
    if (source !== 'kick_boom' && source !== '808') continue
    const pattern = String(track.steps || '')
    if (!pattern.length) continue
    for (let i = 0; i < steps; i++) {
      if (pattern[i % pattern.length] === '.' || !pattern[i % pattern.length]) continue
      const base = Math.round(i * durationSamples / steps)
      const next = Math.round((i + 1) * durationSamples / steps)
      const start = Math.max(0, base + (i % 2 ? Math.round(swing * (next - base) * 0.5) : 0))
      onsets.push(start / sampleRate)
    }
  }
  return onsets.sort((a, b) => a - b)
}

function decodePcm16Stereo(wav, expectedSamples) {
  const view = new DataView(wav.buffer, wav.byteOffset, wav.byteLength)
  const left = new Float32Array(expectedSamples), right = new Float32Array(expectedSamples)
  let offset = 44
  for (let i = 0; i < expectedSamples; i++) {
    left[i] = view.getInt16(offset, true) / 32768; offset += 2
    right[i] = view.getInt16(offset, true) / 32768; offset += 2
  }
  return { left, right }
}

function rawWave(voice, phase) {
  const tau = Math.PI * 2
  const sine = Math.sin(tau * phase)
  if (voice === 'sub') return Math.tanh((sine + Math.sin(tau * phase * 2) * 0.11) * 1.25)
  if (voice === '808') return Math.tanh(sine * 1.5)
  if (voice === 'epiano') return Math.sin(tau * (phase + 0.22 * Math.sin(tau * phase * 2.01))) * 0.8 + Math.sin(tau * phase * 3.98) * 0.16
  if (voice === 'organ') return (Math.sin(tau * phase) + Math.sin(tau * phase * 2) * 0.48 + Math.sin(tau * phase * 3) * 0.22) / 1.7
  if (voice === 'squareLead') return Math.tanh(sine * 1.7) * 0.76 + Math.sin(tau * phase * 2) * 0.08
  if (voice === 'bell') return Math.sin(tau * phase) * 0.72 + Math.sin(tau * phase * 2.72) * 0.22 + Math.sin(tau * phase * 4.09) * 0.08
  if (voice === 'softPad') return (Math.sin(tau * phase) + Math.sin(tau * phase * 1.006) + Math.sin(tau * phase * 0.994)) / 3 * 0.88
  if (voice === 'triangleChoir') return (sine - Math.sin(tau * phase * 3) / 9 + Math.sin(tau * phase * 5) / 25) * 0.88
  if (voice === 'sawPluck') return (2 * (phase - Math.floor(phase + 0.5))) * 0.45 + sine * 0.28
  if (voice === 'squarePluck') return Math.tanh(sine * 2.2) * 0.68
  if (voice === 'formant') return sine * 0.42 + Math.sin(tau * phase * 2) * 0.36 + Math.sin(tau * phase * 3.8) * 0.16
  if (voice === 'whistle') return sine * 0.84
  return sine
}

const WAVE_SIZE = 2048
const WAVE_VOICES = ['sub', '808', 'epiano', 'organ', 'squareLead', 'bell', 'softPad', 'triangleChoir', 'sawPluck', 'squarePluck', 'formant', 'whistle']
const WAVE_TABLES = new Map(WAVE_VOICES.map(voice => {
  const table = new Float32Array(WAVE_SIZE)
  for (let i = 0; i < WAVE_SIZE; i++) table[i] = rawWave(voice, i / WAVE_SIZE)
  return [voice, table]
}))

function osc(voice, phase, seedNoise) {
  const table = WAVE_TABLES.get(voice)
  const wrapped = phase - Math.floor(phase)
  const index = wrapped * WAVE_SIZE
  const i0 = Math.floor(index)
  const fraction = index - i0
  const value = table[i0] + (table[(i0 + 1) % WAVE_SIZE] - table[i0]) * fraction
  return voice === 'whistle' ? value + seedNoise * 0.035 : value
}

function noteEnvelope(voice, t, duration) {
  const attack = voice === 'softPad' || voice === 'triangleChoir' ? 0.12 : voice === 'organ' ? 0.018 : 0.008
  const decay = voice === 'bell' || voice === 'sawPluck' || voice === 'squarePluck' ? Math.exp(-t * 4.6) : 1
  const release = Math.min(0.055, duration * 0.36)
  const inGain = Math.min(1, t / attack)
  const outGain = Math.min(1, Math.max(0, (duration - t) / Math.max(0.002, release)))
  return inGain * outGain * decay
}

function addNote(left, right, note, sampleRate, totalSamples, kickSamples, rng) {
  if (note.muted) return
  const start = Math.round(note.t * sampleRate)
  const duration = Math.max(1, Math.round(note.len * sampleRate))
  const frequency = 440 * (2 ** ((note.midi - 69) / 12))
  const amp = 0.105 * note.vel * (10 ** (note.gainDb / 20))
  const angle = (clamp(note.pan, -1, 1) + 1) * Math.PI / 4
  const panL = Math.cos(angle), panR = Math.sin(angle)
  let hpInL = 0, hpOutL = 0, hpInR = 0, hpOutR = 0
  const hpAlpha = Math.exp(-2 * Math.PI * 180 / sampleRate)
  let kickCursor = 0
  for (let j = 0; j < duration; j++) {
    const pos = start + j
    if (pos >= totalSamples && pos - totalSamples >= totalSamples) break
    const wrapped = pos % totalSamples
    const t = j / sampleRate
    const phase = note.voice === '808' ? frequency * (t + 0.16 * (1 - Math.exp(-18 * t)) / 18) : t * frequency
    const noise = note.voice === 'whistle' ? rng() * 2 - 1 : 0
    let value = osc(note.voice, phase, noise) * noteEnvelope(note.voice, t, duration / sampleRate) * amp
    if (note.voice === '808') value *= Math.exp(-t * 1.3)
    if (note.voice === 'organ') value *= 0.96 + 0.04 * Math.sin(2 * Math.PI * 4.6 * t)
    if (note.role === 'bass' || note.role === 'pad') {
      while (kickCursor < kickSamples.length && kickSamples[kickCursor] < pos) kickCursor++
      const kick = kickCursor < kickSamples.length && kickSamples[kickCursor] - pos < sampleRate * 0.18
      if (kick) value *= 10 ** (-3 / 20)
    }
    let l = value * panL, r = value * panR
    if (note.role === 'pad') {
      const filteredL = (1 - hpAlpha) * l + hpAlpha * hpOutL
      const filteredR = (1 - hpAlpha) * r + hpAlpha * hpOutR
      l = l - hpOutL; r = r - hpOutR
      hpInL = l; hpOutL = filteredL; hpInR = r; hpOutR = filteredR
    }
    left[wrapped] += l
    right[wrapped] += r
  }
}

function addWeather(left, right, weather, seed, sampleRate) {
  if (!weather || weather === 'clear') return
  const rng = mulberry32(seedValue(seed, `weather:${weather}`))
  const gain = 10 ** (-24 / 20)
  let smoothL = 0, smoothR = 0, heldL = 0, heldR = 0
  let nextAccent = 0, currentAccent = -1, accentL = 0, accentR = 0
  const meanSpacing = weather === 'dust' ? sampleRate * 0.09 : sampleRate * 0.32
  const scheduleAccent = () => {
    nextAccent += Math.max(1, Math.round(-Math.log(Math.max(1e-8, rng())) * meanSpacing))
    accentL = rng() * 2 - 1; accentR = rng() * 2 - 1
  }
  scheduleAccent()
  for (let i = 0; i < left.length; i++) {
    if (i % 8 === 0) { heldL = rng() * 2 - 1; heldR = rng() * 2 - 1 }
    if (i >= nextAccent) { currentAccent = nextAccent; scheduleAccent() }
    if (weather === 'dust') {
      left[i] += (heldL * 0.08 + (i === currentAccent ? accentL : 0)) * gain * 0.7
      right[i] += (heldR * 0.08 + (i === currentAccent ? accentR : 0)) * gain * 0.7
    } else if (weather === 'rain') {
      if (i % 8 === 0) { smoothL = smoothL * 0.93 + heldL * 0.07; smoothR = smoothR * 0.93 + heldR * 0.07 }
      const drop = i === currentAccent
      left[i] += (smoothL * 0.18 + (drop ? accentL * 0.8 : 0)) * gain
      right[i] += (smoothR * 0.18 + (drop ? accentR * 0.8 : 0)) * gain
    } else if (weather === 'wind') {
      if (i % 8 === 0) { smoothL = smoothL * 0.9992 + heldL * 0.0008; smoothR = smoothR * 0.9992 + heldR * 0.0008 }
      left[i] += smoothL * gain * 0.4; right[i] += smoothR * gain * 0.4
    }
  }
}

function masterLimit(left, right, sampleRate) {
  const hpAlpha = Math.exp(-2 * Math.PI * 20 / sampleRate)
  let peak = 0
  for (const channel of [left, right]) {
    let priorIn = 0, priorOut = 0
    for (let i = 0; i < channel.length; i++) {
      const input = channel[i]
      const filtered = hpAlpha * (priorOut + input - priorIn)
      priorIn = input; priorOut = filtered
      channel[i] = filtered
      peak = Math.max(peak, Math.abs(filtered))
    }
  }
  const gain = peak > 0 ? Math.min(1.22, TARGET_PEAK * 0.94 / peak) : 1
  for (const channel of [left, right]) for (let i = 0; i < channel.length; i++) {
    const x = channel[i] * gain
    const smooth = TARGET_PEAK * Math.tanh(x / TARGET_PEAK) / Math.tanh(1)
    channel[i] = clamp(smooth, -TARGET_PEAK, TARGET_PEAK)
  }
}

function meter(left, right) {
  let sum = 0, peak = 0, count = left.length + right.length
  for (const channel of [left, right]) for (const value of channel) {
    sum += value * value
    peak = Math.max(peak, Math.abs(value))
  }
  return { rms_db: sum > 0 ? 20 * Math.log10(Math.sqrt(sum / Math.max(1, count))) : -120, peak_db: peak > 0 ? 20 * Math.log10(peak) : -120 }
}

export async function renderFlock(project, flock, { sampleRate = 44100 } = {}) {
  const bars = Math.max(1, Number(project.bars) || 1)
  const bpm = Math.max(1, Number(project.bpm) || 120)
  const durationSamples = Math.round(bars * 4 * 60 / bpm * sampleRate)
  const renderProject = drumProject(project)
  const drum = await synthLoop(renderProject, { sampleRate })
  const samples = decodePcm16Stereo(drum.wav, durationSamples)
  const left = samples.left, right = samples.right
  const activeCombos = detectActiveCombos(flock)
  const events = buildNoteEvents({ ...project, sample_rate: sampleRate }, flock)
  const kickOnsets = drumKickOnsets(renderProject, durationSamples, sampleRate)
  const kickSamples = kickOnsets.map(time => Math.round(time * sampleRate))
  for (const notes of Object.values(events)) {
    for (const note of notes) addNote(left, right, note, sampleRate, durationSamples, kickSamples, mulberry32(seedValue(project.seed, `${note.birdId}:${note.t}:${note.midi}`)))
  }
  addWeather(left, right, flock.weather, project.seed, sampleRate)
  const corvus = getPerches(flock).find(perch => perch?.bird === 'corvus')
  const anySolo = getPerches(flock).some(perch => perch?.solo && !perch.mute)
  if (corvus && !corvus.mute && (!anySolo || corvus.solo)) {
    for (let i = 0; i < durationSamples; i++) {
      left[i] = Math.tanh(left[i] * 1.18) / Math.tanh(1.18)
      right[i] = Math.tanh(right[i] * 1.18) / Math.tanh(1.18)
    }
  }
  masterLimit(left, right, sampleRate)
  if (drum.audio_url && drum.audio_url.startsWith('blob:') && typeof URL?.revokeObjectURL === 'function') URL.revokeObjectURL(drum.audio_url)
  return {
    left, right, duration_samples: durationSamples, events,
    kick_onsets: kickOnsets, active_combos: activeCombos,
    sample_rate: sampleRate, master: meter(left, right)
  }
}
