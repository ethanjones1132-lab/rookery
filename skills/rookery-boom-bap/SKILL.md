---
name: rookery-boom-bap
description: Boom bap template for Rookery. Tempo, swing, four-bar drum phrases, ghost notes, fills, bass, and the edits that make it dustier or harder.
version: 0.2.0
author: Ethan Jones
license: GPL-3.0
platforms: [windows, linux, macos]
---

# Boom bap

Use this when the user asks for boom bap, a dusty loop, or a 90 bpm head-nod song. Load `rookery` first for the sample-song workflow, tool calls, and check fixes.

For a sample song, start with `rookery_new(name="amber-room", bpm=90, bars=8, swing=0.58, genre="boom-bap", key="D", scale="minor")`.

Tempo stays between 84 and 96. Swing stays between 0.54 and 0.66. Default is 90 bpm and swing 0.58.

## Grooves

Start from `theory-boom-bap-ghost` (swing 0.42), or `pocket-95-ghost-snare` (90–100), `pocket-89-swung-hats` (84–94), or `pocket-107-funk-strut` (100–112) for a busier pocket. Patterns and velocities are in `skills/rookery/grooves.json`.

## A four-bar phrase

Do not repeat one bar four times. This is a 64-step phrase: A A A' fill. The last bar is the turnaround.

Kick:

```
x.....x...x.....x.....x.....x...x.....x...x.....x.....x...x.x...
```

Snare (the second and fourth bars carry ghost notes; the fourth is the fill):

```
....x.......x.......x..x....x..x....x.......x.......x..x..x.x.x.
```

Hats (the fourth bar runs into the turnaround):

```
x.x.x.x.x.x.x.x.x.x.x.x.x.x.x.x.x.x.x.x.x.x.x.x.x.x.x.x.x.xxx.xx
```

Paste them as they are: 64 characters each.

Velocity is the feel. For the kick, use a 16-value accent list and repeat it, then give the fill hits their own values:

```
[1.0,0,0,0,0,0,0.85,0,0,0,0.9,0,0,0,0,0]
```

Snare: backbeat `0.95`, ghosts `0.3`. Hats: on-beat `0.55–0.7`, off-beat `0.3–0.45`, the 16th run `0.25–0.4`. The fill snare hits in bar 4 sit around `0.45–0.6`, rising into the downbeat.

If the user asks for eight bars, make bars 1–4 the phrase above and bars 5–8 the same with one new element (an open hat on the "and" of 3, a rim answer, a busier bass) and a bigger fill in bar 8.

## Tracks

Kick `factory:kick_boom`, snare `factory:snare_crack`, hat `factory:hat_closed`, optional open hat `factory:hat_open` and rim `factory:rim`. Use the shared Rookery mix targets for add gains and pans; give both hat roles `choke_group="hats"`.

New projects use calibrated trims. After adding or removing a layer, run one `rookery_apply(ops=[{"op":"balance"}])`; then make taste gain edits on top.

Master: a compressor, then a limiter with `ceiling_db` -1. The renderer normalises to −14 LUFS, so do not chase loudness with gain.

## Bass

Choose the project key before writing the bass line. In D minor, use D as the root on bar 1 and follow the bed's chord changes. In boom bap, duck an 808 0.3–0.5 under the kick.

```
notes = [
  {step: 0, len: 6, pitch: "D2"}, {step: 6, len: 2, pitch: "A1"},
  {step: 10, len: 2, pitch: "D2"}, {step: 14, len: 2, pitch: "F2"},
  {step: 16, len: 4, pitch: "D2"}, {step: 22, len: 2, pitch: "A1"},
  {step: 26, len: 2, pitch: "D2"}, {step: 30, len: 2, pitch: "C2"},
  {step: 32, len: 6, pitch: "D2"}, {step: 40, len: 2, pitch: "F2"},
  {step: 42, len: 2, pitch: "D2"}, {step: 46, len: 2, pitch: "E2"},
  {step: 48, len: 4, pitch: "D2"}, {step: 54, len: 2, pitch: "A1"},
  {step: 58, len: 2, pitch: "D2"}, {step: 60, len: 1, pitch: "C2"},
  {step: 62, len: 2, pitch: "D2"}
]
```

Set them with `rookery_track(action="set", id="808", notes=notes)`. Drop an octave (`D1`, `A0`…) if the user wants more sub. Keep its level within the shared role target.

## Sample pairing

Use a dusty rhodes or soul-guitar chord bed with a higher flute, horn, or vocal-chop lead. Add at most one counter, from a different family and register than both. Search bed/lead/counter together with `queries`, fetch the chosen IDs together, then apply the groove, D-rooted bass notes, sample tracks with `bed`/`lead`/`counter` roles, `balance`, and arrangement in one `rookery_apply`. Read the fetched rhythm strings: keep the bed steady and put the lead's busy steps in its gaps. If both are busy together, gate on alternate bars or slice the lead into one-shot hits. The main `rookery` skill has the full placeholder call and arrangement.

## Moves

Dustier: swing 0.62, hat `gain_db` −10, kick `pitch` −1, a master lowpass around 7000 Hz, and lower the open hat. Keep the ghost snares.

Harder: snare `gain_db` +3 and backbeat velocity `1.0`, swing 0.50, a compressor on the master ahead of the limiter. Do not raise the 808 first; the snare is the attack.

Bouncier: swing 0.66, switch the kick to `x.....x...x.....x.....x...x.x...` (the push), and use the hat 16th run in bar 4.

Sparser: keep the kick and snare, drop the hats to `x...x...x...x...`, and let the lead answer in bar 4.

## After the render

Read `meters`, `mix`, `fit`, and `mix_notes`. If a sample pair crowds the same register and beats, gate one to alternate bars or replace it with a higher/lower, sparser sound. If the lead is buried, raise its track gain by 2–3 dB with `rookery_track(action="set", id="lead", gain_db=...)`. If the low end is muddy, lower the 808. If `seam_click` fails, lower a reverb/delay mix. Render again after one change.
