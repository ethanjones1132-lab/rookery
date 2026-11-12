# Rookery contract: backend ↔ Desktop page

**Status: v0.1 RATIFIED by Claude + Sol, 2026-11-08. Changes now need both to sign on the board.**
Owners: Claude (what the UI needs) + Sol (backend shape, final say). Mock: `dev/preview/mock-backend.js` must match this file. Change both in the same commit.

Sign-off:
- [x] Claude: v0 proposed
- [x] Sol: v0.1 ratified 2026-11-08, decisions in §5

---

## 1. Principles

1. **`project.json` is the only truth.** Routes and tools are thin doors onto the same `rookery/project.py` functions. A user click and an agent tool call go through one code path (validate → snapshot → save → broadcast).
2. **`rev` orders everything.** It's a monotonic int per project, bumped by every successful write from either side. The page never guesses; it compares `rev`.
3. **Errors are messages, not crashes.** Validation errors return the same text the model would see, so the page can show it as-is.
4. **Events accelerate, polling guarantees.** Every event is optional to the page's correctness. The page polls `?since=rev` every 2 s while it's open.

## 2. REST: `/api/plugins/rookery/…` (`ctx.rest('/…')`)

| Method + path | Body | 200 response | Errors |
|---|---|---|---|
| `GET /projects` | | `[{name, rev, updated_at, bpm, bars}]` newest first | |
| `GET /project/{name}` | | `ProjectView` (below) | `404 {message}` |
| `GET /project/{name}?since={rev}` | | `{changed:false, rev}` if unchanged, else `ProjectView` | `404` |
| `POST /project` | `{name?, bpm?: 90, bars?: 4, swing?: 0, from?: string}` | `ProjectView`; `from` duplicates current state with fresh history | `409 {message}` exists · `422 {message}` invalid · `404 {message}` missing source |
| `POST /project/{name}/rename` | `{to}` | `ProjectView` under the new name | `404`, `409`, `422 {message}` |
| `DELETE /project/{name}` | | `{deleted: name}`; files moved to recoverable trash | `404 {message}` |
| `POST /edit` | `Edit` (below) | `{project, rev, diff}` | `409 {message, rev}` stale rev · `422 {message}` invalid · `404` |
| `POST /undo` | `{name, steps?: 1}` | `{project, rev, diff}` | `404`, `422 {message}` nothing to undo |
| `POST /render` | `{name}` | `RenderView` | `404`, `500 {message}` render crashed |
| `GET /audio/{hash}` | | `{hash, mime: 'audio/wav', b64}` (base64 WAV, ~2–4 MB for 4–8 bars) | `404` |
| `GET /status` | | `{version, corvus: {found, path, params: [{name, min, max, default, value?}]}, kits: {factory: [..], user_dir, user: [..]}}` | |

```ts
type ProjectView = {
  project: Project            // HANDOFF §2.1 schema, steps strings expanded to full loop length
  rev: number
  render: RenderView | null   // null when the current rev has never been rendered
  agent_editing: boolean      // true between a tool call's start and end for this project
}
type RenderView = {
  hash: string                // sha256 hex of canonical audio projection + renderer version
  wav_hash: string            // sha256 hex of the rendered WAV bytes
  rev: number                 // the rev that was rendered
  audio_url: string           // relative, e.g. "/audio/<hash>"; the page calls ctx.rest(audio_url) and decodes .b64
  report: Record<CheckName, { pass: boolean, value: number | string, target?: string, hint?: string }>
  meters: { [trackId: string]: { rms_db: number, peak_db: number } }   // for the mixer strip
  duration_samples: number
  sample_rate: 44100
}
type CheckName = 'length_exact' | 'no_clipping' | 'loudness' | 'seam_click' | 'not_silent' | 'deterministic'

type Edit = { name: string, rev?: number } & (
  | { op: 'steps', track: string, steps: string, velocity?: number[] }
  | { op: 'track', action: 'add' | 'remove' | 'set', id: string, kind?, source?, gain_db?, pan?, mute?, solo?, pitch?,
      notes?: { step: number, len: number, pitch: string | number }[], slices?: number }
  | { op: 'mix', target: 'master' | string, fx: FX[] }
  | { op: 'meta', bpm?: number, bars?: 4 | 8, swing?: number }
   | { op: 'clear', track?: string } // clear all steps, or one track; one undoable write
  | { op: 'fx_param', target: 'master' | string, index: number, param: string, value: number }  // a knob turn
)
```

- `rev` on `/edit` is optional. If it's present and stale, the response is `409` and nothing is written. The page sends it on every click, and the agent's tools never send it (the agent always edits the latest).
- **Expanded steps:** responses always carry `steps` at full loop length (`bars × steps_per_bar`). The file may store the short repeating form. The page never has to expand patterns itself.
- `report[k].hint` is the one-line fix the skill would give ("lower 808 gain 3 dB"). The page shows it on a red LED.

## 3. Events: `broadcast_plugin_event("rookery", <event>, payload)`

The page subscribes with `host.onEvent('plugin.rookery.<event>')`.

| Event | Payload | When |
|---|---|---|
| `project.updated` | `{name, rev, source: 'agent'\|'user', tool: string\|null, diff: Diff[]}` | after every successful write, from tools and `/edit` |
| `project.created` | `{name, from?: string}` | after a beat is created or duplicated |
| `project.renamed` | `{from, to}` | after a beat and its history/render records are moved |
| `project.deleted` | `{name}` | after project files are moved into recoverable trash |
| `agent.editing` | `{name, editing: boolean}` | `true` when a rookery tool starts on a project, `false` when it returns (wrap the tool body in try/finally) |
| `render.started` | `{name, rev}` | render begins |
| `render.done` | `{name, rev, hash, report}` | render finished (cache hits too, so the page reacts the same way) |
| `render.failed` | `{name, rev, message}` | renderer raised |

```ts
type Diff =
  | { track: string, field: 'steps', from: string, to: string, steps: number[] }   // ← drives the live-build animation
  | { track: string, field: 'velocity', from: number[], to: number[], steps: number[] }
  | { track: string, field: 'track', action: 'add' | 'remove' }
  | { track: string, field: 'gain_db' | 'pan' | 'mute' | 'solo' | 'pitch' | 'source', from: unknown, to: unknown }
  | { track: string | 'master', field: 'fx', from: FX[], to: FX[] }
  | { field: 'bpm' | 'bars' | 'swing', from: number, to: number }
```

**`steps` in a `steps` / `velocity` diff:** indexes into the expanded loop where the value changed, **in ascending order** (the page staggers the animation in this order, ~30 ms apart). This list is the money shot. Never omit it.

Undo emits a normal `project.updated` whose diff is the reverse change, with `tool: 'rookery_undo'`, so the page animates undo like any other edit.

## 4. What the page does with it (for Sol's context)

- Load: `GET /project/{name}` → draw.
- Event `project.updated` → animate `diff` immediately from the payload, then `GET ?since=` to reconcile.
- Poll every 2 s: `GET ?since=rev`. `{changed:false}` costs nothing.
- Click a pad → `POST /edit {op:'steps', rev}` (optimistic; on `409`/`422`, roll back and toast the message) → debounced `POST /render` after 400 ms idle.
- `render.done` → load `audio_url`, draw the waveform, light the LEDs.

## 4b. Tool result for `rookery_render` (v0.2 RATIFIED by Claude + Sol, 2026-11-08)

The Desktop chat card (`TOOL_MEDIA_RENDERER_AREA`, SDK doc "Tool media renderers") receives the tool's own `result` and a `file` for the WAV. It draws **what was rendered then**, even in a reopened chat after the project changed, so the result carries a compact snapshot:

```ts
{ name, rev, hash, wav_hash, path,   // path = the WAV on disk; the result must name it (that's how Desktop links the file to this tool)
  bpm, bars, swing, duration_samples,
  report,                           // same shape as RenderView.report
  tracks: [{ id, steps, velocity, mute }] }   // expanded steps, ≤ 8 tracks
```

The model then writes `MEDIA:<path>` in its reply (the skill tells it to). The card parses defensively: an object, a JSON string, or a JSON string with trailing text. Without `tracks` the card still plays and shows the LEDs, just with no mini grid.

## 4c. The Flock (v0.3 RATIFIED by Claude + Sol, 2026-11-08). Spec: docs/design/flock.md

- **Project:** optional top-level `flock` block: `{key, scale, progression[], weather, perches[6|7] of {bird, song, mute, solo} | null, seen[], unlocked[]}`. Absent means no melodic layer and every existing project remains valid. `slot` is zero-based. Ordinary birds occupy slots 0–5, each bird once and at most two birds per role. Normal perches contain `{bird, song: A|B|C|D, mute: boolean, solo: boolean}`. Optional slot 6 contains only Corvus with song A and exists only after all 12 ordinary bird IDs have been seen. The transition to all 12 seen auto-perches Corvus once. Users may unperch and later reperch Corvus; unrelated later edits do not respawn it. `seen` and `unlocked` are cumulative ID lists updated by the shared edit path; undo restores the snapshot. Keys accept the 12 sharp names plus `Db`, `Eb`, `Gb`, `Ab`, and `Bb`, normalized to enharmonic sharps.
- **Catalog:** `rookery/flock/birds.json` is the single source for birds, songs, templates, and combos. `GET /flock/catalog` returns that JSON; the page fetches it once per mount.
- **Tool (9th, withdrawn 2026-11-10):** `rookery_flock` was removed from the agent tool list. The Flock stays a full user instrument through `POST /edit {op:'flock', …}` in the page, and it still renders into the mix, hash and checks. There is no `flock` atom in `rookery_apply`: an agent apply batch containing one is rejected with "flock is not an agent apply operation". The history below records the withdrawn tool's shape. It uses the same validate → snapshot → save → broadcast path. Tool calls may omit `name`, which resolves the newest project like existing tools; REST `Edit.name` remains required. `POST /edit {op:'flock', …same args}` handles page edits. `unperch` accepts exactly one of `bird` or `slot`. `perch` without a slot selects that bird's current slot, otherwise the first empty ordinary slot; Corvus uses slot 6. An occupied slot with a different bird is rejected and never silently replaced. Moving an existing bird preserves mute, solo, and song unless song is explicit. Templates accept a catalog ID or display name, replace ordinary perches in bass, keys, pad, lead, arp, call order, and set key, scale, progression, and weather while preserving `seen`, `unlocked`, and an existing Corvus. Perch/song D is accepted only while that bird's D-granting combo is active. Combos automatically render D overrides without changing base A/B/C; breaking a combo reverts explicit D to A.
- **Diff:** `{field:'flock', change:'template'|'perch'|'unperch'|'song'|'mute'|'solo'|'harmony'|'weather', bird?, slot?, from, to}`. Bird-slot diffs carry complete perch objects or `null` as `from`/`to`. A template emits one diff per changed slot, including removals, ordered by the arriving bird's role or the departing bird's role for removals, then slot; roles are bass, keys, pad, lead, arp, call, crown. Harmony and weather emit separate diffs when changed. Other edits and undo infer each actual changed property; a harmony edit that resets D also emits a `song` diff. Harmony `from`/`to` values are `{key, scale, progression}`; weather values are strings. Normal user/agent origin, event revision, and history rules are unchanged.
- **RenderView additions:** `flock_events: {birdId: [{t, len, midi, vel}]}` in seconds for beak sync, `kick_onsets: [t]` for wire vibration, and `flock_active_combos: [comboId]`. Events include only audible synthesized notes and audible kick onsets from rendered drum timing. `flock_active_combos` contains combos whose requirements are currently met by audible birds, not the all-time `unlocked` list. Muted birds and non-soloed birds do not participate while any audible flock bird is soloed. Note degree modulo and octave wrapping use the catalog scale length (five for `minor_pent`); all bonus notes stay in key and register. Bonuses are rendered audio. The flock fingerprint version applies only to projects containing a flock; projects without one retain their previous canonical hash and PCM bytes.
- **`rookery_state`** gains the Wire line and Murmuration hint (flock.md §7.2).
- **`rookery_render` tool result (§4b):** optional `flock: {perches: ({bird, song, mute, solo} | null)[]}` preserves the six or seven slot indices from the immutable rendered revision. It is absent for projects without a flock; existing v0.2 snapshot fields are unchanged.

## 4d. Batch apply, per-bird mix, meters and mix (v0.4, additive)

- **`rookery_apply(name?, ops[])`** applies 1–64 edit atoms in **one revision, one history snapshot and one `project.updated` event**. Each atom is `{op: "steps"|"track"|"mix"|"meta"|"clear"|"groove"|"arrange"|"balance", ...fields}` using the same shapes as the single-edit tools. (The `flock` atom from v0.4 was withdrawn with `rookery_flock`; the Flock is edited in the page only.) A `groove` atom (`{op:"groove", groove:"<id>", swing?}`) expands to the named template's drum tracks, step strings and velocities, and sets swing when supplied. The batch is atomic: if any atom fails, nothing is written. The result is `{project, rev, diff}` like `/edit`.
- **Flock per-bird mix:** perch objects accept optional `gain_db` (−24..12) and `pan` (−1..1). `/edit {op:"flock", action:"mix", …}` sets them in the page. (The `rookery_flock(action="mix", …)` tool was withdrawn with the other Flock actions on 2026-11-10.) `rookery_state` shows the trim; the `flock` diff change is `mix`. Missing fields mean 0, so existing projects are unchanged.
- **Render result additions:** `rookery_render` and `RenderView` now carry `meters` (per-track `{rms_db, peak_db}`) and `mix` (`{correlation, width, lr_balance_db, crest_db, centroid_hz, bands_pct:{sub,low,mid,high,air}}`). The six-check `report` shape is unchanged. Cached legacy renders get `mix` rederived from the WAV and written back.

## Changelog
- **v0.6 (2026-11-11, docs):** `rookery_flock` is withdrawn from the agent tool list; the Flock remains a page instrument through `POST /edit {op:'flock', …}`, and `rookery_apply` rejects a `flock` atom. The agent tool list is 11 names: `rookery_new`, `rookery_steps`, `rookery_track`, `rookery_mix`, `rookery_apply`, `rookery_render`, `rookery_export`, `rookery_state`, `rookery_undo`, `rookery_kits`, `rookery_samples`. No REST or render field changes.
- **v0.5 additive (2026-11-10, agent):** `RenderView` and the `rookery_render` tool result gain `wav_hash` (SHA-256 of the WAV bytes). The canonical audio projection already leaves out the project name, so a copy with identical content has the same `hash` and the same `wav_hash`; the new field proves the bytes directly. The page shows it beside the render hash; the chat card shows it when there is room. No existing field changes.
- **v0.4 additive (2026-11-09, agent):** `rookery_apply(ops[])` applies a batch in one revision/history step/event, including a named `groove` op that expands to drum tracks + steps + swing. Flock perches gain optional `gain_db` (−24..12) and `pan` (−1..1), plus the `mix` action. `rookery_render` results and `RenderView` gain `meters` (per-track RMS/peak) and `mix` (correlation, width, L/R balance, crest, centroid, band percentages). No existing field changes.
- **v0.3 ratified (2026-11-08):** Sol's flock contract clarifications applied in §4c, including slot and template semantics, complete slot diffs, audible render metadata, and the revision-bound render snapshot.
- **v0.2 ratified (2026-11-08 03:15):** §4b rookery_render tool result, built from the immutable rendered revision with expanded steps/velocity; REST RenderView is unchanged.
- **v0.1 ratified (2026-11-08 02:45):** Sol accepted the base64 audio change and answered §5. `track` add/set gained `notes` (bass) and `slices` (sample tracks).
- **v0.1 (2026-11-08 02:00, Claude):** audio moves from a raw `audio/wav` stream to base64 JSON. Reason: `ctx.rest` goes through Electron IPC to `hermesApi()` (`apps/desktop/src/api/plugins.ts:73`) and returns parsed JSON, so a binary stream never reaches the page. The chat card plays through the `TOOL_MEDIA_RENDERER_AREA` `MEDIA:` file instead and isn't affected.

## 5. Decisions (were open questions; answered by Sol, 2026-11-08)

1. **`agent.editing` comes from Rookery's own tool wrapper:** `try/finally` around every rookery tool, with an overlap counter so parallel tool calls don't flicker it off.
2. **`POST /render` blocks and returns the final `RenderView`.** The DSP runs in a threadpool so the gateway stays responsive. `render.started`/`render.done`/`render.failed` fire either way.
3. **The default project is the newest updated one** (`GET /projects`[0]), and the page follows the project in the agent's latest `project.updated`.
