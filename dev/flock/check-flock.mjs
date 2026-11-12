import assert from 'node:assert/strict'
import { encodeWav16 } from '../preview/mock-audio.js'
import { birds, combos, registers, scales, templates } from './birds.js'
import { buildNoteEvents, defaultBoomBapProject, detectActiveCombos, isCorvusUnlocked, renderFlock } from './flock-synth.js'

const NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
const pitch = key => ({ Db: 'C#', Eb: 'D#', Gb: 'F#', Ab: 'G#', Bb: 'A#' }[key] || key) && NOTE_NAMES.indexOf(({ Db: 'C#', Eb: 'D#', Gb: 'F#', Ab: 'G#', Bb: 'A#' }[key] || key))
const project = patch => ({ ...defaultBoomBapProject, ...patch, tracks: patch?.tracks || defaultBoomBapProject.tracks })
const flockFor = template => {
  const perches = Array(6).fill(null)
  template.birds.forEach((bird, index) => { perches[index] = { ...bird, mute: false, solo: false } })
  return { key: template.key, scale: template.scale, progression: [...template.progression], weather: template.weather, perches, seen: template.birds.map(bird => bird.bird), unlocked: [], templateId: template.id }
}
const toWav = output => encodeWav16([output.left, output.right], output.sample_rate)
const bytesEqual = (a, b) => a.length === b.length && a.every((byte, index) => byte === b[index])

const dusty = templates[0]
const baseFlock = flockFor(dusty)
const baseProject = project({ name: dusty.name, bpm: 90, bars: 4, seed: 'acceptance-seed' })
const first = await renderFlock(baseProject, baseFlock)
const second = await renderFlock(baseProject, baseFlock)
assert.ok(bytesEqual(toWav(first), toWav(second)), 'same inputs must render identical WAV bytes')
const differentSeed = await renderFlock({ ...baseProject, seed: 'a-different-seed' }, baseFlock)
assert.ok(!bytesEqual(toWav(first), toWav(differentSeed)), 'changing the seed must change WAV bytes')

const alternateProgressions = [
  ['i', 'VII', 'iv', 'VI'],
  ['I', 'V', 'vi', 'ii']
]
for (const template of templates) {
  const projectForTemplate = project({ bpm: 90, bars: 4, seed: `catalog-${template.id}` })
  const progressionSets = [template.progression, ...alternateProgressions]
  for (const progression of progressionSets) for (const bird of birds) for (const song of ['A', 'B', 'C']) {
    const flock = { ...flockFor(template), progression: [...progression], perches: [{ bird: bird.id, song, mute: false, solo: false }, null, null, null, null, null] }
    const events = buildNoteEvents(projectForTemplate, flock)
    const scale = scales[flock.scale]
    for (const note of events[bird.id]) {
      const pitchClass = ((note.midi - pitch(flock.key)) % 12 + 12) % 12
      assert.ok(scale.semitones.includes(pitchClass), `${template.name}/${bird.name}/${song}/${progression.join('-')} note ${note.midi} must stay in key and scale`)
      const [low, high] = registers[bird.role]
      assert.ok(note.midi >= low && note.midi <= high, `${bird.name} note ${note.midi} must stay in ${bird.role} register ${low}-${high}`)
    }
    assert.ok(events[bird.id].length, `${bird.name} song ${song} should have notes`)
  }
}

for (const [bpm, bars] of [[90, 4], [140, 8], [72, 4]]) {
  const output = await renderFlock(project({ bpm, bars, seed: `length-${bpm}` }), baseFlock)
  assert.equal(output.duration_samples, Math.round(bars * 4 * 60 / bpm * 44100), `${bars} bars at ${bpm} BPM must be exact length`)
}

for (const template of templates) {
  const output = await renderFlock(project({ bpm: template.id === 'trap_night' ? 140 : 90, bars: 4, seed: `peak-${template.id}` }), flockFor(template))
  assert.ok(output.master.peak_db <= -1, `${template.name} master peak ${output.master.peak_db.toFixed(3)} dBFS must be at or below -1 dBFS`)
}

const parliament = { ...baseFlock, perches: [
  { bird: 'bramble', song: 'A' }, { bird: 'quill', song: 'B' }, { bird: 'hush', song: 'A' },
  { bird: 'jinx', song: 'A' }, { bird: 'tick', song: 'A' }, { bird: 'echo', song: 'A' }
] }
assert.ok(detectActiveCombos(parliament).includes('parliament'), 'one bird of every role must detect Parliament')
const parliamentRender = await renderFlock(project({ bpm: 90, bars: 4, seed: 'parliament-loudness' }), parliament)
assert.ok(parliamentRender.master.rms_db > -30, `Parliament master RMS ${parliamentRender.master.rms_db.toFixed(3)} dBFS must exceed -30 dBFS`)

const recipeFlocks = {
  parliament: { scale: 'dorian', weather: 'clear', perches: ['bramble', 'quill', 'hush', 'jinx', 'tick', 'echo'].map(bird => ({ bird, song: 'A' })) },
  night_shift: { scale: 'minor', weather: 'clear', perches: ['hush', 'sable', 'echo'].map(bird => ({ bird, song: 'A' })) },
  shiny_things: { scale: 'minor', weather: 'clear', perches: ['glint', 'cinder', 'jinx'].map(bird => ({ bird, song: 'A' })) },
  back_and_forth: { scale: 'dorian', weather: 'clear', perches: ['echo', 'wren_not'].map(bird => ({ bird, song: 'A' })) },
  two_basses: { scale: 'dorian', weather: 'clear', perches: ['bramble', 'cinder'].map(bird => ({ bird, song: 'A' })) },
  lo_fi_window: { scale: 'dorian', weather: 'rain', perches: ['quill', 'moss'].map(bird => ({ bird, song: 'A' })) }
}
for (const combo of combos) {
  const recipe = recipeFlocks[combo.id]
  const met = { ...baseFlock, ...recipe, progression: ['i', 'iv', 'VII', 'III'], perches: [...recipe.perches, ...Array(6 - recipe.perches.length).fill(null)] }
  assert.ok(detectActiveCombos(met).includes(combo.id), `${combo.name} must detect when its recipe is met`)
  const comboEvents = buildNoteEvents(baseProject, met)
  const comboScale = scales[met.scale]
  for (const notes of Object.values(comboEvents)) for (const note of notes) {
    const pitchClass = ((note.midi - pitch(met.key)) % 12 + 12) % 12
    const [low, high] = registers[note.role]
    assert.ok(comboScale.semitones.includes(pitchClass), `${combo.name} bonus note ${note.midi} stays in key and scale`)
    assert.ok(note.midi >= low && note.midi <= high, `${combo.name} bonus note ${note.midi} stays in its ${note.role} register`)
  }
  const missing = { ...met, perches: [...met.perches] }
  if (combo.requires.birds) {
    const requirement = combo.requires.birds.at(-1)
    missing.perches[missing.perches.findIndex(item => item?.bird === requirement)] = null
  } else if (combo.requires.roles) {
    missing.perches[missing.perches.findIndex(item => item?.bird === 'echo')] = null
  } else if (combo.requires.weather) missing.weather = 'clear'
  else if (combo.requires.scale_family) missing.scale = 'major'
  assert.ok(!detectActiveCombos(missing).includes(combo.id), `${combo.name} must not detect when one requirement is missing`)
}

assert.equal(isCorvusUnlocked({ seen: birds.slice(0, 11).map(bird => bird.id) }), false, 'Corvus stays locked until all twelve birds have been seen')
assert.equal(isCorvusUnlocked({ seen: birds.map(bird => bird.id) }), true, 'all twelve seen unlock Corvus')
assert.equal(isCorvusUnlocked({ seen: birds.map(bird => bird.id).slice(1) }), false, 'missing any bird keeps Corvus locked')

const twoBirds = { ...baseFlock, weather: 'clear', perches: [
  { bird: 'bramble', song: 'A', solo: true, mute: false },
  { bird: 'quill', song: 'A', solo: false, mute: false }, null, null, null, null
] }
const mutedEvents = buildNoteEvents(baseProject, { ...twoBirds, perches: [{ bird: 'bramble', song: 'A', mute: true }, null, null, null, null, null] })
assert.ok(mutedEvents.bramble.length && mutedEvents.bramble.every(event => event.muted), 'muted bird events are retained and flagged muted')
const soloMix = await renderFlock(baseProject, twoBirds)
const explicitlyMutedMix = await renderFlock(baseProject, { ...twoBirds, perches: [twoBirds.perches[0], { ...twoBirds.perches[1], mute: true }, null, null, null, null] })
assert.ok(soloMix.events.quill.every(event => event.muted), 'solo must flag other birds as muted')
assert.ok(bytesEqual(toWav(soloMix), toWav(explicitlyMutedMix)), 'soloed flock audio must silence every other bird')

const speedStart = performance.now()
await renderFlock(project({ bpm: 90, bars: 4, seed: 'speed-check' }), parliament)
const elapsed = performance.now() - speedStart
assert.ok(elapsed < 600, `Parliament render took ${elapsed.toFixed(1)} ms; expected under 600 ms`)

console.log(`PASS: determinism, scale/register coverage (${templates.length} templates × 12 birds × 3 songs × 3 progressions), exact length, peak/RMS, six combos, Corvus unlock, mute/solo`)
console.log(`Parliament 6 birds + drums, 4 bars at 90 BPM: ${elapsed.toFixed(1)} ms (< 600 ms)`)
