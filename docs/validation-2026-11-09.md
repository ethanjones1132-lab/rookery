# Validation — 2026-11-09

Environment: Windows 11, Hermes 0.23.0 (`2bd378ed1b8`), Python 3.11.15
(Hermes dev venv; the managed runtime is 3.14.9). Repo: a local checkout.

## Test suite

```
& "%LOCALAPPDATA%\hermes\hermes-agent\venv\Scripts\python.exe" -m pytest tests/engine tests/acceptance -q
# 284 passed in 120.58s
```

Includes the 19 acceptance tests, the engine tests, the Flock harmony/polyphony
tests, the new batch-apply tests and the mix-report tests.

## Catalog audit

```
python tools/audit.py
PASS binaries: none tracked
PASS samples: 67 first-party voice one-shots (5.17 MiB, manifest provenance ok)
PASS deps: 5 capped
PASS provides_tools: 10 match register()
PASS requires_hermes: >=0.23.0
PASS secrets: no credential reads in code
PASS self_update: none found
```

## Engine round trip (live-check)

A clean project, one batch (groove + Flock template + master chain), render,
per-bird mix, state, undo, and a repeated render:

```
BATCH rev 2 tracks ['kick', 'snare', 'hat'] swing 0.58 diff items 15
RENDER hash 5f4fd71b612cab36 checks {'length_exact': True, 'no_clipping': True,
  'loudness': True, 'seam_click': True, 'not_silent': True, 'deterministic': True}
METERS {"kick":{"rms_db":-19.87,"peak_db":-3.93},
        "snare":{"rms_db":-29.73,"peak_db":-4.37},
        "hat":{"rms_db":-32.70,"peak_db":-9.12}}
MIX {"correlation":0.973,"width":0.116,"lr_balance_db":0.14,"crest_db":13.26,
     "centroid_hz":741.0,
     "bands_pct":{"sub":65.6,"low":17.3,"mid":9.2,"high":7.0,"air":0.6}}
FLOCK MIX rev 3
STATE
live-check | rev 3 | 90 BPM | 4 bars | swing 0.58
Wire (D dorian, i-IV-VII-III, dust): [1 Bramble A] [2 Quill B] [3 Hush A]
  [4 Echo C·+3dB·pan-0.2] [5 —] [6 —]
UNDO rev 4
RENDER2 hash 5f4fd71b612cab36 same True
RENDER3 hash 5f4fd71b612cab36 same True
```

What this proves: a batch is one revision and one undo step; the groove expands
to tracks/steps/swing; the render returns per-track meters and the master mix;
per-bird gain/pan is visible in state and survives undo; re-rendering the same
project returns the same hash.

## What was not tested

- `hermes plugins validate . --install-deps` at the pinned commit (the catalog
  gate). Run it before the catalog PR and paste the output into the README.
- Live Desktop audio after the gateway restart. The page/transport were
  exercised in Desktop on 2026-11-08, before the Flock polyphony and batch-apply
  changes; the engine, API and handler paths are covered by the tests above.
- Telegram/CLI delivery.
- macOS/Linux audio and Desktop.
- A fresh-machine install from the catalog.
- Perceived audio quality: the mix numbers are objective; the ear is Ethan's.
