# The Flock: Rookery's melodic layer (design plan, draft 1)

**Creative lead:** Claude. **Owner of the call:** Ethan. **Status:** draft 1, 2026-11-08. **IN THE HACKATHON CUT** (Ethan, 2026-11-08: "conceptually far more likely to win, we make it happen"). The bird art is the make-or-break piece; Claude owns it. Luna builds the prototype from this. Sol and Grok review the engine and contract parts before anything ships.
**Reference:** [reference-incredibox.md](reference-incredibox.md). We borrow its *mechanics* (characters as voices, combos, templates). We copy **none** of its name, characters, art, sounds or combo recipes.

---

## 1. The idea in one breath

A wire runs across the Rookery page. Birds land on it. **Each bird is a melodic voice**: a bass, a keys player, a lead, a pad, an arp, a singer. Each wears its own costume and has a personality animated in code. Perch a bird and it **starts singing in key, on the grid, over your beat**, so no combination can sound bad. Stack them, swap their songs, mute and solo them. Find secret combinations (**Murmurations**) that unlock bonus parts and moments. Hermes can pick a whole flock for a genre in one sentence, and the birds land one by one: the melodic twin of the live grid build. Then the user takes over.

**Why birds:** a *rookery* is a colony of rooks, and **a group of rooks is called a *parliament***. Corvus (the FX plugin) is the crow genus. The theme is ours, it's original, and it explains the product name.

### Design principles
1. **Nothing sounds bad.** Every note comes from the project's key, scale and chord, on the project's grid. Registers are separated by role. A default auto-mix places every role. Any six birds make music.
2. **The animation tells the truth.** Beaks open on the bird's **actual rendered notes** (note events come back from the render), not on a fake loop. Idle motion is quiet; singing motion is driven by real notes.
3. **One source of truth.** The flock lives in `project.json` like everything else. User clicks and agent tool calls go through one path, and the agent sees what the user did via `rookery_state`.
4. **Deterministic and checked.** Flock audio renders in the same engine, goes into the same hash, and must pass the same six checks.
5. **Native first.** Hermes tokens only. Birds are ink silhouettes in the theme's text color. Each bird's costume is its one accent color. It reskins with every Hermes theme.

---

## 2. The cast

Six **roles**, two birds per role = **12 birds**, plus one secret. Each bird is: a species silhouette + a costume + a persona + a voice + three **songs** (A, B, C).

| # | Bird | Species | Role | Costume (accent) | Persona / idle gesture | Voice (synthesized) |
|---|---|---|---|---|---|---|
| 1 | **Bramble** | rook | bass | flat cap (`--ui-orange`) | Steady, unbothered. Head nods on every beat. | Round sub sine plus a soft-saturated octave; short glide between notes. |
| 2 | **Cinder** | crow | bass | gold chain (`--ui-yellow`) | Swagger. Leans back between notes, chain swings. | 808-style sine with pitch-drop attack, longer decay, glides on slides. |
| 3 | **Quill** | rook | keys | beret + round specs (`--ui-cyan`) | The jazz head. Wing-taps on chord hits, specs glint. | FM electric piano (2-op), soft tine, gentle tremolo. |
| 4 | **Sable** | raven | keys | top hat (`--ui-purple`) | Formal, theatrical. Slow sway, tips hat on bar 1. | Drawbar-style organ (additive, 3 partials), slow rotary wobble. |
| 5 | **Jinx** | jackdaw | lead | spiked feather crest (`--ui-red`) | Show-off. Hops on accents, crest bounces. | Square lead with delayed vibrato and portamento. |
| 6 | **Glint** | magpie | lead | monocle (`--ui-yellow`) | Collector of shiny things. Tilts head at high notes. | Bell/mallet lead (FM, bright attack, fast decay). |
| 7 | **Hush** | raven | pad | nightcap with pom-pom (`--ui-blue`) | Always half asleep. Breathes slowly, eyes half-lidded. | Detuned saw pad, slow attack, low-passed, wide. |
| 8 | **Moss** | rook | pad | knitted scarf (`--ui-green`) | Cozy. Scarf sways, settles feathers. | Warm triangle choir pad with slow filter swell. |
| 9 | **Tick** | chough | arp | pilot goggles (`--ui-orange`) | Nervous energy. Twitchy head moves on every 16th. | Plucky saw arp, short decay, 16th/8th patterns over chord tones. |
| 10 | **Pip** | jackdaw | arp | propeller beanie (`--ui-cyan`) | Playful. The propeller spins when singing. | Square pluck arp, octave-jumping patterns. |
| 11 | **Echo** | crow | call | long scarf (`--ui-purple`) | The singer. Throws its head back on phrase starts. | Formant "ah/oo" vocal synth (two band-passes on a buzz source). Short hooks. |
| 12 | **Wren-Not** | rook | call | flower behind ear (`--ui-red`) | Insists it isn't a wren. Answers other birds. | Whistle synth (sine + breath noise), call-and-response phrases. |
| 13 | **Corvus** *(secret)* | crow | crown | tiny crown (`--ui-accent`) | The king. Appears only after the Murmuration egg (§5). | Not a voice: it puts **Corvus FX** (or the built-in drive if Corvus isn't installed) on the flock bus. |

**Songs.** Every bird has **A** (the default, simple, safe), **B** (busier, the one that makes heads turn) and **C** (sparse or rhythmic, leaves room). Tapping a bird cycles A → B → C. Hidden **D** variants exist only through combos (§5).

**Registers by role** (MIDI, enforced): bass 28–48, keys 48–72, pad 48–76, lead 72–91, arp 60–88, call 60–79.

---

## 3. The musical system (why nothing sounds bad)

### 3.1 Global harmony (one per project)
```json
"flock": {
  "key": "D", "scale": "dorian",
  "progression": ["i", "IV", "VII", "III"],
  "weather": "dust",
  "perches": [ {"bird": "bramble", "song": "A", "mute": false, "solo": false}, null, null, null, null, null ],
  "seen": ["bramble"],
  "unlocked": []
}
```
- **key:** C … B (12). **scale:** `minor`, `dorian`, `major`, `mixolydian`, `minor_pent`, `phrygian`.
- **progression:** 1–8 Roman-numeral chords, one per bar, repeating over the project's bars. Triads by default; keys and pads add 7ths automatically in `dorian`/`minor`/`major` (the "lo-fi" sound for free).
- **weather:** global texture, not a bird: `clear` (none), `dust` (vinyl crackle), `rain` (filtered noise drops), `wind` (slow noise swell). Deterministic noise. This is our own twist: the sky over the wire.

### 3.2 Patterns are chord-relative
Every song is a list of events `{step, len, deg, oct, vel}`, where `deg` is a **chord-tone or scale-degree index relative to the current bar's chord**, not an absolute note. The renderer resolves each event as follows:

`note = key_root + scale[ (chord_root_degree + deg) mod 7 ] + 12 × (oct + octave_wrap)`

It then folds the note into the role's register. Chord tones (deg 0, 2, 4) are preferred on strong steps (0, 4, 8, 12). Passing tones are only allowed on weak steps. So any song works over any progression.

### 3.3 Auto-mix (every combo is balanced)
| Role | Gain | Pan | Notes |
|---|---|---|---|
| bass | −4 dB | 0 | mono below 120 Hz; **ducks 3 dB on kick hits** (the pump) |
| keys | −9 dB | −0.25 | |
| pad | −13 dB | ±0.6 (stereo spread) | high-passed at 180 Hz |
| lead | −8 dB | +0.15 | |
| arp | −11 dB | +0.35 | |
| call | −8 dB | −0.1 | |
| weather | −24 dB | stereo | |

Two birds of the same role on the wire: the second one gets −2 dB and mirrored pan. The flock bus goes through the master chain, so it gets the same limiter and the same checks.

### 3.4 Timing
- The flock follows the project's `bpm`, `bars`, `steps_per_bar`, `swing` and seeded humanize. Swing applies exactly as it does for the drums.
- **Changes land on the downbeat.** Perching a bird triggers a render. The page keeps playing the current loop and crossfades to the new render **at the next bar line** (or the next loop boundary if the render is late). That's slower than the reference app's instant response, but it's honest: what you hear is exactly the checked, hashed render. Renders take about 1 s; a 4-bar loop at 90 BPM is 10.7 s, so changes nearly always land on the next bar.

---

## 4. The page (where it lives, how it feels)

### 4.0 Chat inside Rookery (hard requirement, Ethan 2026-11-08)
The user never leaves Rookery to talk to Hermes. **Default:** a chat built into the Rookery page: a prompt bar under the transport plus a compact, collapsible transcript, talking to Hermes over the gateway. **Option:** "Dock beside chat" puts Rookery next to Hermes's real chat. The Flock's motion is at its best when you type "give me a flock" on the same screen where the birds land. The page must also look right at **pane widths of about 720–900 px** for the docked option: the roster wraps to two rows, the header collapses into a compact row, and the six perches stay on one wire.

### 4.1 Placement
Transport → Waveform → **The Wire** → Channel rack (drums) → Master. The Wire is the hero visual of the melodic layer. It collapses to a 40 px strip (tiny bird heads only) with a chevron. The collapsed state is remembered via `ctx.storage`.

### 4.2 The Wire
- A single hairline (`--ui-stroke-secondary`) with a gentle **catenary sag** (SVG path) between two posts at the page edges. **Six perches**, evenly spaced, each shown as a faint tick when empty.
- On kick hits during playback, the wire **vibrates** by 1–2 px (a damped sine). That's the drums and the flock sharing one world. Driven by the render's kick onsets, not a timer.
- Above the wire: the **sky band** (60 px), where weather draws (tokenized dots and streaks) and where Murmuration bonuses play.
- Below the wire: the **roster** (§4.4).

### 4.3 Bird anatomy (SVG, ~84 px tall on the wire, 40 px in the roster)
- One shared rig: body (ellipse-ish path), tail, wing (a separate group, so it can flap), head group (beak upper/lower as two paths so the beak can open), eye (circle + highlight), legs gripping the wire. Species are parameter tweaks: rook (bare grey beak patch, rounder head), crow (heavier beak), raven (bigger, shaggy throat), jackdaw (small, pale nape, pale eye), magpie (white belly/wing patch), chough (curved beak, tinted in the costume accent).
- **Fill:** `color-mix(in srgb, var(--ui-text-primary) 88%, transparent)` for the body. Beak and legs slightly lighter. The eye uses the editor background with an accent glint. **The costume is the only colored element** (the bird's accent token). Ink silhouettes plus one bright costume reads well and stays clear of the reference app's look.
- **Costume layer** attaches to the head group, so it moves with the head (and stays on through flight).

### 4.4 Motion (all code: CSS keyframes + one rAF loop for note sync)
| Moment | Motion | Duration / timing |
|---|---|---|
| Idle | breathing (`scaleY` 1 → 1.025), blink every 3–7 s (seeded per bird), persona gesture (see the cast table) | continuous, low amplitude |
| Singing | **beak opens on each rendered note** (amplitude ∝ velocity), head bob on beat, role gesture intensifies | driven by render note events + audio clock |
| Muted | eyes closed, beak shut, 40% opacity costume | instant |
| Solo | the other birds dim to 35%; the soloed bird gets an accent ground-shadow under its feet | 120 ms |
| Perch (land) | swoop in from the top-right along an arc, wings open → fold, wire dips at that perch and springs back | 420 ms flight + 300 ms spring |
| Unperch | hop up, flap, exit top-left | 360 ms |
| Song change | quick feather ruffle + a small A/B/C badge pops above the head | 220 ms |
| **Agent picks a flock** | birds land **one by one, 250 ms apart**, in role order bass → keys → pad → lead → arp → call | the melodic money shot |
| Murmuration unlocked | a swarm of 40 tiny bird glyphs swirls through the sky band into a shape (the combo's emblem), the banner shows the combo name, then the bonus joins at the next downbeat | 2.6 s |

`prefers-reduced-motion`: flights become 150 ms cross-fades, no swarm (a static emblem fades in), no wire vibration, beaks still move (that's information, not decoration).

### 4.5 The roster (choosing birds)
- A row of 12 compact **bird cards** under the wire: head-and-costume portrait (40 px), name, role chip. Grouped by role with a hairline between groups. Cards for perched birds show a small "on the wire" dot.
- **Click a card** → the bird flies to the first free perch (or swaps with the same-role bird if the wire is full). **Drag a card onto a perch** → lands there. **Drag a bird on the wire** to reorder (left-to-right order doesn't change sound, only pan mirror, so reordering is purely for taste).
- **Secret slot:** a 13th card shows as a dashed outline with "?" until Corvus is unlocked.
- **Seen state:** birds never perched show a subtle "new" dot (it feeds the Murmuration egg).

### 4.6 Controls per bird (on the wire)
- **Click** = cycle song A → B → C. **M / S** mini-buttons appear on hover/focus under the feet (same visual language as the drum rack). **Right-click or long-press** = a small popover: bio line, song picker, volume trim ±6 dB, "Send home" (unperch).
- **Keyboard:** the wire is a toolbar. ←/→ move between perches, Enter cycles the song, M mutes, S solos, Delete unperches, 1–6 jumps to a perch.

### 4.7 Flock header (left of the wire, small)
Key ▾ · Scale ▾ · Progression (4 chips, click to cycle a chord, or pick a preset) · Weather ▾ · Template ▾ · a **Murmuration meter** (§5.2).

### 4.8 States
- **Empty wire:** the posts and wire draw in. Copy: *"An empty wire. Ask Hermes for a flock, or pick a bird below."* Plus three template chips that put a prompt in the composer via `host.composer.setDraft` (same pattern as the empty page).
- **Rendering:** the birds keep singing the previous render. A tiny "tuning up" shimmer runs along the wire.
- **Render failed:** the birds go quiet with closed beaks, and a red banner shows the reason (from the existing banner).
- **Engine off:** the wire is grey, birds sit with eyes closed, and the copy points at the engine (reuse Offline).

### 4.9 Chat card
The `rookery_render` card adds a **mini wire**: up to six 16 px bird heads with costumes over the mini grid. They bob while the card plays.

---

## 5. Murmurations (combos) and easter eggs. Original designs.

### 5.1 Combos (unlock a bonus that stays until the combo breaks)
| Name | Recipe | What happens |
|---|---|---|
| **Parliament** | one bird of **every** role on the wire (6 birds) | All birds do a synchronized wing-lift on bar 1. Bonus: a soft **harmony chorus** (call voice doubling the lead a 3rd below). Banner: *Parliament is in session.* |
| **Night Shift** | Hush + Sable + Echo, scale in a minor family | The sky band dims to a deep tone, a moon rises, stars twinkle on the hats. Echo unlocks **song D** (a long, slow hook). |
| **Shiny Things** | Glint + Cinder + Jinx | Coins glint across the sky. Glint's lead jumps up an octave with bell sparkle (**Glint D**). |
| **Back and Forth** | Echo + Wren-Not | They trade phrases: Echo on bars 1/3, Wren-Not on 2/4, with little note bubbles. |
| **Two Basses Walk Into a Bar** | Bramble + Cinder | They bicker (alternate bars) and a **sub-octave drop** lands on the last bar of the loop. |
| **Lo-Fi Window** | Quill + Moss + weather `rain` | Rain streaks the sky band. Quill switches to a lazy **Quill D** voicing with extra 9ths. |

Each combo is data: `{id, name, requires: {birds?, roles?, scale_family?, weather?}, bonus: {song_overrides?, extra_layer?, visual}}`. Bonuses render in the engine (so they're hashed and checked). Visuals are page-only.

### 5.2 The hint system: the Murmuration meter
Small dots under the flock header, one per undiscovered combo. When the wire is **one change away** from a combo, its dot pulses and its hover text gives a riddle, never the recipe:
- Night Shift: *"A sleeper, a showman and a singer walk into the dark…"*
- Shiny Things: *"Some birds can't resist anything that sparkles."*
- Two Basses: *"Two low voices, one bar. What could go wrong?"*

Discovered combos are listed in a popover with the date found. The `unlocked` list is stored in the project and survives reloads.

### 5.3 Easter eggs (small, delightful, cheap)
1. **Murmuration** (the big one): perch all 12 birds at least once in one project (`seen` has all 12) → the secret **Corvus** bird lands on a 7th perch that appears at the end of the wire, crown and all. Its "voice" puts Corvus FX (or the built-in drive) on the flock bus.
2. **Wire tap:** click the bare wire 4 times in time with the beat → it twangs a bass note in key, and the closest bird turns to look.
3. **Night owl:** after 23:00 local time, sleeping birds (muted) wear tiny nightcaps.
4. **"parliament"**: name a project `parliament` → every bird wears a tiny judge's wig for that project.
5. **Bird facts:** hold the pointer on a bird for 3 s → a bubble with its one-line bio and a real corvid fact (e.g. *"Rooks have been seen using tools."*).

---

## 6. Templates (what the agent pre-selects)
| Template | Key / scale | Progression | Birds (song) | Weather |
|---|---|---|---|---|
| **Dusty Boom Bap** | D dorian | i - IV – VII – III | Bramble A, Quill B, Hush A, Echo C | dust |
| **Trap Night** | F# minor | i – VI – III – VII | Cinder B, Tick B, Glint A, Hush C | rain |
| **Lo-Fi Study** | B♭ major | I – vi – ii – V | Bramble C, Quill A, Moss A, Wren-Not B | rain |
| **Late House** | A minor | i – VII – VI – VII | Cinder A, Sable B, Pip A, Jinx C | clear |
| **Sunday Soul** | E♭ major | IV – iii – ii – I | Bramble B, Sable A, Moss B, Echo A, Glint C | dust |

The genre skills (`rookery-boom-bap`, `rookery-trap`) gain one line each: *apply the matching flock template, then make one tasteful change.*

---

## 7. Agent surface (proposal for Sol; contract v0.3)

### 7.1 One new tool (the 9th)
`rookery_flock(action, …)`:
- `template` (name) · `perch` (bird, slot?, song?) · `unperch` (bird | slot) · `song` (bird, song) · `mute` / `solo` (bird, on) · `harmony` (key?, scale?, progression?) · `weather` (weather)
- It goes through the same validate → snapshot → save → broadcast path, and emits `project.updated` with a `flock` diff: `{field: 'flock', change: 'perch'|'unperch'|'song'|…, bird, slot, from, to}`. The page animates exactly that.
- **Why a 9th tool instead of folding into `rookery_track`:** birds aren't tracks (no step strings), and one clear verb set is easier for the model. The original plan said "keep it to 8", so **this needs Ethan's OK**. The fallback is `rookery_track(action='flock', …)` with the same arguments.

### 7.2 `rookery_state` text view gains a wire line
```
Wire (D dorian, i-IV-VII-III, dust): [1 Bramble A] [2 Quill B] [3 Hush A] [4 —] [5 Echo C·muted] [6 —]
Murmurations: Night Shift (found), 4 undiscovered. Hint: "Some birds can't resist anything that sparkles."
```
So the agent can see user changes and can *hunt for combos* when asked ("find me a secret combo"), which is a great demo beat.

### 7.3 Render additions
- `RenderView.flock_events`: `{bird_id: [{t: seconds, len: seconds, midi, vel}]}` for beak sync, plus `kick_onsets: [seconds]` for wire vibration. Both are computed by the renderer, so the animation is the truth.
- `RenderView.flock_unlocked`: combos active in this render (the page plays the swarm when one appears that wasn't there before).

### 7.4 Engine (Sol's lane, Python parity)
- `rookery/flock/birds.json`: **the single data file** for birds, songs, templates and combos. The Python renderer and the page both read it (the page gets it once via `GET /flock/catalog`). No duplicated tables.
- `rookery/flock/synth.py`: the six voices + weather, numpy, seeded. Same rules as the factory kit.
- Validation: `perches` length 6 (7 with Corvus), known birds, at most 2 per role, songs in A–C (D only when its combo is active), key/scale/progression whitelist.

---

## 8. Prototype scope for Luna (today)

Build a standalone, runnable prototype **with no Hermes and no Python**, in `dev/flock/`, served by the existing preview server at `http://127.0.0.1:5178/dev/flock/`:
- **Data** (`birds.js`): all 12 birds + Corvus, 3 songs each, the 5 templates, the 6 combos, exactly as this doc says. This is the draft of `birds.json`.
- **Synth** (`flock-synth.js`): pure-JS, deterministic, node-testable. It renders the flock loop to Float32 buffers with the §3 rules, plus note events and kick onsets. A drum bed comes from `dev/preview/mock-audio.js` (`synthLoop`) with a default boom bap project.
- **UI** (`flock-ui.js`): written **in the same style as `desktop/plugin.js`** (`createElement as h`, one scoped CSS string with `.fk-*` classes, Hermes tokens only, no JSX), exporting a `FlockPanel` component, so Claude can lift it into the plugin. Everything from §4: the wire, the 12 SVG birds with costumes and motion, roster, controls, header, Murmuration meter, combos with swarm, at least the eggs 1, 2 and 5, templates, and an **"Agent picks: Dusty Boom Bap"** button that lands birds one by one.
- **Audio:** Web Audio playback of the rendered loop, crossfading to the new render at the next bar line (§3.4).
- **Tests** (`check-flock.mjs`): see the acceptance list in the brief.

**Out of scope today:** Python engine, the real tool, contract changes, `desktop/plugin.js` integration, the chat card. Those follow Ethan's go-ahead.

---

## 9. Schedule and risk

- **Sun (today):** Luna builds the prototype (synth, wire, interactions; her bird drawings are placeholders). **Claude builds the bird art and motion rig** (`dev/flock-art/`), then swaps it into the prototype. **Sol starts the engine** against contract v0.3 (`birds.json`, Python flock synth, `rookery_flock`, render events). Ethan gets a taste call on the birds tonight.
- **Mon:** Sol's flock engine green on `sol/flock`, Grok audits it, merged to main. Claude lifts `FlockPanel` (with the final art) into `plugin.js`. Live test in Hermes Mon evening.
- **Tue:** polish, the demo shot ("Hermes, give me a flock for this" → birds land → "find a secret combo" → Parliament), the video.
- **Kill order (revised):** the Flock is **protected**, not cut first. Inside the Flock, cut from the top if late: (1) eggs 2–5, (2) weather, (3) the drag-to-reorder, (4) the 2nd bird per role (ship 6 birds), (5) combos beyond Parliament + Night Shift. **Never cut inside the Flock:** birds landing live from an agent template, beak-on-real-notes, in-key guarantee, determinism.

## 10. Decisions
1. **9th tool `rookery_flock`:** proceeding with it (Claude's call under Ethan's "make it happen"; the fold-into-`rookery_track` fallback stays one rename away if Ethan objects).
2. Names and personas: unchanged unless Ethan swaps any at the art taste call.
3. **In the hackathon cut.** Decided by Ethan, 2026-11-08.
