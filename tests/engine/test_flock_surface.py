"""Tool, REST, state, render-view, and determinism tests for the Flock surface."""

from __future__ import annotations

import asyncio
import copy
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import types
from pathlib import Path

import numpy as np
import pytest

from rookery import events, tools
from rookery.flock.model import default_flock, load_catalog
from rookery.project import canonical_project, new_project, validate_project
from rookery.service import Service, get_service, reset_services_for_tests


ROOT = Path(__file__).resolve().parents[2]
CATALOG_KEYS = {
    "scales", "chordTables", "registers", "birds", "corvus", "templates",
    "combos", "comboSongs", "secretUnlock",
}
RENDER_VIEW_KEYS = (
    "hash", "rev", "audio_url", "report", "meters", "duration_samples",
    "sample_rate", "flock_events", "kick_onsets", "flock_active_combos",
    "balance", "mix_notes", "ref", "fit",
)


def _load_api(name):
    spec = importlib.util.spec_from_file_location(
        name, ROOT / "dashboard" / "plugin_api.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _mock_renderer(monkeypatch, metadata):
    """Install a fast renderer whose cached metadata is easy to compare."""
    import rookery.checks as checks
    import rookery.render as renderer

    wav_data = b"RIFF-mock-flock-wav"

    def fake_render_project(project, output_dir, user_kit_dir=None):
        digest = hashlib.sha256(
            (canonical_project(project) + renderer.RENDERER_VERSION).encode("utf-8")
        ).hexdigest()
        path = Path(output_dir) / f"{digest}.wav"
        path.write_bytes(wav_data)
        expected = round(
            int(project["bars"]) * 4 * 60 / float(project["bpm"])
            * renderer.SAMPLE_RATE
        )
        return {
            "path": str(path),
            "hash": digest,
            "wav_hash": hashlib.sha256(wav_data).hexdigest(),
            "meters": {"kick": {"rms_db": -12.0, "peak_db": -3.0}},
            "duration_samples": expected,
            "sample_rate": renderer.SAMPLE_RATE,
            **copy.deepcopy(metadata),
        }

    monkeypatch.setattr(renderer, "render_project", fake_render_project)
    monkeypatch.setattr(
        renderer, "render_audio",
        lambda *args, **kwargs: (np.zeros((1, 2), dtype=np.float32), {}),
    )
    monkeypatch.setattr(renderer, "wav_bytes", lambda *args, **kwargs: wav_data)
    monkeypatch.setattr(
        checks, "evaluate_file",
        lambda path, expected, deterministic=None, target_lufs=-14.0: {
            name: {"pass": True, "value": 0, "target": "mock"}
            for name in (
                "length_exact", "no_clipping", "loudness",
                "seam_click", "not_silent", "deterministic",
            )
        },
    )


def test_catalog_route_is_shared_json_and_mutation_isolated(monkeypatch, tmp_path):
    monkeypatch.setenv("ROOKERY_DATA_DIR", str(tmp_path / "data"))
    api = _load_api("hermes_dashboard_plugin_rookery_catalog")
    try:
        catalog = asyncio.run(api.flock_catalog())
        assert set(catalog) == CATALOG_KEYS
        assert len(catalog["birds"]) == 12
        assert catalog["secretUnlock"]["seenRequired"] == [
            bird["id"] for bird in catalog["birds"]
        ]
        json.dumps(catalog)

        catalog["birds"].clear()
        catalog["scales"]["dorian"]["family"] = "mutated"
        again = asyncio.run(api.flock_catalog())
        assert len(again["birds"]) == 12
        assert again["scales"]["dorian"]["family"] != "mutated"
        assert set(again) == CATALOG_KEYS
    finally:
        sys.modules.pop("hermes_dashboard_plugin_rookery_catalog", None)


def test_user_edit_to_tool_state_then_undo_and_stale_409(monkeypatch, tmp_path):
    data_dir = tmp_path / "data"
    monkeypatch.setenv("ROOKERY_DATA_DIR", str(data_dir))
    reset_services_for_tests()
    api = _load_api("hermes_dashboard_plugin_rookery_user_edit")
    try:
        asyncio.run(api._run("new", "wire", 90, genre="boom-bap", source="user"))
        landed = asyncio.run(api.edit({
            "name": "wire", "op": "flock", "action": "template",
            "template": "dusty_boom_bap",
        }))
        assert landed["rev"] == 2
        assert landed["project"]["flock"]["weather"] == "dust"

        state = tools.state(data_dir, "wire")
        assert "Wire (D dorian, i-IV-VII-III, dust):" in state
        assert "[1 Bramble A]" in state
        assert "[4 Echo C]" in state

        perch = asyncio.run(api.edit({
            "name": "wire", "op": "flock", "action": "perch", "bird": "jinx",
        }))
        assert perch["rev"] == 3
        assert perch["project"]["flock"]["perches"][4]["bird"] == "jinx"

        stale = asyncio.run(api.edit({
            "name": "wire", "op": "flock", "action": "weather",
            "weather": "rain", "rev": 1,
        }))
        assert stale.status_code == 409
        assert set(json.loads(stale.body)) == {"message", "rev"}
        assert json.loads(stale.body)["rev"] == 3

        undone = asyncio.run(api.undo({"name": "wire"}))
        assert undone["rev"] == 4
        assert undone["project"]["flock"]["perches"][4] is None
        assert "Bramble A" in tools.state(data_dir, "wire")
    finally:
        sys.modules.pop("hermes_dashboard_plugin_rookery_user_edit", None)
        reset_services_for_tests()


def test_malformed_flock_action_is_422_and_matches_tool_validation(monkeypatch, tmp_path):
    data_dir = tmp_path / "data"
    monkeypatch.setenv("ROOKERY_DATA_DIR", str(data_dir))
    reset_services_for_tests()
    api = _load_api("hermes_dashboard_plugin_rookery_bad_action")
    try:
        asyncio.run(api._run("new", "bad", 90, source="user"))
        response = asyncio.run(api.edit({
            "name": "bad", "op": "flock", "action": "fly",
        }))
        assert response.status_code == 422
        message = json.loads(response.body)["message"]
        assert "unknown flock action" in message
        assert api._engine.events.is_editing("bad") is False
    finally:
        sys.modules.pop("hermes_dashboard_plugin_rookery_bad_action", None)
        reset_services_for_tests()


def test_template_diff_lands_in_role_order_and_preserves_null_slots(tmp_path):
    service = Service(tmp_path / "data")
    service.new("lands", 90)
    changed = service.edit({
        "name": "lands", "op": "flock", "action": "template",
        "template": "dusty_boom_bap",
    }, source="user")
    half = [row for row in changed["diff"]
            if row["field"] == "flock" and row["change"] == "template"]
    assert len(half) == 4
    assert [row["bird"] for row in half] == ["bramble", "quill", "hush", "echo"]
    assert [row["slot"] for row in half] == [0, 1, 2, 3]
    assert all(row["from"] is None for row in half)
    perches = changed["project"]["flock"]["perches"]
    assert len(perches) == 6
    assert perches[4:] == [None, None]
    assert perches[0] == {"bird": "bramble", "song": "A", "mute": False, "solo": False}


def test_all_eleven_tool_schemas_and_handlers_are_registered(monkeypatch, tmp_path):
    monkeypatch.setenv("ROOKERY_DATA_DIR", str(tmp_path / "data"))
    spec = importlib.util.spec_from_file_location(
        "rookery_surface_plugin", ROOT / "__init__.py",
        submodule_search_locations=[str(ROOT)],
    )
    plugin = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = plugin
    spec.loader.exec_module(plugin)
    try:
        ctx = types.SimpleNamespace(tools={})
        ctx.register_tool = lambda **kwargs: ctx.tools.update({kwargs["name"]: kwargs})
        plugin.register(ctx)

        expected = {
            "rookery_new", "rookery_steps", "rookery_track", "rookery_mix",
            "rookery_apply", "rookery_render", "rookery_state", "rookery_undo",
            "rookery_kits", "rookery_export", "rookery_samples",
        }
        assert set(ctx.tools) == expected
        for name, tool in ctx.tools.items():
            assert callable(tool["handler"])
            assert tool["schema"]["name"] == name
            assert tool["schema"]["description"]
            parameters = tool["schema"]["parameters"]
            assert parameters["type"] == "object"
            for field, spec_ in parameters["properties"].items():
                assert spec_.get("description"), (name, field)
        assert "rookery_flock" not in ctx.tools
        apply_ops = ctx.tools["rookery_apply"]["schema"]["parameters"]["properties"]["ops"]["items"]
        assert "flock" not in apply_ops["properties"]["op"]["enum"]
    finally:
        sys.modules.pop("rookery_surface_plugin", None)


def test_user_flock_edit_harmony_weather_perch_song_mute_and_solo_paths(monkeypatch, tmp_path):
    data_dir = tmp_path / "data"
    monkeypatch.setenv("ROOKERY_DATA_DIR", str(data_dir))
    reset_services_for_tests()
    service = Service(data_dir)
    service.new("paths", 90, source="user")

    edit = lambda action, **fields: service.edit(
        {"name": "paths", "op": "flock", "action": action, **fields}, source="user",
    )
    harmony = edit("harmony", key="Eb", scale="minor", progression=["i", "VI", "III", "VII"])
    assert harmony["project"]["flock"]["key"] == "D#"
    assert harmony["project"]["flock"]["progression"] == ["i", "VI", "III", "VII"]

    perched = edit("perch", bird="bramble", slot=0)
    assert perched["project"]["flock"]["perches"][0] == {
        "bird": "bramble", "song": "A", "mute": False, "solo": False,
    }
    song = edit("song", bird="bramble", song="B")
    assert song["project"]["flock"]["perches"][0]["song"] == "B"
    muted = edit("mute", bird="bramble", on=True)
    assert muted["project"]["flock"]["perches"][0]["mute"] is True
    soloed = edit("solo", bird="bramble", on=True)
    assert soloed["project"]["flock"]["perches"][0]["solo"] is True
    weather = edit("weather", weather="wind")
    assert weather["project"]["flock"]["weather"] == "wind"
    unperched = edit("unperch", slot=0)
    assert unperched["project"]["flock"]["perches"][0] is None


def test_editing_events_and_origin_attribution_for_flock(monkeypatch, tmp_path):
    data_dir = tmp_path / "data"
    monkeypatch.setenv("ROOKERY_DATA_DIR", str(data_dir))
    reset_services_for_tests()
    service = get_service()
    service.new("origins", 90)
    seen = []
    old_publisher = events.publisher
    events.publisher = lambda plugin, event, payload: seen.append((plugin, event, payload))
    try:
        service.edit({
            "name": "origins", "op": "flock", "action": "perch", "bird": "bramble",
        }, source="user")
        update = [payload for _, event, payload in seen if event == "project.updated"][-1]
        assert update["source"] == "user"
        assert update["tool"] is None

        service.edit({
            "name": "origins", "op": "flock", "action": "weather",
            "weather": "dust",
        }, source="user")
        update = [payload for _, event, payload in seen if event == "project.updated"][-1]
        assert update["source"] == "user"
        assert update["tool"] is None

        assert events.is_editing("origins") is False
    finally:
        events.publisher = old_publisher
        reset_services_for_tests()


def test_mocked_render_metadata_is_cached_and_served_consistently(
    monkeypatch, tmp_path,
):
    service = Service(tmp_path / "data")
    service.new("cached", 90, genre="boom-bap")
    service.edit({
        "name": "cached", "op": "flock", "action": "template",
        "template": "dusty_boom_bap",
    }, source="user")
    metadata = {
        "flock_events": {
            "bramble": [{"t": 0.0, "len": 0.5, "midi": 36, "vel": 1.0}],
        },
        "kick_onsets": [0.0, 1.3333333333333333],
        "flock_active_combos": ["parliament"],
    }
    _mock_renderer(monkeypatch, metadata)

    first = service.render("cached")
    for key, value in metadata.items():
        assert first[key] == value
    assert first["snapshot"]["flock"]["perches"][4] is None

    import rookery.render as renderer

    monkeypatch.setattr(
        renderer, "render_project",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("cache hit must not rerender")
        ),
    )
    second = service.render("cached")
    for key, value in metadata.items():
        assert second[key] == value

    view = service.get_project("cached")["render"]
    assert set(RENDER_VIEW_KEYS) <= set(view)
    assert {key: view[key] for key in RENDER_VIEW_KEYS} == {
        key: first[key] for key in RENDER_VIEW_KEYS
    }

    immutable = copy.deepcopy(first["snapshot"])
    service.edit({
        "name": "cached", "op": "flock", "action": "song",
        "bird": "bramble", "song": "B",
    }, source="user")
    assert first["snapshot"] == immutable
    assert immutable["flock"]["perches"][0]["song"] == "A"


def test_legacy_cache_without_metadata_rederives_without_reencoding(
    monkeypatch, tmp_path,
):
    service = Service(tmp_path / "data")
    service.new("legacy", 90, genre="boom-bap")
    service.edit({
        "name": "legacy", "op": "flock", "action": "perch", "bird": "bramble",
    }, source="user")
    metadata = {
        "flock_events": {"bramble": [{"t": 0.0, "len": 0.25, "midi": 40, "vel": 0.9}]},
        "kick_onsets": [0.0],
        "flock_active_combos": [],
    }
    _mock_renderer(monkeypatch, metadata)
    first = service.render("legacy")
    report_path = service.render_dir / f"{first['hash']}.json"
    record = json.loads(report_path.read_text(encoding="utf-8"))
    wav_hash = record["wav_hash"]
    for key in metadata:
        record.pop(key)
    report_path.write_text(json.dumps(record), encoding="utf-8")

    import rookery.service as service_module
    import rookery.render as renderer

    monkeypatch.setattr(
        service_module, "_derived_render_metadata",
        lambda project: copy.deepcopy(metadata),
    )
    monkeypatch.setattr(
        renderer, "render_project",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("legacy metadata must be rederived, not re-rendered")
        ),
    )
    view_before = service.get_project("legacy")["render"]
    for key, value in metadata.items():
        assert view_before[key] == value
    again = service.render("legacy")
    assert again["wav_hash"] == wav_hash
    for key, value in metadata.items():
        assert again[key] == value
    restored = json.loads(report_path.read_text(encoding="utf-8"))
    assert restored["wav_hash"] == wav_hash
    assert all(key in restored for key in metadata)
    view = service.get_project("legacy")["render"]
    for key, value in metadata.items():
        assert view[key] == value


def test_legacy_cache_without_mix_fields_renders_once_and_keeps_wav_hash(
    monkeypatch, tmp_path,
):
    service = Service(tmp_path / "data")
    service.new("legacy-mix", 90, genre="boom-bap")
    _mock_renderer(monkeypatch, {
        "flock_events": {}, "kick_onsets": [], "flock_active_combos": [],
    })
    first = service.render("legacy-mix")
    report_path = service.render_dir / f"{first['hash']}.json"
    record = json.loads(report_path.read_text(encoding="utf-8"))
    for key in ("balance", "mix_notes", "ref", "fit"):
        record.pop(key)
    report_path.write_text(json.dumps(record), encoding="utf-8")

    import rookery.render as renderer

    original_render = renderer.render_project
    render_calls = 0

    def counted_render(*args, **kwargs):
        nonlocal render_calls
        render_calls += 1
        return original_render(*args, **kwargs)

    monkeypatch.setattr(renderer, "render_project", counted_render)
    refreshed = service.render("legacy-mix")
    assert render_calls == 1
    assert refreshed["wav_hash"] == first["wav_hash"]
    assert all(key in refreshed for key in ("balance", "mix_notes", "ref", "fit"))

    service.render("legacy-mix")
    assert render_calls == 1


def test_tool_snapshot_preserves_nulls_solo_and_seventh_corvus():
    catalog = load_catalog()
    flock = {
        **default_flock(),
        "perches": [
            {"bird": "bramble", "song": "A", "mute": True, "solo": False},
            None,
            {"bird": "quill", "song": "B", "mute": False, "solo": True},
            None,
            None,
            None,
            {"bird": "corvus", "song": "A", "mute": False, "solo": False},
        ],
        "seen": [bird["id"] for bird in catalog["birds"]],
    }
    project = new_project("snapshot", 90, genre="boom-bap")
    project["rev"] = 1
    project["flock"] = validate_project({**project, "flock": flock})["flock"]
    view = {"hash": "a" * 64, "duration_samples": 470400, "report": {}, "meters": {}}
    snapshot = Service._tool_snapshot(project, view, Path("ignored.wav"))
    assert len(snapshot["flock"]["perches"]) == 7
    assert snapshot["flock"]["perches"][1] is None
    assert snapshot["flock"]["perches"][0] == {
        "bird": "bramble", "song": "A", "mute": True, "solo": False,
    }
    assert snapshot["flock"]["perches"][2] == {
        "bird": "quill", "song": "B", "mute": False, "solo": True,
    }
    assert snapshot["flock"]["perches"][6] == {
        "bird": "corvus", "song": "A", "mute": False, "solo": False,
    }
    assert "seen" not in snapshot["flock"]
    assert [track["id"] for track in snapshot["tracks"]] == ["kick", "snare", "hat"]


def test_integration_real_flock_render_metadata_cache_and_snapshot(tmp_path):
    service = Service(tmp_path / "data")
    service.new("real-flock", 90, genre="boom-bap")
    service.edit({
        "name": "real-flock", "op": "flock", "action": "template",
        "template": "dusty_boom_bap",
    }, source="user")
    service.edit({
        "name": "real-flock", "op": "flock", "action": "perch", "bird": "jinx",
    }, source="user")
    service.edit({
        "name": "real-flock", "op": "flock", "action": "perch", "bird": "tick",
    }, source="user")

    first = service.render("real-flock")
    assert first["sample_rate"] == 44100
    assert first["duration_samples"] == round(4 * 4 * 60 / 90 * 44100)
    assert first["flock_events"]
    assert "bramble" in first["flock_events"]
    assert first["balance"]
    assert "bird:0" in first["balance"]
    assert isinstance(first["mix_notes"], list) and len(first["mix_notes"]) <= 5
    assert first["ref"] == "kick:kick"
    for bird_events in first["flock_events"].values():
        for note in bird_events:
            assert set(note) == {"t", "len", "midi", "vel"}
            assert note["len"] > 0
            assert 0 <= note["vel"] <= 1
    assert first["kick_onsets"]
    assert "parliament" in first["flock_active_combos"]
    assert set(first["report"]) == {
        "length_exact", "no_clipping", "loudness", "seam_click",
        "not_silent", "deterministic",
    }
    assert all(check["pass"] for check in first["report"].values()), first["report"]

    snapshot = copy.deepcopy(first["snapshot"])
    perches = snapshot["flock"]["perches"]
    assert len(perches) == 6
    assert [perch["bird"] for perch in perches] == [
        "bramble", "quill", "hush", "echo", "jinx", "tick",
    ]
    assert all(perch["mute"] is False for perch in perches)

    cached = service.render("real-flock")
    for key in ("hash", "rev", "flock_events", "kick_onsets", "flock_active_combos",
                "balance", "mix_notes", "ref", "fit"):
        assert cached[key] == first[key]
    view = service.get_project("real-flock")["render"]
    for key in RENDER_VIEW_KEYS:
        assert view[key] == cached[key]

    service.edit({
        "name": "real-flock", "op": "flock", "action": "song",
        "bird": "bramble", "song": "B",
    }, source="user")
    assert first["snapshot"] == snapshot


def test_song_render_omits_loop_only_balance_fields(tmp_path):
    service = Service(tmp_path / "data")
    service.new("song-no-balance", 120, genre="trap")
    service.edit({
        "name": "song-no-balance", "op": "arrange",
        "sections": [{"id": "verse", "repeat": 1, "mute": []}],
    })
    result = service.render("song-no-balance", song=True)
    loop_only = {"balance", "mix_notes", "ref", "fit"}
    assert not loop_only.intersection(result)
    assert not loop_only.intersection(result["snapshot"])


def test_integration_full_pcm24_mix_is_byte_deterministic_across_hash_seeds():
    source_root = ROOT.resolve()
    script = r"""
import hashlib
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, sys.argv[1])
from rookery.checks import evaluate_file
from rookery.flock.model import apply_flock_edit
from rookery.project import new_project, validate_project
from rookery.render import render_project

project = new_project(
    "deterministic", 90, bars=4, genre="boom-bap", swing=0.25, seed=721,
)
flock = apply_flock_edit(None, {"action": "template", "template": "dusty_boom_bap"})
flock = apply_flock_edit(flock, {"action": "perch", "bird": "jinx"})
flock = apply_flock_edit(flock, {"action": "perch", "bird": "tick"})
project["flock"] = flock
project = validate_project(project)

with tempfile.TemporaryDirectory() as output:
    rendered = render_project(project, output)
    wav = Path(rendered["path"]).read_bytes()
    expected = round(
        project["bars"] * 4 * 60 / float(project["bpm"]) * rendered["sample_rate"]
    )
    report = evaluate_file(rendered["path"], expected, deterministic=True)
    print(json.dumps({
        "wav_sha256": hashlib.sha256(wav).hexdigest(),
        "wav_hash": rendered["wav_hash"],
        "content_hash": rendered["hash"],
        "duration_samples": rendered["duration_samples"],
        "sample_rate": rendered["sample_rate"],
        "flock_events": rendered["flock_events"],
        "kick_onsets": rendered["kick_onsets"],
        "flock_active_combos": rendered["flock_active_combos"],
        "report": report,
    }, sort_keys=True))
"""

    env_a, env_b = os.environ.copy(), os.environ.copy()
    env_a.pop("PYTHONPATH", None)
    env_b.pop("PYTHONPATH", None)
    env_a["PYTHONHASHSEED"] = "0"
    env_b["PYTHONHASHSEED"] = "91"
    args = [sys.executable, "-c", script, str(source_root)]
    with tempfile.TemporaryDirectory() as unrelated_cwd:
        first = subprocess.run(
            args, cwd=unrelated_cwd, env=env_a,
            capture_output=True, text=True, check=True,
        )
        second = subprocess.run(
            args, cwd=unrelated_cwd, env=env_b,
            capture_output=True, text=True, check=True,
        )

    assert first.stdout == second.stdout
    payload = json.loads(first.stdout)
    assert payload["sample_rate"] == 44100
    assert payload["duration_samples"] == round(4 * 4 * 60 / 90 * 44100)
    assert payload["wav_sha256"] == payload["wav_hash"]
    assert payload["flock_events"]
    assert payload["kick_onsets"]
    assert "parliament" in payload["flock_active_combos"]
    assert set(payload["report"]) == {
        "length_exact", "no_clipping", "loudness", "seam_click",
        "not_silent", "deterministic",
    }
    assert all(check["pass"] for check in payload["report"].values()), payload["report"]
