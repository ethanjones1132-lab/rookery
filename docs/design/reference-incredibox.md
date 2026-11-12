# Reference: Incredibox (the source for Rookery's melodic layer)

Researched 2026-11-08 by Claude for Ethan. Source: [Wikipedia, "Incredibox"](https://en.wikipedia.org/wiki/Incredibox), plus App Store listings. **This is a mechanics reference, not an asset source.**

## What it is
- **Incredibox**, a music game by **So Far So Good**, a French studio (Saint-Étienne). Created by Allan Durand (direction and code), Romain Delambily (art) and Paul Malburet (music). First released Aug 16, 2009 as a browser Flash game, later on iOS, Android, macOS, Windows and Steam.
- About 2 million copies sold by Jan 2023. It went viral in 2012 (a server crash, then coverage on Kotaku, Gizmodo and BBC Click), and it's widely used in schools (AASL Best Apps for Teaching & Learning, 2018).

## How it plays (the loop that made it addictive)
1. **Pick a style** (nine "versions": Alpha, Little Miss, Sunrise, The Love, Brazil, Alive, Jeevan, Dystopia, Wekiddy). Each is a complete sound pack with its own art.
2. **Seven identical performers** stand in a row.
3. **20 icons in 4 categories** (beats, effects, melodies, voices; 5 each). Drag an icon onto a performer and they **put on an accessory** (a hat, sunglasses, a mask, headphones) and **start singing that loop**, always in time.
4. **Swap, mute, solo** any performer.
5. **Combos:** specific 5-sound combinations unlock **3 hidden animated bonuses per version**, a short clip that plays at the top of the screen. There's a hint that tells you which character belongs to the current combo.
6. **Record and share** a mix by URL. Listeners vote, and a **Top 50** chart ranks the best. **Automatic mode** plays endless random mixes.

## Why it works
- **Nothing can sound bad:** every loop is in key and on the grid, so any combination is musical. Low skill floor, high ceiling.
- **Visible cause and effect:** a sound is a character with a costume, so you see the mix as well as hear it.
- **Discovery:** secret combos and bonuses reward experimenting. That gives people a reason to come back and to share what they found.
- **Social proof:** shareable mixes, votes and a chart.

## What Rookery takes vs. what it must not copy
| Take (mechanics, not protected) | Do not copy (their IP) |
|---|---|
| A row of characters, each one a looping voice | The name "Incredibox", version names, the "Polo" performer |
| Choose a sound, the character visibly changes and sings | Their character design (grey/black-and-white beatboxers, Malburet caricature), costumes, icons, art style |
| Everything locked to tempo and key, so any mix is musical | Their sounds or loops (theirs are recorded a cappella; ours are synthesized in code) |
| Mute / solo / swap per character | Their bonus animations or combo recipes |
| Hidden combos that unlock bonuses, plus a hint system | Their screen layout or drag-icon-onto-character presentation one for one |
| Templates / auto mode an agent can drive | |

## Rookery's original take (direction from Ethan, 2026-11-08; build later)
- **The Flock:** a row of **rooks/crows on a wire** (it fits the "Rookery" name and Corvus FX). Each bird is a **melodic voice** (lead, bass, chords, pad, arp, call/response, FX) synthesized deterministically, in key and on the project grid.
- **Each bird gets its own hat, persona or costume** with a **simple animation loop built in code** (SVG/CSS, no image assets), drawn with Hermes theme tokens.
- **Agent templates:** Hermes can pre-select and match a flock ("dusty boom bap flock", "trap flock") and the user can take over: perch, unperch, mute, solo, swap a bird's song.
- **Combos and easter eggs:** original combos that unlock bonuses (a harmony chorus, a hidden bridge, a visual flourish). These are our designs, not theirs.
- Melodic voices render through the same deterministic engine and checks as the drums, so the reliability story holds.

Not verified here: TikTok/YouTube-era virality and fan mods (e.g. "Sprunki"). Wikipedia covers only the official "INCREDIMODS" section (announced Mar 2025).
