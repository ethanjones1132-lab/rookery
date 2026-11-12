from copy import deepcopy

import numpy as np
import pytest

from rookery.flock.model import default_flock
from rookery.project import ProjectStore, ValidationError, new_project, project_hash, validate_project
from rookery.render import render_song_audio
from rookery.service import Service
from rookery import tools
from contextlib import contextmanager
from types import SimpleNamespace
import json


def _project(bpm=120):
    project = new_project("arrangement", bpm=bpm, bars=4, genre="trap")
    project["flock"] = default_flock()
    project["flock"]["perches"][0] = {"bird": "echo", "song": "A"}
    project["tracks"][0]["steps"] = "x..............."
    return validate_project(project)


def _arrange(project, sections):
    project["arrangement"] = {"sections": sections}
    return validate_project(project)


@pytest.mark.parametrize(("sections", "message"), [
    ([{"id": "intro", "repeat": 1, "mute": ["missing"]}], "unknown track"),
    ([{"id": "intro", "repeat": 1, "mute": ["bird:1"]}], "empty perch"),
    ([{"id": "intro", "repeat": 1, "mute": []}, {"id": "intro", "repeat": 1, "mute": []}], "duplicated"),
    ([{"id": "intro", "repeat": 9, "mute": []}], "repeat"),
])
def test_arrangement_validation_messages(sections, message):
    with pytest.raises(ValidationError, match=message):
        _arrange(_project(), sections)


def test_arrangement_limit_reports_actual_song_length():
    project = _project(60)
    project["bars"] = 8
    with pytest.raises(ValidationError, match=r"song length .* exceeds the 180 s limit"):
        _arrange(project, [{"id": "long", "repeat": 8, "mute": []}])


def test_track_and_perch_removal_clean_section_mutes_and_undo(tmp_path):
    store = ProjectStore(tmp_path)
    store.create("cleanup")
    store.edit("cleanup", "track", action="add", id="kick", kind="drum", source="factory:kick_boom")
    store.edit("cleanup", "flock", action="perch", bird="echo", slot=0)
    arranged = store.edit("cleanup", "arrange", sections=[{"id": "intro", "repeat": 1,
                                                             "mute": ["kick", "bird:0"]}])
    removed_track = store.edit("cleanup", "track", action="remove", id="kick")
    assert removed_track["project"]["arrangement"]["sections"][0]["mute"] == ["bird:0"]
    store.edit("cleanup", "flock", action="perch", bird="echo", slot=0)
    removed_perch = store.edit("cleanup", "flock", action="unperch", slot=0)
    assert removed_perch["project"]["arrangement"]["sections"][0]["mute"] == []
    assert store.undo("cleanup")["project"]["arrangement"]["sections"][0]["mute"] == ["bird:0"]
    assert store.undo("cleanup")["project"]["arrangement"]["sections"][0]["mute"] == ["bird:0"]
    assert arranged["rev"] < removed_track["rev"]


def test_arrange_edit_diff_remove_and_undo(tmp_path):
    store = ProjectStore(tmp_path)
    store.create("edit")
    changed = store.edit("edit", "arrange", sections=[{"id": "verse", "repeat": 2, "mute": []}])
    assert changed["diff"] == [{"field": "arrangement", "from": None,
                                "to": {"sections": [{"id": "verse", "repeat": 2, "mute": []}]}}]
    assert store.undo("edit")["project"].get("arrangement") is None
    store.edit("edit", "arrange", sections=[{"id": "verse", "repeat": 2, "mute": []}])
    assert store.edit("edit", "arrange", sections=None)["diff"][0]["to"] is None


def test_apply_receipt_and_state_use_compact_arrangement_line(tmp_path, monkeypatch):
    monkeypatch.setenv("ROOKERY_DATA_DIR", str(tmp_path / "data"))
    from rookery.service import reset_services_for_tests
    reset_services_for_tests()

    class Events:
        @contextmanager
        def editing(self, _name):
            yield

    handler = tools.make_handler(SimpleNamespace(tools=tools, events=Events()), "rookery_apply")
    tools.new(tmp_path / "data", "receipt", 90)
    result = json.loads(handler({"name": "receipt", "ops": [{"op": "arrange", "sections": [
        {"id": "intro", "repeat": 2, "mute": []}, {"id": "verse", "repeat": 4, "mute": []}
    ]}]}))
    assert result["changed"] == ["Arrangement · intro×2, verse×4"]
    assert "Arrangement · intro×2, verse×4" in tools.state(tmp_path / "data", "receipt")


def test_no_arrangement_keeps_hash_and_loop_projection_unchanged():
    before = _project()
    after = deepcopy(before)
    with_arrangement = _arrange(after, [{"id": "verse", "repeat": 1, "mute": []}])
    assert project_hash(before, "renderer") == project_hash(with_arrangement, "renderer")
    assert "arrangement" not in validate_project(before)


def test_song_length_mutes_and_timing_are_exact():
    project = _project()
    project = _arrange(project, [
        {"id": "intro", "repeat": 1, "mute": ["kick", "snare", "hat", "808", "bird:0"]},
        {"id": "verse", "repeat": 1, "mute": ["snare", "hat", "808", "bird:0"]},
    ])
    audio, meters, metadata, timing = render_song_audio(project, 8000)
    loop_frames = round(4 * 4 * 60 / project["bpm"] * 8000)
    assert len(audio) == loop_frames * 2
    assert timing == [{"id": "intro", "start_s": 0.0, "end_s": loop_frames / 8000},
                      {"id": "verse", "start_s": loop_frames / 8000, "end_s": 2 * loop_frames / 8000}]
    assert np.max(np.abs(audio[:loop_frames])) == 0
    assert np.max(np.abs(audio[loop_frames:])) > 0
    assert meters["kick"]["peak_db"] > -120
    assert metadata["flock_events"] == {}


def test_song_is_deterministic_and_requires_arrangement():
    project = _project()
    with pytest.raises(ValidationError, match="this project has no arrangement; add one with the arrange op"):
        render_song_audio(project, 8000)
    project = _arrange(project, [{"id": "part", "repeat": 1, "mute": []}])
    first = render_song_audio(project, 8000)[0]
    second = render_song_audio(project, 8000)[0]
    assert first.tobytes() == second.tobytes()


def test_perch_mute_is_section_scoped():
    project = _project()
    project = _arrange(project, [
        {"id": "intro", "repeat": 1, "mute": ["kick", "snare", "hat", "808", "bird:0"]},
        {"id": "verse", "repeat": 1, "mute": ["kick", "snare", "hat", "808"]},
    ])
    audio, *_ = render_song_audio(project, 8000)
    loop_frames = round(4 * 4 * 60 / project["bpm"] * 8000)
    assert np.max(np.abs(audio[:loop_frames])) == 0
    assert np.max(np.abs(audio[loop_frames:])) > 0


def test_single_section_song_matches_loop_interior():
    from rookery.render import render_audio

    project = new_project("interior", bpm=120, bars=4, genre="trap")
    project = _arrange(project, [{"id": "full", "repeat": 1, "mute": []}])
    loop, _ = render_audio(project, 8000)
    song, *_ = render_song_audio(project, 8000)
    bar = round(4 * 60 / project["bpm"] * 8000)
    start, end = bar, 3 * bar
    lhs, rhs = loop[start:end].astype(np.float64), song[start:end].astype(np.float64)
    similarity = np.corrcoef(lhs.reshape(-1), rhs.reshape(-1))[0, 1]
    assert similarity > 0.98


def test_song_reverb_tail_flows_forward_without_wrapping_to_zero():
    project = _project()
    project["tracks"] = [project["tracks"][0]]
    project["tracks"][0]["steps"] = "." * 63 + "x"
    project["tracks"][0]["fx"] = [{"type": "reverb", "room_size": 0.95,
                                    "damping": 0.2, "wet_level": 0.8,
                                    "dry_level": 0.1, "width": 1.0}]
    project["master"]["fx"] = []
    project = _arrange(project, [
        {"id": "hit", "repeat": 1, "mute": []},
        {"id": "tail", "repeat": 1, "mute": ["kick"]},
    ])
    audio, *_ = render_song_audio(project, 8000)
    loop_frames = round(4 * 4 * 60 / project["bpm"] * 8000)
    assert np.max(np.abs(audio[:100])) == 0
    assert np.max(np.abs(audio[loop_frames:])) > 0


def test_service_song_response_runs_checks_and_exposes_audio(tmp_path):
    service = Service(tmp_path)
    service.new("checked", 120, genre="trap")
    service.edit({"name": "checked", "op": "arrange",
                  "sections": [{"id": "verse", "repeat": 1, "mute": []}]})
    result = service.render("checked", song=True)
    assert result["song"] is True
    assert result["sections"] == [{"id": "verse", "start_s": 0.0, "end_s": 8.0}]
    assert result["report"]["length_exact"]["pass"] is True
    assert result["report"]["no_clipping"]["pass"] is True
    assert result["report"]["deterministic"]["pass"] is True
    assert service.audio(result["hash"])["mime"] == "audio/wav"


def test_song_render_is_what_the_next_project_load_returns(tmp_path):
    # The page renders with song=true, then reloads the project: it must get the song back.
    service = Service(tmp_path)
    service.new("reload", 120, genre="trap")
    service.edit({"name": "reload", "op": "arrange",
                  "sections": [{"id": "intro", "repeat": 1, "mute": ["kick"]},
                               {"id": "verse", "repeat": 1, "mute": []}]})
    rendered = service.render("reload", song=True)
    view = service.get_project("reload")["render"]
    assert view is not None
    assert view["hash"] == rendered["hash"]
    assert view["song"] is True
    assert [section["id"] for section in view["sections"]] == ["intro", "verse"]
    assert view["duration_samples"] == rendered["duration_samples"]
    loop = service.render("reload")
    assert "song" not in service.get_project("reload")["render"]
    assert service.get_project("reload")["render"]["hash"] == loop["hash"]


@pytest.mark.parametrize(("section", "message"), [
    ({"steps": {"missing": "x"}}, "section 'part'.steps references unknown track"),
    ({"steps": {"808": "x"}}, "section 'part'.steps cannot override bass"),
    ({"notes": {"kick": []}}, "section 'part'.notes is only valid for bass"),
    ({"steps": {"kick": "xxx"}}, "section 'part'.steps override.*does not divide"),
    ({"songs": {"bird:0": "D"}}, "song D is not unlocked"),
    ({"songs": {"bird:1": "A"}}, "empty perch"),
    ({"fill": 1}, "section 'part'.fill must be a boolean"),
])
def test_section_override_validation_names_the_section(section, message):
    project = _project()
    with pytest.raises(ValidationError, match=message):
        _arrange(project, [{"id": "part", "repeat": 1, "mute": [], **section}])


def test_section_song_d_uses_the_flock_combo_rules_and_corvus_is_a_only():
    from rookery.flock.model import default_flock, load_catalog

    project = _project()
    project["flock"] = default_flock()
    project["flock"]["scale"] = "minor"
    project["flock"]["perches"][:3] = [
        {"bird": bird, "song": "A"} for bird in ("echo", "hush", "sable")]
    arranged = _arrange(project, [{"id": "night", "repeat": 1, "mute": [],
                                   "songs": {"bird:0": "D"}}])
    from rookery.arrangement import section_flock
    assert section_flock(arranged, arranged["arrangement"]["sections"][0])["perches"][0]["song"] == "D"

    catalog = load_catalog()
    role_counts = {}
    picked = []
    for bird in catalog["birds"]:
        role = bird["role"]
        if role_counts.get(role, 0) < 2:
            picked.append(bird["id"])
            role_counts[role] = role_counts.get(role, 0) + 1
        if len(picked) == 6:
            break
    flock = default_flock()
    flock["seen"] = [bird["id"] for bird in catalog["birds"]]
    flock["perches"] = [{"bird": bird, "song": "A"} for bird in picked]
    flock["perches"].append({"bird": "corvus", "song": "A"})
    project = _project()
    project["flock"] = flock
    with pytest.raises(ValidationError, match="section 'corvus'.*Corvus sings only song A"):
        _arrange(project, [{"id": "corvus", "repeat": 1, "mute": [],
                           "songs": {"bird:6": "B"}}])


def test_loop_sample_section_steps_gate_bars_and_legacy_sections_stay_minimal():
    project = _project()
    project["tracks"].append({"id": "loop", "kind": "sample", "source": "user:loop.wav",
                              "mode": "loop", "steps": "xxxx"})
    normalized = _arrange(project, [{"id": "part", "repeat": 1, "mute": [],
                                    "steps": {"loop": "x."}}])
    section = normalized["arrangement"]["sections"][0]
    assert section["steps"]["loop"] == "x.x."
    with pytest.raises(ValidationError, match="section 'bad'.*steps in loop mode gates bars"):
        _arrange(project, [{"id": "bad", "repeat": 1, "mute": [], "steps": {"loop": "xxx"}}])
    legacy = _arrange(_project(), [{"id": "legacy", "repeat": 1, "mute": []}])
    assert set(legacy["arrangement"]["sections"][0]) == {"id", "repeat", "mute"}


def test_section_track_view_applies_overrides_and_fill_only_to_last_repeat():
    from rookery.arrangement import section_track_view

    project = _project()
    tracks = {track["id"]: track for track in project["tracks"]}
    section = _arrange(project, [{"id": "fill", "repeat": 2, "mute": [], "fill": True,
                                 "steps": {"kick": "................", "snare": "................",
                                           "hat": "xxxxxxxxxxxxxxxx"},
                                 "velocity": {"snare": [0.4]},
                                 "notes": {"808": [{"step": 2, "len": 3, "pitch": "D1"}]}}])["arrangement"]["sections"][0]

    first_kick, _, first_notes = section_track_view(project, section, tracks["kick"], 0)
    assert first_kick == "................"
    assert first_notes == []
    last_kick, kick_velocity, _ = section_track_view(project, section, tracks["kick"], 1)
    assert last_kick[-4:] == "x..."
    assert kick_velocity[-4:] == [0.8, 0.0, 0.0, 0.0]
    last_snare, snare_velocity, _ = section_track_view(project, section, tracks["snare"], 1)
    assert last_snare[-4:] == "xxxx"
    assert snare_velocity[-4:] == [0.35, 0.55, 0.75, 0.95]
    last_hat, _, _ = section_track_view(project, section, tracks["hat"], 1)
    assert last_hat[-2:] == ".."
    assert section_track_view(project, section, tracks["808"], 1)[2] == [
        {"step": 2, "len": 3, "pitch": "D1"}]


def test_section_step_override_changes_only_its_rendered_range():
    from rookery.render import _render_song_audio

    project = _project()
    sections = [{"id": name, "repeat": 1, "mute": []} for name in ("a", "b", "c")]
    original = _arrange(project, sections)
    changed = deepcopy(original)
    changed["arrangement"]["sections"][2]["steps"] = {"kick": "................"}
    changed = validate_project(changed)
    base_audio = _render_song_audio(original, 8000, fixed_gain=1)[0]
    changed_audio = _render_song_audio(changed, 8000, fixed_gain=1)[0]
    loop = round(4 * 4 * 60 / original["bpm"] * 8000)
    assert np.array_equal(base_audio[:2 * loop], changed_audio[:2 * loop])
    assert not np.array_equal(base_audio[2 * loop:], changed_audio[2 * loop:])


def test_section_song_override_changes_flock_events_only_in_its_section():
    project = _project()
    base = _arrange(project, [{"id": name, "repeat": 1, "mute": []}
                              for name in ("a", "b", "c")])
    changed = deepcopy(base)
    changed["arrangement"]["sections"][1]["songs"] = {"bird:0": "B"}
    changed = validate_project(changed)
    base_events = render_song_audio(base, 8000)[2]["flock_events"]["echo"]
    changed_events = render_song_audio(changed, 8000)[2]["flock_events"]["echo"]
    loop_seconds = 4 * 4 * 60 / base["bpm"]
    in_section = lambda values, section: [item for item in values
                                          if section * loop_seconds <= item["t"] < (section + 1) * loop_seconds]
    assert in_section(base_events, 0) == in_section(changed_events, 0)
    assert in_section(base_events, 2) == in_section(changed_events, 2)
    assert in_section(base_events, 1) != in_section(changed_events, 1)


def test_fill_changes_only_last_bar_of_last_repeat():
    from rookery.render import _render_song_audio

    project = _project()
    base = _arrange(project, [{"id": "verse", "repeat": 2, "mute": []}])
    filled = deepcopy(base)
    filled["arrangement"]["sections"][0]["fill"] = True
    filled = validate_project(filled)
    base_audio = _render_song_audio(base, 8000, fixed_gain=1)[0]
    filled_audio = _render_song_audio(filled, 8000, fixed_gain=1)[0]
    loop = round(4 * 4 * 60 / base["bpm"] * 8000)
    bar = loop // 4
    assert np.array_equal(base_audio[:loop], filled_audio[:loop])
    assert np.array_equal(base_audio[loop:2 * loop - bar], filled_audio[loop:2 * loop - bar])
    assert not np.array_equal(base_audio[2 * loop - bar:], filled_audio[2 * loop - bar:])


def test_legacy_arrangement_wav_hash_matches_pre_change_baseline():
    import hashlib

    from rookery.flock.model import apply_flock_edit, default_flock
    from rookery.render import SAMPLE_RATE, _render_song_audio, wav_bytes

    project = new_project("bb", bpm=90, bars=4, swing=0.58, genre="boom-bap")
    project["tracks"] = [
        {"id": "kick", "kind": "drum", "source": "factory:kick_punch",
         "steps": "x......x..x.....", "velocity": [1.0, 0, 0, 0, 0, 0, 0, 0.7, 0, 0, 0.9, 0, 0, 0, 0, 0]},
        {"id": "snare", "kind": "drum", "source": "factory:snare_snap",
         "steps": "....x.x.....x.x.", "velocity": [0, 0, 0, 0, 0.95, 0, 0.32, 0, 0, 0, 0, 0, 0.95, 0, 0.3, 0]},
        {"id": "hat", "kind": "drum", "source": "factory:hat_tight",
         "steps": "x.x.x.x.x.x.x.x.", "velocity": [0.55, 0, 0.35, 0, 0.55, 0, 0.35, 0, 0.55, 0, 0.35, 0, 0.55, 0, 0.35, 0],
         "choke_group": "hats"},
        {"id": "808", "kind": "bass", "source": "factory:808", "notes": [
            {"step": 0, "len": 6, "pitch": "D2"}, {"step": 10, "len": 2, "pitch": "D2"},
            {"step": 16, "len": 6, "pitch": "D2"}, {"step": 32, "len": 6, "pitch": "F2"},
            {"step": 48, "len": 6, "pitch": "A1"}]},
    ]
    project["flock"] = apply_flock_edit(default_flock(), {"action": "template", "template": "dusty_boom_bap"})
    project["master"]["fx"] = [{"type": "compressor", "threshold_db": -14, "ratio": 3},
                                {"type": "limiter", "ceiling_db": -1}]
    project["arrangement"] = {"sections": [
        {"id": "intro", "repeat": 1, "mute": ["kick", "808", "snare"]},
        {"id": "verse", "repeat": 4, "mute": []},
        {"id": "hook", "repeat": 4, "mute": []},
        {"id": "verse2", "repeat": 3, "mute": []},
        {"id": "hook2", "repeat": 3, "mute": []},
        {"id": "outro", "repeat": 1, "mute": ["kick", "808"]},
    ]}
    project = validate_project(project)
    from rookery.flock import synth as flock_synth
    cached_voice_samples = dict(flock_synth._VOICE_SAMPLE_CACHE)
    flock_synth._VOICE_SAMPLE_CACHE.clear()
    try:
        audio = _render_song_audio(project, SAMPLE_RATE)[0]
    finally:
        flock_synth._VOICE_SAMPLE_CACHE.clear()
        flock_synth._VOICE_SAMPLE_CACHE.update(cached_voice_samples)
    actual = hashlib.sha256(wav_bytes(audio, SAMPLE_RATE, "PCM_24")).hexdigest()
    assert actual == "5ea947d7fe7bc889c434478efef1d6a17ccf85e0d65cb9ae9cfe6dbe328f4028"


def test_arrangement_variety_counts_identical_iterations_and_reports_changes():
    from rookery.arrangement import arrangement_variety

    project = _project()
    project = _arrange(project, [
        {"id": "verse", "repeat": 2, "mute": []},
        {"id": "hook", "repeat": 1, "mute": ["kick"], "songs": {"bird:0": "B"},
         "steps": {"hat": "xxxxxxxxxxxxxxxx"}, "fill": True},
    ])
    result = arrangement_variety(project)
    assert result == {
        "longest_unchanged_bars": 8,
        "sections": [
            {"id": "verse", "bars": 8, "changes": []},
            {"id": "hook", "bars": 4, "changes": ["drums", "birds:0", "mute", "fill"]},
        ],
    }


def test_arrangement_receipts_and_song_render_expose_variety(tmp_path, monkeypatch):

    class Events:
        @contextmanager
        def editing(self, _name):
            yield

    monkeypatch.setenv("ROOKERY_DATA_DIR", str(tmp_path / "data"))
    from rookery.service import reset_services_for_tests
    reset_services_for_tests()
    tools.new(tmp_path / "data", "variety", 120, genre="trap")
    handler = tools.make_handler(SimpleNamespace(tools=tools, events=Events()), "rookery_apply")
    receipt = json.loads(handler({"name": "variety", "ops": [{"op": "arrange", "sections": [
        {"id": "verse", "repeat": 1, "mute": []}, {"id": "hook", "repeat": 1, "mute": ["kick"]},
    ]}]}))
    assert receipt["variety"]["sections"][1]["changes"] == ["mute"]
    rendered = Service(tmp_path / "data").render("variety", song=True)
    assert rendered["variety"] == receipt["variety"]
    assert rendered["snapshot"]["variety"] == receipt["variety"]


def test_removed_tracks_and_perches_drop_section_overrides(tmp_path):
    store = ProjectStore(tmp_path)
    store.create("override-cleanup")
    store.edit("override-cleanup", "track", action="add", id="kick", kind="drum", source="factory:kick_boom")
    store.edit("override-cleanup", "flock", action="perch", bird="echo", slot=0)
    store.edit("override-cleanup", "arrange", sections=[{"id": "hook", "repeat": 1, "mute": [],
        "steps": {"kick": "x"}, "velocity": {"kick": [0.5]}, "songs": {"bird:0": "B"}}])
    removed_track = store.edit("override-cleanup", "track", action="remove", id="kick")
    section = removed_track["project"]["arrangement"]["sections"][0]
    assert "steps" not in section and "velocity" not in section
    removed_perch = store.edit("override-cleanup", "flock", action="unperch", slot=0)
    assert "songs" not in removed_perch["project"]["arrangement"]["sections"][0]


def test_song_render_applies_choke_groups_like_the_loop():
    # An open hat must be cut by the closed hat in its choke group, in songs as in loops.
    def song(choke):
        project = new_project("choke", bpm=120, bars=4, genre="trap")
        project["tracks"] = [
            {"id": "hat", "kind": "drum", "source": "factory:hat_closed", "steps": "....x...........",
             **({"choke_group": "hats"} if choke else {})},
            {"id": "open", "kind": "drum", "source": "factory:hat_open", "steps": "x...............",
             **({"choke_group": "hats"} if choke else {})},
        ]
        project = _arrange(validate_project(project), [{"id": "a", "repeat": 1, "mute": []}])
        return render_song_audio(project)[0]
    choked, ringing = song(True), song(False)
    assert choked.shape == ringing.shape
    assert not np.allclose(choked, ringing)
