"""Integrity and playback checks for the shipped Serum one-shots."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from rookery.flock.synth import _CATALOG, _note_signal

VOICE_ROOT = Path(__file__).resolve().parents[2] / "rookery" / "flock" / "voices"


def test_manifest_samples_exist_and_cover_each_bird_lane():
    manifest = json.loads((VOICE_ROOT / "manifest.json").read_text(encoding="utf-8"))
    birds = {bird["id"]: bird for bird in [*_CATALOG["birds"], _CATALOG["corvus"]]}
    assert set(manifest["birds"]) == set(birds)
    for bird_id, entry in manifest["birds"].items():
        role = "keys" if birds[bird_id]["role"] == "crown" else birds[bird_id]["role"]
        low, high = _CATALOG["registers"][role]
        notes = [sample["midi"] for sample in entry["notes"]]
        # Samples are baked on a 3-semitone grid. A lane can extend a few
        # semitones past the nearest baked root; the sample is repitched there.
        assert abs(notes[0] - low) <= 6 and abs(notes[-1] - high) <= 6, (bird_id, role, low, high, notes[0], notes[-1])
        assert all(abs(a - b) <= 3 for a, b in zip(notes, notes[1:]))
        assert all((VOICE_ROOT / sample["file"]).is_file() for sample in entry["notes"])
        assert entry["sample_rate"] == 44100
        assert entry["deterministic_repeat"] is True
    assert sum(path.stat().st_size for path in VOICE_ROOT.rglob("*") if path.is_file()) <= 8 * 1024 * 1024


def test_sample_voice_is_deterministic_and_synth_option_remains_available():
    event = {"bird_id": "glint", "voice": "bell", "role": "lead", "midi": 73,
             "duration_samples": 4096, "vel": 0.5, "seed": 17, "voice_mode": "samples"}
    sample_a = _note_signal(dict(event), 8000)
    sample_b = _note_signal(dict(event), 8000)
    synth = _note_signal({**event, "voice_mode": "synth"}, 8000)
    assert np.array_equal(sample_a, sample_b)
    assert np.isfinite(sample_a).all() and np.any(sample_a)
    assert not np.array_equal(sample_a, synth)
