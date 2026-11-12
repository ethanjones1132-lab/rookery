from __future__ import annotations

import copy
import hashlib
import runpy
from pathlib import Path

import pytest
import numpy as np

from tools.mix_calibrate import CASES
from rookery.project import ProjectStore, ValidationError, _apply_edit, canonical_project, diff_projects, new_project
from rookery.mix import mix_genre, mix_profile_enabled, role_target, track_role
from rookery.render import _balance_response, _render_audio_with_metadata, _render_song_audio, wav_bytes
from rookery.service import Service
from rookery.flock.synth import _plan


def test_genre_is_optional_and_track_add_defaults_are_role_aware():
    legacy = new_project("legacy")
    assert "genre" not in legacy
    assert "mix_profile" not in legacy

    boom_bap = _apply_edit(legacy, "track", {
        "action": "add", "id": "hat", "kind": "drum", "source": "factory:hat_tight",
    })
    assert boom_bap["tracks"][0]["gain_db"] == 5.8  # midpoint -9.5 minus hat_tight level -15.3
    assert boom_bap["tracks"][0]["pan"] == 0.15
    assert "mix_profile" not in boom_bap

    trap = _apply_edit(new_project("trap", genre="trap"), "track", {
        "action": "add", "id": "bass-extra", "kind": "bass", "source": "factory:808",
        "gain_db": -1,
    })
    added = next(track for track in trap["tracks"] if track["id"] == "bass-extra")
    assert added["gain_db"] == -1
    assert added["pan"] == 0
    assert trap["genre"] == "trap"
    assert "mix_profile" not in trap
    defaults = {track["id"]: track for track in new_project("trap-defaults", genre="trap")["tracks"]}
    assert defaults["808"]["gain_db"] == 0


def test_sample_roles_validate_map_to_mix_targets_and_set_add_defaults():
    from rookery.tools import SCHEMAS

    expected_roles = ["bed", "lead", "counter", "texture", "drums"]
    assert SCHEMAS["rookery_track"]["parameters"]["properties"]["role"]["enum"] == expected_roles
    apply_role = SCHEMAS["rookery_apply"]["parameters"]["properties"]["ops"]["items"]["properties"]["role"]
    assert apply_role["enum"] == expected_roles
    assert track_role({"kind": "sample", "source": "user:old.wav"}) == "sample_loop"

    cases = {
        "bed": ("sample_bed", -6, 0, [-8, -4]),
        "lead": ("sample_lead", -3, .2, [-5, -1]),
        "counter": ("sample_counter", -8.5, -.25, [-11, -6]),
        "texture": ("texture", -14, 0, [-20, -12]),
        "drums": ("sample_drums", -4, 0, [-6, -2]),
    }
    for index, (sample_role, expected) in enumerate(cases.items()):
        project = _apply_edit(new_project(f"sample-role-{index}"), "track", {
            "action": "add", "id": "sample", "kind": "sample", "source": "user:sample.wav",
            "role": sample_role,
        })
        track = project["tracks"][0]
        role, gain, pan, target = expected
        assert track["role"] == sample_role
        assert track_role(track) == role
        assert track["gain_db"] == gain and track["pan"] == pan
        assert role_target(role, "boom-bap") == target

    with pytest.raises(ValidationError, match="role must be bed, lead, counter, texture, or drums"):
        _apply_edit(new_project("bad-sample-role"), "track", {
            "action": "add", "id": "sample", "kind": "sample", "source": "user:sample.wav",
            "role": "pad",
        })
    with pytest.raises(ValidationError, match="role must be bed, lead, counter, texture, or drums"):
        _apply_edit(new_project("bad-drum-role"), "track", {
            "action": "add", "id": "kick", "kind": "drum", "source": "factory:kick_punch",
            "role": "lead",
        })

    roleless = _apply_edit(new_project("sample-role-diff"), "track", {
        "action": "add", "id": "sample", "kind": "sample", "source": "user:same.wav",
        "gain_db": -3, "pan": .2,
    })
    role_set = _apply_edit(roleless, "track", {"action": "set", "id": "sample", "role": "lead"})
    assert canonical_project(roleless) != canonical_project(role_set)
    assert any(item.get("field") == "role" for item in diff_projects(roleless, role_set))


def test_cached_sample_profile_sets_add_pan_and_drives_balance_target(tmp_path):
    import soundfile as sf

    from rookery.sampling import analyze

    sr, bpm = 16000, 120
    time = np.arange(4 * sr, dtype=np.float32) / sr
    lead = np.zeros_like(time)
    for bar in range(2):
        for step in (1, 5, 9, 13):
            start = round((bar * 16 + step) * 15 / bpm * sr)
            length = round(.07 * sr)
            local = np.arange(length, dtype=np.float32) / sr
            lead[start:start + length] += .8 * np.sin(2 * np.pi * 1200 * local) * np.exp(-local / .025)
    library = tmp_path / "library"
    library.mkdir()
    sample_path = library / "lead.wav"
    sf.write(sample_path, lead, sr)
    assert analyze(sample_path, title="Lead 120 bpm")["profile"]["role_hint"] == "lead"

    service = Service(tmp_path / "data", user_kit_dir=tmp_path)
    service.new("profile-mix", bpm, bars=4)
    service.apply_ops("profile-mix", [
        {"op": "track", "action": "add", "id": "kick", "kind": "drum",
         "source": "factory:kick_punch", "steps": "x" + "." * 63},
        {"op": "track", "action": "add", "id": "lead", "kind": "sample",
         "source": "user:library/lead.wav", "steps": "x" + "." * 63},
    ])
    added = next(track for track in service.store.read("profile-mix")["tracks"] if track["id"] == "lead")
    assert "role" not in added
    assert added["gain_db"] == -3 and added["pan"] == .2

    service.apply_ops("profile-mix", [{"op": "balance"}])
    report = service.render("profile-mix")["balance"]["lead"]
    assert report["role"] == "sample_lead"
    assert report["target"] == [-5, -1]
    assert report["ok"]

    service.edit({"name": "profile-mix", "op": "track", "action": "add", "id": "counter",
                  "kind": "sample", "source": "user:missing.wav", "role": "counter"})
    counter = next(track for track in service.store.read("profile-mix")["tracks"] if track["id"] == "counter")
    assert counter["gain_db"] == -8.5 and counter["pan"] == -.25
    assert '"role":"counter"' in service.state("profile-mix")


def test_flock_trims_require_mix_profile_not_unrelated_track_levels():
    legacy = _apply_edit(new_project("old-flock"), "flock", {
        "action": "template", "template": "dusty_boom_bap",
    })
    legacy = _apply_edit(legacy, "track", {
        "action": "add", "id": "quiet-hat", "kind": "drum", "source": "factory:hat_tight",
        "gain_db": -10,
    })
    assert "mix_profile" not in legacy
    modern = _apply_edit(new_project("boom-bap", genre="boom-bap"), "track", {
        "action": "add", "id": "mix-hat", "kind": "drum", "source": "factory:hat_tight",
        "gain_db": 0,
    })
    assert "mix_profile" not in modern
    modern["mix_profile"] = "targets-v1"
    modern = _apply_edit(modern, "flock", {
        "action": "template", "template": "dusty_boom_bap",
    })
    unmarked = copy.deepcopy(modern)
    unmarked.pop("mix_profile")
    assert canonical_project(modern) != canonical_project(unmarked)
    _metadata, old_events = _plan(legacy, 8000)
    _metadata, new_events = _plan(modern, 8000)
    old_bass = next(event for event in old_events if event["bird_id"] == "bramble")
    new_bass = next(event for event in new_events if event["bird_id"] == "bramble")
    assert old_bass["gain"] == pytest.approx(10 ** (-3 / 20))
    assert new_bass["gain"] == pytest.approx(10 ** (3.7 / 20))


def test_track_gain_edits_do_not_opt_into_mix_profile():
    project = _apply_edit(new_project("target-set", genre="trap"), "flock", {
        "action": "template", "template": "dusty_boom_bap",
    })
    _metadata, before = _plan(project, 8000)
    old_bass = next(event for event in before if event["bird_id"] == "bramble")
    assert "mix_profile" not in project

    targeted = _apply_edit(project, "track", {
        "action": "set", "id": "hat", "gain_db": 0.5,
    })
    _metadata, after = _plan(targeted, 8000)
    new_bass = next(event for event in after if event["bird_id"] == "bramble")
    assert "mix_profile" not in targeted
    assert new_bass["gain"] == old_bass["gain"]

    unrelated = _apply_edit(new_project("unrelated-set", genre="trap"), "track", {
        "action": "add", "id": "off-role", "kind": "drum", "source": "factory:808",
    })
    assert "mix_profile" not in unrelated
    unrelated = _apply_edit(unrelated, "track", {
        "action": "set", "id": "off-role", "gain_db": 0.5,
    })
    assert "mix_profile" not in unrelated


@pytest.mark.parametrize("genre", [None, "boom-bap", "trap"])
def test_store_create_always_enables_mix_profile_without_changing_new_project(genre, tmp_path):
    project = new_project("unmarked", genre=genre)
    assert "mix_profile" not in project
    assert not mix_profile_enabled(project)
    created = ProjectStore(tmp_path / str(genre)).create("created", genre=genre)["project"]
    assert created["mix_profile"] == "targets-v1"
    assert created.get("genre") == genre
    assert mix_profile_enabled(created)
    assert mix_genre(created) == (genre or "boom-bap")


def test_groove_expansion_uses_genre_defaults(tmp_path):
    service = Service(tmp_path / "data")
    service.new("trap-groove", 140, genre="trap")
    for track_id in ("kick", "snare", "hat", "808"):
        service.edit({"name": "trap-groove", "op": "track", "action": "remove", "id": track_id})
    service.apply_ops("trap-groove", [{"op": "groove", "groove": "pocket-132-trap-bounce"}])

    tracks = {track["id"]: track for track in service.store.read("trap-groove")["tracks"]}
    assert tracks["kick"]["gain_db"] == 0
    assert tracks["hat"]["gain_db"] == 7.8  # trap hat midpoint -7.5 minus hat_tight level -15.3
    assert tracks["hat"]["pan"] == 0.15
    assert tracks["snare"]["gain_db"] == 2.5  # midpoint -1 minus snare_snap level -3.5


def _bass_project(*, duck: float, song: bool = False):
    project = new_project("duck-test", 90)
    project = _apply_edit(project, "track", {
        "action": "add", "id": "kick", "kind": "drum", "source": "factory:kick_punch",
        "steps": "x...............",
    })
    project = _apply_edit(project, "track", {
        "action": "add", "id": "bass", "kind": "bass", "source": "factory:808",
        "duck": duck, "notes": [{"step": 0, "len": 64, "pitch": "C1"}],
    })
    if song:
        project = _apply_edit(project, "arrange", {"sections": [{"id": "part", "repeat": 1, "mute": []}]})
    return project


@pytest.mark.parametrize("song", [False, True])
def test_bass_duck_attenuates_loop_and_song_layers(song):
    render = _render_song_audio if song else _render_audio_with_metadata
    common = {"sample_rate": 8000, "fixed_gain": 1}
    dry_audio, _dry_meters, *_ = render(_bass_project(duck=0, song=song), **common)
    ducked_audio, _ducked_meters, *_ = render(_bass_project(duck=0.8, song=song), **common)
    assert not np.array_equal(dry_audio, ducked_audio)


@pytest.mark.parametrize("song", [False, True])
def test_zero_bass_duck_is_bit_identical_to_omitting_duck(song):
    render = _render_song_audio if song else _render_audio_with_metadata
    common = {"sample_rate": 8000, "fixed_gain": 1}
    zero_duck = _bass_project(duck=0, song=song)
    omitted_duck = copy.deepcopy(zero_duck)
    next(track for track in omitted_duck["tracks"] if track["id"] == "bass").pop("duck")
    zero_audio, *_ = render(zero_duck, **common)
    omitted_audio, *_ = render(omitted_duck, **common)
    assert np.array_equal(zero_audio, omitted_audio)


def test_bass_duck_validation_is_limited_to_bass_and_loop_samples():
    project = new_project("duck-validation")
    bass = _apply_edit(project, "track", {
        "action": "add", "id": "bass", "kind": "bass", "source": "factory:808", "duck": 0.4,
    })
    assert bass["tracks"][0]["duck"] == 0.4
    with pytest.raises(ValidationError, match="duck is only valid"):
        _apply_edit(project, "track", {
            "action": "add", "id": "kick", "kind": "drum", "source": "factory:kick_punch", "duck": 0.4,
        })


def test_balance_uses_kick_or_loudest_drum_and_limits_notes():
    project = new_project("balance")
    project = _apply_edit(project, "track", {
        "action": "add", "id": "kick", "kind": "drum", "source": "factory:kick_punch",
        "steps": "x...............",
    })
    project = _apply_edit(project, "track", {
        "action": "add", "id": "snare", "kind": "drum", "source": "factory:snare_snap",
        "steps": "....x...........",
    })
    project = _apply_edit(project, "flock", {"action": "template", "template": "dusty_boom_bap"})

    _audio, _meters, metadata = _render_audio_with_metadata(
        project, sample_rate=8000, fixed_gain=1, include_balance=True,
    )
    result = _balance_response(project, metadata["_balance_layers"])
    assert result["ref"] == "kick:kick"
    assert result["balance"]["kick"]["lu_vs_kick"] == 0
    assert any(key.startswith("bird:") for key in result["balance"])
    assert len(result["mix_notes"]) <= 5

    no_kick = {**project, "tracks": [track for track in project["tracks"] if track["id"] != "kick"]}
    _audio, _meters, metadata = _render_audio_with_metadata(
        no_kick, sample_rate=8000, fixed_gain=1, include_balance=True,
    )
    fallback = _balance_response(no_kick, metadata["_balance_layers"])
    assert fallback["ref"] == "loudest_drum:snare"

    no_drums = {**project, "tracks": []}
    _audio, _meters, metadata = _render_audio_with_metadata(
        no_drums, sample_rate=8000, fixed_gain=1, include_balance=True,
    )
    no_reference = _balance_response(no_drums, metadata["_balance_layers"])
    assert no_reference["ref"] == "none"
    assert any("add an audible kick or drum" in note for note in no_reference["mix_notes"])

    muted = copy.deepcopy(project)
    muted["flock"]["perches"][0]["mute"] = True
    _audio, _meters, metadata = _render_audio_with_metadata(
        muted, sample_rate=8000, fixed_gain=1, include_balance=True,
    )
    muted_balance = _balance_response(muted, metadata["_balance_layers"])["balance"]
    assert "bird:0" not in muted_balance

    solo = copy.deepcopy(project)
    for perch in solo["flock"]["perches"]:
        if perch is not None:
            perch["solo"] = perch["bird"] == "bramble"
    _audio, _meters, metadata = _render_audio_with_metadata(
        solo, sample_rate=8000, fixed_gain=1, include_balance=True,
    )
    solo_balance = _balance_response(solo, metadata["_balance_layers"])["balance"]
    assert [key for key in solo_balance if key.startswith("bird:")] == ["bird:0"]

    loud_flock = _apply_edit(project, "flock", {
        "action": "mix", "bird": "bramble", "gain_db": 12,
    })
    _audio, _meters, metadata = _render_audio_with_metadata(
        loud_flock, sample_rate=8000, fixed_gain=1, include_balance=True,
    )
    notes = _balance_response(loud_flock, metadata["_balance_layers"])["mix_notes"]
    assert any("ask the user to adjust bird bramble" in note for note in notes)
    assert all("bird bramble gain_db" not in note for note in notes)


def test_loop_render_reports_synthesized_sample_fit_and_respects_bar_gating(tmp_path, monkeypatch):
    import soundfile as sf
    import pedalboard
    from rookery import sampling
    from rookery.project import validate_project

    sr, bpm, bars = 8000, 90, 4
    bar_frames = round(4 * 60 / bpm * sr)
    step_frames = round(15 / bpm * sr)
    bed = np.zeros(bar_frames, dtype=np.float64)
    for step, notes in ((0, (220.0, 261.63, 329.63)), (8, (174.61, 220.0, 261.63))):
        start = step * step_frames
        end = min(bar_frames, start + 8 * step_frames)
        local = np.arange(end - start, dtype=np.float64) / sr
        chord = sum(np.sin(2 * np.pi * hz * local) for hz in notes) / 3
        envelope = np.minimum(1.0, np.arange(end - start) / (sr * .02))
        bed[start:end] = .3 * chord * envelope

    def plucks(steps, frequency):
        signal = np.zeros(bar_frames, dtype=np.float64)
        for step in steps:
            start = round(step * 15 / bpm * sr)
            length = min(round(.16 * sr), bar_frames - start)
            local = np.arange(length, dtype=np.float64) / sr
            signal[start:start + length] += .65 * np.sin(2 * np.pi * frequency * local) * np.exp(-local / .04)
        return signal

    sources = {
        "bed.wav": bed,
        "lead.wav": plucks((2, 6, 10, 14), 1046.5),
        "clash.wav": bed.copy(),
    }
    profiles = {
        "bed.wav": {"pitched": True, "bands": [.1, .9, 0, 0]},
        "lead.wav": {"pitched": True, "bands": [0, 0, 0, 1]},
        "clash.wav": {"pitched": True, "bands": [.1, .9, 0, 0]},
    }
    for name, signal in sources.items():
        sf.write(tmp_path / name, signal.astype(np.float32), sr, subtype="FLOAT")
    monkeypatch.setattr(sampling, "analyze", lambda path, **_kwargs: {
        "bpm": bpm, "key": None if Path(path).name == "clash.wav" else "A minor",
        "downbeat_s": 0.0, "bars": 1, "confidence": .9,
        "profile": profiles[Path(path).name],
    })
    monkeypatch.setattr(pedalboard, "time_stretch", lambda audio, *_args, **_kwargs: np.asarray(audio))

    project = new_project("sample-fit", bpm, bars)
    project["mix_profile"] = "targets-v1"
    project["tracks"] = [
        {"id": ident, "kind": "sample", "source": f"user:{filename}", "mode": "loop",
         "steps": "xxxx", "key_lock": False}
        for ident, filename in (("bed", "bed.wav"), ("lead", "lead.wav"), ("clash", "clash.wav"))
    ]
    project = validate_project(project)
    from rookery import render as renderer
    monkeypatch.setattr(renderer, "SAMPLE_RATE", sr)
    service = Service(tmp_path / "service-data", user_kit_dir=tmp_path)
    service.new("sample-fit", bpm, bars)
    service.apply_ops("sample-fit", [
        {"op": "track", "action": "add", "id": ident, "kind": "sample",
         "source": f"user:{filename}", "mode": "loop", "steps": "xxxx", "key_lock": False}
        for ident, filename in (("bed", "bed.wav"), ("lead", "lead.wav"), ("clash", "clash.wav"))
    ])
    service_response = service.render("sample-fit")
    assert service_response["fit"]
    assert service.render("sample-fit")["fit"] == service_response["fit"]  # cached response keeps fit

    def render(current):
        _audio, _meters, metadata = _render_audio_with_metadata(
            current, sample_rate=sr, user_kit_dir=tmp_path, fixed_gain=1, include_balance=True,
        )
        return _balance_response(current, metadata["_balance_layers"])

    response = render(project)
    fit = {(item["a"], item["b"]): item for item in response["fit"]}
    assert set(fit) == {("bed", "lead"), ("bed", "clash"), ("lead", "clash")}
    assert fit[("bed", "clash")]["register_overlap"] == 1.0
    assert fit[("bed", "clash")]["rhythm_overlap"] > .8
    assert fit[("bed", "lead")]["rhythm_overlap"] < .8
    assert any("bed and clash sit in the same register on the same beats" in note
               for note in response["mix_notes"])
    assert any("clash is pitched but its key is unknown" in note for note in response["mix_notes"])

    gated = {**project, "tracks": [dict(track) for track in project["tracks"][:1] + project["tracks"][2:]]}
    gated["tracks"][0]["steps"] = "x.x."
    gated["tracks"][1]["steps"] = ".x.x"
    gated_fit = render(validate_project(gated))["fit"][0]
    assert gated_fit["register_overlap"] == 1.0
    assert gated_fit["rhythm_overlap"] < .3


def test_balance_apply_op_targets_audible_layers_without_other_edits(tmp_path):
    service = Service(tmp_path / "data")
    service.new("balance-op", 90, genre="boom-bap")
    service.apply_ops("balance-op", [
        {"op": "groove", "groove": "theory-boom-bap-ghost"},
        {"op": "flock", "action": "template", "template": "dusty_boom_bap"},
    ])
    before = service.store.read("balance-op")
    old_rev = before["rev"]
    before_track_gains = {track["id"]: track["gain_db"] for track in before["tracks"]}
    before_bird_gains = [perch.get("gain_db") if perch else None
                         for perch in before["flock"]["perches"]]

    result = service.apply_ops("balance-op", [{"op": "balance"}], rev=old_rev)

    after = service.store.read("balance-op")
    assert after["rev"] == old_rev + 1 == result["rev"]
    assert after["mix_profile"] == "targets-v1"
    assert any(item.get("field") == "gain_db" for item in result["diff"])
    assert [perch.get("gain_db") if perch else None
            for perch in after["flock"]["perches"]] == before_bird_gains
    for project in (before, after):
        for track in project["tracks"]:
            track.pop("gain_db")
        for perch in project.get("flock", {}).get("perches", []):
            if perch is not None:
                perch.pop("gain_db", None)
    before.pop("mix_profile", None)
    after.pop("mix_profile", None)
    for project in (before, after):
        for field in ("rev", "updated_at", "history", "_history_cursor", "_history_parent",
                      "_history_change_source", "_history_change_diff", "_history_to_rev"):
            project.pop(field, None)
    assert after == before

    rendered = service.render("balance-op")
    assert rendered["balance"]
    assert all(item["ok"] for ident, item in rendered["balance"].items()
               if not ident.startswith("bird:"))
    assert any("ask the user to adjust bird" in note for note in rendered["mix_notes"])
    reference_id = rendered["ref"].split(":", 1)[1]
    after_reference = next(track for track in service.store.read("balance-op")["tracks"]
                           if track["id"] == reference_id)
    assert after_reference["gain_db"] == before_track_gains[reference_id]

    restored = service.undo("balance-op")
    assert restored["rev"] == result["rev"] + 1
    assert {track["id"]: track["gain_db"] for track in restored["project"]["tracks"]} == before_track_gains
    assert [perch.get("gain_db") if perch else None
            for perch in restored["project"]["flock"]["perches"]] == [
                perch.get("gain_db") if perch else None for perch in before["flock"]["perches"]
            ]


def test_balance_apply_op_requires_a_balancer_and_accepts_no_fields(tmp_path):
    store = ProjectStore(tmp_path / "data")
    store.create("balance-needs-service", genre="boom-bap")
    with pytest.raises(ValidationError, match="balance op requires a balancer"):
        store.apply_batch("balance-needs-service", [{"op": "balance"}])

    with pytest.raises(ValidationError, match="balance op accepts no fields"):
        _apply_edit(new_project("balance-extra"), "balance", {"gain_db": 2},
                    balancer=lambda _project: {})


def _balance_case_ops(template, genre, groove):
    ops = [
        {"op": "groove", "groove": groove},
        {"op": "flock", "action": "template", "template": template},
    ]
    if genre == "trap":
        ops.append({"op": "flock", "action": "mute", "bird": "cinder", "on": True})
    else:
        # Late House uses Cinder for its bass bird; the other boom-bap cases use Bramble.
        bass_bird = "cinder" if template == "late_house" else "bramble"
        ops.extend([
            {"op": "flock", "action": "mute", "bird": bass_bird, "on": True},
            {"op": "track", "action": "add", "id": "808", "kind": "bass",
             "source": "factory:808", "duck": 0.4,
             "notes": [{"step": 0, "len": 6, "pitch": "A1"},
                       {"step": 16, "len": 6, "pitch": "E2"},
                       {"step": 32, "len": 6, "pitch": "A1"},
                       {"step": 48, "len": 6, "pitch": "G1"}]},
        ])
    return ops


def _audible_gains(project):
    gains = {f"track:{track['id']}": track["gain_db"] for track in project["tracks"]}
    gains.update({f"bird:{slot}": perch.get("gain_db", 0)
                  for slot, perch in enumerate(project.get("flock", {}).get("perches", [])) if perch})
    return gains


@pytest.mark.parametrize("template,genre,groove,bpm,swing", CASES)
def test_balance_covers_calibration_templates_and_is_idempotent(
    template, genre, groove, bpm, swing, tmp_path,
):
    service = Service(tmp_path / "data")
    name = f"balanced-{template}"
    service.new(name, bpm, bars=4, swing=swing, genre=genre)
    service.apply_ops(name, [*_balance_case_ops(template, genre, groove), {"op": "balance"}])

    first = service.store.read(name)
    rendered = service.render(name)
    assert rendered["balance"]
    assert all(item["ok"] for ident, item in rendered["balance"].items()
               if not ident.startswith("bird:"))
    first_gains = _audible_gains(first)

    service.apply_ops(name, [{"op": "balance"}])
    second_gains = _audible_gains(service.store.read(name))
    assert first_gains.keys() == second_gains.keys()
    assert all(abs(first_gains[key] - second_gains[key]) <= 0.2 for key in first_gains)


def test_identical_balanced_projects_have_identical_gains_and_wav_hashes(tmp_path):
    service = Service(tmp_path / "data")
    gains = []
    hashes = []
    for name in ("balanced-copy-a", "balanced-copy-b"):
        service.new(name, 90, genre="boom-bap")
        service.apply_ops(name, [
            *_balance_case_ops("dusty_boom_bap", "boom-bap", "theory-boom-bap-ghost"),
            {"op": "balance"},
        ])
        gains.append(_audible_gains(service.store.read(name)))
        hashes.append(service.render(name)["wav_hash"])
    assert gains[0] == gains[1]
    assert hashes[0] == hashes[1]


def test_balance_keeps_two_audible_basses_and_reports_them(tmp_path):
    service = Service(tmp_path / "data")
    service.new("two-basses", 90, genre="boom-bap")
    service.apply_ops("two-basses", [
        {"op": "groove", "groove": "theory-boom-bap-ghost"},
        {"op": "flock", "action": "template", "template": "dusty_boom_bap"},
        {"op": "track", "action": "add", "id": "808", "kind": "bass",
         "source": "factory:808", "duck": 0.4,
         "notes": [{"step": 0, "len": 6, "pitch": "D2"},
                   {"step": 32, "len": 6, "pitch": "A1"}]},
        {"op": "balance"},
    ])

    project = service.store.read("two-basses")
    bramble = next(perch for perch in project["flock"]["perches"] if perch and perch["bird"] == "bramble")
    assert bramble["mute"] is False
    assert next(track for track in project["tracks"] if track["id"] == "808")["mute"] is False
    rendered = service.render("two-basses")
    assert "808" in rendered["balance"]
    assert any(ident.startswith("bird:") and item["role"] == "flock_bass"
               for ident, item in rendered["balance"].items())
    assert any("two basses" in note for note in rendered["mix_notes"])


def test_existing_legacy_fixture_keeps_frozen_pcm_bytes_without_mix_profile():
    legacy_project = runpy.run_path(str(Path(__file__).with_name("test_flock_synth.py")))["_LEGACY_PROJECT"]

    assert "mix_profile" not in legacy_project
    audio, _meters, _metadata = _render_audio_with_metadata(legacy_project)
    assert hashlib.sha256(wav_bytes(audio, 44100, "PCM_24")).hexdigest() == (
        "a550f7638ec60c3740a507ce46834b1da9347029f6c6bddd97751841f269c1fd"
    )
