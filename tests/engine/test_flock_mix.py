"""Flock mix controls, multi-bird polyphony, and a real call melody."""

from __future__ import annotations

import pytest

from rookery.flock.model import (
    apply_flock_edit,
    default_flock,
    flock_diffs,
    state_lines,
    validate_flock,
)
from rookery.flock.synth import _plan


def _flock(perches=None, **overrides):
    value = default_flock()
    value.update({"key": "D", "scale": "dorian", "progression": ["i", "IV", "VII", "III"]})
    value["perches"] = perches or [None] * 6
    value.update(overrides)
    return value


def _perch(bird, song="A", **extra):
    return {"bird": bird, "song": song, "mute": False, "solo": False, **extra}


def _project(flock, bpm=90):
    return {"bpm": bpm, "bars": 4, "steps_per_bar": 16, "swing": 0.0,
            "seed": 31, "tracks": [], "flock": flock}


def test_perch_mix_validates_edits_diffs_and_state():
    flock = _flock([_perch("quill", gain_db=6, pan=-0.5), None, None, None, None, None])
    normalized = validate_flock(flock)
    assert normalized["perches"][0]["gain_db"] == 6
    assert normalized["perches"][0]["pan"] == -0.5

    with pytest.raises(ValueError):
        validate_flock(_flock([_perch("quill", gain_db=13)]))
    with pytest.raises(ValueError):
        validate_flock(_flock([_perch("quill", pan=1.5)]))

    before = validate_flock(flock)
    after = apply_flock_edit(before, {"action": "mix", "bird": "quill", "gain_db": -3, "pan": 0.25})
    assert after["perches"][0]["gain_db"] == -3
    assert after["perches"][0]["pan"] == 0.25
    diffs = flock_diffs(before, after, change="mix")
    assert any(item["change"] == "mix" and item["bird"] == "quill" for item in diffs)
    assert "-3dB" in "\n".join(state_lines(after))

    with pytest.raises(ValueError):
        apply_flock_edit(before, {"action": "mix", "bird": "quill"})
    with pytest.raises(ValueError):
        apply_flock_edit(before, {"action": "mix", "bird": "jinx", "gain_db": 3})


def test_keys_are_polyphonic_with_a_bass_on_the_wire():
    flock = _flock([_perch("bramble"), _perch("quill"), None, None, None, None])
    _, planned = _plan(_project(flock))
    keys = [event for event in planned if event["bird_id"] == "quill"]
    assert keys
    by_step = {}
    for event in keys:
        by_step.setdefault((event["bar"], event["step"]), set()).add(event["midi"])
    assert max(len(notes) for notes in by_step.values()) >= 3


def test_call_uses_passing_tones_without_pitch_collapse():
    flock = _flock([None, None, None, None, _perch("echo"), None])
    _, planned = _plan(_project(flock))
    call = [event for event in planned if event["bird_id"] == "echo"]
    assert len({event["midi"] for event in call}) >= 4
    longest = 1
    run = 1
    for previous, current in zip(call, call[1:]):
        run = run + 1 if previous["midi"] == current["midi"] else 1
        longest = max(longest, run)
    assert longest <= 2


def test_perch_gain_changes_the_planned_level():
    plain = _flock([None, None, None, _perch("glint"), None, None])
    loud = _flock([None, None, None, _perch("glint", gain_db=6), None, None])
    _, plain_events = _plan(_project(plain))
    _, loud_events = _plan(_project(loud))
    plain_gain = next(event["gain"] for event in plain_events if event["bird_id"] == "glint")
    loud_gain = next(event["gain"] for event in loud_events if event["bird_id"] == "glint")
    assert loud_gain > plain_gain * 1.9
