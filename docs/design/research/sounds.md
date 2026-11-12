# The Flock: sound design research and Serum 1 recipes

**Status:** research draft 1, 2026-11-08. **Scope:** 12 birds plus the secret Corvus, built in Xfer Serum 1 (v1.368) from its init patch and rendered offline through `pedalboard` into one-shot multisamples.
**Read first:** [flock.md](../flock.md) (roles, personas, registers), `rookery/flock/birds.json` (data), `.crew/briefs/claude/G2-serum-voices.md` (how Serum is linked and never bundled).

## 0. What is verified and what is not (read this before trusting any number)

Three kinds of claim appear in this file. Each is labelled.

| Tag | Meaning |
|---|---|
| **[VERIFIED-LOCAL]** | I loaded `Serum.vst3` v1.368 through `pedalboard` on this machine and read or measured it. |
| **[SOURCED]** | Taken from a cited page. The numbers are the page's, or I say they are mine. |
| **[STARTING POINT]** | My synthesis of the sources into a number. **Nothing in section 2 has been auditioned.** Every timbre value is a research-derived starting point to be tuned by ear (and by the checks in section 3.6), not a finished patch. |

What I could not find, plainly:
- **No artist or producer interview with synth settings.** Searches for Metro Boomin / Baauer / Lil Nas X style bell, flute and lead breakdowns returned nothing usable. "2020s hit" claims here rest on production tutorials and synthesis references, not on first-hand producer statements. Do not quote this file as "how producer X made it".
- **No readable official Serum 1 manual.** `xferrecords.com/manual/serum` returned 404; the Scribd copy would not render. Only the Serum 2 web manual is indexed. Serum 1 behaviours below come from the plugin itself (section 1) plus third-party pages, and I mark which.
- **Nothing was listened to.** I measured parameter names, value text, determinism and a few signal properties. I did not judge any of these patches by ear.

## 1. Serum 1 through VST3 and pedalboard: what the script can and cannot set

### 1.1 Parameter naming (the question you asked)

Your guess ("A WTPos", "Fil Cutoff", "Env1 Atk") is **not** what this build exposes. **[VERIFIED-LOCAL]** `pedalboard.load_plugin(...Serum.vst3...)` reports `2397` parameters and `is_instrument=True`. Names are **lowercase snake_case identifiers with a unit suffix**, e.g. `a_wtpos`, `fil_cutoff_hz`, `env1_atk_ms`, `env1_dec_s`, `env1_sus_db`, `env1_rel_ms`. Suffixes: `_ms`, `_s`, `_hz`, `_db`, `_cents`, `_semitones`, `_oct`, `_deg`.

Only 317 of the 2397 are Serum's own controls (the 32 matrix slots, macros, oscillators, filter, envelopes, LFOs, voicing, 10 effects). The other 2080 are generic host-exposed slots that do nothing unless mapped inside Serum:
- 2048 = `cc0_chan_1` ... `cc127_chan_16` (128 CCs x 16 channels);
- 16 `pitch_bend_chan_N`, 16 `aftertouch_chan_N`;
- Note for the real set: the 32 matrix slots are `mod_1_amt`, `mod_1_out` ... `mod32_amt`, `mod32_out` (`mod_1`..`mod_9` have an underscore, `mod10`..`mod32` do not). Their raw 0.5 = amount 0; `mod_N_out` defaults to 100.

The real parameter names used in this file (all **[VERIFIED-LOCAL]** unless noted), with the value text they show **in the init patch**:

| Area | Names (init value) |
|---|---|
| Master | `mastervol` (70% / -9.3 dB), `mast_tun`, `bend_u_semitones` (2), `bend_d_semitones` (-2), `pitch_bend`, `mod_wheel`, `macro_1`..`macro_4` (0) |
| Osc A | `osc_a_on` (on), `a_vol` (75%), `a_pan`, `a_octave_oct` (0), `a_semi_semitones`, `a_fine_cents`, `a_unison` (1), `a_unidet` (0.25), `a_uniblend` (75), `a_uni_lr` (100, unison stereo width), `a_uni_warp`, `a_uni_wtpos`, `a_uni_stack` (off), `a_warp` (warp amount knob), `warposca` (warp **type** menu, Off), `a_wtpos`, `a_randphase` (100), `a_phase_deg` (180), `a_coarsepit` |
| Osc B | the same set with `b_` / `osc_b_on` (**off** in init) / `warposcb` |
| Noise | `osc_n_on` (off), `noise_level` (25%), `noise_pitch` (50), `noise_fine`, `noise_pan`, `noise_randphase` (0), `noise_phase` (0) |
| Sub | `osc_s_on` (off), `sub_osc_level` (75), `sub_osc_pan`, `suboscshape` (Sine; options Sine, RoundRect, Triangle, Saw, Square, Pulse), `suboscoctave_oct` (0) |
| Routing flags | `osca_fil` (on), `oscb_fil`, `oscn_fil`, `oscs_fil` (all off): which oscillators feed the filter |
| Filter | `filter_on` (**off** in init), `fil_type` (MG Low 12; 96 types, see 1.4), `fil_cutoff_hz` (425), `fil_reso` (10), `fil_driv` (0), `fil_var` (0), `fil_mix` (100), `fil_stereo` (50) |
| Env 1 (amp) | `env1_atk_ms` (0.5), `env1_hold_ms` (0.0), `env1_dec_s` (1.00), `env1_sus_db` (0.0 dB), `env1_rel_ms` (15), curves `a_curve1`/`d_curve1`/`r_curve1` |
| Env 2 / 3 | `env2_atk_ms`, `env2_hld_ms`, `env2_dec_s`, `env2_sus` (100 %), `env2_rel_ms`, same for `env3_*`; curves `a_curve2`.. |
| LFO 1-8 | only `lfoN_rate` (tempo-sync enum: 32 bar, 16 bar, ... bar, 1/2, 1/4 ... 1/256, fast), `lfoN_smooth`, `lfoN_rise`, `lfoN_delay` |
| Voicing | `porttime_ms` (0), `portcurve` (0). **Mono/legato/poly mode is not a parameter.** |
| FX on/off | `dist_enable`, `flg_enable`, `phs_enable`, `cho_enable`, `dly_enable`, `comp_enable`, `rev_enable`, `eq_enable`, `fx_fil_enable`, `hyp_enable` (all off) |
| Distortion | `dist_mode` (Tube; Tube, SoftClip, HardClip, Diode 1, Diode 2, Lin.Fold, Sin Fold, Zero-Square, Downsample, Asym, Rectify, X-Shaper, X-Shaper (Asym), Sine Shaper, Stomp Box, Tape Sat.), `dist_drv` (25), `dist_wet` (100), `dist_prepost`, `dist_freq_hz`, `dist_bw`, `dist_l_b_h` |
| Chorus | `cho_wet` (50), `cho_rate_hz` (0.08), `cho_dly_ms` (5.0), `cho_dly2_ms`, `cho_dep_ms` (26.0), `cho_feed` (10), `cho_filt_hz` (1000), `cho_bpm_sync` |
| Delay | `dly_wet` (30), `dly_mode` (Normal / Ping-Pong / Tap->Delay), `dly_timl`, `dly_timr`, `dly_feed` (40), `dly_bpm_sync` (**on**) |
| Reverb | `verb_wet` (20), `verbsize` (35), `decay_s` (4.7), `verbloct`, `verbhict` (35), `spin_rate`, `spin_depth` |
| Compressor | `cmp_thr_db` (-18.1), `cmp_rat` (4:1), `cmp_att_ms` (90.1), `cmp_rel_ms` (90.0), `cmpgain_db`, `cmpmbnd` (Normal / MultBand), `comp_wet` |
| EQ | `eq_frql_hz` (210), `eq_frqh_hz` (2041), `eq_q_l`, `eq_q_h`, `eq_voll_db`, `eq_volh_db`, `eq_typl`, `eq_typh` (Shelf / Peak / LPF-or-HPF) |
| FX filter | `fx_fil_type` (96 types), `fx_fil_freq_hz`, `fx_fil_reso`, `fx_fil_drive`, `fx_fil_var`, `fx_fil_wet` |
| Hyper/Dimension | `hyp_wet` (50), `hyp_rate` (40), `hyp_detune` (25), `hyp_unison` (4), `hypdim_size` (50), `hypdim_mix` (0) |

**How to set them (verified).**
- Assign Serum's own display text as a string: `plugin.fil_type = "Scream LP"`, `plugin.fil_cutoff_hz = "800"`, `plugin.env1_atk_ms = "5"`, `plugin.env1_dec_s = "0.3"`, `plugin.a_unison = "7"`, `plugin.dist_mode = "Tape Sat."`. All worked.
- The text must match one of the parameter's displayed steps. `env1_sus_db = "-6"` **raised** `ValueError` (the steps are `-6.0`, `-5.9` ...). Safest helper: parse `valid_values`, pick the nearest numeric entry, assign that string.
- On/off parameters (`osc_a_on`, `filter_on`, `cho_enable`) take Python **booleans**, not "on"/"off" strings.
- Raw 0..1 values also work (`parameters["a_warp"].raw_value = 0.6`) but the mapping is non-linear (cutoff "800" = raw 0.58; attack "5.00" ms = raw 0.69). Prefer text.
- `a_wtpos` shows " 1" at every raw value in the init patch (the display is the frame number of the loaded table). It still moves the audio once a multi-frame table is loaded; the text is not a useful readback.
- Printing parameter names that contain non-ASCII characters crashes a cp1252 console. Use `errors="replace"` when logging.

### 1.2 What is **not** reachable by parameter name (the real constraint)

**[VERIFIED-LOCAL]** by exhaustive enumeration, none of these has a parameter:

1. **Wavetable choice** for Osc A, Osc B and the Noise oscillator.
2. **Modulation-matrix source and destination.** Only the amount (`mod_N_amt`) and output (`mod_N_out`) of each of the 32 slots are exposed. So `ENV2 -> Cutoff`, `LFO1 -> pitch`, `Velocity -> Cutoff` **cannot be wired by script**.
3. **LFO shape, mode (Trig/Env/Off) and BPM-sync vs Hz.** Only rate-as-enum, smooth, rise and delay exist.
4. **Voicing:** Poly vs Mono, Legato, portamento Always/Scaled, max voices.
5. Effect order, and unison "Legato" style options.

Consequence: **a pure "init patch plus parameter writes" approach gives you** Serum's default wavetable plus the **sub oscillator's six basic shapes**, unison, detune, 96 filter types, 10 effects, and the amp envelope. It gives you **no filter envelope, no vibrato, no FM, no velocity brightness**. A saw (init) through a static filter is not enough for bell, EP, pluck or vowel timbres.

**[VERIFIED-LOCAL]** `warposca`/`warposcb` (the warp *type* menus) **are** exposed as 45-entry enumerations (names in 1.4), so FM/sync/bend warp **types** are settable even though the wavetables are not.

**Recommended way through (two tiers).**
- **Tier P (parameters only, scriptable):** everything in a recipe's "P" block. The script owns these values, so the doc is the source of truth.
- **Tier G (one-time GUI work per bird):** table choice, matrix routes, LFO shape/mode, voicing. Do it once with `plugin.show_editor()` (pedalboard opens Serum's own window), save `plugin.raw_state` to a **local, git-ignored** file per bird, and in the render script do `plugin.raw_state = <bytes>` first, then apply the P block over it. **[STARTING POINT: untested]** I did not exercise `raw_state` round-tripping or `show_editor()`.
  - **Licensing note:** a saved state can embed table or noise data. Keep these files out of the repo, like the G2 brief says for audio and presets. Hand-wire matrix routes with all amounts at **0**, then let the script set `mod_N_amt`. That keeps the per-bird differences in versionable parameters.
- **Tier P-fallback:** each recipe ends with what to do if the GUI step is skipped.

**Chassis matrix (build once, same slot map in every bird state; amounts all 0).** The recipes below refer to these slots. Amount scale is the matrix's own (bipolar; `mod_N_amt` raw 0.5 = 0). **[STARTING POINT]** I did not measure how an amount maps to cutoff or pitch range; tune by ear.

| Slot | Param | Route |
|---|---|---|
| R1 | `mod_1_amt` | ENV 2 -> Filter Cutoff |
| R2 | `mod_2_amt` | ENV 2 -> Osc A WT Pos |
| R3 | `mod_3_amt` | ENV 2 -> Osc A Warp (the FM/bend amount) |
| R4 | `mod_4_amt` | ENV 3 -> Osc B Level (organ key click, tine ring) |
| R5 | `mod_5_amt` | ENV 3 -> Osc A + B Coarse Pitch (unipolar, short pitch blip) |
| R6 | `mod_6_amt` | LFO 1 (sine, Trig) -> Osc A + B Fine pitch (vibrato) |
| R7 | `mod_7_amt` | LFO 2 (sine, Trig) -> Filter Cutoff (slow breathing) |
| R8 | `mod_8_amt` | LFO 3 (random/noise shape, smoothed) -> Osc A + B Fine (wow and flutter) |
| R9 | `mod_9_amt` | LFO 4 (sine) -> Osc A Level (tremolo) |
| R10 | `mod10_amt` | Velocity -> Filter Cutoff |
| R11 | `mod11_amt` | Velocity -> Osc A Warp (FM "bark") |
| R12 | `mod12_amt` | Velocity -> Osc A WT Pos |

### 1.3 Things that matter for offline rendering (measured)

- **Determinism. [VERIFIED-LOCAL]** With `a_randphase = "100"` (init default), two renders of the same note differ, with one voice or seven. With `a_randphase = "0"` they were **bit-identical** on the same plugin instance, with one voice and with 7-voice unison. So **set `a_randphase = "0"` (also `b_randphase`; `noise_randphase` is already 0)** on every bird. LFO phase and effect LFOs were not covered by that test; see the FX determinism result in 1.5.
- **Render cost is a fixed overhead per call. [VERIFIED-LOCAL]** A `plugin(...)` call took ~5.5 s wall for 0.4 s of audio, for 1.2 s, and for a **16 s render containing four notes**. So the cost is per call, not per second of audio. **Render all roots of a bird (even all birds that share a patch) in one call**, with each note spaced by its hold plus tail (section 4), and slice the result afterwards. That turns ~76 calls (~7 minutes) into ~13-30 calls (about 1-3 minutes). Cache by hash as G2 plans. (I only tested up to 16 s; a 60-s single call is untested.)
- **Velocity does nothing in the init patch. [VERIFIED-LOCAL]** Note-ons at velocity 127, 64 and 32 rendered with identical RMS. Velocity only matters once you route it in the matrix (R10-R12 and an amplitude route). So **a "velocity layer" is only real if the GUI chassis wires Velocity -> something**; otherwise it is identical audio at a different filename.
- **Static MIDI pitch bend works; a dynamic bend ramp did NOT reproduce. [VERIFIED-LOCAL]** A max pitch-bend message sent just before a note-on raised a C2 sub note from 65.3 Hz to 73.3 Hz (+2 st = the init `bend_u_semitones`), on channels 1 and 2. `bend_u_semitones` / `bend_d_semitones` accept -24..+24 (raw 1.0 = "24"). But my attempt to ramp the bend (24 messages over 60 ms, starting at +max, note-on 0.5 ms after the first message) measured **no pitch drop** (65.9 Hz in the first 25 ms vs 65.3 Hz later). Cause unknown; the likely suspect is Serum applying events inside the first audio block out of order. **So do not rely on a bend ramp for the 808 drop or vocal scoops until it is debugged** (try sending the first bend >=1 block before the note-on, or use R5 = ENV 3 -> pitch in the GUI chassis, the recommended route).
- **Which effects are deterministic across repeat renders. [VERIFIED-LOCAL]** Identical on repeat (bit-exact): **Distortion, Reverb, Compressor, EQ, FX Filter**. **Not** identical: **Chorus, Flanger, Phaser, Hyper/Dimension** (free-running internal LFOs). To meet G2's byte-identical requirement, **do not use Serum's Chorus/Flanger/Phaser/Hyper in baked samples**; do width with unison, and do chorus in the engine. Where a recipe below lists them, they are marked `ND` and left out of the default P block.
- **Init patch facts. [VERIFIED-LOCAL]** Osc A on, "Default" table, harmonic levels of a C3 note fall roughly 1/n (relative to the fundamental: -6.7, -10.3, -12.1, -13.8 dB for partials 2-5), i.e. an **ordinary saw**. Filter off. Env1 sustain 0.0 dB (full), decay 1.0 s. Sub, noise, Osc B all off. All ten effects off.
- **Noise oscillator is sample-based** (Serum's noise osc plays sampled noise; the stock folder is `Noises/Analog`, `Organics`, `SOR`, `Attacks_*`). [SOURCED: splice.com blog, edmprod/Splice summaries]. The recipes avoid it. Synthesized alternatives are given where a bird needs breath (Wren-Not): a 16-voice max-detune unison saw through a band-pass.
- **Note numbers.** `birds.json` registers use C4 = MIDI 60: bass 28-40 (E1-E2), pad 48-60 (C3-C4), keys 52-64 (E3-E4), arp 72-84 (C5-C6), lead 67-79 (G4-G5), call 69-76 (A4-E5). These match your register advice exactly. (flock.md section 2 still lists the older, wider ranges; the JSON is the newer source.) (Serum's GUI keyboard labelling of middle C was not checked; always pass raw MIDI numbers.)

### 1.4 Enumerations worth knowing (all **[VERIFIED-LOCAL]**)

- `fil_type` / `fx_fil_type` (96): MG Low 6/12/18/24, Low 6/12/18/24, High 6-24, Band 12/24, Peak 12/24, Notch 12/24, LH, LB, LP, LN, HB, HP, HN, BP, BN, PP, PN, NN, L/B/H 12/24, L/P/H, L/N/H, B/P/N, Cmb +/-, Cmb L6+ ..., Flg +/-, Phs 12+ ... Phs 48HL6-, FPhs 12HL6+/-, Low EQ 6/12, Band EQ 12, High EQ 6/12, Ring Mod, Ring Modx2, SampHold, SampHold-, Combs, Allpasses, Reverb, French LP, German LP, Add Bass, **Formant-I, Formant-II, Formant-III**, Bandreject, Dist.Comb 1/2 LP/BP, Scream LP, Scream BP.
- `a_unison` / `b_unison`: 1-16. `a_octave_oct`: -4..+4. `a_semi_semitones`: -12..+12. `suboscoctave_oct`: -4..+4 (9 steps).
- `a_uni_stack`: off, 12 (1x), 12 (2x), 12 (3x), 12+7(1x), 12+7(2x), 12+7(3x), Center-12, Center-24.
- `dly_mode`: Normal, Ping-Pong, Tap->Delay. `cmpmbnd`: Normal, MultBand. `eq_typl`/`eq_typh`: three types (Shelf, Peak, and a pass type).
- `hyp_unison`: 0-7. `portcurve`: -100..+100.

### 1.5 Other measurements (all **[VERIFIED-LOCAL]**)

- **Warp-type menus are settable.** `warposca` / `warposcb` list 45 slots, but only the first **23** are real names; the rest are garbage strings from the plugin's table. The real list, in order: `Off, Sync, Sync 1/2 Win., Sync Window, Bend +, Bend -, Bend +/-, PWM, Asym +, Asym -, Asym +/-, Flip, Mirror, Remap 1, Remap 2, Remap 3, Remap 4, Quantize, FM (from B), AM (from B), RM (from B), FM (Noise), FM (Sub)`. So **FM from B, FM from Sub and FM from Noise are all one parameter write**. Assign the text, e.g. `plugin.warposca = "FM (from B)"` (not run end-to-end).
- **`a_warp` (the warp amount knob) does nothing while `warposca` is `Off`** (harmonic profile unchanged at raw 0.6).
- **The "Default" table is a single frame.** `a_wtpos` at raw 0 and raw 1 gave bit-identical audio (with `a_randphase = "0"`). Wavetable-position sweeps only work after a multi-frame table is loaded in the GUI.
- **Sub oscillator shapes (measured spectra).** `Sine`: harmonics below -85 dB (a pure sine). `Square`: odd harmonics only, 3rd at -10.2 dB relative to the fundamental (ideal square: -9.5 dB). The sub is therefore a clean source of sine/square without any wavetable.
- **Formant filters (crude measurement).** Saw at 110 Hz through `Formant-I/II/III`, three strongest smoothed spectral peaks: `Formant-II` **moves with `fil_cutoff_hz`** (e.g. cutoff "59": peaks ~386/1926/2585 Hz; "193": ~496/1815/2475; "2065": ~385/714/1265), `Formant-I` and `Formant-III` gave **constant** peaks (~274/604/934 and ~274/715/1044) at every cutoff, so their vowel is presumably steered by `fil_var` or `fil_reso`, not tested. The peak finder is rough (110 Hz harmonic spacing vs a 120 Hz smoother), so treat these numbers as "Formant-II is the responsive one", not as vowel data. **The Echo recipe therefore needs a small fitting sweep in the render script** (grid over `fil_cutoff_hz` x `fil_var`, pick the cutoffs whose F1/F2 land near "ah" 730/1090 and "oo" 300/870 Hz).

## 2. Per-role timbre principles (with citations)

Short form: each role owns a **spectral slot, an envelope shape, and a stereo behaviour**. The recipes in section 3 follow these.

### 2.1 Bass (E1-E2): sub-heavy, harmonics for small speakers
- **808 / sliding 808 (Cinder).** Build from a sine or triangle with a fast pitch envelope and saturation; saturate so it translates on phones and laptops; layer a short click/kick on the attack. [violetrecording.com/how-to-make-808-slides, how-to-design-an-808]. A slide needs **one voice, legato on, glide on, overlapping notes** ("overlap by even a 16th and the glide kicks in"); mono low end, light sidechain to the kick, high-pass below ~30 Hz. Glide time is taste (one source: 50-200 ms subtle, 200-500 ms dramatic; no authoritative figure). [violetrecording.com/how-to-make-808-slides; soundtrap/audeobox summaries via search]
- **Pillow sub (Bramble).** Same sine core, no pitch drop, gentler saturation. My synthesis; the lo-fi sources (section 2.3) support rolling off top end and soft tape-style saturation.
- **Afrobeats / amapiano log-drum family** (a *bass-register melodic* hit, usable as a Cinder variant): sine/triangle carrier with FM or a fast pitch drop; the groove comes from glide between notes; ~+10 semitones over ~70 ms pitch drop, ~70 ms amp decay, zero sustain, tune the note to a pitch, tempo 108-115 BPM. [musicproductionwiki.com/articles/how-to-recreate-the-amapiano-log-drum, labelled "inferred" by that page; KVR thread: add "a quick down pitch for 1-5 milliseconds", separate envelopes for FM and filter, a kick-like transient]. Afrobeats specifically: **no source found**; amapiano is the documented neighbour.

### 2.2 Keys (E3-E4)
- **FM electric piano / Rhodes.** Ratio 1:1 body plus a high-ratio, very fast modulator for key click (Beat Kitchen: 14:1) or a single high ratio (Attack: 18:1; Muzines: 11-13). The modulation index drives brightness and should follow its own, shorter envelope than the amp: ~1 s mod decay vs ~4 s amp decay (Reason Studios Thor FM article). A slightly mistuned ratio sounds more electric-piano (Max/MSP tutorial). Hard playing "barks" (pickup nonlinearity); soft playing is mellow. Stereo tremolo and chorus are the standard EP effects. [beatkitchen.io/guides/synthesist/07-fm-synthesis; attackmagazine.com/technique/tutorials/fm-electric-piano; reasonstudios.com Thor demystified 9; docs.cycling74.com synthesis tutorial 5; victorymusical.github.io (bark 30-45% for classic studio Rhodes); support.apple.com MainStage vintage electric piano guide]
- **Lo-fi detuned keys with wow/flutter.** Wow = slower tape-speed drift, flutter = faster; simulate with a randomized LFO on pitch plus a small detune, or a chorus; roll off above ~2-4 kHz; add tape-style saturation. Keep it so subtle "you only notice it when it's off." [abbeyroad.com Waves lo-fi article; musicradar.com tape-string-synth (random LFO, detune pot at 4); hub.yamaha.com how-to-create-lo-fi (chorus, LPF 2-4 kHz); mubert.com/Native Instruments summaries; Spectrasonics Keyscape manual (Rhodes flutter depth and rate)]
- **House organ / M1-style stab (Sable).** The Korg M1 "Organ 1/2" presets are a 1990s house staple, from Madonna's "Vogue" (1990) on; the organ's harmonic content makes it good for stabs and driving basslines. [musicradar.com/news/how-to-create-classic-house-sounds-with-the-korg-m1-and-when-to-use-them (snippet only; article body would not load); create.routenote.com M1 history]. **No source gave M1 patch parameters.** The recipe below is a drawbar-organ approximation (additive sine partials plus a fast percussive harmonic), not an M1 emulation.

### 2.3 Pad (C3-C4): wide, slow, and out of the bass's way
- Two detuned saws or wavetables, a third an octave away for body, unison with **modest** detune, slow attack, long release, a low-pass with little resonance, slow LFO on cutoff/pitch/wavetable position, chorus for width, one long reverb, **high-pass the pad channel** (the page calls low-end build-up the number-one cause of mud), spread voicings. [violetrecording.com/how-to-make-a-pad-sound; edmprod.com/wavetable-synthesis (pad WT Pos on <1 Hz LFO)]
- **Supersaw:** default saw, phase random, 7-8 unison voices, detune and blend by ear; use lower detune with an even voice count; Serum's supersaw can sound thin next to others, so add chorus/Dimension. [productionmusiclive.com 10 supersaw tips for Serum; adsrsounds.com odd-or-even-unison-voices; KVR "airwave supersaw" thread]

### 2.4 Lead (G4-G5): the hook, bright and mid-forward
- **Square/saw trap lead** (Quix-style): saw in Osc A, square in Osc B, triangle sub, a noise layer, a comb filter. [sounds.pauseplayrepeat.com how-to-make-a-trap-lead-like-quix-in-serum, a 2019 post; treat as a starting point]. Portamento "really helps pull the sound together in trap leads"; the pitch operator envelope is the most important step (FM8 trap lead tutorial: adsrsounds.com).
- **Trap bell:** triangle wave with unison and detune, sometimes a fast pitch LFO, plus distortion and reverb [sound-design tips document found via search; weakest source here]. The FM bell design (inharmonic 1:3.5 style ratio) is standard FM knowledge; I could not find a Serum-specific bell page, so the Glint recipe is **[STARTING POINT]**.
- **Flute / whistle lead:** vibrato LFO mapped to **both pitch and volume**, a flanger for hollow upper register, random start phase per note [aulart.com Operator flute lead]; a little tape-hiss noise for breath in a whistle lead [adsrsounds.com tropical-house-whistle-lead-in-massive]. Serum wavetable-position tip: map WT Pos to an **envelope** with long decay and release so the timbre evolves over the note [edmprod.com].

### 2.5 Arp (C5-C6): short, bright, narrow, and clear of the lead
- A pluck is a decay without sustain and a bright, distinct transient: near-instant attack, short decay, zero sustain; low-pass with a filter envelope that opens on the attack (fast attack, decay similar to the amp's); tiny fast **downward pitch blip** for bite; velocity to cutoff; shorter decay at faster tempos; short tail reverb, tempo-synced dotted-eighth delay, quiet. [violetrecording.com/how-to-make-a-pluck-sound; cymatics.fm/blogs/production/creating-plucks-xfer-serum ("very short decay, ~20 ms or 1/32-1/64", pitch transient on coarse pitch, two oscillators detuned a few cents apart, past 30 cents sounds out of tune)]. Marimba-style pluck: wavetable whose early frames are harmonic-rich then fade to sine [adsrsounds.com DJ Snake-style marimba pluck, snippet only].
- Soft sine/triangle pluck: same envelope logic with a lower cutoff and a sine/triangle source (my synthesis).

### 2.6 Call (A4-E5): vowel-like, short, and different from everything else
- **Vowel formants.** "ah" ~ 730 / 1090 / 2440 Hz and "oo" ~ 300 / 870 / 2240 Hz (Peterson-Barney averages, adult male, F1/F2/F3). Method: a saw (all harmonics) into **parallel high-Q band-passes** at the formants, lowest formant loudest; bandwidth and gains matter as much as centre frequencies. [ccrma.stanford.edu/~kglee/m220c/formant.html; soundbridge.io/formants-vowel-sounds; reasonstudios.com Thor demystified 17 (formant filters)]
- **Jersey-club vocal character** (rhythmic chops, call-outs around a centre hook): high-pass 110-130 Hz, bright shelf about +3 dB at 8-10 kHz, compressor ~4:1 with 8-10 ms attack and 40 ms release for ~5 dB, a **short plate reverb 0.8-1.2 s** (0.6 s for Jersey/drill hybrids), pre-delay 10-15 ms, 1/16 ping-pong delay at ~10% wet, ducking the reverb return to the kick, ~135-145 BPM. [bchillmix.com how-to-build-a-jersey-club-vocal-preset-with-stock-plugins]. This is processing of recorded vocals; the synth "chop" recipe borrows the *processing and rhythm*, not a sampled voice.

## 3. The 13 recipes

### 3.0 Conventions for every recipe

- **Start from the Serum init patch.** Only changes from init are listed. Anything not listed stays at its init value.
- **Universal render hygiene (applies to all 13; not repeated):**
  ```
  a_randphase = "0"   b_randphase = "0"   noise_randphase = "0"      # determinism, section 1.3
  dly_enable = False                                                   # tempo delay is NOT baked into samples
  ```
  GUI (Tier G, all birds): set every LFO to **Trig** mode (so LFO phase restarts per note), save the state.
- **Block labels:** `P` = scriptable parameters. `G` = needs the GUI once (tables, routes, voicing). `Rn` = chassis slot from section 1.2 with its amount.
- **Level plan:** after rendering, peak-normalise each root to -3 dBFS and let the engine's auto-mix (flock.md section 3.3) apply gains; do not rely on `mastervol`.
- **FX baking policy:** bake **saturation, EQ, compression, FX filter and short room reverb** (all verified deterministic); leave **chorus, flanger, phaser and Hyper/Dimension to the engine** (verified non-deterministic in Serum). Do **not** bake the tempo-synced delay. Keep baked reverb short (tail inside the render tail in section 4) so the engine's own reverb/weather do not stack on a long one.

---

### 3.1 BRAMBLE (rook, bass) - "pillow sub"
**Reference family:** lo-fi / boom-bap sine sub with a soft-saturated octave. **Register:** E1-E2 (MIDI 28-40).
**G:** Osc A table = **Basic Shapes** (sine frame; first frame assumed sine, check). Voicing = Mono, Legato, portamento Always. R10 velocity -> cutoff.
**P:**
```
osc_a_on=True   a_vol="55"   a_octave_oct="1"      # octave-up sine layer, becomes the saturated "second voice"
a_unison="1"    a_phase_deg="0"
osc_s_on=True   sub_osc_level="95"   suboscshape="Sine"   suboscoctave_oct="0"   # the actual sub; oscs_fil stays off so it bypasses the filter
filter_on=True  fil_type="Low 12"   fil_cutoff_hz="700"   fil_reso="0"            # only osca_fil is on
env1_atk_ms="3"  env1_hold_ms="0"  env1_dec_s="1.00"  env1_sus_db="0.0"  env1_rel_ms="110"
dist_enable=True dist_mode="Tape Sat."  dist_drv="28"  dist_wet="45"
fx_fil_enable=True fx_fil_type="High 12" fx_fil_freq_hz="28"                        # clean subsonic rumble
porttime_ms="45"   mod10_amt = +18   # R10
```
**Mix role:** the polite anchor of the low end: mono, centre, -4 dB, ducks 3 dB on kick (flock.md 3.3). Song A is two hits per bar, so sustained is fine.
**Why it fits:** "Steady, unbothered" = no transient games, no pitch drop, long even sustain; the octave layer through tape saturation puts harmonics where phone speakers can hear the note, so it still reads when the sub can't be reproduced. 45 ms glide is the "short glide between notes" from the cast table. **P-fallback:** drop the octave layer (`osc_a_on=False`) and use sub sine alone with `dist_wet="60"`.

### 3.2 CINDER (crow, bass) - "sliding 808"
**Reference family:** trap/drill 808 with pitch-drop attack and a long decay; the drill slide is a *phrase* behaviour (see section 4.4). **Register:** E1-E2.
**G:** Osc A = Basic Shapes sine. Voicing Mono + Legato + Always portamento (only matters if you ever render a phrase). R5 = ENV 3 -> coarse pitch if you prefer a matrix pitch drop.
**P:**
```
osc_a_on=True  a_vol="40"  a_octave_oct="0"  a_phase_deg="0"
osc_s_on=True  sub_osc_level="100"  suboscshape="Sine"  suboscoctave_oct="0"
filter_on=False
env1_atk_ms="0.5" env1_hold_ms="0" env1_dec_s="1.6"  env1_sus_db="-oo"  env1_rel_ms="60"    # natural 808 decay, ignores key-up
env3_atk_ms="0.5" env3_dec_s="0.035" env3_sus="0"                                          # pitch-drop envelope (with R5 = +full)
dist_enable=True dist_mode="SoftClip"  dist_drv="45"  dist_wet="55"
eq_enable=True   eq_frqh_hz="5000"  eq_volh_db="-6.0"                                       # tame saturation fizz
fx_fil_enable=True fx_fil_type="High 12" fx_fil_freq_hz="28"
porttime_ms="90"
```
**Pitch drop:** primary route is the GUI chassis, **R5 = ENV 3 -> coarse pitch** (ENV 3 decay ~35 ms, drop of roughly +10 to +12 semitones, a 70 ms variant for the log-drum family [musicproductionwiki; a 1-5 ms blip for click per the KVR thread]). A MIDI pitch-bend ramp is the no-GUI alternative but did **not** verify (section 1.3).
**Variants:** `Cinder-B` (busier song): `env1_dec_s="0.7"` and `dist_mode="HardClip"`, `dist_drv="60"` (clipped, shorter, for fast rolls). `Cinder-log` (amapiano log-drum style, optional extra bird/variant): `env1_dec_s="0.12"`, pitch drop ~+10 st over 70 ms, tuned to the key, one octave higher register.
**Mix role:** the swagger bass: centre, -4 dB, mono under 120 Hz, ducks on kick. Never play it together with Bramble below ~80 Hz except via the "Two Basses" combo, which alternates bars (flock.md 5.1).
**Why it fits:** swagger = a bigger, longer, saturated note with a visible "lean back" decay; the 808 pitch drop is the genre identity. **Velocity layers:** 1 is enough (vel 94 matches the 0.74 song velocity); velocity does not change distortion drive in Serum (no route), so a second layer only adds amp change.

### 3.3 QUILL (rook, keys) - "lazy Rhodes"
**Reference family:** FM electric piano with lo-fi flutter (boom-bap and lo-fi). **Register:** E3-E4.
**G:** Osc A table = Basic Shapes sine; Osc B = same. A warp type = **FM (from B)** (menu `warposca`, see 1.5 for the exact entry text). R3, R8, R9, R11.
**P:**
```
osc_a_on=True  a_vol="80"  a_unison="1"  a_phase_deg="0"
osc_b_on=True  b_vol="0"   b_octave_oct="0" b_semi_semitones="0" b_fine_cents="4"   # 1:1 ratio, slightly mistuned (Max tutorial); B level 0 so only its FM is heard
a_warp="28"                                   # base FM amount (value text as shown)
env1_atk_ms="1.0" env1_dec_s="3.5" env1_sus_db="-oo" env1_rel_ms="260"
env2_atk_ms="0.5" env2_dec_s="0.9" env2_sus="0"   mod_3_amt = +45   # R3: FM index decays faster than amp (~1 s vs ~4 s, Thor article)
mod11_amt = +22                               # R11: harder = more bark (FM index)
mod_8_amt = +6    mod_9_amt = +10             # R8 wow/flutter ±few cents; R9 tremolo ~4.6 Hz (LFO4 rate: set sync enum "1/8" or free in GUI)
filter_on=True fil_type="Low 12" fil_cutoff_hz="3400" fil_reso="0"          # lo-fi roll-off 2-4 kHz (Yamaha)
dist_enable=True dist_mode="Tape Sat." dist_drv="18" dist_wet="35"
# ND (optional, not bit-exact): cho_enable=True cho_wet="30" cho_rate_hz="0.35" cho_dly_ms="6.0" cho_dep_ms="5.0"   -> prefer engine-side chorus
```
**Velocity layers: two, but only if the chassis wires Velocity -> FM amount (R11) and Velocity -> cutoff (R10).** Without those routes velocity renders identical audio (section 1.3), so use one layer. If wired: vel ~48 (mellow, where song velocities 0.34-0.42 live) and vel ~100 (barking), crossfade in the engine by note velocity.
**Mix role:** -9 dB, pan -0.25; the harmony. Plays the chord's 3rd/7th through weak steps (songs A-C).
**Why it fits:** "jazz head, wing-taps on chord hits" = a warm, slightly wobbly EP with a visible attack; the FM index envelope gives the "tine then mellow" shape. **P-fallback (no GUI):** Osc A on, Osc B off; use sub `Triangle` + A saw through `Low 12` at 900 Hz with `env1_dec_s="1.4"` gives a flat, EP-ish tone but no FM bark.

### 3.4 SABLE (raven, keys) - "drawbar stab"
**Reference family:** house organ / M1-style stab (approximation, section 2.2). **Register:** E3-E4.
**G:** Osc A = Basic Shapes sine, Osc B = same. R4 (ENV 3 -> B level), R9.
**P:** drawbars at 8' (sub), 4' (A, +1 octave), 2 2/3' (B, +19 semitones):
```
osc_s_on=True  sub_osc_level="100" suboscshape="Sine"  suboscoctave_oct="0"        # 8'
osc_a_on=True  a_vol="65"  a_octave_oct="1"                                         # 4'
osc_b_on=True  b_vol="22"  b_octave_oct="1" b_semi_semitones="7"                    # 2 2/3' (+19 st)
env3_atk_ms="0.5" env3_dec_s="0.04" env3_sus="0"    mod_4_amt = +55                 # R4: percussive click on the 2 2/3' partial
env1_atk_ms="2"  env1_dec_s="1.0" env1_sus_db="0.0" env1_rel_ms="70"                 # organ gate; engine controls the note length
dist_enable=True dist_mode="Tube" dist_drv="30" dist_wet="60"
# ND (optional): cho_enable=True cho_wet="45" cho_rate_hz="0.80" cho_dly_ms="6.0" cho_dep_ms="5.0"   # slow-rotary shimmer; deterministic alternative: R6 LFO1 vibrato ~0.8 Hz at +4
```
**Velocity layers:** 1 (organs are not velocity sensitive; render at vel 100 and let the engine scale).
**Mix role:** -9 dB, the "second keys": plays off-beat stabs (song A steps 6/14). The sine-heavy tone sits above Bramble and below the arps.
**Why it fits:** formal, theatrical = a clear, hollow, church-and-club organ tone with a crisp attack. Different from Quill by spectrum (odd/harmonic sines vs inharmonic FM tine) and by envelope (sustain 0 dB gated vs decaying). **P-fallback (no GUI):** sub Sine 8' + `a_octave_oct="1"` default saw through `Low 12` at 1.2 kHz (a saw, not a sine, so brighter and buzzier).

### 3.5 HUSH (raven, pad) - "moonlit supersaw"
**Reference family:** wide, dark detuned saw pad. **Register:** C3-C4.
**G:** Osc A and B both = **Default** (saw; this is the init table, so no GUI needed for the oscillators). R1 (swell) and R7 (breathing).
**P:**
```
osc_a_on=True  a_vol="60"  a_unison="7"  a_unidet="0.22"  a_uniblend="75"  a_uni_lr="80"
osc_b_on=True  b_vol="38"  b_unison="5"  b_unidet="0.18"  b_fine_cents="7"
filter_on=True fil_type="Low 24" fil_cutoff_hz="1600" fil_reso="8"   oscb_fil=True
env1_atk_ms="650" env1_dec_s="1.0" env1_sus_db="0.0" env1_rel_ms="1400"
env2_atk_ms="900" env2_dec_s="3.0" env2_sus="40"      mod_1_amt = +35               # R1: cutoff opens as the chord blooms
mod_7_amt = +8                                         # R7: slow breathing (LFO2 rate "bar" or slower)
# ND (optional): hyp_enable=True hyp_wet="0" hypdim_size="55" hypdim_mix="40"   # Dimension; skip for bit-exact renders
# ND (optional): cho_enable=True cho_wet="35" cho_rate_hz="0.20"
rev_enable=True verb_wet="20" verbsize="65" decay_s="2.4"
fx_fil_enable=True fx_fil_type="High 12" fx_fil_freq_hz="110"
```
**Velocity layers:** 1 (velocity 0.25 in songs = quiet; render at 100 and scale).
**Mix role:** -13 dB, panned wide (stereo spread +/-0.6), high-passed 180 Hz in the mix. Background bed.
**Why it fits:** half-asleep and breathing = slow 650 ms attack, dark low-pass, slow filter breathing. Brightest of the two pads only in the width, not in the highs. 7+5 voices at different detune produce the "wide" layer. Odd voice counts with moderate detune per the supersaw tips. **P-fallback:** works fully without the GUI except R1/R7 (then use a static `fil_cutoff_hz="1300"` and rely on the attack).

### 3.6 MOSS (rook, pad) - "hearth choir"
**Reference family:** warm triangle/vowel choir pad with a slow filter swell. **Register:** C3-C4.
**G:** Osc A table = Vowel/**DudaChoir** (factory vowel table, `wtpos` ~0.35 for an "ooh"), Osc B = Basic Shapes triangle. R1 (slow swell), R7.
**P:**
```
osc_a_on=True  a_vol="45"  a_unison="4"  a_unidet="0.12"  a_uniblend="75"  a_wtpos (raw 0.35)
osc_b_on=True  b_vol="60"  b_unison="3"  b_unidet="0.08"  oscb_fil=True
osc_s_on=True  sub_osc_level="30" suboscshape="Triangle" suboscoctave_oct="-1" oscs_fil=True
filter_on=True fil_type="Low 12" fil_cutoff_hz="1100" fil_reso="0"
env1_atk_ms="900" env1_dec_s="1.0" env1_sus_db="0.0" env1_rel_ms="1600"
env2_atk_ms="1400" env2_dec_s="2.5" env2_sus="55"     mod_1_amt = +45               # R1: the slow filter swell
# ND (optional): cho_enable=True cho_wet="40" cho_rate_hz="0.30"
dist_enable=True dist_mode="Tape Sat." dist_drv="15" dist_wet="30"
rev_enable=True verb_wet="18" verbsize="55" decay_s="2.2"
```
**Velocity layers:** 1.
**Mix role:** -13 dB, pan mirrored against Hush when both are perched; second-bird rule gives -2 dB.
**Why it fits:** cozy = rounder, darker and more static than Hush: triangle and a vowel table instead of saws, lower cutoff, a slower and larger swell. They stay distinct: Hush is saw-bright and wide with Dimension; Moss is hollow and vocal and mid-centred. **P-fallback:** sub Triangle + default saw through `Low 12` at 700 Hz (loses the vowel layer).

### 3.7 JINX (jackdaw, lead) - "show-off square lead"
**Reference family:** modern square/saw pop-trap lead with delayed vibrato and portamento. **Register:** G4-G5.
**G:** Osc A = Default (saw). Voicing = Mono, Legato, portamento Always. LFO1 sine, Trig. R1, R6, R10.
**P:**
```
osc_a_on=True  a_vol="70"  a_unison="3"  a_unidet="0.10"  a_uniblend="60"
osc_s_on=True  sub_osc_level="85" suboscshape="Square" suboscoctave_oct="0"  oscs_fil=True      # square comes from the sub oscillator
filter_on=True fil_type="Low 12" fil_cutoff_hz="3600" fil_reso="14"
env1_atk_ms="2" env1_dec_s="1.0" env1_sus_db="0.0" env1_rel_ms="140"
env2_atk_ms="0.5" env2_dec_s="0.16" env2_sus="40"     mod_1_amt = +30               # R1: little "zip" on each note
lfo1_delay (set ~250 ms)  mod_6_amt = +18             # R6: vibrato +/- ~18 cents, arriving late
dist_enable=True dist_mode="SoftClip" dist_drv="35" dist_wet="40"
rev_enable=True verb_wet="10" verbsize="30" decay_s="1.2"
porttime_ms="70"   mod10_amt = +25                    # R10
```
**Velocity layers:** 1.
**Mix role:** -8 dB, pan +0.15: the front hook. Narrow, mid-bright, zippy; owns 1.5-5 kHz.
**Why it fits:** "show-off, hops on accents" = forward, slightly cutting, with a late vibrato "wiggle" and a portamento hop. The saw+square sub follows the Quix-style layout. **P-fallback:** no vibrato or zip; only the saw+sub-square through a static `fil_cutoff_hz="3000"` (still reads as a lead).

### 3.8 GLINT (magpie, lead) - "trap bell"
**Reference family:** FM bell/mallet lead (trap bell). **Register:** G4-G5.
**G:** Osc A = Basic Shapes sine, A warp type = **FM (from B)**, Osc B = sine. R3 (index envelope), R11.
**P:**
```
osc_a_on=True  a_vol="80" a_unison="2" a_unidet="0.06"
osc_b_on=True  b_vol="0"  b_octave_oct="1" b_semi_semitones="10"                   # +22 st, ratio ~3.56:1 (inharmonic bell)
a_warp="34"
osc_s_on=True  sub_osc_level="20" suboscshape="Triangle" suboscoctave_oct="2"      # +2 octaves "ding" partial
env1_atk_ms="0.5" env1_dec_s="1.3" env1_sus_db="-oo" env1_rel_ms="450"
env2_atk_ms="0.5" env2_dec_s="0.38" env2_sus="0"   mod_3_amt = +50                 # R3: bright strike, mellow ring
mod11_amt = +25                                                                     # R11
filter_on=False
eq_enable=True eq_frqh_hz="7000" eq_volh_db="2.0"
rev_enable=True verb_wet="16" verbsize="55" decay_s="2.0"
```
**Velocity layers:** 1 (brightness comes from R11 at the render velocity, vel 100).
**Mix role:** -8 dB, +0.15 pan with Jinx not on the wire at once ("Shiny Things" combo has both; they must not sound alike).
**Why it fits:** "collector of shiny things" = a glassy, inharmonic, quickly decaying strike. Different from Jinx by decay shape (strike-and-ring vs held note) and spectrum (inharmonic partials vs harmonic). **P-fallback (no GUI):** sub Triangle +2 oct at 70% plus a default saw at `a_octave_oct="1"` through `Low 12` cutoff 2 kHz with `env1_dec_s="0.5"`: a toy-bell, no FM.

### 3.9 TICK (chough, arp) - "zipper pluck"
**Reference family:** bright saw pluck arp (progressive/pop). **Register:** C5-C6.
**G:** Default saw (init). R1, R5, R10.
**P:**
```
osc_a_on=True  a_vol="80"  a_unison="2"  a_unidet="0.08"  a_uniblend="100"
filter_on=True fil_type="MG Low 24" fil_cutoff_hz="520" fil_reso="18"
env1_atk_ms="0.5" env1_dec_s="0.17" env1_sus_db="-oo" env1_rel_ms="50"
env2_atk_ms="0.5" env2_dec_s="0.13" env2_sus="0"       mod_1_amt = +62             # R1: filter opens on the attack, closes in ~130 ms
env3_atk_ms="0.5" env3_dec_s="0.02" env3_sus="0"       mod_5_amt = -18             # R5: ~20 ms downward blip (Cymatics)
dist_enable=True dist_mode="Tube" dist_drv="20" dist_wet="30"
fx_fil_enable=True fx_fil_type="High 12" fx_fil_freq_hz="200"
mod10_amt = +30                                         # R10: harder = brighter
```
**Velocity layers:** 1 (songs alternate 0.42 and 0.38, a 4 percent step; not worth two layers).
**Mix role:** -11 dB, pan +0.35; the rhythmic sparkle on every 16th. Narrow band so it doesn't mask Echo/Glint.
**Why it fits:** "nervous energy, twitches on each sixteenth" = very short, snappy, high-resonance zip. **P-fallback:** without R1 use a static `fil_cutoff_hz="1500"`, `fil_reso="12"` and `env1_dec_s="0.12"` (a dry staccato saw).

### 3.10 PIP (jackdaw, arp) - "hollow kalimba pluck"
**Reference family:** square/soft pluck with a marimba-style overtone (see 2.5). **Register:** C5-C6.
**G:** Osc B = Basic Shapes sine. R1.
**P:**
```
osc_a_on=False
osc_s_on=True  sub_osc_level="95" suboscshape="Square" suboscoctave_oct="0"  oscs_fil=True     # hollow square
osc_b_on=True  b_vol="25" b_octave_oct="2"                                                     # sine 2 octaves up: the knock
filter_on=True fil_type="Low 12" fil_cutoff_hz="1900" fil_reso="6"   oscb_fil=True
env1_atk_ms="0.5" env1_dec_s="0.22" env1_sus_db="-oo" env1_rel_ms="60"
env2_atk_ms="0.5" env2_dec_s="0.09" env2_sus="0"     mod_1_amt = +35               # R1
# ND (optional): cho_enable=True cho_wet="20" cho_rate_hz="0.4"
```
**Variant "Pip-soft" (soft sine/triangle pluck):** `suboscshape="Triangle"`, `fil_cutoff_hz="1200"`, `b_vol="12"`, `env1_dec_s="0.30"`.
**Velocity layers:** 1.
**Mix role:** -11 dB, pan +0.35 (and mirrored -0.35 when it is the second arp). Rounder and quieter in the highs than Tick, so the two can stack.
**Why it fits:** playful, octave-jumping = a woody, round, "toy" pluck that still stays clear under Glint. **P-fallback:** works without the GUI except the sine B partial (use `b_vol="0"`).

### 3.11 ECHO (crow, call) - "formant chop"
**Reference family:** formant "ah/oo" vocal lead / Jersey-style vocal chop. **Register:** A4-E5.
**G:** Osc A = Default saw. R1 (vowel move), R6, `lfo1_delay`.
**P:**
```
osc_a_on=True  a_vol="75"  a_unison="2"  a_unidet="0.10"
filter_on=True fil_type="Formant-II"   fil_cutoff_hz=<oo start>  fil_reso="55"      # exact cutoff -> vowel mapping: see 1.5 formant sweep
env1_atk_ms="6"  env1_dec_s="0.32" env1_sus_db="-6.0"  env1_rel_ms="140"
env2_atk_ms="0.5" env2_dec_s="0.25" env2_sus="0"      mod_1_amt = +40               # R1: "oo" -> "ah" within the syllable
lfo1_delay (~220 ms)  mod_6_amt = +14
# ND (optional): cho_enable=True cho_wet="20"
eq_enable=True eq_frqh_hz="9000" eq_volh_db="3.0"                                    # +3 dB shelf at 8-10 kHz (Jersey vocal preset)
fx_fil_enable=True fx_fil_type="High 12" fx_fil_freq_hz="120"                        # HP 110-130 Hz
comp_enable=True cmp_rat="4:1" cmp_att_ms="9" cmp_rel_ms="40"
rev_enable=True verb_wet="12" verbsize="35" decay_s="0.9"                            # short plate, 0.8-1.2 s
```
Pitch scoop (optional): ENV 3 -> pitch (R5) at about -0.6 st with ~45 ms decay, or a MIDI bend ramp once that works (section 1.3).
**Velocity layers:** 1. **Mix role:** -8 dB, pan -0.1; short call-out that answers the hook. Keep its notes off Jinx's steps.
**Why it fits:** "the singer, throws its head back at phrase starts" = a vowel with a micro-scoop and syllable envelope that is audibly human; the Jersey processing keeps it forward and crisp rather than washy. **P-fallback:** the closest to P-only of the 13: Formant-II responds to `fil_cutoff_hz` on its own, but the "oo -> ah" move (R1) and late vibrato (R6) need the chassis, and the vowel targets need the fitting sweep from 1.5.

### 3.12 WREN-NOT (rook, call) - "whistle with breath"
**Reference family:** whistle / flute lead (tropical-house whistle lead, trap flute); stands in for the "flute lead" request. **Register:** A4-E5.
**G:** Osc A = Basic Shapes sine (2nd partial). R6 with `lfo1_delay`.
**P:**
```
osc_a_on=True  a_vol="8"  a_octave_oct="1"                                           # faint 2nd partial
osc_s_on=True  sub_osc_level="100" suboscshape="Sine" suboscoctave_oct="0"           # the whistle; oscs_fil stays off
osc_b_on=True  b_vol="6"  b_unison="16"  b_unidet="1.00"  b_uniblend="100"           # synthesized "breath": 16 max-detuned saws
oscb_fil=True  filter_on=True  fil_type="Band 12"  fil_cutoff_hz="4600"  fil_reso="35"   # only the breath goes through the band-pass
env1_atk_ms="35" env1_dec_s="1.0" env1_sus_db="0.0" env1_rel_ms="160"
lfo1_delay (~300 ms)  mod_6_amt = +12                                                # vibrato after the note blooms
rev_enable=True verb_wet="16" verbsize="45" decay_s="1.6"
```
Scoop (optional): ENV 3 -> pitch (R5) at about -1.5 st over ~70 ms, and optionally a fall at the tail.
**Noise alternatives:** the stock `Noises/Organics/H-Breath` or `Noises/Analog/BrightWhite` are sample-based (avoid); a resonant `Scream BP` filter on a single saw also hisses. The unison-saw breath above is fully synthesized and, with `b_randphase="0"`, deterministic.
**Velocity layers:** 1. **Mix role:** -8 dB, pan -0.1 (mirrors Echo; the "Back and Forth" combo alternates bars 1/3 vs 2/4). Sine + air sits above Echo's buzz in spectrum so the two don't mask.
**Why it fits:** insists it isn't a wren = a pure whistle line answering the others; breath makes it alive. **P-fallback:** sub sine + breath work without the GUI; the faint 2nd partial and vibrato are lost.

### 3.13 CORVUS (secret crown) - "crown stack"
**Status:** `birds.json` gives Corvus **no notes** (`songs.A` empty, voice `flockDrive`): its documented job is the Corvus FX / built-in drive on the flock bus. This Serum patch is an **optional accent** (my addition; needs Ethan's call). If used: one sparse downbeat hit.
**Reference family:** brass-like octave+fifth swell stack. **Register:** E3-E4 (keys range; my choice).
**G:** Osc A, B = Default saw. R1.
**P:**
```
osc_a_on=True  a_vol="70"  a_unison="5"  a_unidet="0.14"  a_uniblend="75"  a_uni_stack="12+7 (2x)"
osc_b_on=True  b_vol="45"  b_octave_oct="-1" b_unison="3" b_unidet="0.10" b_fine_cents="-9"  oscb_fil=True
filter_on=True fil_type="MG Low 24" fil_cutoff_hz="1200" fil_reso="12"
env1_atk_ms="40" env1_dec_s="1.2" env1_sus_db="-2.0" env1_rel_ms="500"
env2_atk_ms="90" env2_dec_s="0.7" env2_sus="35"       mod_1_amt = +55               # R1: brass swell
dist_enable=True dist_mode="Tube" dist_drv="38" dist_wet="50"
# ND (optional): cho_enable=True cho_wet="30" cho_rate_hz="0.25"
rev_enable=True verb_wet="24" verbsize="75" decay_s="3.2"
```
**Velocity layers:** 1. **Mix role:** -10 dB; stays out of the way, then the Corvus FX takes over the bus.
**Why it fits:** the king arrives with a regal, wide brass hit that is unlike any of the 12 (they are sines, FM, organ, saws, squares, formants; this is the only 12+7 stack brass).

### 3.14 Distinctness and blend check

| Bird | Source | Envelope | Spectral band (approx.) | Stereo |
|---|---|---|---|---|
| Bramble | sine + sat. octave | sustained | 40-400 Hz | mono |
| Cinder | sine, pitch drop | long decay | 30-300 Hz + saturation | mono |
| Quill | FM sines, flutter | decaying EP | 200 Hz-4 kHz | engine chorus |
| Sable | additive sines | gated | 200 Hz-3 kHz | rotary shimmer |
| Hush | detuned saws | slow swell | 150 Hz-2.5 kHz | wide |
| Moss | triangle + vowel table | slower swell | 150 Hz-1.5 kHz | medium |
| Jinx | saw + square sub | held, late vibrato | 400 Hz-6 kHz | centre-right |
| Glint | FM inharmonic | strike-and-ring | 600 Hz-10 kHz | centre |
| Tick | resonant saw | 130 ms zip | 600 Hz-5 kHz | narrow |
| Pip | square + sine knock | 90-220 ms | 500 Hz-3 kHz | narrow |
| Echo | formant saw | short syllable | 300 Hz-3 kHz | centre-left |
| Wren-Not | sine + band-passed air | held, vibrato | 700 Hz-6 kHz | centre-left |
| Corvus | 12+7 stack | swell | 150 Hz-3 kHz | wide |

Pairs most at risk of masking: **Jinx/Glint** (same register, both on the lead role; separate by decay shape, kept at -2 dB for the second bird), **Hush/Moss** (both pads; separate by spectral brightness and by mirrored pan), **Tick/Pip** (both arps; separate by cutoff and waveform), **Echo/Wren-Not** (both calls; separate by a buzzy formant vs pure air).

**Cross-checks to run once the patches exist (not done):** render each C-root, take the long-term spectrum, and check (a) no bird has more than 3 dB of overlap with another in its own 1/3-octave peak band, (b) the formant sweeps hit the vowel targets in 2.6, (c) the six HANDOFF checks from the engine.

## 4. Render advice for one-shot multisampling

### 4.1 Length per role (hold = key down, tail = after note-off)

Song events are in 16th steps: at 90 BPM one step is 167 ms; at 140 BPM it is 107 ms. Pad notes in the songs are 8-14 steps (1.3-2.3 s at 90 BPM, up to ~3 s at 70 BPM).

| Role | Hold (s) | Tail (s) | Total render | Notes |
|---|---|---|---|---|
| Bass: Bramble | 1.2 | 0.35 | 1.6 | sustained; engine ends notes early with its own fade |
| Bass: Cinder (808) | 0.5 | 1.5 | 2.0 | amp env decays naturally (`sus=-oo`); the tail must hold the whole decay |
| Keys: Quill | 1.0 | 1.2 | 2.2 | EP decays on its own |
| Keys: Sable, Corvus | 0.8 | 0.6 | 1.4 | gated; Corvus reverb adds a longer tail |
| Pad | 3.4 | 1.8 | 5.2 | hold covers the longest note plus the 650-1400 ms swell; `env1_rel_ms` 1400-1600 needs the tail |
| Lead: Jinx | 0.6 | 0.4 | 1.0 | |
| Lead: Glint | 0.4 | 1.2 | 1.6 | bell keeps ringing |
| Arp (Tick, Pip) | 0.15 | 0.3 | 0.45 | short; most of the sound is the first 200 ms |
| Call: Echo | 0.4 | 0.6 | 1.0 | |
| Call: Wren-Not | 0.5 | 0.6 | 1.1 | |

**The engine should shorten, not stretch.** Long samples can be cut by any note length with a gain fade (30-80 ms for bass/keys/lead, 120 ms for pads). Never time-stretch. Where the sample's own tail is longer than the next note, it simply runs into it (polyphonic overlap), which suits pads, bells, 808 and EP.

### 4.2 Release tail
- Render with a sustained key-down of `hold` seconds, then note-off, then a **tail** long enough for `env1_rel_ms` plus the baked reverb: tail >= release + reverb decay x ~0.6, with 20 ms of trailing digital silence.
- **Trim by threshold, not by length:** cut when the RMS of 50 ms windows falls below -70 dBFS, then apply a 10 ms fade. Do not truncate mid-tail.
- Do not leave a loop point; one-shots only.

### 4.3 Velocity layers
- **Quill: two layers** (vel ~48 and ~100), because FM bark is the velocity-dependent character and the songs sit at 0.34-0.42.
- **Cinder: one layer** (Serum has no velocity route to distortion drive, and velocity does nothing at all without a matrix route).
- **Everything else: one layer at vel 100**, and the engine scales by event velocity. Pad/arp/call songs use velocities 0.25-0.52, which would make Serum's own velocity->amplitude curve render too quietly if rendered at the event velocity.
- Total roots (section 4.4) is ~76. Because render cost is per call, not per second (section 1.3), render each bird's roots in **one call**: about 13 calls, ~1.5 minutes, instead of ~7 minutes.

### 4.4 Root spacing (every 3 semitones is the plan)
Roots at each 3 semitones means the engine resamples at most +/-1.5 semitones: pitch ratio 0.917-1.091.

| Role / bird | Spacing | Roots over the register | Why |
|---|---|---|---|
| Bass (Bramble) | 3 | E1 G1 Bb1 Db2 E2 (5) | sine; transposition is harmless |
| Bass (Cinder) | **3 only if the pitch drop is acceptable; else 2** | 5-7 | a +/-1.5 st shift also speeds/slows the pitch-drop and decay by ~9%; audible on a hard 808. Use 2 st (E1 F#1 Ab1 Bb1 C2 D2 E2) if you hear it. |
| Keys (Quill, Sable) | 3 | E3 G3 Bb3 Db4 E4 (5, x2 layers for Quill) | EP tine is rich; 9% shift acceptable |
| Pad | 3 | C3 Eb3 Gb3 A3 C4 (5) | detune beating changes with transposition (+/-9% beat rate) but stays sensible |
| Lead (Jinx, Glint) | 3 | G4 Bb4 Db5 E5 G5 (5) | Glint's inharmonic partials shift consistently; fine |
| Arp | 3 | C5 Eb5 Gb5 A5 C6 (5) | transients are short |
| **Call (Echo)** | **1 or 2** | A4 B4 C#5 D#5 E5 (every 2) or all 8 (every 1) | **transposing a formant filter moves the vowel**; it is a *filter* cutoff, not an offline formant, so the vowel is baked at the root. A +/-9% shift is a vowel shift. The register is only 7 semitones, so denser spacing costs little. |
| **Call (Wren-Not)** | 2 | same | a whistle's breath band and vibrato rate shift with resampling |
| Corvus | 3 | 5 | one-off |

Total: ~5+7+10+5+5+5+5+5+5+5+8+6+5 = ~76 renders.

**Slides and glides:** a one-shot cannot slide by itself. Cinder's drill slide and Bramble's short glide should be **engine-side**: when two consecutive bass notes overlap, ramp the playback rate of the first sample (or crossfade into the second at a pitch-ramped rate) over 45-200 ms with an exponential curve. Serum's own portamento only helps if you render a whole phrase, which breaks the one-shot design.

## 5. Open items for you
1. **Decide the Tier G path.** Either (a) approve the one-time GUI + `raw_state` step per bird (best sound), or (b) ship Tier P-fallbacks only (plain saw, sub shapes, filter types, FX; markedly less distinct). I recommend (a) for Quill, Glint, Echo, Sable and (b) is acceptable for Bramble, Cinder, Hush, Tick, Pip, Wren-Not.
2. **Corvus voice:** accept the optional crown-stack accent or leave Corvus as bus FX only.
3. **Audition.** Every number here is untested by ear. The first listening pass should be Echo (formant mapping), Glint (FM bell) and Quill (EP bark), because those depend most on the GUI-only parts.

## 6. Sources

Fetched or searched; "snippet" means I only saw the search summary, not the page body.

**Serum / synthesis references**
- Xfer Serum 2 manual (Serum 2, not 1): https://xferrecords.com/manual/serum-2
- Splice, features of Xfer Serum (unison up to 16; sample-based noise oscillator): https://splice.com/blog/exploring-the-feautres-of-xfer-records-serum/
- EDMProd, wavetable synthesis (WT Pos modulation, warp, unison, pads and leads): https://www.edmprod.com/wavetable-synthesis/
- Cymatics, plucks in Serum (20 ms transient envelope on coarse pitch, detune limits): https://cymatics.fm/blogs/production/creating-plucks-xfer-serum
- ADSR Sounds, Serum odd or even unison voices (snippet): https://www.adsrsounds.com/serum-tutorials/xfer-serum-odd-or-even-unison-voices/
- ADSR Sounds, DJ Snake-style marimba pluck in Serum (snippet): https://www.adsrsounds.com/serum-tutorials/dj-snake-style-marimba-pluck-in-serum/
- Production Music Live, 10 supersaw tips for Serum (snippet): https://www.productionmusiclive.com/blogs/news/10-supersaw-tips-for-xfer-serum-get-a-big-lush-sound-without-layering
- Pause Play Repeat, Quix-style trap lead in Serum (snippet): https://sounds.pauseplayrepeat.com/blogs/news/how-to-make-a-trap-lead-like-quix-in-serum
- Xfer forum, mono mode same-note retrigger: https://www.xferrecords.com/forums/posts/80458
- Local: `Serum.vst3` v1.368 enumeration via `pedalboard` (this file, section 1)

**Bass**
- Violet Recording, 808 slides: https://violetrecording.com/how-to-make-808-slides/
- Violet Recording, designing an 808 (snippet): https://violetrecording.com/how-to-design-an-808/
- Music Production Wiki, amapiano log drum: https://musicproductionwiki.com/articles/how-to-recreate-the-amapiano-log-drum
- KVR, log drum in Serum or Sylenth (pitch-drop 1-5 ms, separate FM and filter envelopes): https://www.kvraudio.com/forum/viewtopic.php?p=8213712

**Keys**
- Beat Kitchen, FM synthesis (EP 1:1 + 14:1 click; snippet): https://beatkitchen.io/guides/synthesist/07-fm-synthesis/
- Attack Magazine, FM electric piano (ratio 18; partial page): https://www.attackmagazine.com/technique/tutorials/fm-electric-piano/
- Reason Studios, Thor demystified 9 (FM; snippet): https://www.reasonstudios.com/news/post/thor-demystified-9-an-introduction-to-fm-synthesis-part-1
- Cycling '74, synthesis tutorial 5, frequency modulation: https://docs.cycling74.com/max8/tutorials/06_synthesischapter05
- Victory Musical, Rhodes bark range (snippet): https://victorymusical.github.io/victory-bender-roads/
- Apple MainStage vintage electric piano (tremolo, chorus; snippet): https://support.apple.com/en-kg/guide/mainstage/lgsifc1ba323/3.5/mac
- MusicRadar, tape-style string synth (random LFO wow/flutter, detune; snippet): https://www.musicradar.com/how-to/tape-string-synth
- Abbey Road / Waves, lo-fi vintage vibe (wow and flutter definitions; snippet): https://www.abbeyroad.com/news/adding-a-lo-fi-vintage-vibe-to-your-track-waves-audio-productionhub-2951
- Yamaha, how to create lo-fi (chorus, LPF 2-4 kHz; snippet): https://hub.yamaha.com/proaudio/recording/how-to-create-lo-fi
- Spectrasonics Keyscape manual, lo-fi (Rhodes flutter depth and rate; snippet): https://support.spectrasonics.net/manual/Keyscape/11/en/topic/lo-fi
- MusicRadar, classic house sounds with the Korg M1 (page body would not load; snippet): https://www.musicradar.com/news/how-to-create-classic-house-sounds-with-the-korg-m1-and-when-to-use-them
- RouteNote, Korg M1 history (snippet): https://create.routenote.com/blog/the-korg-m1-a-legendary-synth-that-defined-an-era/

**Pad, lead, arp**
- Violet Recording, pad: https://violetrecording.com/how-to-make-a-pad-sound/
- Violet Recording, pluck: https://violetrecording.com/how-to-make-a-pluck-sound/
- ADSR Sounds, FM8 trap sounds and lead (portamento; snippet): https://www.adsrsounds.com/fm8-tutorials/trap-sounds-and-production-with-fm8-part-3-the-rise-and-lead/
- Aulart, analog-style leads with Operator (flute lead with pitch and volume vibrato; snippet): https://www.aulart.com/analog-style-lead-synths-with-abletons-operator/
- ADSR Sounds, tropical house whistle lead in Massive (tape-hiss breath; snippet): https://www.adsrsounds.com/ni-massive-tutorials/tropical-house-whistle-lead-in-massive/

**Call**
- Stanford CCRMA, formant table (Peterson-Barney averages): https://ccrma.stanford.edu/~kglee/m220c/formant.html
- SoundBridge, formants and vowel sounds (snippet): https://www.soundbridge.io/formants-vowel-sounds
- Reason Studios, Thor demystified 17, formant filters (snippet): https://www.reasonstudios.com/news/post/thor-demystified-17-filters-pt-5-formant-filters
- B Chill Mix, Jersey club vocal preset with stock plugins: https://bchillmix.com/blogs/news/how-to-build-a-jersey-club-vocal-preset-with-stock-plugins
- Native Instruments, vocal chops (formant shifting; snippet): https://blog.native-instruments.com/vocal-chops/
