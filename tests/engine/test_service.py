import json
from pathlib import Path

import pytest

from rookery import events, tools
from rookery.project import ValidationError
from rookery.service import Service, get_service, reset_services_for_tests


ROOT = Path(__file__).resolve().parents[2]


def test_service_edit_state_undo_and_contract_events(tmp_path):
    service = Service(tmp_path)
    events_seen = []
    old_publisher = events.publisher
    events.publisher = lambda plugin, event, payload: events_seen.append((plugin, event, payload))
    try:
        made = service.new("beat", 90, genre="boom-bap")
        assert made["rev"] == 1
        changed = service.edit({
            "name": "beat", "rev": 1, "op": "steps", "track": "kick",
            "steps": "....x...........",
        }, source="user")
        assert changed["rev"] == 2
        step_diff = next(item for item in changed["diff"] if item["field"] == "steps")
        assert step_diff["steps"] == sorted(step_diff["steps"])
        assert 0 in step_diff["steps"] and 4 in step_diff["steps"]
        assert service.get_project("beat", since=2) == {"changed": False, "rev": 2}
        assert "beat" in service.state("beat")
        undone = service.undo("beat", source="user")
        assert undone["rev"] == 3
        assert any(event == "project.updated" and payload["source"] == "user"
                   for _, event, payload in events_seen)
        assert events_seen[-1][2]["tool"] == "rookery_undo"
        with events.editing("beat"):
            assert service.get_project("beat")["agent_editing"] is True
        assert service.get_project("beat")["agent_editing"] is False
    finally:
        events.publisher = old_publisher


def test_acceptance_tools_use_service_and_return_compact_state(tmp_path):
    made = tools.new(tmp_path, "low", 142, genre=None)
    assert made["project"]["tracks"] == []
    tools.track(tmp_path, "low", "add", "sub", kind="bass", source="factory:808",
                notes=[{"step": 0, "len": 8, "pitch": "C1"}])
    changed = tools.track(tmp_path, "low", "set", "sub", notes=[{"step": 0, "len": 4, "pitch": "F1"}])
    assert changed["project"]["tracks"][0]["notes"][0]["pitch"] == "F1"
    assert "sub" in tools.state(tmp_path, "low")


def test_state_exposes_persisted_mixer_velocity_and_fx(tmp_path):
    service = Service(tmp_path)
    service.new("mix", 120)
    service.edit({"name": "mix", "op": "track", "action": "add", "id": "hat",
                  "kind": "drum", "source": "factory:hat_open", "steps": "x...",
                  "choke_group": "hats", "gain_db": -6, "pan": 0.25, "mute": True,
                  "solo": False, "pitch": 2, "velocity": [0.2, 0.7],
                  "fx": [{"type": "highpass", "cutoff_hz": 120}]}, source="user")
    service.edit({"name": "mix", "op": "mix", "target": "master",
                  "fx": [{"type": "limiter", "ceiling_db": -1}]}, source="user")
    state = tools.state(tmp_path, "mix")
    assert "hat (drum, factory:hat_open)" in state
    assert '"gain_db":-6,"pan":0.25,"mute":true,"solo":false,"pitch":2' in state
    assert '"velocity":[0.2,0.7]' in state
    assert '"type":"highpass","cutoff_hz":120' in state
    assert '"choke_group":"hats"' in state
    assert 'master fx: [{"type":"limiter","ceiling_db":-1}]' in state


def test_master_track_shortcut_edits_swing_and_undoes(tmp_path):
    tools.new(tmp_path, "low", 142)
    changed = tools.track(tmp_path, "low", "set", "master", swing=0.5)
    assert changed["project"]["swing"] == 0.5
    assert "swing 0.5" in tools.state(tmp_path, "low")
    undone = tools.undo(tmp_path, "low")
    assert undone["project"]["swing"] == 0


@pytest.mark.parametrize("fields", [
    {},
    {"swing": 0.5, "gain_db": 2},
    {"choke_group": "hats"},
    {"swing": 1.1},
])
def test_invalid_master_track_args_do_not_write_or_bump_revision(tmp_path, fields):
    service = Service(tmp_path)
    service.new("low", 142)
    before = service.get_project("low")["project"]
    with pytest.raises(ValidationError):
        tools.track(tmp_path, "low", "set", "master", **fields)
    after = service.get_project("low")["project"]
    assert after["rev"] == before["rev"]
    assert after["swing"] == before["swing"]


def test_get_service_is_cached_by_data_directory_and_settings(tmp_path):
    reset_services_for_tests()
    first = get_service(tmp_path, user_kit_dir=tmp_path / "kit-a")
    same = get_service(tmp_path, user_kit_dir=tmp_path / "kit-a")
    other = get_service(tmp_path, user_kit_dir=tmp_path / "kit-b")
    assert first is same
    assert first is not other


def test_kits_credits_map_soundza_and_openverse_files(tmp_path):
    kit = tmp_path / "kit"
    (kit / "library").mkdir(parents=True)
    (kit / "library" / "credits.json").write_text(json.dumps({
        "soundza:cmudkgpuo000409gmjonfn7qq": {
            "file": "skipit-horns.flac", "source": "soundza", "title": "Skipit Horns",
            "creator": "Antronical", "landing_url": "https://soundza.com/sound/skipit-horns",
            "license_url": "https://soundza.com/license",
        },
        "abc": {
            "file": "CC0-kick.wav", "title": "Dusty Kick", "creator": "someone",
            "license_url": "https://creativecommons.org/publicdomain/zero/1.0/",
        },
    }), encoding="utf-8")
    service = Service(tmp_path / "data", user_kit_dir=kit)
    assert service.kits()["credits"] == {
        "library/skipit-horns.flac": {
            "source": "soundza", "title": "Skipit Horns", "creator": "Antronical",
            "landing_url": "https://soundza.com/sound/skipit-horns",
            "license_url": "https://soundza.com/license",
        },
        "library/CC0-kick.wav": {
            "source": "openverse", "title": "Dusty Kick", "creator": "someone",
            "landing_url": None,
            "license_url": "https://creativecommons.org/publicdomain/zero/1.0/",
        },
    }
    assert service.status()["kits"]["credits"] == service.kits()["credits"]


def test_kits_credits_are_empty_when_the_credit_file_is_missing(tmp_path):
    service = Service(tmp_path / "data", user_kit_dir=tmp_path / "absent-kit")
    assert service.kits()["credits"] == {}


@pytest.mark.parametrize("payload", [
    "{not json",
    "[]",
    '"text"',
    json.dumps({"bad": "entry", "also": {"title": "no file"}, "ok": {"file": ""}}),
])
def test_kits_credits_are_empty_when_the_credit_file_is_malformed(tmp_path, payload):
    kit = tmp_path / "kit"
    (kit / "library").mkdir(parents=True)
    (kit / "library" / "credits.json").write_text(payload, encoding="utf-8")
    service = Service(tmp_path / "data", user_kit_dir=kit)
    assert service.kits()["credits"] == {}


def test_render_snapshot_survives_later_project_edit(tmp_path):
    service = Service(tmp_path)
    service.new("beat", 90, genre="boom-bap")
    rendered = service.render("beat")
    snapshot = json.loads(json.dumps(rendered["snapshot"]))
    service.edit({"name": "beat", "op": "steps", "track": "kick", "steps": ".x.............."}, source="user")
    assert rendered["snapshot"] == snapshot
    assert snapshot["rev"] == 1
    assert service.get_project("beat")["render"] is None


def test_reloaded_render_view_keeps_the_audio_hash(tmp_path):
    service = Service(tmp_path)
    service.new("beat", 90, genre="boom-bap")
    rendered = service.render("beat")
    view = service.get_project("beat")["render"]
    assert view["hash"] == rendered["hash"]
    assert view["wav_hash"] == rendered["wav_hash"]
    assert len(view["wav_hash"]) == 64
