<!-- Demo: <VIDEO_URL>  (90-second walkthrough; no sped-up section, real model name on screen) -->

# plugin-catalog: add rookery (Plugin Hackathon entry)

Rookery is a step-sequencer DAW inside Hermes Desktop. You tell the agent the
beat ("make a dusty boom bap at 90 in A minor, eight bars"); it writes the same
`project.json` your clicks write, and you watch the grid fill in step by step.
Every render is local, exact-length and checked for clipping, loudness and the
loop seam, and the same project renders the same bytes.

It is sample-first for songs, not just loops: `rookery_samples` searches Soundza
in one batch, fetches a chord bed, a melodic lead and at most one counter into
your own kit with the credit recorded, and `rookery_apply` writes the drums,
bass, sample parts, `balance` and the arrangement in one revision.
`rookery_render(song=true)` renders the whole song; a loop render returns role
balance, pairwise sample fit and actionable mix notes, so "the lead is buried"
becomes a measured gain change. `rookery_export` writes a creator-ready WAV,
stems, MIDI, `cues.json` (bars, kicks, snares, sections, optional frame cues) and
`LICENSE.txt`, so another agent can score to picture without a cloud music
service. The Flock is the user's melodic instrument on the page: twelve birds on
a wire, edited by hand, rendered into the same mix and checks, with no agent
tool.

Pinned commit: `<FULL_40_CHAR_SHA>` (full 40-character SHA; `version: "0.2.0"`).

## Hermes surfaces used

- **Tools (11):** `rookery_new`, `rookery_steps`, `rookery_track`,
  `rookery_mix`, `rookery_apply`, `rookery_render`, `rookery_export`,
  `rookery_state`, `rookery_undo`, `rookery_kits`, `rookery_samples`.
- **Bundled skills:** `rookery`, `rookery-boom-bap`, `rookery-trap`.
- **Desktop page:** `/rookery`, a sidebar row, a live step grid with per-step
  velocity, the Flock wire, a waveform and playhead, a mixer/FX strip and an
  in-page chat.
- **Chat media renderer:** a compact, playable render card for `rookery_render`
  with the mini grid and the six check lights.
- **Plugin API:** `/api/plugins/rookery/…` for projects, edits, undo, render,
  audio, export, status and the Flock catalog.
- **Plugin events:** `project.updated` (with the step diff that drives the live
  build), `project.created`/`renamed`/`deleted`, `agent.editing`,
  `render.started`/`done`/`failed`.
- **Plugin data:** projects, history, renders, exports and the user kit live
  under `plugin_data_dir("rookery")`.

## How it was tested

Windows 11, Hermes Agent **0.23.0** (`2bd378ed1b8d`), Python **3.11.15** in the
Hermes dev venv (the managed runtime is **3.14.9**). The suite exercises the
project schema, exact length, the six checks, determinism (render twice, compare
hash and WAV bytes), the loop seam, undo, arrangement variety, sample import and
gating, export, and every registered tool handler end to end. The headless
managed-runtime proof is in `docs/validation-2026-11-10.md`.

```text
$ python -m pytest tests/engine tests/acceptance -q -p no:cacheprovider
512 passed, 6 xfailed in 226.47s
```

```text
$ python tools/audit.py
PASS binaries: none tracked
PASS samples: 67 first-party voice one-shots (5.17 MiB, manifest provenance ok)
PASS deps: 5 capped
PASS provides_tools: 11 match register()
PASS requires_hermes: >=0.23.0
PASS secrets: no credential reads in code
PASS self_update: none found
```

```text
$ hermes plugins validate .
✓ manifest — plugin.yaml parses
✓ requires_hermes — spec '>=0.23.0' parses
✓ loadable — entry: __init__.py, desktop/plugin.js
✓ python dependencies — 5 requirements from pyproject
✓ capability probe — register() ran in isolation
✓ declared tools — matches registrations
✓ security scan — safe
✓ no core override — no runtime rebinds of Hermes core
✓ desktop surface — stays inside the plugin SDK surface
Validation passed.

$ hermes plugins validate . --install-deps
# Every validation check above passes. On this machine the --install-deps
# dependency-preparation step fails first with: uv error "Two workspace members
# are both named `rookery`" (two linked Rookery checkouts in the local Hermes
# workspace). Local workspace collision, not a dependency problem.
```

```text
$ node dev/preview/check-mock.mjs
ok: routes, edit ops, validation, revs, undo, events, deterministic renders, audio, status and the lost-event fallback
```

Cross-platform CI (Ubuntu, macOS, Windows; Python 3.11, plus 3.14 on Ubuntu):
`<FILL: CI run URL or "pending first push">`.

## What was not tested

- **Desktop UI on macOS or Linux.** The page, live audio playback and Corvus
  knobs were verified on Windows 11 only. The Python engine has a CI matrix for
  Ubuntu/macOS; the Desktop page does not.
- **Remote gateways.** The WAV was not delivered through Telegram or a remote
  gateway in this pass; the tools are surface-independent but that route is
  unproven here.
- **A fresh-machine catalog install** (`hermes plugins install rookery`).
- **The Flock in real Desktop on the final commit.** It stays a page-only
  instrument; the headless managed-runtime proof of the render path is in
  `docs/validation-2026-11-10.md`.
- **A recorded demo of the Flock scene** if it is cut from the video; the shot
  list in `docs/demo.md` marks it as optional and page-driven.

The engine, API, handler and export paths are covered by the suite. Rookery is
GPL-3.0-only because pedalboard is GPL-3.0.

## Disclosure

- **Local files.** Projects, history, renders and exports are written under
  `plugin_data_dir("rookery")`. Nothing is uploaded.
- **User kit folder.** Rookery reads audio files from the configured
  `user_kit_dir` (default: `plugin_data_dir/kits`). It never copies them into
  the repo.
- **VST3.** If you point `corvus_vst3_path` at a VST3, Rookery loads it
  in-process through pedalboard. That is third-party native code running with
  your permissions. If it is not configured, Rookery uses its built-in effects.
- **First-party voice one-shots.** `rookery/flock/voices/` contains FLAC
  one-shots rendered by the Rookery authors with Xfer Serum from original
  patches. No Serum binaries, presets or wavetable files are included; Serum is
  a build-time authoring tool only. The manifest records the provenance, patch
  hashes and an 8 MiB budget.
- **Network (`rookery_samples` only).** The core plugin makes no network calls.
  `rookery_samples` searches Soundza at `api.soundza.com`; a download follows
  the signed link Soundza issues for it, on its Cloudflare R2 storage
  (`*.r2.cloudflarestorage.com`; the link lasts five minutes). With
  `source="openverse"` it searches `api.openverse.org` and downloads CC0
  previews from `cdn.freesound.org`. Search works without a key; downloads need
  a free `SOUNDZA_API_KEY` set through Hermes's env (optional; Rookery never
  logs or stores it). Soundza sounds are royalty-free for use in your music
  with no attribution required, but you may not share a sound, or stems that
  are only one of them, as standalone files or in a sample pack. Rookery checks
  Soundza's removals list weekly and deletes sounds that were taken down.
  Credits, with the licence and landing URL, live in
  `<user_kit_dir>/library/credits.json`. No telemetry.
- **Corvus FX.** Linked, never bundled or auto-downloaded. If it is not
  installed, the FX panel links to its repository.
