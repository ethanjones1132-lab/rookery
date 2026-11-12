// Stand-in for @hermes/plugin-sdk, preview harness only.
// Covers the subset Rookery uses. Signatures follow
// website/docs/developer-guide/desktop-plugin-sdk.md and apps/desktop/src/sdk/index.ts.
// If the plugin needs an export that isn't here, add it, and match the real
// shape exactly. The real app is the source of truth.
import * as React from 'react'
import { jsx } from 'react/jsx-runtime'

// ── areas ────────────────────────────────────────────────────────────────
export const PANES_AREA = 'panes'
export const ROUTES_AREA = 'routes'
export const SIDEBAR_NAV_AREA = 'sidebar.nav'
export const TOOL_MEDIA_RENDERER_AREA = 'transcript.toolMedia'
export const STATUSBAR_AREAS = { left: 'statusBar.left', right: 'statusBar.right' }
export const PALETTE_AREA = 'palette'
export const KEYBINDS_AREA = 'keybinds'

// ── nanostores-like atoms ───────────────────────────────────────────────
export function atom(initial) {
  let value = initial
  const subs = new Set()
  return {
    get: () => value,
    set(v) { value = v; subs.forEach(fn => fn(v)) },
    subscribe(fn) { subs.add(fn); fn(value); return () => subs.delete(fn) },
    listen(fn) { subs.add(fn); return () => subs.delete(fn) }
  }
}
export function computed(stores, fn) {
  const list = Array.isArray(stores) ? stores : [stores]
  const calc = () => fn(...list.map(s => s.get()))
  const out = atom(calc())
  list.forEach(s => s.listen(() => out.set(calc())))
  return out
}
export function useValue(store) {
  return React.useSyncExternalStore(fn => store.listen(fn), store.get, store.get)
}

// ── harness internals (not part of the real SDK) ─────────────────────────
const registry = atom([])
const eventListeners = new Map() // type → Set<fn>
const route = atom('/rookery')
let backend = null
let gateway = null

export const __harness = {
  registry,
  route,
  setBackend(b) { backend = b },
  /** Mock gateway JSON-RPC: (method, params) => Promise<result>. */
  setGateway(fn) { gateway = fn },
  /** A gateway event, shaped like the real GatewayEvent {type, session_id, payload}. */
  emitGateway(type, session_id, payload) {
    const ev = { type, payload, session_id }
    for (const key of [type, '*']) eventListeners.get(key)?.forEach(fn => { try { fn(ev) } catch (e) { console.error(e) } })
  },
  emit(type, payload) {
    const ev = { type, payload, session_id: '' }
    for (const key of [type, '*']) eventListeners.get(key)?.forEach(fn => { try { fn(ev) } catch (e) { console.error(e) } })
  },
  createContext(id) {
    const disposers = []
    const add = (type, fn) => {
      if (!eventListeners.has(type)) eventListeners.set(type, new Set())
      eventListeners.get(type).add(fn)
      const off = () => eventListeners.get(type)?.delete(fn)
      disposers.push(off)
      return off
    }
    const ctx = {
      source: `plugin:${id}`,
      register(c) {
        const entry = { ...c, id: `${id}:${c.id}`, source: `plugin:${id}` }
        registry.set([...registry.get(), entry])
        return () => registry.set(registry.get().filter(x => x !== entry))
      },
      registerMany(cs) { const offs = cs.map(c => ctx.register(c)); return () => offs.forEach(f => f()) },
      registerSettingsPage: () => () => {},
      async rest(path, opts = {}) {
        if (!backend) throw new Error('rest: backend not mounted')
        if (path.includes('..')) throw new Error('rest: path traversal refused')
        await new Promise(r => setTimeout(r, 40 + Math.random() * 60)) // feels like a network
        return backend.handle(opts.method || 'GET', path, opts.body)
      },
      socket: () => () => {},
      onEvent: add,
      onDispose: fn => disposers.push(fn),
      setTimeout(fn, ms) { const t = setTimeout(fn, ms); return () => clearTimeout(t) },
      setInterval(fn, ms) { const t = setInterval(fn, ms); return () => clearInterval(t) },
      addEventListener(target, type, fn, o) { target.addEventListener(type, fn, o); return () => target.removeEventListener(type, fn, o) },
      storage: {
        get(k, d) { try { const v = localStorage.getItem(`hermes.plugin.${id}.${k}`); return v == null ? d : JSON.parse(v) } catch { return d } },
        set(k, v) { try { localStorage.setItem(`hermes.plugin.${id}.${k}`, JSON.stringify(v)) } catch {} },
        remove(k) { try { localStorage.removeItem(`hermes.plugin.${id}.${k}`) } catch {} }
      },
      os: { openExternal: url => window.open(url, '_blank', 'noopener') },
      pet: { say: () => {} }
    }
    return ctx
  }
}

// ── host ────────────────────────────────────────────────────────────────
const prefersReduced = atom(matchMedia('(prefers-reduced-motion: reduce)').matches)
export const host = {
  state: {
    gateway: atom('open'),
    activeSessionId: atom('preview-session'),
    model: atom('preview-model'),
    viewport: atom({ reducedMotion: prefersReduced.get() })
  },
  notify: ({ kind = 'info', message }) => console.log(`[toast:${kind}]`, message),
  notifyError: (e) => console.error('[toast:error]', e),
  navigate: (path) => route.set(path),
  onEvent: (type, fn) => {
    if (!eventListeners.has(type)) eventListeners.set(type, new Set())
    eventListeners.get(type).add(fn)
    return () => eventListeners.get(type)?.delete(fn)
  },
  request: async (method, params = {}) => {
    if (!gateway) throw new Error('host.request is not mocked in the preview')
    return gateway(method, params)
  },
  openSession: async id => console.log('[host] openSession', id)
}

// ── helpers + a minimal UI kit (shapes only; the real app styles them) ──────
export const cn = (...xs) => xs.flat().filter(Boolean).join(' ')
export const haptic = () => {}
export function Codicon({ name, className }) {
  return jsx('span', { className: cn('codicon', `codicon-${name}`, className), 'aria-hidden': true })
}
export function StatusDot({ tone = 'neutral', className }) {
  return jsx('span', { className: cn('hx-status-dot', className), 'data-tone': tone })
}
export function Tip({ content, label, children }) {
  // Radix's trigger is asChild in the real app: no wrapper element in the layout.
  const text = typeof (label ?? content) === 'string' ? (label ?? content) : undefined
  return React.isValidElement(children) ? React.cloneElement(children, { title: children.props.title ?? text }) : jsx('span', { title: text, children })
}
export function Button({ variant, size, className, ...rest }) {
  return jsx('button', { type: 'button', className: cn('hx-btn', className), ...rest })
}

// The main composer's surface pieces, copied verbatim from
// apps/desktop/src/components/chat/composer-dock.ts and control-classes.ts.
// The harness loads the installed Hermes CSS, so these classes paint for real.
export const composerSurfaceRing =
  'border border-[color-mix(in_srgb,var(--dt-composer-ring)_calc(18%*var(--composer-ring-strength)),var(--dt-input))]'
export const composerInputBacking =
  'pointer-events-none absolute inset-0 -z-10 rounded-[inherit] bg-(--composer-fill) transition-[background-color] duration-150 ease-out'
export const PRIMARY_ICON_BTN =
  'size-(--composer-control-primary-size,var(--composer-control-size)) shrink-0 rounded-full p-0 bg-foreground text-background hover:bg-foreground/90 disabled:bg-foreground/30 disabled:text-background disabled:opacity-100'
export const GHOST_ICON_BTN =
  'size-(--composer-control-size) shrink-0 rounded-md text-(--ui-text-tertiary) hover:bg-(--chrome-action-hover) hover:text-foreground'

// Stand-in for MessageTextContent: paragraphs, lists, **bold**, `code`. The real
// one is core's full markdown renderer; this only has to read the same.
function inline(text, key) {
  const out = []
  text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).forEach((s, i) => {
    if (/^\*\*[^*]+\*\*$/.test(s)) out.push(jsx('strong', { children: s.slice(2, -2) }, `${key}-${i}`))
    else if (/^`[^`]+`$/.test(s)) out.push(jsx('code', { className: 'hx-code', children: s.slice(1, -1) }, `${key}-${i}`))
    else if (s) out.push(s)
  })
  return out
}
export function MessageTextContent({ text }) {
  const blocks = String(text || '').trim().split(/\n{2,}/)
  return jsx('div', { className: 'hx-md', children: blocks.map((b, i) => {
    const lines = b.split('\n')
    if (lines.every(l => /^\s*[-*] /.test(l))) return jsx('ul', { children: lines.map((l, k) => jsx('li', { children: inline(l.replace(/^\s*[-*] /, ''), k) }, k)) }, i)
    return jsx('p', { children: inline(b, i) }, i)
  }) })
}
export function GlyphSpinner() {
  const [f, setF] = React.useState(0)
  React.useEffect(() => { const t = setInterval(() => setF(n => (n + 1) % 10), 80); return () => clearInterval(t) }, [])
  return jsx('span', { role: 'status', 'aria-label': 'Loading', style: { fontFamily: 'var(--dt-font-mono, monospace)', width: '1ch', display: 'inline-block' }, children: '⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏'[f] })
}

// Stand-ins for the dropdown family (Radix in the real app). Shapes only: open state,
// asChild trigger, an upward/downward content box, items that close unless onSelect
// calls preventDefault. The real app's classes still paint, since its CSS is loaded.
const DDCtx = React.createContext(null)
export function DropdownMenu({ open, onOpenChange, children }) {
  const [own, setOwn] = React.useState(false)
  const isOpen = open ?? own
  const set = v => (onOpenChange ? onOpenChange(v) : setOwn(v))
  const ref = React.useRef(null)
  React.useEffect(() => {
    if (!isOpen) return
    const away = e => { if (!ref.current?.contains(e.target)) set(false) }
    const esc = e => { if (e.key === 'Escape') set(false) }
    document.addEventListener('pointerdown', away, true); document.addEventListener('keydown', esc)
    return () => { document.removeEventListener('pointerdown', away, true); document.removeEventListener('keydown', esc) }
  }, [isOpen])
  return jsx(DDCtx.Provider, { value: { open: isOpen, set }, children: jsx('span', { ref, style: { display: 'contents' }, children }) })
}
export function DropdownMenuTrigger({ children }) {
  const c = React.useContext(DDCtx)
  return React.cloneElement(children, { 'aria-expanded': c.open, 'data-state': c.open ? 'open' : 'closed', onClick: e => { children.props.onClick?.(e); c.set(!c.open) } })
}
export function DropdownMenuContent({ className, children, side = 'bottom', align = 'start', sideOffset = 4 }) {
  const c = React.useContext(DDCtx)
  if (!c.open) return null
  const style = { position: 'absolute', zIndex: 50, [side === 'top' ? 'bottom' : 'top']: `calc(100% + ${sideOffset}px)`, [align === 'end' ? 'right' : 'left']: 0 }
  return jsx('div', { role: 'menu', className: cn('hx-dd', className), style, children })
}
export function DropdownMenuItem({ className, onSelect, disabled, children }) {
  const c = React.useContext(DDCtx)
  return jsx('div', {
    role: 'menuitem', tabIndex: -1, 'data-disabled': disabled ? '' : undefined, className: cn('hx-dd-item', className),
    onClick: () => { if (disabled) return; let kept = false; onSelect?.({ preventDefault() { kept = true } }); if (!kept) c.set(false) },
    children
  })
}
export function DropdownMenuSeparator({ className }) { return jsx('div', { role: 'separator', className: cn('hx-dd-sep', className) }) }
export function Badge({ className, children }) { return jsx('span', { className: cn('hx-badge', className), children }) }
export function DisclosureCaret({ open, className }) {
  return jsx('span', { className: cn('codicon', 'codicon-chevron-right', className), style: { fontSize: '0.625rem', transform: open ? 'rotate(90deg)' : 'none', transition: 'transform .15s' }, 'aria-hidden': true })
}
export const catalogProviderMatches = (p, id) => !!id && (p.slug === id || p.name === id || (p.aliases || []).includes(id))
