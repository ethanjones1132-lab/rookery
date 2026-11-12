import assert from 'node:assert/strict'
import { performance } from 'node:perf_hooks'
import { synthLoop } from './mock-audio.js'

const busy = {
  bpm: 90, bars: 4, steps_per_bar: 16, swing: 0, seed: 'preview-check',
  tracks: [
    { id: 'kick', kind: 'drum', source: 'factory:kick_boom', steps: 'x...x...x...x...', velocity: [1], gain_db: 0, pan: 0 },
    { id: 'snare', kind: 'drum', source: 'factory:snare_crack', steps: '....x.......x...', velocity: [0.9], gain_db: -1, pan: 0 },
    { id: 'hat', kind: 'drum', source: 'factory:hat_closed', steps: 'x.x.x.x.x.x.x.x.', velocity: [0.55], gain_db: -3, pan: 0.2 },
    { id: 'bass', kind: 'drum', source: 'factory:808', steps: 'x.......x.......', velocity: [0.7], gain_db: -2, pan: 0 },
  ], master: { fx: [] },
}

const expectedSamples = (bpm, bars, sr = 44100) => Math.round(bars * 4 * 60 / bpm * sr)
for (const [bpm, bars] of [[90, 4], [70, 8], [140, 4]]) {
  const result = await synthLoop({ ...busy, bpm, bars })
  assert.equal(result.duration_samples, expectedSamples(bpm, bars))
  assert.equal(result.wav.byteLength, 44 + result.duration_samples * 4)
}

const first = await synthLoop(busy)
const same = await synthLoop(busy)
assert.deepEqual(first.wav, same.wav, 'same project must render identical bytes')
assert(first.master.peak_db <= -1 + 1e-4, `peak is ${first.master.peak_db} dBFS`)
assert(first.master.rms_db > -30, `busy mix RMS is ${first.master.rms_db} dBFS`)

const allRest = { ...busy, tracks: busy.tracks.map(track => ({ ...track, steps: '................' })) }
const silence = await synthLoop(allRest)
assert(silence.master.rms_db <= -90, `rest project RMS is ${silence.master.rms_db} dBFS`)

const noisy = { ...busy, tracks: [{ ...busy.tracks[2], steps: 'x...............' }] }
const differentSeed = await synthLoop({ ...noisy, seed: 'different-seed' })
const originalSeed = await synthLoop(noisy)
assert.notDeepEqual(originalSeed.wav, differentSeed.wav, 'noise must depend on project seed')

const hatPattern = { ...noisy, bars: 1, tracks: [{ ...noisy.tracks[0], steps: '.x..............' }] }
const noSwing = await synthLoop({ ...hatPattern, swing: 0 })
const swung = await synthLoop({ ...hatPattern, swing: 0.2 })
function firstAbove(wav, threshold = 0.0005) {
  const view = new DataView(wav.buffer, wav.byteOffset, wav.byteLength)
  for (let i = 0; i < (wav.byteLength - 44) / 4; i++) {
    const left = view.getInt16(44 + i * 4, true) / 32768
    const right = view.getInt16(46 + i * 4, true) / 32768
    if (Math.max(Math.abs(left), Math.abs(right)) > threshold) return i
  }
  return -1
}
assert(firstAbove(swung.wav) > firstAbove(noSwing.wav), 'swing should delay an odd sixteenth onset')

const muted = await synthLoop({ ...busy, tracks: [{ ...busy.tracks[0], mute: true }] })
assert.equal(muted.meters.kick.rms_db, -120)

const speedProject = {
  ...busy, bpm: 70, bars: 8,
  tracks: [...busy.tracks, { id: 'clap', source: 'factory:clap', steps: '..x...x...x...x.', velocity: [0.5], gain_db: -6, pan: -0.2 },
    { id: 'open', source: 'factory:hat_open', steps: '....x.......x...', velocity: [0.4], gain_db: -5, pan: 0.3 }],
}
const started = performance.now()
const fast = await synthLoop(speedProject)
const elapsed = performance.now() - started
assert.equal(fast.duration_samples, expectedSamples(70, 8))
assert(elapsed < 400, `render took ${elapsed.toFixed(1)} ms`)

console.log(`duration_samples: ${first.duration_samples}`)
console.log(`wav_bytes: ${first.wav.byteLength}`)
console.log(`master: rms ${first.master.rms_db.toFixed(2)} dBFS, peak ${first.master.peak_db.toFixed(2)} dBFS, LUFS est ${first.master.lufs_estimate.toFixed(2)}`)
console.log(`8-bar/6-track render: ${elapsed.toFixed(1)} ms`)
console.log('check-audio: all assertions passed')
