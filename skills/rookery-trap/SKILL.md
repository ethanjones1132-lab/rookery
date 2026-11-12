---
name: rookery-trap
description: Trap template for Rookery. Half-time snare, 3+3+2 hats, 808 notes, four-bar phrases, and the edits that make it harder or bouncier.
version: 0.2.0
author: Ethan Jones
license: GPL-3.0
platforms: [windows, linux, macos]
---

# Trap

Use this when the user asks for trap, an 808 loop, or a half-time song around 140. Load `rookery` first for the sample-song workflow, tool calls, and check fixes.

For a sample song, start with `rookery_new(name, bpm=142, bars=8, swing=0, genre="trap", key="F#", scale="minor")`.

Tempo stays between 134 and 150. Swing stays between 0 and 0.12. Default is 142 bpm and swing 0.

## Grooves

Start from `pocket-132-trap-bounce` (128–140), `theory-trap-rolls` (132–150), `pocket-142-skitter` (136–148), `pocket-152-hat-run` (146–158), or `theory-drill-slide` (138–150). Patterns and velocities are in `skills/rookery/grooves.json`.

## A four-bar phrase

The snare is half-time on beat 3. The hats carry the motion. The 808 carries the hook. Do not repeat one bar four times.

Kick:

```
x.........x.....x.........x.....x..x......x.....x.........x...x.
```

Snare (half-time, with a roll in bar 4):

```
........x...............x...............x...............x..x.x.x
```

Hats (3+3+2, then a 16th roll into the loop):

```
x.xxx.xxx.xxx.x.x.xxx.xxx.xxx.x.x.xxx.xxx.xxx.x.x.xxx.xxx.xxxxxx
```

Paste them as they are: 64 characters each.

Velocity is the feel. Kick: downbeat `1.0`, secondary `0.7–0.9`. Snare: backbeat `0.95`, roll hits `0.35–0.6` rising into the downbeat. Hats: accents `0.8–0.95`, ghosts `0.3–0.45`. Use a 64-value list for the hat phrase; the roll needs its own values.

## Tracks

Kick `factory:kick_boom`, snare `factory:snare_crack`, hat `factory:hat_closed`, and an optional 808 (`kind="bass"`). Use the shared Rookery role targets for add gains and pans. Master: a 30 Hz highpass, then a limiter `ceiling_db` -1.

The trap 808 target is −3..+1 LU relative to the kick; shorten long notes or lower its gain if the sub crowds the sample lead. Check the master `mix.bands_pct` before adding compression.

New projects use calibrated trims. After adding or removing a layer, run one `rookery_apply(ops=[{"op":"balance"}])`; then make taste gain edits on top.

## 808

The 808 is a bass track with `notes`. In an F# minor project, this line follows the project root and its chord changes.

```
notes = [
  {step: 0, len: 9, pitch: "F#1"}, {step: 10, len: 2, pitch: "F#1"},
  {step: 14, len: 2, pitch: "C#2"},
  {step: 16, len: 9, pitch: "F#1"}, {step: 26, len: 2, pitch: "A1"},
  {step: 30, len: 2, pitch: "F#1"},
  {step: 32, len: 7, pitch: "F#1"}, {step: 40, len: 2, pitch: "C#2"},
  {step: 42, len: 2, pitch: "F#1"}, {step: 46, len: 2, pitch: "E2"},
  {step: 48, len: 9, pitch: "F#1"}, {step: 58, len: 2, pitch: "C#2"},
  {step: 60, len: 2, pitch: "A1"}, {step: 62, len: 2, pitch: "F#1"}
]
```

Set them with `rookery_track(action="set", id="808", notes=notes)`. That call is supported; do not hedge or skip it.

For a slide, use the `808_long_glide` voice: its attack glides into the note. True portamento **between** two notes is not in the engine yet; do not claim it. Changing pitch between two notes is a pitch change, not a slide.

## Sample pairing

Use a dark piano, bell, or choir bed with a higher pluck or flute lead. Add at most one counter from a different family and register than both. Search bed/lead/counter together with `queries`, fetch the chosen IDs together, then apply the trap groove, F#-rooted 808, role-tagged sample tracks, `balance`, and arrangement in one `rookery_apply`. Read the fetched rhythm strings; keep the bed steady and put the lead in its gaps. If both are busy together, gate them on alternate bars or slice the lead into one-shot hits. Keep the 808 under its role target. The main `rookery` skill has the full placeholder call and arrangement.

## Moves

Harder: add a distortion stage to the chosen bass before the master limiter, switch hats to the 16th roll, and keep the bass and snare inside their role targets.

Bouncier: swing 0.10, the syncopated kick `x..x.....x.x....` extended to four bars, and a hat roll in bar 4. Leave the snare on beat 3.

Darker: hat `gain_db` −9, kick `pitch` −2, a master lowpass around 6000 Hz.

Sparser: keep the kick and half-time snare, use one bass source, drop hats to `x...x...x...x...`, and let the sample lead carry the bar.

## After the render

Read `meters`, `mix`, `fit`, and `mix_notes`. If the low end is muddy, shorten the 808 notes or lower its gain before adding compression. If a sample pair crowds the same register and beats, gate one or replace it; if the hook lead is buried, raise its track gain 2–3 dB. If `no_clipping` fails, lower the 808 or the master limiter ceiling. Render again after one change.
