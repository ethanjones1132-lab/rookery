// Mock renderer for the preview harness. STUB: returns silence of the exact length.
// Being replaced by a pure-JS drum synth (brief: .crew/briefs/claude/B-mock-audio.md).
// Interface (stable, mock-backend depends on it):
//   synthLoop(project, { sampleRate = 44100 } = {}) →
//     { wav: Uint8Array (16-bit PCM stereo WAV), audio_url: string | null (blob: URL in browsers),
//       duration_samples: number, sample_rate: number,
//       meters: { [trackId]: { rms_db: number, peak_db: number } }, master: { rms_db, peak_db, lufs_estimate } }
const SILENCE_DB = -120
const TARGET_PEAK = 10 ** (-1 / 20)

// The engine's default voices are the measured recipes (commit 3026f32). The
// preview synth plays their nearest legacy family so the mock keeps sounding
// like the real engine while the grid shows the real source names.
const VOICE_FAMILY = {
  kick_punch: 'kick_boom', kick_deep: 'kick_boom',
  snare_snap: 'snare_crack', snare_snap_dry: 'snare_crack',
  clap_stack: 'clap', hat_tight: 'hat_closed', hat_open_short: 'hat_open',
  '808_round': '808',
}
const familyOf = source => VOICE_FAMILY[source] || source

function db(value) { return value > 0 ? 20 * Math.log10(value) : SILENCE_DB }

function seedValue(seed, trackIndex) {
  let h = (0x811c9dc5 ^ trackIndex) >>> 0
  const text = String(seed ?? 0)
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

function voiceSample(source, t, rng, pitchRatio) {
  const noise = () => rng() * 2 - 1
  if (source === 'kick_boom') {
    const f = 48 + 102 * Math.exp(-t * 25)
    const tone = Math.sin(2 * Math.PI * (48 * t + 102 * (1 - Math.exp(-25 * t)) / 25)) * Math.exp(-t * 9)
    const click = t < 0.009 ? noise() * Math.exp(-t * 430) * 0.38 : 0
    return tone * 0.9 + click
  }
  if (source === '808') return Math.tanh(Math.sin(2 * Math.PI * 49 * pitchRatio * t) * Math.exp(-t * 3.3) * 1.65)
  if (source === 'snare_crack') {
    const n = noise() * Math.exp(-t * 25)
    return n * 0.72 + Math.sin(2 * Math.PI * 190 * t) * Math.exp(-t * 20) * 0.42
  }
  if (source === 'clap') {
    let n = 0
    for (const delay of [0, 0.01, 0.02]) if (t >= delay) n += noise() * Math.exp(-(t - delay) * 42) * 0.42
    return n
  }
  if (source === 'hat_closed' || source === 'hat_open') return noise()
  if (source === 'rim') return (Math.sin(2 * Math.PI * 1450 * t) * 0.7 + Math.sin(2 * Math.PI * 2200 * t) * 0.3) * Math.exp(-t * 75)
  // perc and unknown sources
  return (Math.sin(2 * Math.PI * 620 * t) * 0.7 + Math.sin(2 * Math.PI * 930 * t) * 0.3) * Math.exp(-t * 45)
}

function voiceLength(source, sampleRate) {
  const seconds = source === 'kick_boom' ? 0.35 : source === '808' ? 0.9
    : source === 'snare_crack' ? 0.18 : source === 'clap' ? 0.16
      : source === 'hat_closed' ? 0.045 : source === 'hat_open' ? 0.32
        : source === 'rim' ? 0.07 : 0.11
  return Math.max(1, Math.round(seconds * sampleRate))
}

function meter(channels) {
  let squares = 0, peak = 0, count = channels[0].length * channels.length
  for (const channel of channels) for (const value of channel) {
    squares += value * value
    peak = Math.max(peak, Math.abs(value))
  }
  return { rms_db: db(Math.sqrt(squares / Math.max(1, count))), peak_db: db(peak) }
}

export async function synthLoop(project, { sampleRate = 44100 } = {}) {
  const bars = Math.max(1, Number(project.bars) || 1)
  const bpm = Math.max(1, Number(project.bpm) || 120)
  const total = Math.round(bars * 4 * 60 / bpm * sampleRate)
  const nSteps = bars * 16
  const tail = Math.round(4 * 60 / bpm * sampleRate)
  const extendedLength = total + tail
  const tracks = project.tracks || []
  const anySolo = tracks.some(track => track.solo)
  const trackMixes = tracks.map(() => [new Float32Array(total), new Float32Array(total)])
  const events = []
  const randomByTrack = tracks.map((_, ti) => mulberry32(seedValue(project.seed, ti)))

  for (let ti = 0; ti < tracks.length; ti++) {
    const track = tracks[ti]
    if (track.mute || (anySolo && !track.solo)) continue
    const steps = String(track.steps || '')
    for (let i = 0; i < nSteps; i++) {
      const mark = steps.length ? steps[i % steps.length] : '.'
      if (mark === '.' || mark === undefined || mark === '') continue
      const base = Math.round(i * total / nSteps)
      const next = Math.round((i + 1) * total / nSteps)
      const swing = Math.max(0, Math.min(0.5, Number(project.swing) || 0))
      const start = Math.max(0, base + (i % 2 ? Math.round(swing * (next - base) * 0.5) : 0))
      let hitsBefore = 0
      for (let previous = 0; previous < i; previous++) if (steps.length && steps[previous % steps.length] !== '.') hitsBefore++
      const velocityList = Array.isArray(track.velocity) && track.velocity.length ? track.velocity : [1]
      const velocity = Math.max(0, Number(velocityList[hitsBefore % velocityList.length]) || 0)
      const source = familyOf(String(track.source || '').replace(/^factory:/, ''))
      events.push({ ti, track, source, start, velocity, rng: randomByTrack[ti] })
    }
  }
  events.sort((a, b) => a.start - b.start || a.ti - b.ti)

  const active = new Map()
  for (const event of events) {
    const { ti, track, source, start } = event
    const choke = source === '808' ? '808' : source === 'hat_closed' ? 'hats' : null
    if (choke) {
      const prior = active.get(choke)
      if (prior) prior.end = Math.min(prior.end, start)
      if (source === 'hat_closed') {
        const open = active.get('open-hat')
        if (open) open.end = Math.min(open.end, start)
      }
    }
    const voice = { ...event, end: start + voiceLength(source, sampleRate) }
    if (source === '808') active.set('808', voice)
    if (source === 'hat_open') active.set('open-hat', voice)
    if (source === 'hat_closed') active.set('hats', voice)
    event.voice = voice
  }

  for (const event of events) {
    const { ti, track, source, start, velocity, rng, voice } = event
    if (velocity <= 0) continue
    const pitchRatio = 2 ** ((Number(track.pitch) || 0) / 12)
    const gain = 10 ** ((Number(track.gain_db) || 0) / 20)
    const pan = Math.max(-1, Math.min(1, Number(track.pan) || 0))
    const leftGain = Math.cos((pan + 1) * Math.PI / 4) * gain
    const rightGain = Math.sin((pan + 1) * Math.PI / 4) * gain
    const duration = Math.max(0, Math.min(voice.end, start + voiceLength(source, sampleRate)) - start)
    const fade = Math.max(1, Math.round(sampleRate * 0.002))
    const mix = trackMixes[ti]
    let hpState = 0
    const hpAlpha = Math.exp(-2 * Math.PI * 7000 / sampleRate)
    for (let j = 0; j < duration; j++) {
      const t = j / sampleRate
      let value = voiceSample(source, t, rng, pitchRatio)
      if (source === 'hat_closed' || source === 'hat_open') {
        hpState = (1 - hpAlpha) * value + hpAlpha * hpState
        value -= hpState
      }
      const fadeIn = Math.min(1, (j + 1) / fade)
      const fadeOut = Math.min(1, (duration - j) / fade)
      value *= fadeIn * fadeOut * velocity
      const pos = start + j
      if (pos < total) { mix[0][pos] += value * leftGain; mix[1][pos] += value * rightGain }
      else if (pos < extendedLength) {
        const wrapped = pos - total
        if (wrapped < total) { mix[0][wrapped] += value * leftGain; mix[1][wrapped] += value * rightGain }
      }
    }
  }

  const meters = {}
  const masterChannels = [new Float32Array(total), new Float32Array(total)]
  for (let ti = 0; ti < tracks.length; ti++) {
    const mix = trackMixes[ti]
    meters[tracks[ti].id] = tracks[ti].mute || (anySolo && !tracks[ti].solo) ? { rms_db: SILENCE_DB, peak_db: SILENCE_DB } : meter(mix)
    for (let c = 0; c < 2; c++) for (let i = 0; i < total; i++) masterChannels[c][i] += mix[c][i]
  }

  // 20 Hz one-pole high-pass, followed by gentle peak compression.
  const alpha = Math.exp(-2 * Math.PI * 20 / sampleRate)
  let peakBeforeLimit = 0
  for (let c = 0; c < 2; c++) {
    let previousInput = 0, previousOutput = 0
    for (let i = 0; i < total; i++) {
      const input = masterChannels[c][i]
      const filtered = alpha * (previousOutput + input - previousInput)
      previousInput = input; previousOutput = filtered
      const compressed = Math.abs(filtered) > 0.65 ? Math.sign(filtered) * (0.65 + (Math.abs(filtered) - 0.65) * 0.55) : filtered
      masterChannels[c][i] = compressed
      peakBeforeLimit = Math.max(peakBeforeLimit, Math.abs(compressed))
    }
  }
  if (peakBeforeLimit > 0) {
    const makeup = Math.min(3.6, 1.05 / peakBeforeLimit)
    for (const channel of masterChannels) for (let i = 0; i < total; i++) {
      const x = channel[i] * makeup
      // Smooth soft knee, with an explicit final cap for the promised sample peak.
      channel[i] = Math.max(-TARGET_PEAK, Math.min(TARGET_PEAK, Math.tanh(x * 1.08) / Math.tanh(1.08) * TARGET_PEAK))
    }
  }
  const masterMeter = meter(masterChannels)
  const master = { ...masterMeter, lufs_estimate: masterMeter.rms_db <= SILENCE_DB ? SILENCE_DB : masterMeter.rms_db - 0.7 }
  const wav = encodeWav16(masterChannels, sampleRate)
  const audio_url = typeof Blob !== 'undefined' && typeof URL?.createObjectURL === 'function'
    ? URL.createObjectURL(new Blob([wav], { type: 'audio/wav' })) : null
  return { wav, audio_url, duration_samples: total, sample_rate: sampleRate, meters, master }
}

export function encodeWav16(channels, sampleRate) {
  const n = channels[0].length, ch = channels.length
  const buf = new ArrayBuffer(44 + n * ch * 2), v = new DataView(buf)
  const str = (o, s) => { for (let i = 0; i < s.length; i++) v.setUint8(o + i, s.charCodeAt(i)) }
  str(0, 'RIFF'); v.setUint32(4, 36 + n * ch * 2, true); str(8, 'WAVE'); str(12, 'fmt ')
  v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, ch, true); v.setUint32(24, sampleRate, true)
  v.setUint32(28, sampleRate * ch * 2, true); v.setUint16(32, ch * 2, true); v.setUint16(34, 16, true)
  str(36, 'data'); v.setUint32(40, n * ch * 2, true)
  let o = 44
  for (let i = 0; i < n; i++) for (let c = 0; c < ch; c++) {
    const s = Math.max(-1, Math.min(1, channels[c][i])); v.setInt16(o, s < 0 ? s * 0x8000 : s * 0x7fff, true); o += 2
  }
  return new Uint8Array(buf)
}
