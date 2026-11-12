// Scripted preview scenes for the demo's agent panel. Every edit still goes
// through the mock backend's public helpers, so the UI sees the same events.

const PROJECT = 'dusty-90'
const HAT_PATTERN = 'x.x.x.x.x.x.x.x.'
const SNARE_PATTERN = '....x.......x...'
const KICK_PATTERN = 'x.....x...x.....x.....x...x.....'
const BASS_PATTERN = 'x.........x.....x.......x.......'
const OPEN_HAT_PATTERN = '........x.......'
const CORVUS_PATH = 'C:\\Program Files\\Common Files\\VST3\\Corvus FX.vst3'

let firstRenderHash = null

const pause = ms => new Promise(resolve => setTimeout(resolve, ms))

function toolCalls(api, say) {
  let count = 0
  return async (label, action) => {
    if (count > 0) await pause(600 + Math.floor(Math.random() * 301))
    count++
    say(label, 'tool')
    return action()
  }
}

async function buildBeat(api, call, name) {
  await call(`rookery_new(name="${name}", bpm=90, bars=4)`, () => api.newProject({ name, bpm: 90, bars: 4, swing: 0 }))
  const tracks = [
    { id: 'kick', kind: 'drum', source: 'factory:kick_boom' },
    { id: 'snare', kind: 'drum', source: 'factory:snare_crack' },
    { id: 'hat', kind: 'drum', source: 'factory:hat_closed' },
    { id: '808', kind: 'bass', source: 'factory:808' },
    { id: 'hat_open', kind: 'drum', source: 'factory:hat_open' }
  ]
  for (const track of tracks) {
    await call(`rookery_track(action="add", id="${track.id}", …)`, () => api.agentEdit({
      name, tool: 'rookery_track', op: 'track', action: 'add', ...track
    }))
  }

  const patterns = [
    ['kick', KICK_PATTERN],
    ['snare', SNARE_PATTERN],
    ['hat', HAT_PATTERN],
    ['808', BASS_PATTERN],
    ['hat_open', OPEN_HAT_PATTERN]
  ]
  for (const [track, steps] of patterns) {
    await call(`rookery_steps(track="${track}", …)`, () => api.agentEdit({ name, tool: 'rookery_steps', op: 'steps', track, steps }))
  }
  return call('rookery_render()', () => api.handle('POST', '/render', { name }))
}

function withEditing(api, name, run) {
  api.setAgentEditing(name, true)
  return Promise.resolve()
    .then(run)
    .finally(() => api.setAgentEditing(name, false))
}

function hatStepNames(indexes) {
  return indexes.map(index => `bar ${Math.floor(index / 16) + 1}, step ${(index % 16) + 1}`)
}

function checksSummary(rendered) {
  const checks = Object.values(rendered.report)
  return `${checks.filter(check => check.pass).length}/${checks.length} checks pass.`
}

export const SCENES = [
  {
    id: 'build-boom-bap',
    label: '1 · Build boom bap',
    user: 'Boom bap at 90, dusty, 4 bars.',
    run: async (api, say) => withEditing(api, PROJECT, async () => {
      const call = toolCalls(api, say)
      const rendered = await buildBeat(api, call, PROJECT)
      firstRenderHash = rendered.hash
      say(`Dusty boom bap at 90 BPM, 4 bars. ${checksSummary(rendered)}`, 'agent')
    })
  },
  {
    id: 'add-the-flock',
    label: 'Add the flock',
    user: 'Add the flock',
    run: async (api, say) => withEditing(api, PROJECT, async () => {
      const call = toolCalls(api, say)
      try { await api.handle('GET', `/project/${encodeURIComponent(PROJECT)}`) }
      catch (error) {
        if (error.status !== 404) throw error
        const beat = await buildBeat(api, call, PROJECT)
        firstRenderHash = beat.hash
      }
      await call('rookery_flock(action="template", template="dusty_boom_bap")', () => api.agentEdit({
        name: PROJECT, tool: 'rookery_flock', op: 'flock', action: 'template', template: 'dusty_boom_bap'
      }))
      const rendered = await call('rookery_render()', () => api.handle('POST', '/render', { name: PROJECT }))
      say(`Dusty Boom Bap flock added to the beat. ${checksSummary(rendered)}`, 'agent')
    })
  },
  {
    id: 'snare-and-swing',
    label: '2 · Snare + swing',
    user: 'Snare hits harder, add some swing.',
    run: async (api, say) => withEditing(api, PROJECT, async () => {
      const call = toolCalls(api, say)
      const velocity = [...SNARE_PATTERN].map(step => step === 'x' ? 1 : 0.9)
      await call('rookery_steps(track="snare", velocity=…)', () => api.agentEdit({
        name: PROJECT, tool: 'rookery_steps', op: 'steps', track: 'snare', steps: SNARE_PATTERN, velocity
      }))
      await call('rookery_meta(swing=0.18)', () => api.agentEdit({ name: PROJECT, tool: 'rookery_meta', op: 'meta', swing: 0.18 }))
      const rendered = await call('rookery_render()', () => api.handle('POST', '/render', { name: PROJECT }))
      say(`Snare velocity is up and swing is 0.18. Render ${rendered.hash.slice(0, 12)}. ${checksSummary(rendered)}`, 'agent')
    })
  },
  {
    id: 'undo-swing',
    label: '3 · Undo swing',
    user: 'Undo the swing.',
    run: async (api, say) => withEditing(api, PROJECT, async () => {
      const call = toolCalls(api, say)
      const undone = await call('rookery_undo()', () => api.handle('POST', '/undo', { name: PROJECT }))
      const rendered = await call('rookery_render()', () => api.handle('POST', '/render', { name: PROJECT }))
      say(`Swing undone (now ${undone.project.swing}). ${checksSummary(rendered)}`, 'agent')
      return rendered
    })
  },
  {
    id: 'what-changed',
    label: '4 · What changed?',
    user: 'What changed?',
    run: async (api, say) => withEditing(api, PROJECT, async () => {
      const call = toolCalls(api, say)
      const view = await call('rookery_state()', () => api.handle('GET', `/project/${encodeURIComponent(PROJECT)}`))
      const loopLength = view.project.bars * view.project.steps_per_bar
      const expected = HAT_PATTERN.repeat(Math.ceil(loopLength / HAT_PATTERN.length)).slice(0, loopLength)
      const hat = view.project.tracks.find(track => track.id === 'hat')
      const changed = hat ? [...hat.steps].flatMap((step, index) => step === expected[index] ? [] : [index]) : []
      const names = hatStepNames(changed)
      say(names.length
        ? `Compared the hat row with my last pattern. Changed pads: ${names.join('; ')}.`
        : 'The closed-hat row still matches my last pattern; I found no changed pads.', 'agent')
    })
  },
  {
    id: 'corvus-warm',
    label: '5 · Corvus warm',
    user: 'Put Corvus on the master, warm.',
    run: async (api, say) => withEditing(api, PROJECT, async () => {
      const call = toolCalls(api, say)
      await call('rookery_mix(target="master", fx=[Corvus FX, limiter])', () => api.agentEdit({
        name: PROJECT,
        tool: 'rookery_mix',
        op: 'mix',
        target: 'master',
        fx: [
          { type: 'vst3', path: CORVUS_PATH, params: { Drive: 0.35, Warmth: 0.6 } },
          { type: 'limiter', ceiling_db: -1 }
        ]
      }))
      await call('rookery_fx_param(Drive=0.42)', () => api.agentEdit({
        name: PROJECT, tool: 'rookery_fx_param', op: 'fx_param', target: 'master', index: 0, param: 'Drive', value: 0.42
      }))
      await call('rookery_fx_param(Warmth=0.72)', () => api.agentEdit({
        name: PROJECT, tool: 'rookery_fx_param', op: 'fx_param', target: 'master', index: 0, param: 'Warmth', value: 0.72
      }))
      const rendered = await call('rookery_render()', () => api.handle('POST', '/render', { name: PROJECT }))
      say(`Corvus is on the master with Drive 0.42 and Warmth 0.72. Render ${rendered.hash.slice(0, 12)}. ${checksSummary(rendered)}`, 'agent')
    })
  },
  {
    id: 'same-prompt-new-project',
    label: '6 · Same prompt, new project',
    user: 'Same prompt, new project.',
    run: async (api, say) => {
      api.setAgentEditing('dusty-90-b', true)
      try {
        const call = toolCalls(api, say)
        if (!firstRenderHash) {
          api.setAgentEditing(PROJECT, true)
          try {
            const baseline = await buildBeat(api, call, PROJECT)
            firstRenderHash = baseline.hash
          } finally {
            api.setAgentEditing(PROJECT, false)
          }
        }
        const rendered = await buildBeat(api, call, 'dusty-90-b')
        say(`Original ${firstRenderHash}. New ${rendered.hash}. Match: ${firstRenderHash === rendered.hash ? 'yes' : 'no'}.`, 'agent')
      } finally {
        api.setAgentEditing('dusty-90-b', false)
      }
    }
  }
]
