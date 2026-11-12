"""Catchiness metrics for every Flock song (the hook research, section 3b)."""

from __future__ import annotations

import json
import re
from pathlib import Path

from rookery.flock.model import default_flock, load_catalog
from rookery.flock.synth import _resolve_midi

CATALOG = load_catalog()
BIRDS = {bird["id"]: bird for bird in CATALOG["birds"]}
REFERENCE = {**default_flock(), "key": "D", "scale": "dorian",
             "progression": ["i", "IV", "VII", "III"]}
MELODIC_ROLES = {"lead", "call", "keys"}


def _songs():
    for bird in CATALOG["birds"]:
        for song, events in bird["songs"].items():
            yield bird, song, events
    for bird_id, songs in CATALOG["comboSongs"].items():
        for song, events in songs.items():
            yield BIRDS[bird_id], song, events


def _first_half(events, bar):
    return sorted(event["step"] for event in events
                  if event["bar"] == bar and event["step"] < 8)


def _bar_signature(events, bar):
    return tuple(sorted((event["step"], event["deg"], event["len"],
                         event.get("oct", 0)) for event in events if event["bar"] == bar))


def _share_offbeat(events):
    assert events
    return sum(event["step"] % 4 != 0 for event in events) / len(events)


def _motif_midi(role, events):
    bar = sorted((event for event in events if event["bar"] == 0),
                 key=lambda event: event["step"])
    return [_resolve_midi(REFERENCE, role, event["deg"], event.get("oct", 0), 0)
            for event in bar]


def test_every_song_has_an_aaba_hook_with_a_short_motif():
    for bird, song, events in _songs():
        role = bird["role"]
        if role not in MELODIC_ROLES:
            continue
        label = f"{bird['id']} {song}"
        # R2/R10: bars 0, 1 and 3 share their first-half onset rhythm, and the
        # first two bars are the same statement.
        assert _first_half(events, 0) == _first_half(events, 1) == _first_half(events, 3), label
        assert _bar_signature(events, 0) == _bar_signature(events, 1), label
        # R5: 3-6 notes in the motif.
        assert 3 <= sum(event["bar"] == 0 for event in events) <= 6, label
        # R6: medium syncopation plus an anchor in both two-bar halves.
        assert 0.35 <= _share_offbeat(events) <= 0.65, label
        for first_bar in (0, 2):
            anchors = {event["step"] for event in events
                       if event["bar"] in (first_bar, first_bar + 1)
                       and event["step"] in (0, 8)}
            assert anchors, label


def test_lead_and_call_motifs_leap_and_own_their_half_of_the_bar():
    for bird, song, events in _songs():
        role = bird["role"]
        if role not in {"lead", "call"}:
            continue
        label = f"{bird['id']} {song}"
        midi = _motif_midi(role, events)
        leaps = [abs(right - left) for left, right in zip(midi, midi[1:])]
        assert leaps and max(leaps) >= 3, (label, midi)
        first = min(event["step"] for event in events if event["bar"] == 0)
        if role == "lead":
            assert 0 <= first <= 7, (label, first)
        else:
            assert 8 <= first <= 15, (label, first)


def test_templates_use_their_scale_degrees_and_hook_research_feel():
    qualities = {3: "minor", 4: "major", 2: "diminished"}
    for template in CATALOG["templates"]:
        label = template["id"]
        assert 0 <= template["swing"] <= 0.5, label
        low, high = template["bpm_range"]
        assert low <= template["bpm"] <= high, label
        scale = CATALOG["scales"][template["scale"]]["semitones"]
        for chord in template["progression"]:
            degree = CATALOG["chordTables"]["romanDegrees"][chord]
            third = (scale[(degree + 2) % len(scale)] - scale[degree]) % 12
            expected = "diminished" if chord in {"vii", "vii°"} else (
                "minor" if chord.islower() else "major")
            assert qualities[third] == expected, (label, chord, third)


def test_dev_flock_birds_js_matches_the_engine_catalog():
    js_path = Path(__file__).resolve().parents[2] / "dev" / "flock" / "birds.js"
    text = js_path.read_text(encoding="utf-8")
    chunks = re.findall(r"^export const (\w+) = (.*?)(?=\n\nexport const |\Z)",
                        text, flags=re.S | re.M)
    exported = {name: json.loads(body) for name, body in chunks}
    assert exported == {key: CATALOG[key] for key in exported}
