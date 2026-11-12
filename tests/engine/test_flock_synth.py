"""Event planning, synthesis behavior, and frozen legacy compatibility for Flock."""

from __future__ import annotations

import hashlib
import json
import math
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from rookery.checks import check_audio
from rookery.flock.model import apply_flock_edit, default_flock
from rookery.flock.synth import (
    _CATALOG,
    _ROLE_SETTINGS,
    _VOICE_SAMPLE_CACHE,
    _sample_note_signal,
    _duck_envelope,
    _note_signal,
    _plan,
    _resolve_midi,
    _voice_release_samples,
    _weather,
    compile_events,
    render_flock,
)
from rookery.flock import synth as flock_synth
from rookery.project import canonical_project, project_hash
from rookery.render import RENDERER_VERSION, render_audio, wav_bytes


_KEYS = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
_KEY_PC = {key: i for i, key in enumerate(_KEYS)}
_ROLE_BIRDS = {bird["id"]: bird for bird in [*_CATALOG["birds"], _CATALOG["corvus"]]}
_FROZEN_RENDERER_PREFIX = "rookery-render-2;cyclic-hp;per-track-fx;bar-tail;"
_BASELINE_RENDERER_VERSION = (
    _FROZEN_RENDERER_PREFIX
    + "numpy=2.4.3;scipy=1.17.1;pedalboard=0.9.26;soundfile=0.14.0;pyloudnorm=0.2.0"
)
# Canonical-hash baselines proven on both supported Hermes environments.
_LEGACY_HASH_BY_ENV = {
    "numpy=2.4.3;scipy=1.17.1;pedalboard=0.9.26;soundfile=0.14.0;pyloudnorm=0.2.0":
        "f6db078920ac9b4b0f58ccb42fc212b3998e59a24ed080a37e67380b6dda2d75",
    "numpy=2.5.4;scipy=1.18.1;pedalboard=0.9.26;soundfile=0.14.0;pyloudnorm=0.2.0":
        "889d3c91b7768e1e7deb6dc797e0bea03c244b6fa17eb75045b3ad4e37ed1cb7",
}
_LEGACY_CANONICAL = (
    '{"bars":4,"bpm":90,"master":{"fx":[]},"schema":"rookery.project/1","seed":1337,'
    '"steps_per_bar":16,"swing":0.25,"tracks":[{"fx":[],"gain_db":0,"id":"kick","kind":"drum",'
    '"mute":false,"pan":0,"pitch":0,"solo":false,"source":"factory:kick_boom",'
    '"steps":"x.....x...x.....x.....x...x.....x.....x...x.....x.....x...x.....",'
    '"velocity":[1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1]},'
    '{"fx":[],"gain_db":0,"id":"snare","kind":"drum","mute":false,"pan":0,"pitch":0,'
    '"solo":false,"source":"factory:snare_crack","steps":"....x.......x.......x.......x.......x.......x.......x.......x...",'
    '"velocity":[0.9,0.9,0.9,0.9,0.9,0.9,0.9,0.9,0.9,0.9,0.9,0.9,0.9,0.9,0.9,0.9,0.9,0.9,0.9,0.9,0.9,0.9,0.9,0.9,0.9,0.9,0.9,0.9,0.9,0.9,0.9,0.9,0.9,0.9,0.9,0.9,0.9,0.9,0.9,0.9,0.9,0.9,0.9,0.9,0.9,0.9,0.9,0.9,0.9,0.9,0.9,0.9,0.9,0.9,0.9,0.9,0.9,0.9,0.9,0.9,0.9,0.9,0.9,0.9]},'
    '{"choke_group":"hats","fx":[],"gain_db":0,"id":"hat","kind":"drum","mute":false,"pan":0,'
    '"pitch":0,"solo":false,"source":"factory:hat_closed",'
    '"steps":"x.x.x.x.x.x.x.x.x.x.x.x.x.x.x.x.x.x.x.x.x.x.x.x.x.x.x.x.x.x.x.x.",'
    '"velocity":[1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1]}]}'
)
_LEGACY_PROJECT = {
    "schema": "rookery.project/1", "name": "legacy-flockless", "bpm": 90, "bars": 4,
    "steps_per_bar": 16, "swing": 0.25, "seed": 1337,
    "tracks": [
        {"id": "kick", "kind": "drum", "source": "factory:kick_boom", "steps": "x.....x...x.....", "velocity": [1.0]},
        {"id": "snare", "kind": "drum", "source": "factory:snare_crack", "steps": "....x.......x...", "velocity": [0.9]},
        {"id": "hat", "kind": "drum", "source": "factory:hat_closed", "steps": "x.x.x.x.x.x.x.x.",
         "velocity": [1.0], "choke_group": "hats"},
    ],
}


def _project(*, flock=None, tracks=None, key="D", scale="dorian", seed=1337, bpm=90, swing=0.25, bars=4):
    value = {
        "schema": "rookery.project/1", "name": "flock-test", "bpm": bpm, "bars": bars,
        "steps_per_bar": 16, "swing": swing, "seed": seed, "tracks": tracks or [],
    }
    if flock is not None:
        value["flock"] = {**default_flock(), "key": key, "scale": scale, **flock}
    return value


def _perches(*birds):
    result = [None] * 6
    for index, item in enumerate(birds):
        if isinstance(item, str):
            item = {"bird": item, "song": "A"}
        result[index] = {"bird": item["bird"], "song": item.get("song", "A"),
                         "mute": item.get("mute", False), "solo": item.get("solo", False)}
    return result


def _perches7(*birds):
    result = [None] * 7
    ordinary_slot = 0
    for item in birds:
        if isinstance(item, str):
            item = {"bird": item, "song": "A"}
        slot = 6 if item["bird"] == "corvus" else ordinary_slot
        if item["bird"] != "corvus":
            ordinary_slot += 1
        result[slot] = {"bird": item["bird"], "song": item.get("song", "A"),
                        "mute": item.get("mute", False), "solo": item.get("solo", False)}
    return result


def _reference_duck_envelope(total, sample_rate, onsets):
    """Original full-length implementation, retained as a bit-exact oracle."""
    envelope = np.ones(total, dtype=np.float64)
    if not onsets:
        return envelope
    duck = 10.0 ** (-3.0 / 20.0)
    attack = max(1, round(sample_rate * 0.002))
    release = max(1, round(sample_rate * 0.08))
    samples = np.arange(total, dtype=np.int64)
    for onset in onsets:
        distance = (samples - int(onset)) % total
        curve = np.ones(total, dtype=np.float64)
        attacking = distance < attack
        curve[attacking] = 1.0 - (1.0 - duck) * distance[attacking] / attack
        releasing = ~attacking
        elapsed = distance[releasing] - attack
        curve[releasing] = duck + (1.0 - duck) * (1.0 - np.exp(-elapsed / release))
        envelope = np.minimum(envelope, curve)
    return envelope


@pytest.mark.parametrize("timeline,total", [("cyclic", 16_000), ("song", 64_000)])
def test_duck_envelope_window_is_bit_exact_for_random_onsets(timeline, total):
    rng = np.random.default_rng(613 + total)
    for count in (0, 1, 5, 19):
        onsets = rng.integers(-200, total + 200, size=count).tolist()
        if count > 2:
            onsets[-1] = onsets[0]
        if timeline == "song":
            onsets.extend((total - 1, total - 12_345))
        assert np.array_equal(
            _duck_envelope(total, 8_000, onsets),
            _reference_duck_envelope(total, 8_000, onsets),
        ), timeline


def _assert_project_events_in_key(project):
    metadata = compile_events(project)
    semitones = set(_CATALOG["scales"][project["flock"]["scale"]]["semitones"])
    root = _KEY_PC[project["flock"]["key"]]
    for bird_id, events in metadata["flock_events"].items():
        role = _ROLE_BIRDS[bird_id]["role"]
        low, high = _CATALOG["registers"][role]
        for event in events:
            assert isinstance(event["midi"], int)
            assert low <= event["midi"] <= high
            assert (event["midi"] - root) % 12 in semitones
            assert math.isfinite(event["vel"]) and event["vel"] > 0
            assert event["len"] > 0 and event["t"] >= 0
    return metadata


def test_all_bird_songs_stay_in_key_and_role_register_for_every_key_and_scale():
    for key in _KEYS:
        for scale in _CATALOG["scales"]:
            for bird in _CATALOG["birds"]:
                for song in ("A", "B", "C"):
                    project = _project(key=key, scale=scale, flock={"perches": _perches({"bird": bird["id"], "song": song})})
                    metadata = _assert_project_events_in_key(project)
                    assert metadata["flock_events"][bird["id"]]


def test_every_catalog_song_keeps_strong_steps_on_chord_tones():
    for bird in _CATALOG["birds"]:
        for events in bird["songs"].values():
            for event in events:
                if event["step"] % 4 == 0:
                    assert event["deg"] in {0, 2, 4, 6}
    # Quill D's added ninth is a weak-step colour tone, so strong steps stay on chord tones.
    quill_d = _CATALOG["comboSongs"]["quill"]["D"]
    ninth = [event for event in quill_d if event["deg"] == 1]
    assert any(event["step"] % 4 != 0 and event["len"] == 3 for event in ninth)


def test_combo_d_songs_are_available_only_with_their_active_catalog_combo():
    requirements = {
        "echo": ("hush", "sable", "echo"),
        "glint": ("cinder", "glint", "jinx"),
        "quill": ("quill", "moss"),
    }
    for key in _KEYS:
        for scale, scale_data in _CATALOG["scales"].items():
            for bird_id, required in requirements.items():
                if bird_id == "echo" and scale_data["family"] != "minor":
                    continue
                perches = _perches(*[
                    {"bird": bird, "song": "D" if bird == bird_id else "A"} for bird in required
                ])
                flock = {**default_flock(), "key": key, "scale": scale, "perches": perches,
                         "weather": "rain" if bird_id == "quill" else "clear"}
                project = _project(key=key, scale=scale, flock=flock)
                metadata = _assert_project_events_in_key(project)
                assert bird_id in metadata["flock_events"]
                assert metadata["flock_active_combos"]


def test_templates_and_progressions_plan_in_key_and_register():
    for template in _CATALOG["templates"]:
        flock = apply_flock_edit(None, {"action": "template", "template": template["id"]})
        project = _project(flock=flock)
        metadata = _assert_project_events_in_key(project)
        assert metadata["flock_events"]
        assert len(flock["progression"]) in range(1, 9)


def test_every_roman_chord_progression_stays_in_key_and_register():
    roman = list(_CATALOG["chordTables"]["romanDegrees"])
    progressions = [roman[index:index + 8] for index in range(0, len(roman), 8)]
    six_roles = _perches("bramble", "quill", "hush", "jinx", "tick", "echo")
    for key in _KEYS:
        for scale in _CATALOG["scales"]:
            for progression in progressions:
                project = _project(key=key, scale=scale,
                                   flock={"progression": progression, "perches": six_roles})
                metadata = _assert_project_events_in_key(project)
                assert metadata["flock_events"]


def test_no_flock_metadata_is_empty_but_kicks_still_use_actual_audible_timing():
    tracks = [
        {"id": "not_the_kick_id", "kind": "drum", "source": "factory:kick_boom",
         "steps": "xx..", "velocity": [1.0, 0.4, 0.0, 0.0]},
        {"id": "muted", "kind": "drum", "source": "factory:kick_boom", "steps": "x", "mute": True},
    ]
    project = _project(tracks=tracks, bpm=93, swing=0.8)
    metadata = compile_events(project)
    assert metadata["flock_events"] == {}
    assert metadata["flock_active_combos"] == []
    total = round(4 * 4 * 60 / 93 * 44100)
    step_len = total / 64
    expected = []
    for index in range(64):
        if index % 4 not in (0, 1):
            continue
        start = round(index * step_len)
        if index % 2:
            start = (start + round(0.8 * step_len * 0.5)) % total
        expected.append(start / 44100)
    assert metadata["kick_onsets"] == expected
    soloed = _project(tracks=tracks + [{"id": "snare-solo", "kind": "drum", "source": "factory:snare_crack",
                                       "steps": "x", "solo": True}])
    assert compile_events(soloed)["kick_onsets"] == []


def test_swing_matches_old_renderer_sample_rounding_for_flock_and_kicks():
    project = _project(flock={"perches": _perches({"bird": "quill", "song": "B"})},
                       tracks=[{"id": "drum", "kind": "drum", "source": "factory:kick_boom", "steps": ".x"}],
                       bpm=93, swing=0.8)
    metadata = compile_events(project)
    total = round(4 * 4 * 60 / 93 * 44100)
    step_len = total / 64
    first_kick = round(step_len) + round(0.8 * step_len * 0.5)
    assert metadata["kick_onsets"][0] == first_kick / 44100
    swung_step_three = round(3 * step_len) + round(0.8 * step_len * 0.5)
    quill_events = metadata["flock_events"]["quill"]
    assert any(event["t"] == swung_step_three / 44100 for event in quill_events)
    # Keys now own off-beat slots only; the first attack is the swung pickup.
    assert quill_events[0]["t"] == swung_step_three / 44100


def test_mute_solo_and_zero_velocity_never_create_phantom_notes():
    flock = {**default_flock(), "perches": _perches(
        {"bird": "bramble", "mute": True}, {"bird": "cinder"}, {"bird": "quill", "solo": True})}
    metadata = compile_events(_project(flock=flock))
    assert set(metadata["flock_events"]) == {"quill"}
    assert all(note["vel"] > 0 for notes in metadata["flock_events"].values() for note in notes)


def test_role_mix_uses_documented_gain_pan_and_second_bird_attenuation():
    project = _project(flock={"perches": _perches("quill", "sable")})
    _, events = _plan(project)
    first = next(event for event in events if event["bird_id"] == "quill")
    second = next(event for event in events if event["bird_id"] == "sable")
    assert first["gain"] == pytest.approx(10 ** (_ROLE_SETTINGS["keys"][0] / 20))
    assert second["gain"] == pytest.approx(first["gain"] * 10 ** (-2 / 20))
    assert first["pan"] == -0.25 and second["pan"] == 0.25


def test_bass_duck_has_fast_attack_release_and_wraps_across_loop_boundary():
    sr, total = 8000, 8000
    onset = total - 100
    envelope = _duck_envelope(total, sr, [onset])
    assert envelope[onset] == 1.0
    assert envelope[onset + 16] == pytest.approx(10 ** (-3 / 20), abs=0.002)
    assert envelope[0] < 0.8
    assert envelope[round(0.04 * sr)] > envelope[0]
    assert envelope[round(0.25 * sr)] > 0.98


def test_weather_is_seeded_stereo_and_clear_is_exact_zero():
    clear = {**default_flock(), "weather": "clear"}
    dust = {**default_flock(), "weather": "dust"}
    rain = {**default_flock(), "weather": "rain"}
    wind = {**default_flock(), "weather": "wind"}
    assert not np.any(_weather(_project(), clear, 8000, 64000))
    first = _weather(_project(seed=17), dust, 8000, 64000)
    repeat = _weather(_project(seed=17), dust, 8000, 64000)
    other_seed = _weather(_project(seed=18), dust, 8000, 64000)
    assert first.shape == (64000, 2)
    assert np.array_equal(first, repeat)
    assert not np.array_equal(first, other_seed)
    assert np.any(_weather(_project(), rain, 8000, 64000))
    assert np.any(_weather(_project(), wind, 8000, 64000))


def test_twelve_catalog_voice_variants_produce_distinct_signals():
    signals = []
    for bird in _CATALOG["birds"]:
        signal = _note_signal({"voice": bird["voice"], "role": bird["role"], "midi": 60,
                               "duration_samples": 2048, "vel": 0.5, "seed": 1234}, 8000)
        assert np.isfinite(signal).all()
        signals.append(signal)
    assert len({hashlib.sha256(signal.tobytes()).hexdigest() for signal in signals}) == 12


def test_seed_changes_event_velocity_and_flock_audio_without_global_rng():
    flock = {"perches": _perches({"bird": "bramble", "song": "B"})}
    first = _project(flock=flock, seed=7)
    second = _project(flock=flock, seed=8)
    assert compile_events(first)["flock_events"] != compile_events(second)["flock_events"]
    audio_a, _ = render_flock(first, 8000)
    audio_b, _ = render_flock(second, 8000)
    assert np.any(audio_a)
    assert not np.array_equal(audio_a, audio_b)


def test_back_and_forth_and_two_basses_extra_layers_change_planned_notes():
    call = _project(flock={"perches": _perches("echo", "wren_not")})
    call_meta = compile_events(call)
    bar_seconds = 4 * 60 / call["bpm"]
    assert {int(event["t"] // bar_seconds) for event in call_meta["flock_events"]["echo"]} == {0, 2}
    assert {int(event["t"] // bar_seconds) for event in call_meta["flock_events"]["wren_not"]} == {1, 3}
    assert "back_and_forth" in call_meta["flock_active_combos"]

    bass = _project(key="C", scale="major", flock={"progression": ["I"], "perches": _perches(
        {"bird": "bramble", "song": "B"}, {"bird": "cinder", "song": "B"})})
    bass_meta, planned = _plan(bass)
    regular = [event for event in planned if event["bird_id"] in {"bramble", "cinder"}
               and event["layer"].startswith("song:")]
    assert all((event["bird_id"] == "bramble") == (event["bar"] % 2 == 0)
               for event in regular if event["bar"] < 3)
    assert any(event["layer"] == "sub_octave_drop" and 28 <= event["midi"] <= 48 for event in planned)
    assert "two_basses" in bass_meta["flock_active_combos"]


def test_combo_song_overrides_and_extra_layers_are_audible():
    shiny = _project(flock={"perches": _perches("cinder", "glint", "jinx")})
    shiny_meta, shiny_plan = _plan(shiny)
    assert "shiny_things" in shiny_meta["flock_active_combos"]
    assert any(event["bird_id"] == "glint" and event["layer"] == "bell_sparkle" for event in shiny_plan)
    assert {event["voice"] for event in shiny_plan if event["bird_id"] == "glint"} >= {"bell"}

    parliament = _project(flock={"perches": _perches("bramble", "quill", "hush", "jinx", "tick", "echo")})
    parliament_meta, parliament_plan = _plan(parliament)
    assert "parliament" in parliament_meta["flock_active_combos"]
    assert any(event["layer"] == "harmony_chorus" and event["role"] == "call" for event in parliament_plan)
    assert any(event["layer"] == "auto_seventh" for event in parliament_plan)

    lo_fi = _project(flock={"weather": "rain", "perches": _perches("quill", "moss")})
    lo_fi_meta, lo_fi_plan = _plan(lo_fi)
    assert "lo_fi_window" in lo_fi_meta["flock_active_combos"]
    assert any(event["bird_id"] == "quill" and event["layer"].startswith("song:D:") for event in lo_fi_plan)
    lo_fi_flock = lo_fi["flock"]
    quill_seventh = _resolve_midi(lo_fi_flock, "keys", 6, 0, 0)
    assert any(event["bird_id"] == "quill" and event["midi"] == quill_seventh
               for event in lo_fi_plan)


def test_integration_catalog_combo_overrides_and_extra_layers_change_pcm(monkeypatch):
    import rookery.flock.synth as synth

    cases = [
        ("night_shift", _project(scale="minor", flock={"perches": _perches("hush", "sable", "echo")})),
        ("shiny_things", _project(flock={"perches": _perches("cinder", "glint", "jinx")})),
        ("lo_fi_window", _project(flock={"weather": "rain", "perches": _perches("quill", "moss")})),
    ]
    for combo_id, project in cases:
        with_bonus, _ = render_flock(project, 8000)
        song_overrides = synth._COMBOS[combo_id]["bonus"].get("song_overrides")
        if song_overrides:
            monkeypatch.setitem(synth._COMBOS[combo_id]["bonus"], "song_overrides", {})
            without_override, _ = render_flock(project, 8000)
            assert not np.array_equal(with_bonus, without_override), combo_id
            monkeypatch.setitem(synth._COMBOS[combo_id]["bonus"], "song_overrides", song_overrides)

    for combo_id, project in [
        ("parliament", _project(flock={"perches": _perches("bramble", "quill", "hush", "jinx", "tick", "echo")})),
        ("shiny_things", _project(flock={"perches": _perches("cinder", "glint", "jinx")})),
        ("two_basses", _project(key="C", scale="major", flock={"progression": ["I"],
                                                                    "perches": _perches("bramble", "cinder")})),
        ("back_and_forth", _project(flock={"perches": _perches("echo", "wren_not")})),
    ]:
        with_bonus, _ = render_flock(project, 8000)
        layer = synth._COMBOS[combo_id]["bonus"].get("extra_layer")
        monkeypatch.setitem(synth._COMBOS[combo_id]["bonus"], "extra_layer", None)
        without_layer, _ = render_flock(project, 8000)
        assert layer and not np.array_equal(with_bonus, without_layer), combo_id
        monkeypatch.setitem(synth._COMBOS[combo_id]["bonus"], "extra_layer", layer)


def test_flock_render_is_audible_when_unmuted_and_exact_silence_when_muted():
    audible = _project(flock={"perches": _perches("bramble")}, bpm=120)
    muted = _project(flock={"perches": _perches({"bird": "bramble", "mute": True})}, bpm=120)
    audio, metadata = render_flock(audible, 8000)
    silence, muted_metadata = render_flock(muted, 8000)
    assert audio.dtype == np.float32 and audio.shape == (64000, 2)
    assert np.any(audio)
    assert metadata["flock_events"]["bramble"]
    assert metadata == compile_events(audible, 8000)
    assert not np.any(silence)
    assert muted_metadata["flock_events"] == {}


def test_legacy_flockless_project_keeps_frozen_canonical_hash_and_pcm_bytes():
    assert canonical_project(_LEGACY_PROJECT) == _LEGACY_CANONICAL
    assert RENDERER_VERSION.startswith(_FROZEN_RENDERER_PREFIX), (
        "the frozen legacy canonical hash assumes the documented renderer phases; "
        f"update the baseline for {RENDERER_VERSION!r}"
    )
    expected_wav_sha256 = "a550f7638ec60c3740a507ce46834b1da9347029f6c6bddd97751841f269c1fd"
    env_suffix = RENDERER_VERSION[len(_FROZEN_RENDERER_PREFIX):]
    known_hash = _LEGACY_HASH_BY_ENV.get(env_suffix)
    if known_hash is None:
        raise AssertionError(
            "unrecognized renderer environment for the frozen legacy canonical hash; "
            f"record a new baseline for {env_suffix!r} instead of skipping"
        )
    computed_hash = hashlib.sha256(
        (_LEGACY_CANONICAL + RENDERER_VERSION).encode("utf-8")
    ).hexdigest()
    assert computed_hash == known_hash
    assert project_hash(_LEGACY_PROJECT, RENDERER_VERSION) == known_hash
    audio, _ = render_audio(_LEGACY_PROJECT)
    actual_wav = wav_bytes(audio, 44100, "PCM_24")
    assert hashlib.sha256(actual_wav).hexdigest() == expected_wav_sha256


def test_render_audio_tuple_stays_stable_and_render_project_exposes_planner_metadata(monkeypatch):
    import rookery.render as renderer

    project = _project()
    result = render_audio(project, 8000)
    assert isinstance(result, tuple) and len(result) == 2
    metadata = {"flock_events": {}, "kick_onsets": [0.0], "flock_active_combos": []}
    monkeypatch.setattr(renderer, "_render_audio_with_metadata",
                        lambda *_args, **_kwargs: (np.zeros((8, 2), dtype=np.float32), {}, metadata))
    with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[2]) as directory:
        rendered = renderer.render_project(project, directory)
        assert rendered["flock_events"] == {}
        assert rendered["kick_onsets"] == [0.0]
        assert rendered["flock_active_combos"] == []


def test_lead_voicing_stays_in_its_lane_and_glint_d_adds_a_pickup():
    harmony = {"key": "C", "scale": "major", "progression": ["I"]}
    low = _resolve_midi(harmony, "lead", 0, 0, 0)
    high = _resolve_midi(harmony, "lead", 0, 1, 0)
    lead_low, lead_high = _CATALOG["registers"]["lead"]
    assert all(lead_low <= note <= lead_high for note in (low, high))
    for role in ("arp", "pad"):
        low, high = (_resolve_midi(harmony, role, 4, octave, 0) for octave in (0, 1))
        role_low, role_high = _CATALOG["registers"][role]
        assert role_low <= low <= role_high, role
        assert role_low <= high <= role_high, role
        assert all(_CATALOG["registers"][role][0] <= note <= _CATALOG["registers"][role][1]
                   for note in (low, high))

    glint_a = _project(key="C", scale="major", flock={"progression": ["I"],
                                                      "perches": _perches({"bird": "glint", "song": "A"})})
    glint_d = _project(key="C", scale="major", flock={"progression": ["I"],
                                                      "perches": _perches("cinder", "glint", "jinx")})
    _, planned_a = _plan(glint_a)
    _, planned_d = _plan(glint_d)
    midi_a = {event["midi"] for event in planned_a if event["bird_id"] == "glint"}
    midi_d = {event["midi"] for event in planned_d if event["bird_id"] == "glint"
              and event["layer"].startswith("song:D:")}
    assert len(midi_d) >= 3
    assert midi_a <= midi_d
    assert all(lead_low <= note <= lead_high for note in midi_a | midi_d)


def test_every_voice_has_exact_zero_edges_and_public_length_matches_signal():
    for bird in _CATALOG["birds"]:
        voice = bird["voice"]
        signal = _note_signal({"voice": voice, "role": bird["role"], "midi": 60,
                               "duration_samples": 2048, "vel": 0.5, "seed": 1234}, 8000)
        assert abs(float(signal[0])) < 1e-12, voice
        assert abs(float(signal[-1])) < 1e-12, voice
        assert len(signal) == 2048 + _voice_release_samples(voice, 8000)
        peak = float(np.max(np.abs(signal)))
        assert abs(float(signal[-1] - signal[-2])) <= max(1e-6, 0.05 * peak), voice

    project = _project(flock={"perches": _perches("quill", "hush")})
    metadata, planned = _plan(project, 8000)
    for bird_id, entries in metadata["flock_events"].items():
        ordered = [event for event in planned
                   if event["bird_id"] == bird_id and not event.get("skip_dsp")]
        assert len(entries) == len(ordered)
        for entry, event in zip(entries, ordered):
            rendered_frames = len(_note_signal(event, 8000))
            assert round(entry["len"] * 8000) == rendered_frames


def test_pads_render_decorrelated_wide_stereo_with_low_frequency_control():
    for bird_id in ("hush", "moss"):
        project = _project(key="C", scale="major", bpm=120,
                           flock={"progression": ["I"], "perches": _perches(bird_id)})
        audio, _ = render_flock(project, 8000)
        left, right = audio[:, 0].astype(np.float64), audio[:, 1].astype(np.float64)
        assert np.any(left) and np.any(right)
        gain = float(np.dot(left, right) / max(np.dot(right, right), 1e-12))
        residual = np.linalg.norm(left - gain * right) / max(np.linalg.norm(left), 1e-12)
        assert residual > 0.25, bird_id
        assert abs(float(np.corrcoef(left, right)[0, 1])) < 0.8, bird_id
        _, planned = _plan(project, 8000)
        pad_notes = [(event["bar"], event["step"], event["midi"]) for event in planned
                     if event["role"] == "pad"]
        assert len(pad_notes) == len(set(pad_notes)), bird_id

    hush = _note_signal({"voice": "softPad", "role": "pad", "midi": 60,
                         "duration_samples": 16000, "vel": 0.5, "seed": 1234}, 8000)
    spectrum = np.abs(np.fft.rfft(hush)) ** 2
    frequencies = np.fft.rfftfreq(len(hush), 1.0 / 8000)
    assert spectrum[frequencies < 150.0].sum() / spectrum.sum() < 0.01

    moss = _note_signal({"voice": "triangleChoir", "role": "pad", "midi": 60,
                         "duration_samples": 16000, "vel": 0.5, "seed": 1234}, 8000)
    def high_ratio(segment):
        local = np.abs(np.fft.rfft(segment)) ** 2
        local_freq = np.fft.rfftfreq(len(segment), 1.0 / 8000)
        return local[local_freq > 1200.0].sum() / local.sum()
    assert high_ratio(moss[10000:14000]) > 2.0 * high_ratio(moss[1000:5000])


def test_sampled_pad_high_pass_reduces_sub_120_hz_energy(tmp_path, monkeypatch):
    sample_rate = 8000
    bird_id = "hush"
    folder = tmp_path / bird_id
    folder.mkdir()
    time = np.arange(sample_rate, dtype=np.float64) / sample_rate
    source = 0.7 * np.sin(2 * np.pi * 65 * time) + 0.3 * np.sin(2 * np.pi * 260 * time)
    sf.write(folder / "48.flac", source, sample_rate, subtype="PCM_24")
    monkeypatch.setattr(flock_synth, "_VOICE_SAMPLE_ROOT", tmp_path)
    _VOICE_SAMPLE_CACHE.clear()
    event = {"bird_id": bird_id, "role": "pad", "midi": 48, "vel": 1.0}
    filtered = _sample_note_signal(event, sample_rate, sample_rate, sample_rate, 0)
    real_filter = flock_synth.lfilter
    monkeypatch.setattr(flock_synth, "lfilter", lambda _b, _a, signal: signal)
    unfiltered = _sample_note_signal(event, sample_rate, sample_rate, sample_rate, 0)

    def low_band_energy(signal):
        spectrum = np.abs(np.fft.rfft(signal)) ** 2
        frequencies = np.fft.rfftfreq(len(signal), 1.0 / sample_rate)
        return float(spectrum[frequencies < 120.0].sum())

    assert low_band_energy(filtered) < low_band_energy(unfiltered) * 0.2
    monkeypatch.setattr(flock_synth, "lfilter", real_filter)
    _VOICE_SAMPLE_CACHE.clear()


def test_keys_and_pads_voice_triads_and_sevenths_while_pentatonic_stays_clean():
    for scale in ("major", "dorian", "minor"):
        for bird_id in ("quill", "hush", "moss"):
            role = _ROLE_BIRDS[bird_id]["role"]
            project = _project(key="C", scale=scale,
                               flock={"progression": ["I"], "perches": _perches(bird_id)})
            flock = {**project["flock"], "progression": ["I"]}
            _, planned = _plan(project)
            bar_zero = [event for event in planned if event["bar"] == 0 and event["role"] == role]
            present = {event["midi"] for event in bar_zero}
            triad = {_resolve_midi(flock, role, degree, 0, 0) for degree in (0, 2, 4)}
            seventh = _resolve_midi(flock, role, 6, 0, 0)
            assert triad <= present, (scale, bird_id)
            assert len(triad) == 3
            assert seventh in present

    for key in _KEYS:
        project = _project(key=key, scale="minor_pent",
                           flock={"progression": ["i"], "perches": _perches("quill", "hush")})
        _, planned = _plan(project)
        assert not any(event["layer"] == "auto_seventh" for event in planned)
        _assert_project_events_in_key(project)

    # The Lo-Fi Window D song deliberately adds the ninth even in a pentatonic scale.
    lo_fi = _project(key="C", scale="minor_pent",
                     flock={"progression": ["i"], "weather": "rain",
                            "perches": _perches("quill", "moss")})
    flock = {**lo_fi["flock"], "progression": ["i"]}
    ninth = _resolve_midi(flock, "keys", 1, 1, 0)
    _, planned = _plan(lo_fi)
    assert any(event["bird_id"] == "quill" and event["midi"] == ninth
               and event["layer"].startswith("song:D:") for event in planned)
    assert _assert_project_events_in_key(lo_fi)["flock_events"]["quill"]

    # Two simultaneous pads share voiced chord tones; none are generated twice.
    pads = _project(key="C", scale="major",
                    flock={"progression": ["I"], "perches": _perches("hush", "moss")})
    _, planned = _plan(pads)
    generated = [(event["bar"], event["step"], event["midi"]) for event in planned
                 if event["layer"] in {"auto_chord_tone", "auto_seventh"}]
    assert len(generated) == len(set(generated))


def test_two_basses_sub_octave_drop_always_lands_in_key_and_low_range():
    roots = ("I", "II", "III", "IV", "V", "VI", "VII")
    for key in _KEYS:
        for scale, scale_data in _CATALOG["scales"].items():
            for root in roots:
                project = _project(key=key, scale=scale,
                                   flock={"progression": [root],
                                          "perches": _perches({"bird": "bramble", "song": "A"},
                                                              {"bird": "cinder", "song": "A"})})
                metadata, planned = _plan(project)
                assert "two_basses" in metadata["flock_active_combos"]
                subs = [event for event in planned if event["layer"] == "sub_octave_drop"]
                assert subs, (key, scale, root)
                sub = subs[-1]
                assert sub["bar"] == project["bars"] - 1
                assert 28 <= sub["midi"] <= 48
                assert (sub["midi"] - _KEY_PC[key]) % 12 in scale_data["semitones"]
                last_bar_notes = [event["midi"] for event in planned
                                  if event["bar"] == sub["bar"] and event["role"] == "bass"
                                  and event["layer"].startswith("song:")
                                  and not event.get("skip_dsp")]
                higher = max(last_bar_notes)
                if 28 <= higher - 12 <= 48:
                    assert sub["midi"] == higher - 12

    # C minor i with a low Cinder A used to leave the last bar without a sub gesture.
    c_minor = _project(key="C", scale="minor",
                       flock={"progression": ["i"],
                              "perches": _perches({"bird": "bramble", "song": "A"},
                                                  {"bird": "cinder", "song": "A"})})
    _, planned = _plan(c_minor)
    subs = [event for event in planned
            if event["layer"] == "sub_octave_drop" and event["bar"] == 3]
    assert subs and 28 <= subs[-1]["midi"] <= 48
    assert (subs[-1]["midi"] - _KEY_PC["C"]) % 12 in _CATALOG["scales"]["minor"]["semitones"]


def test_corvus_bus_drive_respects_active_perches_and_solo_filtering():
    seen = [bird["id"] for bird in _CATALOG["birds"]]

    def corvus_project(*birds):
        return _project(bpm=120, flock={"perches": _perches7(*birds), "seen": seen})

    plain = corvus_project("bramble")
    with_corvus = corvus_project("bramble", "corvus")
    driven, _ = render_flock(with_corvus, 8000)
    undriven, _ = render_flock(plain, 8000)
    assert not np.array_equal(driven, undriven)

    soloed = corvus_project({"bird": "bramble", "solo": True}, "corvus")
    soloed_plain = corvus_project({"bird": "bramble", "solo": True})
    assert np.array_equal(render_flock(soloed, 8000)[0], render_flock(soloed_plain, 8000)[0])

    muted = corvus_project("bramble", {"bird": "corvus", "mute": True})
    assert np.array_equal(render_flock(muted, 8000)[0], undriven)


def test_every_bird_song_under_every_template_harmony_plans_in_key():
    for template in _CATALOG["templates"]:
        harmony = apply_flock_edit(None, {"action": "template", "template": template["id"]})
        for bird in _CATALOG["birds"]:
            for song in ("A", "B", "C"):
                project = _project(
                    key=harmony["key"], scale=harmony["scale"],
                    flock={"progression": harmony["progression"],
                           "perches": _perches({"bird": bird["id"], "song": song})},
                )
                metadata = _assert_project_events_in_key(project)
                assert metadata["flock_events"][bird["id"]], (template["id"], bird["id"], song)


def test_combo_d_and_bonus_layers_stay_valid_for_every_key_and_scale():
    d_birds = {"night_shift": "echo", "shiny_things": "glint", "lo_fi_window": "quill"}

    def assert_planned_in_key(flock, planned):
        semitones = set(_CATALOG["scales"][flock["scale"]]["semitones"])
        root = _KEY_PC[flock["key"]]
        for event in planned:
            low, high = _CATALOG["registers"][event["role"]]
            assert low <= event["midi"] <= high, event
            assert (event["midi"] - root) % 12 in semitones, event
            assert math.isfinite(event["vel"]) and event["vel"] > 0

    cases = {
        "parliament": ("bramble", "quill", "hush", "jinx", "tick", "echo"),
        "back_and_forth": ("echo", "wren_not"),
        "shiny_things": ("cinder", "glint", "jinx"),
        "two_basses": ("bramble", "cinder"),
        "night_shift": ("hush", "sable", "echo"),
        "lo_fi_window": ("quill", "moss"),
    }
    for key in _KEYS:
        for scale, scale_data in _CATALOG["scales"].items():
            for combo_id, birds in cases.items():
                if combo_id == "night_shift" and scale_data["family"] != "minor":
                    continue
                project = _project(
                    key=key, scale=scale,
                    flock={"progression": ["I", "IV", "V", "I"],
                           "weather": "rain" if combo_id == "lo_fi_window" else "clear",
                           "perches": _perches(*birds)},
                )
                metadata, planned = _plan(project)
                assert combo_id in metadata["flock_active_combos"], (key, scale, combo_id)
                assert planned
                assert_planned_in_key(project["flock"], planned)
                layers = {event["layer"] for event in planned}
                if combo_id == "parliament":
                    assert "harmony_chorus" in layers
                elif combo_id == "shiny_things":
                    assert "bell_sparkle" in layers
                elif combo_id == "two_basses":
                    assert "sub_octave_drop" in layers
                elif combo_id == "back_and_forth":
                    assert {event["bar"] for event in planned if event["bird_id"] == "echo"} <= {0, 2}
                    assert {event["bar"] for event in planned if event["bird_id"] == "wren_not"} <= {1, 3}
                d_bird = d_birds.get(combo_id)
                if d_bird:
                    assert any(event["bird_id"] == d_bird and event["layer"].startswith("song:D:")
                               for event in planned), (key, scale, combo_id)


@pytest.mark.parametrize("weather", ["rain", "wind", "dust"])
def test_integration_weather_only_full_render_passes_all_six_checks(weather):
    flock = {**default_flock(), "weather": weather}
    project = _project(flock=flock, bpm=92, swing=0.25)
    first, _, _ = _render_audio_with_metadata(project)
    second, _, _ = _render_audio_with_metadata(project)
    assert wav_bytes(first) == wav_bytes(second)
    expected = round(project["bars"] * 4 * 60 / project["bpm"] * 44100)
    checks = check_audio(first, 44100, expected, deterministic=True)
    assert len(checks) == 6
    assert all(item["pass"] for item in checks.values()), (weather, checks)

    texture = _weather(project, flock, 8000, 64000)
    assert np.any(texture)
    assert np.max(np.abs(texture)) < 0.95
    assert not np.array_equal(texture[:, 0], texture[:, 1])
    edge_jump = np.abs(texture[0] - texture[-1])
    assert np.max(edge_jump) <= np.max(np.abs(np.diff(texture, axis=0)))
    if weather == "wind":
        frame_rms = np.sqrt(np.mean(texture[:32000].reshape(-1, 160, 2) ** 2, axis=(1, 2)))
        assert np.std(frame_rms) / np.mean(frame_rms) > 0.02


def test_integration_flock_render_is_deterministic_in_independent_processes():
    project = _project(flock={"perches": _perches("bramble", "quill")}, seed=721)
    source_root = Path(__file__).resolve().parents[2]
    script = r"""
import hashlib
import json
import sys
sys.path.insert(0, sys.argv[1])
from rookery.flock.synth import render_flock
project = json.loads(sys.argv[2])
audio, metadata = render_flock(project, 8000)
print(hashlib.sha256(audio.tobytes()).hexdigest())
print(json.dumps(metadata, sort_keys=True, separators=(",", ":")))
"""
    env_a, env_b = os.environ.copy(), os.environ.copy()
    env_a.pop("PYTHONPATH", None)
    env_b.pop("PYTHONPATH", None)
    env_a["PYTHONHASHSEED"], env_b["PYTHONHASHSEED"] = "0", "91"
    args = [sys.executable, "-c", script, str(source_root), json.dumps(project, sort_keys=True)]
    with tempfile.TemporaryDirectory(dir=source_root) as directory:
        first = subprocess.run(args, cwd=directory, env=env_a, capture_output=True, text=True, check=True)
        second = subprocess.run(args, cwd=directory, env=env_b, capture_output=True, text=True, check=True)
        assert first.stdout == second.stdout


@pytest.mark.parametrize("template_id", [template["id"] for template in _CATALOG["templates"]])
def test_integration_full_render_template_passes_all_six_checks(template_id):
    flock = apply_flock_edit(None, {"action": "template", "template": template_id})
    project = _project(flock=flock, bpm=92, swing=0.25)
    first, _, _ = _render_audio_with_metadata(project)
    second, _, _ = _render_audio_with_metadata(project)
    assert wav_bytes(first) == wav_bytes(second)
    expected = round(project["bars"] * 4 * 60 / project["bpm"] * 44100)
    checks = check_audio(first, 44100, expected, deterministic=True)
    assert len(checks) == 6
    assert all(item["pass"] for item in checks.values()), checks


def _render_audio_with_metadata(project):
    # Keep the public render_audio API's historical two-item result unchanged.
    from rookery.render import _render_audio_with_metadata as render_with_metadata

    return render_with_metadata(project)
