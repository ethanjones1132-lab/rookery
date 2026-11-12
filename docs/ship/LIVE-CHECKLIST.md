# Live checklist — 10 minutes in real Desktop before recording

Do this **before** you open the screen recorder. It is a click-through, not a
test suite. If a step fails, stop and write down the step number and the
on-screen message; do not restart the gateway mid-check.

## 0. Pre-flight (2 min)

- [ ] Hermes Desktop is open and signed in. Rookery is enabled in
      Capabilities → Plugins.
- [ ] The gateway is up. Check without restarting it:
      `hermes gateway status`
- [ ] The chat model answers. Send `say ready` in a new chat; expect a one-word
      reply, not a 400/model error.
- [ ] Open **Rookery** from the sidebar. The page loads with an empty rack or the
      last project, no red error panel.
- [ ] Audio output is on and the system volume is up. The recording captures it.
- [ ] `docs/validation-2026-11-10.md` is open in another window for the hashes
      if you want to compare.

## 1. Live build (2 min)

Prompt: **"Boom bap at 90, dusty, 4 bars."**

- [ ] The "Hermes is editing" pill pulses.
- [ ] Pads light in step order; kick, snare and hats land as separate edits.
- [ ] The project name appears in the transport.
- [ ] No red toast.

Expected: kick `kick_punch`, snare `snap`, hat `tight` (the measured default
voices), 90 BPM, 4 bars.

## 2. Render and the six checks (1 min)

- [ ] Click **Render** (or let the agent render).
- [ ] The waveform draws and the playhead loops.
- [ ] The six LEDs are green. Hover: `6/6`.
- [ ] The transport shows **two** hashes: `#……` and `audio #……`. Hover the audio
      hash; the title is the SHA-256 of the WAV bytes.
- [ ] Press Play. Audio is audible and loops without a click.

If a check is red, read its value and hint in the popover; do not record past it.

## 3. The Flock — your hands only (1 min)

There is no agent Flock tool. Open the Flock section and seat a template yourself,
or perch two birds.

- [ ] Birds land one by one on the wire.
- [ ] The hook enters; the call answers in the back half.
- [ ] Beaks move on the rendered notes.
- [ ] Re-render: still 6/6.
- [ ] Asking the agent to "give me a flock" does not change the project; it
      should say the Flock is yours to edit in the page.

## 4. Mix raise (1 min)

Prompt: **"The lead is buried. Fix it."**

- [ ] Render a loop and show the agent the `balance`, `fit` and `mix_notes`
      fields; it names the miss and the fix.
- [ ] The agent raises the lead (or runs one `balance` op) and re-renders.
- [ ] Re-render: the lead is louder, still 6/6.
- [ ] The agent does not claim it turned a Flock knob: it has no Flock tool.

## 5. Two hands (1 min)

- [ ] Click three hat pads yourself. They light and the project says Saving… then
      Saved.
- [ ] Ask **"What changed?"** The agent reads back your three steps.
- [ ] The agent's next edit still lands without a 409.

## 6. Determinism proof (1 min)

- [ ] Render the same project a second time with no edits. The `#` hash and the
      `audio #` hash are identical.
- [ ] If you show a new project: same prompt, same content, new name → the
      **audio hash** matches. Point at `audio #…`, not just `#`.

## 7. Export (1 min)

Prompt: **"Export this for a video."** (or `rookery_export`)

- [ ] The agent returns an export folder.
- [ ] The folder contains `<name>.wav`, `stems/` (one per track, plus `flock.wav`
      only when the project has perched birds), `<name>.mid`, `cues.json`,
      `LICENSE.txt` and `README.txt`.
- [ ] `cues.json` has beats, bars, kicks, snares and (if requested) frame numbers.
- [ ] If the project has an arrangement, `song` defaults to true; export the
      whole song, not one loop.

## 8. A Soundza loop and its credit (1 min)

- [ ] Set a free `SOUNDZA_API_KEY` in Hermes's env (get one at
      https://soundza.com/developers/keys) and reload Rookery. Do not paste the
      key into chat.
- [ ] Prompt: **"Find a 90 BPM loop on Soundza and add it in loop mode."**
- [ ] The sample track row shows the sound's title and creator and a small
      "Powered by soundza" link; clicking it opens soundza.com in the system
      browser.
- [ ] Export and open `LICENSE.txt`: it names the sound under the Soundza
      Standard License and says not to share it as a standalone file.

## 9. Corvus (1 min, optional if recording that scene)

Prompt: **"Put Corvus on the master, warm."**

- [ ] Corvus loads and its knobs appear.
- [ ] Turning Drive changes the sound after re-render.
- [ ] If Corvus is not installed, the card reads "Get Corvus FX" and the link
      opens the repository. Note what the release page actually shows (the
      current only release is titled "Aphelion Fx v0.1.0").

## Record

- [ ] Close notifications, other windows and the preview server.
- [ ] 1920×1080, 60 fps if possible, real model name in a corner.
- [ ] Follow `docs/demo.md` shot by shot.
- [ ] Put the video/GIF URL at the top of `README.md` and in `PR_BODY.md`.

If anything fails once, try the same prompt again before changing the project.
The model's first move is the thing you are recording; a retry is cheaper than a
new setup.
