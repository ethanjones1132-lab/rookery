import { birds, combos, corvus, registers, secretUnlock, templates } from './birds.js'
import { detectActiveCombos, isCorvusUnlocked } from './flock-synth.js'

export const FLOCK_CSS = `
.fk{box-sizing:border-box;width:100%;min-width:0;color:var(--ui-text-primary);font:inherit;--fk-pad:clamp(10px,2vw,24px)}
.fk *{box-sizing:border-box}
.fk button,.fk select,.fk input{font:inherit;color:inherit}
.fk button{border:0;background:none;cursor:pointer}
.fk button:focus-visible,.fk select:focus-visible,.fk input:focus-visible,.fk [tabindex]:focus-visible{outline:2px solid var(--ui-accent);outline-offset:2px;border-radius:5px}
.fk-head{display:flex;align-items:center;gap:12px;flex-wrap:wrap;padding:10px var(--fk-pad);border-bottom:1px solid var(--ui-stroke-tertiary)}
.fk-title{font-size:15px;font-weight:650;letter-spacing:.01em;margin-right:4px}
.fk-fields{display:flex;align-items:center;gap:8px;flex-wrap:wrap;min-width:0}
.fk-field{display:flex;align-items:center;gap:6px;font-size:11.5px;color:var(--ui-text-tertiary)}
.fk select{max-width:150px;padding:5px 8px;border:1px solid var(--ui-stroke-secondary);border-radius:6px;background:var(--ui-bg-input,var(--ui-bg-tertiary));font-size:12px}
.fk-progression{display:flex;gap:4px;align-items:center}
.fk-progression button{padding:4px 7px;border:1px solid var(--ui-stroke-tertiary);border-radius:5px;background:var(--ui-bg-tertiary);font-size:11px}
.fk-progression button:hover,.fk-field select:hover{border-color:var(--ui-stroke-secondary)}
.fk-meter{display:flex;align-items:center;gap:6px;margin-left:auto;position:relative}
.fk-meter-label{font-size:10.5px;letter-spacing:.05em;text-transform:uppercase;color:var(--ui-text-quaternary)}
.fk-dots{display:flex;align-items:center;gap:5px}
.fk-dot{width:8px;height:8px;padding:0!important;border-radius:50%;background:var(--ui-stroke-secondary)!important;position:relative}
.fk-dot[data-near=true]{background:var(--ui-accent)!important;animation:fk-pulse 1.4s ease-in-out infinite}
.fk-dot[data-found=true]{background:var(--ui-success,var(--ui-green))!important}
.fk-discoveries{position:absolute;z-index:20;right:0;top:calc(100% + 8px);width:min(270px,80vw);padding:10px;border:1px solid var(--ui-stroke-tertiary);border-radius:8px;background:var(--ui-bg-elevated);box-shadow:0 8px 22px color-mix(in srgb,var(--ui-base) 18%,transparent);font-size:11.5px}
.fk-discoveries b{display:block;margin-bottom:5px}.fk-discoveries p{margin:4px 0;color:var(--ui-text-secondary)}
.fk-scene{position:relative;margin:0 var(--fk-pad);overflow:hidden;border-bottom:1px solid var(--ui-stroke-tertiary)}
.fk-sky{position:relative;height:60px;overflow:hidden;display:flex;align-items:center;justify-content:center;color:var(--ui-text-quaternary)}
.fk-sky[data-combo=night_shift]{background:color-mix(in srgb,var(--ui-text-primary) 4%,transparent)}
.fk-sky[data-combo=night_shift]::before{content:'';position:absolute;right:17%;top:10px;width:21px;height:21px;border-radius:50%;background:var(--ui-text-secondary);box-shadow:-6px -2px 0 0 var(--ui-bg-editor)}
.fk-sky[data-combo=night_shift]::after{content:'·  ✦  ·';position:absolute;left:20%;top:13px;color:var(--ui-text-secondary);font-size:12px;animation:fk-glimmer 1.4s ease-in-out infinite alternate}
.fk-sky[data-combo=shiny_things]::after{content:'◇  ·  ◇';position:absolute;right:12%;top:15px;color:var(--ui-text-secondary);font-size:13px;animation:fk-glimmer 1.1s ease-in-out infinite alternate}
.fk-sky[data-combo=back_and_forth]::after{content:'♫';position:absolute;left:18%;top:17px;color:var(--ui-text-secondary);font-size:14px;animation:fk-bubble 1.4s ease-in-out infinite}
.fk-sky[data-combo=two_basses]::after{content:'♪  ↔  ♪';position:absolute;left:17%;top:12px;color:var(--ui-text-tertiary);font-size:13px;animation:fk-bubble 1.2s ease-in-out infinite}
.fk-sky[data-combo=lo_fi_window]{box-shadow:inset 0 -1px 0 color-mix(in srgb,var(--ui-text-primary) 14%,transparent)}
.fk-weather{position:absolute;inset:0;pointer-events:none;overflow:hidden}
.fk-weather i{position:absolute;display:block;width:3px;height:3px;border-radius:50%;background:color-mix(in srgb,var(--ui-text-primary) 52%,transparent);opacity:.28;animation:fk-weather-drift 5s ease-in-out infinite alternate;animation-delay:calc(var(--i)*-137ms)}
.fk-weather[data-kind=rain] i{width:1px;height:12px;border-radius:2px;opacity:.34;transform:rotate(18deg)}
.fk-weather[data-kind=wind] i{width:20px;height:1px;border-radius:2px;opacity:.28}
.fk-banner{position:relative;z-index:2;display:flex;align-items:center;gap:8px;padding:6px 12px;border:1px solid var(--ui-stroke-tertiary);border-radius:999px;background:color-mix(in srgb,var(--ui-bg-editor) 84%,transparent);font-size:12px;color:var(--ui-text-secondary)}
.fk-error{margin:8px var(--fk-pad) 0;padding:8px 11px;border:1px solid color-mix(in srgb,var(--ui-red) 40%,transparent);border-radius:7px;background:color-mix(in srgb,var(--ui-red) 10%,transparent);color:var(--ui-red);font-size:12px}
.fk-banner strong{font-weight:650;color:var(--ui-text-primary)}
.fk-swarm{position:absolute;inset:0;pointer-events:none;overflow:hidden}
.fk-swarm i{position:absolute;left:calc(50% + (var(--i) - 20)*3px);top:50%;width:5px;height:3px;border-radius:50% 50% 45% 10%;background:var(--ui-text-primary);opacity:.55;animation:fk-swarm-flight 2.6s ease-in-out both;animation-delay:calc(var(--i)*13ms)}
.fk-wire-wrap{position:relative;height:190px}
.fk-collapsed-strip{display:none;align-items:center;gap:8px;position:relative;height:40px;padding:2px 12px;overflow:hidden;border-bottom:1px solid var(--ui-stroke-tertiary)}
.fk-collapsed-strip::before{content:'';position:absolute;left:0;right:0;top:25px;border-top:1px solid var(--ui-stroke-secondary)}
.fk-collapsed-strip svg{position:relative;z-index:1;width:30px;height:36px;overflow:visible}
.fk-wire{display:block;width:100%;height:100%;overflow:visible;transform-origin:50% 50%}
.fk-post{stroke:var(--ui-stroke-tertiary);stroke-width:3;fill:none;stroke-linecap:round}
.fk-wire-line{stroke:var(--ui-stroke-secondary);stroke-width:1.4;fill:none;stroke-linecap:round;vector-effect:non-scaling-stroke}
.fk-wire-hit{stroke:var(--ui-stroke-secondary);stroke-width:18;fill:none;opacity:.01;cursor:pointer}
.fk-perch-tick{stroke:var(--ui-stroke-tertiary);stroke-width:1.2;stroke-linecap:round}
.fk-bird{cursor:pointer;transform-box:fill-box;transform-origin:50% 80%;outline:none}
.fk-bird[data-present=true]{animation:fk-idle 3.1s ease-in-out infinite;animation-delay:calc(var(--fk-delay,0)*-1ms)}
.fk-bird[data-present=true][data-role=bass]{animation-name:fk-nod}
.fk-bird[data-present=true][data-role=lead]{animation-name:fk-hop}
.fk-bird[data-present=true][data-role=arp]{animation-name:fk-twitch}
.fk-bird[data-muted=true]{opacity:.62;animation:none!important}
.fk-bird[data-solo-dim=true]{opacity:.35}
.fk-bird[data-speaking=true] .fk-beak-lower{transform:translateY(var(--fk-open,0px))}
.fk-bird[data-speaking=true] .fk-wing{animation:fk-wing .22s ease-in-out infinite alternate}
.fk-bird[data-wing-lift=true] .fk-wing{animation:fk-winglift .8s ease-in-out both}
.fk-bird[data-look=true] .fk-head{transform:rotate(12deg)}
.fk-species-jackdaw .fk-eye{fill:color-mix(in srgb,var(--ui-text-primary) 55%,var(--ui-bg-editor))}
.fk-bird[data-speaking=true] .fk-propeller{animation:fk-prop-spin .45s linear infinite;transform-origin:20px -69px}
.fk-bird[data-present=true] .fk-eye,.fk-bird[data-present=true] .fk-eye-dot{animation:fk-blink 4.7s ease-in-out infinite;animation-delay:calc(var(--fk-delay,0)*-1ms)}
.fk-body{transform-origin:0 -22px;animation:fk-breathe 3.1s ease-in-out infinite}
.fk-bird[data-bird=cinder] .fk-costume-line{transform-origin:4px -8px;animation:fk-chain 1.1s ease-in-out infinite}
.fk-bird[data-bird=sable] .fk-head{animation:fk-tip 5.2s ease-in-out infinite;transform-origin:20px -50px}
.fk-bird[data-bird=hush] .fk-eye{transform:scaleY(.66)}
.fk-bird[data-speaking=true][data-bird=echo] .fk-head{transform:rotate(-10deg)}
.fk-bird[data-high=true][data-bird=glint] .fk-head{transform:rotate(10deg)}
.fk-bird[data-bird=moss] .fk-costume-line{transform-origin:8px -6px;animation:fk-sway 2.4s ease-in-out infinite}
.fk-bird[data-song-change=true]{animation:fk-ruffle .22s ease-out}
.fk-song-badge{font-size:12px;font-weight:700;fill:var(--ui-text-secondary);opacity:0}
.fk-bird[data-motion=song] .fk-song-badge{opacity:1;animation:fk-badge .22s ease-out}
.fk-bird[data-motion=land]{animation:fk-land .42s cubic-bezier(.2,.8,.2,1) both}
.fk-bird[data-motion=leave]{animation:fk-leave .36s ease-in both}
.fk-body-fill{fill:color-mix(in srgb,var(--ui-text-primary) 88%,transparent)}
.fk-body-light{fill:color-mix(in srgb,var(--ui-text-primary) 70%,transparent)}
.fk-cutout{fill:color-mix(in srgb,var(--ui-bg-editor) 80%,var(--ui-text-primary))}
.fk-eye{fill:var(--ui-bg-editor);stroke:var(--ui-text-primary);stroke-width:1.2}
.fk-eye-dot{fill:var(--ui-text-primary)}
.fk-eye-closed{fill:none;stroke:var(--ui-text-primary);stroke-width:1.5;stroke-linecap:round;display:none}
.fk-bird[data-muted=true] .fk-eye{display:none}.fk-bird[data-muted=true] .fk-eye-dot{display:none}.fk-bird[data-muted=true] .fk-eye-closed{display:block}
.fk-beak-upper,.fk-beak-lower{fill:color-mix(in srgb,var(--ui-text-primary) 94%,transparent)}
.fk-beak-lower{transform-origin:0 0;transition:transform .045s linear}
.fk-costume{fill:var(--fk-costume-color,var(--ui-accent));stroke:var(--fk-costume-color,var(--ui-accent));stroke-width:2;stroke-linecap:round;stroke-linejoin:round}
.fk-costume-line{fill:none;stroke:var(--fk-costume-color,var(--ui-accent));stroke-width:3;stroke-linecap:round;stroke-linejoin:round}
.fk-bird[data-muted=true] .fk-costume,.fk-bird[data-muted=true] .fk-costume-line{opacity:.4}
.fk-shadow{fill:color-mix(in srgb,var(--ui-accent) 23%,transparent);opacity:0}
.fk-bird[data-solo=true] .fk-shadow{opacity:1}
.fk-wire-tools{position:absolute;left:0;right:0;bottom:9px;pointer-events:none}
.fk-slot-tools{position:absolute;transform:translateX(-50%);display:flex;gap:3px;pointer-events:auto;opacity:0;transition:opacity .12s ease}
.fk-slot-tools:hover,.fk-slot-tools:focus-within{opacity:1}
.fk-slot-tools button{width:20px;height:18px;border-radius:4px;background:var(--ui-bg-elevated);border:1px solid var(--ui-stroke-tertiary);font-size:9px;font-weight:700;color:var(--ui-text-quaternary)}
.fk-slot-tools button[aria-pressed=true][data-kind=m]{color:var(--ui-orange);background:color-mix(in srgb,var(--ui-orange) 15%,var(--ui-bg-elevated))}
.fk-slot-tools button[aria-pressed=true][data-kind=s]{color:var(--ui-yellow);background:color-mix(in srgb,var(--ui-yellow) 15%,var(--ui-bg-elevated))}
.fk-empty-copy{position:absolute;left:50%;top:38%;transform:translate(-50%,-50%);width:min(420px,80%);text-align:center;font-size:12px;line-height:1.5;color:var(--ui-text-tertiary);pointer-events:none}
.fk-empty-actions{pointer-events:auto;display:flex;justify-content:center;gap:6px;flex-wrap:wrap;margin-top:9px}
.fk-empty-actions button{padding:5px 8px;border:1px solid var(--ui-stroke-tertiary);border-radius:999px;background:var(--ui-bg-tertiary);font-size:10.5px;color:var(--ui-text-secondary)}
.fk-roster{padding:10px var(--fk-pad) 14px}
.fk-roster-head{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;color:var(--ui-text-quaternary);font-size:10.5px;letter-spacing:.06em;text-transform:uppercase}
.fk-roster-grid{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:6px}
.fk-card{position:relative;display:flex;align-items:center;gap:8px;min-width:0;padding:6px 8px!important;text-align:left;border-radius:8px;background:color-mix(in srgb,var(--ui-bg-tertiary) 66%,transparent)!important;box-shadow:inset 0 0 0 1px var(--ui-stroke-quaternary)}
.fk-card:hover{background:var(--ui-bg-tertiary)!important}
.fk-card[data-on-wire=true]{box-shadow:inset 0 0 0 1px var(--ui-stroke-secondary)}
.fk-card[data-new=true]::after{content:'';position:absolute;right:7px;top:7px;width:5px;height:5px;border-radius:50%;background:var(--ui-accent)}
.fk-card-svg{width:36px;height:38px;flex:none;overflow:visible}
.fk-card-copy{min-width:0;display:flex;flex-direction:column;gap:2px}
.fk-card-copy b{font-size:11.5px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.fk-role{font-size:9.5px;color:var(--ui-text-quaternary);text-transform:uppercase;letter-spacing:.04em}
.fk-role-start{border-left:1px solid var(--ui-stroke-tertiary);padding-left:10px;margin-left:2px}
.fk-secret{border:1px dashed var(--ui-stroke-secondary)!important;background:transparent!important;color:var(--ui-text-quaternary)!important;justify-content:center}
.fk-controls{display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap;padding:9px var(--fk-pad) 12px;border-top:1px solid var(--ui-stroke-tertiary)}
.fk-combo-label{font-size:11px;color:var(--ui-text-secondary)}
.fk-combo-banner{display:flex;align-items:center;gap:8px;min-width:0}
.fk-pop{position:absolute;z-index:25;width:230px;padding:10px;border:1px solid var(--ui-stroke-tertiary);border-radius:9px;background:var(--ui-bg-elevated);box-shadow:0 9px 24px color-mix(in srgb,var(--ui-base) 18%,transparent);font-size:11.5px}
.fk-pop p{margin:3px 0 8px;color:var(--ui-text-secondary);line-height:1.4}
.fk-pop-row{display:flex;gap:4px;align-items:center;margin:6px 0}
.fk-pop-row button{padding:4px 7px;border:1px solid var(--ui-stroke-tertiary);border-radius:5px;background:var(--ui-bg-tertiary);font-size:10.5px}
.fk-pop-row input{width:100%;accent-color:var(--ui-accent)}
.fk-fact{position:absolute;z-index:30;padding:7px 9px;border-radius:7px;background:var(--ui-bg-elevated);border:1px solid var(--ui-stroke-tertiary);font-size:11px;color:var(--ui-text-secondary);pointer-events:none;max-width:220px}
.fk-collapse{margin-left:auto;padding:4px 8px!important;border-radius:5px;color:var(--ui-text-tertiary)!important;font-size:11px}
.fk-collapse:hover{background:var(--ui-control-hover-background)!important}
.fk[data-collapsed=true] .fk-scene{display:none}
.fk[data-collapsed=true] .fk-collapsed-strip{display:flex}
.fk[data-collapsed=true] .fk-sky,.fk[data-collapsed=true] .fk-roster,.fk[data-collapsed=true] .fk-controls{display:none}
.fk[data-collapsed=true] .fk-wire-wrap{height:40px}
.fk[data-rendering=true] .fk-wire-line{stroke-dasharray:2 8;animation:fk-tune 1.4s linear infinite}
@keyframes fk-idle{50%{transform:translateY(-1.5px)}}
@keyframes fk-breathe{50%{transform:scaleY(1.025)}}
@keyframes fk-blink{0%,95%,100%{opacity:1}97%,98%{opacity:0}}
@keyframes fk-chain{50%{transform:rotate(8deg)}}
@keyframes fk-tip{0%,88%,100%{transform:rotate(0)}92%{transform:rotate(-9deg)}}
@keyframes fk-sway{50%{transform:rotate(5deg)}}
@keyframes fk-glimmer{to{transform:translateY(-3px);opacity:.45}}
@keyframes fk-bubble{50%{transform:translateY(-4px);opacity:.5}}
@keyframes fk-nod{50%{transform:translateY(2px) rotate(1deg)}}
@keyframes fk-hop{50%{transform:translateY(-4px)}}
@keyframes fk-twitch{25%{transform:translateY(-1px) rotate(-1deg)}75%{transform:translateY(1px) rotate(1deg)}}
@keyframes fk-wing{to{transform:rotate(-9deg)}}
@keyframes fk-winglift{0%{transform:rotate(0)}45%{transform:rotate(-18deg)}100%{transform:rotate(0)}}
@keyframes fk-land{0%{opacity:0;transform:translate(70px,-120px) rotate(18deg)}72%{opacity:1;transform:translate(-4px,5px) rotate(-2deg)}100%{transform:none}}
@keyframes fk-leave{to{opacity:0;transform:translate(-55px,-80px) rotate(-18deg)}}
@keyframes fk-ruffle{50%{transform:rotate(6deg) scale(1.06)}}
@keyframes fk-badge{0%{opacity:0;transform:translateY(4px)}60%{opacity:1;transform:translateY(-4px)}100%{opacity:0;transform:translateY(-7px)}}
@keyframes fk-prop-spin{to{transform:rotate(360deg)}}
@keyframes fk-pulse{50%{transform:scale(1.45);opacity:.58}}
@keyframes fk-weather-drift{to{transform:translate(9px,7px);opacity:.55}}
@keyframes fk-swarm-flight{0%{transform:translate(0,14px) rotate(0) scale(.5);opacity:0}40%{opacity:.75}100%{transform:translate(calc((var(--i) - 20)*4px),-8px) rotate(24deg) scale(.2);opacity:0}}
@keyframes fk-tune{to{stroke-dashoffset:-30}}
@media(max-width:1100px){.fk-roster-grid{grid-template-columns:repeat(4,minmax(0,1fr))}.fk-title{margin-right:0}}
@media(max-width:660px){.fk-roster-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.fk-head{gap:8px}.fk-meter{margin-left:0}.fk-wire-wrap{height:165px}}
@media(prefers-reduced-motion:reduce){.fk *{animation:none!important;transition:none!important}.fk-wire[data-vibrate=true]{transform:none!important}.fk-swarm i{display:none}.fk-swarm::after{content:'✦';position:absolute;left:50%;top:50%;color:var(--ui-text-secondary);opacity:.5}.fk-wire-line{stroke-dasharray:none!important}}
`

const SVG_NS = 'http://www.w3.org/2000/svg'
const SVG_TAGS = new Set(['svg', 'g', 'path', 'ellipse', 'circle', 'line', 'rect', 'polyline', 'polygon', 'title', 'text'])
function createElement(tag, props, ...children) {
  if (typeof tag === 'function') return tag({ ...(props || {}), children })
  const element = SVG_TAGS.has(tag) ? document.createElementNS(SVG_NS, tag) : document.createElement(tag)
  for (const [key, value] of Object.entries(props || {})) {
    if (value == null || value === false) continue
    if (key === 'ref') { value(element); continue }
    if (key === 'className') { element.setAttribute('class', value); continue }
    if (key === 'style' && typeof value === 'object') {
      for (const [name, styleValue] of Object.entries(value)) {
        if (name.startsWith('--')) element.style.setProperty(name, styleValue)
        else element.style[name] = styleValue
      }
      continue
    }
    if (/^on[A-Z]/.test(key) && typeof value === 'function') { element.addEventListener(key.slice(2).toLowerCase(), value); continue }
    if (key === 'draggable' || key === 'hidden') { element.setAttribute(key, value ? 'true' : 'false'); continue }
    if (key === 'tabIndex') { element.setAttribute('tabindex', value); continue }
    element.setAttribute(key, value === true ? 'true' : String(value))
  }
  const append = child => {
    if (Array.isArray(child)) { child.forEach(append); return }
    if (child == null || child === false || child === true) return
    element.appendChild(typeof child === 'string' || typeof child === 'number' ? document.createTextNode(String(child)) : child)
  }
  children.forEach(append)
  return element
}
const h = createElement

const ROLE_ORDER = ['bass', 'keys', 'pad', 'lead', 'arp', 'call']
  const SLOT_X = [100, 260, 420, 580, 740, 900, 940]
const clamp = (n, min, max) => Math.max(min, Math.min(max, n))
const tokenFor = bird => bird.costume?.token || '--ui-accent'
const birdById = id => birds.find(bird => bird.id === id) || (id === corvus.id ? corvus : null)
const millis = () => globalThis.performance?.now?.() ?? 0

function wireY(x) { return 128 + 24 * (1 - ((x - 500) / 500) ** 2) }
function normalizedFlock(flock) {
  const next = { key: 'D', scale: 'dorian', progression: ['i', 'iv', 'VII', 'III'], weather: 'clear', perches: Array(6).fill(null), seen: [], unlocked: [], ...flock }
  next.perches = [...(next.perches || [])]
  while (next.perches.length < (isCorvusUnlocked(next) ? 7 : 6)) next.perches.push(null)
  return next
}

function useSlot(flock) { return flock.perches.findIndex(perch => !perch) }
function firstFreeSlot(flock) { return useSlot(flock) }

function BirdRig({ bird, x, y, perch, motion, parliament, parliamentCombo, nightOwl, compact, stretch, onSong, onKeyDown, onContext, onDragStart, onFact }) {
  const species = bird.species
  const isOnWire = !!perch
  const muted = !!perch?.mute
  const solo = !!perch?.solo
  const widthCompensation = stretch ? Math.min(1, 1000 / (window.innerWidth || 1000)) : 1
  const transform = `translate(${x} ${y}) scale(${compact ? 0.42 : widthCompensation} ${compact ? 0.42 : 1})`
  const head = bird.role === 'call' ? 'M 5 -48 C 7 -62 25 -63 31 -52 C 28 -42 14 -38 5 -48 Z'
    : species === 'magpie' ? 'M 5 -49 C 6 -63 25 -63 31 -51 C 29 -41 14 -38 5 -49 Z'
      : species === 'raven' ? 'M 4 -47 C 5 -62 26 -64 32 -51 C 30 -40 15 -37 4 -47 Z'
        : species === 'jackdaw' ? 'M 6 -48 C 8 -61 24 -62 30 -51 C 28 -42 15 -39 6 -48 Z'
          : 'M 5 -48 C 6 -63 26 -62 31 -50 C 28 -40 14 -38 5 -48 Z'
  const body = species === 'raven' ? 'M -31 -26 C -26 -43 -7 -43 14 -31 C 29 -22 24 -7 5 -4 L -21 -6 C -36 -10 -40 -19 -31 -26 Z'
    : 'M -30 -25 C -23 -40 -4 -41 15 -30 C 28 -22 24 -8 5 -5 L -20 -7 C -34 -11 -39 -19 -30 -25 Z'
  const beak = species === 'crow' || species === 'raven' ? 'M 30 -51 Q 45 -53 49 -47 Q 39 -43 31 -45 Z' : species === 'chough' ? 'M 29 -51 Q 42 -57 44 -50 Q 39 -43 31 -44 Z' : 'M 29 -50 Q 40 -52 44 -47 Q 38 -44 30 -45 Z'
  const costume = bird.id === 'bramble' ? h('path', { className: 'fk-costume', d: 'M 4 -57 Q 18 -68 34 -58 L 32 -53 L 5 -53 Z' })
    : bird.id === 'cinder' ? h('path', { className: 'fk-costume-line', d: 'M -6 -10 Q 7 -5 15 -13 M 4 -8 L 7 -4' })
      : bird.id === 'quill' ? h('g', null, h('path', { className: 'fk-costume', d: 'M 4 -58 Q 20 -69 34 -57 L 31 -53 L 6 -54 Z' }), h('circle', { className: 'fk-costume-line', cx: 14, cy: -48, r: 3.5, fill: 'none' }), h('circle', { className: 'fk-costume-line', cx: 25, cy: -48, r: 3.5, fill: 'none' }), h('path', { className: 'fk-costume-line', d: 'M 17 -48 L 22 -48' }))
        : bird.id === 'sable' ? h('path', { className: 'fk-costume', d: 'M 8 -66 L 30 -66 L 30 -58 L 34 -58 L 34 -53 L 4 -53 L 4 -58 L 8 -58 Z' })
          : bird.id === 'jinx' ? h('path', { className: 'fk-costume', d: 'M 7 -56 L 4 -67 L 13 -59 L 17 -72 L 21 -59 L 31 -67 L 28 -55 Z' })
            : bird.id === 'glint' ? h('g', null, h('circle', { className: 'fk-costume-line', cx: 24, cy: -49, r: 6, fill: 'none' }), h('path', { className: 'fk-costume-line', d: 'M 29 -45 L 34 -41' }))
              : bird.id === 'hush' ? h('path', { className: 'fk-costume', d: 'M 5 -56 Q 12 -67 22 -61 Q 28 -58 32 -53 L 8 -52 Z M 22 -61 Q 29 -68 29 -60 Q 27 -56 24 -57 Z' })
                : bird.id === 'moss' ? h('path', { className: 'fk-costume-line', d: 'M 0 -10 Q 10 -4 18 -11 L 20 -6 Q 8 1 -1 -5 Z' })
                  : bird.id === 'tick' ? h('g', null, h('path', { className: 'fk-costume-line', d: 'M 8 -52 Q 19 -61 31 -52 M 8 -52 L 10 -47 M 31 -52 L 29 -47' }), h('path', { className: 'fk-costume', d: 'M 8 -52 L 13 -50 L 12 -46 L 8 -47 Z M 26 -50 L 31 -52 L 31 -47 L 27 -46 Z' }))
                    : bird.id === 'pip' ? h('g', null, h('path', { className: 'fk-costume', d: 'M 6 -56 Q 18 -64 31 -56 L 29 -53 L 7 -53 Z' }), h('path', { className: 'fk-costume-line fk-propeller', d: 'M 19 -59 L 20 -69 M 20 -69 L 26 -72 M 20 -69 L 14 -72' }))
                      : bird.id === 'echo' ? h('path', { className: 'fk-costume-line', d: 'M 5 -42 Q -1 -26 4 -9 M 31 -39 Q 38 -24 32 -7' })
                        : bird.id === 'wren_not' ? h('g', null, h('circle', { className: 'fk-costume', cx: 8, cy: -54, r: 3 }), h('path', { className: 'fk-costume-line', d: 'M 8 -54 L 3 -60 M 8 -54 L 15 -59 M 8 -54 L 2 -49' }))
                          : bird.id === 'corvus' ? h('path', { className: 'fk-costume', d: 'M 4 -56 L 7 -68 L 15 -61 L 20 -72 L 25 -61 L 34 -68 L 33 -55 Z' })
                            : h('path', { className: 'fk-costume', d: 'M 8 -58 Q 19 -68 31 -58 L 28 -53 L 10 -53 Z' })
  const wig = parliament ? h('g', { className: 'fk-costume' }, h('path', { d: 'M 4 -58 Q 18 -65 33 -58 L 31 -55 L 7 -55 Z' }), h('circle', { cx: 9, cy: -62, r: 3 }), h('circle', { cx: 18, cy: -65, r: 3 }), h('circle', { cx: 28, cy: -62, r: 3 })) : null
  const cap = muted && nightOwl ? h('path', { className: 'fk-costume', d: 'M 7 -56 Q 18 -66 30 -56 L 27 -53 L 8 -53 Z M 29 -56 Q 36 -57 35 -53 Q 32 -50 29 -53 Z' }) : null
  return h('g', {
    className: `fk-bird fk-species-${species}`, transform, 'data-bird': bird.id,
    'data-slot-focus': isOnWire ? perch.slot : undefined,
    'data-role': bird.role, 'data-present': isOnWire, 'data-muted': muted,
    'data-wing-lift': false, 'data-parliament': !!parliamentCombo,
    'data-solo': solo, 'data-solo-dim': motion?.soloed && !solo,
    'data-speaking': false, 'data-motion': motion?.birdId === bird.id ? motion.kind : undefined,
    'aria-label': `${bird.name}, ${bird.role}${perch ? `, song ${perch.song || 'A'}` : ''}`,
    role: isOnWire ? 'button' : undefined, tabindex: isOnWire ? 0 : -1, draggable: isOnWire,
    style: { '--fk-costume-color': `var(${tokenFor(bird)})`, '--fk-delay': String((bird.id.length * 419) % 3300) },
    onClick: event => { event.stopPropagation(); if (perch) onSong(bird.id) },
    onKeyDown: event => onKeyDown(event, bird.id),
    onContextMenu: event => { event.preventDefault(); event.stopPropagation(); onContext(event, bird) },
    onDragStart: event => onDragStart(event, bird.id, true),
    onPointerEnter: event => onFact(event, bird), onPointerLeave: onFact.clear
  },
    h('ellipse', { className: 'fk-shadow', cx: 0, cy: -1, rx: 24, ry: 3 }),
    h('path', { className: 'fk-post fk-legs', d: 'M -8 -6 L -9 0 L -13 0 M 10 -6 L 10 0 L 14 0' }),
    h('path', { className: 'fk-body-fill fk-body', d: body }),
    h('path', { className: 'fk-body-fill fk-tail', d: 'M -28 -20 L -47 -14 L -31 -10 Z' }),
    species === 'magpie' ? h('path', { className: 'fk-cutout', d: 'M -23 -20 Q -7 -29 7 -18 L -1 -8 Q -16 -9 -23 -20 Z' }) : null,
    species === 'jackdaw' ? h('path', { className: 'fk-body-light', d: 'M 11 -58 Q 23 -62 29 -52 L 24 -48 Q 18 -52 11 -51 Z' }) : null,
    species === 'raven' ? h('path', { className: 'fk-body-fill', d: 'M -10 -15 Q -5 -5 -1 -10 L -6 -18 L 1 -8 L 5 -18 L 2 -7 L 10 -15 L 5 -24 Z' }) : null,
    h('g', { className: 'fk-wing' }, h('path', { className: 'fk-body-light', d: 'M -23 -24 Q -10 -38 5 -26 Q -2 -14 -20 -12 Z' })),
    h('g', { className: 'fk-head' },
      h('path', { className: 'fk-body-fill', d: head }),
      species === 'rook' ? h('path', { className: 'fk-body-light', d: 'M 28 -49 Q 35 -53 42 -49 L 39 -45 L 29 -45 Z' }) : null,
      h('circle', { className: 'fk-eye', cx: 23, cy: -52, r: 3.7 }), h('circle', { className: 'fk-eye-dot', cx: 24, cy: -52, r: 1.5 }),
      h('path', { className: 'fk-eye-closed', d: 'M 19 -51 Q 23 -48 27 -51' }),
      h('path', { className: 'fk-beak-upper', d: beak }),
      h('path', { className: 'fk-beak-lower', d: 'M 30 -45 Q 39 -44 44 -47 Q 39 -42 31 -42 Z' })),
    h('path', { className: 'fk-post', d: 'M 2 -6 L 1 -2 M 12 -6 L 12 -2' }),
    h('g', { className: 'fk-costume-layer' }, costume, cap, parliament ? wig : null),
    perch && h('text', { className: 'fk-song-badge', x: 21, y: -73, 'aria-hidden': true }, perch.song || 'A')
  )
}

function PerchSvg({ project, flock, motion, activeCombos, onSlot, onWireTap, onSong, onKeyDown, onContext, onDragStart, onFact }) {
  const active = flock.perches.slice(0, 6)
  const isUnlocked = isCorvusUnlocked(flock)
  const soloed = flock.perches.some(perch => perch?.solo && !perch.mute)
  const motions = Array.isArray(motion) ? motion : motion ? [motion] : []
  const motionFor = birdId => ({ ...(motions.find(item => item.birdId === birdId) || {}), soloed })
  if (isUnlocked) active.push(flock.perches[6] || { bird: corvus.id, song: 'A', mute: false, solo: false, locked: true })
  const wirePath = `M 42 128 Q 500 174 958 128`
  const birdsOnWire = []
  return h('div', { className: 'fk-wire-wrap' },
    h('svg', {
      className: 'fk-wire', viewBox: '0 0 1000 200', preserveAspectRatio: 'none', role: 'toolbar', 'aria-label': 'The Wire. Use arrow keys to move among six perches.',
      onKeyDown: onKeyDown,
      onDragOver: event => event.preventDefault(),
      onDrop: event => {
        event.preventDefault()
        const data = event.dataTransfer?.getData('text/plain') || ''
        if (!data.startsWith('bird:')) return
        const bounds = event.currentTarget.getBoundingClientRect()
        const fraction = clamp((event.clientX - bounds.left) / bounds.width, 0, 1)
        const slot = clamp(Math.round(fraction * 5), 0, 5)
        onSlot(data.slice(5), slot)
      }
    },
      h('path', { className: 'fk-post', d: 'M 28 173 L 28 92 M 972 173 L 972 92' }),
      h('path', { className: 'fk-wire-line', d: wirePath }),
      h('path', { className: 'fk-wire-line fk-wire-hit', d: wirePath, onClick: onWireTap }),
      Array.from({ length: 6 }, (_, slot) => {
        const x = SLOT_X[slot], y = wireY(x)
        const perch = flock.perches[slot]
        if (perch) {
          const bird = birdById(perch.bird)
          if (bird) {
            const group = BirdRig({ bird, x, y, perch: { ...perch, slot }, motion: motionFor(bird.id), parliament: flock.projectName?.toLowerCase() === 'parliament', parliamentCombo: activeCombos.includes('parliament'), nightOwl: new Date().getHours() >= 23, compact: false, stretch: true, onSong, onKeyDown: (event, id) => onKeyDown(event, slot, id), onContext, onDragStart, onFact })
            group.setAttribute('data-slot-focus', String(slot))
            birdsOnWire.push(group)
          }
        }
        return h('g', { key: `slot-${slot}`, role: 'button', tabindex: perch ? -1 : 0, 'data-slot-focus': perch ? undefined : slot, 'aria-label': perch ? `Perch ${slot + 1}, ${birdById(perch.bird)?.name || 'bird'}` : `Empty perch ${slot + 1}`, onClick: () => { if (!perch) onSlot(null, slot) }, onKeyDown: event => onKeyDown(event, slot, null) },
          h('path', { className: 'fk-perch-tick', d: `M ${x} ${y - 3} L ${x} ${y + 4}` }))
      }),
      isUnlocked && !flock.perches[6] ? h('g', { role: 'button', tabindex: 0, 'data-slot-focus': 6, 'aria-label': 'Seventh perch for Corvus', onClick: () => onSlot(corvus.id, 6) }, h('path', { className: 'fk-perch-tick', d: `M ${SLOT_X[6]} ${wireY(SLOT_X[6]) - 3} L ${SLOT_X[6]} ${wireY(SLOT_X[6]) + 4}` })) : null,
      flock.perches[6] && isUnlocked ? BirdRig({ bird: corvus, x: SLOT_X[6], y: wireY(SLOT_X[6]), perch: { ...flock.perches[6], slot: 6 }, motion: motionFor(corvus.id), parliament: flock.projectName?.toLowerCase() === 'parliament', parliamentCombo: activeCombos.includes('parliament'), nightOwl: false, compact: false, stretch: true, onSong, onKeyDown: (event, id) => onKeyDown(event, 6, id), onContext, onDragStart, onFact }) : null,
      ...birdsOnWire,
      ...motions.filter(item => item.kind === 'leave' && item.bird).map(item => BirdRig({ bird: item.bird, x: item.fromX || 500, y: item.fromY || 128, perch: item.birdPerch, motion: { ...item, soloed: false }, parliament: false, nightOwl: false, compact: false, stretch: true, onSong, onKeyDown, onContext, onDragStart, onFact }))
    ),
    active.map((perch, i) => {
      if (!perch) return null
      if (i === 6 && !flock.perches[6]) return null
      const slot = i, x = SLOT_X[slot] / 10
      const bird = birdById(perch.bird)
      if (!bird) return null
      return h('div', { key: `tools-${slot}`, className: 'fk-wire-tools' }, h('div', { className: 'fk-slot-tools', style: { left: `${x}%` } },
        h('button', { 'data-kind': 'm', 'aria-label': `Mute ${bird.name}`, 'aria-pressed': !!perch.mute, onClick: () => onSlot(bird.id, slot, { mute: !perch.mute }) }, 'M'),
        h('button', { 'data-kind': 's', 'aria-label': `Solo ${bird.name}`, 'aria-pressed': !!perch.solo, onClick: () => onSlot(bird.id, slot, { solo: !perch.solo }) }, 'S')))
    })
  )
}

function BirdCard({ bird, perch, seen, onClick, onDragStart, firstOfRole }) {
  const svgBird = BirdRig({ bird, x: 50, y: 49, perch: null, compact: true, parliament: false, nightOwl: false, onSong: () => {}, onKeyDown: () => {}, onContext: () => {}, onDragStart: () => {}, onFact: () => {} })
  return h('button', {
    className: `fk-card${firstOfRole ? ' fk-role-start' : ''}`, 'data-on-wire': !!perch, 'data-new': !seen,
    draggable: true, 'aria-label': `Add ${bird.name}, ${bird.role}${perch ? ', already on wire' : ''}`,
    onClick: () => onClick(bird.id), onDragStart: event => onDragStart(event, bird.id, false)
  }, h('svg', { className: 'fk-card-svg', viewBox: '0 0 100 54', 'aria-hidden': true }, svgBird),
    h('span', { className: 'fk-card-copy' }, h('b', null, bird.name), h('span', { className: 'fk-role' }, bird.role)))
}

function updatePerch(flock, birdId, slot, patch) {
  const perches = [...flock.perches]
  if (birdId == null) return flock
  const currentSlot = perches.findIndex(perch => perch?.bird === birdId)
  const target = slot == null ? firstFreeSlot(flock) : slot
  if (target < 0 || target >= 7) return flock
  if (currentSlot >= 0) {
    if (patch) { perches[currentSlot] = { ...perches[currentSlot], ...patch }; return { ...flock, perches } }
    if (currentSlot === target) return { ...flock, perches }
    const previous = perches[target]
    perches[target] = perches[currentSlot]
    perches[currentSlot] = previous || null
  } else {
    if (target === 6 && !isCorvusUnlocked(flock)) return flock
    perches[target] = { bird: birdId, song: 'A', mute: false, solo: false }
  }
  const seen = new Set(flock.seen || [])
  seen.add(birdId)
  const corvusOpen = isCorvusUnlocked({ ...flock, seen: [...seen] })
  if (corvusOpen && perches.length < 7) perches.push(null)
  const unlocked = corvusOpen ? [...new Set([...(flock.unlocked || []), 'murmuration'])] : flock.unlocked || []
  return { ...flock, perches, seen: [...seen], unlocked }
}

function cycleSong(flock, birdId) {
  const order = ['A', 'B', 'C']
  const slot = flock.perches.findIndex(perch => perch?.bird === birdId)
  if (slot < 0) return flock
  const perch = flock.perches[slot]
  const next = order[(order.indexOf(perch.song || 'A') + 1) % order.length]
  const perches = [...flock.perches]
  perches[slot] = { ...perch, song: next }
  return { ...flock, perches }
}

function applyTemplate(template, flock) {
  const perches = Array(6).fill(null)
  template.birds.forEach((entry, index) => { perches[index] = { ...entry, mute: false, solo: false } })
  return { ...flock, key: template.key, scale: template.scale, progression: [...template.progression], weather: template.weather, templateId: template.id, perches, seen: [...new Set([...(flock.seen || []), ...template.birds.map(entry => entry.bird)])] }
}

function colorForWeather(weather) { return weather }

export function FlockPanel({ project = {}, flock: inputFlock = {}, onChange = () => {}, playing = false, getPosition = () => 0, render = null, motion = null }) {
  const flock = normalizedFlock({ ...inputFlock, projectName: project.name })
  const activeCombos = render?.active_combos || detectActiveCombos(flock)
  const activeSet = new Set(activeCombos)
  const nearCombo = combo => {
    const present = new Set(flock.perches.filter(Boolean).map(perch => perch.bird))
    const required = combo.requires.birds || []
    const missing = required.filter(id => !present.has(id)).length
    const roleMissing = (combo.requires.roles || []).filter(role => !flock.perches.filter(Boolean).some(perch => birdById(perch.bird)?.role === role)).length
    const environmentMissing = (combo.requires.weather && combo.requires.weather !== flock.weather ? 1 : 0) + (combo.requires.scale_family && !['minor', 'dorian', 'minor_pent', 'phrygian'].includes(flock.scale) ? 1 : 0)
    return missing + roleMissing + environmentMissing === 1
  }
  let discoveriesOpen = false
  let contextPopover = null
  let factTimer = null
  let lastTap = null
  let tapCount = 0
  let rafId = 0
  let destroyed = false
  const root = h('section', { className: 'fk', 'data-playing': !!playing, 'data-rendering': !!render?.rendering, 'data-collapsed': localStorage.getItem('rookery.flock.collapsed') === 'true' })
  root.appendChild(h('style', null, FLOCK_CSS))

  const emit = (next, meta = {}) => onChange(next, meta)
  const slotChange = (birdId, slot, patch) => {
    if (birdId == null) {
      const available = birds.find(bird => !flock.seen?.includes(bird.id) && !flock.perches.some(perch => perch?.bird === bird.id)) || birds.find(bird => !flock.perches.some(perch => perch?.bird === bird.id))
      if (!available) return
      slotChange(available.id, slot)
      return
    }
    let targetSlot = slot
    const bird = birdById(birdId)
    const currentSlot = flock.perches.findIndex(perch => perch?.bird === birdId)
    if (!patch && bird && currentSlot < 0 && bird.role !== 'crown') {
      const sameRole = flock.perches.map((perch, index) => perch && birdById(perch.bird)?.role === bird.role ? index : -1).filter(index => index >= 0)
      if (sameRole.length >= 2) targetSlot = sameRole[0]
    }
    const next = updatePerch(flock, birdId, targetSlot, patch)
    if (next !== flock) emit(next, { action: patch ? 'control' : 'land', birdId, slot: targetSlot })
  }
  const songChange = birdId => emit(cycleSong(flock, birdId), { action: 'song', birdId })
  const toggleMuteSolo = (birdId, slot, kind) => {
    const perch = flock.perches[slot]
    if (!perch) return
    slotChange(birdId, slot, { [kind]: !perch[kind] })
  }
  const setTemplate = template => emit(applyTemplate(template, flock), { action: 'template', templateId: template.id, projectPatch: template.id === 'trap_night' ? { bpm: 140, bars: 8 } : template.id === 'lo_fi_study' ? { bpm: 72, bars: 4 } : template.id === 'dusty_boom_bap' ? { bpm: 90, bars: 4 } : {} })
  const focusSlot = slot => root.querySelector(`[data-slot-focus="${slot}"]`)?.focus()
  const onWireKey = (event, slot = null, birdId = null) => {
    const activeSlot = slot ?? Number(root.dataset.activeSlot || 0)
    if (['ArrowLeft', 'ArrowRight', 'Enter', 'Delete', '1', '2', '3', '4', '5', '6'].includes(event.key) || ['m', 's'].includes(event.key.toLowerCase())) event.stopPropagation()
    if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
      event.preventDefault()
      const next = clamp(activeSlot + (event.key === 'ArrowRight' ? 1 : -1), 0, 5)
      root.dataset.activeSlot = String(next); focusSlot(next)
    } else if (/^[1-6]$/.test(event.key)) {
      event.preventDefault(); const next = Number(event.key) - 1; root.dataset.activeSlot = String(next); focusSlot(next)
    } else if (!birdId && event.key === 'Enter') { event.preventDefault(); slotChange(null, activeSlot) }
    else if (birdId && event.key === 'Enter') { event.preventDefault(); songChange(birdId) }
    else if (birdId && event.key.toLowerCase() === 'm') { event.preventDefault(); const index = flock.perches.findIndex(perch => perch?.bird === birdId); toggleMuteSolo(birdId, index, 'mute') }
    else if (birdId && event.key.toLowerCase() === 's') { event.preventDefault(); const index = flock.perches.findIndex(perch => perch?.bird === birdId); toggleMuteSolo(birdId, index, 'solo') }
    else if (birdId && event.key === 'Delete') { event.preventDefault(); const index = flock.perches.findIndex(perch => perch?.bird === birdId); const perches = [...flock.perches]; const bird = birdById(birdId); const x = SLOT_X[index] || 500; perches[index] = null; emit({ ...flock, perches }, { action: 'leave', birdId, bird, fromX: x, fromY: wireY(x), birdPerch: flock.perches[index] }) }
  }
  const dragStart = (event, birdId, fromWire) => {
    event.dataTransfer?.setData('text/plain', `bird:${birdId}`)
    if (event.dataTransfer) event.dataTransfer.effectAllowed = fromWire ? 'move' : 'copy'
  }
  const showFact = (event, bird) => {
    clearTimeout(factTimer)
    factTimer = setTimeout(() => {
      root.querySelector('.fk-fact')?.remove()
      const rect = root.getBoundingClientRect()
      const fact = h('div', { className: 'fk-fact', style: { left: `${event.clientX - rect.left}px`, top: `${event.clientY - rect.top - 34}px` } }, `${bird.name}: ${bird.persona} ${bird.bio}`)
      root.appendChild(fact)
    }, 3000)
  }
  const clearFact = () => { clearTimeout(factTimer); root.querySelector('.fk-fact')?.remove() }
  showFact.clear = clearFact
  const showContext = (event, bird) => {
    contextPopover?.remove()
    const rect = root.getBoundingClientRect()
    const perchIndex = flock.perches.findIndex(perch => perch?.bird === bird.id)
    const perch = flock.perches[perchIndex]
    contextPopover = h('div', { className: 'fk-pop', role: 'dialog', 'aria-label': `${bird.name} controls`, style: { left: `${clamp(event.clientX - rect.left, 6, rect.width - 242)}px`, top: `${clamp(event.clientY - rect.top, 6, rect.height - 220)}px` } },
      h('b', null, bird.name), h('p', null, bird.persona, ' ', bird.bio),
      h('div', { className: 'fk-pop-row', role: 'group', 'aria-label': 'Choose song' }, ['A', 'B', 'C'].map(song => h('button', { 'aria-pressed': perch?.song === song, onClick: () => { const perches = [...flock.perches]; if (perchIndex >= 0) perches[perchIndex] = { ...perch, song }; emit({ ...flock, perches }, { action: 'song', birdId: bird.id }); contextPopover?.remove() } }, song))),
      perch && h('label', { className: 'fk-pop-row' }, 'Trim ', h('input', { type: 'range', min: -6, max: 6, step: 0.5, value: perch.trim_db || 0, 'aria-label': `${bird.name} volume trim`, onChange: event => { const perches = [...flock.perches]; perches[perchIndex] = { ...perch, trim_db: Number(event.target.value) }; emit({ ...flock, perches }, { action: 'trim', birdId: bird.id }) } })),
      perch && h('div', { className: 'fk-pop-row' }, h('button', { onClick: () => { const perches = [...flock.perches]; perches[perchIndex] = null; emit({ ...flock, perches }, { action: 'leave', birdId: bird.id, bird, fromX: SLOT_X[perchIndex], fromY: wireY(SLOT_X[perchIndex]), birdPerch: perch }); contextPopover?.remove() } }, 'Send home')))
    root.appendChild(contextPopover)
  }
  const wireTap = event => {
    const now = millis()
    const beat = 60000 / (Number(project.bpm) || 90)
    if (playing) {
      const pos = getPosition() % (beat / 1000)
      if (Math.min(pos, beat / 1000 - pos) > beat / 1000 * 0.18) { lastTap = null; tapCount = 0; return }
    }
    if (lastTap == null || Math.abs(now - lastTap - beat) > beat * 0.28) tapCount = 1
    else tapCount++
    lastTap = now
    if (tapCount >= 4) {
      tapCount = 0
      const bounds = root.querySelector('.fk-wire')?.getBoundingClientRect()
      const x = bounds?.width ? (event.clientX - bounds.left) / bounds.width * 1000 : 500
      const occupied = flock.perches.map((perch, slot) => perch ? { perch, slot } : null).filter(Boolean)
      const closest = occupied.sort((a, b) => Math.abs(SLOT_X[a.slot] - x) - Math.abs(SLOT_X[b.slot] - x))[0]
      emit(flock, { action: 'wireTap', birdId: closest?.perch.bird || null })
      const group = closest && root.querySelector(`.fk-bird[data-bird="${closest.perch.bird}"]`)
      if (group) { group.dataset.look = 'true'; setTimeout(() => { if (group.isConnected) delete group.dataset.look }, 700) }
    }
  }

  const header = h('div', { className: 'fk-head' },
    h('strong', { className: 'fk-title' }, 'The Wire'),
    h('div', { className: 'fk-fields' },
      h('label', { className: 'fk-field' }, 'Key', h('select', { 'aria-label': 'Key', 'data-ui-key': 'key', value: flock.key, onChange: event => emit({ ...flock, key: event.target.value }, { action: 'harmony' }) }, ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'].map(key => h('option', { value: key }, key)))),
      h('label', { className: 'fk-field' }, 'Scale', h('select', { 'aria-label': 'Scale', 'data-ui-key': 'scale', value: flock.scale, onChange: event => emit({ ...flock, scale: event.target.value }, { action: 'harmony' }) }, ['minor', 'dorian', 'major', 'mixolydian', 'minor_pent', 'phrygian'].map(scale => h('option', { value: scale }, scale.replace('_', ' '))))),
      h('span', { className: 'fk-field' }, 'Progression', h('span', { className: 'fk-progression' }, flock.progression.map((chord, index) => h('button', { 'aria-label': `Change chord ${index + 1}, current ${chord}`, title: 'Click to cycle this chord', onClick: () => { const choices = ['i', 'iv', 'VII', 'III', 'I', 'vi', 'ii', 'V']; const next = [...flock.progression]; next[index] = choices[(choices.indexOf(chord) + 1) % choices.length]; emit({ ...flock, progression: next }, { action: 'harmony' }) } }, chord)))),
      h('label', { className: 'fk-field' }, 'Weather', h('select', { 'aria-label': 'Weather', 'data-ui-key': 'weather', value: flock.weather, onChange: event => emit({ ...flock, weather: event.target.value }, { action: 'weather' }) }, ['clear', 'dust', 'rain', 'wind'].map(weather => h('option', { value: weather }, weather)))),
      h('label', { className: 'fk-field' }, 'Template', h('select', { 'aria-label': 'Flock template', 'data-ui-key': 'template', value: flock.templateId || '', onChange: event => { const template = templates.find(item => item.id === event.target.value); if (template) setTemplate(template) } }, h('option', { value: '' }, 'Choose'), templates.map(template => h('option', { value: template.id }, template.name))))),
    h('div', { className: 'fk-meter' },
      h('span', { className: 'fk-meter-label' }, 'Murmurations'),
      h('div', { className: 'fk-dots', role: 'group', 'aria-label': 'Murmuration hints' }, combos.map(combo => {
        const found = (flock.unlocked || []).includes(combo.id)
        return h('button', { className: 'fk-dot', 'data-found': found, 'data-near': !found && nearCombo(combo), title: combo.riddle, 'aria-label': `${combo.name}: ${found ? 'found' : combo.riddle}`, onClick: () => { discoveriesOpen = !discoveriesOpen; root.querySelector('.fk-discoveries')?.remove(); if (discoveriesOpen) root.querySelector('.fk-meter')?.appendChild(discoveriesNode()) } })
      })),
      h('button', { className: 'fk-collapse', 'aria-label': root.dataset.collapsed === 'true' ? 'Expand The Wire' : 'Collapse The Wire', title: 'Collapse or expand The Wire', onClick: () => { const collapsed = root.dataset.collapsed !== 'true'; root.dataset.collapsed = String(collapsed); localStorage.setItem('rookery.flock.collapsed', String(collapsed)) } }, root.dataset.collapsed === 'true' ? 'Expand' : 'Collapse')))
  const discoveriesNode = () => h('div', { className: 'fk-discoveries', role: 'status' }, h('b', null, 'Found murmurations'), (flock.unlocked || []).filter(id => combos.some(combo => combo.id === id)).length ? combos.filter(combo => flock.unlocked.includes(combo.id)).map(combo => h('p', null, combo.name, ' · ', flock.discoveryDates?.[combo.id] || 'Found previously')) : h('p', null, 'Keep experimenting. The birds remember who has visited.'))

  const scene = h('div', { className: 'fk-scene' },
    render?.error && h('div', { className: 'fk-error', role: 'alert' }, 'Render failed: ', render.error),
    h('div', { className: 'fk-sky', 'data-combo': activeCombos[0] || 'none', 'aria-label': `${flock.weather} weather` },
      h('div', { className: 'fk-weather', 'data-kind': colorForWeather(flock.weather), 'aria-hidden': true }, Array.from({ length: flock.weather === 'clear' ? 0 : 28 }, (_, i) => h('i', { style: { left: `${(i * 37) % 100}%`, top: `${(i * 19) % 100}%`, '--i': i } }))),
      activeCombos.length ? h('div', { className: 'fk-combo-banner' },
        h('div', { className: 'fk-swarm', 'aria-hidden': true }, (matchMedia('(prefers-reduced-motion: reduce)').matches ? [] : Array.from({ length: 40 }, (_, i) => h('i', { style: { '--i': i } })))),
        h('div', { className: 'fk-banner' }, h('strong', null, combos.find(combo => combo.id === activeCombos[0])?.name || 'Murmuration'), h('span', null, combos.find(combo => combo.id === activeCombos[0])?.id === 'parliament' ? 'Parliament is in session.' : 'A new arrangement takes flight.'))) : null),
    h(PerchSvg, { project, flock, motion, activeCombos, onSlot: slotChange, onWireTap: wireTap, onSong: songChange, onKeyDown: onWireKey, onContext: showContext, onDragStart: dragStart, onFact: showFact }),
    flock.perches.filter(Boolean).length === 0 && h('div', { className: 'fk-empty-copy' },
      h('span', null, 'An empty wire. Ask Hermes for a flock, or pick a bird below.'),
      h('div', { className: 'fk-empty-actions' }, templates.slice(0, 3).map(template => h('button', { onClick: () => setTemplate(template) }, template.name)))))

  const collapsedStrip = h('div', { className: 'fk-collapsed-strip', 'aria-label': 'Collapsed flock birds' },
    flock.perches.filter(Boolean).map(perch => {
      const bird = birdById(perch.bird)
      return bird ? h('svg', { viewBox: '0 0 100 90', 'aria-hidden': true }, BirdRig({ bird, x: 50, y: 77, perch: null, compact: true, parliament: flock.projectName?.toLowerCase() === 'parliament', nightOwl: false, onSong: () => {}, onKeyDown: () => {}, onContext: () => {}, onDragStart: () => {}, onFact: () => {} })) : null
    }))

  const rosterBirds = [...birds].sort((a, b) => ROLE_ORDER.indexOf(a.role) - ROLE_ORDER.indexOf(b.role))
  const roster = h('div', { className: 'fk-roster' },
    h('div', { className: 'fk-roster-head' }, h('span', null, 'Flock roster'), h('span', null, `${flock.seen.length} of 12 visited`)),
    h('div', { className: 'fk-roster-grid' },
      rosterBirds.map((bird, index) => {
        const perch = flock.perches.find(item => item?.bird === bird.id)
        const first = index === 0 || rosterBirds[index - 1].role !== bird.role
        return BirdCard({ bird, perch, seen: flock.seen.includes(bird.id), firstOfRole: first, onClick: birdId => {
          if (perch) return
          let slot = firstFreeSlot(flock)
          if (slot < 0) slot = flock.perches.findIndex(item => item && birdById(item.bird)?.role === bird.role)
          if (slot >= 0) slotChange(birdId, slot)
        }, onDragStart: dragStart })
      }),
      !isCorvusUnlocked(flock) ? h('button', { className: 'fk-card fk-secret', disabled: true, 'aria-label': 'Secret bird. Visit all twelve birds to unlock.' }, h('span', null, '?'), h('span', { className: 'fk-card-copy' }, h('b', null, 'Secret'), h('span', { className: 'fk-role' }, 'unknown'))) : BirdCard({ bird: corvus, perch: flock.perches[6], seen: true, firstOfRole: true, onClick: birdId => slotChange(birdId, 6), onDragStart: dragStart })))

  const controlArea = h('div', { className: 'fk-controls' },
    h('span', { className: 'fk-combo-label' }, 'The birds stay in key, on the beat, and in their own registers.'),
    h('div', { className: 'fk-combo-banner', 'aria-live': 'polite' }, activeCombos.map(id => h('span', { className: 'fk-banner' }, combos.find(combo => combo.id === id)?.name))))
  root.append(header, collapsedStrip, scene, roster, controlArea)

  // One frame loop drives both beaks and kick vibration from the render clock.
  if (playing && render) {
    const tick = () => {
      if (destroyed) return
      const position = getPosition() || 0
      const duration = (render.duration_samples || 1) / (render.sample_rate || 44100)
      const kick = (render.kick_onsets || []).find(time => {
        let elapsed = position - time
        if (elapsed < 0) elapsed += duration
        return elapsed >= 0 && elapsed < 0.18
      })
      const elapsed = kick == null ? Infinity : ((position - kick + duration) % duration)
      const wire = root.querySelector('.fk-wire')
      if (wire) {
        const amp = Number.isFinite(elapsed) ? Math.sin(elapsed * 36) * Math.exp(-elapsed * 18) * 2 : 0
        wire.style.transform = `translateY(${amp.toFixed(2)}px)`
        wire.dataset.vibrate = String(amp !== 0)
      }
      for (const bird of birds) {
        const group = root.querySelector(`.fk-bird[data-bird="${bird.id}"][data-present="true"]`)
        if (!group) continue
        group.dataset.wingLift = String(activeCombos.includes('parliament') && position < 240 / Math.max(1, Number(project.bpm) || 120))
        const notes = render.events?.[bird.id] || []
        const event = render.error ? null : notes.find(note => {
          if (note.muted) return false
          let delta = position - note.t
          if (delta < 0 && note.t + note.len > duration) delta += duration
          return delta >= 0 && delta <= note.len
        })
        group.dataset.speaking = String(!!event)
        if (event) group.style.setProperty('--fk-open', `${clamp(event.vel * 5, 1, 5)}px`)
      }
      rafId = requestAnimationFrame(tick)
    }
    rafId = requestAnimationFrame(tick)
  }
  root.addEventListener('pointerup', clearFact)
  root.addEventListener('pointerleave', clearFact)
  root._flockDestroy = () => { destroyed = true; cancelAnimationFrame(rafId); clearTimeout(factTimer); contextPopover?.remove() }
  return root
}

export default FlockPanel
