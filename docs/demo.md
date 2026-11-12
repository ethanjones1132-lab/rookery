# Rookery — the 90-second demo

Owner: Ethan. This is the shot list for the hackathon video. It is cut around the two things no rival has: **the live build** and **the agent measuring its own mix**. The agent has no Flock tool; the Flock is the user's instrument on the page, so it appears as your hands on the wire, never as an agent prompt.

## Before recording (15 minutes)

- Hermes Desktop is running, Rookery is enabled, the gateway is up, and the chat model answers a one-word prompt.
- A clean project list (or one "demo" project), no notifications, no other windows on screen.
- Audio output is on and audible in the recording. Test one render end to end.
- Record at 1920×1080, 60 fps if possible. Show the real model name in a corner.
- Have a second terminal ready for the Telegram/CLI shot (only if it works; otherwise skip it).
- Run the same prompt once or twice before recording so the model's first move is predictable. Do not fake a sped-up section without marking it.

## The shots

| Time | Shot | What the viewer sees | Voiceover |
|---|---|---|---|
| 0–8 | Title card | **Rookery — tell Hermes the beat. Watch it build.** | "I make beats and I build VSTs. I wanted an agent that works like a producer, not a prompt box." |
| 8–22 | Desktop, Rookery open, chat rail on the right | Type: *"Make a dusty boom bap at 90 in A minor, eight bars."* The agent loads the skill, creates the project, and the grid fills **step by step**: kick, snare, hats, bass. The "Hermes is editing" pill pulses. | "One sentence, with a key. The agent writes the project file. I watch every step land." |
| 22–32 | Samples | *"Find a rhodes bed, a flute lead and a guitar counter on Soundza."* One search batch returns three groups; one fetch brings all three in with their credits. The rows appear with role labels. | "It searches free, lossless loops in one batch, then fetches the three it wants into my kit. The credit is recorded." |
| 32–44 | Arrangement and render | The agent writes drums, bass, the three sample parts, `balance` and a seven-section arrangement in one batch. Render the song: the waveform draws, the playhead runs, the six LEDs go green, both hashes appear. **Beat plays.** | "Eight bars become a two-and-a-half-minute song: intro, verse, hook, breakdown, final hook. It renders locally and checks length, clipping, loudness, the seam and the bytes." |
| 44–54 | Mix fix | *"The lead is buried. Fix it."* The agent reads `balance`, pair `fit` and `mix_notes`, raises the lead and gates a crowded pair onto alternate bars, then re-renders. The lead comes forward. | "It can't hear, so the render gives it meters: role balance, pairwise fit, masking notes, width and band energy. It fixes the mix with numbers." |
| 54–64 | Two hands | Ethan clicks three hat pads. *"What changed?"* The agent calls `rookery_state(since=…)` and reads back your three steps, marked user. | "I edit the same file. It sees my clicks. One project, two hands." |
| 64–72 | The Flock (your hands only) | Open the Flock section, pick a template or seat two birds, press play. Beaks move on the rendered notes. No agent prompt. | "The Flock is my instrument: twelve birds on a wire, in key, on the grid. The agent stays out of it — that part is mine." |
| 72–82 | Export and proof | *"Export it for a video at 30 fps."* The folder opens: WAV, stems, MIDI, `cues.json`, `LICENSE.txt`. Cut to a second render of the same project: the hash is identical. | "WAV, stems, MIDI and frame cues for the editor. Same project, same bytes. No cloud, no credits, no account. Your machine." |
| 82–90 | End card | Repo URL, `hermes plugins install ethanjones1132-lab/rookery`, "No cloud. No credits. Your machine." | — |

## The determinism proof (important)

There are two hashes on screen:

- **Render hash** (`#…`) is the SHA-256 of the **canonical audio projection plus the renderer version**. The projection leaves out the project name and other metadata that cannot change the audio.
- **Audio hash** (`audio #…`) is the SHA-256 of the **WAV bytes** themselves.

The honest claim, true by test:

- **Render the same project twice** (no edits) → identical render hash **and** identical audio hash.
- **Same prompt, new project** → the **audio hash matches** when the content is the same, and so does the render hash. Say "same beat, same audio" and point at `audio #…`; it is the strongest proof because it hashes the thing you can hear.

The suite proves different names with identical content produce the same `wav_hash`
(`tests/engine/test_render.py::test_wav_hash_ignores_the_project_name`). Render the same project in a fresh process in the tests and compare the WAV SHA-256 if you prefer to show that line on screen.

## If the sample search fails on camera

Soundza search works without a key; fetch needs a free `SOUNDZA_API_KEY` in Hermes's env. If the key is missing or the service is slow, do not fake it:

1. Switch the prompt to `source="openverse"` and use its CC0 previews, or
2. cut the sample scene (22–32) and keep the drum/bass song, arrangement and mix fix.

The rest of the video stands: live build, checked song, measured mix, two hands, export, hash proof.

## The prompts to have ready

- *"Make a dusty boom bap at 90 in A minor, eight bars."*
- *"Find a rhodes bed, a flute lead and a guitar counter on Soundza."*
- *"The lead is buried. Fix it."*
- *"I clicked three hat steps. What changed?"*
- *"Export it for a video at 30 fps."*

Optional, your hands only: open the Flock and seat a template.

## What to put on screen

- The real model name in a corner.
- The hash and the six check LEDs (they are the reliability story).
- The mix numbers when the agent fixes the lead (`balance`, `fit`, `mix_notes`).
- The exact command if you show the CLI/Telegram path.
- Mark any sped-up section.

## After recording

- Put the video URL at the top of `README.md` and in `plugin-catalog-draft/PR_BODY.md`.
- Add a GIF of the live build (8–12 s, looped) to the README.
- Add 3–4 screenshots: the grid, the Flock, the mixer/mix, the chat card.
- Pin the catalog entry to the recorded commit and paste `hermes plugins validate . --install-deps`.
