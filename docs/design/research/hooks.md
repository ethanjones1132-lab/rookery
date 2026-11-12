# Flock hooks: what makes the loops catchy (research + implementable rules)

Researched 2026-11-08 for the Flock rewrite (see `../flock.md`, `../flock-music-implementation-plan.md`). Goal: replace "beeps and boops" with parts that feel modern, hooky, and still fit together in any 2-6 bird combination.

## 0. How to read the evidence labels

| Label | Meaning |
|---|---|
| **EMPIRICAL** | A controlled or survey study with listeners (n and design noted). |
| **STATISTICAL** | A corpus count or model fit over many songs. Describes what is common, not what causes catchiness. |
| **CONVENTION** | Practitioner sources (producer guides, tutorials, wikis). Useful for genre feel, weak as proof. |
| **DESIGN** | A number or threshold I chose to turn a finding into a testable rule. The finding is cited, the number is mine and should be tuned by ear. |

**Honest limits of this research**
- I read the full text of the Hooked (ISMIR 2013) and Van Balen et al. (ISMIR 2015) papers, the Witek 2014 paper (first 100k chars), and the Incredibox modding docs. For Jakubowski et al. 2017, Margulis, Nunes et al., Savage et al., Tan/Lustig/Temperley, Interiano and all genre sources I only got abstracts, press summaries or search-result summaries. Those claims are labeled as such. Re-check numbers before quoting them publicly.
- **I could not find a published scale-degree frequency table for pop melodies** (Hooktheory's per-degree charts are interactive, and the blog posts I fetched give chord statistics, not melody degrees). So a rule like "use scale degrees 1, 5, 6, 3 most" is **not** backed here. The substitute rule (R9) is chord-tone-on-strong-beat, which is backed by Hooktheory's own tension metric as a definition and by the universals work.
- Incredibox's official docs say loops share one duration and BPM is info only. They say nothing about keys or harmony. How Incredibox keeps every mix in key is inferred, not documented (see R12).
- Genre claims (trap, drill, Afrobeats, Jersey club, lo-fi, house) come from producer guides and wikis. They agree with each other on tempo and feel but they are not rigorous.

---

## 1. Principles (15 rules)

Notation used below is defined in section 2.0. A "bar" is 16 steps; step 1 is beat 1, step 3 is the "and" of 1, step 7 is the "and" of 2, step 15 is the "and" of 4.

### R1. The hook is a 5-10 second object: build it from a 2-bar motif inside a 4-bar loop
- **Evidence (EMPIRICAL, small pilot, n=26 testers, 32 songs).** In Hooked, recognition took about 5 s on average, sections of the same song differed by about 4 s, and the authors place the hook window at "5 to 10 s", longer than 400 ms "plinks" and shorter than a whole chorus. [Burgoyne et al. 2013]
- **Rule.** The memorable unit is 1-2 bars (3-6 s at 80-120 BPM). Loops are 4 bars so the motif is heard twice per cycle. Never write a lead or call part that needs more than 4 bars to state its idea.
- **Test.** Each lead/call pattern has a motif of at most 2 bars, repeated or answered inside the 4 bars.

### R2. Repeat, then vary: AABA' (bars 1, 2 identical; bar 3 contrasts; bar 4 = bar 1 with a changed ending)
- **Evidence.** EMPIRICAL: adding repetition made unfamiliar music more enjoyable and interesting to everyday listeners, and the effect held for music they liked and disliked; over-repetition is a real risk. [Margulis, On Repeat; OUP blog 2014]. STATISTICAL: Hot 100 songs with more repetitive choruses reached chart success faster (press figures differ: about 17% higher top-40 odds per repetition, not verified in the paper). [Nunes, Ordanini, Valsesia 2015]. EMPIRICAL/STATISTICAL: within a song the more recognizable sections have melodies with lower entropy and more typical motifs, "recognizable melodies are more repetitive". [Van Balen et al. 2015]
- **Rule.** At least 2 of the 4 bars are note-for-note (in chord-relative terms) identical. The one changed bar is bar 3 (contrast) or bar 4 (turnaround), never both unless the pattern is explicitly a "B" song.
- **Test.** Count bars with identical event lists after chord-relative resolution: >= 2 per lead/arp/call pattern. At most 1 bar may differ by more than 3 events from bar 1.

### R3. Use a common overall shape with one distinctive local move
- **Evidence.** EMPIRICAL (abstract only): earworm tunes had **more common global contours** but **less common average gradients between turning points** than matched non-earworm tunes, and faster average tempo, in a 100 vs 100 comparison over 83 melodic features. [Jakubowski et al. 2017]. STATISTICAL: descending and arched contours are statistically common across 304 recordings from many cultures. [Savage et al. 2015]
- **Rule.** Lead motifs use an **arch** (up then down), **descending**, or **rise-then-fall** shape over the bar. Zigzag shapes are out. Each motif gets exactly **one** distinctive feature: one leap of a 4th or more, one repeated-note cluster, or one off-beat anticipation. The rest is stepwise or chord-tone skips.
- **Test.** Classify the pitch sequence of each lead/call motif into {arch, descending, ascending-then-hold}; reject others. Count leaps >= 5 semitones: exactly 1 per motif (<= 2 per bar).

### R4. Small intervals, and reverse direction after a leap
- **Evidence.** STATISTICAL: small intervals are among the statistically common cross-cultural features (secondary summary of Savage et al. 2015). STATISTICAL/EMPIRICAL: melodies tend to reverse after a skip, but von Hippel and Huron argue most of that is regression to the mean from tessitura limits, not an innate rule, and listeners still expect upward continuation after downward skips. [von Hippel & Huron 2000]
- **Rule.** At least 70% of lead/call intervals are steps or 3rds in the chord-relative grid (a "step" = adjacent chord tone or scale tone). After any leap of 5+ semitones, the next move is the opposite direction or a repeat. Keep the part inside its register band so the regression happens naturally.
- **Test.** Interval histogram per pattern; post-leap direction check.

### R5. Short motifs: 3-6 notes per bar, 3 or fewer distinct note lengths, 5 or fewer distinct pitches
- **Evidence.** STATISTICAL: motivic patterns, short phrases, few durational values and 7 or fewer scale degrees were all statistically frequent cross-cultural features (secondary summary of Savage et al. 2015). EMPIRICAL: lower melodic entropy predicted recognizability. [Van Balen et al. 2015]
- **Rule (DESIGN thresholds).** Lead: 3-6 notes per bar, <= 5 distinct pitch classes per 4 bars, <= 3 distinct durations. Call: 1-4 notes per bar. Arp is exempt from the note count but not from the pitch-class limit.
- **Test.** Count onsets per bar, distinct (degree, octave) pairs, distinct durations.

### R6. Aim for medium syncopation, not none and not maximum
- **Evidence.** EMPIRICAL: 120 BPM funk drum breaks with low, medium and high syncopation; the relationship with wanting to move and with pleasure was an **inverted U** (quadratic coefficients -0.59 and -0.65), peaking at medium. Medium beat Low by about 0.3 and High by about 0.4-0.55 on a 5-point scale. Effect strongest in people who like dancing. [Witek et al. 2014] (Drum breaks, not melodies. Applying it to melody is an extrapolation.)
- **Rule (DESIGN thresholds).** For lead and keys, 35-65% of onsets sit off the quarter-note beats (steps other than 1, 5, 9, 13). Fewer than 35% sounds like a metronome; more than 65% loses the pulse. Always keep one anchor onset on beat 1 or beat 3 in each 2-bar half.
- **Test.** Off-beat onset fraction per pattern and per role in the mix; anchor check.

### R7. Anticipate the next bar: put a note or chord on the "and" of 4 (step 15) that belongs to the next chord
- **Evidence.** STATISTICAL (abstract-level, not read in full): rock melodies show a corpus-wide habit of anticipatory syncopation, notes landing an eighth before a strong beat. [Tan, Lustig, Temperley 2019]. CONVENTION: gospel/soul chord pushes and house stabs on the off-beats. [Attack Magazine; producer guides]
- **Rule.** Every template pattern for keys, lead and bass may use step 15 (and/or step 7 or 11) as an anticipation of the following chord (`>` prefix or `ap`). Bar 4 step 15 should anticipate bar 1 of the next loop so the loop point feels pulled, not slammed.
- **Test.** At least one anticipation onset (step 15 or 7 resolving forward) in each bar-4 of keys/lead/bass patterns.

### R8. Four chords, one bar each (or two bars each), from the common-progression family
- **Evidence.** STATISTICAL: Hooktheory's database (tens of thousands of TheoryTab songs) shows I-V-vi-IV as the most common four-chord loop; V is the most likely chord after I (31%); IV-I is as common as V-I; iii almost always goes to IV or vi. A 10,000-song analysis found C-G-Am-F and C-F-G-C the top two. [Hooktheory blog; Dong report]. Minor-key equivalents (i-VI-III-VII, i-VII-VI-VII) are CONVENTION: I did not retrieve minor-key frequency numbers.
- **Rule.** Project progressions come from the four-chord set the templates already use. Offer a user-facing "pick a progression" list limited to that family so manual choices cannot leave the common zone. Chords change on bar lines only (no mid-bar changes except the `>` anticipation).
- **Test.** Progression field is one of an allow-list; no iii -> I or other rare edges.

### R9. Strong beats get chord tones; passing tones live on weak 16ths
- **Evidence.** STATISTICAL (definition): Hooktheory tracks "Chord-Melody Tension", the share of melody notes outside the current chord, and "Melodic Complexity" as off-key notes plus syncopation. Low tension is the default consonant case. [Hooktheory song metrics]. This is also what keeps any 2-6 bird combination consonant.
- **Rule (DESIGN threshold).** At least 85% of onsets on steps 1, 5, 9, 13 are chord tones (1, 3, 5, 7 or octave copies). Passing tones (2, 4, 6) only on steps that are not 1, 5, 9, 13, and shorter than 3 steps. Keys/pad extensions (9, 11, 13) are allowed only when the voicing also contains at least 3 chord tones.
- **Test.** Strong-beat chord-tone ratio per role and for the full mix (matches the harmony-test plan).

### R10. Start the hook at a structural change: bar 1 downbeat or a pickup into it
- **Evidence.** The hooks literature the Hooked authors cite agrees that hooks start at points of considerable structural change, the beginning of a new section. [Burgoyne et al. 2013, citing Burns 1987 and Mercer-Taylor 1999]. CONVENTION supports the pickup idea.
- **Rule.** The lead/call hook states its first note on step 1 or on a pickup in steps 13-16 of bar 4. Loop restarts therefore sound like a new section arriving.
- **Test.** First onset of the lead motif is within steps {1, 3, 4} of bar 1 or a pickup at {13..16} of bar 4.

### R11. The vocal-like voice (call) must be able to carry the hook alone
- **Evidence.** EMPIRICAL/STATISTICAL: in the Hooked recognition data, "Vocal Prominence" had the strongest effect on recognizability of all components. Sections that sound typical and representative of the song were also more recognizable. [Van Balen et al. 2015]
- **Rule.** Every call pattern set includes one "hook carrier" (CL7) that works as the sole melody when no lead is perched. When both are perched, the call voice gets the question/answer slot (R12), not the competing melody. The call voice stays in the 64-79 band, mid-loud (velocities 84-104), and never gets filtered below the lead in the auto-mix.
- **Test.** Mix with only {bass, call}: call has >= 3 notes per bar average over 4 bars and an arch/descending contour.

### R12. Leave space for the answer: lead and call own different steps
- **Evidence.** CONVENTION: call-and-response is a standard hook-building technique across the genres in scope (producer guides). The Incredibox mechanics: each performer holds exactly one loop, all loops have the same duration (`looptime`), and bars alternate A/B states so parts are built to be simultaneous. Official modding docs; the key/harmony design is not documented there. [Incredibox mod docs]. Incredibox sounds are a cappella recordings by one musician, which fits a "write all parts against each other" workflow. [Clubic interview, via search; not fetched]
- **Rule (DESIGN).** Ownership masks per bar for the melodic pair: **Lead owns steps 1-10 of bars 1-3 and steps 1-8 of bar 4. Call owns steps 11-16 of bars 1-3 and steps 9-16 of bar 4.** If a call event begins inside the lead's active note, the call event is dropped (not moved). If lead is absent, the call may play its CL7 hook-carrier over all steps.
- **Test.** Zero call onsets inside lead sustain windows; zero lead onsets inside call-owned steps unless the lead is marked "doubles".

### R13. Role separation by register, density budget and onset cap
- **Evidence.** CONVENTION (arrangement practice; also the stated design in the Flock plan: roles have registers and an auto-mix).
- **Rule (DESIGN).** Registers (MIDI): bass 28-48, pad 48-64, keys 55-72, call 64-79, arp 60-76 (60-88 allowed only if the lead is absent), lead 72-91. Onsets per bar budget: bass 3-6, keys 2-5, pad 1-2 (long), lead 3-6, arp 4-16 (cap 8 when lead is present), call 1-4. Hard cap: <= 4 onsets on any one 16th step across all roles. Collision priority (low priority yields): lead > call > bass > keys > arp > pad. When 5-6 birds are perched, arp velocity -12 and keys drop to the sparse pattern of the same song.
- **Test.** Per-step onset count, per-bar budgets, register containment; `test_flock_harmony.py` for all 2-6 combinations.

### R14. Swing, tempo and feel belong to the template, not the bird
- **Evidence.** CONVENTION: lo-fi guides recommend about 55-65% swing; amapiano guides cite 54-58% swing on 16ths; UK drill is generally 138-150 BPM with a 3+3+2 hat grouping and sliding 808s; amapiano is about 108-115 BPM; house is 120-128 BPM with stabs on the off-beat steps 3, 7, 11, 15; Jersey club is about 130-140 BPM with a syncopated kick pattern and chopped vocals; lo-fi is about 70-95 BPM. (Sources in section 4.) EMPIRICAL (abstract only): earworms had faster average tempo than matched non-earworms. [Jakubowski et al. 2017]
- **Rule.** Swing is a template parameter applied to every even 16th step of every role (shared groove), as a timing offset, so all birds swing identically. When a template gives a tempo range, the default sits in the upper half of it. Trap/drill patterns use 3+3+2 groupings (steps 1, 4, 7, 9, 12, 15) instead of triplets because the grid is 16ths.
- **Test.** All roles' onsets shift identically for a given swing value (no per-bird swing).

### R15. Default mood for the 2020s palette: minor, dorian or mixolydian, with 7ths
- **Evidence.** STATISTICAL: across about 500,000 UK songs 1985-2015, "happiness" and "brightness" declined and "sadness" rose slightly, while successful songs were happier and more party-like than the rest. [Interiano et al. 2018] (Low-level audio descriptors, not mode counts. Weak support.) CONVENTION: trap and drill guides push minor keys almost exclusively; lo-fi and soul lean on 7ths and 9ths.
- **Rule.** Four of the five templates are minor-family or soul-colored; major keys (Lo-Fi Study, Sunday Soul) must carry 7ths/9ths in keys and pad to avoid a nursery-rhyme sound.
- **Test.** Keys/pad voicings include a 7th or 9th in major-key templates.

---

## 2. Per-role pattern library

### 2.0 Notation (every pattern is data a programmer can paste into `birds.json`)

```
event   := step ":" degree ["~"] "@" velocity ["/" length]       step 1..16; length in 16th steps (default 2)
degree  := chord-relative scale step. 1 = chord root, 3 = chord third (diatonic), 5, 7 = diatonic seventh.
           2, 4, 6 = passing/extension steps. 8 = root one octave up, 9 = 2nd up, 10 = 3rd up, 12 = 5th up, 14 = 7th up.
           "L" prefix = one octave lower (L5 = fifth below the root). All degrees are diatonic steps of the
           project scale, so they are always in key; pentatonic feel comes from using only 1,3,5,7 and 2.
           "ap" = approach: the scale step directly below the NEXT bar's chord root (bar 4 wraps to bar 1).
           "~" suffix = glide from the previous note (808 slide / portamento).
           "[a,b,c]" = chord of simultaneous degrees. Named voicings (keys/pad):
             T = [1,3,5]   S7 = [1,5,7,10]   R9 = [3,5,7,9] (rootless)   O = [1,5,10] (open)   SUS = [1,5,9]
           ">" prefix on a voicing = play the NEXT bar's chord (anticipation).
velocity: 1-127 base; the engine adds +/-6 humanization and the template's swing.
"bN=bM"  = bar N is a copy of bar M. "bN=bM +{...}" = copy, then replace/add the listed events.
Steps for reference: 1 beat1, 3 &1, 5 beat2, 7 &2, 9 beat3, 11 &3, 13 beat4, 15 &4.
Strong beats = 1, 5, 9, 13 (R9). 3+3+2 grid = 1, 4, 7, 9, 12, 15.
"K" prefix on a degree (e.g. K1) = KEY-relative (tonic = 1) instead of chord-relative. Needs one engine
  extension; used by 2 lead patterns marked [needs K]. Drop those if the engine cannot take it.
```

Every pattern also carries: `tags` (genres), `dens` (onsets per 4 bars), `why`.
All velocities assume the bird's auto-mix gain; the "loudest" accent in any pattern is 100-108.

### 2.1 BASS (register 28-48; root = chord root)

**BS1 "Dusty Walker"** tags: boom-bap, lo-fi | dens 18 | pairs with: KY5, KY1, any drum kit with kick on 1 and 3
- b1: `1:1@104/6  7:1@78/2  11:5@88/2  13:1@92/3`
- b2 = b1   |  b3 = b1 +{`11:3@84/2`}   |  b4: `1:1@104/6  9:5@84/2  11:3@80/2  15:ap@90/2`
- Why: root-fifth bounce with a push on the "and" of 2 (steps 7, 11) is the classic head-nod, and the step-15 approach tone pulls into the loop restart (R7).

**BS2 "Half-Time 808"** tags: trap | dens 15 | pairs with: PD4, AR2, LD1
- b1: `1:1@112/9  11:1@92/2  14:5@86/2~`
- b2 = b1   |  b3: `1:1@112/7  9:1@90/2  12:5@90/2~  15:1@84/2~`   |  b4 = b1 +{`14:ap@90/3~`}
- Why: long sub root with one late slide is the tension-and-release every trap listener expects; few notes keep it out of the way of the bell hook (R13).

**BS3 "Drill Slide"** tags: drill, trap | dens 20 | pairs with: LD5, KY4, AR2
- b1: `1:1@108/3  4:1@86/3  7:L5@96/2~  9:1@104/6`
- b2 = b1   |  b3: `1:1@108/3  4:3@84/3  7:1@96/2~  9:L5@104/6~`   |  b4 = b1 +{`15:ap@92/2~`}
- Why: the 3+3+2 onset spacing plus slides (the signature of the style) gives a lurching, ominous groove from three notes per half bar (R14).

**BS4 "Offbeat Roller"** tags: house, disco | dens 16 | pairs with: KY2, AR5, PD5 (kick on 1/5/9/13)
- b1: `3:1@96/2  7:1@90/2  11:1@96/2  15:5@86/2`
- b2 = b1   |  b3 = b1 +{`15:3@86/2`}   |  b4 = b1 +{`15:ap@92/2`}
- Why: bass lives on the off-beat steps the four-on-the-floor kick leaves open, so groove and low-end never mask each other.

**BS5 "3-2 Bounce"** tags: afrobeats, amapiano, dancehall | dens 20 | pairs with: KY6, LD2, CL6
- b1: `1:1@100/3  4:1@78/2  7:5@90/2  11:1@96/2  13:3@84/2`
- b2 = b1   |  b3 = b1 +{`13:5@84/2`}   |  b4 = b1 +{`15:ap@90/2`}
- Why: steps 1-4-7 then 11-13 is the son-clave 3-2 shape, the syncopated spine that Afrobeats and amapiano bass/log drums bounce on (CONVENTION).

**BS6 "Soul Walk"** tags: r&b, soul, gospel | dens 17 | pairs with: KY3, PD6, LD6
- b1: `1:1@96/4  5:3@80/4  9:5@86/4  13:ap@84/4`   (the `ap` on step 13 is the only allowed strong-beat non-chord tone; it resolves by step into the next root)
- b2 = b1   |  b3: `1:1@100/6  7:1@60/1  9:5@84/3  13:3@80/2  15:ap@84/2`   |  b4 = b1
- Why: a quarter-note walk through 1-3-5 with a stepwise approach is a real walking line, and it works well against a descending chord progression like Sunday Soul's.

**BS7 "Lazy Pocket"** tags: lo-fi, chillhop | dens 15 | pairs with: KY1, PD1, LD4
- b1: `1:1@98/7  8:5@64/1  11:1@86/3  15:5@78/2`
- b2 = b1   |  b3 = b1 +{`11:3@84/3`}   |  b4: `1:1@98/7  9:5@80/3  13:ap@84/4`
- Why: few notes, late and soft, leaves room for the 7th/9th chords on top (R13) and the ghost note at step 8 gives the "lazy" feel under shared swing (R14).

### 2.2 KEYS (register 55-72; chord stabs and comping)

**KY1 "Rhodes Comp"** tags: lo-fi, r&b | dens 12 | pairs with: BS7, LD4, PD1
- b1: `1:R9@78/5  7:R9@62/2  11:R9@70/4`
- b2 = b1   |  b3: `1:R9@78/5  11:R9@70/4  15:>R9@66/2`   |  b4: `1:R9@78/5  7:R9@62/2  15:>R9@72/2`
- Why: rootless 3-5-7-9 voicings sound like 7th/9th jazz chords, and the pushed hits on the "and" of 2/3/4 are the swung comping a Rhodes player would do (R7, R15).

**KY2 "Offbeat Stab"** tags: house, uk-garage | dens 15 | pairs with: BS4, AR5, LD3
- b1: `3:S7@96/2  7:S7@88/2  11:S7@96/2  15:S7@84/2`
- b2: `3:S7@96/2  11:S7@96/2  15:S7@84/2`   |  b3 = b1   |  b4: `3:S7@96/2  7:S7@88/2  11:S7@96/2  14:S7@72/1  15:>S7@92/2`
- Why: stabs on steps 3, 7, 11, 15 are the house off-beat; dropping step 7 in bar 2 is the variation that stops it being a metronome (R2, R6).

**KY3 "Gospel Push"** tags: soul, gospel, r&b | dens 11 | pairs with: BS6, PD6, LD6, CL3
- b1: `1:S7@92/6  11:S7@70/2  15:>S7@84/2`
- b2 = b1   |  b3: `1:S7@92/4  5:S7@70/2  11:S7@76/2  15:>S7@86/2`   |  b4: `1:S7@92/6  9:S7@70/2  15:>S7@90/2`
- Why: chord on the downbeat and a push on the "and" of 4 into the next chord (the anticipation is the gospel/soul move that makes progressions feel like they lean forward).

**KY4 "Sparse Pluck"** tags: trap, drill | dens 9 | pairs with: BS2, BS3, AR2, LD1, LD5
- b1: `1:O@90/3  11:O@72/2`
- b2: `1:O@90/3  7:O@70/2`   |  b3 = b1   |  b4: `1:O@90/3  9:O@72/2  15:>O@80/2`
- Why: two or three open-voiced hits a bar. In trap, the chord should punctuate, not fill; that space is what lets the bell hook speak (R12, R13).

**KY5 "Boom-Bap Stab"** tags: boom-bap, jazz-rap | dens 12 | pairs with: BS1, LD4, CL4, CL1
- b1: `1:S7@98/2  8:S7@74/2  11:S7@86/2`
- b2 = b1   |  b3: `1:S7@98/2  8:S7@74/2  13:S7@80/2`   |  b4: `1:S7@98/2  11:S7@86/2  15:>S7@82/2`
- Why: a loud hit on 1, a ghost at step 8 (the "a" of 2) and one more hit before the bar ends is the chopped-sample rhythm of a boom-bap piano loop.

**KY6 "Muted Chank"** tags: afrobeats, highlife, dancehall | dens 20 | pairs with: BS5, LD2, CL6
- b1: `1:T@88/1  4:T@72/1  7:T@80/1  11:T@84/1  14:T@70/1`
- b2 = b1   |  b3: `1:T@88/1  4:T@72/1  7:T@80/1  9:T@76/1  12:T@84/1  15:T@70/1`   |  b4 = b1
- Why: short, muted triad hits on the 3+3+2 skeleton imitate a funk/highlife guitar part, and the very short note length leaves the lead the spaces between (R12).

### 2.3 PAD (register 48-64; sustained, slow attack, one chord per bar, smooth voice-leading)

Rule for all pads: choose the octave placement of each voice to minimize total semitone movement between consecutive chords (common tones stay). Hooktheory's bass-smoothness metric rewards stepwise motion; the same logic applies to pad voicings.

**PD1 "Slow Wash"** tags: lo-fi, boom-bap | dens 4 | `1:S7@56/16` every bar. Why: one soft chord a bar is the harmonic bed that makes lo-fi sound like lo-fi.
**PD2 "Swell"** tags: house, r&b | dens 4 | per bar `1:O@44/16` with a velocity ramp 44 -> 72 across the bar (engine: cc swell). Why: rising level builds anticipation toward the next chord.
**PD3 "Late Entry"** tags: trap, drill | dens 4 | per bar `5:T@58/12`. Why: arrives on beat 2 so the downbeat belongs to drums, 808 and the hook.
**PD4 "Shell Drone"** tags: trap, drill, any minor | dens 4 | per bar `1:[1,5,8]@52/16`. Why: no third, so it never clashes with a differently-voiced keys or lead and works in any mode.
**PD5 "Sus Pulse"** tags: house, afro-house | dens 8 | per bar `1:SUS@60/8  9:SUS@52/8`. Why: open sus chords re-voiced every half bar give house its sustained lift without a clear major/minor claim.
**PD6 "Choir Bed"** tags: soul, gospel, r&b | dens 4 | per bar `1:R9@58/16`. Why: warm 3-5-7-9 voicing under gospel-style keys and the vocal-like call.
**PD7 "Open Fifths"** tags: boom-bap, drill, ambient | dens 4 | per bar `1:[1,5,12]@50/16`. Why: dusty and neutral; leaves harmony coloring to the other birds.

### 2.4 LEAD (register 72-91; the main hook; owns steps per R12)

Each lead is AABA'. Chord-relative degrees mean the motif **transposes with the chord** (a sequence), a very common hook device.

**LD1 "Bell Hook"** tags: trap, melodic-trap | dens 14 | pairs with: CL1, BS2, PD4, KY4
- b1: `1:8@100/3  4:7@78/2  7:5@92/4`
- b2 = b1   |  b3: `1:10@104/3  4:8@80/2  7:7@90/2  9:5@96/4`   |  b4 = b1 +{`15:3@80/2` (pickup into bar 1)}
- Why: descending 3-note shape on a bell tone, repeated, then one higher contrast bar; sparse and ringing, the pattern behind so many minor-key trap loops (R1-R3).

**LD2 "Pentatonic Hop"** tags: afrobeats, amapiano, dancehall | dens 20 | pairs with: CL6, BS5, KY6
- b1: `3:5@88/2  6:5@70/1  7:8@96/2  11:7@84/2  14:5@80/2`
- b2 = b1   |  b3: `3:5@88/2  6:5@70/1  7:8@96/2  11:10@100/3  14:8@82/2`   |  b4 = b1 +{`15:3@78/2`}
- Why: starts on the "and" of 1 (anticipation), the repeated-note pick-up, then a high point on the 3-2 skeleton; bounces without sounding busy (R6, R7).

**LD3 "Piano Riff"** tags: house, uk-garage | dens 22 | pairs with: KY2, BS4, CL2
- b1: `1:8@96/2  3:7@80/1  5:5@88/2  8:5@72/1  11:7@90/2  15:8@84/2`
- b2 = b1   |  b3: `1:10@98/2  3:8@80/1  5:7@88/2  8:5@72/1  11:8@92/2  15:10@86/2`   |  b4 = b1 +{`15:8@90/2` (replaces the bar-1 step-15 note)}
- Why: a rolling eighth-note piano riff that circles root-seventh-fifth with pushed accents; bar 3 lifts everything by a third for the "chorus" feeling.

**LD4 "Lazy Sigh"** tags: lo-fi, boom-bap, chillhop | dens 10 | pairs with: KY1, BS7, CL3
- b1: `1:5@80/6  9:3@72/4  12:2@62/1`
- b2 = b1   |  b3: `1:7@80/6  9:5@74/4  13:3@70/3`   |  b4 = b1 +{`15:7@66/2`}
- Why: three to four notes a bar, long and soft, the 7th and 9th flavor colored by the passing 2: a hook you can hum while studying (R5).

**LD5 "Dark Dyad"** tags: drill, trap, dark | dens 16 | pairs with: BS3, KY4, CL1
- b1: `1:5@100/3  4:5@82/3  7:6@92/2  9:5@100/4`
- b2 = b1   |  b3: `1:8@100/3  4:8@82/3  7:7@92/2  9:5@100/4`   |  b4 = b1 +{`13:3@84/2`}
- Why: a repeated-note figure with a neighbor tone is the ominous minor piano idea of drill; 3+3+2 spacing plus a neighbor step makes it creep rather than sing (R14).

**LD6 "Soul Call-Up"** tags: r&b, soul, gospel | dens 14 | pairs with: CL3, KY3, BS6, PD6
- b1: `1:3@92/4  5:5@86/3  9:8@100/4  13:7@80/2  15:5@76/2`
- b2 = b1   |  b3: `1:5@92/4  5:8@88/3  9:10@104/4  13:8@82/2  15:7@78/2`   |  b4 = b1 +{`15:3@70/2`}
- Why: a single arch per bar, up through the chord and falling back, singable and gospel-leaning; bar 3 is the same shape one step higher (R3).

**LD7 "Cascade"** tags: jersey-club, trap, house | dens 24 | pairs with: CL2, BS3, KY2 (lead drops to only first 8 steps when CL2 is perched)
- b1: `1:8@100/1  4:8@86/1  7:8@92/1  10:7@80/1  13:8@96/1  16:7@72/1`
- b2 = b1   |  b3: `1:10@100/1  4:10@86/1  7:10@92/1  10:8@80/1  13:10@96/1  16:8@72/1`   |  b4 = b1
- Why: a 3-step cascade of staccato repeats (dotted-eighth spacing) is the stutter that Jersey club leans on, and the shift up in bar 3 is the whole contrast (R2, R5).

[needs K] **LD8 "Fixed Hook"** tags: trap, afrobeats | dens 12 | key-relative (stays put while chords move)
- b1: `1:K5@100/3  4:K3@82/2  7:K1@92/4` (descending 5-3-1 of the key, whatever the chord)
- b2 = b1  |  b3: `1:K6@100/3  4:K5@82/2  7:K3@92/4`  |  b4 = b1
- Why: a hook that does not move is the strongest earworm form (identical every repeat) and works only over chords that all contain or tolerate K1/K3/K5; engine must check, else fall back to nearest chord tone.

### 2.5 ARP (register 60-76; chord-tone patterns, 8ths/16ths, supports and does not compete)

**AR1 "Up-Down Eighths"** tags: lo-fi, house, r&b | dens 32 | b1: steps 1,3,5,7,9,11,13,15 degrees `1 3 5 8 5 3 5 3`, velocities `90 66 74 66 90 66 74 62`, length 2. b2-b4 = b1. Why: an eighth-note arch in chord tones is the plain, consonant bed; accents on beats 1 and 3.
**AR2 "Skip 3-3-2"** tags: trap, drill, afrobeats | dens 24 | b1: steps 1,4,7,9,12,15 degrees `1 5 8 5 3 5`, velocities `88 70 84 78 66 80`, length 2. b2 = b1, b3 degrees `3 5 8 5 3 5`, b4 = b1. Why: the cross-rhythm groove sits against a straight kick and keeps trap and drill moving.
**AR3 "Octave Bounce"** tags: house, jersey-club | dens 32 | steps 1,3,5,7,9,11,13,15 degrees `1 8 1 8 1 8 5 12` velocities alternating 92 / 70. b2-b4 = b1 (b4 final two degrees `5 ap`). Why: octave jumps are the most reliable dance-floor motion; the last two notes turn toward the next chord.
**AR4 "Sparse Pluck"** tags: lo-fi, boom-bap | dens 16 | steps 1,7,11,15 degrees `5 8 7 5`, velocity `70 62 66 60`, length 3. b2 = b1, b3 degrees `3 8 7 5`, b4 = b1. Why: four soft notes a bar; adds sparkle without adding density.
**AR5 "Gated Sixteenths"** tags: house | dens 64 | all 16 steps, degrees cycle `1 5 8 5` x4, velocity 100 on steps 3,7,11,15 else 52, length 1. Same every bar, bar 4 last 4 steps rise `5 8 10 12`. Why: relentless quiet 16ths with the off-beats accented, in the same slots as KY2/BS4's off-beat grid, so it reads as energy not clutter. Use only when lead is absent or dropped to LD3's first half (R13).
**AR6 "Rolling Cascade"** tags: afrobeats, amapiano | dens 24 | steps 1,4,7,10,13,16 degrees `1 3 5 8 5 3`, velocity `84 66 76 70 82 62`. b3 degrees shift +1 chord tone. Why: the 3-step cascade gives a rolling motion that crosses the bar line and so glues the loop together.

### 2.6 CALL (register 64-79; vocal-chop-like; vowel field = `ah` `oo` `oh` `hey` `ha`)

**CL1 "Answer Tag"** tags: trap, boom-bap, r&b | dens 10 | vowel `oh` | pairs with: LD1, LD5, KY5
- b1: `11:5@96/2  14:3@84/3`
- b2 = b1   |  b3: `11:8@98/2  14:5@84/3`   |  b4: `9:8@100/3  13:5@90/4`
- Why: lives in lead's quiet steps 11-16, answering the first phrase with a falling pair; bar 4 grabs the empty second half for the "reply" (R12).

**CL2 "Chop Stutter"** tags: jersey-club, house, pop | dens 18 | vowel `hey` | pairs with: LD7, LD3, AR3
- b1: `9:8@100/1  10:8@80/1  12:8@92/1  14:7@86/1`
- b2 = b1   |  b3 = b1 +{`16:10@84/1`}   |  b4: `9:8@100/1  10:8@80/1  11:8@90/1  13:7@96/2`
- Why: repeated short vocal stabs on a syncopated cell are the chop technique Jersey club and house use as a rhythmic hook; bar 4's stutter run-up announces the loop restart.

**CL3 "Long Sigh"** tags: r&b, soul, lo-fi | dens 6 | vowel `ah` | pairs with: LD6, LD4, KY3, KY1
- b1: `9:5@88/6~  15:3@70/2`
- b2 = b1 +{`9:7@88/6~`}   |  b3 = b1   |  b4: `9:8@92/6~  15:5@72/2`
- Why: a long portamento note per bar, the melismatic sustained voice that R&B uses for "singing" the harmony, always in the back half so the lead keeps the front.

**CL4 "Hey!"** tags: boom-bap, hip-hop | dens 4 | vowel `hey` | pairs with: KY5, BS1
- b1: rest   |  b2: `13:8@104/2`   |  b3: rest   |  b4: `13:8@104/2  15:5@80/1`
- Why: one ad-lib shout every second bar; scarcity makes it a fingerprint.

**CL5 "Call and Echo"** tags: lo-fi, house, pop | dens 8 | vowel `oo` | pairs with: LD4, LD3
- b1: `5:5@96/2  8:5@58/2`   |  b2 = b1   |  b3: `5:8@98/2  8:8@58/2`   |  b4: `5:5@96/2  8:5@58/2  13:3@80/3`
- Why: a call and its quieter echo three steps later, doubled for effect; turns two events into a rhythm.

**CL6 "Afro Chant"** tags: afrobeats, amapiano | dens 12 | vowel `oh` | pairs with: LD2, BS5, KY6
- b1: `11:5@92/2  14:5@78/2`   |  b2 = b1   |  b3: `11:8@94/2  14:5@78/2  16:3@72/1`   |  b4 = b1
- Why: a repeated-note chant on the back half of the 3-2 skeleton, the group-vocal answer idiom.

**CL7 "Vocal Hook" (hook carrier, used when no lead is perched)** tags: all | dens 14 | vowel `ah`/`oh`
- b1: `1:5@100/3  4:3@84/2  7:1@92/4  13:3@80/2`   |  b2 = b1   |  b3: `1:8@100/3  4:7@84/2  7:5@92/4  13:3@80/2`   |  b4 = b1 +{`15:ap@78/2`}
- Why: R11. A complete AABA' arch with the same rhythm as LD1, so a flock of only {bass, call, drums} still has a singable melody.
- Rule: if a lead is perched, CL7 is replaced by that bird's own song, not played.

### 2.7 Cross-role pairing guide (what slots which pattern owns)

| Pair (lead + call) | Slot ownership | Why it works |
|---|---|---|
| LD1 + CL1 | Lead steps 1-10, call 11-16 (bar 4: call 9-16) | Lead states 3 notes, call answers with 2 |
| LD2 + CL6 | Lead 3-14, call 11-16 only in bars 2, 4 | Afro: lead has steps 3-10, chant overlaps only at the 3-2 tail |
| LD3 + CL2 | Lead drops to bars' first 8 steps | House riff then chop stutter |
| LD4 + CL3 | Lead 1-12 (long notes), call 9-16 | Both slow; sigh sits where lead is decaying |
| LD5 + CL1 | Lead 1-12, call 13-16 | Drill: call becomes one sparse echo |
| LD6 + CL3 | Lead 1-15, call 15-16 tails + bar 4 | Soul: lead sings, call adds a held harmony |
| LD7 + CL2 | Lead 1-8, call 9-16 | Both cascades alternate halves |

Other helpful pairings (bass + keys + drums):
- **BS1 + KY5**: sparse/loud keys on 1, 8 and 11; bass on 1, 7, 11. Close but not equal onsets: keys hit steps the bass sustains through, not attacks.
- **BS4 + KY2**: both on steps 3, 7, 11, 15 by design. This is house: the same off-beat grid, with bass in the low register and stabs in the high.
- **BS2 + KY4 + AR2**: the 808 sustains over steps 1-9; keys on 1 and 11 only; arp fills the 3+3+2 skeleton.
- **BS6 + KY3 + PD6**: soul trio; the walk covers 1, 5, 9, 13, keys push at 11 and 15, pad is the sustain.

Pairs that are **bad** (do not recommend; engine should thin them):
- KY2 + AR5 + LD3 simultaneously: three roles on steps 3/7/11/15; the collision resolver (R13) drops AR5 first.
- LD7 + AR3: both staccato eighth-ish cascades; arp is muted if lead pattern is LD7.
- KY6 + AR6: both 3+3+2; arp keeps only chord-tone degrees and velocity -12.

Song map (suggestion): **A = the first listed pattern for that role in the template (simple, safe), B = busier variant (e.g. LD3/AR5/KY2), C = sparse variant (e.g. LD4/AR4/KY4).** Hidden D songs reuse CL7 for the lead's role.

---

## 3. Template recipes

Keys, scales and progressions are the ones already fixed in `../flock.md` section 6, so the catalog does not need to change. Chord names assume diatonic seventh-capable chords from the project scale. Two issues found in the existing table: (1) "D dorian i - iv - VII - III" should read **i - IV - VII - III** (the dorian iv is major: Dm, G, C, F); with scale-derived chord quality the engine will play it correctly, only the label is wrong. (2) Sunday Soul's IV - iii - ii - I is a descending soul loop (Ab, Gm, Fm, Eb); it works because bass BS6 walks it.

### 3.1 Dusty Boom Bap
- **Key / scale:** D dorian. **Progression:** i - IV - VII - III (Dm - G - C - F), 1 bar each.
- **Tempo:** 84-94 BPM (default 90). **Swing:** 56%.
- **Roles:** bass BS1, keys KY5 (B song = KY1), pad PD7 or PD1, lead LD4 (as lead A), arp AR4, call CL4 (A) / CL1 (C).
- **Existing 4-bird flock:** Bramble A (BS1), Quill B (KY5), Hush A (PD7), Echo C (CL1).
- **Hook:** keys stab (KY5) plus the Hey! ad-lib every second bar. Rules in play: R2 (AABA'), R6 (ghost note at step 8), R12.

### 3.2 Trap Night
- **Key / scale:** F# minor. **Progression:** i - VI - III - VII (F#m - D - A - E).
- **Tempo:** 130-150 BPM (default 140, half-time feel). **Swing:** 50% (straight; triplet feel comes from 3+3+2 groupings).
- **Roles:** bass BS2 (B song = BS3), keys KY4, pad PD4 (C song = PD3), lead LD1 (alt LD8), arp AR2, call CL1.
- **Existing 4-bird flock:** Cinder B (BS2), Tick B (AR2), Glint A (LD1), Hush C (PD3).
- **Hook:** bell lead LD1 with the 808 sliding at step 14. Rules in play: R1, R3, R14.

### 3.3 Lo-Fi Study
- **Key / scale:** Bb major (Ionian). **Progression:** I - vi - ii - V (Bb - Gm - Cm - F), with 7ths.
- **Tempo:** 72-88 BPM (default 82). **Swing:** 60%.
- **Roles:** bass BS7, keys KY1, pad PD1 (R15: 7ths/9ths), lead LD4, arp AR4, call CL3 (alt CL5).
- **Existing 4-bird flock:** Bramble C (BS7), Quill A (KY1), Moss A (PD1), Wren-Not B (CL5).
- **Hook:** Lazy Sigh melody plus the call echo. Rules in play: R5 (sparse), R9 (extensions in voicings), R15.

### 3.4 Late House
- **Key / scale:** A minor (natural, with dorian 6 allowed in arps). **Progression:** i - VII - VI - VII (Am - G - F - G).
- **Tempo:** 120-126 BPM (default 124). **Swing:** 52%.
- **Roles:** bass BS4, keys KY2, pad PD5 (alt PD2), lead LD3, arp AR3 (busy: AR5 only if lead absent), call CL2.
- **Existing 4-bird flock:** Cinder A (BS4), Sable B (KY2), Pip A (AR3), Jinx C (LD3 first-half form).
- **Hook:** piano riff LD3 over off-beat stabs; the call (CL2) chops answer in the second half. Rules in play: R6, R7 (step 15 anticipation), R13 (AR5 dropped when five or more birds).

### 3.5 Sunday Soul
- **Key / scale:** Eb major. **Progression:** IV - iii - ii - I (Ab - Gm - Fm - Eb), with 7ths/9ths.
- **Tempo:** 72-88 BPM (default 80). **Swing:** 58%.
- **Roles:** bass BS6, keys KY3, pad PD6, lead LD6, arp none (or AR4 on bar 4), call CL3 (alt CL5).
- **Existing 5-bird flock:** Bramble B (BS6), Sable A (KY3), Moss B (PD6), Echo A (CL3), Glint C (LD6's bell-sparkle variant).
- **Hook:** LD6 arch with the sustained call under it. Rules in play: R3, R7 (the gospel push KY3), R15.

### 3.6 Future templates that the pattern library already supports (not requested)
Afro Bounce (BS5 + KY6 + LD2 + CL6 + AR6, about 100-108 BPM, swing 56%), Drill Night (BS3 + KY4 + LD5 + CL1 + AR2, 140 BPM, swing 50%), Jersey Club (LD7 + CL2 + AR3 + BS3, 135 BPM, swing 50%).

---

## 3b. Suggested automated checks (derived from the rules)

| Check | Rule |
|---|---|
| Pattern has >= 2 identical bars | R2 |
| Lead/call contour in {arch, descending, ascending-hold} | R3 |
| >= 70% intervals steps or 3rds; post-leap reversal | R4 |
| Lead 3-6 notes/bar, <= 5 pitch classes, <= 3 durations | R5 |
| Off-beat share 35-65% (lead, keys) | R6 |
| Bar-4 anticipation onset exists | R7 |
| Progression in allow-list, chord changes on bar lines | R8 |
| >= 85% of strong-beat onsets are chord tones, per role and per mix | R9 |
| First lead/call onset in bar 1 or bar 4 pickup | R10 |
| bass + call alone: >= 3 call notes/bar | R11 |
| Zero call onsets inside lead sustain | R12 |
| Per-step onset cap <= 4; per-bar budgets; registers | R13 |
| One swing value applied to all roles | R14 |
| Major-key templates have 7th/9th in keys/pad | R15 |

---

## 4. Sources

Verified by reading the source (full or most of the text):
- Burgoyne, Bountouridis, Van Balen, Honing (2013). Hooked: A Game for Discovering What Makes Music Catchy. ISMIR. https://archives.ismir.net/ismir2013/paper/000101.pdf
- Van Balen, Burgoyne, Bountouridis, Müllensiefen, Veltkamp (2015). Corpus Analysis Tools for Computational Hook Discovery. ISMIR. https://archives.ismir.net/ismir2015/paper/000148.pdf
- Witek, Clarke, Wallentin, Kringelbach, Vuust (2014). Syncopation, Body-Movement and Pleasure in Groove Music. PLOS ONE 9(4). https://pmc.ncbi.nlm.nih.gov/articles/PMC3989225/
- Incredibox official modding documentation (loop duration, bpm "for info", slot limits). https://www.incredibox.com/mod/doc
- Hooktheory, "The most common chord progressions" analysis (part 2). https://www.hooktheory.com/blog/music-theory-analysis-1300-songs-for-songwriting-part2/
- Hooktheory song metrics (Chord-Melody Tension, Melodic Complexity definitions). https://hooktheory.com/song-metrics/about
- Hooktheory, chord progression search patterns (V follows I 31%). https://www.hooktheory.com/blog/chord-progression-search-patterns-and-trends/

Read at abstract or summary level only (claims labeled accordingly):
- Jakubowski, Finkel, Stewart, Müllensiefen (2017). Dissecting an Earworm. Psychology of Aesthetics, Creativity, and the Arts 11(2). https://research.gold.ac.uk/19405 ; DOI 10.1037/aca0000090
- Margulis (2014). On Repeat: How Music Plays the Mind (OUP). Summary: https://blog.oup.com/2014/01/music-repetition-neuroscience/
- Nunes, Ordanini, Valsesia (2015). The power of repetition: repetitive lyrics in a song increase processing fluency and drive market success. J. Consumer Psychology. https://iris.unibocconi.it/handle/11565/3955321
- Savage, Brown, Sakai, Currie (2015). Statistical universals reveal the structures and functions of human music. PNAS 112(29). https://ore.exeter.ac.uk/repository/handle/10871/31311 ; summary https://hraf.yale.edu/documents/1115
- Interiano et al. (2018). Musical trends and predictability of success in contemporary songs in and out of the top charts. Royal Society Open Science. https://www.ncbi.nlm.nih.gov/pmc/articles/PMC5990848/
- von Hippel & Huron (2000). Why do skips precede reversals? Music Perception 18(1) (cited via search summary; I did not open the paper).
- Tan, Lustig, Temperley (2019). Anticipatory syncopation in rock: a corpus study. Music Perception (cited via search summary only).
- Williamson & Müllensiefen (2012) earworm study: referenced from the Hooked paper, not read.

Genre/practitioner sources (CONVENTION; surfaced by search, mostly summaries):
- UK drill (3+3+2 hats, 138-150 BPM, sliding 808): https://en.wikipedia.org/wiki/UK_drill ; https://blog.soundtrap.com/how-to-make-uk-drill-beats/
- Afrobeats / amapiano (tempo, log drum, swing): https://articles.roland.com/?p=67237 ; https://beatstorapon.com/blog/how-to-make-amapiano-beat/ ; https://www.native-instruments.com/blogs/blog/amapiano-music
- Jersey club (130-140 BPM, kick pattern, chops): https://musicorigins.org/jersey-club-jersey-trap-and-tang-dance/ ; https://en.wikipedia.org/wiki/Jersey_club
- Lo-fi (70-95 BPM, 7ths/9ths, swing): https://blog.landr.com/lofi-music/ ; https://splice.com/blog/lo-fi-chord-progressions/
- House piano stabs (off-beat steps 3/7/11/15): https://www.attackmagazine.com/technique/tutorials/creating-house-piano-chords-with-toontracks-ezkeys/ ; https://www.attackmagazine.com/technique/passing-notes/kerri-chandler-chords-part2/
- Trap melody/chords (minor, bells, flutes): https://emastered.com/blog/trap-chord-progressions ; https://create.routenote.com/blog/how-to-make-trap-melodies/
- Incredibox interview (a cappella recordings, single musician): https://www.clubic.com/application-mobile/actualite-860534-incredibox-beatbox-destine-creation-musicale-originale-interview.html
- Incredibox (history, structure): https://en.wikipedia.org/wiki/Incredibox

**Originality note.** Every pattern in section 2 was written from the rules above and general genre conventions; none transcribes a specific song. Do not tune patterns toward any particular recording.
