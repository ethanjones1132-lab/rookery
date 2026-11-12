# Rookery

**A DAW that lives inside your agent.** Tell Hermes the beat; watch it build. Every render is exact-length, measured and reproducible.

Rookery is a step-sequencer DAW built as a Hermes plugin. The agent and you edit **one JSON project file** in the same window: you click pads, it writes steps, and both of you see the same grid, the same history and the same render. It runs locally. No account, no credits, no cloud music API, no model download.

```
"Make a dusty boom bap at 90 in A minor, eight bars."
  → the grid fills in live, step by step
  → the agent searches Soundza for a bed, a lead and a counter
  → drums, bass, samples, balance and the arrangement land in one batch
  → the render draws, the playhead runs, six checks go green
  → "the lead is buried" → it reads the mix report and raises the lead
  → "export it for a video" → WAV, stems, MIDI, cues.json and LICENSE.txt
```

> **Demo:** `docs/demo.md` has the 90-second shot list. Add the video URL and a GIF here before publishing.

## What it is

- **A real step sequencer.** Transport, channel rack, per-step velocity, swing, per-track gain/pan/FX, a master chain, a waveform and a playhead.
- **Sample-first songs.** `rookery_samples` searches Soundza by default (lossless, tempo/key tagged, royalty-free) and fetches into your own kit folder with the credit recorded. `source="openverse"` searches Openverse's CC0 sounds instead. Search works without a key; downloads need a free optional `SOUNDZA_API_KEY`.
- **Songs, not just loops.** Give the project a key and scale, layer a chord bed, a melodic lead and at most one counter, then `rookery_apply` an arrangement: 1–16 sections, mutes and step/note overrides per section, and a deterministic fill on a section's last repeat. `rookery_render(song=true)` renders the whole arrangement.
- **The Flock, your instrument on the page.** Twelve costumed corvids on a wire, each a voice (bass, keys, pad, lead, arp, call). They sing in key, on the grid, and answer each other. Seating them, swapping their songs, muting, soloing and the murmuration combos are done in the Rookery page: the agent has no Flock tool, so it cannot perch, re-voice or mix birds for you (it can read the wire in `rookery_state` and undo history). The Flock renders into the same mix, the same hash and the same six checks as the drums.
- **A checked renderer.** 44.1 kHz, exact sample count, seamless loop, true peak ≤ −1 dBTP, −14 LUFS, a per-track meter and a master mix report. The same project renders the same bytes.
- **A mix report the agent can act on.** A loop render returns role `balance` (each track's LU relative to the kick), pairwise sample `fit` (register and rhythm overlap) and actionable `mix_notes`. That is the difference between "the checks passed" and "the beat sounds right."
- **Two editors, one truth.** Agent tools and user clicks share `rev`, history and undo. The agent sees what you clicked; you see what it wrote, as it writes it.
- **A chat inside the page.** Ask for a beat, a change or a render without leaving the instrument. It uses your Hermes session and model.
- **Creator-ready export.** WAV, per-track and Flock stems, a MIDI file, `cues.json` (bars, kicks, snares, sections and optional frame cues for video work), `LICENSE.txt` and a short `README.txt`, all deterministic.
- **A chat card.** `rookery_render` returns a compact, playable card in the agent's reply, with the mini grid and the check lights.

The positioning is simple: **license-clean music for creators and video**, made on your machine, with an agent that can measure what it made. No generated-audio subscription, no unclear sample rights, no guesswork about whether the loop actually loops.

## The sample-first workflow

1. `rookery_new(name, bpm, bars, genre?, swing?, key?, scale?)` creates the project. `key` is a pitch class (`A`, `Bb`, …) and `scale` is `major` or `minor`.
2. `rookery_samples(action="search", queries=[...], kind="loop", bpm=..., key=...)` runs 1–4 descriptive searches in one call and returns one group per query, with tags, BPM/key when known, seamless-loop status and a fit score. Soundza is the default; `source="openverse"` uses CC0 previews.
3. `rookery_samples(action="fetch", ids=[...])` imports up to four selected sounds together. Each comes back as a ready `user:library/...` source, with its key-lock shift, a compact profile (`register`, `bands`, `rhythm`, `sustain`, `pitched`, `role_hint`) and the credit recorded in `credits.json`.
4. `rookery_apply(ops=[...])` writes the whole song in one revision: a named `groove`, `track` atoms for drums, bass and samples (with `role` and `duck`), `balance`, and `arrange`.
5. `rookery_render(song=true)` renders and checks the arrangement. Render a loop first only when you want the loop-only `balance`/`fit`/`mix_notes` read.
6. `rookery_export(fps=...)` writes the creator folder.

Melodic sample loops use `mode:"loop"` on the track (`rookery_track`, or a `track` atom in `rookery_apply`): Rookery stretches them to the project tempo, key-locks them to the project key/scale, starts them on the downbeat and repeats them with crossfades. One-shots and textures stay in the default slice mode (10 slices, `x` plays the first, digits `0`–`9` chop). Bass tracks use `notes` as `{step, len, pitch}` and can duck under the kick.

## How it differs

| | Rookery | `hermes-band` | Kumi | Hermes Sound Studio | Agent Music Jam |
|---|---|---|---|---|---|
| **What it is** | A DAW inside Hermes | A deterministic arrangement renderer | Hermes inside Ableton Live, REAPER and Renoise | A procedural sound designer with a piano-grid composer | A live browser band conducted by Hermes |
| **UI** | Live grid, wire, waveform, mixer, chat | None (tools + skill) | The DAW's UI plus a Desktop pane and sound-map workspace | Desktop page with a piano grid, velocity and loops | Browser studio with a piano keyboard |
| **Agent edits the project** | Yes, the same file as you | Yes, arrangement data | Yes, the open DAW project | Yes, through a background draft conversation | Yes, by conducting the band |
| **Your own samples** | Yes: Soundza or Openverse into a local kit, key-locked loops | No | Your DAW's samples | No | No |
| **Deterministic re-render** | Yes: render hash + audio hash | Yes | Not claimed | Not claimed | Not claimed |
| **Runs locally, no account** | Yes | Yes | Yes, with a DAW installed | Yes | Yes |
| **Works from CLI/Telegram** | Same tools, any Hermes surface | Yes | Not claimed | Not claimed | Starts from a Hermes tool; playback is in the browser |
| **Sound and export** | Synthesized drums/808, first-party voices, Corvus FX; WAV, stems, MIDI, cues | General MIDI soundfont; wav/mp3 and stems | Your DAW's instruments and samples | Procedural Web Audio; WAV/JSON/TypeScript | Synthesized band; WAV/MIDI |

`hermes-band` is already merged into the Hermes plugin catalog; Rookery is a
different bet (a shared, visible project rather than a renderer). Sources for the
rivals' claims: [Kumi PR #152258](https://github.com/NousResearch/hermes-agent/pull/152258),
[Hermes Sound Studio PR #152362](https://github.com/NousResearch/hermes-agent/pull/152362),
[Agent Music Jam](https://github.com/vdimarco/agent-music-jam).

## Hermes surfaces used

- **Tools (11):** `rookery_new`, `rookery_steps`, `rookery_track`, `rookery_mix`, `rookery_apply`, `rookery_render`, `rookery_export`, `rookery_state`, `rookery_undo`, `rookery_kits`, `rookery_samples`.
- **Bundled skills:** `rookery`, `rookery-boom-bap`, `rookery-trap`.
- **Desktop page:** `/rookery`, a sidebar row, the live grid, the Flock wire (edited in the page only), the mixer, the waveform and the in-page chat.
- **Plugin API:** `/api/plugins/rookery/…` for projects, edits, undo, renders, audio, export, status and the Flock catalog.
- **Events:** `project.updated` (with the step diff that drives the live build), `project.created` / `renamed` / `deleted`, `agent.editing`, `render.started` / `done` / `failed`.
- **Chat media renderer:** a mini beat card for `rookery_render`.
- **Plugin data:** projects, history, renders, exports and the user kit live under `plugin_data_dir("rookery")`.

## Reliability

Every render writes `report.json` and returns it to the agent and the page:

| Check | Pass when |
|---|---|
| `length_exact` | `len(wav) == round(bars * 4 * 60 / bpm * sr)` |
| `no_clipping` | true peak ≤ −1.0 dBTP (4× oversampled) |
| `loudness` | integrated LUFS −14 ± 1 |
| `seam_click` | the loop seam jump ≤ the body's 99.9th percentile × 1.5 |
| `not_silent` | RMS above −50 dBFS |
| `deterministic` | an independent second render has identical WAV bytes |

`length_exact`, `loudness` and `no_clipping` are enforced by the renderer, so they are regression sensors; `seam_click`, `not_silent` and `deterministic` are the live ones. The render filename is the SHA-256 of the canonical audio projection plus the renderer version, so a re-render of an unchanged project is a cache hit.

**Same beat, same bytes.** On the same machine and renderer version, the same project produces identical PCM. The canonical audio projection leaves out the project name and other metadata that cannot change the audio, so a copy under a new name produces the same render hash **and** the same `wav_hash` (the SHA-256 of the WAV bytes). The renderer version includes the NumPy/SciPy/pedalboard/soundfile/pyloudnorm versions, so a dependency upgrade changes the version string (and the hash) deliberately.

### The mix report

The agent cannot listen, so the render returns numbers it can act on:

- per-track `meters`: RMS and peak in dB;
- loop role `balance`: each track's integrated LU relative to the kick, with `ok`/miss per role;
- loop pairwise sample `fit`: register and rhythm overlap for each sample pair;
- loop `mix_notes`: named misses and crowded pairs, with the fix;
- master `mix`: stereo correlation, width, L/R balance, crest factor, spectral centroid and band energy percentages (sub/low/mid/high/air).

The skill teaches the repair: run one `balance` op, gate two crowded layers onto alternate bars, raise a buried lead, high-pass a pad, shorten an 808, widen a mono mix.

## Install

Requires **Hermes Agent 0.23.0 or newer** (the tested floor).

```
hermes plugins install ethanjones1132-lab/rookery
hermes plugins enable rookery
```

Or link a checkout for development (Windows):

```
mklink /J "%LOCALAPPDATA%\hermes\plugins\rookery" "C:\Projects\rookery"
```

Python dependencies are declared and capped in `pyproject.toml`: `pedalboard>=0.9.26,<0.10`, `numpy>=2,<3`, `scipy>=1.11,<2`, `soundfile>=0.13,<0.15`, `pyloudnorm>=0.2,<0.3`. SciPy is used directly by the renderer and the checks.

Open **Rookery** from the Hermes Desktop sidebar, or ask from any Hermes surface:

```
Make a dusty boom bap at 90 in A minor, eight bars.
Find a rhodes bed, a flute lead and a guitar counter on Soundza.
The lead is buried. Fix it.
Export this for a video at 30 fps.
```

## Validation

Run on **2026-11-11** on **Windows 11**, Hermes **0.23.0** (`2bd378ed1b8d`), Python **3.11.15** in the Hermes dev venv (the managed runtime is **3.14.9**):

```
python -m pytest tests/engine tests/acceptance -q -p no:cacheprovider
# 512 passed, 6 xfailed in 226.47s

python tools/audit.py
PASS binaries: none tracked
PASS samples: 67 first-party voice one-shots (5.17 MiB, manifest provenance ok)
PASS deps: 5 capped
PASS provides_tools: 11 match register()
PASS requires_hermes: >=0.23.0
PASS secrets: no credential reads in code
PASS self_update: none found

node dev/preview/check-mock.mjs
ok: routes, edit ops, validation, revs, undo, events, deterministic renders, audio, status and the lost-event fallback
```

`hermes plugins validate .` passes every check (manifest, requires_hermes,
loadable, 5 capped Python requirements, capability probe, declared tools/hooks/
middleware, no collisions, security scan safe, no core override, desktop surface
inside the SDK, plugin host isolation):

```
hermes plugins validate .
# ... 16 checks ...
# Validation passed.
```

`hermes plugins validate . --install-deps` reaches the same result but its
dependency-preparation step fails on this machine before validation runs: two
linked Rookery checkouts share the name `rookery` in the local Hermes workspace
(`uv` reports "Two workspace members are both named `rookery`"). That is a local
workspace collision, not a dependency resolution problem; the pinned, capped
requirements are the five above.

The headless end-to-end proof (the registered tool handlers in the Hermes
managed runtime) and loop-mode seam validation are in
`docs/validation-2026-11-10.md`. `.github/workflows/test.yml` runs the same suite
on Ubuntu, macOS and Windows, plus Python 3.14 on Ubuntu.

**What was not tested:** the Desktop page, live audio playback and Corvus knobs
on macOS/Linux; remote gateways (Telegram/CLI delivery of the WAV); a
fresh-machine catalog install; and the Flock in real Desktop on the final
commit. The engine/API/handler/export paths are covered by the suite. Loop-mode
seam testing found a backwards 5 ms wrap blend that broke an already-seamless
phrase (`seam_click` 0.3572 before, 0.0000 after); the blend is removed and
synthetic loops now pass at 84, 90 and 100 BPM.

## Disclosure

- **Local files.** Projects, history, renders and exports are written under `plugin_data_dir("rookery")`. Nothing is uploaded.
- **User kit folder.** Rookery reads audio files from the configured `user_kit_dir` (default: `plugin_data_dir/kits`). It never copies them into the repo.
- **VST3.** If you point `corvus_vst3_path` at a VST3, Rookery loads it in-process through pedalboard. That is third-party native code running with your permissions. Rookery loads only that configured plugin: the agent cannot name a path, and an effect that names any other plugin is refused. If it is not configured, no VST3 is loaded and Rookery uses its built-in effects.
- **First-party voice one-shots.** `rookery/flock/voices/` contains FLAC one-shots rendered by the Rookery authors with Xfer Serum from original patches. No Serum binaries, presets or wavetable files are included; Serum is a build-time authoring tool only. The manifest records the provenance, patch hashes and an 8 MiB budget.
- **Network (`rookery_samples` only).** The core plugin makes no network calls. `rookery_samples` searches Soundza at `api.soundza.com`, and a download follows the signed link Soundza issues for it, on Soundza's Cloudflare R2 storage (`*.r2.cloudflarestorage.com`; the link lasts five minutes). Every Soundza download must pass Rookery's sample quality gate (lossless, 44.1 kHz or more, no clipping, loops in whole bars) before it is saved. With `source="openverse"` it searches `api.openverse.org` and downloads CC0 previews from `cdn.freesound.org`. Search works without a key; downloads need a free `SOUNDZA_API_KEY` set through Hermes's env (optional; Rookery never logs or stores it). Soundza sounds are royalty-free for use in your music with no attribution required, but you may not share a sound, or stems that are only one of them, as standalone files or in a sample pack. Rookery checks Soundza's removals list weekly and deletes sounds that were taken down. Credits, with the licence and landing URL, live in `<user_kit_dir>/library/credits.json`. No telemetry.
- **Corvus FX.** Linked, never bundled or auto-downloaded. If it is not installed, the FX panel links to its repository.

## Limits

- **Songs are arrangements of loops.** An arrangement is 1–16 sections, each repeating 1–8 times, with per-section mutes, step overrides, velocity/notes overrides and an optional fill. There are no tempo, meter or automation changes inside a song.
- **No vocals or audio recording.** The Flock voices are synthesized/one-shot instruments. The sample track plays your own files; loop-mode samples are time-stretched and key-locked, while one-shot slices are not stretched.
- **The Flock is a page instrument.** Twelve birds, three songs each, five templates, six murmuration combos and a secret seventh perch. The page seats and edits them; the agent has no Flock tool, so it cannot add or re-voice the wire for you.
- **No note-to-note 808 portamento.** The `808_long_glide` voice glides within a note; a slide between two notes is not implemented yet.
- **VST3 effects, not instruments.** pedalboard hosts an installed VST3 effect (Corvus); Rookery does not host instrument plugins.
- **No MIDI import.** MIDI export exists; importing a MIDI file does not.
- **Windows is the tested platform for the page and audio.** The engine is pure Python and the CI matrix is set up for Ubuntu/macOS. This pass could not run WSL (`E_ACCESSDENIED` attaching its disk), so the Desktop page and audio path remain Windows 11 evidence only.

## Credits

- **pedalboard** — Spotify, GPL-3.0. The FX chains and VST3 hosting.
- **NumPy**, **SciPy**, **soundfile**, **pyloudnorm** — BSD/MIT-style licenses; the DSP and the meters.
- **Hermes Agent** — Nous Research. The plugin surface, the Desktop SDK and the gateway.
- **soundza.com** — Sounds by soundza.com, used under the Soundza Standard License (royalty-free, no attribution required).
- **Drum targets** — `tools/drum_match.py` measured a commercial pack (Capital Drum Kit 4) to derive numeric tuning targets. **No audio from that pack is copied, shipped or required**: the repository stores only the numbers in `tools/drum_targets.json`, and the voices are synthesized.

Rookery is GPL-3.0-only. The project file is yours; the sounds are generated locally; the renders are reproducible.
