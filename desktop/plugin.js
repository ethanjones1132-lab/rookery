// Rookery: the beat lab Hermes plays like an instrument.
// Hermes Desktop disk plugin: plain ESM, no JSX, no build step. Only
// @hermes/plugin-sdk and react may be imported. Every color comes from Hermes
// theme variables, so it reskins with any theme.
//
// Data: docs/contract.md (REST at /api/plugins/rookery, events plugin.rookery.*).
// Design brief: docs/design/flock.md.
import * as sdk from '@hermes/plugin-sdk'
import { Component, createElement as h, Fragment, memo, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react'

const { host, ROUTES_AREA, SIDEBAR_NAV_AREA } = sdk

const ID = 'rookery'
const EV = `plugin.${ID}.`
const STAGGER_MS = 12
const POLL_MS = 2000
const REV_POLL_MS = 1500
const RENDER_DEBOUNCE_MS = 450
const CORVUS_URL = 'https://github.com/ethanjones1132-lab/CorvusFx/releases'
const SOUNDZA_URL = 'https://soundza.com'

const CHECKS = [
  ['length_exact', 'Exact length'],
  ['no_clipping', 'No clipping'],
  ['loudness', 'Loudness'],
  ['seam_click', 'Seamless loop'],
  ['not_silent', 'Not silent'],
  ['deterministic', 'Deterministic']
]
// Sample-led starters: these prompts ask for a bed and a lead, not just drums.
export const PROMPTS = [
  'Dusty rhodes and flute boom bap at 90, 8 bars.',
  'Dark piano and pluck trap at 140, 8 bars.',
  'Lo-fi piano bed with a soft bell lead at 72.'
]

// ── fallbacks when push events are lost ───────────────────────────────────
// The page normally hears `plugin.rookery.*` over the gateway event stream, but
// a broken publisher (or a tool that ran in another process) can drop every
// event. These two helpers keep the page honest without it: poll the open
// project's revision while the window is visible, and follow a project that
// appeared while the event stream was down (the `project.updated` handler does
// the same for an agent edit). Exported for dev/preview/check-mock.mjs, which
// imports this file with stubbed React/SDK modules.

// Run `poll` every `intervalMs` while visible, and once immediately whenever
// the window becomes visible again. Returns a disposer.
export function startRevWatch({ poll, intervalMs = REV_POLL_MS, setInterval: startTimer, addEventListener: listen, document: doc }) {
  let stopped = false
  const visible = () => !doc || doc.visibilityState !== 'hidden'
  const tick = () => { if (!stopped && visible()) poll() }
  const stopTimer = startTimer(tick, intervalMs)
  const off = doc && listen
    ? listen(doc, 'visibilitychange', () => { if (!stopped && visible()) poll() })
    : () => {}
  return () => {
    if (stopped) return
    stopped = true
    stopTimer()
    off()
  }
}

// One name the page has never listed is one an agent (or another window)
// created while this page was detached. More than one at once is ambiguous:
// leave the choice to the project switcher.
export function newlyCreatedProject({ previous, current, list }) {
  if (!previous.length || !list.length) return null
  const known = new Set(previous)
  const fresh = list.map(project => project.name).filter(name => !known.has(name))
  return fresh.length === 1 && fresh[0] !== current ? fresh[0] : null
}

// When the backend times out (Hermes logs 30 s reads on every poll), backing off
// keeps the page from stacking a new request the moment the old one expires.
// First failure waits 2 s, then 5/10/20, capped at 30 s; success resets it.
export function retryDelay(failures) {
  const steps = [2000, 5000, 10000, 20000, 30000]
  if (!(failures > 0)) return 0
  return steps[Math.min(Math.floor(failures), steps.length) - 1]
}

// A queued edit belongs to the project that was open when the user clicked. If
// the page switched projects while the request waited in the queue, drop it.
export function editBelongsTo(target, current) {
  return !!target && target === current
}

// Mix notes and pairwise sample fit come from a loop render only (song renders
// have no single loop to compare). Keep the page's summary compact.
export function mixHighlights(render) {
  const notes = Array.isArray(render?.mix_notes) ? render.mix_notes.filter(note => typeof note === 'string') : []
  const pairs = (Array.isArray(render?.fit) ? render.fit : []).map(pair => {
    const register = Math.round((Number(pair?.register_overlap) || 0) * 100)
    const rhythm = Math.round((Number(pair?.rhythm_overlap) || 0) * 100)
    return { key: `${pair?.a}:${pair?.b}`, label: `${pair?.a} ↔ ${pair?.b}`, detail: `register ${register}% · rhythm ${rhythm}%` }
  })
  return { notes: notes.slice(0, 4), pairs: pairs.slice(0, 3) }
}


// ── styles ────────────────────────────────────────────────────────────────
// Runtime plugins can't count on the app's Tailwind build containing arbitrary
// classes, so Rookery ships scoped CSS. It's rendered inside the page and
// unmounts with it. Tokens only: no literal colors.
const CSS = `
.rk{--rk-pad-h:30px;--rk-head-w:184px;--rk-gap:10px;height:100%;overflow:auto;color:var(--ui-text-primary);font-variant-numeric:tabular-nums;outline:none}
.rk-in{max-width:1480px;margin:0 auto;padding:18px 24px 32px;display:flex;flex-direction:column;gap:14px}
.rk-in>*{animation:rk-enter .28s ease-out both;animation-delay:calc(var(--rk-enter,0) * 30ms)}
.rk-in>.rk-tp{--rk-enter:0}.rk-in>.rk-wave{--rk-enter:1}.rk-in>.rk-flock{--rk-enter:2}.rk-in>.rk-rack{--rk-enter:3}
.rk button{font:inherit;color:inherit;background:none;border:0;padding:0;cursor:pointer}
.rk button:focus-visible,.rk [tabindex]:focus-visible{outline:2px solid var(--ui-accent);outline-offset:2px;border-radius:5px}
.rk-mono{font-family:var(--dt-font-mono,ui-monospace,monospace)}
.rk-q{color:var(--ui-text-tertiary)}.rk-qq{color:var(--ui-text-quaternary)}
.rk-label{font-size:10.5px;letter-spacing:.06em;text-transform:uppercase;color:var(--ui-text-quaternary)}

/* transport */
.rk-tp{position:relative;z-index:30;display:flex;align-items:center;gap:18px;min-height:40px;flex-wrap:wrap}
.rk-tp-group{display:flex;align-items:center;gap:10px}
.rk-sep{width:1px;height:20px;background:var(--ui-stroke-tertiary)}
.rk-play{width:34px;height:34px;border-radius:50%!important;display:grid;place-items:center;background:var(--ui-bg-quaternary)!important;transition:background-color .1s}
.rk-play:hover{background:var(--ui-control-hover-background)!important;transition:none}
.rk-play[data-on="true"]{background:var(--ui-accent)!important;color:var(--dt-primary-foreground,var(--ui-bg-editor))}
.rk-play svg{width:14px;height:14px;fill:currentColor}
.rk-proj{display:flex;align-items:center;gap:6px;font-size:14px;font-weight:600;letter-spacing:.005em;padding:4px 6px!important;margin-left:-6px;border-radius:6px}
.rk-proj:hover{background:var(--ui-control-hover-background)}
.rk-proj svg{width:12px;height:12px;stroke:var(--ui-text-tertiary);fill:none;stroke-width:1.6}
.rk-field{display:flex;flex-direction:column;gap:2px;min-width:0}
.rk-num{font-size:15px;font-weight:550;cursor:ns-resize;user-select:none;border-radius:4px;padding:0 2px;margin:0 -2px;line-height:1.2}
.rk-num:hover{background:var(--ui-control-hover-background)}
.rk-num input{width:3.2em;font:inherit;color:inherit;background:var(--ui-bg-input,transparent);border:1px solid var(--ui-accent);border-radius:4px;padding:0 3px;outline:none}
.rk-seg{display:flex;background:var(--ui-bg-quaternary);border-radius:6px;padding:2px}
.rk-seg button{font-size:12px!important;padding:2px 9px!important;border-radius:4px;color:var(--ui-text-tertiary)!important}
.rk-seg button[aria-pressed="true"]{background:var(--ui-bg-editor);color:var(--ui-text-primary)!important;box-shadow:0 0 0 1px var(--ui-stroke-tertiary)}
.rk-spacer{flex:1}
.rk-live{display:flex;align-items:center;gap:7px;font-size:12px;color:var(--ui-text-quaternary);transition:color .2s}
.rk-live i{width:7px;height:7px;border-radius:50%;background:currentColor}
.rk-live[data-on="true"]{color:var(--ui-accent)}
.rk-live[data-on="true"] i{animation:rk-breathe 1.1s ease-in-out infinite;box-shadow:0 0 8px currentColor}
.rk-render{font-size:12px!important;padding:6px 11px!important;border-radius:7px;background:var(--ui-bg-quaternary)!important;display:flex;align-items:center;gap:7px}
.rk-render:hover:not([disabled]){background:var(--ui-control-hover-background)!important}
.rk-render[disabled]{cursor:default!important;color:var(--ui-text-tertiary)}
.rk-render[data-failed="true"]{color:var(--ui-red)!important;border:1px solid color-mix(in srgb,var(--ui-red) 45%,transparent)!important}
.rk-arr{display:flex;flex-direction:column;gap:8px;padding:2px 0 4px}
.rk-arr-empty{font-size:12px;color:var(--ui-text-quaternary);text-align:left;padding:7px 2px!important;border-bottom:1px solid var(--ui-stroke-tertiary)}
.rk-arr-empty:hover{color:var(--ui-text-secondary)!important}
.rk-arr-line{display:flex;gap:4px;min-height:34px;position:relative}
.rk-arr-block{position:relative;min-width:56px;flex:var(--repeat);display:flex;align-items:center;justify-content:center;gap:5px;padding:5px!important;border:1px solid var(--ui-stroke-tertiary)!important;border-radius:6px;background:var(--ui-bg-quaternary)!important;font-size:11px!important;overflow:hidden;white-space:nowrap}
.rk-arr-block[aria-pressed="true"]{border-color:var(--ui-accent)!important;color:var(--ui-text-primary);box-shadow:inset 0 0 0 1px var(--ui-accent)}
.rk-arr-block[data-current="true"]{background:color-mix(in srgb,var(--ui-accent) 18%,var(--ui-bg-quaternary))!important}
.rk-arr-block small{color:var(--ui-text-quaternary)}
.rk-arr-ph{position:absolute;z-index:2;left:0;top:0;bottom:0;width:2px;background:var(--ui-accent);box-shadow:0 0 7px var(--ui-accent);pointer-events:none;display:none}
.rk-arr-line[data-playing="true"] .rk-arr-ph{display:block}
.rk-arr-controls,.rk-arr-mutes{display:flex;align-items:center;gap:6px;flex-wrap:wrap}
.rk-arr-controls{font-size:11px;color:var(--ui-text-tertiary)}
.rk-arr-controls button,.rk-arr-toggle{padding:3px 7px!important;border-radius:5px;background:var(--ui-bg-quaternary)!important;font-size:11px!important}
.rk-arr-controls button:hover,.rk-arr-toggle:hover{background:var(--ui-control-hover-background)!important}
.rk-arr-mutes{padding-top:4px;border-top:1px solid var(--ui-stroke-tertiary)}
.rk-arr-toggle{display:inline-flex;align-items:center;gap:5px;color:var(--ui-text-secondary)!important}
.rk-arr-toggle[data-muted="true"]{background:color-mix(in srgb,var(--ui-orange) 22%,transparent)!important;color:var(--ui-orange)!important;text-decoration:line-through}
.rk-arr-toggle i{width:7px;height:7px;border-radius:50%;background:var(--ui-accent)}
.rk-arr-toggle[data-muted="true"] i{background:transparent;box-shadow:inset 0 0 0 1.5px var(--ui-orange)}
.rk-arr-hint{font-size:11px;color:var(--ui-text-quaternary);margin-left:2px}
.rk-arr-name{width:110px;font-size:11px;padding:2px 5px;border-radius:5px;border:1px solid var(--ui-accent);background:var(--ui-bg-input);color:var(--ui-text-primary);outline:none}
.rk-render[data-busy="true"] i{width:10px;height:10px;border-radius:50%;border:1.5px solid var(--ui-stroke-secondary);border-top-color:var(--ui-accent);animation:rk-spin .7s linear infinite}

/* checks + hash */
.rk-checks{position:relative}
.rk-checks-btn{display:flex;align-items:center;gap:8px;padding:5px 8px!important;border-radius:7px}
.rk-checks-btn:hover,.rk-checks[data-open="true"] .rk-checks-btn{background:var(--ui-control-hover-background)}
.rk-leds{display:flex;gap:4px}
.rk-led{width:7px;height:7px;border-radius:50%;background:var(--ui-stroke-secondary);transition:background-color .25s,box-shadow .25s}
.rk-led[data-s="pass"]{background:var(--ui-success,var(--ui-green));box-shadow:0 0 6px color-mix(in srgb,var(--ui-success,var(--ui-green)) 70%,transparent);transition-delay:calc(var(--led-i,0) * 40ms)}
.rk-led[data-s="fail"]{background:var(--ui-red);box-shadow:0 0 6px color-mix(in srgb,var(--ui-red) 70%,transparent)}
.rk-led[data-s="stale"]{background:color-mix(in srgb,var(--ui-success,var(--ui-green)) 35%,var(--ui-stroke-secondary))}
.rk-checks-n{font-size:12px;color:var(--ui-text-tertiary)}
.rk-mix{position:relative;font-size:12px;color:var(--ui-text-tertiary)}
.rk-mix-btn{padding:5px 8px!important;border-radius:7px;white-space:nowrap}
.rk-mix-btn:hover,.rk-mix[data-open="true"] .rk-mix-btn{background:var(--ui-control-hover-background)}
.rk .rk-mix-pop,.rkc .rk-mix-pop{position:absolute;right:0;top:calc(100% + 6px);z-index:29;width:260px;padding:10px;border-radius:9px;background:var(--ui-widget-surface-background,var(--ui-bg-editor))!important;border:1px solid var(--ui-stroke-tertiary);box-shadow:var(--shadow-nous,none)}
.rk-mix-bands{display:flex;height:8px;overflow:hidden;border-radius:4px;margin:2px 0 9px;background:var(--ui-bg-tertiary)}
.rk-mix-bands i{height:100%;background:color-mix(in srgb,var(--ui-accent) calc(50% + var(--i) * 10%),var(--ui-bg-elevated))}
.rk-mix-band-labels{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:1px;margin-bottom:8px;font-size:9px;color:var(--ui-text-tertiary);font-variant-numeric:tabular-nums}
.rk-mix-band-labels span{text-align:center;white-space:nowrap;letter-spacing:-.025em}
.rk-mix-stats{display:grid;grid-template-columns:1fr 1fr;gap:5px 10px;font-size:11px}
.rk-mix-stats>div{display:flex;justify-content:space-between;gap:8px;min-width:0}.rk-mix-stats span{color:var(--ui-text-quaternary)}.rk-mix-stats b{color:var(--ui-text-secondary);font-weight:500;white-space:nowrap}
.rk-mix-notes{margin-top:9px;padding-top:8px;border-top:1px solid var(--ui-stroke-tertiary);display:flex;flex-direction:column;gap:5px;max-height:150px;overflow-y:auto}
.rk-mix-notes p{margin:0;font-size:10.5px;line-height:1.45;color:var(--ui-text-secondary)}
.rk-mix-fit{display:flex;justify-content:space-between;gap:8px;font-size:10.5px;color:var(--ui-text-secondary)}
.rk-mix-fit span{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.rk-mix-fit b{font-weight:500;color:var(--ui-text-quaternary);white-space:nowrap}
.rk-pop{position:absolute;right:0;top:calc(100% + 6px);z-index:30;width:320px;padding:8px;border-radius:10px;background:var(--ui-bg-elevated);box-shadow:var(--shadow-nous,0 8px 30px color-mix(in srgb,var(--ui-base) 0%,transparent));border:1px solid var(--stroke-nous,var(--ui-stroke-tertiary))}
.rk-pop-row{display:grid;grid-template-columns:12px 1fr auto;gap:8px;align-items:baseline;padding:6px 6px;border-radius:6px;font-size:12px}
.rk-pop-row .rk-led{transform:translateY(-1px)}
.rk-pop-val{color:var(--ui-text-secondary);font-size:11.5px}
.rk-pop-tgt{grid-column:2/4;color:var(--ui-text-quaternary);font-size:11px;margin-top:-2px}
.rk-pop-hint{grid-column:2/4;color:var(--ui-red);font-size:11.5px}
.rk-pop-foot{border-top:1px solid var(--ui-stroke-tertiary);margin-top:6px;padding:8px 6px 2px;font-size:11px;color:var(--ui-text-quaternary);display:flex;justify-content:space-between;gap:8px}
.rk-hash{font-size:11.5px;color:var(--ui-text-tertiary);padding:5px 7px!important;border-radius:6px;animation:rk-pulse .32s ease-out}
.rk-hash:hover{background:var(--ui-control-hover-background);color:var(--ui-text-secondary)}
.rk-hash[data-pulse="true"]{animation:rk-pulse .32s ease-out}
.rk-content{animation:rk-project .24s ease-out both}
.rk-undo .codicon{display:inline-block;animation:rk-undo .32s ease-out}
.rk-save .codicon{display:inline-block;animation:rk-save .24s ease-out}
.rk-match{font-size:11.5px;color:var(--ui-success,var(--ui-green));display:flex;align-items:center;gap:6px;animation:rk-match 1.6s ease-out}
.rk-match svg{width:12px;height:12px;stroke:currentColor;fill:none;stroke-width:2}

/* waveform */
.rk-wave{position:relative;height:76px;border-radius:8px;background:color-mix(in srgb,var(--ui-base) 3%,transparent);overflow:hidden}
.rk-wave canvas{position:absolute;inset:0;width:100%;height:100%}
.rk-wave-lit{position:absolute;inset:0;clip-path:inset(0 100% 0 0)}
.rk-wave[data-stale="true"] canvas{opacity:.38}
.rk-wave-ph{position:absolute;top:0;bottom:0;left:0;width:1.5px;background:var(--ui-accent);box-shadow:0 0 10px var(--ui-accent);opacity:0;will-change:transform}
.rk-wave[data-playing="true"] .rk-wave-ph{opacity:1}
.rk-wave-bars{position:absolute;inset:0;display:flex;pointer-events:none}
.rk-wave-bars span{flex:1;border-left:1px solid var(--ui-stroke-quaternary);font-size:10px;color:var(--ui-text-quaternary);padding:4px 6px}
.rk-wave-bars span:first-child{border-left:0}
.rk-wave-note{position:absolute;right:10px;bottom:7px;font-size:11px;color:var(--ui-text-quaternary)}

/* rack */
.rk-rack{display:flex;flex-direction:column;gap:4px}
.rk-row{position:relative;display:grid;grid-template-columns:var(--rk-head-w) 1fr 10px;align-items:center;gap:14px;padding:3px 0;border-radius:8px}
.rk-flash{position:absolute;inset:-2px -8px;border-radius:9px;pointer-events:none;animation:rk-row .9s ease-out both;background:color-mix(in srgb,var(--ui-accent) 0%,transparent)}
.rk-th{display:flex;align-items:center;gap:8px;min-width:0}
.rk-ms{display:flex;gap:2px}
.rk-ms button{width:20px;height:20px;border-radius:4px;font-size:10.5px!important;font-weight:650;color:var(--ui-text-quaternary)!important;background:var(--ui-bg-quaternary)!important}
.rk-ms button:hover{color:var(--ui-text-secondary)!important}
.rk-ms button[data-k="m"][aria-pressed="true"]{background:color-mix(in srgb,var(--ui-orange) 28%,transparent)!important;color:var(--ui-orange)!important}
.rk-ms button[data-k="s"][aria-pressed="true"]{background:color-mix(in srgb,var(--ui-yellow) 28%,transparent)!important;color:var(--ui-yellow)!important}
.rk-tn{display:flex;flex-direction:column;min-width:0;line-height:1.25}
.rk-tn b{font-weight:600;font-size:12.5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.rk-tn span{font-size:11px;color:var(--ui-text-quaternary);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.rk-tn .rk-role{display:inline-block;margin-left:5px;padding:0 4px;border-radius:4px;font-size:9px;letter-spacing:.05em;text-transform:uppercase;background:var(--ui-bg-quaternary);color:var(--ui-text-tertiary)}
.rk-credit-link{align-self:flex-start;margin-top:1px;text-transform:none;letter-spacing:0;line-height:1.2;cursor:pointer}
.rk-credit-link:hover{color:var(--ui-text-secondary)!important;text-decoration:underline}
.rk-row[data-flash="true"] .rk-tn b{animation:rk-name .9s ease-out}
.rk-gain{margin-left:auto;font-size:11px;color:var(--ui-text-tertiary);cursor:ns-resize;user-select:none;padding:1px 4px;border-radius:4px;white-space:nowrap}
.rk-gain:hover{background:var(--ui-control-hover-background);color:var(--ui-text-secondary)}
.rk-row[data-muted="true"] .rk-grid{opacity:.35}
.rk-grid{display:grid;gap:var(--rk-gap);transition:opacity .15s}
.rk-bar{display:grid;grid-template-columns:repeat(16,1fr);gap:3px}
.rk-pad{position:relative;height:var(--rk-pad-h);border-radius:4px!important;background:var(--ui-bg-tertiary)!important;overflow:hidden;box-shadow:inset 0 0 0 1px var(--ui-stroke-quaternary)}
.rk-rack .rk-pad{animation:rk-ripple .24s ease-out both;animation-delay:calc(var(--i) * 12ms)}
.rk-pad[data-beat="true"]{background:var(--ui-bg-secondary)!important}
.rk-pad:hover{box-shadow:inset 0 0 0 1px var(--ui-stroke-secondary)}
.rk-pad i{position:absolute;left:0;right:0;bottom:0;height:0;background:var(--ui-accent);transition:height .22s cubic-bezier(.2,.8,.2,1)}
.rk-pad[data-on="true"]{box-shadow:0 0 12px -2px color-mix(in srgb,var(--ui-accent) 55%,transparent),inset 0 0 0 1px color-mix(in srgb,var(--ui-accent) 70%,transparent)}
.rk-pad[data-on="true"] i{height:calc(var(--v,1) * 100%)}
.rk-pad em{position:absolute;inset:0;display:grid;place-items:center;font-style:normal;font-size:10px;font-weight:650;color:var(--dt-primary-foreground,var(--ui-bg-editor))}
.rk-pad[data-ph]{background:color-mix(in srgb,var(--ui-accent) 16%,var(--ui-bg-secondary))!important}
.rk-pad[data-ph][data-on="true"] i{filter:brightness(1.35)}
.rk-pad[data-lit="on"] i{animation:rk-lit .46s cubic-bezier(.2,.8,.2,1) both}
.rk-pad[data-lit="on"]{animation:rk-glow .7s ease-out both}
.rk-pad[data-lit="off"]{animation:rk-off .4s ease-out both}
.rk-pad[data-ripple="true"]{animation:rk-ripple .24s ease-out both;animation-delay:calc(var(--i) * 12ms)}
.rk-meter{position:relative;height:var(--rk-pad-h);border-radius:3px;background:var(--ui-bg-tertiary);overflow:hidden}
.rk-meter i{position:absolute;left:0;right:0;bottom:0;background:color-mix(in srgb,var(--ui-success,var(--ui-green)) 75%,transparent);transition:height .3s}
.rk-meter b{position:absolute;left:0;right:0;height:1.5px;background:var(--ui-text-secondary);transition:bottom .3s}

/* master */
.rk-master{display:grid;grid-template-columns:var(--rk-head-w) 1fr;gap:14px;align-items:start;padding-top:14px;margin-top:4px;border-top:1px solid var(--ui-stroke-tertiary)}
.rk-chain{display:flex;align-items:stretch;gap:8px;flex-wrap:wrap}
.rk-fx{display:flex;flex-direction:column;gap:8px;padding:9px 12px;border-radius:9px;background:color-mix(in srgb,var(--ui-base) 3.5%,transparent);min-width:120px}
.rk-fx-h{display:flex;align-items:baseline;gap:8px;font-size:12.5px;font-weight:600}
.rk-fx-h span{font-weight:400;font-size:11px;color:var(--ui-text-quaternary)}
.rk-fx[data-vst="true"]{background:color-mix(in srgb,var(--ui-accent) 7%,transparent);box-shadow:inset 0 0 0 1px color-mix(in srgb,var(--ui-accent) 22%,transparent)}
.rk-knobs{display:flex;gap:14px}
.rk-arrow{align-self:center;color:var(--ui-text-quaternary);font-size:12px}
.rk-get{display:flex;flex-direction:column;gap:3px;padding:9px 12px;border-radius:9px;border:1px dashed var(--ui-stroke-secondary);font-size:12px;text-align:left}
.rk-get:hover{border-color:var(--ui-accent)}
.rk-get b{font-weight:600}.rk-get span{color:var(--ui-text-tertiary);font-size:11px}

/* knob */
.rk-knob{display:flex;flex-direction:column;align-items:center;gap:3px;font-size:10.5px;color:var(--ui-text-tertiary);user-select:none}
.rk-knob svg{width:var(--ks,30px);height:var(--ks,30px);cursor:ns-resize;overflow:visible;touch-action:none}
.rk-knob .tr{stroke:var(--ui-stroke-secondary)}.rk-knob .val{stroke:var(--ui-accent);transition:stroke-dashoffset .35s cubic-bezier(.2,.8,.2,1)}
.rk-knob .ptr{stroke:var(--ui-text-primary);transform-origin:50% 50%;transition:transform .35s cubic-bezier(.2,.8,.2,1)}
.rk-knob[data-drag="true"] .val,.rk-knob[data-drag="true"] .ptr{transition:none}
.rk-knob-row{display:flex;align-items:center;gap:8px}
.rk-knob-row .rk-knob{--ks:26px}

/* menu */
.rk-menu-wrap{position:relative}
.rk-menu{position:absolute;left:-6px;top:calc(100% + 4px);z-index:30;min-width:240px;padding:4px;border-radius:9px;background:var(--ui-bg-elevated);box-shadow:var(--shadow-nous,none);border:1px solid var(--stroke-nous,var(--ui-stroke-tertiary))}
.rk-menu button{display:flex;width:100%;justify-content:space-between;gap:12px;padding:6px 8px!important;border-radius:6px;font-size:12.5px!important;text-align:left}
.rk-menu button:hover,.rk-menu button[aria-current="true"]{background:var(--ui-row-hover-background,var(--ui-control-hover-background))}
.rk-menu button span{color:var(--ui-text-quaternary);font-size:11px}

/* states */
.rk-empty{min-height:60vh;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:10px;text-align:center;padding:24px}
.rk-empty h2{margin:0;font-size:19px;font-weight:600;letter-spacing:-.005em}
.rk-empty p{margin:0;max-width:420px;color:var(--ui-text-tertiary);line-height:1.5;font-size:13px}
.rk-ghost{display:grid;grid-template-columns:repeat(16,1fr);gap:3px;width:min(420px,80%);margin-bottom:14px}
.rk-ghost i{height:16px;border-radius:3px;background:var(--ui-bg-tertiary)}
.rk-ghost i[data-on="true"]{background:color-mix(in srgb,var(--ui-accent) 55%,transparent);animation:rk-ghost 2.4s ease-in-out infinite;animation-delay:calc(var(--d) * 90ms)}
.rk-chips{display:flex;gap:8px;flex-wrap:wrap;justify-content:center;margin-top:8px}
.rk-empty .rk-point{margin-top:6px;font-size:12.5px;color:var(--ui-text-secondary)}
.rk-point span{display:inline-block;color:var(--ui-accent);animation:rk-nudge 1.8s ease-in-out infinite}
@keyframes rk-nudge{50%{transform:translateX(4px)}}
.rk-chip{font-size:12.5px!important;padding:7px 12px!important;border-radius:999px;background:var(--ui-bg-quaternary)!important;transition:background-color .1s}
.rk-chip:hover{background:var(--ui-control-hover-background)!important;transition:none}
.rk-chip.rk-chip-primary{background:var(--ui-accent)!important;color:var(--dt-primary-foreground,var(--ui-text-primary))!important;font-weight:550}
.rk-chip.rk-chip-primary:hover{background:color-mix(in srgb,var(--ui-accent) 88%,var(--ui-text-primary))!important}
.rk-banner{display:flex;align-items:center;gap:10px;padding:9px 12px;border-radius:8px;font-size:12.5px;background:color-mix(in srgb,var(--ui-red) 9%,transparent);color:var(--ui-text-secondary)}
.rk-banner b{color:var(--ui-red);font-weight:600}
.rk-banner button{margin-left:auto;font-size:12px!important;color:var(--ui-text-tertiary)!important}
.rk-skel{height:var(--rk-pad-h);border-radius:6px;background:var(--ui-bg-tertiary);animation:rk-breathe 1.4s ease-in-out infinite}

@keyframes rk-breathe{50%{opacity:.4}}
@keyframes rk-enter{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}
@keyframes rk-spin{to{transform:rotate(360deg)}}
@keyframes rk-lit{0%{transform:scaleY(.15);filter:brightness(2.4)}60%{filter:brightness(1.4)}100%{transform:none;filter:none}}
@keyframes rk-glow{0%{box-shadow:0 0 22px 2px var(--ui-accent),inset 0 0 0 1px var(--ui-accent)}}
@keyframes rk-off{0%{background:color-mix(in srgb,var(--ui-accent) 40%,var(--ui-bg-tertiary))}}
@keyframes rk-row{0%{background:color-mix(in srgb,var(--ui-accent) 13%,transparent)}100%{background:color-mix(in srgb,var(--ui-accent) 0%,transparent)}}
@keyframes rk-name{0%{color:var(--ui-accent)}}
@keyframes rk-match{0%{text-shadow:0 0 12px currentColor}}
@keyframes rk-project{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}
@keyframes rk-ripple{from{opacity:.45;transform:translateX(-5px)}to{opacity:1;transform:none}}
@keyframes rk-pulse{50%{transform:scale(1.08);color:var(--ui-accent)}}
@keyframes rk-undo{to{transform:rotate(-360deg)}}
@keyframes rk-save{50%{transform:scale(1.25)}}
@keyframes rk-ghost{0%,100%{opacity:.35}50%{opacity:1}}
@media (max-width:860px){.rk{--rk-head-w:120px}.rk-gain{display:none}.rk-in{padding:14px 14px 24px}}
@media (prefers-reduced-motion:reduce){.rk *{animation:none!important;transition:none!important}}
`

// ── helpers ───────────────────────────────────────────────────────────────
const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v))
const loopLen = p => p.bars * (p.steps_per_bar || 16)
const isHit = c => c !== '.' && c !== undefined
const swingPct = s => Math.round(50 + (s || 0) * 25)
const fmtDb = v => (v > 0 ? '+' : '') + (Math.round(v * 10) / 10).toFixed(1) + ' dB'
const shortHash = hsh => (hsh ? hsh.slice(0, 7) : '·······')
const fxName = fx => {
  if (fx.type === 'vst3') return (fx.name || String(fx.path || '').split(/[\\/]/).pop().replace(/\.vst3$/i, '') || 'VST3').replace(/^DrippyFX$/i, 'Corvus FX')
  return { compressor: 'Compressor', limiter: 'Limiter', reverb: 'Reverb', delay: 'Delay', distortion: 'Distortion', chorus: 'Chorus', highpass: 'High-pass', lowpass: 'Low-pass' }[fx.type] || fx.type
}
const fxDetail = fx => fx.type === 'limiter' ? `${fx.ceiling_db ?? -1} dB` : fx.type === 'highpass' || fx.type === 'lowpass' ? `${fx.cutoff_hz ?? ''} Hz` : fx.type === 'vst3' ? 'VST3' : ''

// A VST can expose dozens of parameters (Corvus FX has 27). Show what the agent
// touched first, then a few musical macros, capped at six knobs.
const MACROS = ['master_drive', 'fatness', 'overall', 'master_width', 'reverb_mix', 'delay_mix', 'chorus_mix', 'output_trim', 'Drive', 'Warmth', 'Tone', 'Width', 'Mix']
const HIDE = /bypass|preset|program/i
function curateParams(all, touched = {}) {
  const pickd = [], seen = new Set()
  const add = pp => { if (pp && !seen.has(pp.name) && !HIDE.test(pp.name) && pickd.length < 6) { seen.add(pp.name); pickd.push(pp) } }
  Object.keys(touched || {}).forEach(n => add(all.find(pp => pp.name === n)))
  MACROS.forEach(n => add(all.find(pp => pp.name === n)))
  if (all.length <= 6) all.forEach(add)
  return pickd
}
const PARAM_NAMES = { master_drive: 'Drive', fatness: 'Warmth', overall: 'Amount', master_width: 'Width', output_trim: 'Trim', master_mid_drive: 'Mid drive', master_side_drive: 'Side drive' }
const paramLabel = n => PARAM_NAMES[n] || n.replace(/_/g, ' ').replace(/\b\w/, c => c.toUpperCase()).replace(/ hz$/i, ' Hz').replace(/ ms$/i, ' ms')

function velocityAt(track, i) {
  const vel = track.velocity && track.velocity.length ? track.velocity : [1]
  let k = 0
  for (let j = 0; j < i; j++) if (isHit(track.steps[j])) k++
  return clamp(vel[k % vel.length] ?? 1, 0.05, 1)
}

function b64ToBytes(b64) {
  const bin = atob(b64)
  const out = new Uint8Array(bin.length)
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i)
  return out.buffer
}

// Canvas can't read CSS variables or color-mix(); resolve through the DOM.
function resolveColor(el, cssValue) {
  const probe = document.createElement('span')
  probe.style.color = cssValue
  probe.style.display = 'none'
  el.appendChild(probe)
  const c = getComputedStyle(probe).color
  probe.remove()
  return c
}

export function applyDiffLocally(project, diff) {
  if ((diff || []).some(d => d.field === 'flock')) return null
  const next = { ...project, tracks: project.tracks.map(t => ({ ...t })) }
  for (const d of diff || []) {
    // Changing bars resizes every step string on the server. Reload rather than
    // painting an 8-bar transport over 4-bar patterns.
    if (!d.track && d.field === 'bars') return null
    if (!d.track && (d.field === 'bpm' || d.field === 'swing')) { next[d.field] = d.to; continue }
    const t = next.tracks.find(x => x.id === d.track)
    if (!t) return null
    if (d.field === 'steps' || d.field === 'velocity') t[d.field] = d.to
    else if (['gain_db', 'pan', 'mute', 'solo', 'pitch', 'source'].includes(d.field)) t[d.field] = d.to
    else return null // structural change: reload instead
  }
  return next
}

function litFromDiff(diff, nonce) {
  const tracks = {}
  for (const d of diff || []) {
    if (!d.track || !Array.isArray(d.steps)) {
      if (d.track) tracks[d.track] = tracks[d.track] || { order: new Map(), off: new Set(), nonce }
      continue
    }
    const t = (tracks[d.track] = tracks[d.track] || { order: new Map(), off: new Set(), nonce })
      d.steps.forEach((s, k) => {
      const column = s % 16
      t.order.set(s, d.field === 'steps' && !isHit(d.to?.[s]) ? 15 - column : column)
      if (d.field === 'steps' && !isHit(d.to?.[s])) t.off.add(s)
    })
  }
  return { nonce, tracks }
}

// ── audio engine: sample-accurate looping through Web Audio ────────────────
// One loop plays at a time across the page and every chat card.
const ENGINES = new Set()
class Engine {
  constructor() { this.ac = null; this.buffer = null; this.src = null; this.t0 = 0; this.playing = false; this.subs = new Set(); ENGINES.add(this) }
  ctx() { if (!this.ac) this.ac = new (window.AudioContext || window.webkitAudioContext)(); return this.ac }
  emit() { this.subs.forEach(fn => fn()) }
  async decode(bytes) { return this.ctx().decodeAudioData(bytes) }
  position() { return this.playing && this.buffer ? (this.ctx().currentTime - this.t0) % this.buffer.duration : 0 }
  start(offset) {
    const ac = this.ctx(), s = ac.createBufferSource()
    s.buffer = this.buffer; s.loop = true; s.connect(ac.destination); s.start(0, offset)
    this.src = s; this.t0 = ac.currentTime - offset
  }
  halt() { try { this.src && this.src.stop() } catch {} this.src && this.src.disconnect(); this.src = null }
  setBuffer(buf) {
    const pos = this.position()
    this.buffer = buf
    if (this.playing) {
      this.halt()
      if (buf) this.start(pos % buf.duration)
      else this.playing = false
    }
    this.emit()
  }
  async play() {
    if (!this.buffer) return
    const ac = this.ctx()
    if (ac.state === 'suspended') await ac.resume()
    ENGINES.forEach(e => e !== this && e.playing && e.stop())
    this.halt(); this.start(0); this.playing = true; this.emit()
  }
  stop() { this.halt(); this.playing = false; this.emit() }
  dispose() { this.halt(); this.playing = false; this.ac && this.ac.close().catch(() => {}); this.subs.clear(); ENGINES.delete(this) }
}

// "Open in Rookery" from a chat card: the page picks this project up when it mounts or is already open.
const focusSubs = new Set()
let focusRequest = null
function requestFocus(name) { focusRequest = name; focusSubs.forEach(fn => fn(name)); host.navigate('/rookery') }

// ── small controls ────────────────────────────────────────────────────────
function usePointerDrag(onMove, onEnd) {
  return useCallback(e => {
    if (e.button !== 0) return
    e.preventDefault()
    const el = e.currentTarget, y0 = e.clientY
    el.setPointerCapture?.(e.pointerId)
    const move = ev => onMove(y0 - ev.clientY, ev.shiftKey)
    const up = () => { el.removeEventListener('pointermove', move); el.removeEventListener('pointerup', up); el.removeEventListener('pointercancel', up); onEnd() }
    el.addEventListener('pointermove', move); el.addEventListener('pointerup', up); el.addEventListener('pointercancel', up)
  }, [onMove, onEnd])
}

function Knob({ label, value, min = 0, max = 1, def = min, display, onChange, onCommit, size, caption = true }) {
  const [drag, setDrag] = useState(null)
  const shown = drag ?? value
  const start = useRef(value)
  const frac = (shown - min) / (max - min || 1)
  const R = 13, C = 2 * Math.PI * R, ARC = C * 0.75
  const set = v => { const nv = clamp(v, min, max); setDrag(nv); onChange && onChange(nv) }
  const down = usePointerDrag(
    (dy, fine) => set(start.current + dy * (max - min) / (fine ? 600 : 150)),
    () => setDrag(d => { if (d != null) onCommit(d); return null })
  )
  return h('div', { className: 'rk-knob', 'data-drag': drag != null, style: size ? { '--ks': size + 'px' } : undefined },
    h('svg', {
      viewBox: '0 0 32 32', role: 'slider', tabIndex: 0, 'aria-label': label, 'aria-valuemin': min, 'aria-valuemax': max, 'aria-valuenow': shown,
      'aria-valuetext': display ? display(shown) : String(shown),
      onPointerDown: e => { start.current = value; down(e) },
      onDoubleClick: () => onCommit(def),
      onKeyDown: e => {
        const step = (max - min) / (e.shiftKey ? 100 : 20)
        if (e.key === 'ArrowUp' || e.key === 'ArrowRight') { e.preventDefault(); onCommit(clamp(value + step, min, max)) }
        if (e.key === 'ArrowDown' || e.key === 'ArrowLeft') { e.preventDefault(); onCommit(clamp(value - step, min, max)) }
      }
    },
      h('circle', { className: 'tr', cx: 16, cy: 16, r: R, fill: 'none', strokeWidth: 2.5, strokeLinecap: 'round', strokeDasharray: `${ARC} ${C}`, transform: 'rotate(135 16 16)' }),
      h('circle', { className: 'val', cx: 16, cy: 16, r: R, fill: 'none', strokeWidth: 2.5, strokeLinecap: 'round', strokeDasharray: `${ARC} ${C}`, strokeDashoffset: ARC * (1 - frac), transform: 'rotate(135 16 16)' }),
      h('line', { className: 'ptr', x1: 16, y1: 16, x2: 16, y2: 6.5, strokeWidth: 2, strokeLinecap: 'round', style: { transform: `rotate(${-135 + frac * 270}deg)` } })
    ),
    caption && label && h('span', null, display ? display(shown) : label)
  )
}

function ScrubNumber({ value, min, max, step = 1, format = v => v, label, onCommit, className = 'rk-num' }) {
  const [drag, setDrag] = useState(null)
  const [editing, setEditing] = useState(false)
  const start = useRef(value)
  const down = usePointerDrag(
    (dy, fine) => setDrag(clamp(Math.round((start.current + dy / (fine ? 16 : 4) * step) / step) * step, min, max)),
    () => setDrag(d => { if (d != null && d !== value) onCommit(d); return null })
  )
  if (editing) {
    return h('span', { className },
      h('input', {
        autoFocus: true, defaultValue: value, 'aria-label': label,
        onBlur: e => { setEditing(false); const v = Number(e.target.value); if (Number.isFinite(v)) onCommit(clamp(v, min, max)) },
        onKeyDown: e => { if (e.key === 'Enter') e.currentTarget.blur(); if (e.key === 'Escape') setEditing(false) }
      }))
  }
  return h('span', {
    className, role: 'spinbutton', tabIndex: 0, 'aria-label': label, 'aria-valuenow': drag ?? value,
    onPointerDown: e => { start.current = value; down(e) },
    onDoubleClick: () => setEditing(true),
    onKeyDown: e => {
      if (e.key === 'Enter') setEditing(true)
      if (e.key === 'ArrowUp') { e.preventDefault(); onCommit(clamp(value + step, min, max)) }
      if (e.key === 'ArrowDown') { e.preventDefault(); onCommit(clamp(value - step, min, max)) }
    }
  }, format(drag ?? value))
}

const Icon = {
  play: () => h('svg', { viewBox: '0 0 16 16' }, h('path', { d: 'M4.5 2.8v10.4c0 .5.6.8 1 .5l8-5.2c.4-.3.4-.8 0-1L5.5 2.3c-.4-.3-1 0-1 .5Z' })),
  stop: () => h('svg', { viewBox: '0 0 16 16' }, h('rect', { x: 3.5, y: 3.5, width: 9, height: 9, rx: 1.5 })),
  chev: () => h('svg', { viewBox: '0 0 12 12' }, h('path', { d: 'M3 4.5 6 7.5 9 4.5', strokeLinecap: 'round', strokeLinejoin: 'round' })),
  check: () => h('svg', { viewBox: '0 0 12 12' }, h('path', { d: 'M2.5 6.2 5 8.6 9.5 3.6', strokeLinecap: 'round', strokeLinejoin: 'round' }))
}

// ── project lifecycle ─────────────────────────────────────────────────────
const PROJECT_MENU_NATIVE = !!(sdk.DropdownMenu && sdk.DropdownMenuTrigger && sdk.DropdownMenuContent && sdk.DropdownMenuItem && sdk.Button)
const projectIcon = name => sdk.Codicon ? h(sdk.Codicon, { name }) : h('span', { className: `codicon codicon-${name}`, 'aria-hidden': true })
const PROJECT_ROW = 'gap-2 rounded-none px-2.5 py-1 text-xs'
const PROJECT_LABEL = 'flex min-w-0 flex-1 flex-col'
const PROJECT_META = 'text-[0.625rem] text-(--ui-text-tertiary)'
const projectAge = updated => {
  const timestamp = Date.parse(updated || '')
  if (!Number.isFinite(timestamp)) return '—'
  const date = new Date(timestamp), age = Math.max(0, Date.now() - timestamp)
  if (age < 60000) return 'now'
  const minutes = Math.floor(age / 60000)
  if (minutes < 60) return `${minutes}m`
  const hours = Math.floor(age / 3600000)
  if (hours < 24) return `${hours}h`
  const days = Math.floor(age / 86400000)
  if (days < 30) return `${days}d`
  return new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric' }).format(date)
}

function ProjectActions({ current, projects, onPick, onNew, onRename, onDuplicate, onClear, onDelete }) {
  const { DropdownMenu, DropdownMenuTrigger, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, Button } = sdk
  const [open, setOpen] = useState(false), [armed, setArmed] = useState(false)
  const timer = useRef(null)
  useEffect(() => () => clearTimeout(timer.current), [])
  const select = fn => { setArmed(false); clearTimeout(timer.current); fn?.() }
  if (!PROJECT_MENU_NATIVE) return h(FallbackProjectActions, { current, projects, onPick, onNew, onRename, onDuplicate, onClear, onDelete })
  const row = (key, label, icon, fn, destructive = false) => h(DropdownMenuItem, {
    key, className: `${PROJECT_ROW} ${destructive ? 'text-(--ui-red)' : ''}`,
    onSelect: event => { if (key === 'delete' && !armed) { event.preventDefault(); setArmed(true); timer.current = setTimeout(() => setArmed(false), 3000); return } select(fn) }
  }, projectIcon(icon), label)
  const rows = h(DropdownMenuContent, { align: 'start', side: 'bottom', sideOffset: 4, className: 'min-w-64 p-0' },
    row('new', 'New beat', 'add', onNew),
    DropdownMenuSeparator && h(DropdownMenuSeparator, { className: 'mx-0' }),
    (projects || []).map(p => h(DropdownMenuItem, { key: p.name, className: PROJECT_ROW, onSelect: () => select(() => onPick(p.name)) },
      h('span', { className: PROJECT_LABEL }, h('span', null, p.name), h('span', { className: PROJECT_META }, `${p.bpm} BPM · ${p.bars} bars · ${projectAge(p.updated_at)}`)),
      p.name === current && projectIcon('check'))),
    DropdownMenuSeparator && h(DropdownMenuSeparator, { className: 'mx-0' }),
    row('rename', 'Rename…', 'edit', onRename), row('duplicate', 'Duplicate', 'copy', onDuplicate),
    row('clear', 'Clear pattern', 'clear-all', onClear), row('delete', armed ? `Delete ${current}? Click again` : 'Delete…', 'trash', onDelete, true))
  return h(DropdownMenu, { open, onOpenChange: setOpen },
    h(DropdownMenuTrigger, { asChild: true }, h(Button, { type: 'button', variant: 'ghost', className: NATIVE.pill, 'aria-label': 'Project menu' }, h(Icon.chev))), rows)
}

function FallbackProjectActions({ current, projects, onPick, onNew, onRename, onDuplicate, onClear, onDelete }) {
  const [open, setOpen] = useState(false), [armed, setArmed] = useState(false)
  const wrap = useRef(null), timer = useRef(null)
  useEffect(() => { if (!open) return; const away = e => { if (!wrap.current?.contains(e.target)) setOpen(false) }; const esc = e => { if (e.key === 'Escape') setOpen(false) }; document.addEventListener('pointerdown', away, true); document.addEventListener('keydown', esc); return () => { document.removeEventListener('pointerdown', away, true); document.removeEventListener('keydown', esc) } }, [open])
  useEffect(() => () => clearTimeout(timer.current), [])
  const item = (label, fn, icon, danger = false) => h('button', { type: 'button', role: 'menuitem', className: PROJECT_ROW, style: { display: 'flex', width: '100%', color: danger ? 'var(--ui-red)' : undefined }, onClick: () => { fn?.(); setOpen(false) } }, icon && projectIcon(icon), label)
  return h('div', { ref: wrap, className: 'relative' }, h('button', { type: 'button', className: NATIVE.pill, 'aria-label': 'Project menu', onClick: () => setOpen(v => !v) }, h(Icon.chev)),
    open && h('div', { role: 'menu', className: 'absolute left-0 top-full z-50 min-w-64 rounded-md border border-(--ui-stroke-tertiary) bg-(--ui-bg-elevated) p-1' },
      item('New beat', onNew, 'add'), h('hr', null), (projects || []).map(p => item(`${p.name} · ${p.bpm} BPM · ${p.bars} bars · ${projectAge(p.updated_at)}${p.name === current ? ' ✓' : ''}`, () => onPick(p.name), '')),
      h('hr', null), item('Rename…', onRename, 'edit'), item('Duplicate', onDuplicate, 'copy'), item('Clear pattern', onClear, 'clear-all'),
      item(armed ? `Delete ${current}? Click again` : 'Delete…', () => { if (armed) onDelete?.(); else { setArmed(true); timer.current = setTimeout(() => setArmed(false), 3000) } }, 'trash', true)))
}

function ProjectMenu(props) {
  const { current, renaming, renameError, onRenameStart, onRenameCommit, onRenameCancel } = props
  const input = useRef(null)
  useEffect(() => { if (renaming) { input.current?.focus(); input.current?.select() } }, [renaming])
  return h('div', { className: 'rk-menu-wrap', style: { display: 'flex', alignItems: 'center', gap: 2, position: 'relative' } },
    renaming ? h('div', { className: 'rk-field' }, h('input', { ref: input, defaultValue: current, 'aria-label': 'Project name', className: 'min-w-24 rounded border border-(--ui-accent) bg-(--ui-bg-input) px-1 text-sm text-foreground outline-none', onKeyDown: e => { if (e.key === 'Enter') { e.preventDefault(); onRenameCommit(e.currentTarget.value) } if (e.key === 'Escape') onRenameCancel() }, onBlur: onRenameCancel }), renameError && h('span', { className: 'text-[0.625rem] text-(--ui-red)' }, renameError))
      : h('button', { className: 'rk-proj', title: 'Rename project', onClick: onRenameStart }, current),
    h(ProjectActions, props))
}

// ── transport ─────────────────────────────────────────────────────────────

function Checks({ report, stale, hash, rev, renderRev }) {
  const [open, setOpen] = useState(false)
  const states = CHECKS.map(([k]) => !report ? 'none' : stale ? 'stale' : report[k]?.pass ? 'pass' : 'fail')
  const passed = states.filter(s => s === 'pass' || s === 'stale').length
  return h('div', { className: 'rk-checks', 'data-open': open, onMouseEnter: () => setOpen(true), onMouseLeave: () => setOpen(false) },
    h('button', { className: 'rk-checks-btn', 'aria-expanded': open, onFocus: () => setOpen(true), onBlur: () => setOpen(false), 'aria-label': `Checks: ${report ? passed : 0} of 6 passing` },
      h('span', { className: 'rk-leds' }, states.map((s, i) => h('i', { key: i, className: 'rk-led', 'data-s': s, style: { '--led-i': i } }))),
      h('span', { className: 'rk-checks-n' }, report ? `${passed}/6` : 'not rendered')),
    open && h('div', { className: 'rk-pop', role: 'tooltip' },
      CHECKS.map(([k, label], i) => {
        const c = report?.[k]
        return h('div', { key: k, className: 'rk-pop-row' },
          h('i', { className: 'rk-led', 'data-s': states[i] }),
          h('span', null, label),
          h('span', { className: 'rk-pop-val rk-mono' }, c ? String(c.value) : '—'),
          c?.target && h('span', { className: 'rk-pop-tgt' }, c.target),
          c && !c.pass && c.hint && h('span', { className: 'rk-pop-hint' }, c.hint))
      }),
      h('div', { className: 'rk-pop-foot' },
        h('span', null, report ? (stale ? `Rendered at rev ${renderRev}; edited since (rev ${rev})` : `Checked at rev ${rev}`) : 'Render to run the checks'),
        hash && h('span', { className: 'rk-mono' }, shortHash(hash))))
  )
}

function MixReport({ mix, render }) {
  const [open, setOpen] = useState(false)
  if (!mix) return null
  const bands = mix.bands_pct || {}
  const centroid = Number(mix.centroid_hz) || 0
  const centroidLabel = centroid >= 1000 ? `${(centroid / 1000).toFixed(1)} kHz` : `${Math.round(centroid)} Hz`
  const { notes, pairs } = mixHighlights(render)
  return h('div', { className: 'rk-mix', 'data-open': open },
    h('button', { className: 'rk-mix-btn', 'aria-expanded': open, onClick: () => setOpen(value => !value), title: notes.length ? `Mix · ${notes.length} note${notes.length === 1 ? '' : 's'}` : undefined }, `Mix · centroid ${centroidLabel} · sub ${Math.round(bands.sub || 0)}%`),
    open && h('div', { className: 'rk-mix-pop' },
      h('div', { className: 'rk-mix-bands', title: `Sub ${bands.sub || 0}% · low ${bands.low || 0}% · mid ${bands.mid || 0}% · high ${bands.high || 0}% · air ${bands.air || 0}%` },
        ['sub', 'low', 'mid', 'high', 'air'].map((band, i) => h('i', { key: band, style: { width: `${Math.max(0, Number(bands[band]) || 0)}%`, '--i': i } }))),
      h('div', { className: 'rk-mix-band-labels' }, ['sub', 'low', 'mid', 'high', 'air'].map(band => h('span', { key: band }, `${band} ${Math.round(bands[band] || 0)}`))),
      h('div', { className: 'rk-mix-stats' },
        ...[['Correlation', mix.correlation], ['Width', mix.width], ['Centroid', centroidLabel], ['Crest', mix.crest_db == null ? null : `${mix.crest_db} dB`]].map(([label, value]) => h('div', { key: label }, h('span', null, label), h('b', null, value ?? '—')))),
      (notes.length > 0 || pairs.length > 0) && h('div', { className: 'rk-mix-notes', 'aria-label': 'Mix notes' },
        notes.map((note, i) => h('p', { key: 'n' + i }, note)),
        pairs.map(pair => h('div', { key: pair.key, className: 'rk-mix-fit' }, h('span', null, pair.label), h('b', null, pair.detail)))))
  )
}

function Transport({ ctx, view, projects, playing, canPlay, rendering, match, pending, saveFailed, onRetry, onNew, renaming, renameError, onRenameStart, onRenameCommit, onRenameCancel, onPick, onRename, onDuplicate, onClear, onDelete, onUndo, onMeta, onRender, onPlay, renderMode, onRenderMode, renderError }) {
  const p = view.project, r = view.render
  const stale = !!r && r.rev !== view.rev
  return h('div', { className: 'rk-tp' },
    h('div', { className: 'rk-tp-group' },
      h('button', { className: 'rk-play', 'data-on': playing, disabled: !canPlay, 'aria-label': playing ? 'Stop' : 'Play', onClick: onPlay }, playing ? h(Icon.stop) : h(Icon.play)),
      h('div', { className: 'rk-field' },
        h('span', { className: 'rk-label' }, 'Project'),
        h('div', { style: { display: 'flex', alignItems: 'center', gap: 3 } },
          h(ProjectMenu, { ctx, current: p.name, projects, renaming, renameError, onRenameStart, onRenameCommit, onRenameCancel, onPick, onNew, onRename, onDuplicate, onClear, onDelete }),
          !renaming && h('button', { type: 'button', className: 'size-(--composer-control-size) grid place-items-center rounded-md text-(--ui-text-tertiary) hover:bg-(--chrome-action-hover)', title: 'New beat', 'aria-label': 'New beat', onClick: onNew }, projectIcon('add')))),
      h('span', { title: 'Rookery saves every change.', className: 'rk-save text-xs', style: { color: saveFailed ? 'var(--ui-red)' : 'var(--ui-text-quaternary)', whiteSpace: 'nowrap' } },
        saveFailed ? h('button', { type: 'button', style: { color: 'var(--ui-red)' }, onClick: onRetry }, 'Not saved · Retry')
       : pending ? 'Saving…' : h(Fragment, null, projectIcon('check'), ' Saved')),
      h('button', { type: 'button', className: 'rk-undo size-(--composer-control-size) grid place-items-center rounded-md text-(--ui-text-tertiary) hover:bg-(--chrome-action-hover)', title: 'Undo (Ctrl+Z)', 'aria-label': 'Undo (Ctrl+Z)', disabled: view.rev === 1, onClick: e => { const icon=e.currentTarget.firstChild; if(icon){icon.style.animation='none'; void icon.offsetWidth; icon.style.animation=''} onUndo() } }, projectIcon('discard'))),
    h('span', { className: 'rk-sep' }),
    h('div', { className: 'rk-tp-group' },
      h('div', { className: 'rk-field' }, h('span', { className: 'rk-label' }, 'Tempo'),
        h(ScrubNumber, { value: p.bpm, min: 50, max: 200, label: 'Tempo, BPM', format: v => h(Fragment, null, v, h('span', { className: 'rk-qq', style: { fontSize: 11, fontWeight: 400, marginLeft: 3 } }, 'BPM')), onCommit: v => onMeta({ bpm: v }) })),
      h('div', { className: 'rk-field' }, h('span', { className: 'rk-label' }, 'Bars'),
        h('div', { className: 'rk-seg', role: 'group', 'aria-label': 'Bars' }, [4, 8].map(b => h('button', { key: b, 'aria-pressed': p.bars === b, onClick: () => p.bars !== b && onMeta({ bars: b }) }, b)))),
      h('div', { className: 'rk-knob-row' },
        h(Knob, { label: 'Swing', caption: false, value: p.swing || 0, min: 0, max: 1, def: 0, display: v => `${swingPct(v)}%`, onCommit: v => onMeta({ swing: Math.round(v * 100) / 100 }) }),
        h('div', { className: 'rk-field' }, h('span', { className: 'rk-label' }, 'Swing'), h('span', { style: { fontSize: 15, fontWeight: 550, lineHeight: 1.2 } }, `${swingPct(p.swing)}%`)))),
    h('span', { className: 'rk-spacer' }),
    h('div', { className: 'rk-live', 'data-on': !!view.agent_editing, 'aria-live': 'polite' }, h('i'), view.agent_editing ? 'Hermes is editing' : 'Idle'),
    h('div', { className: 'rk-seg', role: 'group', 'aria-label': 'Render mode' }, ['loop', 'song'].map(mode => h('button', { key: mode, 'aria-pressed': renderMode === mode, onClick: () => onRenderMode(mode) }, mode === 'loop' ? 'Loop' : 'Song'))),
    h('button', { className: 'rk-render', 'data-busy': rendering, 'data-failed': !!renderError, disabled: rendering || (!renderError && !!r && !stale && (!!r.song === (renderMode === 'song'))), onClick: onRender, title: renderError ? `Last render failed: ${renderError}. Click to try again.` : undefined },
      rendering ? h('i') : null, rendering ? 'Rendering' : renderError ? 'Retry render' : r && !stale ? 'Rendered' : 'Render'),
    h(Checks, { report: r?.report, stale, hash: r?.hash, rev: view.rev, renderRev: r?.rev }),
    h(MixReport, { mix: r?.mix, render: r }),
    match ? h('span', { className: 'rk-match', key: match.hash, title: match.hash }, h(Icon.check), `Byte-identical to ${match.other}`)
      : h('button', { key: r?.rev, className: 'rk-hash rk-mono', title: r?.hash ? 'Render hash (project + renderer version). Click to copy.' : 'Not rendered yet', disabled: !r, onClick: () => r && navigator.clipboard?.writeText(r.hash).then(() => host.notify({ kind: 'info', message: 'Render hash copied' })) }, '#' + shortHash(r?.hash)),
    r?.wav_hash && h('button', { className: 'rk-hash rk-mono', title: `Audio hash (SHA-256 of the WAV bytes): ${r.wav_hash}\nClick to copy.`, onClick: () => navigator.clipboard?.writeText(r.wav_hash).then(() => host.notify({ kind: 'info', message: 'Audio hash copied' })) }, 'audio #' + shortHash(r.wav_hash))
  )
}

function Arrangement({ project, playing, render, getPosition, onSections }) {
  const sections = project.arrangement?.sections || []
  const [selected, setSelected] = useState(sections[0]?.id || null)
  const [renaming, setRenaming] = useState(false)
  const line = useRef(null), ph = useRef(null)
  useEffect(() => { if (!sections.some(section => section.id === selected)) setSelected(sections[0]?.id || null) }, [project.arrangement, selected])
  useEffect(() => {
    if (!playing || !render?.song || !line.current) return
    let raf = 0
    const tick = () => {
      const elapsed = getPosition(), duration = render.duration_samples / render.sample_rate
      if (ph.current) ph.current.style.transform = `translateX(${Math.min(1, elapsed / duration) * line.current.clientWidth}px)`
      const section = render.sections?.find(item => elapsed >= item.start_s && elapsed < item.end_s)
      line.current.querySelectorAll('[data-current]').forEach(el => el.dataset.current = String(el.dataset.section === section?.id))
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [playing, render?.hash])
  const update = next => onSections(next)
  const add = () => {
    const id = uniqueId(sections.length ? `section${sections.length + 1}` : 'main')
    const next = [...sections, { id, repeat: 1, mute: [] }]
    update(next); setSelected(id)
  }
  const selectedSection = sections.find(section => section.id === selected)
  const toggleMute = target => update(sections.map(section => section.id !== selected ? section : { ...section, mute: section.mute.includes(target) ? section.mute.filter(item => item !== target) : [...section.mute, target] }))
  if (!sections.length) return h('div', { className: 'rk-arr' }, h('button', { className: 'rk-arr-empty', onClick: () => { update([{ id: 'main', repeat: 1, mute: [] }]); setSelected('main') } }, 'Arrangement · Make a song from this loop'))
  const commitRename = raw => { const id = String(raw || '').trim(); setRenaming(false); if (id && id !== selected && /^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$/.test(id) && !sections.some(section => section.id === id)) { update(sections.map(section => section.id === selected ? { ...section, id } : section)); setSelected(id) } }
  const uniqueId = base => { let id = base.slice(0, 64), n = 2; while (sections.some(section => section.id === id)) id = `${base.slice(0, 60)}-${n++}`; return id }
  const move = delta => { const from = sections.findIndex(section => section.id === selected), to = from + delta; if (to < 0 || to >= sections.length) return; const next = [...sections]; [next[from], next[to]] = [next[to], next[from]]; update(next) }
  return h('div', { className: 'rk-arr' },
    h('div', { className: 'rk-arr-line', ref: line, 'data-playing': playing && !!render?.song },
      sections.map(section => h('button', { key: section.id, className: 'rk-arr-block', style: { '--repeat': section.repeat }, 'aria-pressed': selected === section.id, 'data-section': section.id, 'data-current': false, onClick: () => setSelected(section.id) }, section.id, h('small', null, `×${section.repeat}`))),
      h('i', { className: 'rk-arr-ph', ref: ph })),
    h('div', { className: 'rk-arr-controls' }, h('span', { className: 'rk-label' }, 'Arrangement'), h('button', { onClick: add }, '+ Section'), selectedSection && h(Fragment, null,
      renaming ? h('input', { className: 'rk-arr-name', autoFocus: true, defaultValue: selectedSection.id, 'aria-label': 'Section name', onKeyDown: e => { if (e.key === 'Enter') { e.preventDefault(); commitRename(e.currentTarget.value) } if (e.key === 'Escape') setRenaming(false) }, onBlur: e => commitRename(e.currentTarget.value) })
        : h('span', null, selectedSection.id), h(ScrubNumber, { className: 'rk-num', value: selectedSection.repeat, min: 1, max: 8, label: 'Section repeat', format: v => `×${v}`, onCommit: repeat => update(sections.map(section => section.id === selected ? { ...section, repeat } : section)) }),
      h('button', { onClick: () => { const id = uniqueId(`${selected}-copy`); const next = [...sections]; next.splice(next.findIndex(section => section.id === selected) + 1, 0, { ...selectedSection, id, mute: [...selectedSection.mute] }); update(next); setSelected(id) } }, 'Duplicate'),
      h('button', { onClick: () => setRenaming(true) }, 'Rename'), h('button', { onClick: () => move(-1), disabled: sections[0]?.id === selected }, '←'), h('button', { onClick: () => move(1), disabled: sections.at(-1)?.id === selected }, '→'),
      h('button', { onClick: () => { const next = sections.filter(section => section.id !== selected); update(next.length ? next : null); setSelected(next[0]?.id || null) } }, 'Delete'))),
    selectedSection && h('div', { className: 'rk-arr-mutes' },
      h('span', { className: 'rk-arr-hint' }, `In ${selectedSection.id}:`),
      [...project.tracks.map(track => [track.id, track.id]), ...(project.flock?.perches || []).flatMap((perch, slot) => perch ? [[`bird:${slot}`, FLOCK_BIRD_NAMES.get(perch.bird) || perch.bird]] : [])].map(([target, label]) => {
        const muted = selectedSection.mute.includes(target)
        return h('button', { key: target, className: 'rk-arr-toggle', 'data-muted': muted, 'aria-pressed': !muted, title: `${label} ${muted ? 'is muted' : 'plays'} in ${selectedSection.id}; click to ${muted ? 'unmute' : 'mute'}`, onClick: () => toggleMute(target) }, h('i'), label)
      })))
}

// ── waveform ──────────────────────────────────────────────────────────────
function Waveform({ buffer, bars, stale, playing, rendered, phRef, litRef }) {
  const box = useRef(null), base = useRef(null), lit = useRef(null)
  useEffect(() => {
    const el = box.current
    const draw = () => {
      const w = el.clientWidth, hgt = el.clientHeight, dpr = window.devicePixelRatio || 1
      for (const [cv, color] of [[base.current, 'color-mix(in srgb, var(--ui-text-primary) 42%, transparent)'], [lit.current, 'var(--ui-accent)']]) {
        cv.width = Math.round(w * dpr); cv.height = Math.round(hgt * dpr)
        const g = cv.getContext('2d')
        g.setTransform(dpr, 0, 0, dpr, 0, 0); g.clearRect(0, 0, w, hgt)
        g.fillStyle = resolveColor(el, color)
        const mid = hgt / 2
        if (!buffer) { g.fillRect(0, mid - 0.5, w, 1); continue }
        const L = buffer.getChannelData(0), R = buffer.numberOfChannels > 1 ? buffer.getChannelData(1) : L
        const per = L.length / w
        for (let x = 0; x < w; x++) {
          let lo = 0, hi = 0
          const a = Math.floor(x * per), b = Math.min(L.length, Math.floor((x + 1) * per))
          for (let i = a; i < b; i += 2) { const v = (L[i] + R[i]) * 0.5; if (v < lo) lo = v; if (v > hi) hi = v }
          const top = mid - hi * mid * 0.92, bot = mid - lo * mid * 0.92
          g.fillRect(x, top, 1, Math.max(1, bot - top))
        }
      }
    }
    draw()
    const ro = new ResizeObserver(draw)
    ro.observe(el)
    return () => ro.disconnect()
  }, [buffer])
  return h('div', { className: 'rk-wave', ref: box, 'data-stale': stale, 'data-playing': playing },
    h('canvas', { ref: base, 'aria-hidden': true }),
    h('div', { className: 'rk-wave-lit', ref: litRef }, h('canvas', { ref: lit, 'aria-hidden': true })),
    h('div', { className: 'rk-wave-bars' }, Array.from({ length: bars }, (_, i) => h('span', { key: i }, i + 1))),
    h('div', { className: 'rk-wave-ph', ref: phRef }),
    (!rendered || stale) && h('div', { className: 'rk-wave-note' }, !rendered ? 'Not rendered yet' : 'Edited since last render')
  )
}

// ── channel rack ──────────────────────────────────────────────────────────
const Pad = memo(function Pad({ i, on, beat, vel, digit, lit, delay, track, onToggle }) {
  return h('button', {
    className: 'rk-pad', 'data-i': i, 'data-on': on, 'data-beat': beat, 'data-lit': lit || undefined,
    'aria-pressed': on, 'aria-label': `${track} step ${i + 1}`,
    style: { '--v': vel, '--i': i % 16, animationDelay: lit ? `${delay}ms` : undefined },
    onClick: () => onToggle(track, i)
  }, h('i', { style: lit === 'on' ? { animationDelay: `${delay}ms` } : undefined }), digit ? h('em', null, digit) : null)
})

const TrackRow = memo(function TrackRow({ track, lit, meter, onToggle, onTrack, credits = {}, ctx }) {
  const n = track.steps.length, bars = Math.max(1, Math.ceil(n / 16))
  const out = []
  for (let b = 0; b < bars; b++) {
    const pads = []
    for (let s = 0; s < 16; s++) {
      const i = b * 16 + s, c = track.steps[i], on = isHit(c)
      const k = lit?.order.get(i)
      const litKind = k == null ? null : on ? 'on' : lit.off.has(i) ? 'off' : null
      pads.push(h(Pad, {
        key: litKind ? `${i}:${lit.nonce}` : i, i, on, beat: s % 4 === 0, vel: on ? velocityAt(track, i) : 0,
        digit: on && /\d/.test(c) ? c : null, lit: litKind, delay: (k ?? 0) * STAGGER_MS, track: track.id, onToggle
      }))
    }
    out.push(h('div', { key: b, className: 'rk-bar' }, pads))
  }
  const source = String(track.source || '')
  const src = source.replace(/^factory:/, '').replace(/^user:/, '↗ ')
  const credit = credits[source.replace(/^user:/, '')]
  const soundza = credit?.source === 'soundza' ? credit : null
  const creditLabel = soundza && [soundza.title, soundza.creator && `by ${soundza.creator}`].filter(Boolean).join(' · ')
  const openExternal = url => ctx?.os?.openExternal ? ctx.os.openExternal(url) : window.open(url, '_blank', 'noopener')
  const rms = meter ? clamp((meter.rms_db + 60) / 60, 0, 1) : 0, pk = meter ? clamp((meter.peak_db + 60) / 60, 0, 1) : 0
  return h('div', { className: 'rk-row', 'data-muted': !!track.mute, 'data-flash': !!lit },
    lit && h('i', { key: lit.nonce, className: 'rk-flash', 'aria-hidden': true }),
    h('div', { className: 'rk-th' },
      h('div', { className: 'rk-ms' },
        h('button', { 'data-k': 'm', 'aria-pressed': !!track.mute, 'aria-label': `Mute ${track.id}`, onClick: () => onTrack(track.id, { mute: !track.mute }) }, 'M'),
        h('button', { 'data-k': 's', 'aria-pressed': !!track.solo, 'aria-label': `Solo ${track.id}`, onClick: () => onTrack(track.id, { solo: !track.solo }) }, 'S')),
      h('div', { className: 'rk-tn' }, h('b', null, track.id), h('span', null, creditLabel || src,
        track.role && h('em', { className: 'rk-role', title: `Sample role: ${track.role}` }, track.role)),
        soundza && h('button', {
          type: 'button', className: 'rk-label rk-credit-link', title: 'Open soundza.com',
          'aria-label': 'Powered by soundza, open soundza.com',
          onClick: e => { e.stopPropagation(); openExternal(SOUNDZA_URL) }
        }, 'Powered by soundza')),
      h(ScrubNumber, { className: 'rk-gain', value: track.gain_db || 0, min: -24, max: 6, step: 0.5, label: `${track.id} gain`, format: fmtDb, onCommit: v => onTrack(track.id, { gain_db: v }) })),
    h('div', { className: 'rk-grid', style: { gridTemplateColumns: `repeat(${bars}, 1fr)` } }, out),
    h('div', { className: 'rk-meter', title: meter ? `RMS ${fmtDb(meter.rms_db)} · peak ${fmtDb(meter.peak_db)}` : 'No render yet' },
      h('i', { style: { height: `${rms * 100}%` } }), meter && h('b', { style: { bottom: `${pk * 100}%` } }))
  )
})

// ── master chain ──────────────────────────────────────────────────────────
function Master({ ctx, project, status, onFxParam }) {
  const chain = project.master?.fx || []
  const corvus = status?.corvus
  const hasVst = chain.some(f => f.type === 'vst3')
  const items = []
  chain.forEach((fx, idx) => {
    if (idx) items.push(h('span', { key: 'a' + idx, className: 'rk-arrow', 'aria-hidden': true }, '→'))
    const isVst = fx.type === 'vst3'
    const all = isVst ? (corvus?.params || []).map(pp => ({ ...pp, value: fx.params?.[pp.name] ?? pp.value ?? pp.default })) : []
    const params = curateParams(all, fx.params)
    const hidden = all.length - params.length
    items.push(h('div', { key: idx, className: 'rk-fx', 'data-vst': isVst },
      h('div', { className: 'rk-fx-h' }, fxName(fx), fxDetail(fx) && h('span', null, fxDetail(fx))),
      params.length > 0 && h('div', { className: 'rk-knobs' }, params.map(pp => h(Knob, {
        key: pp.name, label: pp.name, value: pp.value, min: pp.min ?? 0, max: pp.max ?? 1, def: pp.default ?? 0,
        display: () => paramLabel(pp.name), onCommit: v => onFxParam(idx, pp.name, Math.round(v * 1000) / 1000)
      }))),
      hidden > 0 && h('span', { className: 'rk-qq', style: { fontSize: 10.5 } }, `${hidden} more parameters. Ask Hermes to set any of them by name.`)))
  })
  if (!hasVst && corvus && !corvus.found) {
    items.push(h('button', { key: 'get', className: 'rk-get', onClick: () => ctx.os?.openExternal ? ctx.os.openExternal(CORVUS_URL) : window.open(CORVUS_URL, '_blank', 'noopener') },
      h('b', null, 'Get Corvus FX'), h('span', null, /Win/i.test(navigator.platform || navigator.userAgent) ? 'Free, MIT · Windows VST3' : 'Free, MIT · Windows only for now')))
  }
  return h('div', { className: 'rk-master' },
    h('div', { className: 'rk-th' }, h('div', { className: 'rk-tn' }, h('b', null, 'Master'), h('span', null, chain.length ? `${chain.length} in chain` : 'No effects'))),
    h('div', { className: 'rk-chain' }, items.length ? items : h('span', { className: 'rk-qq', style: { fontSize: 12, alignSelf: 'center' } }, 'Ask Hermes for a master chain, or say "put Corvus on the master".'))
  )
}

// ── the flock ──
// Template edits use catalog data for both the optimistic view and display names.
const FLOCK_BIRD_NAMES = new Map()
const FLOCK_KEY_SHARPS = { DB: 'C#', 'C#': 'C#', EB: 'D#', 'D#': 'D#', GB: 'F#', 'F#': 'F#', AB: 'G#', 'G#': 'G#', BB: 'A#', 'A#': 'A#' }
const normalizeFlockKey = key => {
  const value = typeof key === 'string' ? key.trim() : key
  return FLOCK_KEY_SHARPS[value?.toUpperCase()] || value
}
const flockValueEqual = (a, b) => JSON.stringify(a) === JSON.stringify(b)

function flockEditBody(current, next, meta) {
  const action = meta?.action
  if (!action || action === 'wireTap') return null
  if (action === 'template') return typeof meta.template === 'string' ? { action, template: meta.template } : null
  if (action === 'perch') {
    const bird = meta.bird || next?.perches?.find(p => p && p.bird)?.bird
    if (!bird) return null
    const body = { action, bird }
    if (Number.isInteger(meta.slot)) body.slot = meta.slot
    const perch = next?.perches?.find(p => p?.bird === bird)
    if (perch?.song && perch.song !== 'A') body.song = perch.song
    return body
  }
  if (action === 'unperch') {
    if (typeof meta.bird === 'string' && meta.bird) return { action, bird: meta.bird }
    if (Number.isInteger(meta.slot)) return { action, slot: meta.slot }
    return null
  }
  if (action === 'song') {
    const bird = meta.bird || next?.perches?.find(p => p && p.bird)?.bird
    const perch = next?.perches?.find(p => p?.bird === bird)
    if (!bird || !perch || current?.perches?.find(p => p?.bird === bird)?.song === perch.song) return null
    return { action, bird, song: perch.song }
  }
  if (action === 'mute' || action === 'solo') {
    const bird = meta.bird || next?.perches?.find(p => p && p.bird)?.bird
    const before = current?.perches?.find(p => p?.bird === bird)
    const after = next?.perches?.find(p => p?.bird === bird)
    if (!bird || !before || !after || before[action] === after[action]) return null
    return { action, bird, on: !!after[action] }
  }
  if (action === 'mix') {
    const bird = meta.bird
    const before = current?.perches?.find(p => p?.bird === bird)
    const after = next?.perches?.find(p => p?.bird === bird)
    if (!bird || !before || !after) return null
    const body = { action, bird }
    for (const field of (meta.fields || ['gain_db', 'pan'])) if (!flockValueEqual(before[field] ?? 0, after[field] ?? 0)) body[field] = after[field] ?? 0
    return Object.keys(body).length > 2 ? body : null
  }
  if (action === 'harmony') {
    const body = { action }
    for (const field of ['key', 'scale', 'progression']) {
      if (!flockValueEqual(current?.[field], next?.[field])) body[field] = field === 'key' ? normalizeFlockKey(next[field]) : next[field]
    }
    return Object.keys(body).length > 1 ? body : null
  }
  if (action === 'weather') {
    return current?.weather !== next?.weather ? { action, weather: next.weather } : null
  }
  return null
}

function flockFromTemplate(template, catalog, prior) {
  const previous = prior || { key: 'D', scale: 'dorian', progression: ['i', 'iv', 'VII', 'III'], weather: 'clear', perches: Array(6).fill(null), seen: [], unlocked: [] }
  const roleOrder = ['bass', 'keys', 'pad', 'lead', 'arp', 'call']
  const birdById = Object.fromEntries([...(catalog?.birds || []), catalog?.corvus].filter(Boolean).map(b => [b.id, b]))
  const landing = [...template.birds].sort((a, b) => roleOrder.indexOf(birdById[a.bird]?.role) - roleOrder.indexOf(birdById[b.bird]?.role) || a.bird.localeCompare(b.bird))
  const perches = Array(6).fill(null)
  landing.forEach((item, i) => { perches[i] = { bird: item.bird, song: item.song || 'A', mute: false, solo: false } })
  if (previous.perches?.length === 7) perches.push(previous.perches[6] || null)
  const seen = new Set(previous.seen || [])
  landing.forEach(item => seen.add(item.bird))
  return { key: normalizeFlockKey(template.key), scale: template.scale, progression: [...template.progression], weather: template.weather,
    perches, seen: [...seen], unlocked: [...(previous.unlocked || [])] }
}

function optimisticFlockProject(project, next, meta, catalog) {
  if (meta?.action === 'template') {
    const template = catalog?.templates?.find(t => t.id === meta.template || t.name === meta.template)
    return template ? { ...project, flock: flockFromTemplate(template, catalog, project.flock) } : project
  }
  if (!next || typeof next !== 'object') return project
  const fields = ['key', 'scale', 'progression', 'weather', 'perches', 'seen', 'unlocked']
  const flock = Object.fromEntries(fields.filter(k => Object.hasOwn(next, k)).map(k => [k, Array.isArray(next[k]) ? next[k].map(x => x && typeof x === 'object' ? { ...x } : x) : next[k]]))
  if (Object.hasOwn(flock, 'key')) return { ...project, flock }
  return project
}

const FLOCK_SECTION_CSS = `
.rk-flock{display:flex;flex-direction:column;gap:10px;color:var(--ui-text-primary)}
.rk-flock-head{display:flex;align-items:center;gap:8px;align-self:flex-start;border:0;background:none;color:var(--ui-text-secondary);font:inherit;font-size:13px;font-weight:650;cursor:pointer}
.rk-flock-head:hover{color:var(--ui-text-primary)}
.rk-flock-head .codicon{font-size:11px;color:var(--ui-text-quaternary);transition:transform .15s}
.rk-flock-invite{display:flex;align-items:center;gap:10px;flex-wrap:wrap;padding:10px 12px;border:1px solid var(--ui-stroke-tertiary);border-radius:9px;background:color-mix(in srgb,var(--ui-bg-editor) 48%,transparent)}
.rk-flock-invite-label{font-size:12px;color:var(--ui-text-secondary);font-weight:600}
.rk-flock-chips{display:flex;gap:6px;flex-wrap:wrap}
.rk-flock-chip{border:1px solid var(--ui-stroke-tertiary)!important;border-radius:999px!important;padding:5px 10px!important;background:var(--ui-bg-quaternary)!important;color:var(--ui-text-secondary)!important;font:inherit;font-size:11px!important;cursor:pointer}
.rk-flock-chip:hover{background:var(--ui-control-hover-background)!important;color:var(--ui-text-primary)!important}
.rk-flock-chip[data-suggested="true"]{border-color:color-mix(in srgb,var(--ui-accent) 62%,var(--ui-stroke-tertiary))!important;color:var(--ui-text-primary)!important;background:color-mix(in srgb,var(--ui-accent) 12%,var(--ui-bg-quaternary))!important}
.rk-flock-error{font-size:12px;color:var(--ui-text-tertiary)}
`

function FlockSection({ catalog, flock, collapsed, onCollapsed, onTemplate, onChange, render, playing, getPosition, bpm }) {
  const suggested = bpm >= 85 && bpm <= 95 ? 'dusty_boom_bap'
    : bpm >= 130 ? 'trap_night'
      : bpm <= 80 ? 'lo_fi_study'
        : bpm >= 118 && bpm <= 128 ? 'late_house' : 'sunday_soul'
  const caret = sdk.DisclosureCaret
    ? h(sdk.DisclosureCaret, { open: !collapsed })
    : sdk.Codicon ? h(sdk.Codicon, { name: collapsed ? 'chevron-right' : 'chevron-down' })
      : h('span', { className: `codicon codicon-chevron-${collapsed ? 'right' : 'down'}`, 'aria-hidden': true })
  const templates = catalog?.templates || []
  return h('section', { className: 'rk-flock', 'aria-label': 'The Flock' },
    h('style', null, FLOCK_SECTION_CSS),
    h('button', { type: 'button', className: 'rk-flock-head', 'aria-expanded': !collapsed, onClick: () => onCollapsed(!collapsed) }, caret, h('span', null, 'The Flock')),
    !collapsed && (catalog?.error
      ? h('div', { className: 'rk-flock-error', role: 'status' }, 'The flock catalog is unavailable.')
      : flock
        ? h(FlockPanel, { catalog, flock, render, playing, getPosition, onChange, bpm })
        : h('div', { className: 'rk-flock-invite' },
          h('span', { className: 'rk-flock-invite-label' }, 'Add the flock'),
          h('div', { className: 'rk-flock-chips', role: 'group', 'aria-label': 'Flock templates' }, templates.map(template =>
            h('button', { key: template.id, type: 'button', className: 'rk-flock-chip', 'data-suggested': template.id === suggested,
              'aria-pressed': template.id === suggested, onClick: () => onTemplate(template.id) }, template.name))))))
}

// The Flock: pixel crows, v3. Original 48×44 sprites drawn natively in code (style reference:
// chunky indigo-black pixel crows; no third-party pixels are copied or shipped).
// Every color is a Hermes theme token, every motion moves in whole sprite pixels.
//
// House style of desktop/plugin.js (createElement as h, scoped CSS string), so it
// can be lifted into the plugin as-is.
//
//   <Bird id="quill" state="idle|singing|muted|dim" anim="land|leave|ruffle|null" bpm={90} size={96} />
//   --beak (0..1) on the bird's root opens the beak from real note events: ≥0.3 caws,
//   ≥0.7 is a big caw (the head tips back a pixel).

// ── the cast ─────────────────────────────────────────────────────────────
// eyes: plain · wide · sleepy · cool · kind · regal  (brows and lids drawn in pixels)
// fx: notes · zzz · sparkle (pixel particles with meaning)
const CAST = [
  { id: 'bramble', name: 'Bramble', species: 'rook', role: 'bass', costume: 'cap', accent: 'var(--ui-orange)', eyes: 'kind', fx: 'notes', persona: 'Steady, unbothered. Nods on every beat.', gesture: 'nod' },
  { id: 'cinder', name: 'Cinder', species: 'crow', role: 'bass', costume: 'chain', accent: 'var(--ui-yellow)', eyes: 'cool', fx: 'sparkle', persona: 'Swagger. Leans back between notes.', gesture: 'lean' },
  { id: 'quill', name: 'Quill', species: 'rook', role: 'keys', costume: 'beret', accent: 'var(--ui-cyan)', eyes: 'plain', fx: 'notes', persona: 'The jazz head. Wing-taps the chords.', gesture: 'tap' },
  { id: 'sable', name: 'Sable', species: 'raven', role: 'keys', costume: 'tophat', accent: 'var(--ui-purple)', eyes: 'regal', fx: 'notes', persona: 'Formal and theatrical. Tips the hat on bar one.', gesture: 'sway' },
  { id: 'jinx', name: 'Jinx', species: 'jackdaw', role: 'lead', costume: 'crest', accent: 'var(--ui-red)', eyes: 'wide', fx: 'notes', persona: 'Show-off. Hops on the accents.', gesture: 'hop' },
  { id: 'glint', name: 'Glint', species: 'magpie', role: 'lead', costume: 'monocle', accent: 'var(--ui-yellow)', eyes: 'plain', fx: 'sparkle', persona: "Can't resist anything shiny.", gesture: 'tilt' },
  { id: 'hush', name: 'Hush', species: 'raven', role: 'pad', costume: 'nightcap', accent: 'var(--ui-blue)', eyes: 'sleepy', fx: 'zzz', persona: 'Always half asleep. Breathes like a slow pad.', gesture: 'doze' },
  { id: 'moss', name: 'Moss', species: 'rook', role: 'pad', costume: 'knit', accent: 'var(--ui-green)', eyes: 'kind', fx: 'notes', persona: 'Cozy. Settles its feathers.', gesture: 'settle' },
  { id: 'tick', name: 'Tick', species: 'chough', role: 'arp', costume: 'goggles', accent: 'var(--ui-orange)', eyes: 'wide', fx: 'notes', persona: 'Nervous energy. Twitches every sixteenth.', gesture: 'twitch' },
  { id: 'pip', name: 'Pip', species: 'jackdaw', role: 'arp', costume: 'propeller', accent: 'var(--ui-cyan)', eyes: 'wide', fx: 'notes', persona: 'Playful. The propeller spins when it sings.', gesture: 'bounce' },
  { id: 'echo', name: 'Echo', species: 'crow', role: 'call', costume: 'silk', accent: 'var(--ui-purple)', eyes: 'plain', fx: 'notes', persona: 'The singer. Throws its head back on every phrase.', gesture: 'belt' },
  { id: 'wrennot', name: 'Wren-Not', species: 'rook', role: 'call', costume: 'flower', accent: 'var(--ui-red)', eyes: 'kind', fx: 'notes', persona: "Insists it isn't a wren.", gesture: 'answer' },
  { id: 'corvus', name: 'Corvus', species: 'crow', role: 'crown', costume: 'crown', accent: 'var(--ui-accent)', eyes: 'regal', fx: 'sparkle', persona: 'The king. Arrives when the whole flock has sung.', gesture: 'regal', secret: true }
]
const CAST_BY_ID = Object.fromEntries(CAST.map(b => [b.id, b]))

// ── base sprite: a perched crow facing right, drawn natively at 48 × 44 ─────────
// Hand-shaded final pixel codes, four tones per material:
//   body o outline · M shadow · d base · r light      wing p shadow · m base · h / H sheen (blue / purple)
//   bill o outline · M gape · Y base · y light         eye o pupil · e catch-light      legs Y base · l light
// Species, eyes, the caw and costumes are patches painted over it in compose().
const W = 48, H = 44
const MASK = [
  '................................................', // 0
  '................................................', // 1
  '................................................', // 2
  '................................................', // 3
  '................................................', // 4
  '................................................', // 5
  '................................................', // 6
  '................................................', // 7
  '................................................', // 8
  '.......................ooooooooooo..............', // 9
  '......................orrrrrrrrrrroooo..........', // 10
  '.....................orrrdddddddddddyyyooo......', // 11
  '.....................orddddddeoddddMYyyyyyoo....', // 12
  '.....................orddddddoodddMYYYYYYyyyo...', // 13
  '.....................ordddddddddddYYYYYYYYYYyo..', // 14
  '.....................ordddddddddddMYYYYYYYYYYYo.', // 15
  '.....................ordddddddddddMMMMMMMMMMYYo.', // 16
  '.....................orddddddddddMMYYYYYYYYooo..', // 17
  '....................orddddddddddMMMoooooooo.....', // 18
  '....................orddddddddMMMMdo............', // 19
  '...................ormmhhhmMdddddrddro..........', // 20
  '...................orhhhhhhHHMddddMdo...........', // 21
  '..................orhhhhhHHHHmMdrrddrro.........', // 22
  '..................orhhhHHHHHmmmMddMddo..........', // 23
  '.................ommHHHHHmmmmmmMdrddrrdo........', // 24
  '.................omHHHmmmmmmmpppMdMdddo.........', // 25
  '................ommmmmmmmmpppmmmMddrddo.........', // 26
  '................ommmmmmpppmmmhpmMrddddo.........', // 27
  '...............ommmmpppmmmmmhpmmMddddMo.........', // 28
  '...............ompppmmmmmmmmpmmodddddMo.........', // 29
  '..............ompmmmmmmmmmmpmmmodddMMo..........', // 30
  '..............ommmmmmmmmmmpmmmoddddMMo..........', // 31
  '.............opppmmmmmmmmpmmmodddMMMo...........', // 32
  '.............oppmppmmmmmpmmmoddMMMMo............', // 33
  '............oppmpppmpmmpmmoddMMMMMo.............', // 34
  '............opmpppmppppmoddMMMMMMo..............', // 35
  '...........opmpppmpppmoMMoMMMMoo................', // 36
  '..........opmpppmpmooMooYo.olYo.................', // 37
  '.........opmppmopopMo..oYo.olYo.................', // 38
  '........opmmopopMMo....oYo.olYo.................', // 39
  '.......omopopMMMo......oYo.olYo.................', // 40
  '......ommppMMo.......oYYYo.olllllo..............', // 41
  '.....ompMMo.........oYooYolYo.oYYo..............', // 42
  '....oooo.............o....o......o..............'  // 43
]
const HEAD = { y0: 8, y1: 19, x0: 20 }
const SHOULDER_Y = 20

// Species patches: [x, y, rows] painted over the base ('.' keeps a pixel, '_' erases it).
// iris: the eye color (jackdaw's pale eye) · legs: the leg color (chough's red legs).
const SPECIES = {
  crow: {},
  rook: { // bare pale face, slimmer bill, shaggy "trousers"
    paint: [
      [32, 11, ['..gw', 'gwwg', 'gwg.', 'gg..', 'ggg.', '.gg.', 'ggg.', 'gggg']],
      [32, 19, ['gg']],
      [43, 13, ['yo_', 'Yyo', 'YYo', 'Yo_', 'o__']],
      [22, 35, ['.oMddMdMMo', 'oMdMdMdMdMo', 'oMoMoMoMMo', '.o.o.o.oo']]
    ]
  },
  raven: { // bigger hooked bill, heavy shaggy hackles
    paint: [
      [34, 10, ['oooooo']],
      [36, 11, ['yyyyyoo']],
      [35, 12, ['MYyyyyyyoo']],
      [34, 13, ['MYYYYYYYyyyo']],
      [34, 14, ['YYYYYYYYYYYyo']],
      [34, 15, ['MYYYYYYYYYYYYo']],
      [34, 16, ['MMMMMMMMMMYYYo']],
      [33, 17, ['MMYYYYYYYYYoYo']],
      [35, 18, ['ooooooooo_o']],
      [33, 19, ['drdrdo']],
      [33, 20, ['dMddrro']],
      [33, 21, ['rdMdo_']],
      [32, 22, ['rdrddrro']],
      [33, 23, ['MdMdo_']],
      [33, 24, ['rdMdrro']],
      [34, 25, ['MdMdo']],
      [35, 26, ['rddo']]
    ]
  },
  jackdaw: { // grey nape, pale eye, short bill
    iris: 'w',
    paint: [
      [22, 12, ['gg']],
      [22, 13, ['gggg']],
      [22, 14, ['ggggg']],
      [21, 15, ['oggggggg']],
      [21, 16, ['ogggggg']],
      [21, 17, ['ogggggg']],
      [20, 18, ['oggggg']],
      [20, 19, ['ogggg']],
      [19, 20, ['og']],
      [34, 10, ['ooo____']],
      [36, 11, ['yyoo____']],
      [35, 12, ['MYyyoo____']],
      [34, 13, ['MYYYYyo_____']],
      [34, 14, ['YYYYYYyo____']],
      [34, 15, ['MYYYYYYo_____']],
      [34, 16, ['MMMMMMYo_____']],
      [33, 17, ['MMYYYYYo______']],
      [35, 18, ['oooooo____']]
    ]
  },
  magpie: { // white belly and scapular bar, long sheened tail
    paint: [
      [31, 26, ['owwwwww']],
      [29, 27, ['oowwwwwww']],
      [29, 28, ['owwwwwwwg']],
      [28, 29, ['owwwwwwwwg']],
      [28, 30, ['owwwwwwgg']],
      [27, 31, ['owwwwwwwgg']],
      [26, 32, ['owwwwwwggg']],
      [25, 33, ['owwwwwgggg']],
      [24, 34, ['owwwwgggg']],
      [24, 35, ['oggggggggo']],
      [20, 20, ['..ww']],
      [20, 21, ['.wwwww']],
      [19, 22, ['owwwww']],
      [18, 23, ['owwwww']],
      [17, 24, ['owww']],
      [0, 39, ['......oo', '....oohm', '..oohhm', 'oohhmm', 'ommmpp']],
      [0, 43, ['oooooo']]
    ]
  },
  chough: { // red, slender, down-curved bill; red legs
    legs: 'R',
    paint: [
      [34, 10, ['o___']],
      [34, 11, ['dooo_______']],
      [34, 12, ['MRRRoo______']],
      [34, 13, ['MeRRRRoo____']],
      [34, 14, ['MRRRRRRRo___']],
      [34, 15, ['MRRRRRRRRo__']],
      [34, 16, ['MMMMMMMRRRo_']],
      [33, 17, ['MMRRRRRRoRRo']],
      [35, 18, ['oooooo_oRo']],
      [43, 19, ['o']]
    ]
  }
}

// Eyes: E iris (species color) · e catch-light · any other code is drawn as is (lids, brows).
const EYES = {
  plain: [[29, 12, 'e'], [30, 12, 'E'], [29, 13, 'E'], [30, 13, 'E']],
  wide: [[29, 11, 'e'], [30, 11, 'E'], [29, 12, 'E'], [30, 12, 'E'], [29, 13, 'E'], [30, 13, 'E'], [28, 12, 'E'], [28, 11, 'o']],
  sleepy: [[28, 12, 'M'], [29, 12, 'M'], [30, 12, 'M'], [31, 12, 'M'], [29, 13, 'e'], [30, 13, 'E'], [31, 13, 'o']],
  cool: [[28, 11, 'o'], [29, 11, 'o'], [30, 11, 'o'], [31, 11, 'o'], [29, 12, 'M'], [30, 12, 'M'], [29, 13, 'e'], [30, 13, 'E']],
  kind: [[29, 12, 'e'], [30, 12, 'E'], [28, 13, 'o'], [29, 13, 'r'], [30, 13, 'r'], [31, 13, 'o']],
  regal: [[28, 11, 'o'], [29, 10, 'o'], [30, 10, 'o'], [29, 12, 'M'], [30, 12, 'E'], [29, 13, 'e'], [30, 13, 'E']]
}
const BLINK = [[29, 11, 'd'], [30, 11, 'd'], [28, 12, 'd'], [29, 12, 'M'], [30, 12, 'M'], [28, 13, 'o'], [29, 13, 'o'], [30, 13, 'o'], [31, 13, 'M']]

// Caw: below the gape the lower mandible drops (1px at the base, 2px further out), the bill
// tip lifts a pixel so the head reads tipped back, and the mouth shows dark with a tongue.
const CAW = { x0: 35, gape: 16, liftFrom: 40 }

// Wing raised (take-off and landing frame): repaints the folded wing as body and tail, and
// lifts the near wing with its primaries fanned. gridForFrame draws it one row up, hence y + 1.
const WING_UP = { x: 4, y: 1, rows: [
  '.........oo.................',
  '......oo.omo................',
  '...oo.omoompo...............',
  '.oomoompmpmpo...............',
  'ompmpmpmpppmo...............',
  'omppmppmpphho...............',
  '.ompmppmphhHo...............',
  'ompppmpmhhHHho..............',
  'omppppmmhHHhho..............',
  '.omppmmmhHhhhmo.............',
  '.omppmmmmHhhmmo.............',
  '..ompmmmmmhhmmmo............',
  '..omppmmmmmhmmmo............',
  '...ompmmmmmmmmmmo...........',
  '...oompmmmmpmmmmm...........',
  '....oompmmmmpmmmm...........',
  '.....oompmmmmpmmmmo.........',
  '......oomppmmmpmmmmo........',
  '........oomppmmmpmmmo.......',
  '..........ooppmmmpmmMo......',
  '............ooppp..mMod.....',
  '..............o.ppmMModdd...',
  '................oooodddddd..',
  '................ddddddddddd.',
  '..............rdddddddddddd.',
  '..............rddddddddddddd',
  '.............rdddddddddddddd',
  '.............rdddddddddddddd',
  '............rddddddddddddddd',
  '............rddddddddddddddd',
  '...........rdddddddddddddddd',
  '...........rMMMMMMMMMMMMMMM.',
  '..........rMMMMMMMMMMMMMMM..',
  '..........MMMMMMMMMMMMMMM...',
  '.........MMMMMMMMMMMMMM.....',
  '.........MM.MMMMMMMMM.......',
  '........MM.MMMM.MMM..M....M.',
  '.......MM.MMMMp.............',
  '......MM.MM.M.M.............',
  '.....MMp.M.M................',
  '....M...M...................',
  '...MM.M.....................'] }

// Costumes: x, y, rows (o outline · c accent · C accent detail · k light), optional alt frame (2-frame loop), on head or body.
const COSTUMES = {
  cap: { at: 'head', x: 21, y: 4, rows: [
    '....oooooooo',
    '...okkcccccoo',
    '..okcccccccCCo',
    '..occcccccccCCoooo',
    '.oCCCCCCCCCCCCcccco',
    '..oooooooooooooooo'] },
  beret: { at: 'head', x: 21, y: 3, rows: [
    '......oo',
    '.....oCo',
    '...oooooooooo',
    '.ookkccccccccoo',
    'okcccccccccccccco',
    'occccccccccccccco',
    '.oCCCCCCCCCCCCCo',
    '..ooooooooooooo',
    '......cccc',
    '.....c....c',
    'CCCCc.....kc',
    '....c......ccc',
    '.....c....c',
    '......cccc'] },
  tophat: { at: 'head', x: 21, y: 0, rows: [
    '...oooooooooo',
    '...okcccccccCo',
    '...okcccccccCo',
    '...okcccccccCo',
    '...okcccccccCo',
    '...oCCCCCCCCCo',
    '...okcccccccCo',
    'ooocccccccccccoooo',
    'okcccccccccccccccco',
    '.ooooooooooooooooo'] },
  crest: { at: 'head', x: 20, y: 1, rows: [
    'o.....o',
    'oco...oco...o',
    '.okco..okco.oco',
    '..okcco.okccokco',
    '...okccookcccco',
    '....okcccccccco',
    '.....occcccccCo',
    '......oCCCCCCo',
    '.......ooooooo'],
    alt: [
    '.o.....o',
    '.oco...oco...o',
    '..okco..okco.oco',
    '..okcco.okccokco',
    '...okccookcccco',
    '....okcccccccco',
    '.....occcccccCo',
    '......oCCCCCCo',
    '.......ooooooo'] },
  monocle: { at: 'head', x: 27, y: 10, rows: [
    '.cccc',
    'c...kc',
    'c....c',
    'c....c',
    'c....c',
    '.cccc',
    '..C',
    '...C',
    '...C',
    '....C',
    '....C',
    '.....k'] },
  nightcap: { at: 'head', x: 8, y: 2, rows: [
    '...............oooooo',
    '............oookkccccoo',
    '..........ookkcccccccccoo',
    '........ookccccccccccccccco',
    '......ookcccCccccccccccccco',
    '....oookccCo.oCCCCCCCCCCCCo',
    '..okkocccCo...ooooooooooooo',
    '.okkkkoCCo',
    '.okkkko.o',
    '..okko'],
    alt: [
    '...............oooooo',
    '............oookkccccoo',
    '..........ookkcccccccccoo',
    '........ookccccccccccccccco',
    '.......okccCcccccccccccccco',
    '.....ookcCCo.oCCCCCCCCCCCCo',
    '....okkoCCo...ooooooooooooo',
    '...okkkkoo',
    '...okkkko',
    '....okko'] },
  goggles: { at: 'head', x: 21, y: 5, rows: [
    '....oooo..oooo',
    '...okekcookekco',
    'oCCocckcoocckco',
    'oCCCoooo..oooo'] },
  propeller: { at: 'head', x: 21, y: 1, rows: [
    '..oooooo.oooooo',
    '..okkkkCoCcccco',
    '..oooooooooooo',
    '.......oCo',
    '....ooooCoooo',
    '..ookkcccccccoo',
    '.okccccccccccccoo',
    'oCCcCCcCCcCCcCCco',
    '.ooooooooooooooo'],
    alt: [
    '......oooooo',
    '......okCcco',
    '......oooooo',
    '.......oCo',
    '....ooooCoooo',
    '..ookkcccccccoo',
    '.okccccccccccccoo',
    'oCCcCCcCCcCCcCCco',
    '.ooooooooooooooo'] },
  crown: { at: 'head', x: 22, y: 3, rows: [
    '.o...o...o...o',
    'oko.oko.oko.oko',
    'okcoocccocccocCo',
    'okcccckccccccCCo',
    'occkccccccckccCo',
    'oCCCCCCCCCCCCCCo',
    '.oooooooooooooo'],
    alt: [
    '.o...o...o...o',
    'oko.oko.oko.oko',
    'okcoocccocccocCo',
    'okccccccccccccCo',
    'occCcccckccCccCo',
    'oCCCCCCCCCCCCCCo',
    '.oooooooooooooo'] },
  flower: { at: 'head', x: 19, y: 7, rows: [
    '..ooo',
    '.okcco',
    'okckkco',
    'occkcCo',
    '.occCo',
    '..oCoC',
    '.....C'] },
  chain: { at: 'body', x: 21, y: 18, rows: [
    'o..........o..',
    'Ck.......kCo',
    '.cC.....Cc',
    '..kCc.cCk',
    '....oko',
    '...okcco',
    '...occCo',
    '....oCo'],
    alt: [
    'o..........o..',
    'Cc.......cCo',
    '.kC.....Ck',
    '..cCk.kCc',
    '....oco',
    '...ocko',
    '...occCo',
    '....oCo'] },
  knit: { at: 'body', x: 19, y: 17, rows: [
    '.oooooooooooooooo',
    'okcCccCccCccCccCo',
    'occCccCccCccCccCco',
    '.oooooooooocCcCoo',
    '...........ocCco',
    '...........occCo',
    '...........ocCco',
    '...........occCo',
    '...........ocCco',
    '...........okkko',
    '...........k.k.k'] },
  silk: { at: 'body', x: 0, y: 14, rows: [
    '',
    '',
    '..........oooooo',
    '.o......ookkkkkkoo.ooooooooooooooooo',
    'ocooooookkcccccckkokkkkkkccccccccccc',
    'oCcccckkccCCCCCCcckccCCCCCCCCCCCCCkco',
    '.oCCCCccCCooooooCCcCCCooooooooooooccCo',
    '..ooooCCoo......ooCooo...........ocCo',
    '......oo..........o..............oCo',
    '.................................oco',
    '.................................oo',
    ''],
    alt: [
    '',
    '',
    '.......oooooo',
    '.....ookkkkkkoo....ooooooooooooooooo',
    '.oooockcccccckkooookkkkkkccccccccccc',
    'occccCcCCCCCCcckkkkccCCCCCCCCCCCCCkco',
    'oCCCCoCooooooCCccccCCCooooooooooooccCo',
    '.oooo.o......ooCCCCooo...........ocCo',
    '...............oooo..............oCo',
    '.................................oco',
    '.................................oo',
    ''] }
}

// Pixel particles (sprite pixels), placed near the beak / head.
const GLYPH = {
  note: ['..###', '..#.#', '..#..', '###..', '###..'],
  z: ['#####', '...#.', '..#..', '.#...', '#####'],
  spark: ['..#..', '..#..', '##.##', '..#..', '..#..']
}

// ── compose: base + species + caw + eyes → pixel grid ─────────────────────────
// Output codes: o outline · d body · r body light · M shadow · m wing · h / H sheen · p primaries
// y bill light · Y bill · e catch-light · w white · g grey · R red · l legs · c / C / k costume
function paint(g, x0, y0, rows) {
  rows.forEach((row, dy) => [...row].forEach((c, dx) => {
    const x = x0 + dx, y = y0 + dy
    if (c !== '.' && x >= 0 && x < W && y >= 0 && y < H) g[y][x] = c === '_' ? '.' : c
  }))
}

function openBill(g) {
  const { x0, gape, liftFrom } = CAW, src = g.map(r => r.slice())
  let lt = x0 - 1 // last column of the lower mandible
  while (lt + 1 < W && !'.o'.includes(src[gape + 1][lt + 1])) lt++
  for (let x = x0; x < W; x++) {
    const lower = x <= lt + 1, drop = lower ? (x < x0 + 2 ? 1 : 2) : 0, lift = x >= liftFrom ? 1 : 0
    const top = lower ? gape : gape + 4
    for (let y = 8; y <= (lower ? gape + 2 : top); y++) g[y][x] = '.'
    for (let y = 8; y <= top; y++) if (src[y][x] !== '.' && y - lift >= 0) g[y - lift][x] = src[y][x]
    if (!drop) continue
    for (const y of [gape + 1, gape + 2]) if (src[y][x] !== '.') g[y + drop][x] = src[y][x]
    if (x <= lt) for (let y = gape + 1 - lift; y < gape + 1 + drop; y++) g[y][x] = x < x0 + 3 && y === gape + drop ? 'R' : 'M'
  }
}

function compose(species, eyes, caw) {
  const g = MASK.map(r => r.padEnd(W, '.').slice(0, W).split(''))
  const sp = SPECIES[species] || SPECIES.crow
  ;(sp.paint || []).forEach(([x, y, rows]) => paint(g, x, y, rows))
  if (sp.legs) for (let y = 36; y < H; y++) for (let x = 18; x < 36; x++) if ('lY'.includes(g[y][x])) g[y][x] = sp.legs
  if (caw) openBill(g)
  ;(EYES[eyes] || EYES.plain).forEach(([x, y, c]) => { g[y][x] = c === 'E' ? sp.iris || 'o' : c === 'e' && sp.iris ? 'o' : c })
  return g
}

function rects(g, keep, key, cls) {
  const out = []
  for (let y = 0; y < g.length; y++) {
    let x = 0
    while (x < W) {
      const c = g[y][x]
      if (c === '.' || !keep(x, y)) { x++; continue }
      let x2 = x + 1
      while (x2 < W && g[y][x2] === c && keep(x2, y)) x2++
      out.push(h('rect', { key: `${key}${y}:${x}`, x, y, width: x2 - x, height: 1, className: cls || `p-${c}` }))
      x = x2
    }
  }
  return out
}

function stamp(rows, x0, y0, extra) {
  const g = Array.from({ length: H + 2 }, () => Array(W).fill('.'))
  rows.forEach((row, dy) => [...row].forEach((c, dx) => {
    const x = x0 + dx, y = y0 + dy + 1 // +1: costumes may sit one row above the canvas (tall hats)
    if (c !== '.' && x >= 0 && x < W && y >= 0 && y < H + 1) g[y][x] = c
  }))
  ;(extra || []).forEach(([x, y, c]) => { g[y + 1][x] = c })
  return g
}

function costume(kind, layer) {
  const cos = COSTUMES[kind]
  if (!cos || cos.at !== layer) return null
  const a = rects(stamp(cos.rows, cos.x, cos.y, cos.extra), () => true, 'ca')
  if (!cos.alt) return h('g', { className: 'c-costume', transform: 'translate(0 -1)' }, a)
  const b = rects(stamp(cos.alt, cos.x, cos.y, cos.extra), () => true, 'cb')
  return h('g', { className: 'c-costume', transform: 'translate(0 -1)' }, h('g', { className: 'c-a' }, a), h('g', { className: 'c-b' }, b))
}

function particles(kind) {
  if (!kind) return null
  const glyph = kind === 'zzz' ? GLYPH.z : kind === 'sparkle' ? GLYPH.spark : GLYPH.note
  const spots = kind === 'zzz' ? [[35, 3], [39, 0], [42, -1]] : kind === 'sparkle' ? [[38, 4], [15, 12], [41, 22]] : [[40, 3], [43, -1], [37, -1]]
  return h('g', { className: `fx fx-${kind}`, 'aria-hidden': true },
    spots.map(([x, y], i) => h('g', { key: i, className: `fx-p fx-p${i}` },
      rects(stamp(glyph, x, y), () => true, `fx${i}`))))
}

const inHead = (x, y) => y >= HEAD.y0 && y <= HEAD.y1 && x >= HEAD.x0

const BIRD_SPRITE_CACHE = new Map()
const SPRITE_W = 48, SPRITE_H = 44
const PX_CODES = ['o','d','r','M','m','p','h','H','y','Y','e','w','g','l','R','c','C','k','i','q']
const PX_FALLBACK = { o:'#11131c', d:'#25273c', r:'#777b9a', M:'#181a2b', m:'#343651', p:'#44465f', h:'#565a85', H:'#484a7b', y:'#c7b56c', Y:'#8f7746', e:'#11131c', w:'#f1efff', g:'#9ba4b8', l:'#c7b56c', R:'#c53953', c:'#bd78e8', C:'#9b67cb', k:'#7650a5', i:'#fff4d6', q:'#fff0bd' }
function gridForFrame(b, frame) {
  const g = compose(b.species, b.eyes, frame === 'sing')
  const overlay = (rows, x, y, extra) => {
    const layer = stamp(rows, x, y, extra)
    for (let py = 0; py < H; py++) for (let px = 0; px < W; px++) if (layer[py + 1]?.[px] && layer[py + 1][px] !== '.') g[py][px] = layer[py + 1][px]
  }
  const cos = COSTUMES[b.costume]
  if (cos) overlay(cos.rows, cos.x, cos.y, cos.extra)
  if (frame === 'wing') overlay(WING_UP.rows.map(r => r.replace(/s/g,'h').replace(/w/g,'m')), WING_UP.x, WING_UP.y - 1)
  if (frame === 'blink') BLINK.forEach(([x, y, c]) => { g[y][x] = c })
  // The art is authored at the rig size (48×44), so this expansion is the identity.
  return Array.from({length:SPRITE_H},(_,y)=>Array.from({length:SPRITE_W},(_,x)=>g[Math.floor(y*H/SPRITE_H)][Math.floor(x*W/SPRITE_W)]))
}
function spriteUrl(id, b, frame, palette) {
  const key = JSON.stringify([id,b.costume,b.species,b.eyes,frame,palette])
  if (BIRD_SPRITE_CACHE.has(key)) return BIRD_SPRITE_CACHE.get(key)
  const src=gridForFrame(b,frame), canvas=document.createElement('canvas'); canvas.width=SPRITE_W; canvas.height=SPRITE_H
  const ctx=canvas.getContext('2d'); ctx.imageSmoothingEnabled=false
  for(let y=0;y<SPRITE_H;y++) for(let x=0;x<SPRITE_W;x++) {
    const c=src[y][x]
    if(c!=='.') { ctx.fillStyle=palette[c]||PX_FALLBACK[c]||'#fff'; ctx.fillRect(x,y,1,1) }
  }
  const url=canvas.toDataURL(); BIRD_SPRITE_CACHE.set(key,url); return url
}
function BirdSVG({ id, title = true }) {
  const b = CAST_BY_ID[id]
  if (!b) return null
  const ref=useRef(null), [palette,setPalette]=useState(null)
  useEffect(()=>{
    const el=ref.current; if(!el) return
    const resolve=()=>{
      const next={}
      for(const code of PX_CODES) { const value=getComputedStyle(el).getPropertyValue('--px-'+code).trim(); next[code]=value ? resolveColor(el,value) : PX_FALLBACK[code] }
      setPalette(next)
    }
    resolve()
    const observer=new MutationObserver(resolve)
    observer.observe(document.documentElement,{attributes:true,attributeFilter:['class','style']})
    return ()=>observer.disconnect()
  },[id])
  const n=[...id].reduce((v,c)=>(v*31+c.charCodeAt(0))>>>0,7)
  const blank='data:image/gif;base64,R0lGODlhAQABAAD/ACwAAAAAAQABAAACADs='
  const urls=palette ? ['idle','blink','sing','wing'].map(frame=>spriteUrl(id,b,frame,palette)) : [blank,blank,blank,blank]
  return h('div',{className:'fkb-svg b-root',role:'img','aria-label':title ? b.name+', the '+b.species+', '+b.role : undefined,title:title?b.name+': '+b.persona:undefined},
    h('div',{ref,className:'fkb-frame-stack b-body b-head'},
      urls.map((src,i)=>h('img',{key:i,src,alt:'',draggable:false,className:['fkb-frame b-shut','fkb-frame b-lid','fkb-frame b-caw','fkb-frame b-wingup'][i]})),
      h('svg',{className:'fkb-particles',viewBox:`0 0 ${W} ${H-1}`,'aria-hidden':true},particles(b.fx))))
}

function Bird({ id, state = 'idle', anim = null, bpm = 90, size = 96, seed = 0, onClick, label }) {
  const b = CAST_BY_ID[id]
  if (!b) return null
  const n = [...id].reduce((s, c) => (s * 31 + c.charCodeAt(0)) >>> 0, 7 + seed)
  const style = {
    '--beat': `${(60 / bpm).toFixed(4)}s`,
    '--blink': `${(3.2 + (n % 40) / 10).toFixed(2)}s`,
    '--breath': `${(2.6 + (n % 13) / 10).toFixed(2)}s`,
    '--phase': `-${((n % 97) / 31).toFixed(2)}s`,
    '--accent': b.accent,
    width: size, height: size * SPRITE_H / SPRITE_W
  }
  return h('button', {
    type: 'button', className: 'fkb', 'data-bird': id, 'data-gesture': b.gesture, 'data-state': state, 'data-anim': anim || undefined,
    style, onClick, 'aria-label': label || `${b.name}, ${b.role}${state === 'muted' ? ', muted' : state === 'singing' ? ', singing' : ''}`
  }, h(BirdSVG, { id }))
}

// ── palette + motion ────────────────────────────────────────────────────────
// Light themes: ink-dark crows. Dark themes: indigo-black bodies tinted by the accent,
// a rim light along the back, and a purple-blue iridescent sheen on the wing.
const BIRD_CSS = `
.fkb{all:unset;cursor:pointer;display:block;position:relative;--beak:0;-webkit-tap-highlight-color:transparent;
  --px-o:color-mix(in srgb,var(--ui-text-primary) 97%,transparent);
  --px-d:color-mix(in srgb,var(--ui-accent) 18%,color-mix(in srgb,var(--ui-text-primary) 80%,var(--ui-bg-editor,transparent)));
  --px-r:color-mix(in srgb,var(--ui-accent) 24%,color-mix(in srgb,var(--ui-text-primary) 64%,var(--ui-bg-editor,transparent)));
  --px-M:color-mix(in srgb,var(--ui-text-primary) 90%,var(--ui-bg-editor,transparent));
  --px-m:color-mix(in srgb,var(--ui-accent) 22%,color-mix(in srgb,var(--ui-text-primary) 70%,var(--ui-bg-editor,transparent)));
  --px-p:color-mix(in srgb,var(--ui-text-primary) 86%,var(--ui-bg-editor,transparent));
  --px-h:color-mix(in srgb,var(--ui-accent) 40%,color-mix(in srgb,var(--ui-text-primary) 50%,var(--ui-bg-editor,transparent)));
  --px-H:color-mix(in srgb,var(--ui-purple) 40%,color-mix(in srgb,var(--ui-text-primary) 52%,var(--ui-bg-editor,transparent)));
  --px-y:color-mix(in srgb,var(--ui-text-primary) 66%,var(--ui-bg-editor,transparent));
  --px-Y:color-mix(in srgb,var(--ui-text-primary) 84%,var(--ui-bg-editor,transparent));
  --px-e:var(--ui-bg-editor);--px-w:color-mix(in srgb,var(--ui-bg-editor) 94%,var(--ui-text-primary));
  --px-g:color-mix(in srgb,var(--ui-text-primary) 44%,var(--ui-bg-editor,transparent));
  --px-l:color-mix(in srgb,var(--ui-text-primary) 76%,var(--ui-bg-editor,transparent));
  --px-R:color-mix(in srgb,var(--ui-red) 88%,var(--ui-text-primary));
  --px-c:var(--accent);--px-C:color-mix(in srgb,var(--accent) 62%,var(--ui-text-primary));--px-k:color-mix(in srgb,var(--accent) 28%,var(--ui-bg-editor));--px-i:color-mix(in srgb,var(--ui-text-primary) 95%,#fff);--px-q:color-mix(in srgb,var(--ui-yellow) 72%,var(--ui-text-primary))}
:root.dark .fkb{
  --px-o:color-mix(in srgb,var(--ui-accent) 5%,var(--ui-bg-editor));
  --px-d:color-mix(in srgb,var(--ui-accent) 20%,color-mix(in srgb,var(--ui-text-primary) 15%,var(--ui-bg-editor)));
  --px-r:color-mix(in srgb,var(--ui-accent) 30%,color-mix(in srgb,var(--ui-text-primary) 34%,var(--ui-bg-editor)));
  --px-M:color-mix(in srgb,var(--ui-accent) 14%,color-mix(in srgb,var(--ui-text-primary) 9%,var(--ui-bg-editor)));
  --px-m:color-mix(in srgb,var(--ui-accent) 26%,color-mix(in srgb,var(--ui-text-primary) 23%,var(--ui-bg-editor)));
  --px-p:color-mix(in srgb,var(--ui-accent) 16%,color-mix(in srgb,var(--ui-text-primary) 12%,var(--ui-bg-editor)));
  --px-h:color-mix(in srgb,var(--ui-accent) 46%,color-mix(in srgb,var(--ui-text-primary) 40%,var(--ui-bg-editor)));
  --px-H:color-mix(in srgb,var(--ui-purple) 46%,color-mix(in srgb,var(--ui-text-primary) 34%,var(--ui-bg-editor)));
  --px-y:color-mix(in srgb,var(--ui-text-primary) 46%,var(--ui-bg-editor));
  --px-Y:color-mix(in srgb,var(--ui-text-primary) 26%,var(--ui-bg-editor));
  --px-e:color-mix(in srgb,var(--ui-text-primary) 94%,transparent);--px-w:color-mix(in srgb,var(--ui-text-primary) 88%,transparent);
  --px-g:color-mix(in srgb,var(--ui-text-primary) 40%,var(--ui-bg-editor));
  --px-l:color-mix(in srgb,var(--ui-text-primary) 48%,var(--ui-bg-editor));
  --px-k:color-mix(in srgb,var(--accent) 35%,var(--ui-text-primary));--px-i:color-mix(in srgb,var(--ui-text-primary) 95%,#fff);--px-q:color-mix(in srgb,var(--ui-yellow) 72%,var(--ui-text-primary))}
.fkb .p-o{fill:var(--px-o)}.fkb .p-d{fill:var(--px-d)}.fkb .p-r{fill:var(--px-r)}.fkb .p-M{fill:var(--px-M)}
.fkb .p-m{fill:var(--px-m)}.fkb .p-p{fill:var(--px-p)}.fkb .p-h{fill:var(--px-h)}.fkb .p-H{fill:var(--px-H)}
.fkb .p-y{fill:var(--px-y)}.fkb .p-Y{fill:var(--px-Y)}.fkb .p-e{fill:var(--px-e)}.fkb .p-w{fill:var(--px-w)}
.fkb .p-g{fill:var(--px-g)}.fkb .p-l{fill:var(--px-l)}.fkb .p-R{fill:var(--px-R)}
.fkb .p-c{fill:var(--px-c)}.fkb .p-C{fill:var(--px-C)}.fkb .p-k{fill:var(--px-k)}
.fkb .fx .p-\\#{fill:var(--px-c)}.fkb .fx-zzz .p-\\#{fill:var(--px-y)}.fkb .fx-sparkle .p-\\#{fill:var(--px-k)}
.fkb:focus-visible{outline:2px solid var(--ui-accent);outline-offset:4px;border-radius:8px}
.fkb-svg{width:100%;height:100%;overflow:visible;display:block}
.fkb-frame-stack{position:relative;display:block;width:100%;height:100%;image-rendering:pixelated}
.fkb-frame{position:absolute;inset:0;width:100%;height:100%;image-rendering:pixelated;object-fit:fill}
.fkb-frame.b-caw,.fkb-frame.b-lid,.fkb-frame.b-wingup{opacity:0}
.fkb .fkb-frame.b-shut{opacity:1}
.fkb .fkb-frame.b-caw{opacity:clamp(0,calc((var(--beak) - .3) * 100),1)}
.fkb .fkb-frame.b-shut{opacity:clamp(0,calc((.3 - var(--beak)) * 100 + 1),1)}
.fkb .fkb-frame.b-lid{animation:fkb-blink var(--blink) steps(1) var(--phase) infinite}
.fkb .fkb-frame.b-wingup{animation:none}
.fkb[data-state="muted"] .fkb-frame.b-shut{opacity:0!important}
.fkb[data-state="muted"] .fkb-frame.b-lid{opacity:1!important;animation:none}
.fkb-particles{position:absolute;inset:0;width:100%;height:100%;overflow:visible;pointer-events:none}
.fkb g{transform-box:view-box}
/* beak: caw on notes, big caw tips the head back a pixel */
.fkb .b-caw{opacity:clamp(0,calc((var(--beak) - .3) * 100),1)}
.fkb .b-shut{opacity:clamp(0,calc((.3 - var(--beak)) * 100 + 1),1)}
.fkb .b-tilt{transform:translate(calc(clamp(0,(var(--beak) - .7) * 100,1) * -1px),calc(clamp(0,(var(--beak) - .7) * 100,1) * -1px))}
.fkb .b-lid{opacity:0;animation:fkb-blink var(--blink) steps(1) var(--phase) infinite}
.fkb .b-wingup{opacity:0}
/* two-frame costume loops */
.fkb .c-b{opacity:0;animation:fkb-alt-b .9s steps(1) var(--phase) infinite}
.fkb .c-a{animation:fkb-alt-a .9s steps(1) var(--phase) infinite}
.fkb[data-state="singing"] .c-a{animation-duration:calc(var(--beat) / 1)}
.fkb[data-state="singing"] .c-b{animation-duration:calc(var(--beat) / 1)}
.fkb[data-gesture="bounce"][data-state="singing"] .c-a,.fkb[data-gesture="bounce"][data-state="singing"] .c-b{animation-duration:.16s}
/* particles: notes when singing, Z's when dozing or muted, sparkles near shiny things */
.fkb .fx-p{opacity:0}
.fkb[data-state="singing"] .fx-notes .fx-p{animation:fkb-rise calc(var(--beat) * 2) steps(6) infinite}
.fkb[data-state="singing"] .fx-notes .fx-p1{animation-delay:calc(var(--beat) * .66)}
.fkb[data-state="singing"] .fx-notes .fx-p2{animation-delay:calc(var(--beat) * 1.33)}
.fkb:not([data-state="singing"]) .fx-zzz .fx-p,.fkb[data-state="muted"] .fx-zzz .fx-p{animation:fkb-rise 3.6s steps(8) infinite}
.fkb .fx-zzz .fx-p1{animation-delay:1.2s}.fkb .fx-zzz .fx-p2{animation-delay:2.4s}
.fkb .fx-sparkle .fx-p{animation:fkb-spark 2.8s steps(1) var(--phase) infinite}
.fkb .fx-sparkle .fx-p1{animation-delay:.9s}.fkb .fx-sparkle .fx-p2{animation-delay:1.8s}
/* idle: whole-pixel, stepped like a real sprite */
.fkb .b-body{animation:fkb-breathe var(--breath) steps(1) var(--phase) infinite}
.fkb[data-gesture="nod"] .b-head,.fkb[data-gesture="regal"] .b-head{animation:fkb-nod calc(var(--beat) * 2) steps(1) var(--phase) infinite}
.fkb[data-gesture="lean"] .b-root{animation:fkb-lean 3.2s steps(1) var(--phase) infinite}
.fkb[data-gesture="tap"] .b-wing{animation:fkb-tap calc(var(--beat) * 2) steps(1) var(--phase) infinite}
.fkb[data-gesture="sway"] .b-root{animation:fkb-sway 4s steps(1) var(--phase) infinite}
.fkb[data-gesture="tilt"] .b-head{animation:fkb-peek 5s steps(1) var(--phase) infinite}
.fkb[data-gesture="doze"] .b-head{animation:fkb-droop 5s steps(1) var(--phase) infinite}
.fkb[data-gesture="settle"] .b-wing{animation:fkb-tap 6s steps(1) var(--phase) infinite}
.fkb[data-gesture="twitch"] .b-head{animation:fkb-twitch 2.4s steps(1) var(--phase) infinite}
.fkb[data-gesture="bounce"] .b-root{animation:fkb-bob 2.2s steps(1) var(--phase) infinite}
.fkb[data-gesture="answer"] .b-head{animation:fkb-peek 4s steps(1) var(--phase) infinite}
/* singing: gestures lock to the beat */
.fkb[data-state="singing"] .b-head{animation:fkb-nod var(--beat) steps(1) infinite}
.fkb[data-state="singing"][data-gesture="hop"] .b-root{animation:fkb-hop calc(var(--beat) * 2) steps(1) infinite}
.fkb[data-state="singing"][data-gesture="bounce"] .b-root{animation:fkb-bob var(--beat) steps(1) infinite}
.fkb[data-state="singing"][data-gesture="tap"] .b-wing{animation:fkb-tap var(--beat) steps(1) infinite}
.fkb[data-state="singing"][data-gesture="twitch"] .b-head{animation:fkb-twitch calc(var(--beat) * 2) steps(1) infinite}
.fkb[data-state="singing"][data-gesture="belt"] .b-head{animation:fkb-belt calc(var(--beat) * 4) steps(1) infinite}
.fkb[data-state="singing"][data-gesture="lean"] .b-root{animation:fkb-lean calc(var(--beat) * 2) steps(1) infinite}
/* muted / dimmed */
.fkb[data-state="muted"] .b-lid{opacity:1;animation:none}
.fkb[data-state="muted"] .b-head{animation:none;transform:translateY(1px)}
.fkb[data-state="muted"] .c-costume{opacity:.45}
.fkb[data-state="dim"]{opacity:.3;filter:saturate(.3)}
.fkb{transition:opacity .12s,filter .12s}
/* arrivals and departures: the real wing-up frame flaps, then folds */
.fkb[data-anim="land"] .b-root{animation:fkb-land .64s steps(8,end) var(--land-delay,0ms) both!important}
.fkb[data-anim="land"] .b-wingup{animation:fkb-wingup .64s steps(1) var(--land-delay,0ms) both!important}
.fkb[data-anim="land"] .b-wing{animation:fkb-wingfold .64s steps(1) var(--land-delay,0ms) both!important}
.fkb[data-anim="leave"] .b-root{animation:fkb-leave .4s steps(6,end) var(--leave-delay,0ms) both!important}
.fkb[data-anim="leave"] .b-wingup{animation:fkb-wingup .4s steps(1) var(--leave-delay,0ms) both reverse!important}
.fkb[data-anim="leave"] .b-wing{opacity:0}
.fkb[data-anim="ruffle"] .b-body{animation:fkb-ruffle .24s steps(1) both!important}

@keyframes fkb-blink{0%,94%{opacity:0}95%,98%{opacity:1}99%,100%{opacity:0}}
@keyframes fkb-alt-a{0%,49%{opacity:1}50%,100%{opacity:0}}
@keyframes fkb-alt-b{0%,49%{opacity:0}50%,100%{opacity:1}}
@keyframes fkb-rise{0%{opacity:0;transform:none}12%{opacity:1}80%{opacity:1;transform:translate(1px,-5px)}100%{opacity:0;transform:translate(2px,-7px)}}
@keyframes fkb-spark{0%,70%,100%{opacity:0}74%,82%{opacity:1}}
@keyframes fkb-breathe{0%,49%{transform:none}50%,100%{transform:translateY(-.5px)}}
@keyframes fkb-nod{0%,49%{transform:none}50%,100%{transform:translateY(1px)}}
@keyframes fkb-droop{0%,59%{transform:translateY(1px)}60%,72%{transform:none}73%,100%{transform:translateY(1px)}}
@keyframes fkb-lean{0%,49%{transform:none}50%,100%{transform:translateX(-1px)}}
@keyframes fkb-tap{0%,79%{transform:none}80%,100%{transform:translateY(-1px)}}
@keyframes fkb-sway{0%,24%{transform:none}25%,49%{transform:translateX(1px)}50%,74%{transform:none}75%,100%{transform:translateX(-1px)}}
@keyframes fkb-peek{0%,64%{transform:none}65%,89%{transform:translate(1px,-1px)}90%,100%{transform:none}}
@keyframes fkb-twitch{0%{transform:none}20%{transform:translateX(1px)}35%{transform:none}55%{transform:translateY(1px)}70%{transform:translate(1px,0)}85%{transform:none}}
@keyframes fkb-bob{0%,49%{transform:none}50%,100%{transform:translateY(-1px)}}
@keyframes fkb-hop{0%,14%{transform:translateY(-3px)}15%,24%{transform:translateY(-1px)}25%,100%{transform:none}}
@keyframes fkb-belt{0%,24%{transform:translate(-1px,-2px)}25%,100%{transform:none}}
@keyframes fkb-land{0%{transform:translate(22px,-26px) scale(.9,.9);opacity:0}10%{opacity:1}78%{transform:translate(0,1px) scale(1.08,.88)}90%{transform:translateY(-1px) scale(.96,1.04)}100%{transform:none}}
@keyframes fkb-wingup{0%,12%{opacity:1;transform:none}13%,25%{opacity:1;transform:translateY(3px)}26%,38%{opacity:1;transform:none}39%,51%{opacity:1;transform:translateY(3px)}52%,70%{opacity:1;transform:none}71%,100%{opacity:0}}
@keyframes fkb-wingfold{0%,70%{opacity:0}71%,100%{opacity:1}}
@keyframes fkb-leave{0%{transform:none}20%{transform:translateY(1px)}100%{transform:translate(-24px,-28px);opacity:0}}
@keyframes fkb-ruffle{0%,49%{transform:translateY(-1px)}50%,100%{transform:none}}
@media (prefers-reduced-motion:reduce){.fkb *{animation:none!important}.fkb .b-lid,.fkb .fx-p,.fkb .b-wingup,.fkb .c-b{opacity:0}}
`

// The Wire: Rookery's melodic layer UI (React, desktop/plugin.js house style).
// Data in, events out: the flock lives in project.json; this component only draws it
// and reports user intent through onChange(nextFlock, meta). Beaks open on rendered
// note events and the wire shivers on rendered kick onsets: the animation tells the truth.
//
//   <FlockPanel catalog flock render playing getPosition onChange bpm />
//     catalog: { birds, corvus, templates, combos }   (GET /flock/catalog)
//     render:  { events: {birdId: [{t, len, midi, vel}]}, kick_onsets: [t], active_combos: [id] } | null

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
const FLOCK_CSS = BIRD_CSS + `
.fkp{display:flex;flex-direction:column;gap:12px;color:var(--ui-text-primary);font-variant-numeric:tabular-nums}
.fkp button{font:inherit;color:inherit;background:none;border:0;padding:0;cursor:pointer}
.fkp button:focus-visible,.fkp select:focus-visible{outline:2px solid var(--ui-accent);outline-offset:2px;border-radius:6px}
.fkp-head{display:flex;align-items:center;gap:14px;flex-wrap:wrap;min-height:30px}
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

.fkp-stage{position:relative;height:${STAGE_H}px;border-radius:12px;overflow:hidden;isolation:isolate;background:var(--ui-bg-editor);transition:height .12s ease}
.fkp-stage[data-mix-open="true"]{height:370px}
.fkp-scene{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;image-rendering:pixelated;pointer-events:none;z-index:0}
.fkp-scene-clouds{animation:fkp-cloud-drift 96s linear infinite alternate}
.fkp-scene-ground{animation:fkp-ground-drift 72s linear infinite alternate}
.fkp-weather{position:absolute;inset:0;width:100%;height:100%;pointer-events:none;z-index:1}
.fkp-stage:before,.fkp-stage:after{content:'';position:absolute;inset:0;pointer-events:none;z-index:-1}
.fkp-stage:before{background:linear-gradient(180deg,transparent 56%,color-mix(in srgb,var(--ui-text-primary) 5%,transparent) 56%),linear-gradient(90deg,transparent 4%,color-mix(in srgb,var(--ui-text-primary) 6%,transparent) 4% 5%,transparent 5% 13%,color-mix(in srgb,var(--ui-text-primary) 8%,transparent) 13% 15%,transparent 15% 28%,color-mix(in srgb,var(--ui-text-primary) 5%,transparent) 28% 31%,transparent 31%);background-size:100% 100%,100% 100%;opacity:.4;animation:fkp-drift 28s linear infinite alternate}
.fkp-stage:after{inset:auto 0 0;height:34%;background:linear-gradient(180deg,transparent,color-mix(in srgb,var(--ui-text-primary) 5%,transparent));opacity:.7}
.fkp-stage[data-combo="night_shift"]{background:linear-gradient(180deg,color-mix(in srgb,var(--ui-purple) 14%,var(--ui-bg-editor)) 0%,color-mix(in srgb,var(--ui-bg-editor) 92%,var(--ui-text-primary)) 100%)}
.fkp-star{position:absolute;width:2px;height:2px;background:var(--ui-text-primary);opacity:.16}
.fkp-star[data-tw="true"]{animation:fkp-twinkle 3.2s steps(2) infinite}
.fkp-moon{position:absolute;right:56px;top:22px;width:22px;height:22px;background:color-mix(in srgb,var(--ui-text-primary) 25%,transparent);
  clip-path:polygon(30% 0,70% 0,70% 10%,90% 10%,90% 30%,100% 30%,100% 70%,90% 70%,90% 90%,70% 90%,70% 100%,30% 100%,30% 90%,10% 90%,10% 70%,0 70%,0 30%,10% 30%,10% 10%,30% 10%);opacity:0;transition:opacity .6s}
.fkp-stage[data-combo="night_shift"] .fkp-moon{opacity:.3}
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
.fkp-name{position:absolute;z-index:2;left:50%;top:calc(100% + 9px);transform:translateX(-50%);font-size:11px;color:var(--ui-text-quaternary);white-space:nowrap;padding:2px 5px;border-radius:4px;background:color-mix(in srgb,var(--ui-bg-editor) 70%,transparent)}
.fkp-name b{color:var(--ui-text-secondary);font-weight:600}
.fkp-badge{position:absolute;left:58%;top:-6px;font-size:10px;font-weight:700;padding:1px 5px;border-radius:4px;background:var(--ui-bg-elevated);color:var(--ui-text-secondary);box-shadow:0 0 0 1px var(--ui-stroke-tertiary);animation:fkp-pop .9s steps(3) both}
.fkp-mix-badge{position:absolute;left:58%;top:-22px;font-size:9.5px;padding:1px 4px;border-radius:4px;background:var(--ui-bg-elevated);color:var(--ui-text-secondary);box-shadow:0 0 0 1px var(--ui-stroke-tertiary);white-space:nowrap}
.fkp-mix-ctl{position:absolute;z-index:8;left:50%;top:calc(100% + 47px);transform:translateX(-50%);display:flex;align-items:center;gap:7px;max-width:calc(100vw - 32px);padding:6px 8px;border-radius:7px;background:var(--ui-bg-elevated);border:1px solid var(--ui-stroke-tertiary);box-shadow:var(--shadow-nous,none);font-size:10px;color:var(--ui-text-tertiary)}
.fkp-mix-ctl label{display:flex;align-items:center;gap:4px;white-space:nowrap;flex-shrink:0}.fkp-mix-ctl input{width:52px;height:14px;accent-color:var(--ui-accent)}
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
@keyframes fkp-drift{to{transform:translateX(-8px)}}
@keyframes fkp-cloud-drift{to{transform:translateX(-14px)}}
@keyframes fkp-ground-drift{to{transform:translateX(8px)}}
@keyframes fkp-twinkle{50%{opacity:.4}}
@keyframes fkp-dust{0%{transform:translate(0,0)}100%{transform:translate(28px,-14px);opacity:0}}
@keyframes fkp-rain{0%{transform:translate(0,-10px)}100%{transform:translate(-6px,${STAGE_H}px)}}
@keyframes fkp-wind{0%{transform:translateX(-30px);opacity:0}30%{opacity:.2}100%{transform:translateX(160px);opacity:0}}
@keyframes fkp-pop{0%{transform:translateY(4px);opacity:0}30%,80%{transform:none;opacity:1}100%{opacity:0}}
@keyframes fkp-banner{0%{opacity:0}6%,88%{opacity:1}100%{opacity:0}}
@keyframes fkp-swarm{0%{opacity:0;transform:translate(0,0)}10%{opacity:.85}
  50%{transform:translate(calc(cos(var(--a)) * var(--r) * 1px),calc(sin(var(--a)) * var(--r) * .45px - 40px))}
  100%{opacity:0;transform:translate(calc(cos(var(--a) + 2rad) * var(--r) * 1.6px),calc(sin(var(--a) + 2rad) * var(--r) * .6px - 90px))}}
@media (prefers-reduced-motion:reduce){.fkp *{animation:none!important}.fkp *{transition:none!important}.fkp-swarm{display:none}.fkp-banner{opacity:1}}
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

// Raster scene layers once per template/weather/theme palette, just like sprites.
const FLOCK_SCENE_CACHE = new Map()
function flockSceneUrls(el, template, weather) {
  const color = token => resolveColor(el, `var(${token})`)
  const editor = color('--ui-bg-editor')
  const accent = color('--ui-accent')
  const purple = color('--ui-purple')
  const palette = [editor, accent, color('--ui-text-primary'), purple,
    resolveColor(el, `color-mix(in srgb, ${template === 'trap_night' || template === 'late_house' ? purple : accent} 65%, ${editor} 35%)`),
    resolveColor(el, `color-mix(in srgb, ${template === 'trap_night' || template === 'late_house' ? purple : accent} 40%, ${editor} 60%)`),
    resolveColor(el, `color-mix(in srgb, ${template === 'trap_night' || template === 'late_house' ? purple : accent} 55%, ${editor} 45%)`),
    color('--ui-yellow')]
  const key = JSON.stringify([template || 'Custom', weather, palette])
  if (FLOCK_SCENE_CACHE.has(key)) return FLOCK_SCENE_CACHE.get(key)
  const make = draw => {
    const c = document.createElement('canvas'); c.width = 480; c.height = STAGE_H
    const x = c.getContext('2d'); x.imageSmoothingEnabled = false; draw(x, ...palette)
    return c.toDataURL()
  }
  const night = template === 'trap_night' || template === 'late_house'
  const sky = make((x, base, accent, ink, purple, far, near, middle, yellow) => {
    const g = x.createLinearGradient(0, 0, 0, STAGE_H); g.addColorStop(0, night ? purple : accent); g.addColorStop(1, base)
    x.fillStyle = g; x.fillRect(0, 0, 480, STAGE_H)
    x.globalAlpha = .2; x.fillStyle = ink
    for (let i = 0; i < 30; i++) x.fillRect((i * 83) % 480, (i * 47) % 135, 2, 2)
    x.globalAlpha = 1
    x.fillStyle = night ? yellow : accent; x.globalAlpha = .27; x.fillRect(night ? 394 : 62, 30, 12, 12); x.globalAlpha = 1
  })
  const clouds = make((x, base, accent, ink) => {
    x.fillStyle = ink; x.globalAlpha = .13
    for (let i = 0; i < 7; i++) { const a = 24 + i * 67, b = 42 + (i % 3) * 24; x.fillRect(a, b, 30, 4); x.fillRect(a + 6, b - 4, 18, 4) }
    x.globalAlpha = 1
  })
  const ground = make((x, base, accent, ink, purple, far, near, middle, yellow) => {
    const kind = template || 'custom'
    // Receding blocks stay subdued and vary in height; roof equipment breaks the skyline.
    x.fillStyle = far
    for (let i = 0; i < 13; i++) {
      const a = i * 39 - 4, top = 181 + ((i * 17 + kind.length * 3) % 26)
      const width = 25 + (i * 7 % 13)
      x.fillRect(a, top, width, 236 - top)
      x.fillStyle = middle
      x.fillRect(a + 4, top - 2, Math.max(8, width - 8), 2)
      x.fillStyle = far
      if (i % 3 === 0) { x.fillRect(a + 8, top - 7, 3, 7); x.fillRect(a + 5, top - 9, 9, 2) }
      if (i % 4 === 1) { x.fillRect(a + 12, top - 5, 2, 5); x.fillRect(a + 9, top - 6, 8, 2) }
    }
    // Template landmarks: a church spire, study roof, broad house roofs, or taller city blocks.
    if (kind === 'sunday_soul') {
      x.fillStyle = far; x.fillRect(232, 164, 16, 72); x.fillRect(226, 162, 28, 4)
      x.fillRect(237, 151, 6, 11); x.fillRect(239, 143, 2, 8); x.fillRect(234, 155, 12, 2)
      x.fillStyle = middle; x.fillRect(238, 174, 4, 14); x.fillRect(238, 198, 4, 14)
    } else if (kind === 'lo_fi_study') {
      x.fillStyle = near; x.fillRect(66, 193, 5, 43); x.fillRect(197, 193, 5, 43); x.fillRect(66, 193, 136, 4)
      x.fillRect(116, 207, 5, 29); x.fillRect(109, 204, 19, 3)
    } else if (kind === 'dusty_boom_bap') {
      x.fillStyle = near; x.fillRect(84, 203, 75, 33); x.fillRect(93, 196, 53, 7); x.fillRect(123, 188, 3, 8)
    } else if (kind === 'trap_night' || kind === 'late_house') {
      x.fillStyle = near
      for (let i = 0; i < 7; i++) { const a = i * 73 - 6, top = 187 + (i * 11 % 23); x.fillRect(a, top, 48, 236 - top); x.fillRect(a + 6, top - 3, 36, 3); if (i % 2 === 0) x.fillRect(a + 19, top - 9, 3, 9) }
    }
    // Irregular tree crowns and trunks form a darker foreground, kept below the name row.
    x.fillStyle = near
    for (const [a, y, size] of [[15,205,1],[47,198,0],[275,206,1],[324,201,0],[390,204,1],[448,199,0]]) {
      const r = size ? 12 : 9
      x.fillRect(a + 9, y + 13, 4, 31)
      x.fillRect(a + 4, y + 7, 13, 11); x.fillRect(a, y + 10, 8, 8); x.fillRect(a + 12, y + 3, 9, 12)
      x.fillRect(a + 6, y + 2, 10, 6); x.fillRect(a + 3, y + 14, 15, 3)
      if (r === 12) { x.fillStyle = middle; x.fillRect(a + 7, y + 5, 7, 2); x.fillStyle = near }
    }
    // A restrained handful of lit windows: never more than twelve 1–2 px accents.
    x.fillStyle = yellow; x.globalAlpha = .32
    for (const [wx, wy] of [[39,205],[103,218],[174,199],[212,215],[296,210],[350,197],[417,219],[463,207]]) x.fillRect(wx, wy, 2, 2)
    x.globalAlpha = 1
  })
  const result = { sky, clouds, ground }; FLOCK_SCENE_CACHE.set(key, result); return result
}

function WeatherCanvas({ weather, visible }) {
  const ref = useRef(null)
  useEffect(() => {
    const canvas = ref.current, ctx = canvas?.getContext('2d')
    if (!canvas || !ctx || !visible || weather === 'clear' || matchMedia('(prefers-reduced-motion: reduce)').matches) return
    let raf = 0, frame = 0
    const draw = () => {
      const w = canvas.clientWidth, hgt = canvas.clientHeight, dpr = devicePixelRatio || 1
      if (canvas.width !== Math.round(w*dpr) || canvas.height !== Math.round(hgt*dpr)) { canvas.width=Math.round(w*dpr); canvas.height=Math.round(hgt*dpr) }
      ctx.setTransform(dpr,0,0,dpr,0,0); ctx.clearRect(0,0,w,hgt); ctx.fillStyle=resolveColor(canvas.parentElement,'var(--ui-text-primary)')
      for(let i=0;i<60;i++){const px=(i*79+frame*(weather==='wind'?1.2:.25))%w, py=(i*43+frame*(weather==='rain'?5:.55))%hgt; ctx.fillRect(px,py,weather==='rain'?1:2,weather==='rain'?7:2)}
      frame++; raf=requestAnimationFrame(draw)
    }
    raf=requestAnimationFrame(draw); return ()=>cancelAnimationFrame(raf)
  }, [weather, visible])
  return h('canvas',{className:'fkp-weather',ref,'aria-hidden':true})
}

function FlockPanel({ catalog, flock, render, playing, getPosition, onChange, bpm = 90 }) {
  const stage = useRef(null), wire = useRef(null), birdEls = useRef({}), slotRefs = useRef({})
  const [scene, setScene] = useState(null), [stageVisible, setStageVisible] = useState(false)
  const w = useWidth(stage)
  const [hint, setHint] = useState(null)
  const [banner, setBanner] = useState(null)
  const [badges, setBadges] = useState({}) // slot -> nonce for the song badge
  const [mixOpen, setMixOpen] = useState(null)
  const [mixDraft, setMixDraft] = useState({})
  const mixTimers = useRef({})
  const mixPending = useRef({})
  const [anims, setAnims] = useState({})   // slot -> 'land' | 'leave'
  const [leaving, setLeaving] = useState([])
  const prev = useRef(flock.perches)
  const shownCombos = useRef(new Set())
  const taps = useRef([])
  const timers = useRef([])

  const byId = useMemo(() => Object.fromEntries([...catalog.birds, catalog.corvus].map(b => [b.id, b])), [catalog])
  const perches = flock.perches || []
  const selectedTemplate = (catalog.templates || []).find(template => {
    // Applying a template preserves the unlocked seventh perch (Corvus), which
    // is an optional player layer rather than part of the template's identity.
    const perched = perches.filter(item => item && item.bird !== catalog.corvus?.id)
    const progression = flock.progression || []
    const expectedBirds = new Set(template.birds.map(item => `${item.bird}\u0000${item.song || 'A'}`))
    const actualBirds = new Set(perched.map(item => `${item.bird}\u0000${item.song || 'A'}`))
    return normalizeFlockKey(template.key) === normalizeFlockKey(flock.key) && template.scale === flock.scale &&
      template.progression.length === progression.length && template.progression.every((chord, i) => chord === progression[i]) &&
      expectedBirds.size === actualBirds.size && [...expectedBirds].every(item => actualBirds.has(item))
  })
  useEffect(() => {
    const el=stage.current; if(!el) return
    setScene(flockSceneUrls(el, selectedTemplate?.id || 'Custom', flock.weather || 'clear'))
  }, [selectedTemplate?.id, flock.weather])
  useEffect(() => {
    const el=stage.current; if(!el) return
    const io=new IntersectionObserver(entries=>setStageVisible(!!entries[0]?.isIntersecting)); io.observe(el)
    return ()=>io.disconnect()
  }, [])
  const corvusUnlocked = (catalog.birds || []).every(b => (flock.seen || []).includes(b.id))
  const slots = corvusUnlocked ? 7 : 6
  const xs = Array.from({ length: slots }, (_, i) => PAD + 64 + (i * (w - 2 * PAD - 128)) / (slots - 1))
  // landing / leaving: diff perches against the previous render
  useEffect(() => {
    const before = prev.current || [], next = perches
    const add = {}
    let order = 0
    for (let i = 0; i < Math.max(before.length, next.length); i++) {
      if (next[i] && (!before[i] || before[i].bird !== next[i].bird)) add[i] = { kind: 'land', delay: (leaving.length ? 400 + (leaving.length - 1) * 60 : 0) + order++ * 60 }
    }
    prev.current = next
    if (!Object.keys(add).length) return
    setAnims(a => ({ ...a, ...add }))
    // One timer per landing, never cancelled by the next landing.
    timers.current.push(setTimeout(() => setAnims(a => { const c = { ...a }; for (const k of Object.keys(add)) if (c[k] === add[k]) delete c[k]; return c }), 720 + order * 60))
  }, [perches.map(p => p?.bird || '-').join(','), leaving.length])
  useEffect(() => () => { timers.current.forEach(clearTimeout); Object.values(mixTimers.current).forEach(clearTimeout) }, [])

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
      const loop = render?.loop_seconds || 0
      let amp = 0
      if (t >= 0 && render) {
        for (const k of render.kick_onsets || []) { const elapsed = loop > 0 ? (t - k + loop) % loop : t - k; if (elapsed >= 0 && elapsed < 0.45) amp += 1.8 * Math.exp(-elapsed * 10) * Math.sin(elapsed * 64) }
        for (const p of perches) {
          if (!p) continue
          const el = birdEls.current[p.bird]
          if (!el) continue
          let v = 0
          if (!p.mute) for (const n of render.events?.[p.bird] || []) {
            const elapsed = loop > 0 ? (t - n.t + loop) % loop : t - n.t
            if (elapsed >= 0 && elapsed < n.len) { v = Math.max(v, (n.vel ?? 0.8) * (1 - 0.45 * elapsed / Math.max(n.len, 0.08))); }
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
    if (target < 0) {
      target = next.findIndex(p => p && byId[p.bird]?.role === bird.role)
      if (target >= 0 && next[target]) {
        const departing = next[target]
        const cleared = [...next]
        cleared[target] = null
        onChange({ ...flock, perches: cleared }, { action: 'unperch', bird: departing.bird, slot: target })
      }
    }
    if (target < 0) return
    next[target] = { bird: id, song: 'A', mute: false, solo: false }
    setPerches(next, { action: 'perch', bird: id, slot: target })
  }
  const patch = (slot, change, meta) => { const next = [...perches]; next[slot] = { ...next[slot], ...change }; setPerches(next, meta) }
  const queueMixChange = (slot, field, raw) => {
    const p = perches[slot]
    if (!p) return
    const value = Number(raw)
    const key = p.bird
    mixPending.current[key] = { ...(mixPending.current[key] || {}), [field]: value }
    setMixDraft(d => ({ ...d, [key]: { ...(d[key] || {}), [field]: value } }))
    clearTimeout(mixTimers.current[key])
    mixTimers.current[key] = setTimeout(() => {
      const changes = mixPending.current[key] || {}
      delete mixPending.current[key]
      const next = [...perches]
      next[slot] = { ...next[slot], ...changes }
      onChange({ ...flock, perches: next }, { action: 'mix', bird: key, fields: Object.keys(changes) })
      setMixDraft(d => { const copy = { ...d }; delete copy[key]; return copy })
    }, 220)
  }
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
    const outgoing = perches.flatMap((p, slot) => p && !next.some(q => q?.bird === p.bird) ? [{ ...p, slot, delay: perches.slice(0, slot).filter(q => q && !next.some(n => n?.bird === q.bird)).length * 60 }] : [])
    if (outgoing.length) {
      setLeaving(outgoing)
      timers.current.push(setTimeout(() => setLeaving([]), 400 + (outgoing.length - 1) * 60))
    }
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
      slotRefs.current[nxt]?.focus?.()
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

  return h('section', { className: 'fkp', 'aria-label': 'Flock controls' },
    h('style', null, FLOCK_CSS),
    h('div', { className: 'fkp-head' },
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
        h('select', { className: 'fkp-sel', value: selectedTemplate?.id || '', onChange: e => applyTemplate(e.target.value) },
          h('option', { value: '' }, 'Custom'), catalog.templates.map(t => h('option', { key: t.id, value: t.id }, t.name)))),
      h('div', { className: 'fkp-meter', onMouseEnter: () => setHint(true), onMouseLeave: () => setHint(null) },
        'Murmurations',
        h('div', { className: 'fkp-dots' }, combos.map(c => h('i', { key: c.id, className: 'fkp-dot', 'data-found': (flock.unlocked || []).includes(c.id), 'data-near': near?.id === c.id }))),
        hint && h('div', { className: 'fkp-hint', role: 'tooltip' },
          h('b', null, `${(flock.unlocked || []).length} of ${combos.length} found`),
          near ? near.riddle : 'Keep mixing. Some birds sing differently together.'))),
    h('div', { className: 'fkp-stage', ref: stage, 'data-mix-open': !!mixOpen, 'data-combo': (render?.active_combos || []).includes('night_shift') ? 'night_shift' : undefined },
      scene && h(Fragment,null,h('img',{className:'fkp-scene',src:scene.sky,alt:''}),h('img',{className:'fkp-scene fkp-scene-clouds',src:scene.clouds,alt:''}),h('img',{className:'fkp-scene fkp-scene-ground',src:scene.ground,alt:''})),
      h(WeatherCanvas,{weather:flock.weather,visible:stageVisible}),
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
          if (slot === 6) return h('button', { key: slot, ref: el => { if (el) slotRefs.current[slot] = el; else delete slotRefs.current[slot] }, 'data-slot': slot, className: 'fkp-empty', style: { left: x, top: y - 14 }, title: 'A seventh perch has appeared…', onClick: () => perchBird('corvus', 6) }, '♛')
          return h('button', { key: slot, ref: el => { if (el) slotRefs.current[slot] = el; else delete slotRefs.current[slot] }, 'data-slot': slot, className: 'fkp-empty', style: { left: x, top: y - 14 }, 'aria-label': `Empty perch ${slot + 1}`, onKeyDown: e => onKey(e, slot), onClick: () => {
            const unseen = catalog.birds.find(b => !perches.some(q => q?.bird === b.id) && !perches.some(q => q && byId[q.bird]?.role === b.role))
            if (unseen) perchBird(unseen.id, slot)
          } }, '+')
        }
        const bird = byId[p.bird]
        const anim = anims[slot]
        const mix = { ...p, ...(mixDraft[p.bird] || {}) }
        const panBadge = (p.pan || 0) ? fmtPan(p.pan).replace(/(\d+)([LR])/, '$2$1') : ''
        const mixBadge = `${(p.gain_db || 0) ? fmtDb(p.gain_db) : ''}${(p.gain_db || 0) && panBadge ? ' · ' : ''}${panBadge}`
        const state = p.mute ? 'muted' : anySolo && !p.solo ? 'dim' : playing ? 'singing' : 'idle'
        return h('div', { key: `${slot}:${p.bird}`, className: 'fkp-perch', style: { left: x, top: y + BIRD / 32, '--land-delay': `${anim?.delay || 0}ms` } },
          h('div', { ref: el => { if (el) { birdEls.current[p.bird] = el.firstChild; slotRefs.current[slot] = el.firstChild } else { delete birdEls.current[p.bird]; delete slotRefs.current[slot] } }, onKeyDown: e => onKey(e, slot) },
            h(Bird, { id: artId(p.bird), size: BIRD, bpm, state, anim: anim?.kind || null, onClick: () => cycleSong(slot), label: `${bird?.name || p.bird}, ${bird?.role}, song ${p.song}${p.mute ? ', muted' : ''}. Click to change the song.` })),
          badges[slot] && h('span', { key: badges[slot], className: 'fkp-badge' }, p.song),
          mixBadge && h('span', { className: 'fkp-mix-badge' }, mixBadge),
          h('div', { className: 'fkp-tools' },
            h('button', { 'data-k': 'm', 'aria-pressed': !!p.mute, 'aria-label': `Mute ${bird?.name}`, onClick: () => patch(slot, { mute: !p.mute }, { action: 'mute', bird: p.bird, slot }) }, 'M'),
            h('button', { 'data-k': 's', 'aria-pressed': !!p.solo, 'aria-label': `Solo ${bird?.name}`, onClick: () => patch(slot, { solo: !p.solo }, { action: 'solo', bird: p.bird, slot }) }, 'S'),
            h('button', { className: NATIVE.pill, 'aria-expanded': mixOpen === p.bird, 'aria-label': `Mix ${bird?.name}`, onClick: () => setMixOpen(current => current === p.bird ? null : p.bird) }, 'Mix'),
            h('button', { 'aria-label': `Song ${p.song} of ${bird?.name}, click for the next`, onClick: () => cycleSong(slot) }, p.song),
            h('button', { className: 'fkp-x', 'aria-label': `Send ${bird?.name} home`, onClick: () => { const next = [...perches]; next[slot] = null; setPerches(next, { action: 'unperch', bird: p.bird, slot }) } }, '×')),
          mixOpen === p.bird && h('div', { className: 'fkp-mix-ctl', 'aria-label': `${bird?.name} gain and pan`, style: { transform: `translateX(calc(-50% + ${Math.max(0, 130 - x) - Math.max(0, x - (w - 130))}px))` } },
            h('label', null, 'Gain', h('input', { type: 'range', min: -24, max: 12, step: 0.5, value: mix.gain_db ?? 0, 'aria-label': `${bird?.name} gain dB`, onChange: e => queueMixChange(slot, 'gain_db', e.target.value) }), fmtDb(mix.gain_db || 0)),
            h('label', null, 'Pan', h('input', { type: 'range', min: -1, max: 1, step: 0.01, value: mix.pan ?? 0, 'aria-label': `${bird?.name} pan`, onChange: e => queueMixChange(slot, 'pan', e.target.value) }), fmtPan(mix.pan || 0).replace(/(\d+)([LR])/, '$2$1'))),
          h('div', { className: 'fkp-name' }, h('b', null, bird?.name), ` · ${bird?.role}`))
      }),
      leaving.map(item => {
        const x = xs[item.slot] ?? xs[0], y = wireYAt(x, w), bird = byId[item.bird]
        return h('div', { key: `leaving:${item.slot}:${item.bird}`, className: 'fkp-perch', style: { left: x, top: y + BIRD / 32, '--leave-delay': `${item.delay}ms` } },
          h(Bird, { id: artId(item.bird), size: BIRD, bpm, state: 'idle', anim: 'leave', label: `${bird?.name || item.bird} leaving` }))
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

// ── states ────────────────────────────────────────────────────────────────
const GHOST = 'x...x.x...x.x..x'
// With the chat rail open the starters live there, so the page just points at it.
function Empty({ onPrompt, onNew, chatOpen }) {
  const use = async text => {
    if (onPrompt) return onPrompt(text)
    const ok = await host.composer?.setDraft?.(null, text).catch(() => false)
    if (!ok) host.notify({ kind: 'info', message: 'Open a chat, then pick a prompt to drop it in.' })
  }
  return h('div', { className: 'rk-empty' },
    h('div', { className: 'rk-ghost', 'aria-hidden': true }, GHOST.split('').map((c, i) => h('i', { key: i, 'data-on': c === 'x', style: { '--d': i } }))),
    h('h2', null, 'Tell Hermes the beat.'),
    h('p', null, 'Rookery is a step sequencer Hermes plays like an instrument. Ask in the chat and watch the grid fill in, render, and pass its checks. Click any pad to change it yourself.'),
    chatOpen
      ? h('div', { style: { display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap', justifyContent: 'center' } }, h('p', { className: 'rk-point' }, 'Describe it in the chat', h('span', { 'aria-hidden': true }, ' →')), h('button', { type: 'button', className: 'rk-chip rk-chip-primary', onClick: onNew }, 'Start a blank beat'))
      : h('div', { className: 'rk-chips' }, PROMPTS.map(t => h('button', { key: t, className: 'rk-chip', onClick: () => use(t) }, t)), h('button', { type: 'button', className: 'rk-chip rk-chip-primary', onClick: onNew }, 'Start a blank beat')))
}

function Offline({ message, onRetry }) {
  return h('div', { className: 'rk-empty' },
    h('h2', null, 'Rookery’s engine isn’t running'),
    h('p', null, 'The page is installed, but its backend didn’t answer. Make sure “rookery” is in plugins.enabled in config.yaml, then restart the gateway.'),
    h('p', { className: 'rk-mono', style: { fontSize: 11.5, color: 'var(--ui-text-quaternary)' } }, message),
    h('div', { className: 'rk-chips' }, h('button', { className: 'rk-chip', onClick: onRetry }, 'Try again')))
}

// ── in-page chat: Hermes's own parts, Rookery's upgrades (docs/design/chat.md) ──
// The session is a real Hermes session (gateway RPC through host.request), so
// "Dock beside chat" can hand the same conversation to the main thread.
const CHAT_CSS = `
.rk-split{position:relative;display:flex;height:100%;min-height:0;min-width:0;background:var(--ui-bg-editor)}
.rk-split>.rk{flex:1;min-width:0}
.rk-split[data-narrow="true"]{flex-direction:column}
.rkx{position:relative;display:flex;flex-direction:column;min-height:0;width:var(--rkx-w,380px);flex-shrink:0;border-left:1px solid var(--ui-stroke-tertiary);background:var(--ui-bg-editor);color:var(--ui-text-primary);font-size:13px;font-variant-numeric:tabular-nums;
  --rkx-text:calc(var(--conversation-text-base-size,.875rem)*var(--chat-text-scale,1));--rkx-lh:var(--dt-line-height,1.55);
  --composer-fill:color-mix(in srgb,var(--dt-card,var(--ui-bg-elevated)) 88%,transparent);--rkx-hover:var(--chrome-action-hover,var(--ui-control-hover-background))}
.rk-split[data-narrow="true"] .rkx{width:auto;max-height:64%;border-left:0;border-top:1px solid var(--ui-stroke-tertiary)}
.rk-split[data-narrow="true"] .rkx[data-sheet="closed"] .rkx-log{display:none}
/* In Tailwind's base layer: unlayered, this reset beat core's utility classes and flattened
   the SDK parts (the primary send lost its filled circle, the model pill its padding). */
@layer base{.rkx button{font:inherit;color:inherit;background:none;border:0;padding:0;cursor:pointer}}
.rkx button:focus-visible,.rkx textarea:focus-visible{outline:2px solid var(--ui-accent);outline-offset:1px;border-radius:6px}
.rkx-resize{position:absolute;left:-4px;top:0;bottom:0;width:7px;cursor:col-resize;z-index:6;touch-action:none}
.rkx-resize::after{content:'';position:absolute;left:3px;top:0;bottom:0;width:1.5px;background:var(--ui-accent);opacity:0;transition:opacity .12s}
.rkx-resize:hover::after,.rkx-resize[data-drag="true"]::after{opacity:1}
.rk-split[data-narrow="true"] .rkx-resize{display:none}
.rkx-head{display:flex;align-items:center;gap:2px;height:40px;padding:0 6px 0 14px;flex-shrink:0;border-bottom:1px solid var(--ui-stroke-tertiary)}
.rkx-title{font-size:13px;font-weight:600;white-space:nowrap}
.rkx-model{margin-left:8px;font-size:11.5px;color:var(--ui-text-quaternary);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;min-width:0}
.rkx-sp{flex:1}
.rkx-mp{position:static;min-width:0;margin-left:6px}
.rkx-mbtn{display:inline-flex!important;align-items:center;gap:4px;max-width:100%;height:24px;padding:0 6px!important;border-radius:6px;font-size:11.5px!important;color:var(--ui-text-tertiary)!important;white-space:nowrap}
.rkx-mbtn span{overflow:hidden;text-overflow:ellipsis;min-width:0}
.rkx-mbtn:hover:not([disabled]),.rkx-mbtn[aria-expanded="true"]{background:var(--rkx-hover)!important;color:var(--ui-text-primary)!important}
.rkx-mbtn[disabled]{opacity:.5;cursor:default!important}
.rkx-mpill{display:inline-flex;align-items:center;max-width:58%}
.rkx-mpill .codicon{opacity:.5;flex-shrink:0}
.rkx-tagchip{flex-shrink:0;padding:0 4px;border-radius:4px;font-size:9.5px;letter-spacing:.04em;text-transform:uppercase;background:var(--ui-bg-quaternary);color:var(--ui-text-tertiary)}
.rkx-skel-row{display:block;height:12px;width:100%;border-radius:4px;background:var(--ui-bg-tertiary)}
.rkx-menu{position:absolute;bottom:64px;left:8px;right:8px;z-index:20;display:flex;flex-direction:column;max-height:min(420px,70%);border-radius:10px;background:var(--ui-bg-elevated);border:1px solid var(--stroke-nous,var(--ui-stroke-tertiary));box-shadow:var(--shadow-nous,0 10px 30px rgba(0,0,0,.35));animation:rkx-in .12s ease-out both;overflow:hidden}
.rkx-q{margin:6px;height:28px;padding:0 9px;border-radius:7px;border:1px solid var(--ui-stroke-tertiary);background:var(--dt-input,var(--ui-bg-editor));color:var(--ui-text-primary);font:inherit;font-size:12px;outline:none}
.rkx-q:focus{border-color:var(--ui-accent)}
.rkx-mlist{overflow-y:auto;padding:0 4px 4px}
.rkx-mhead{padding:8px 8px 3px;font-size:10.5px;letter-spacing:.06em;text-transform:uppercase;color:var(--ui-text-quaternary)}
.rkx-mrow{display:flex!important;align-items:center;gap:8px;width:100%;padding:5px 8px!important;border-radius:6px;text-align:left;font-size:12.5px!important}
.rkx-mrow:hover,.rkx-mrow[aria-selected="true"]{background:var(--ui-row-hover-background,var(--rkx-hover))!important}
.rkx-mrow span{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;min-width:0}
.rkx-mrow em{font-style:normal;font-size:11px;color:var(--ui-text-quaternary);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;min-width:0;flex:1}
.rkx-mrow .codicon{margin-left:auto;color:var(--ui-accent)}
.rkx-mnote{padding:10px 8px;font-size:12px;color:var(--ui-text-tertiary);display:flex;align-items:center;gap:6px}
.rkx-ib{position:relative;width:26px;height:26px;flex-shrink:0;display:grid!important;place-items:center;border-radius:6px;color:var(--ui-text-tertiary)!important;transition:background-color .1s}
.rkx-ib:hover:not([disabled]){background:var(--rkx-hover)!important;color:var(--ui-text-primary)!important;transition:none}
.rkx-ib[disabled]{opacity:.35;cursor:default!important}
.rkx-ib[aria-pressed="true"]{color:var(--ui-accent)!important}
.rkx-unread{position:absolute;top:4px;right:4px;width:6px;height:6px;border-radius:50%;background:var(--ui-accent);box-shadow:0 0 6px var(--ui-accent)}
.rkx-strip{position:relative;width:40px;flex-shrink:0;display:flex;flex-direction:column;align-items:center;gap:4px;padding-top:7px;border-left:1px solid var(--ui-stroke-tertiary);background:var(--ui-bg-editor)}
.rk-split[data-narrow="true"] .rkx-strip{width:auto;flex-direction:row;padding:6px 10px;border-left:0;border-top:1px solid var(--ui-stroke-tertiary)}
.rkx-strip span{writing-mode:vertical-rl;font-size:11px;color:var(--ui-text-quaternary);margin-top:6px;letter-spacing:.04em}
.rk-split[data-narrow="true"] .rkx-strip span{writing-mode:horizontal-tb;margin:0 0 0 6px}

.rkx-log{position:relative;flex:1;min-height:0;overflow-y:auto;overflow-anchor:none;padding:14px 16px 6px;display:flex;flex-direction:column;gap:14px;scrollbar-gutter:stable}
.rkx-u{display:flex;flex-direction:column;gap:6px;padding:8px 12px;border-radius:12px;border:1px solid var(--ui-stroke-tertiary);background:var(--dt-user-bubble,var(--ui-bg-tertiary));font-size:var(--rkx-text);line-height:var(--rkx-lh);white-space:pre-wrap;overflow-wrap:anywhere;animation:rkx-in .16s ease-out both}
.rkx-a{display:flex;flex-direction:column;gap:8px;min-width:0;font-size:var(--rkx-text);line-height:var(--rkx-lh);overflow-wrap:anywhere;--conversation-text-font-size:var(--rkx-text)}
.rkx-a>.rkx-md{animation:rkx-in .18s ease-out both}
.rkx-plain{white-space:pre-wrap}
.rkx-tag{align-self:flex-start;display:inline-flex;align-items:center;gap:6px;height:20px;padding:0 7px 0 5px;border-radius:6px;font-size:11px;line-height:1;color:var(--ui-text-tertiary);background:color-mix(in srgb,var(--ui-accent) 9%,transparent);white-space:nowrap}
.rkx-glyph{display:grid;grid-template-columns:repeat(4,3px);gap:1.5px}
.rkx-glyph i{width:3px;height:3px;border-radius:.5px;background:var(--ui-stroke-secondary)}
.rkx-glyph i[data-on="true"]{background:var(--ui-accent)}

.rkx-act{display:flex;flex-direction:column;border-radius:10px;padding:3px;background:color-mix(in srgb,var(--ui-text-primary) 3%,transparent);font-size:12px;line-height:1.35}
.rkx-sumrow{display:flex;align-items:center;gap:6px}
.rkx-sumrow>.rkx-play{margin-right:5px;flex-shrink:0}
.rkx-sum{display:flex!important;align-items:center;gap:8px;flex:1;min-width:0;padding:5px 8px!important;border-radius:7px;text-align:left;color:var(--ui-text-secondary)!important}
.rkx-sum:hover{background:var(--rkx-hover)!important;color:var(--ui-text-primary)!important}
.rkx-sum .rkx-chev{margin-left:auto;color:var(--ui-text-quaternary);transition:transform .15s}
.rkx-sum[aria-expanded="true"] .rkx-chev{transform:rotate(90deg)}
.rkx-it{display:grid;grid-template-columns:14px minmax(0,1fr) auto;align-items:center;gap:8px;min-height:24px;padding:3px 8px;border-radius:7px;color:var(--ui-text-secondary);animation:rkx-in .14s ease-out both}
.rkx-it[data-lights="true"]{cursor:default}
.rkx-it[data-lights="true"]:hover{background:var(--rkx-hover);color:var(--ui-text-primary)}
.rkx-it b{font-weight:560;color:var(--ui-text-primary)}
.rkx-it .rkx-t{min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.rkx-it .rkx-ctxt{color:var(--ui-text-quaternary);margin-left:6px}
.rkx-pip{justify-self:center;width:6px;height:6px;border-radius:2px;background:var(--ui-accent)}
.rkx-pip[data-k="undo"],.rkx-pip[data-k="look"]{background:var(--ui-text-quaternary)}
.rkx-pip[data-k="tool"]{background:none;width:auto;height:auto;color:var(--ui-text-quaternary)}
.rkx-more{align-self:flex-start;padding:2px 8px 3px 30px!important;font-size:11.5px!important;color:var(--ui-text-quaternary)!important}
.rkx-more:hover{color:var(--ui-text-secondary)!important}
.rkx-rend{display:flex;align-items:center;gap:8px}
.rkx-rend .rk-leds{display:flex;gap:3px}.rkx-rend .rk-led{width:6px;height:6px}
.rkx-hash{font-family:var(--dt-font-mono,ui-monospace,monospace);font-size:11px;color:var(--ui-text-tertiary)}
.rkx-play{width:22px;height:22px;border-radius:50%!important;display:grid!important;place-items:center;background:var(--ui-accent)!important;color:var(--dt-primary-foreground,var(--ui-bg-editor))!important}
.rkx-play svg{width:9px;height:9px;fill:currentColor}
.rkx-play[disabled]{background:var(--ui-bg-quaternary)!important;color:var(--ui-text-quaternary)!important;cursor:default!important}

.rkx-foot{display:flex;align-items:center;gap:12px;min-height:20px;font-size:11.5px;color:var(--ui-text-quaternary)}
.rkx-link{display:inline-flex!important;align-items:center;gap:5px;padding:2px 6px!important;margin:-2px -6px!important;border-radius:5px;color:var(--ui-text-tertiary)!important}
.rkx-link:hover{background:var(--rkx-hover)!important;color:var(--ui-text-primary)!important}
.rkx-note{display:flex;align-items:center;gap:8px;padding:7px 10px;border-radius:9px;font-size:12px;line-height:1.4;background:color-mix(in srgb,var(--ui-red) 9%,transparent);color:var(--ui-text-secondary);animation:rkx-in .16s ease-out both}
.rkx-note[data-tone="ask"]{background:color-mix(in srgb,var(--ui-accent) 10%,transparent)}
.rkx-note[data-tone="quiet"]{background:none;padding:0 2px;color:var(--ui-text-quaternary)}
.rkx-note .rkx-link{margin-left:auto!important;flex-shrink:0}
.rkx-hello{margin-top:auto;display:flex;flex-direction:column;gap:8px;padding:6px 2px 2px}
.rkx-hello h3{margin:0;font-size:15px;font-weight:600;letter-spacing:-.005em}
.rkx-hello p{margin:0;font-size:12.5px;line-height:1.5;color:var(--ui-text-tertiary)}
.rkx-start{display:flex;flex-direction:column;gap:1px;margin:4px -8px 0}
.rkx-start button{display:flex!important;align-items:center;gap:10px;padding:7px 8px!important;border-radius:8px;text-align:left;font-size:12.5px!important;color:var(--ui-text-secondary)!important}
.rkx-start button:hover{background:var(--ui-row-hover-background,var(--rkx-hover))!important;color:var(--ui-text-primary)!important}
.rkx-start button .codicon{color:var(--ui-text-quaternary)}
.rkx-jump{position:sticky;bottom:4px;align-self:center;display:inline-flex!important;align-items:center;gap:5px;height:24px;padding:0 10px!important;border-radius:999px;font-size:11.5px!important;background:var(--ui-bg-elevated)!important;border:1px solid var(--ui-stroke-secondary)!important;box-shadow:var(--shadow-nous,none);animation:rkx-bounce .28s ease-out both;z-index:2}

.rkx-comp{flex-shrink:0;display:flex;flex-direction:column;gap:6px;padding:4px 12px 12px}
.rkx-status{display:flex;align-items:center;gap:7px;min-height:18px;padding:0 6px;font-size:11.5px;color:var(--ui-text-tertiary);animation:rkx-in .14s ease-out both}
.rkx-status b{font-weight:500;color:var(--ui-text-secondary);min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.rkx-status .rkx-el{margin-left:auto;color:var(--ui-text-quaternary)}
.rkx-spin{width:10px;height:10px;flex-shrink:0;border-radius:50%;border:1.5px solid var(--ui-stroke-secondary);border-top-color:var(--ui-accent);animation:rk-spin .7s linear infinite}
.rkx-status [role="status"],.rkx-status>span:first-child{color:var(--ui-accent)}
.rkx-pills{display:flex;flex-wrap:wrap;gap:6px}
.rkx-pill{display:inline-flex!important;align-items:center;height:24px;padding:0 10px!important;border-radius:999px;font-size:12px!important;white-space:nowrap;color:var(--ui-text-secondary)!important;background:var(--composer-fill)!important;border:1px solid color-mix(in srgb,var(--ui-stroke-secondary) 65%,transparent)!important;animation:rkx-in .16s ease-out both}
.rkx-pill:hover{background:var(--rkx-hover)!important;color:var(--ui-text-primary)!important}
.rkx-surface{position:relative;isolation:isolate;display:flex;flex-direction:column;gap:2px;border-radius:16px;padding:6px 6px 6px 8px}
.rkx-surface[data-fallback="true"]{border:1px solid color-mix(in srgb,var(--dt-composer-ring,var(--ui-accent)) 18%,var(--dt-input,var(--ui-stroke-tertiary)));background:var(--composer-fill)}
.rkx-surface[data-disabled="true"]{opacity:.6}
.rkx-row{display:flex;align-items:center;gap:4px;min-width:0}
.rkx-row .rkx-ctx{min-width:0;flex-shrink:1}
.rkx-row .rkx-ctx>span:not(.rkx-x){overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:0}
.rkx-ta{flex:1;min-width:0;display:block;resize:none;border:0;outline:none!important;background:transparent;color:var(--ui-text-primary);font:inherit;font-size:var(--rkx-text);line-height:var(--rkx-lh);padding:3px 4px;min-height:26px;max-height:150px;overflow-y:auto}
.rkx-ta::placeholder{color:var(--ui-text-tertiary)}
.rkx-send{display:grid!important;place-items:center;flex-shrink:0;margin-bottom:1px}
.rkx-send[data-fallback="true"]{width:26px;height:26px;border-radius:50%;background:var(--ui-text-primary)!important;color:var(--ui-bg-editor)!important}
.rkx-send[data-fallback="true"][disabled]{opacity:.3;cursor:default!important}
.rkx-ctx{align-self:flex-start;display:inline-flex!important;align-items:center;gap:6px;height:22px;padding:0 8px 0 6px!important;border-radius:7px;font-size:11.5px!important;color:var(--ui-text-secondary)!important;background:color-mix(in srgb,var(--ui-accent) 9%,transparent)!important}
.rkx-ctx:hover{background:color-mix(in srgb,var(--ui-accent) 15%,transparent)!important}
.rkx-ctx[data-off="true"]{background:none!important;color:var(--ui-text-quaternary)!important}
.rkx-ctx[data-off="true"] .rkx-glyph i[data-on="true"]{background:var(--ui-stroke-secondary)}
.rkx-ctx .rkx-x{color:var(--ui-text-quaternary);font-size:10px!important}
@keyframes rkx-in{from{opacity:0;transform:translateY(3px)}}
@keyframes rkx-bounce{0%{opacity:0;transform:translateY(7px)}65%{opacity:1;transform:translateY(-3px)}100%{transform:none}}
@media (prefers-reduced-motion:reduce){.rkx *{animation:none!important;transition:none!important}}
`

const CHAT_KEYS = { session: 'chat.session', mode: 'chat.mode', width: 'chat.width', context: 'chat.context', model: 'chat.model' }
const CHAT_W = { min: 320, def: 380, max: 560 }
const NARROW_PX = 900
const LIVE_SHOWN = 4

// Feature-detected SDK parts: the page must render on any desktop build.
const SDK_MD = typeof sdk.MessageTextContent === 'function' ? sdk.MessageTextContent : null
const SDK_RING = typeof sdk.composerSurfaceRing === 'string' ? sdk.composerSurfaceRing : null
const SDK_BACKING = typeof sdk.composerInputBacking === 'string' ? sdk.composerInputBacking : null
const SDK_PRIMARY = typeof sdk.PRIMARY_ICON_BTN === 'string' ? sdk.PRIMARY_ICON_BTN : null

class Safe extends Component {
  constructor(p) { super(p); this.state = { err: false } }
  static getDerivedStateFromError() { return { err: true } }
  componentDidCatch(e) { console.warn('[rookery] chat part fell back', e) }
  render() { return this.state.err ? this.props.fallback : this.props.children }
}
const Ico = ({ n, s = '0.875rem' }) => sdk.Codicon
  ? h(sdk.Codicon, { name: n, size: s, 'aria-hidden': true })
  : h('span', { className: `codicon codicon-${n}`, 'aria-hidden': true, style: { fontSize: s } })
const Tipped = ({ label, children }) => (sdk.Tip ? h(sdk.Tip, { label, content: label }, children) : children)
const Spin = () => (sdk.GlyphSpinner ? h(Safe, { fallback: h('i', { className: 'rkx-spin' }) }, h(sdk.GlyphSpinner, null)) : h('i', { className: 'rkx-spin' }))
function IB({ icon, label, onClick, disabled, pressed, children }) {
  return h(Tipped, { label }, h('button', { type: 'button', className: 'rkx-ib', 'aria-label': label, title: sdk.Tip ? undefined : label, onClick, disabled, 'aria-pressed': pressed }, h(Ico, { n: icon }), children))
}
function Md({ text }) {
  const plain = h('div', { className: 'rkx-plain' }, text)
  return h('div', { className: 'rkx-md' }, SDK_MD ? h(Safe, { fallback: plain }, h(SDK_MD, { text })) : plain)
}
function useAtom(a, fallback) {
  const sub = useCallback(fn => (a?.listen ? a.listen(fn) : a?.subscribe ? a.subscribe(fn) : () => {}), [a])
  const get = useCallback(() => (a?.get ? a.get() : fallback), [a])
  return useSyncExternalStore(sub, get, get)
}
const GridGlyph = () => h('span', { className: 'rkx-glyph', 'aria-hidden': true }, 'x.x.x..x'.split('').map((c, i) => h('i', { key: i, 'data-on': c === 'x' })))

// Words. Receipts say what changed, built from the engine's own diff.
const trackLabel = id => (/^\d/.test(id) ? id : String(id).replace(/_/g, ' ').replace(/^\w/, c => c.toUpperCase()))
const plural = (n, w) => `${n} ${w}${n === 1 ? '' : 's'}`
const hits = s => Array.from(String(s || '')).filter(isHit).length
const sourceName = s => String(s || '').replace(/^factory:/, '').replace(/^.*[\\/]/, '').replace(/\.(wav|vst3)$/i, '').replace(/_/g, ' ')
const fmtPan = v => (Math.abs(v) < 0.01 ? 'C' : `${Math.round(Math.abs(v) * 100)}${v < 0 ? 'L' : 'R'}`)
function describeDiff(d) {
  const who = d.track === 'master' ? 'Master' : d.track ? trackLabel(d.track) : null
  switch (d.field) {
    case 'steps': {
      const from = String(d.from || ''), to = String(d.to || '')
      if (!hits(from)) return { who, what: plural(hits(to), 'hit') }
      let add = 0, rem = 0
      for (let i = 0; i < Math.max(from.length, to.length); i++) { const a = isHit(from[i]), b = isHit(to[i]); if (b && !a) add++; if (a && !b) rem++ }
      if (add && rem) return { who, what: `+${add} −${rem} hits` }
      if (add) return { who, what: `${plural(add, 'hit')} added` }
      if (rem) return { who, what: `${plural(rem, 'hit')} removed` }
      return { who, what: 'pattern rewritten' }
    }
    case 'velocity': return { who, what: `velocity on ${plural((d.steps || []).length || 0, 'step')}` }
    case 'track': return { who: null, what: `${d.action === 'remove' ? 'Removed' : 'Added'} `, strong: who }
    case 'gain_db': return { who, what: `gain ${fmtDb(+d.from || 0)} → ${fmtDb(+d.to || 0)}` }
    case 'pan': return { who, what: `pan ${fmtPan(+d.from || 0)} → ${fmtPan(+d.to || 0)}` }
    case 'mute': return { who: null, what: d.to ? 'Muted ' : 'Unmuted ', strong: who }
    case 'solo': return { who: null, what: d.to ? 'Soloed ' : 'Unsoloed ', strong: who }
    case 'pitch': return { who, what: `pitch ${d.from ?? 0} → ${d.to} st` }
    case 'source': return { who, what: `sound → ${sourceName(d.to)}` }
    case 'fx': return { who, what: (d.to || []).length ? (d.to || []).map(fxName).join(' → ') : 'chain cleared' }
    case 'bpm': return { who: 'Tempo', what: `${d.from} → ${d.to} BPM` }
    case 'bars': return { who: 'Length', what: `${d.from} → ${plural(d.to, 'bar')}` }
    case 'swing': return { who: 'Swing', what: `${swingPct(d.from)}% → ${swingPct(d.to)}%` }
    case 'arrangement': return { who: 'Arrangement', what: !d.to ? 'removed' : d.to.sections.map(section => `${section.id}×${section.repeat}`).join(', ') }
    case 'flock': {
      const birdId = d.bird || d.to?.bird || d.from?.bird
      const bird = birdId ? (FLOCK_BIRD_NAMES.get(birdId) || birdId.replace(/_/g, ' ')) : null
      if (d.change === 'template' || d.change === 'perch') return { who: 'Flock', what: `${bird || 'Bird'} ${d.to?.bird ? 'perched' : 'unperched'}` }
      if (d.change === 'unperch') return { who: 'Flock', what: `${bird || 'Bird'} unperched` }
      if (d.change === 'song') return { who: 'Flock', what: `${bird || 'Bird'} song ${d.to?.song || d.to}` }
      if (d.change === 'mute') return { who: 'Flock', what: `${bird || 'Bird'} ${d.to?.mute ?? d.to ? 'muted' : 'unmuted'}` }
      if (d.change === 'solo') return { who: 'Flock', what: `${bird || 'Bird'} ${d.to?.solo ?? d.to ? 'soloed' : 'unsoloed'}` }
      if (d.change === 'gain_db' || d.change === 'pan') {
        return { who: 'Flock', what: `${bird || 'Bird'} ${d.change === 'gain_db' ? fmtDb(d.to?.gain_db ?? d.to) : `pan ${fmtPan(d.to?.pan ?? d.to)}`}` }
      }
      if (d.change === 'mix') {
        const from = d.from || {}, to = d.to || {}
        const detail = [
          (from.gain_db ?? 0) !== (to.gain_db ?? 0) && fmtDb(to.gain_db || 0),
          (from.pan ?? 0) !== (to.pan ?? 0) && `pan ${fmtPan(to.pan || 0).replace(/(\d+)([LR])/, '$2$1')}`
        ].filter(Boolean).join(', ')
        return { who: 'Flock', what: `${bird || 'Bird'} ${detail}`.trim() }
      }
      if (d.change === 'harmony') {
        const to = d.to || {}
        if (to.key || to.scale) return { who: 'Flock', what: `key ${to.key || d.from?.key || ''}${to.scale ? ` ${to.scale}` : ''}`.trim() }
        if (to.progression) return { who: 'Flock', what: `progression ${to.progression.join(' · ')}` }
        return { who: 'Flock', what: 'harmony changed' }
      }
      if (d.change === 'weather') return { who: 'Flock', what: `weather ${String(d.to || 'clear').replace(/^./, c => c.toUpperCase())}` }
      return { who: 'Flock', what: String(d.change || 'changed').replace(/_/g, ' ') }
    }
    default: return { who, what: d.field ? `${d.field} changed` : 'changed' }
  }
}
function Receipt({ item }) {
  const diff = item.diff || []
  if (!diff.length) return h('span', { className: 'rkx-t' }, item.tool === 'rookery_new' ? h(Fragment, null, 'New beat ', h('b', null, item.name)) : 'Project updated')
  if (item.tool === 'rookery_flock' && diff.some(d => d.field === 'flock' && (d.change === 'mix' || ['gain_db', 'pan'].includes(d.change)))) {
    const mix = diff.filter(d => d.field === 'flock' && (d.change === 'mix' || ['gain_db', 'pan'].includes(d.change)))
    const birdId = mix[0].bird || mix[0].to?.bird
    const bird = FLOCK_BIRD_NAMES.get(birdId) || birdId || 'Bird'
    const combined = mix.find(d => d.change === 'mix')
    const gain = mix.find(d => d.change === 'gain_db'), pan = mix.find(d => d.change === 'pan')
    const from = combined?.from || {}, to = combined?.to || {}
    const detail = [
      gain ? fmtDb(gain.to?.gain_db ?? gain.to) : combined && (from.gain_db ?? 0) !== (to.gain_db ?? 0) && fmtDb(to.gain_db || 0),
      pan ? `pan ${fmtPan(pan.to?.pan ?? pan.to).replace(/(\d+)([LR])/, '$2$1')}` : combined && (from.pan ?? 0) !== (to.pan ?? 0) && `pan ${fmtPan(to.pan || 0).replace(/(\d+)([LR])/, '$2$1')}`
    ].filter(Boolean).join(', ')
    return h('span', { className: 'rkx-t' }, h('b', null, 'Flock'), ' · ', `${bird} ${detail}`)
  }
  const d = describeDiff(diff[0])
  return h('span', { className: 'rkx-t' },
    item.tool === 'rookery_apply' && h(Fragment, null, h('b', null, 'Batch'), ' · ', `${diff.length} edits · `),
    item.tool === 'rookery_undo' && 'Undid: ',
    d.who && h('b', null, d.who), d.who && ' · ', d.what, d.strong && h('b', null, d.strong),
    diff.length > 1 && h('span', { className: 'rkx-ctxt' }, `+${diff.length - 1} more`))
}

const TOOL_LIVE = { rookery_new: 'Starting a beat', rookery_steps: 'Writing steps', rookery_track: 'Setting up tracks', rookery_mix: 'Mixing', rookery_render: 'Rendering and checking', rookery_state: 'Reading the beat', rookery_undo: 'Undoing', rookery_kits: 'Browsing the kits', rookery_flock: 'Moving the flock', rookery_apply: 'Applying a batch' }
const TOOL_PAST = { rookery_new: 'Started a beat', rookery_steps: 'Wrote steps', rookery_track: 'Changed tracks', rookery_mix: 'Changed the mix', rookery_render: 'Rendered', rookery_state: 'Read the beat', rookery_undo: 'Undid an edit', rookery_kits: 'Browsed the kits', rookery_flock: 'Moved the flock', rookery_apply: 'Applied a batch' }
const toolCtx = c => (typeof c === 'string' ? c : c && typeof c === 'object' ? Object.values(c).filter(v => typeof v === 'string').join(' ') : '')
// A replayed tool row only has the call's short arg preview: read the few args that matter.
const argOf = (ctx, key) => { const m = new RegExp(`["']?${key}["']?\\s*[:=]\\s*["']?([\\w .-]+)`).exec(ctx || ''); return m ? m[1].trim() : null }
function pastLabel(item) {
  const c = item.context || '', track = argOf(c, 'track') || argOf(c, 'id')
  switch (item.name) {
    case 'rookery_new': return { what: 'New beat ', strong: argOf(c, 'name') || '' }
    case 'rookery_track': {
      const a = argOf(c, 'action')
      return track ? { what: a === 'remove' ? 'Removed ' : a === 'add' ? 'Added ' : 'Changed ', strong: trackLabel(track) } : { what: TOOL_PAST.rookery_track }
    }
    case 'rookery_steps': return track ? { who: trackLabel(track), what: 'steps written' } : { what: TOOL_PAST.rookery_steps }
    default: return { what: TOOL_PAST[item.name] || `Used ${String(item.name || 'a tool')}` }
  }
}
function statusPhrase(act) {
  if (!act) return ''
  if (act.phase === 'writing') return 'Writing'
  if (act.phase === 'tool') {
    const live = TOOL_LIVE[act.tool]
    const m = /track["'=:\s]+["']?([\w-]+)/.exec(toolCtx(act.detail))
    if (act.tool === 'rookery_steps' && m) return `Writing the ${trackLabel(m[1]).toLowerCase()}`
    return live || `Using ${String(act.tool || 'a tool').replace(/_/g, ' ')}`
  }
  return 'Thinking'
}
function blockSummary(items) {
  const edits = items.filter(i => i.k === 'edit'), renders = items.filter(i => i.k === 'render')
  const tools = [...new Set(items.filter(i => i.k === 'tool').map(i => i.name).filter(Boolean))], past = items.filter(i => i.k === 'past')
  const added = edits.reduce((n, e) => n + (e.diff || []).filter(d => d.field === 'track' && d.action !== 'remove').length, 0) +
    past.filter(i => i.name === 'rookery_track' && argOf(i.context, 'action') === 'add').length
  const r = renders[renders.length - 1]
  const checks = r?.report ? Object.values(r.report).filter(c => c && typeof c === 'object') : []
  return [
    added > 1 && `Built ${added} tracks`,
    edits.length && plural(edits.length, 'edit'),
    r && (checks.length ? `${checks.filter(c => c.pass).length}/${checks.length} checks` : 'Rendered'),
    !edits.length && items.some(i => i.k === 'look' && i.name === 'rookery_state') && 'Read the beat',
    tools.length && `Used ${tools.slice(0, 2).join(', ')}${tools.length > 2 ? '…' : ''}`,
    past.length && !edits.length && plural(past.length, 'step')
  ].filter(Boolean).join(' · ') || 'Worked'
}

// "[Rookery: name]" travels with the prompt so Hermes knows which beat; it's drawn as a chip, never as text.
const CTX_RE = /^\[Rookery: ([^\]\n]+)\]\n?/
const splitHeader = text => { const m = CTX_RE.exec(text || ''); return m ? { ctx: m[1], body: text.slice(m[0].length) } : { ctx: null, body: text || '' } }

let chatUid = 0
const nid = () => `c${Date.now().toString(36)}${++chatUid}`
function fromHistory(messages) {
  const out = []
  let cur = null
  const asst = () => { if (!cur) out.push(cur = { id: nid(), role: 'assistant', parts: [], status: 'done', past: true }); return cur }
  const textOf = m => {
    const c = m.text ?? m.content
    if (typeof c === 'string') return c
    if (Array.isArray(c)) return c.map(p => (typeof p === 'string' ? p : p?.text || '')).join('')
    return ''
  }
  for (const m of messages || []) {
    if (m.role === 'user') {
      const { ctx, body } = splitHeader(textOf(m))
      if (!body.trim()) continue
      cur = null
      out.push({ id: nid(), role: 'user', text: body, ctx })
    }
    else if (m.role === 'assistant') { const t = textOf(m).trim(); if (t) asst().parts.push({ k: 'text', text: t }) }
    else if (m.role === 'tool') {
      const a = asst()
      let last = a.parts[a.parts.length - 1]
      if (!last || last.k !== 'act') a.parts.push(last = { k: 'act', items: [] })
      const name = String(m.name || m.tool_name || m.tool || m.function?.name || 'tool')
      last.items.push({ k: name.startsWith('rookery_') ? 'past' : 'tool', id: nid(), name, context: toolCtx(m.context ?? m.args), done: true })
    }
  }
  return out
}

function useChat(ctx) {
  const store = ctx.storage
  const [turns, setTurns] = useState([])
  const [busy, setBusy] = useState(false)
  const [act, setAct] = useState(null)
  const [unread, setUnread] = useState(false)
  const [stored, setStored] = useState(() => store?.get(CHAT_KEYS.session, null)?.stored || null)
  const [model, setModelState] = useState(() => store?.get(CHAT_KEYS.model, null))
  const sid = useRef(null), storedRef = useRef(stored), open = useRef(null), pending = useRef(''), raf = useRef(0), creating = useRef(null), modelRef = useRef(model)
  const gateway = useAtom(host.state?.gateway, 'open')

  // Capture the id now: React runs updaters later, after finish() may have cleared open.current.
  const patchOpen = fn => { const id = open.current; if (id) setTurns(ts => ts.map(t => (t.id === id ? fn(t) : t))) }
  const pushPart = (t, part) => ({ ...t, parts: [...t.parts, part] })
  const addItem = item => patchOpen(t => {
    const last = t.parts[t.parts.length - 1]
    return last?.k === 'act' ? { ...t, parts: [...t.parts.slice(0, -1), { ...last, items: [...last.items, item] }] } : pushPart(t, { k: 'act', items: [item] })
  })
  const flush = () => {
    raf.current = 0
    const chunk = pending.current
    if (!chunk) return
    pending.current = ''
    patchOpen(t => {
      const last = t.parts[t.parts.length - 1]
      return last?.k === 'text' && !last.sealed ? { ...t, parts: [...t.parts.slice(0, -1), { ...last, text: last.text + chunk }] } : pushPart(t, { k: 'text', text: chunk })
    })
  }
  const seal = () => { flush(); patchOpen(t => { const last = t.parts[t.parts.length - 1]; return last?.k === 'text' ? { ...t, parts: [...t.parts.slice(0, -1), { ...last, sealed: true }] } : t }) }
  const finish = (status, error) => {
    flush()
    if (!open.current) return
    patchOpen(t => ({ ...t, status, error, t1: Date.now() }))
    open.current = null
    setBusy(false); setAct(null); setUnread(true)
  }
  const openTurn = () => {
    if (open.current) return
    const id = nid()
    open.current = id
    setTurns(ts => [...ts, { id, role: 'assistant', parts: [], status: 'streaming', t0: Date.now() }])
    setBusy(true); setAct({ phase: 'thinking', t0: Date.now() })
  }
  const remember = (st) => { storedRef.current = st; setStored(st); st ? store?.set(CHAT_KEYS.session, { stored: st }) : store?.remove(CHAT_KEYS.session) }

  // Resume the stored session on mount: history repaints, the runtime id binds to this socket.
  const resume = async () => {
    const st = storedRef.current
    if (!st) return null
    const r = await host.request('session.resume', { session_id: st })
    sid.current = r?.session_id || null
    if (Array.isArray(r?.messages) && !open.current) setTurns(fromHistory(r.messages))
    return sid.current
  }
  const ensure = async () => {
    if (sid.current) return sid.current
    if (creating.current) return creating.current
    creating.current = (async () => {
      if (storedRef.current) { try { if (await resume()) return sid.current } catch { remember(null) } }
      const m = modelRef.current
      // No fixed title: the owner treats a title as the session's identity, so every "Rookery" create
      // resolved to the first Rookery session (old model, old history). Hermes auto-titles from the
      // first message instead, like its own chats. A fresh request_id per create too: the desktop
      // memoizes one per identical params, and a repeated id is answered with the same session.
      const request_id = globalThis.crypto?.randomUUID?.() || `rk-${Date.now()}-${Math.random().toString(36).slice(2)}`
      const r = await host.request('session.create', { request_id, source: 'desktop', ...(m?.model ? { model: m.model, ...(m.provider ? { provider: m.provider } : {}) } : {}) })
      sid.current = r?.session_id || null
      if (r?.stored_session_id) remember(r.stored_session_id)
      if (!sid.current) throw new Error('Hermes did not open a session')
      return sid.current
    })().finally(() => { creating.current = null })
    return creating.current
  }

  useEffect(() => {
    if (storedRef.current && gateway === 'open' && !sid.current) resume().catch(e => console.warn('[rookery] chat resume failed', e))
    if (gateway !== 'open' && open.current) finish('error', 'Lost the connection to Hermes.')
  }, [gateway])

  useEffect(() => {
    const ours = ev => ev && ev.session_id && ev.session_id === sid.current
    const on = (type, fn) => host.onEvent(type, ev => { if (ours(ev)) fn(ev.payload || {}, ev) })
    const offs = [
      on('message.start', () => openTurn()),
      on('message.delta', pl => {
        if (typeof pl.text !== 'string' || !pl.text) return
        openTurn()
        pending.current += pl.text
        setAct(a => (a?.phase === 'writing' ? a : { phase: 'writing', t0: a?.t0 || Date.now() }))
        if (!raf.current) raf.current = requestAnimationFrame(flush)
      }),
      on('reasoning.delta', () => setAct(a => (a && a.phase !== 'thinking' ? { ...a, phase: 'thinking' } : a))),
      on('thinking.delta', () => setAct(a => (a && a.phase !== 'thinking' ? { ...a, phase: 'thinking' } : a))),
      on('tool.start', pl => {
        openTurn(); seal()
        const name = String(pl.name || pl.tool_name || 'tool')
        setAct(a => ({ phase: 'tool', tool: name, detail: pl.context, t0: a?.t0 || Date.now() }))
        if (name === 'rookery_state' || name === 'rookery_kits') addItem({ k: 'look', id: pl.tool_id || nid(), name, done: false })
        else if (!name.startsWith('rookery_')) addItem({ k: 'tool', id: pl.tool_id || nid(), name, context: toolCtx(pl.context), done: false })
      }),
      on('tool.complete', pl => {
        const id = pl.tool_id
        patchOpen(t => ({ ...t, parts: t.parts.map(p => (p.k !== 'act' ? p : { ...p, items: p.items.map(i => (i.id === id ? { ...i, done: true } : i)) })) }))
        setAct(a => (a ? { ...a, phase: 'thinking' } : a))
      }),
      on('message.complete', pl => {
        flush()
        const text = typeof pl.text === 'string' ? pl.text.trim() : ''
        const status = pl.status === 'error' ? 'error' : /interrupt|cancel/i.test(pl.status || '') ? 'stopped' : 'done'
        if (status !== 'error' && text) patchOpen(t => (t.parts.some(p => p.k === 'text') ? t : pushPart(t, { k: 'text', text })))
        finish(status, status === 'error' ? text.replace(/^Error:\s*/, '') || 'The turn failed.' : null)
      }),
      ...['approval.request', 'clarify.request'].map(type => on(type, () => { openTurn(); addItem({ k: 'ask', id: nid(), kind: type.split('.')[0] }) })),
      // The engine's own events say exactly what changed; attach them to the open turn.
      host.onEvent(EV + 'project.updated', ({ payload: pl }) => {
        if (open.current && pl && pl.source === 'agent') addItem({ k: 'edit', id: nid(), name: pl.name, rev: pl.rev, tool: pl.tool, diff: pl.diff || [] })
      }),
      host.onEvent(EV + 'render.done', ({ payload: pl }) => {
        if (open.current && pl) addItem({ k: 'render', id: nid(), name: pl.name, rev: pl.rev, hash: pl.hash, report: pl.report })
      })
    ]
    return () => { offs.forEach(off => off && off()); cancelAnimationFrame(raf.current) }
  }, [])

  const send = async (text, context) => {
    const body = String(text || '').trim()
    if (!body || open.current) return false
    const userId = nid()
    setTurns(ts => [...ts, { id: userId, role: 'user', text: body, ctx: context || null }])
    openTurn()
    const full = (context ? `[Rookery: ${context}]\n` : '') + body
    const submit = async () => host.request('prompt.submit', { session_id: await ensure(), text: full })
    try {
      try { await submit() } catch (e) {
        if (!/4001|not found|unknown session|no such session/i.test(String(e?.message || e))) throw e
        sid.current = null // the runtime id went stale (gateway restart): resume or recreate once
        await submit()
      }
      return true
    } catch (e) {
      finish('error', String(e?.message || e) || 'Hermes didn’t take the message.')
      return false
    }
  }
  const stop = () => { if (sid.current) host.request('session.interrupt', { session_id: sid.current }).catch(() => {}) }
  const reset = () => { if (open.current) return; sid.current = null; remember(null); setTurns([]); setAct(null) }
  const markUndone = id => setTurns(ts => ts.map(t => (t.id === id ? { ...t, undone: true } : t)))
  // A session's model is fixed when it's created, so a new pick starts a fresh chat on it.
  const setModel = m => {
    if (open.current) return
    const cur = modelRef.current
    if ((cur?.model || null) === (m?.model || null) && (cur?.provider || null) === (m?.provider || null)) return // same pick: keep the chat
    modelRef.current = m; setModelState(m)
    m ? store?.set(CHAT_KEYS.model, m) : store?.remove(CHAT_KEYS.model)
    reset()
  }
  return { turns, busy, act, gateway, stored, unread, clearUnread: () => setUnread(false), send, stop, reset, ensure, markUndone, model, setModel }
}

export const EDIT_STARTERS = ['Make it dustier', 'Add a fill in bar 4', 'Gate the lead on alternate bars', 'Swing it harder', 'Half-time the drums', 'Give the 808 a slide', 'Open the hats up', 'Add a counter melody']
function suggestionsFor(view) {
  if (!view) return PROMPTS
  if (!view.render) return ['Render it and run the checks', 'Add a sample chord bed', 'Add a flute lead']
  const k = (view.rev || 0) % EDIT_STARTERS.length
  return [0, 1, 2].map(i => EDIT_STARTERS[(k + i * 2) % EDIT_STARTERS.length])
}

function ActBlock({ items, live, onLight, renderHash, canPlay, playing, onPlay, onAnswer }) {
  const [open, setOpen] = useState(false)
  const [showAll, setShowAll] = useState(false)
  const row = item => {
    if (item.k === 'edit') {
      return h('div', { key: item.id, className: 'rkx-it', 'data-lights': true, onMouseEnter: () => onLight(item) },
        h('i', { className: 'rkx-pip', 'data-k': item.tool === 'rookery_undo' ? 'undo' : 'edit' }), h(Receipt, { item }))
    }
    if (item.k === 'render') {
      const checks = item.report ? Object.values(item.report).filter(c => c && typeof c === 'object') : []
      const current = item.hash && item.hash === renderHash
      return h('div', { key: item.id, className: 'rkx-it' },
        h('i', { className: 'rkx-pip' }),
        h('span', { className: 'rkx-t rkx-rend' }, h('b', null, 'Rendered'),
          checks.length > 0 && h('span', { className: 'rk-leds', title: `${checks.filter(c => c.pass).length}/${checks.length} checks pass` }, checks.map((c, i) => h('i', { key: i, className: 'rk-led', 'data-s': c.pass ? 'pass' : 'fail' }))),
          h('span', { className: 'rkx-hash' }, shortHash(item.hash))),
        h(Tipped, { label: current ? (playing ? 'Stop' : 'Play this render') : 'A newer render replaced this one' },
          h('button', { type: 'button', className: 'rkx-play', disabled: !current || !canPlay, 'aria-label': playing && current ? 'Stop' : 'Play', onClick: onPlay }, playing && current ? Icon.stop() : Icon.play())))
    }
    if (item.k === 'ask') {
      return h('div', { key: item.id, className: 'rkx-note', 'data-tone': 'ask' }, h(Ico, { n: 'question' }),
        h('span', null, item.kind === 'approval' ? 'Hermes needs your OK to continue.' : 'Hermes has a question for you.'),
        h('button', { type: 'button', className: 'rkx-link', onClick: onAnswer }, 'Answer in chat', h(Ico, { n: 'arrow-right', s: '0.75rem' })))
    }
    const pip = item.done ? h('i', { className: 'rkx-pip', 'data-k': item.k === 'tool' ? 'tool' : item.k === 'past' ? 'edit' : 'look' }, item.k === 'tool' && h(Ico, { n: 'tools', s: '0.75rem' })) : h(Spin)
    if (item.k === 'past') {
      const d = pastLabel(item)
      return h('div', { key: item.id, className: 'rkx-it' }, pip, h('span', { className: 'rkx-t' }, d.who && h('b', null, d.who), d.who && ' · ', d.what, d.strong && h('b', null, d.strong)))
    }
    const label = item.k === 'tool' ? `Used ${item.name}` : TOOL_PAST[item.name] || item.name
    return h('div', { key: item.id, className: 'rkx-it' }, pip,
      h('span', { className: 'rkx-t' }, label, item.k === 'tool' && item.context && h('span', { className: 'rkx-ctxt' }, item.context)))
  }
  const asks = items.filter(i => i.k === 'ask')
  const rest = items.filter(i => i.k !== 'ask')
  if (live) {
    const hidden = showAll ? 0 : Math.max(0, rest.length - LIVE_SHOWN)
    return h(Fragment, null,
      rest.length > 0 && h('div', { className: 'rkx-act' },
        hidden > 0 && h('button', { type: 'button', className: 'rkx-more', onClick: () => setShowAll(true) }, `${hidden} earlier`),
        rest.slice(hidden).map(row)),
      asks.map(row))
  }
  const lastRender = [...rest].reverse().find(i => i.k === 'render')
  const playable = lastRender && lastRender.hash === renderHash && canPlay
  return h(Fragment, null,
    rest.length > 0 && h('div', { className: 'rkx-act' },
      h('div', { className: 'rkx-sumrow' },
        h('button', { type: 'button', className: 'rkx-sum', 'aria-expanded': open, onClick: () => setOpen(o => !o) },
          h(Ico, { n: rest.some(i => i.k === 'edit') ? 'symbol-event' : 'check', s: '0.8125rem' }), h('span', null, blockSummary(rest)), h('span', { className: 'rkx-chev' }, h(Ico, { n: 'chevron-right', s: '0.75rem' }))),
        playable && h(Tipped, { label: playing ? 'Stop' : 'Play the result' },
          h('button', { type: 'button', className: 'rkx-play', 'aria-label': playing ? 'Stop' : 'Play the result', onClick: onPlay }, playing ? Icon.stop() : Icon.play()))),
      open && rest.map(row)),
    asks.map(row))
}

function TurnView({ turn, last, view, chatProps }) {
  if (turn.role === 'user') {
    return h('div', { className: 'rkx-u' },
      turn.ctx && h('span', { className: 'rkx-tag' }, h(GridGlyph), turn.ctx),
      h('span', null, turn.text))
  }
  const live = turn.status === 'streaming'
  const edits = turn.parts.flatMap(p => (p.k === 'act' ? p.items.filter(i => i.k === 'edit') : []))
  const lastEdit = edits[edits.length - 1]
  const canUndo = !live && !turn.undone && lastEdit && view && view.project.name === lastEdit.name && view.rev === lastEdit.rev && edits.every(e => e.name === lastEdit.name)
  const secs = turn.t1 && turn.t0 ? Math.max(1, Math.round((turn.t1 - turn.t0) / 1000)) : null
  return h('div', { className: 'rkx-a' },
    turn.parts.map((p, i) => (p.k === 'text'
      ? h(Md, { key: i, text: p.text })
      : h(ActBlock, { key: i, items: p.items, live, ...chatProps }))),
    turn.status === 'error' && h('div', { className: 'rkx-note', role: 'alert' }, h(Ico, { n: 'error' }), h('span', null, turn.error || 'Something went wrong.'),
      last && chatProps.onRetry && h('button', { type: 'button', className: 'rkx-link', onClick: chatProps.onRetry }, 'Retry')),
    turn.status === 'stopped' && h('div', { className: 'rkx-note', 'data-tone': 'quiet' }, 'Stopped.'),
    !live && !turn.past && (canUndo || secs) && h('div', { className: 'rkx-foot' },
      secs && edits.length > 0 && h('span', null, `${plural(edits.length, 'edit')} in ${secs}s`),
      canUndo && h('button', { type: 'button', className: 'rkx-link', onClick: () => chatProps.onUndoTurn(turn, edits) }, h(Ico, { n: 'discard', s: '0.75rem' }), 'Undo turn'),
      turn.undone && h('span', null, 'Undone')))
}

function ChatStatus({ act }) {
  const [, tick] = useState(0)
  useEffect(() => { const t = setInterval(() => tick(n => n + 1), 1000); return () => clearInterval(t) }, [])
  const secs = act?.t0 ? Math.floor((Date.now() - act.t0) / 1000) : 0
  return h('div', { className: 'rkx-status', 'aria-live': 'polite' }, h(Spin), h('b', null, statusPhrase(act)), h('span', { className: 'rkx-el' }, `${secs}s`))
}

function ChatRail({ chat, view, width, narrow, sheet, onSheet, onWidth, onHide, onDock, canDock, onLight, canPlay, playing, onPlay, onUndoTurn }) {
  const [draft, setDraft] = useState('')
  const [useCtx, setUseCtx] = useState(true)
  const [below, setBelow] = useState(false)
  const log = useRef(null), ta = useRef(null), atBottom = useRef(true), lastSent = useRef('')
  const model = useAtom(host.state?.model, '')
  const offline = chat.gateway !== 'open'
  const project = view?.project
  const ctxName = useCtx && project ? project.name : null

  useLayoutEffect(() => {
    const el = log.current
    if (!el) return
    if (atBottom.current) el.scrollTop = el.scrollHeight
    else setBelow(true)
  }, [chat.turns])
  useEffect(() => { if (log.current) log.current.scrollTop = log.current.scrollHeight }, [])
  const onScroll = () => {
    const el = log.current
    atBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 48
    if (atBottom.current) setBelow(false)
  }
  const jump = () => { log.current?.scrollTo({ top: log.current.scrollHeight, behavior: 'smooth' }); atBottom.current = true; setBelow(false) }
  const grow = () => { const el = ta.current; if (!el) return; el.style.height = 'auto'; el.style.height = `${Math.min(150, el.scrollHeight)}px` }
  useLayoutEffect(grow, [draft])

  const send = async text => {
    const t = (text ?? draft).trim()
    if (!t || chat.busy || offline) return
    lastSent.current = t
    atBottom.current = true
    if (text == null) setDraft('')
    if (narrow) onSheet(true)
    await chat.send(t, ctxName)
  }
  const onKey = e => {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent?.isComposing) { e.preventDefault(); send() }
    else if (e.key === 'Escape' && chat.busy) { e.preventDefault(); chat.stop() }
  }
  const chatProps = { onLight, renderHash: view?.render?.hash, canPlay, playing, onPlay, onUndoTurn, onAnswer: () => chat.stored && host.openSession?.(chat.stored), onRetry: () => lastSent.current && send(lastSent.current) }
  const pills = !chat.busy && !draft && !offline && chat.turns.length > 0 ? suggestionsFor(view) : []
  const lastTurn = chat.turns[chat.turns.length - 1]

  // Resize from the rail's left edge.
  const onResize = e => {
    if (e.button !== 0) return
    e.preventDefault()
    const el = e.currentTarget, x0 = e.clientX, w0 = width
    el.setPointerCapture?.(e.pointerId); el.dataset.drag = 'true'
    const move = ev => onWidth(clamp(w0 + (x0 - ev.clientX), CHAT_W.min, CHAT_W.max), false)
    const up = () => { delete el.dataset.drag; el.removeEventListener('pointermove', move); el.removeEventListener('pointerup', up); el.removeEventListener('pointercancel', up); onWidth(null, true) }
    el.addEventListener('pointermove', move); el.addEventListener('pointerup', up); el.addEventListener('pointercancel', up)
  }

  const send_ = chat.busy
    ? h(Tipped, { label: 'Stop (Esc)' }, h('button', { type: 'button', className: cn2('rkx-send', SDK_PRIMARY), 'data-fallback': !SDK_PRIMARY, 'aria-label': 'Stop', onClick: chat.stop }, h(Ico, { n: 'debug-stop', s: '0.75rem' })))
    : h(Tipped, { label: 'Send (Enter)' }, h('button', { type: 'submit', className: cn2('rkx-send', SDK_PRIMARY), 'data-fallback': !SDK_PRIMARY, 'aria-label': 'Send', disabled: !draft.trim() || offline }, h(Ico, { n: 'arrow-up', s: '0.875rem' })))

  return h('aside', { className: 'rkx', style: { '--rkx-w': `${width}px` }, 'data-sheet': narrow ? (sheet ? 'open' : 'closed') : undefined, 'aria-label': 'Rookery chat' },
    h('div', { className: 'rkx-resize', onPointerDown: onResize, role: 'separator', 'aria-orientation': 'vertical', 'aria-label': 'Resize chat' }),
    h('header', { className: 'rkx-head' },
      h('span', { className: 'rkx-title' }, 'Chat'),
      h('span', { className: 'rkx-sp' }),
      h(IB, { icon: 'add', label: 'New chat', onClick: chat.reset, disabled: chat.busy || !chat.turns.length }),
      canDock && h(IB, { icon: 'split-horizontal', label: chat.stored ? 'Dock beside chat' : 'Dock beside chat (send a message first)', onClick: onDock, disabled: !chat.stored || chat.busy }),
      narrow
        ? h(IB, { icon: sheet ? 'chevron-down' : 'chevron-up', label: sheet ? 'Shrink chat' : 'Expand chat', onClick: () => onSheet(!sheet) })
        : h(IB, { icon: 'layout-sidebar-right-off', label: 'Hide chat', onClick: onHide })),
    h('div', { className: 'rkx-log', ref: log, onScroll, role: 'log', 'aria-live': 'polite', 'aria-busy': chat.busy },
      !chat.turns.length && h('div', { className: 'rkx-hello' },
        h('h3', null, project ? `What next for ${project.name}?` : 'Make a beat with Hermes'),
        h('p', null, project
          ? 'Ask for a change. Hermes edits the grid in front of you, renders it, and checks it. Hover any change it makes to see it on the pads.'
          : 'Describe a groove. Hermes builds it on the grid, renders it, and runs the six checks.'),
        h('div', { className: 'rkx-start' }, suggestionsFor(view).map(t => h('button', { key: t, type: 'button', onClick: () => send(t), disabled: offline }, h(Ico, { n: 'arrow-small-right' }), t)))),
      chat.turns.map(t => h(TurnView, { key: t.id, turn: t, last: t === lastTurn, view, chatProps })),
      below && h('button', { type: 'button', className: 'rkx-jump', onClick: jump }, h(Ico, { n: 'arrow-down', s: '0.75rem' }), 'New activity')),
    h('form', { className: 'rkx-comp', onSubmit: e => { e.preventDefault(); send() } },
      chat.busy ? h(ChatStatus, { act: chat.act }) : offline ? h('div', { className: 'rkx-status' }, h(Ico, { n: 'debug-disconnect', s: '0.75rem' }), h('b', null, 'Hermes is offline. The chat will reconnect.')) : null,
      pills.length > 0 && h('div', { className: 'rkx-pills' }, pills.map(t => h('button', { key: t, type: 'button', className: 'rkx-pill', onClick: () => send(t) }, t))),
      h('div', { className: cn2('rkx-surface', SDK_RING), 'data-fallback': !SDK_RING, 'data-disabled': offline, onClick: e => { if (e.target === e.currentTarget) ta.current?.focus() } },
        SDK_BACKING && h('div', { 'aria-hidden': true, className: SDK_BACKING }),
        h('textarea', {
          ref: ta, className: 'rkx-ta', rows: 1, value: draft, disabled: offline, onChange: e => setDraft(e.target.value), onKeyDown: onKey,
          placeholder: offline ? 'Waiting for Hermes…' : project ? 'Ask Hermes to change the beat…' : 'Describe a beat…', 'aria-label': 'Message Hermes'
        }),
        // The main composer's control row: context on the left, model pill + send on the right.
        h('div', { className: 'rkx-row' },
          project && h(Tipped, { label: `${project.name} · ${project.bpm} BPM · ${project.bars} bars. ${useCtx ? 'Hermes will work on this beat. Click to leave it out.' : 'Click to point Hermes at this beat.'}` },
            h('button', { type: 'button', className: 'rkx-ctx', 'data-off': !useCtx, onClick: () => setUseCtx(v => !v), 'aria-pressed': useCtx },
              h(GridGlyph), h('span', null, project.name), useCtx && h('span', { className: 'rkx-x' }, h(Ico, { n: 'close', s: '0.625rem' })))),
          h('span', { className: 'rkx-sp' }),
          h(ModelPill, { current: chat.model, fallback: model, onPick: chat.setModel, disabled: chat.busy || offline, onClosed: () => ta.current?.focus({ preventScroll: true }) }),
          send_))))
}
const cn2 = (...xs) => xs.filter(Boolean).join(' ')
const words = s => String(s || '').toLowerCase().split(/[\s/._-]+/).filter(Boolean)

// The chat's model: Hermes's own catalog (model.options), searchable, grouped by provider.
const modelId = m => (typeof m === 'string' ? m : m?.id || m?.model || m?.slug || m?.name || '')
const shortModel = s => String(s || '').replace(/^.*\//, '')

// ── model pill: Hermes's composer model selector, rebuilt from the SDK's own parts ──
// Same chrome as apps/desktop/src/app/chat/composer/model-pill.tsx and the menu in
// app/shell/model-catalog-menu.tsx: ghost pill "Name · Tag ⌄", a w-72 dropdown opening
// upward, a search field, collapsible provider groups, rows with tag, price and check.
// The class strings are core's, so they are already in the app's compiled CSS.
const NATIVE = {
  pill: 'h-(--composer-control-size) min-w-0 shrink gap-1 rounded-md px-2 text-xs font-normal text-(--ui-text-tertiary) hover:bg-(--chrome-action-hover) hover:text-foreground',
  content: 'w-72 p-0',
  search: 'px-2.5 py-1.5 has-[>input:focus]:shadow-[inset_0_-1px_0_var(--color-ring)]',
  searchInput: 'h-4 w-full bg-transparent text-xs leading-none text-foreground placeholder:text-(--ui-text-tertiary) focus:outline-hidden',
  list: 'max-h-[max(150px,30dvh)] overflow-y-auto py-0.5',
  row: 'gap-2 rounded-none px-2.5 py-1 text-xs',
  group: 'px-2 pb-0.5 pt-0.5 text-[0.625rem] font-semibold uppercase tracking-wider text-(--ui-text-secondary) group/label flex w-full cursor-pointer items-center gap-1 !bg-transparent focus:!bg-transparent',
  rowName: 'flex min-w-0 flex-1 items-center gap-1.5',
  price: 'flex shrink-0 items-center gap-1.5 pl-2 text-[0.625rem] tabular-nums text-(--ui-text-tertiary)',
  free: 'shrink-0 pl-2 text-[0.625rem] text-(--ui-green)'
}
const NAV_KEYS = new Set(['ArrowDown', 'ArrowUp', 'Enter', 'Escape', 'Tab'])
const HAS_NATIVE_MENU = !!(sdk.DropdownMenu && sdk.DropdownMenuTrigger && sdk.DropdownMenuContent && sdk.DropdownMenuItem && sdk.Button)

// Core's model naming (lib/model-status-label.ts): last path segment, date pin dropped,
// a trailing variant becomes a tag, vendor casing ("DeepSeek V4.1 Flash 1017").
const VARIANT_TAGS = [[/-fast$/i, 'Fast'], [/-flash$/i, 'Flash'], [/-thinking$/i, 'Thinking'], [/-preview$/i, 'Preview'], [/-latest$/i, 'Latest']]
const VENDOR_CASE = { deepseek: 'DeepSeek', glm: 'GLM', qwen: 'Qwen', grok: 'Grok', gemini: 'Gemini', kimi: 'Kimi', llama: 'Llama', minimax: 'MiniMax', mimo: 'MiMo', mistral: 'Mistral', gemma: 'Gemma', step: 'Step', luna: 'Luna', sol: 'Sol' }
function modelParts(id) {
  let base = shortModel(String(id || '').trim()).replace(/-\d{8}$/, '')
  let tag = ''
  for (const [re, t] of VARIANT_TAGS) if (re.test(base)) { tag = t; base = base.replace(re, ''); break }
  let name
  if (/^claude-/i.test(base)) name = base.replace(/^claude-/i, '').replace(/(\d)-(?=\d)/g, '$1.').replace(/-/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
  else if (/^gpt-/i.test(base)) name = base.replace(/^gpt-/i, 'GPT-')
  else name = base.split(/[-_ ]+/).map(w => VENDOR_CASE[w.toLowerCase()] || (/^v?\d/i.test(w) ? w.toUpperCase().replace(/^V/, 'V') : w.charAt(0).toUpperCase() + w.slice(1))).join(' ')
  return { name: name || String(id || '').trim() || 'No model', tag }
}
const pillLabel = id => { const p = modelParts(id); return p.tag ? `${p.name} · ${p.tag}` : p.name }
const providerMatches = (p, id) => !!id && (typeof sdk.catalogProviderMatches === 'function'
  ? sdk.catalogProviderMatches(p, id)
  : p.slug === id || p.name === id || (p.aliases || []).includes(id))

// One catalog read shared by every pill, fresh for two minutes (core's staleTime), bounded at 20 s.
let catalogCache = { at: 0, data: null, inflight: null }
function loadCatalog(force) {
  if (!force && catalogCache.data && Date.now() - catalogCache.at < 120000) return Promise.resolve(catalogCache.data)
  if (catalogCache.inflight) return catalogCache.inflight
  const deadline = new Promise((_, rej) => setTimeout(() => rej(new Error('model.options did not answer within 20s')), 20000))
  catalogCache.inflight = Promise.race([host.request('model.options', {}), deadline])
    .then(r => {
      const data = (r?.providers || []).filter(p => p && p.slug).map(p => ({
        slug: p.slug, name: p.name || p.slug, aliases: p.aliases || [], pricing: p.pricing || {},
        models: (p.models || []).map(modelId).filter(Boolean)
      })).filter(p => p.models.length)
      catalogCache = { at: Date.now(), data, inflight: null }
      return data
    })
    .catch(e => { catalogCache.inflight = null; throw e })
  return catalogCache.inflight
}

function NativePrice({ pricing }) {
  if (!pricing) return null
  if (pricing.free) return h('span', { className: NATIVE.free }, 'Free')
  const input = pricing.input || null, output = pricing.output || null
  if (!input && !output) return null
  return h('span', { className: NATIVE.price, title: `${input ?? '—'} in / ${output ?? '—'} out per Mtok` }, `${input ?? '—'}/${output ?? '—'}`)
}
const ModelTag = ({ children }) => (sdk.Badge
  ? h(sdk.Badge, { className: 'shrink-0 uppercase tracking-wide', size: 'xs', variant: 'muted' }, children)
  : h('span', { className: 'rkx-tagchip' }, children))

function ModelPill(props) {
  return HAS_NATIVE_MENU ? h(Safe, { fallback: h(ModelPicker, props) }, h(NativeModelPill, props)) : h(ModelPicker, props)
}
function NativeModelPill({ current, fallback, onPick, disabled, onClosed }) {
  const { DropdownMenu, DropdownMenuTrigger, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, Button } = sdk
  const [open, setOpen] = useState(false)
  const [catalog, setCatalog] = useState(catalogCache.data)
  const [err, setErr] = useState(null)
  const [q, setQ] = useState('')
  const [collapsed, setCollapsed] = useState(() => new Set())
  const onOpenChange = next => {
    setOpen(next)
    if (next) { setErr(null); loadCatalog().then(setCatalog, e => setErr(String(e?.message || e))) }
    else setQ('')
  }
  const currentId = current?.model || fallback || ''
  const label = currentId ? pillLabel(currentId) : null
  const title = current?.model ? `${current.provider ? `${current.provider} · ` : ''}${current.model}` : `Hermes default${fallback ? ` · ${fallback}` : ''}`
  const terms = words(q)
  const hit = (p, m) => { const hay = `${p.name} ${p.slug} ${m} ${pillLabel(m)}`.toLowerCase(); return terms.every(t => hay.includes(t)) }
  const groups = (catalog || []).map(p => ({ ...p, models: terms.length ? p.models.filter(m => hit(p, m)) : p.models })).filter(p => p.models.length)
  const isCurrent = (p, m) => !!current?.model && current.model === m && (!current.provider || providerMatches(p, current.provider))
  const pick = sel => { setOpen(false); setQ(''); onPick(sel) }
  const toggleGroup = slug => setCollapsed(s => { const n = new Set(s); n.has(slug) ? n.delete(slug) : n.add(slug); return n })

  const row = (key, name, tag, extra, on, onSelect) => h(DropdownMenuItem, { key, className: NATIVE.row, onSelect },
    h('span', { className: NATIVE.rowName }, h('span', { className: 'min-w-0 truncate' }, name), tag && h(ModelTag, null, tag)),
    extra, on && h(Ico, { n: 'check', s: '0.75rem' }))
  let shown = 0
  return h(DropdownMenu, { open, onOpenChange },
    h(Tipped, { label: title },
      h(DropdownMenuTrigger, { asChild: true },
        h(Button, { type: 'button', variant: 'ghost', className: cn2(NATIVE.pill, 'rkx-mpill'), disabled, 'aria-label': `Model: ${title}` },
          label ? h('span', { className: 'truncate' }, label) : h(Spin),
          current?.model && h('span', { className: 'size-1 shrink-0 rounded-full bg-(--ui-accent) rkx-pin', 'aria-label': 'Picked for Rookery', role: 'img' }),
          h(Ico, { n: 'chevron-down', s: '0.625rem' })))),
    // Like core's pill: closing hands the keyboard back to the input instead of parking focus on the pill.
    h(DropdownMenuContent, { align: 'end', side: 'top', sideOffset: 8, className: cn2(NATIVE.content, 'rkx-mmenu'), onCloseAutoFocus: e => { if (onClosed) { e.preventDefault(); onClosed() } } },
      h('div', { className: NATIVE.search, 'data-slot': 'dropdown-menu-search' },
        h('input', {
          autoFocus: true, type: 'text', spellCheck: false, className: NATIVE.searchInput, placeholder: 'Search models', 'aria-label': 'Search models', value: q,
          onChange: e => setQ(e.target.value),
          onKeyDown: e => {
            if (!NAV_KEYS.has(e.key)) e.stopPropagation() // typing filters; Radix typeahead must not take it
            if (e.key === 'Enter' && terms.length && groups[0]) { e.preventDefault(); pick({ model: groups[0].models[0], provider: groups[0].slug }) }
          }
        })),
      DropdownMenuSeparator && h(DropdownMenuSeparator, { className: 'mx-0' }),
      h('div', { className: NATIVE.list },
        !terms.length && row('default', fallback ? pillLabel(fallback) : 'Hermes default', 'Default', null, !current?.model, () => pick(null)),
        err ? h(DropdownMenuItem, { className: NATIVE.row, disabled: true }, `Couldn’t load models: ${err}`)
          : !catalog ? [0, 1, 2, 3].map(i => h(DropdownMenuItem, { key: `sk${i}`, className: NATIVE.row, disabled: true, onSelect: e => e.preventDefault() },
              sdk.Skeleton ? h(sdk.Skeleton, { className: 'h-4 w-full' }) : h('span', { className: 'rkx-skel-row' })))
          : !groups.length ? h(DropdownMenuItem, { className: NATIVE.row, disabled: true }, 'No models match')
          : groups.map(p => {
              const closed = collapsed.has(p.slug) && !terms.length
              return h(Fragment, { key: p.slug },
                h(DropdownMenuItem, { className: NATIVE.group, onSelect: e => { e.preventDefault(); toggleGroup(p.slug) }, textValue: '' },
                  h('span', { className: 'truncate' }, p.name),
                  sdk.DisclosureCaret
                    ? h(sdk.DisclosureCaret, { className: 'shrink-0 text-(--ui-text-tertiary) opacity-0 transition group-hover/label:opacity-100', open: !closed, size: '0.625rem' })
                    : h(Ico, { n: closed ? 'chevron-right' : 'chevron-down', s: '0.625rem' })),
                !closed && p.models.map(m => {
                  if (++shown > 400) return null
                  const parts = modelParts(m)
                  return row(`${p.slug}:${m}`, parts.name, parts.tag, h(NativePrice, { pricing: p.pricing?.[m] }), isCurrent(p, m), () => pick({ model: m, provider: p.slug }))
                }))
            }))))
}

// Fallback for desktop builds without the SDK dropdown parts.
function ModelPicker({ current, fallback, onPick, disabled }) {
  const [open, setOpen] = useState(false)
  const [opts, setOpts] = useState(null)
  const [err, setErr] = useState(null)
  const [q, setQ] = useState('')
  const wrap = useRef(null), input = useRef(null)
  useEffect(() => {
    if (!open) return
    input.current?.focus()
    const away = e => { if (!wrap.current?.contains(e.target)) setOpen(false) }
    const esc = e => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('pointerdown', away, true); document.addEventListener('keydown', esc)
    return () => { document.removeEventListener('pointerdown', away, true); document.removeEventListener('keydown', esc) }
  }, [open])
  const load = async () => {
    setErr(null)
    try {
      const r = await host.request('model.options', {})
      setOpts((r?.providers || []).map(p => ({ slug: p.slug, name: p.name || p.label || p.slug, models: (p.models || []).map(modelId).filter(Boolean) })).filter(p => p.models.length))
    } catch (e) { setErr(String(e?.message || e)) }
  }
  const toggle = () => { if (disabled) return; setOpen(o => !o); if (!opts) load() }
  const pick = m => { setOpen(false); setQ(''); onPick(m) }
  const needle = q.trim().toLowerCase(), terms = words(needle)
  const hit = (p, m) => { const hay = `${p.name} ${p.slug} ${m}`.toLowerCase(); return terms.every(t => hay.includes(t)) }
  let shown = 0
  const groups = (opts || []).map(p => ({ ...p, models: p.models.filter(m => !terms.length || hit(p, m)) })).filter(p => p.models.length)
  const label = current?.model ? shortModel(current.model) : shortModel(fallback) || 'Default model'
  return h('div', { className: 'rkx-mp', ref: wrap },
    h(Tipped, { label: current?.model ? `${current.model} · ${current.provider || 'default provider'}` : 'Model for new Rookery chats' },
      h('button', { type: 'button', className: 'rkx-mbtn', onClick: toggle, disabled, 'aria-expanded': open, 'aria-haspopup': 'listbox' },
        h('span', null, label), h(Ico, { n: 'chevron-down', s: '0.6875rem' }))),
    open && h('div', { className: 'rkx-menu', role: 'listbox' },
      h('input', {
        ref: input, className: 'rkx-q', placeholder: 'Search models', value: q, onChange: e => setQ(e.target.value),
        onKeyDown: e => { if (e.key === 'Enter') { const g = groups[0]; if (g) pick({ model: g.models[0], provider: g.slug }) } }
      }),
      h('div', { className: 'rkx-mlist' },
        !needle && h('button', { type: 'button', className: 'rkx-mrow', 'aria-selected': !current, onClick: () => pick(null) },
          h('span', null, 'Hermes default'), h('em', null, shortModel(fallback)), !current && h(Ico, { n: 'check', s: '0.75rem' })),
        err ? h('div', { className: 'rkx-mnote' }, `Couldn’t load models: ${err}`)
          : !opts ? h('div', { className: 'rkx-mnote' }, h(Spin), ' Loading models…')
          : !groups.length ? h('div', { className: 'rkx-mnote' }, 'No models match.')
          : groups.map(p => h(Fragment, { key: p.slug },
              h('div', { className: 'rkx-mhead' }, p.name),
              p.models.map(m => {
                if (++shown > 80) return null
                const on = current?.model === m && (current?.provider || null) === (p.slug || null)
                return h('button', { key: m, type: 'button', className: 'rkx-mrow', 'aria-selected': on, onClick: () => pick({ model: m, provider: p.slug }) },
                  h('span', null, shortModel(m)), h('em', null, m.includes('/') ? m.replace(/\/[^/]*$/, '') : ''), on && h(Ico, { n: 'check', s: '0.75rem' }))
              }))))))
}

function ChatStrip({ unread, docked, onShow }) {
  return h('div', { className: 'rkx-strip' },
    h(IB, { icon: docked ? 'layout-sidebar-right' : 'comment-discussion', label: docked ? 'Bring the chat back into Rookery' : 'Show chat', onClick: onShow }, unread && h('i', { className: 'rkx-unread' })),
    h('span', null, docked ? 'Chat is docked' : 'Chat'))
}

let dockDispose = null

// ── page ──────────────────────────────────────────────────────────────────
function RookeryPage({ ctx, embedded = false }) {
  const [projects, setProjects] = useState(null)
  const [name, setName] = useState(null)
  const [view, setViewState] = useState(null)
  const [flockCatalog, setFlockCatalog] = useState(null)
  const [flockCollapsed, setFlockCollapsedState] = useState(() => !!ctx.storage?.get('flock.collapsed', false))
  const [offline, setOffline] = useState(null)
  const [lit, setLit] = useState(null)
  const [rendering, setRendering] = useState(false)
  const [renderErr, setRenderErr] = useState(null)
  const [status, setStatus] = useState(null)
  const [match, setMatch] = useState(null)
  const [buffer, setBuffer] = useState(null)
  const [playing, setPlaying] = useState(false)
  const [renderMode, setRenderMode] = useState('loop')
  const arrangementTimer = useRef(null), arrangementDraft = useRef(null), autoplaySong = useRef(false)
  const [pendingEdits, setPendingEdits] = useState(0)
  const [saveFailed, setSaveFailed] = useState(false)
  const [renaming, setRenaming] = useState(false)
  const [renameError, setRenameError] = useState(null)

  const viewRef = useRef(null), nameRef = useRef(null), hashes = useRef(new Map())
  const projectNames = useRef([])
  const renameNextBeat = useRef(null)
  const engine = useRef(null), loadedHash = useRef(null), queue = useRef(Promise.resolve()), renderTimer = useRef(null)
  const nonce = useRef(0), root = useRef(null), rack = useRef(null), phRef = useRef(null), waveLit = useRef(null)
  nameRef.current = name
  useEffect(() => {
    if (name !== null && renameNextBeat.current === name) {
      renameNextBeat.current = null
      return
    }
    renameNextBeat.current = null
    setRenaming(false); setRenameError(null)
  }, [name])
  const setView = next => { viewRef.current = next; setViewState(next) }
  const setFlockCollapsed = collapsed => { const value = !!collapsed; setFlockCollapsedState(value); ctx.storage?.set('flock.collapsed', value) }

  if (!engine.current) engine.current = new Engine()

  const noteRender = r => {
    if (!r?.render?.hash) return
    const other = hashes.current.get(r.render.hash)
    if (other && other !== r.project.name) setMatch({ hash: r.render.hash, other })
    else if (!other) hashes.current.set(r.render.hash, r.project.name)
  }

  // One request of each kind in flight at a time: a hung gateway must not stack polls.
  const inflight = useRef({ load: false, list: false })
  // After a timeout, wait before trying again (retryDelay). A user action forces.
  const failure = useRef({ load: 0, list: 0 })
  const retryAt = useRef({ load: 0, list: 0 })
  const canPoll = kind => Date.now() >= (retryAt.current[kind] || 0)
  const noteSaved = kind => { failure.current[kind] = 0; retryAt.current[kind] = 0 }
  const noteFailed = kind => {
    failure.current[kind] = (failure.current[kind] || 0) + 1
    retryAt.current[kind] = Date.now() + retryDelay(failure.current[kind])
  }
  const load = async (nm = nameRef.current, force = false) => {
    if (!nm) return
    if (inflight.current.load && !force) return
    if (!force && !canPoll('load')) return
    inflight.current.load = true
    try { await loadOnce(nm, force) } finally { inflight.current.load = false }
  }
  const loadOnce = async (nm, force) => {
    const cur = viewRef.current
    const since = !force && cur && cur.project.name === nm ? `?since=${cur.rev}` : ''
    try {
      const r = await ctx.rest(`/project/${encodeURIComponent(nm)}${since}`)
      setOffline(null)
      noteSaved('load')
      if (r.changed === false || nameRef.current !== nm) return
      if (viewRef.current?.render?.hash !== r.render?.hash) setMatch(m => (m && m.hash === r.render?.hash ? m : null))
      setView(r)
      noteRender(r)
    } catch (e) {
      noteFailed('load')
      if (e.status === 404) { refreshProjects(true); return }
      setOffline(String(e.message || e))
    }
  }

  const refreshProjects = async (force = false) => {
    if (inflight.current.list) return
    if (!force && !canPoll('list')) return
    inflight.current.list = true
    try {
      const list = await ctx.rest('/projects')
      setOffline(null)
      noteSaved('list')
      const follow = newlyCreatedProject({ previous: projectNames.current, current: nameRef.current, list })
      projectNames.current = list.map(project => project.name)
      setProjects(list)
      if (follow) pick(follow)
      else if ((!nameRef.current || !list.some(p => p.name === nameRef.current)) && list.length) pick(list[0].name)
      if (!list.length) { nameRef.current = null; setName(null); setView(null) }
    } catch (e) { noteFailed('list'); setOffline(String(e.message || e)) }
    finally { inflight.current.list = false }
  }

  const pick = nm => {
    if (nm === nameRef.current) return
    nameRef.current = nm
    setName(nm); setView(null); setLit(null); setRenderErr(null); setMatch(null)
    // Never leave the previous project's audio on the transport or waveform.
    const eng = engine.current
    if (eng) { eng.stop(); eng.setBuffer(null) }
    loadedHash.current = null
    setBuffer(null)
    load(nm, true)
  }

  // serialized edits: each body is built from the freshest state at send time,
  // but only for the project that was open when the user acted.
  const edit = (makeBody, optimistic) => {
    const target = nameRef.current
    setPendingEdits(count => count + 1)
    const before = viewRef.current
    if (optimistic && before) setView({ ...before, project: optimistic(before.project) })
    queue.current = queue.current.then(async () => {
      const cur = viewRef.current
      if (!cur || !editBelongsTo(target, nameRef.current) || cur.project.name !== target) {
        setPendingEdits(count => Math.max(0, count - 1))
        return
      }
      try {
        const operation = makeBody(cur.project)
        const r = await ctx.rest('/edit', { method: 'POST', body: { name: target, rev: cur.rev, ...operation } })
        setSaveFailed(false)
        if (!editBelongsTo(target, nameRef.current)) return
        setView({ ...viewRef.current, project: r.project, rev: r.rev })
        if (operation.op === 'clear' && r.diff?.length) setLit(litFromDiff(r.diff, ++nonce.current))
        scheduleRender()
      } catch (e) {
        if (e.status >= 400 && e.status < 500) setSaveFailed(false)
        else setSaveFailed(true)
        host.notify({ kind: 'error', message: e.message || 'Edit failed' })
        load(undefined, true) // roll back to the truth
      } finally { setPendingEdits(count => Math.max(0, count - 1)) }
    })
  }

  const createBeat = async (from = null, name = null) => {
    try {
      const result = await ctx.rest('/project', { method: 'POST', body: { ...(from ? { from } : {}), ...(name ? { name } : {}) } })
      renameNextBeat.current = result.project.name
      await refreshProjects()
      setRenaming(true); setRenameError(null)
      if (result.project.name !== nameRef.current) {
        renameNextBeat.current = result.project.name
        pick(result.project.name)
      }
    } catch (e) { host.notify({ kind: 'error', message: e.message || 'Could not create beat' }) }
  }
  const duplicateName = from => {
    const names = new Set((projects || []).map(project => project.name))
    const base = `${from}-copy`
    if (!names.has(base)) return base
    let index = 2
    while (names.has(`${base}-${index}`)) index++
    return `${base}-${index}`
  }
  const renameBeat = async to => {
    const from = viewRef.current?.project?.name
    const next = String(to ?? '').trim()
    if (next === from) { setRenaming(false); setRenameError(null); return }
    try {
      await ctx.rest(`/project/${encodeURIComponent(from)}/rename`, { method: 'POST', body: { to: next } })
      setRenaming(false); setRenameError(null); await refreshProjects(); pick(next)
    } catch (e) { setRenameError(String(e.message || 'Invalid project name')) }
  }
  const deleteBeat = async () => {
    const current = viewRef.current?.project?.name
    try { await ctx.rest(`/project/${encodeURIComponent(current)}`, { method: 'DELETE' }); nameRef.current = null; setName(null); setView(null); engine.current?.stop(); engine.current?.setBuffer(null); loadedHash.current = null; setBuffer(null); await refreshProjects() }
    catch (e) { host.notify({ kind: 'error', message: e.message || 'Could not delete beat' }) }
  }
  const clearPattern = () => {
    const project = viewRef.current?.project
    if (!project?.tracks?.some(track => Array.from(track.steps || '').some(isHit))) {
      host.notify({ kind: 'info', message: 'Nothing to clear' })
      return
    }
    edit(() => ({ op: 'clear' })); scheduleRender()
  }
  const retrySave = async () => {
    const target = nameRef.current
    await load(undefined, true)
    if (target && viewRef.current?.project?.name === target) setSaveFailed(false)
  }
  const undoOne = async () => {
    const current = viewRef.current
    if (!current || current.rev === 1) return
    try { await ctx.rest('/undo', { method: 'POST', body: { name: current.project.name, steps: 1 } }); await load(undefined, true); scheduleRender() }
    catch (e) { host.notify({ kind: 'error', message: e.message || 'Undo failed' }) }
  }

  const renderBusy = useRef(false), renderWant = useRef(false)
  const doRender = async () => {
    const cur = viewRef.current
    if (!cur) return
    if (renderBusy.current) { renderWant.current = true; return }
    renderBusy.current = true
    autoplaySong.current = renderMode === 'song'
    setRendering(true); setRenderErr(null)
    try { await ctx.rest('/render', { method: 'POST', body: { name: cur.project.name, ...(renderMode === 'song' ? { song: true } : {}) } }); await load(undefined, true) }
    catch (e) { setRenderErr(String(e.message || e)) }
    finally {
      renderBusy.current = false
      setRendering(false)
      if (renderWant.current) { renderWant.current = false; scheduleRender() }
    }
  }
  const scheduleRender = () => { clearTimeout(renderTimer.current); renderTimer.current = setTimeout(doRender, RENDER_DEBOUNCE_MS) }

  const onToggle = useCallback((trackId, i) => {
    const flip = p => ({ ...p, tracks: p.tracks.map(t => t.id !== trackId ? t : { ...t, steps: t.steps.slice(0, i) + (isHit(t.steps[i]) ? '.' : 'x') + t.steps.slice(i + 1) }) })
    edit(p => ({ op: 'steps', track: trackId, steps: p.tracks.find(t => t.id === trackId).steps }), flip)
  }, [])
  const onTrack = useCallback((id, patch) => {
    edit(() => ({ op: 'track', action: 'set', id, ...patch }), p => ({ ...p, tracks: p.tracks.map(t => (t.id === id ? { ...t, ...patch } : t)) }))
  }, [])
  const onMeta = patch => edit(() => ({ op: 'meta', ...patch }), p => ({ ...p, ...patch }))
  const onArrangement = sections => {
    arrangementDraft.current = sections
    const current = viewRef.current
    if (current) setView({ ...current, project: sections ? { ...current.project, arrangement: { sections } } : (() => { const project = { ...current.project }; delete project.arrangement; return project })() })
    clearTimeout(arrangementTimer.current)
    arrangementTimer.current = setTimeout(() => {
      const next = arrangementDraft.current
      arrangementDraft.current = null
      edit(() => ({ op: 'arrange', sections: next }), p => next ? ({ ...p, arrangement: { sections: next } }) : (() => { const project = { ...p }; delete project.arrangement; return project })())
    }, 180)
  }
  const onFlockChange = (next, meta) => {
    if (meta?.action === 'wireTap') return
    const body = flockEditBody(viewRef.current?.project?.flock, next, meta)
    if (!body) return
    // Freeze the just-computed flock payload before optimistic state lands; the
    // queued request must compare against the pre-edit state, not its own patch.
    if (meta?.action === 'mix') {
      edit(() => ({ op: 'flock', ...body }), project => optimisticFlockProject(project, next, meta, flockCatalog))
      return
    }
    edit(project => ({ op: 'flock', ...flockEditBody(project.flock, next, meta) }),
      project => optimisticFlockProject(project, next, meta, flockCatalog))
  }
  const onFlockTemplate = template => onFlockChange(null, { action: 'template', template })
  const onFxParam = (index, param, value) => edit(
    () => ({ op: 'fx_param', target: 'master', index, param, value }),
    p => ({ ...p, master: { ...p.master, fx: p.master.fx.map((f, k) => (k === index ? { ...f, params: { ...(f.params || {}), [param]: value } } : f)) } }))

  // boot, events, polling
  useEffect(() => {
    const takeFocus = nm => { if (nm) { focusRequest = null; nameRef.current ? pick(nm) : (nameRef.current = nm, setName(nm), load(nm, true)) } }
    focusSubs.add(takeFocus)
    if (focusRequest) takeFocus(focusRequest)
    refreshProjects()
    ctx.rest('/status').then(setStatus).catch(() => {})
    let ticks = 0
    const offs = [
      host.onEvent(EV + 'project.updated', ({ payload: pl }) => {
        if (!pl) return
        if (pl.name !== nameRef.current) {
          refreshProjects()
          if (pl.source === 'agent') { pick(pl.name); setLit(litFromDiff(pl.diff, ++nonce.current)) }
          return
        }
        const cur = viewRef.current
        if (cur && pl.rev <= cur.rev) return // our own optimistic edit, already painted
        const local = cur && applyDiffLocally(cur.project, pl.diff)
        if (local) setView({ ...cur, project: local, rev: pl.rev })
        if (pl.source !== 'user' || !cur) setLit(litFromDiff(pl.diff, ++nonce.current))
        load(undefined, !local)
      }),
      host.onEvent(EV + 'project.created', () => refreshProjects()),
      host.onEvent(EV + 'project.renamed', ({ payload: pl }) => {
        refreshProjects()
        if (pl?.from === nameRef.current) pick(pl.to)
      }),
      host.onEvent(EV + 'project.deleted', ({ payload: pl }) => {
        if (pl?.name === nameRef.current) { nameRef.current = null; setName(null); setView(null) }
        refreshProjects()
      }),
      host.onEvent(EV + 'agent.editing', ({ payload: pl }) => {
        if (pl?.name === nameRef.current && viewRef.current) setView({ ...viewRef.current, agent_editing: !!pl.editing })
      }),
      host.onEvent(EV + 'render.started', ({ payload: pl }) => { if (pl?.name === nameRef.current) { setRendering(true); setRenderErr(null) } }),
      host.onEvent(EV + 'render.done', ({ payload: pl }) => { if (pl?.name === nameRef.current) { setRendering(false); load(undefined, true) } }),
      host.onEvent(EV + 'render.failed', ({ payload: pl }) => { if (pl?.name === nameRef.current) { setRendering(false); setRenderErr(pl.message || 'Render failed') } }),
      // Rev watch: the page stays in sync when push events are lost. Visible
      // windows poll every REV_POLL_MS; a hidden one resumes at once.
      startRevWatch({
        poll: () => { if (nameRef.current) load() },
        setInterval: ctx.setInterval,
        addEventListener: ctx.addEventListener,
        document: typeof document === 'undefined' ? null : document
      }),
      ctx.setInterval(() => {
        ticks++
        refreshProjects()
        // Sample credits land after a fetch, so keep the kit map fresh without a reload.
        if (ticks % 3 === 0) ctx.rest('/status').then(setStatus).catch(() => {})
      }, POLL_MS)
    ]
    const eng = engine.current
    const sub = () => setPlaying(eng.playing)
    eng.subs.add(sub)
    return () => { focusSubs.delete(takeFocus); offs.forEach(off => off()); clearTimeout(renderTimer.current); clearTimeout(arrangementTimer.current); eng.dispose(); engine.current = null }
  }, [])

  useEffect(() => {
    let cancelled = false
    ctx.rest('/flock/catalog').then(catalog => {
      if (cancelled) return
      FLOCK_BIRD_NAMES.clear()
      for (const bird of [...(catalog?.birds || []), catalog?.corvus].filter(Boolean)) FLOCK_BIRD_NAMES.set(bird.id, bird.name)
      setFlockCatalog(catalog)
    }).catch(error => {
      if (!cancelled) setFlockCatalog({ error: String(error?.message || error) })
    })
    return () => { cancelled = true }
  }, [])

  // fetch + decode audio when the render changes
  const render = view?.render
  useEffect(() => {
    if (!render?.hash || !render.audio_url || loadedHash.current === render.hash) return
    let dead = false
    ;(async () => {
      try {
        const url = render.audio_url
        const bytes = /^(blob:|https?:|data:)/.test(url) ? await (await fetch(url)).arrayBuffer() : b64ToBytes((await ctx.rest(url)).b64)
        const buf = await engine.current.decode(bytes)
        if (dead) return
        loadedHash.current = render.hash
        engine.current.setBuffer(buf)
        setBuffer(buf)
        if (autoplaySong.current && render.song) { autoplaySong.current = false; engine.current.play() }
      } catch (e) { if (!dead) setRenderErr(`Couldn’t load audio: ${e.message || e}`) }
    })()
    return () => { dead = true }
  }, [render?.hash])

  // playhead: imperative, one rAF loop while playing, no React renders per frame
  useEffect(() => {
    if (!playing) {
      rack.current?.querySelectorAll('[data-ph]').forEach(el => el.removeAttribute('data-ph'))
      if (waveLit.current) waveLit.current.style.clipPath = 'inset(0 100% 0 0)'
      return
    }
    let raf = 0, col = -1
    const tick = () => {
      const eng = engine.current, cur = viewRef.current
      if (!eng?.buffer || !cur) { raf = requestAnimationFrame(tick); return }
      const frac = eng.position() / eng.buffer.duration
      const ph = phRef.current
      if (ph) ph.style.transform = `translateX(${frac * ph.parentElement.clientWidth}px)`
      if (waveLit.current) waveLit.current.style.clipPath = `inset(0 ${(1 - frac) * 100}% 0 0)`
      // A song render is many loops long: the pads follow the position inside the current loop.
      const loopSecs = cur.project.bars * 4 * 60 / cur.project.bpm
      const stepFrac = cur.render?.song ? (eng.position() % loopSecs) / loopSecs : frac
      const n = loopLen(cur.project), c = Math.min(n - 1, Math.floor(stepFrac * n))
      if (c !== col && rack.current) {
        rack.current.querySelectorAll('[data-ph]').forEach(el => el.removeAttribute('data-ph'))
        rack.current.querySelectorAll(`[data-i="${c}"]`).forEach(el => el.setAttribute('data-ph', ''))
        col = c
      }
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [playing])

  const togglePlay = () => (engine.current.playing ? engine.current.stop() : engine.current.play())
  const onKey = e => {
    if (e.target !== root.current && e.target.closest?.('input,textarea,[contenteditable="true"]')) return
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z' && !e.shiftKey) { e.preventDefault(); undoOne(); return }
    if (e.code === 'Space' && !e.target.closest?.('button,[role="slider"],[role="spinbutton"]')) { e.preventDefault(); togglePlay() }
  }

  // ── chat: in the page by default, docked beside the main thread on request ──
  const chat = useChat(ctx)
  const [mode, setModeState] = useState(() => (embedded ? 'docked' : ctx.storage?.get(CHAT_KEYS.mode, 'rail') || 'rail'))
  const [chatW, setChatW] = useState(() => clamp(+ctx.storage?.get(CHAT_KEYS.width, CHAT_W.def) || CHAT_W.def, CHAT_W.min, CHAT_W.max))
  const [narrow, setNarrow] = useState(false)
  const [sheet, setSheet] = useState(false)
  const split = useRef(null), chatWRef = useRef(chatW)
  const setMode = m => { setModeState(m); ctx.storage?.set(CHAT_KEYS.mode, m) }
  useEffect(() => {
    const el = split.current
    if (!el || typeof ResizeObserver === 'undefined') return
    const ro = new ResizeObserver(([e]) => setNarrow(e.contentRect.width < NARROW_PX))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
  useEffect(() => { if (mode === 'rail' && chat.unread) chat.clearUnread() }, [mode, chat.unread])
  // A docked session that was closed elsewhere comes back to the page.
  useEffect(() => { if (!embedded && mode === 'docked' && !dockDispose) setMode('rail') }, [])
  const onWidth = (w, commit) => {
    if (w != null) { chatWRef.current = w; setChatW(w) }
    if (commit) ctx.storage?.set(CHAT_KEYS.width, chatWRef.current)
  }
  const canDock = !embedded && typeof host.openWorkspace === 'function' && typeof host.openSession === 'function'
  const dock = async () => {
    if (!chat.stored) return
    setMode('docked')
    try {
      await host.openSession(chat.stored)
      try { dockDispose?.() } catch {}
      dockDispose = host.openWorkspace('rookery', {
        title: 'Rookery', minWidth: '480px', dock: { pane: 'workspace', pos: 'right' },
        render: () => h(RookeryPage, { ctx, embedded: true }),
        onClose: () => { dockDispose = null; ctx.storage?.set(CHAT_KEYS.mode, 'rail') }
      })
    } catch (e) {
      setMode('rail')
      host.notify({ kind: 'error', message: `Couldn’t dock the chat: ${e.message || e}` })
    }
  }
  const undock = () => {
    const d = dockDispose
    dockDispose = null
    ctx.storage?.set(CHAT_KEYS.mode, 'rail')
    if (!embedded) setModeState('rail')
    host.navigate('/rookery')
    try { d?.() } catch {}
  }
  const lightItem = item => { if (item.name === nameRef.current && item.diff?.length) setLit(litFromDiff(item.diff, ++nonce.current)) }
  const undoTurn = async (turn, edits) => {
    try {
      await ctx.rest('/undo', { method: 'POST', body: { name: edits[0].name, steps: edits.length } })
      chat.markUndone(turn.id)
      await load(undefined, true)
      scheduleRender()
    } catch (e) { host.notify({ kind: 'error', message: e.message || 'Undo failed' }) }
  }
  const promptFromPage = text => { if (mode !== 'rail' && !embedded) setMode('rail'); chat.send(text, viewRef.current?.project?.name || null) }

  const chatEl = embedded
    ? h(ChatStrip, { docked: true, onShow: undock })
    : mode === 'rail'
      ? h(ChatRail, {
          chat, view, width: chatW, narrow, sheet, onSheet: setSheet, onWidth, onHide: () => setMode('hidden'), onDock: dock, canDock,
          onLight: lightItem, canPlay: !!buffer, playing, onPlay: togglePlay, onUndoTurn: undoTurn
        })
      : h(ChatStrip, { unread: chat.unread, docked: mode === 'docked', onShow: mode === 'docked' ? undock : () => setMode('rail') })
  const frame = main => h('div', { className: 'rk-split', ref: split, 'data-narrow': narrow }, h('style', null, CSS + CHAT_CSS), main, chatEl)

  const style = null
  if (offline && !view) return frame(h('div', { className: 'rk' }, style, h(Offline, { message: offline, onRetry: refreshProjects })))
  if (projects && !projects.length) return frame(h('div', { className: 'rk' }, style, h(Empty, { onPrompt: embedded ? null : promptFromPage, onNew: () => createBeat(), chatOpen: !embedded && mode === 'rail' })))
  if (!view) {
    return frame(h('div', { className: 'rk' }, style, h('div', { className: 'rk-in', 'aria-busy': true },
      h('div', { className: 'rk-skel', style: { height: 40, width: '40%' } }), h('div', { className: 'rk-skel', style: { height: 76 } }),
      [0, 1, 2, 3].map(i => h('div', { key: i, className: 'rk-skel', style: { animationDelay: `${i * 120}ms` } })))))
  }

  const p = view.project
  const stale = !!render && render.rev !== view.rev
  const flockRender = render ? {
    events: render.flock_events || {},
    kick_onsets: render.kick_onsets || [],
    active_combos: render.flock_active_combos || [],
    loop_seconds: render.duration_samples && render.sample_rate ? render.duration_samples / render.sample_rate : p.bars * 4 * 60 / p.bpm
  } : null
  const lt = lit?.tracks || {}
  return frame(h('div', { className: 'rk', ref: root, tabIndex: -1, onKeyDown: onKey },
    style,
    h('div', { key: p.name, className: 'rk-in' },
       h(Transport, { ctx, view, projects, playing, canPlay: !!buffer, rendering, match, pending: pendingEdits > 0, saveFailed, onRetry: retrySave, renderMode, onRenderMode: setRenderMode,
        onNew: () => createBeat(), renaming, renameError, onRenameStart: () => { setRenameError(null); setRenaming(true) },
        onRenameCommit: renameBeat, onRenameCancel: () => { setRenaming(false); setRenameError(null) },
        onPick: nm => { setRenaming(false); pick(nm) }, onRename: () => { setRenameError(null); setRenaming(true) },
        onDuplicate: () => createBeat(p.name, duplicateName(p.name)), onClear: clearPattern, onDelete: deleteBeat, onUndo: undoOne,
        onPlay: togglePlay, onMeta, onRender: doRender, renderError: renderErr }),
      (renderErr || offline) && h('div', { className: 'rk-banner', role: 'alert' },
        h('b', null, renderErr ? 'Render failed' : 'Connection lost'), h('span', null, renderErr || 'Reconnecting… edits will sync when the engine answers.'),
        renderErr && h('button', { onClick: () => setRenderErr(null) }, 'Dismiss')),
       h(Waveform, { buffer, bars: p.bars, stale, playing, rendered: !!render, phRef, litRef: waveLit }),
       h(Arrangement, { project: p, playing, render, getPosition: () => engine.current?.position() ?? 0, onSections: onArrangement }),
      h('div', { className: 'rk-rack', ref: rack },
        p.tracks.map(t => h(TrackRow, { key: t.id, track: t, lit: lt[t.id], meter: render?.meters?.[t.id], onToggle, onTrack, ctx, credits: status?.kits?.credits }))),
      h(FlockSection, { catalog: flockCatalog, flock: p.flock, collapsed: flockCollapsed, onCollapsed: setFlockCollapsed,
        onTemplate: onFlockTemplate, onChange: onFlockChange, render: flockRender, playing,
        getPosition: () => engine.current?.position() ?? 0, bpm: p.bpm }),
      h(Master, { ctx, project: p, status, onFxParam }))))
}

// ── chat card: the rookery_render result, playable inline ──────────────────
const CARD_CSS = `
.rkc{box-sizing:border-box;width:100%;display:grid;grid-template-columns:38px minmax(0,1fr);gap:4px 12px;align-items:center;max-width:540px;padding:12px 14px 10px;border-radius:12px;background:var(--ui-widget-surface-background,var(--ui-bg-editor));border:1px solid var(--ui-stroke-tertiary);color:var(--ui-text-primary);font-variant-numeric:tabular-nums}
.rkc button{font:inherit;color:inherit;background:none;border:0;padding:0;cursor:pointer}
.rkc button:focus-visible{outline:2px solid var(--ui-accent);outline-offset:2px;border-radius:6px}
.rkc-play{grid-row:1/3;width:38px;height:38px;border-radius:50%!important;display:grid;place-items:center;background:var(--ui-accent)!important;color:var(--dt-primary-foreground,var(--ui-bg-editor))!important;transition:transform .1s}
.rkc-play:hover{transform:scale(1.05);transition:none}
.rkc-play svg{width:14px;height:14px;fill:currentColor}
.rkc-play[data-busy="true"] svg{animation:rk-breathe .9s ease-in-out infinite}
.rkc-h{display:flex;align-items:baseline;gap:8px;min-width:0;font-size:13px}
.rkc-h b{font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.rkc-h span{color:var(--ui-text-tertiary);font-size:11.5px;white-space:nowrap}
.rkc-h .rkc-checks{margin-left:auto;display:flex;align-items:center;gap:6px}
.rkc-grid{position:relative;display:flex;flex-direction:column;gap:2px;padding:3px 0}
.rkc-row{display:grid;gap:1px;height:5px}
.rkc-row i{border-radius:1px;background:var(--ui-bg-tertiary)}
.rkc-row i[data-on="true"]{background:var(--ui-accent);opacity:var(--v,1)}
.rkc-row i[data-bar="true"]{margin-left:3px}
.rkc-ph{position:absolute;top:0;bottom:0;left:0;width:1.5px;background:var(--ui-accent);box-shadow:0 0 8px var(--ui-accent);opacity:0;will-change:transform}
.rkc[data-playing="true"] .rkc-ph{opacity:1}
.rkc-foot{grid-column:2;display:flex;align-items:center;gap:10px;font-size:11px;color:var(--ui-text-quaternary);margin-top:2px;min-width:0;white-space:nowrap}
.rkc-foot span{overflow:hidden;text-overflow:ellipsis;min-width:0}
.rkc-open{margin-left:auto;flex-shrink:0;font-size:11.5px!important;color:var(--ui-text-secondary)!important;padding:3px 8px!important;border-radius:6px;background:var(--ui-bg-quaternary)!important}
.rkc-open:hover{background:var(--ui-control-hover-background)!important}
.rkc .rk-leds{display:flex;gap:3px}
.rkc .rk-led{width:6px;height:6px;border-radius:50%;background:var(--ui-stroke-secondary)}
.rkc .rk-led[data-s="pass"]{background:var(--ui-success,var(--ui-green));box-shadow:0 0 5px color-mix(in srgb,var(--ui-success,var(--ui-green)) 70%,transparent)}
.rkc .rk-led[data-s="fail"]{background:var(--ui-red)}
.rkc .rk-mix{grid-column:1/-1;font-size:10.5px}
.rkc .rk-mix-btn{padding:2px 4px!important;font-size:10.5px}
.rkc .rk-mix-pop{position:static;width:auto;padding:6px;margin-top:4px;box-shadow:var(--shadow-nous,none)}
.rkc .rk-mix-bands{height:6px;margin-bottom:5px}
.rkc .rk-mix-band-labels{font-size:8px;margin-bottom:4px}
.rkc .rk-mix-stats{font-size:10px}
.rkc .rk-mono{font-family:var(--dt-font-mono,ui-monospace,monospace)}
@keyframes rk-breathe{50%{opacity:.4}}
@media (prefers-reduced-motion:reduce){.rkc *{animation:none!important;transition:none!important}}
`

function parseResult(result) {
  if (result && typeof result === 'object') return result
  if (typeof result !== 'string') return null
  try { return JSON.parse(result) } catch {}
  const a = result.indexOf('{'), b = result.lastIndexOf('}')
  if (a >= 0 && b > a) { try { return JSON.parse(result.slice(a, b + 1)) } catch {} }
  return null
}

function MiniGrid({ tracks, phRef }) {
  return h('div', { className: 'rkc-grid', 'aria-hidden': true },
    tracks.slice(0, 8).map(t => {
      const n = String(t.steps || '').length || 16
      const vel = Array.isArray(t.velocity) && t.velocity.length ? t.velocity : [1]
      let k = 0
      return h('div', { key: t.id, className: 'rkc-row', style: { gridTemplateColumns: `repeat(${n}, 1fr)`, opacity: t.mute ? 0.35 : 1 } },
        Array.from(t.steps || '', (c, i) => {
          const on = isHit(c), v = on ? clamp(vel[k++ % vel.length] ?? 1, 0.3, 1) : 0
          return h('i', { key: i, 'data-on': on, 'data-bar': i > 0 && i % 16 === 0, style: on ? { '--v': v } : undefined })
        }))
    }),
    h('div', { className: 'rkc-ph', ref: phRef }))
}

function RenderCard({ file, result, fallback }) {
  const data = useMemo(() => parseResult(result), [result])
  const [phase, setPhase] = useState('idle') // idle | loading | ready | error
  const [playing, setPlaying] = useState(false)
  const eng = useRef(null), ph = useRef(null)
  useEffect(() => {
    const e = new Engine()
    eng.current = e
    e.subs.add(() => setPlaying(e.playing))
    return () => e.dispose()
  }, [])
  useEffect(() => {
    if (!playing) return
    let raf = 0
    const tick = () => {
      const e = eng.current, el = ph.current
      if (e?.buffer && el) el.style.transform = `translateX(${(e.position() / e.buffer.duration) * el.parentElement.clientWidth}px)`
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [playing])

  if (!data || (file && file.kind && file.kind !== 'audio') || phase === 'error') return fallback ?? null

  const toggle = async () => {
    const e = eng.current
    if (e.playing) return e.stop()
    if (!e.buffer) {
      setPhase('loading')
      try {
        const url = await file.resolveUrl()
        e.setBuffer(await e.decode(await (await fetch(url)).arrayBuffer()))
        setPhase('ready')
      } catch { setPhase('error'); return }
    }
    e.play()
  }
  const report = data.report || null
  const states = CHECKS.map(([k]) => !report ? 'none' : report[k]?.pass ? 'pass' : 'fail')
  const passed = states.filter(s => s === 'pass').length
  const failed = CHECKS.filter(([k]) => report && report[k] && !report[k].pass).map(([, l]) => l)
  const tracks = Array.isArray(data.tracks) ? data.tracks : []
  const meta = [data.bpm && `${data.bpm} BPM`, data.bars && `${data.bars} bars`, data.swing ? `swing ${swingPct(data.swing)}%` : null].filter(Boolean).join(' · ')
  return h('div', { className: 'rkc', 'data-playing': playing },
    h('style', null, CARD_CSS),
    h('button', { className: 'rkc-play', 'data-busy': phase === 'loading', 'aria-label': playing ? 'Stop' : `Play ${data.name || 'loop'}`, onClick: toggle }, playing ? h(Icon.stop) : h(Icon.play)),
    h('div', { className: 'rkc-h' },
      h('b', null, data.name || file?.name || 'Rookery loop'),
      report && h('span', { className: 'rkc-checks', title: failed.length ? `Failed: ${failed.join(', ')}` : 'All checks pass' },
        h('span', { className: 'rk-leds' }, states.map((s, i) => h('i', { key: i, className: 'rk-led', 'data-s': s }))), `${passed}/6`)),
    tracks.length ? h(MiniGrid, { tracks, phRef: ph }) : h('div', { className: 'rkc-grid' }, h('div', { className: 'rkc-ph', ref: ph })),
    h('div', { className: 'rkc-foot' },
      meta && h('span', null, meta),
      h(MixReport, { mix: data.mix }),
      data.hash && h('span', { className: 'rk-mono', title: data.rev != null ? `Render hash · rev ${data.rev}` : undefined }, '#' + shortHash(data.hash)),
      data.wav_hash && h('span', { className: 'rk-mono', title: `Audio hash (SHA-256 of the WAV bytes): ${data.wav_hash}` }, 'audio #' + shortHash(data.wav_hash)),
      h('button', { className: 'rkc-open', onClick: () => requestFocus(data.name) }, 'Open in Rookery')))
}

export default {
  id: ID,
  name: 'Rookery',
  register(ctx) {
    ctx.registerMany([
      { id: 'page', area: ROUTES_AREA, data: { path: '/rookery' }, render: () => h(RookeryPage, { ctx }) },
      { id: 'nav', area: SIDEBAR_NAV_AREA, data: { path: '/rookery', label: 'Rookery', codicon: 'pulse' } }
    ])
    // Older Desktops don't export the area; the page still works there.
    if (typeof sdk.TOOL_MEDIA_RENDERER_AREA === 'string') {
      ctx.register({ id: 'render-card', area: sdk.TOOL_MEDIA_RENDERER_AREA, data: { tools: ['rookery_render'], render: props => h(RenderCard, props) } })
    }
  }
}
