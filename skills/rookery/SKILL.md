---
name: rookery
description: Drive the Rookery beat lab. Make a project, edit the grid, render, read the mix, and fix a failed check.
version: 0.2.0
author: Ethan Jones
license: GPL-3.0
platforms: [windows, linux, macos]
---

# Rookery

Use this when the user wants a beat, a change to the current beat, a render, or a read of what they clicked.

The project file is the only truth. Edit it with the tools below. Edits return a short receipt (`name`, `rev`, one line per change), not the whole project, so keep the `rev`. The user can click pads between your turns: call `rookery_state(since=<your last rev>)` to see only what changed and who changed it, and `rookery_state` with no `since` before you describe the whole grid.

The Flock is the user's instrument. Don't edit it; if the user perched birds, leave them and work around them.

## Tools

- `rookery_new(name, bpm, bars=4, swing=0, genre?, key?, scale?)` creates the project. `bars` is 4 or 8; `genre` is `boom-bap` or `trap`; `key` is a pitch class and `scale` is `major` or `minor`.
- `rookery_track(action, id, kind?, source?, steps?, velocity?, fx?, role?, gain_db?, pan?, mute?, solo?, pitch?, notes?, slices?, mode?, key_lock?, loop_bars?, duck?, choke_group?)` adds, removes, or sets a track. `action` is `add`, `remove`, or `set`. Sample `mode` is `oneshot` or `loop`; loop controls are `key_lock` (false for unpitched audio) and `loop_bars` (1, 2, 4, or 8). Use `id="master"` with `action="set"` to change `bpm`, `bars`, `swing`, or `humanize_ms` (0 to 6 ms of deterministic timing feel; drums stay on the grid).
- `rookery_steps(track, steps, velocity?)` sets the pattern. `x` is a hit, `.` is a rest. A short string repeats to fill the loop, but its length must divide the loop (1, 2, 4, 8, 16, 32 or 64 steps at 4 bars; up to 128 at 8 bars), or the edit is rejected. `velocity` is a list that repeats the same way. One value means every hit.
- `rookery_mix(target, fx)` sets the effect chain on `master` or a track id.
- `rookery_apply(ops=[...])` applies a **batch** of edits in one revision. Each item is one of `steps`, `track`, `mix`, `meta`, `clear`, `groove`, `balance`, or `arrange`; track ops accept the same sample fields as `rookery_track`. One call, one history step, one combined diff. Use it for a whole build.
- `rookery_render(name?, song?)` renders, runs the checks, and returns the wav path, hash, report, per-track `meters` and the master `mix`. Loop renders also return role `balance`, pairwise sample `fit`, and actionable `mix_notes`; `song=true` renders the whole arrangement instead of one loop and omits those loop-only fields.
- `rookery_samples(action, query? | queries?, kind?, bpm?, key?, max_seconds?, limit?, id? | ids?, source?)` searches Soundza by default, or Openverse with `source="openverse"`. A search batch has 1–4 `queries` and returns one result group per query; a fetch batch has 1–4 `ids` and returns one result per id. Fetch saves the sound and returns a ready `source` (`user:library/...`) plus its profile. Downloads need a free `SOUNDZA_API_KEY`; search works without one.
- `rookery_export(name?, song?, stems?, midi?, fps?)` writes a creator-ready folder: the mix WAV, stems, MIDI, `cues.json` (beats, bars, kicks, snares, sections, and frame numbers with `fps`) and `LICENSE.txt`. Other agents making a video can call it as their soundtrack step.
- `rookery_state(name?, since?)` is the grid as text. With `since=<rev>` it returns only the changes after that revision, each marked agent or user. Call it before answering "what changed?".
- `rookery_undo(name?, steps=1)` restores a history snapshot. Undo covers your edits and the user's clicks.
- `rookery_kits()` lists factory sounds, the user kit folder, and whether Corvus FX is installed.

## The rule that matters most: phrase, don't loop

A one-bar cell is a reference, not a beat. A beat is at least four bars. Write the **full** step string (`bars * 16` characters: 64 for four bars, 128 for eight). Each bar has a job:

- **Bar 1** states the idea.
- **Bar 2** repeats it, with one ghost note or a different velocity.
- **Bar 3** lifts or drops: a different kick, an open hat, a snare ghost.
- **Bar 4** is the turnaround/fill: extra snares, a hat run, a kick drop, a bass approach note.

For eight bars, bars 1–4 are A and bars 5–8 are A′: same groove, one new element (an open hat, a percussion layer, a busier bass) and a bigger fill in bar 8.

Never write a 4-bar beat as the same 16 characters four times. If the user asks for "simple," keep the same instruments but still change the fill and the ghost notes.

## Velocity is the feel

Do not set every hit to the same velocity.

- Kick: the downbeat 1.0, secondary kicks 0.7–0.9.
- Snare: backbeat 0.95, ghost snares 0.25–0.35.
- Hats: on-beat 0.55–0.7, off-beat 0.3–0.45, a 16th run 0.25–0.4.
- Percussion: 0.4–0.7, sparse.
- Bass notes: root 0.9–1.0, approach/passing 0.55–0.7.

`velocity` is a list that repeats with the pattern. Give it 16 or 64 values, not one.

## Grooves

`grooves.json` in this skill has 20 drum templates with step strings, velocity lists, BPM ranges, swing and variations. Read the one that matches the genre and BPM, then adapt it. The strongest starting points:

| id | genre | BPM | feel |
| --- | --- | --- | --- |
| `theory-boom-bap-ghost` | boom bap | 86–94 | backbeat with ghost snares; swing 0.42 |
| `pocket-95-ghost-snare` | boom bap | 90–100 | loose 95 clap/snare pocket |
| `pocket-89-swung-hats` | lo-fi | 84–94 | late swung hats, ghost kick |
| `theory-lofi-limp` | lo-fi | 70–90 | lazy swing and a ghost kick |
| `pocket-132-trap-bounce` | trap | 128–140 | busy 808 kick, half-time snare |
| `theory-trap-rolls` | trap | 132–150 | half-time snare, 1/32 roll hint |
| `pocket-142-skitter` | trap/drill | 136–148 | skittering hats, half-time snare |
| `theory-drill-slide` | drill | 138–150 | half-time drill, sliding 808 |
| `theory-house-4floor` | house | 120–128 | four-on-the-floor, offbeat open hats |
| `pocket-124-tribal-house` | house | 118–128 | four-on-the-floor with a tribal shaker |
| `theory-uk-garage-2step` | UK garage | 130–138 | two-step skip |
| `theory-afrobeats-clave` | afrobeats | 100–112 | 3-2 son clave feel |
| `pocket-104-dancehall` | dancehall | 96–108 | dancehall kick, clipped offbeat hat |
| `pocket-107-funk-strut` | funk | 100–112 | strutting funk kick with rim answers |
| `theory-half-time-break` | breakbeat | 160–180 | half-time breakbeat |
| `pocket-180-jungle-chop` | jungle | 165–180 | chopped jungle break |

To use one:

1. Read its `tracks` (kick, snare, clap, hat, hat_open, perc) and `bars`.
2. Create the project with `rookery_new` and the template's BPM/swing.
3. Add each role with the matching factory source (see below).
4. Set the steps and velocity. Give both hat roles `choke_group="hats"`.
5. Extend the one-bar template to four bars, then add a fill in bar 4 and a variation in bar 2. Do not just repeat it.

## Sample-first song workflow

For a sample-led song, use this order: `rookery_new` with key/scale and BPM → one `rookery_samples(search)` with `queries` for bed, lead, counter (and optionally a drum loop or texture) → one `rookery_samples(fetch)` with the selected `ids` → one `rookery_apply` containing the drum groove, full-length phrase patterns, bass, role-tagged sample tracks, `balance`, and `arrange` → `rookery_render(song=true)`. That is five tool calls; batch queries, fetches, and edits rather than adding tracks one by one. Render a loop first only when `fit` needs checking.

### Choose complementary sounds

Use one sustained chord bed (rhodes, piano, guitar, strings, organ), one higher-register melodic lead (flute, sax, bell, pluck, vocal chop, lead guitar), and at most one counter. A counter must differ in both family and register from the bed and lead. Never stack two layers from the same family in the same register. Prefer tagged BPM within 10% of the song and fetch-reported key shifts of 5 semitones or less; replace a larger shift rather than forcing it. Use the fetched `profile` (`register`, `bands`, `rhythm`, `sustain`, `pitched`, `role_hint`) to choose and place sounds. Unpitched material should use `key_lock:false`.

| Style | Bed + lead | Optional counter / texture |
| --- | --- | --- |
| Boom bap | dusty rhodes or soul-guitar chords + flute, horn, or vocal-chop phrase | different-family guitar answer; quiet vinyl texture |
| Lo-fi | piano or guitar bed + soft bell/pluck lead | sparse different-register counter; quiet vinyl texture |
| Trap | dark piano/bell or choir bed + pluck/flute lead | one different-family counter; 808 follows the harmony |

### Make the melody answer

- Read the fetched 16-character `rhythm` strings. Let the bed be steady; place the lead in its quiet steps for call and response.
- If both are busy on the same steps, gate them on alternate bars (`steps:"x."` and `".x"`), move one to a different section, or chop the lead into one-shot slices (`slices`, digit steps) in the bed's gaps. Use `mode:"loop"` for beds and melodic loops; use `mode:"oneshot"` for chops and textures.
- Put bass notes with the kick and the bed's chord changes. Start bar 1 on the root of the project key; change bass notes with the bed harmony.
- After a loop render, use pair `fit` and `mix_notes`: high register and rhythm overlap calls for alternate-bar gating, a section change, or a more distinct sample.

### Arrange the samples

For an 8-bar project, shape each section: intro bed alone (or filtered/quiet drums) → verse bed + drums + bass → hook adds lead → verse 2 swaps lead for the counter or gates the bed → breakdown lead or bed alone, no kick → final hook all layers → outro bed alone. Use `mute` and per-section `steps` for gates, and `fill:true` before hooks. Neighbouring sections must differ in at least two layers or patterns; no unchanged run may exceed 16 bars.

The full copy-paste shape below uses placeholders, not real Soundza IDs. Replace each ID with one from that query group, and each file placeholder with the `source` returned by fetch. Eight 8-bar passes at 90 BPM last about 2:51.

```text
  rookery_new(name="amber-room", bpm=90, bars=8, swing=0.58, genre="boom-bap", key="A", scale="minor")
rookery_samples(action="search", queries=["sustained rhodes chord loop", "high flute melodic phrase", "sparse soul guitar counter"], kind="loop", bpm=90, key="A", limit=6)
rookery_samples(action="fetch", ids=["<bed-id>", "<lead-id>", "<counter-id>"])
rookery_apply(name="amber-room", ops=[
    {"op":"groove", "groove":"theory-boom-bap-ghost", "swing":0.58},
    {"op":"steps", "track":"kick", "steps":"x.....x...x.....x.....x.....x...x.....x...x.....x.....x...x.x...x.....x...x.....x.....x...x.x...x.....x...x.....x.....x...x.x..."},
    {"op":"steps", "track":"snare", "steps":"....x.......x.......x..x....x..x....x.......x.......x..x..x.x.x.....x.......x.......x..x....x..x....x.......x.......x..x..x.xxxx"},
    {"op":"steps", "track":"hat", "steps":"x.x.x.x.x.x.x.x.x.x.x.x.x.x.x.x.x.x.x.x.x.x.x.x.x.x.x.x.x.xxx.xxx.x.x.x.x.x.x.x.xxx.x.x.x.x.x.x.x.x.x.x.x.x.x.x.x.x.x.x.x.xxx.xx"},
  {"op":"track", "action":"add", "id":"808", "kind":"bass", "source":"factory:808", "duck":0.4,
   "notes":[{"step":0,"len":12,"pitch":"A1"},{"step":16,"len":6,"pitch":"E2"},
            {"step":32,"len":12,"pitch":"F1"},{"step":48,"len":6,"pitch":"C2"},
            {"step":64,"len":12,"pitch":"A1"},{"step":80,"len":6,"pitch":"G1"},
            {"step":96,"len":12,"pitch":"F1"},{"step":112,"len":6,"pitch":"E1"}]},
  {"op":"track", "action":"add", "id":"bed", "kind":"sample", "source":"user:library/<bed file>.flac", "mode":"loop", "steps":"xxxxxxxx", "role":"bed"},
  {"op":"track", "action":"add", "id":"lead", "kind":"sample", "source":"user:library/<lead file>.flac", "mode":"loop", "steps":"xxxxxxxx", "role":"lead"},
  {"op":"track", "action":"add", "id":"counter", "kind":"sample", "source":"user:library/<counter file>.flac", "mode":"loop", "steps":"xxxxxxxx", "role":"counter"},
  {"op":"balance"},
  {"op":"arrange", "sections":[
    {"id":"intro","repeat":1,"mute":["kick","snare","hat","808","lead","counter"]},
    {"id":"verse","repeat":1,"mute":["lead","counter"],"fill":true},
    {"id":"hook","repeat":1,"mute":["counter"],"steps":{"hat":"xxxxxxxxxxxxxxxx"},"fill":true},
    {"id":"verse-2","repeat":1,"mute":["lead"],"steps":{"hat":"x...x...x...x..."},"fill":true},
    {"id":"breakdown","repeat":1,"mute":["kick","snare","hat","808","lead","counter"]},
    {"id":"final-hook","repeat":2,"mute":[],"steps":{"hat":"x.x.x.x.x.x.x.x."}},
    {"id":"outro","repeat":1,"mute":["kick","snare","hat","808","lead","counter"]}
  ]}
])
rookery_render(name="amber-room", song=true)
```

Finished means at least five sections, 2:00–3:00 total, outro last, and the variety rule passes. Total arrangement duration must remain ≤180 seconds (`bars * 240 / bpm * section repeats`).

## Drum sources

Factory drums (new beats default to `kick_punch`/`kick_deep`, `snare_snap`, `hat_tight`, `clap_stack`, `hat_open_short` and `808_round`, tuned against a commercial kit; prefer them): `kick_boom`, `kick_punch`, `kick_thump`, `kick_sub`, `kick_snap`, `kick_rumble`, `snare_crack`, `snare_crack_wide`, `snare_snap_dry`, `snare_body`, `snare_burst`, `snare_dust`, `clap`, `clap_stack`, `clap_wide`, `clap_sharp`, `clap_dust`, `clap_tail`, `hat_closed`, `hat_closed_bright`, `hat_closed_dark`, `hat_closed_dust`, `hat_closed_metal`, `hat_closed_tight_tick`, `hat_open`, `hat_open_wash`, `hat_open_sizzle`, `hat_open_bright`, `hat_open_dark`, `hat_open_long`, `rim`, `perc`, `perc_tom_low`, `perc_tom_high`, `perc_woodblock`, `perc_rimshot`, `perc_bongo`.

Bass: `808`, `808_sub_clean`, `808_long_glide`, `808_drop`, `808_bloom`, `808_grit`.

## Bass and 808

Bass tracks use `notes`: a list of `{step, len, pitch}`. Use note names (`D1`, `F1`, `A1`) or MIDI numbers. Write a line, not one long note: root, fifth, approach note, a rest.

For a slide, use the `808_long_glide` voice: its attack glides into the note. True portamento **between** two notes is not in the engine yet; do not claim it.

For boom bap, duck an added 808 0.3–0.5 under the kick. Shorten notes or reduce gain if the low end is muddy; don't add compression first.

## Samples

Batch 1–4 descriptive queries with one `rookery_samples(action="search", queries=[...])` call. Results are grouped by query; each hit carries tags, BPM/key when known, seamless-loop status, and a fit score. Fetch the selected IDs together with one `rookery_samples(action="fetch", ids=[...])` call. Each result includes its original id, ready `source`, key-lock shift, and compact sample profile. Match the fetched profile to the query role before adding the track.

Without a `SOUNDZA_API_KEY`, search still works but fetch does not. Tell the user to get a free key at https://soundza.com/developers/keys and set `SOUNDZA_API_KEY` in Hermes; never ask them to paste a key into the chat. Offer Openverse as the fallback with `source="openverse"`. Soundza removes sounds: if a fetched sound disappears, fetch a replacement before release.

**Melodic loops: use `mode:"loop"`.** Rookery stretches the loop to the project tempo, applies key lock to the project `key`/`scale`, starts on its downbeat, and repeats it on each bar with seamless crossfades. Legacy projects without a project key use the stored project harmony. In loop mode `steps` gates bars, not 16ths: `x` plays every bar, `x.` every other bar, `xxx.` drops the fourth bar. Don't use `pitch` to fix the key; use the reported key-lock shift and replace a sample if it exceeds 5 semitones. Use `pitch` only for a deliberate semitone change. Optional: `loop_bars` uses the first N bars; `duck` (0–1) dips the loop under the kick. Bass tracks also accept `duck`.

```
rookery_track(action="add", id="bed", kind="sample", source="user:library/<bed file>.flac", mode="loop", steps="x", role="bed", duck=0.3)
```

**One-shots and textures** (a vocal chop, a crackle, a hit) stay in the default mode: a hit plays until the track's next hit, like a hardware sampler. Sample tracks are cut into 10 slices by default and `x` plays the first one; set `slices=1` to play the whole sound from each hit, or keep slices and use digits `0`-`9` in `steps` to chop. Keep textures quiet (`gain_db` -12 or lower).

## Music for a video

When the user needs music for a video, animation or ad: ask the length and the mood, build the loop, arrange it so the song length fits (song length = total repeats × one loop), render with `song=true`, then `rookery_export(fps=<their frame rate>)`. Tell them to cut scene changes on `bars` and hits on `kicks` from `cues.json`, and that `LICENSE.txt` says the music is theirs.

## Mix cheat sheet

Targets are each stem's integrated LU relative to the kick; use the ranges, not loudness chasing. Default pan is in the last column.

| Role | Boom bap | Trap | Default pan |
|---|---:|---:|---|
| Kick | 0 | 0 | center |
| Snare / clap | −3..+1 | −3..+1 | center |
| Closed hat | −12..−7 | −10..−5 | +0.15 |
| Open hat | −14..−8 | −12..−7 | −0.15 |
| Perc / rim | −14..−7 | −14..−7 | −0.2 |
| 808 / bass | −6..−2 | −3..+1 | center |
| Sample bed | −8..−4 | −8..−4 | 0 |
| Sample lead | −5..−1 | −5..−1 | +0.2 |
| Sample counter | −11..−6 | −11..−6 | −0.25 |
| Sample drums | −6..−2 | −6..−2 | center |
| Sample texture | −20..−12 | −20..−12 | center |

A factory track added without `gain_db` starts at its role's target midpoint (measured per sound). New projects use calibrated trims. `{"op":"balance"}` sets track gains to role targets; use it after adding/removing layers, then make taste edits. Read loop `balance` as each track's LU relative to the kick (`ok` means in range); `mix_notes` names misses and crowded sample pairs. `fit` gives pairwise register/rhythm overlap. If a render still shows misses, run one `balance` op rather than hand-editing gains. If there is no kick, `ref` uses the loudest drum. Read master `mix` for stereo correlation (0.4–0.9 healthy; >0.95 nearly mono), bands (`sub` 20–120 Hz, `mid` 400–2500 Hz), centroid, crest, and L/R balance. The master stage normalises to −14 LUFS; don't raise tracks to chase loudness.

## After a render

The report has six checks. Each one has `pass` and `value`. Talk about a failure by name and by the number. Then make one edit and render again.

- `length_exact` failed: the renderer is wrong. Say so. Do not chase it with gain changes.
- `no_clipping` failed: lower the hottest track by 3 dB, or set a master limiter with `ceiling_db` -1. Render again.
- `loudness` failed: the renderer normalises to −14 LUFS, so this is a renderer/meter problem. Do not "fix" it by raising tracks; that changes the balance.
- `seam_click` failed: lower the reverb or delay mix, then render again. The tail has to fold back into the start of the loop.
- `not_silent` failed: the pattern is empty or the gains are down. Put hits on the drums or samples, then render again.
- `deterministic` failed: you changed something between the two renders, or a random call ignored the project seed. Render the same project again before you tell the user the hash.

## Corvus

Call `rookery_kits` before you promise Corvus. Rookery loads only the VST3 the user set as `corvus_vst3_path` in its plugin settings: add `{"type":"vst3","params":{...}}` to a chain to switch it on, with parameter names from `corvus.params`. There is no path to pass. If `corvus.found` is false, use the built-in limiter and tell the user to set `corvus_vst3_path` (or that Corvus is not installed); never download it.

## Same beat, same bytes

Same project, same seed, same renderer version: the hash matches. Say the hash when you claim that. To prove it, render twice without editing in between.

A bad edit comes back as a message. Read it, fix the argument, and try that call again. The file did not change.
