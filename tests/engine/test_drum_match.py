"""Factory drum voices must land inside the measured commercial sound cloud.

The target numbers in ``tools/drum_targets.json`` were measured from a local
reference pack with ``tools/drum_match.py``; no reference audio is stored or
needed here. Distances are robust z-scores (see ``rookery.kit.measure``): 0 is
the middle of the reference cloud, ~1.0 is a typical reference one-shot, and
the worst reference in the pack is ~2.6. New voices must stay below 1.45.
"""

import hashlib
import json
from pathlib import Path

import pytest
import numpy as np

from rookery.kit import FACTORY_NAMES, synthesize
from rookery.kit.measure import analyse, distance

ROOT = Path(__file__).resolve().parents[2]
TARGETS = json.loads((ROOT / "tools" / "drum_targets.json").read_text(encoding="utf-8"))
SAMPLE_RATE = 44100
THRESHOLD = 1.45

# Two matched voices per family: a crack/tight/bright option and a body/deep
# option. The first entry of a pair is the added or retuned voice that must
# sit inside the cloud.
MATCHED = {
    "kick": ("kick_punch", "kick_deep"),
    "snare": ("snare_snap", "snare_body"),
    "clap": ("clap_stack", "clap_body"),
    "hat_closed": ("hat_tight", "hat_bright"),
    "hat_open": ("hat_open_short", "hat_open_wash"),
    "808": ("808_round", "808_sub_clean"),
}

NEW_SOUNDS = (
    "kick_deep",
    "snare_snap",
    "clap_body",
    "hat_tight",
    "hat_bright",
    "hat_open_short",
    "808_round",
)

# The eight frozen legacy voices: bytes must never move.
LEGACY_SHA256 = {
    "kick_boom": "5da778918ea4f6ac911a0794dbcda2d4b77c37ad97da4b701c9c9e3549a7bf3c",
    "808": "e76327b70462856462e92796254a3648665aa674119e1b9954acb1b63c72570c",
    "snare_crack": "03bf07d65968ad31d24950be7ee43f461edd988d6fde6b1e8015e4f8ef9d6bfe",
    "clap": "bd858f8c0f75bd0e49235dccfe9202d6960a0957b65de2bdb96011bab4e88412",
    "hat_closed": "2b16211440a14cc659c605eb6fa89fceb04a3912dc231c8e48babe98b314c5c9",
    "hat_open": "a075c4c4fc0f6db364c70fab7a5328e1b43b89b2622cba65a8c58d747aa28c1e",
    "rim": "6a4ff31f9cc4c38b6ed248a6c931a15431f54068a55d675401db7b3e15ffcc2a",
    "perc": "f9a85ef7614391205b533e77ee553563035f9872a711f0210a50444634ec334b",
}


def test_new_voices_exist_and_render_deterministically():
    assert set(NEW_SOUNDS) <= set(FACTORY_NAMES)
    for name in sorted({voice for pair in MATCHED.values() for voice in pair}):
        assert name in FACTORY_NAMES
        first = synthesize(name, sr=16000, seed=71)
        second = synthesize(name, sr=16000, seed=71)
        assert first.dtype.name == "float32"
        assert first.shape == second.shape
        assert first.tobytes() == second.tobytes(), name
        assert np.isfinite(first).all(), name
        assert float(abs(first).max()) > 0.05, name
        assert float(abs(first).max()) <= 1.0, name


@pytest.mark.parametrize(
    ("family", "name"),
    [(family, name) for family, names in MATCHED.items() for name in names],
)
def test_matched_voice_sits_inside_the_reference_cloud(family, name):
    target = TARGETS["families"][family]
    audio = synthesize(name, sr=SAMPLE_RATE)
    stats = analyse(audio, SAMPLE_RATE, family)
    score = distance(stats, target, family)
    assert score <= THRESHOLD, (
        f"{name} is {score:.2f} robust-z from the {family} reference median "
        f"(threshold {THRESHOLD}); measured {stats}"
    )


def test_legacy_factory_voices_are_byte_frozen():
    for name, digest in LEGACY_SHA256.items():
        audio = synthesize(name, sr=16000, seed=1337)
        assert hashlib.sha256(audio.tobytes()).hexdigest() == digest, name
