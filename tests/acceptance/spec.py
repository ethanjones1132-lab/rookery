"""Numbers shared by the acceptance tests. See docs/audit/acceptance-api.md."""
import numpy as np

SR = 44100
CHECKS = (
    "length_exact",
    "no_clipping",
    "loudness",
    "seam_click",
    "not_silent",
    "deterministic",
)
FACTORY = (
    "kick_boom",
    "808",
    "snare_crack",
    "clap",
    "hat_closed",
    "hat_open",
    "rim",
    "perc",
)


def expected_samples(bars, bpm, sr=SR):
    return round(bars * 4 * 60 / bpm * sr)


def empty_project(bpm=90, bars=4, swing=0.0, name="length"):
    return {
        "schema": "rookery.project/1",
        "name": name,
        "bpm": bpm,
        "bars": bars,
        "steps_per_bar": 16,
        "swing": swing,
        "seed": 1337,
        "tracks": [],
        "master": {"fx": []},
    }


def dc(n, amp):
    return np.full((n, 2), np.float32(amp), dtype=np.float32)


def tiled(pattern, n):
    if len(pattern) >= n:
        return pattern[:n]
    reps = (n + len(pattern) - 1) // len(pattern)
    return (pattern * reps)[:n]
