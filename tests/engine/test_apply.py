"""Batch apply: one revision, one history step, and named grooves."""

from __future__ import annotations

import json
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from rookery import tools
from rookery.service import reset_services_for_tests


def _root(tmp_path, monkeypatch):
    data = tmp_path / "data"
    monkeypatch.setenv("ROOKERY_DATA_DIR", str(data))
    reset_services_for_tests()
    return data


def test_apply_batch_is_one_revision_and_undoes_as_one_step(tmp_path, monkeypatch):
    root = _root(tmp_path, monkeypatch)
    tools.new(root, "batch", 90)
    result = tools.apply(root, "batch", [
        {"op": "track", "action": "add", "id": "kick", "kind": "drum", "source": "factory:kick_boom"},
        {"op": "steps", "track": "kick", "steps": "x.....x...x....."},
        {"op": "track", "action": "add", "id": "snare", "kind": "drum", "source": "factory:snare_crack"},
        {"op": "steps", "track": "snare", "steps": "....x.......x...", "velocity": [0.9]},
        {"op": "meta", "swing": 0.58},
    ])
    assert result["rev"] == 2
    assert [track["id"] for track in result["project"]["tracks"]] == ["kick", "snare"]
    assert result["project"]["swing"] == 0.58
    assert any(item.get("field") == "swing" for item in result["diff"])

    undone = tools.undo(root, "batch", steps=1)
    assert undone["rev"] == 3
    assert undone["project"]["tracks"] == []
    assert undone["project"]["swing"] == 0


def test_apply_groove_expands_to_tracks_steps_and_swing(tmp_path, monkeypatch):
    root = _root(tmp_path, monkeypatch)
    tools.new(root, "groove", 90)
    result = tools.apply(root, "groove", [
        {"op": "groove", "groove": "theory-boom-bap-ghost", "swing": 0.42},
    ])
    tracks = {track["id"]: track for track in result["project"]["tracks"]}
    assert {"kick", "snare", "hat"} <= set(tracks)
    assert tracks["kick"]["steps"] == "x......x..x....." * 4
    assert tracks["hat"]["choke_group"] == "hats"
    assert result["project"]["swing"] == 0.42
    assert result["rev"] == 2


def test_apply_handler_returns_json_and_uses_the_latest_project(tmp_path, monkeypatch):
    root = _root(tmp_path, monkeypatch)
    tools.new(root, "handler", 90)

    class Events:
        @contextmanager
        def editing(self, name):
            yield

    engine = SimpleNamespace(tools=tools, events=Events())
    handler = tools.make_handler(engine, "rookery_apply")
    result = json.loads(handler({"ops": [
        {"op": "track", "action": "add", "id": "kick", "kind": "drum", "source": "factory:kick_boom"},
        {"op": "steps", "track": "kick", "steps": "x.....x...x....."},
    ]}))
    assert result["rev"] == 2
    assert result["name"] == "handler"
    assert result["changed"] == ["kick added", "kick steps changed (12 steps)"]


def test_sample_loop_fields_work_through_both_agent_track_handlers(tmp_path, monkeypatch):
    root = _root(tmp_path, monkeypatch)
    tools.new(root, "sample-fields", 90, bars=4, key="A", scale="minor")

    class Events:
        @contextmanager
        def editing(self, _name):
            yield

    engine = SimpleNamespace(tools=tools, events=Events())
    batch = tools.make_handler(engine, "rookery_apply")
    direct = tools.make_handler(engine, "rookery_track")
    batched = json.loads(batch({"ops": [{
        "op": "track", "action": "add", "id": "bed", "kind": "sample",
        "source": "user:library/bed.flac", "mode": "loop", "key_lock": False,
        "loop_bars": 4, "steps": "x", "role": "bed", "duck": 0.3,
    }]}))
    added = json.loads(direct({
        "action": "add", "id": "lead", "kind": "sample",
        "source": "user:library/lead.flac", "mode": "loop", "key_lock": True,
        "loop_bars": 2, "steps": "x.", "role": "lead",
    }))
    assert batched["rev"] == 2 and added["rev"] == 3
    project = tools.state(root, "sample-fields")
    assert '"mode":"loop","key_lock":false,"loop_bars":4,"duck":0.3' in project
    assert '"mode":"loop","key_lock":true,"loop_bars":2' in project

    properties = tools.SCHEMAS["rookery_apply"]["parameters"]["properties"]["ops"]["items"]["properties"]
    assert properties["mode"]["enum"] == ["oneshot", "loop"]
    assert properties["loop_bars"]["enum"] == [1, 2, 4, 8]
    assert properties["key_lock"]["type"] == "boolean"
    track_properties = tools.SCHEMAS["rookery_track"]["parameters"]["properties"]
    assert track_properties["mode"]["enum"] == ["oneshot", "loop"]


def test_apply_invalid_op_and_flock_errors_tell_agent_what_to_send(tmp_path, monkeypatch):
    root = _root(tmp_path, monkeypatch)
    tools.new(root, "bad-op", 90)

    class Events:
        @contextmanager
        def editing(self, _name):
            yield

    handler = tools.make_handler(SimpleNamespace(tools=tools, events=Events()), "rookery_apply")
    unknown = json.loads(handler({"ops": [{"op": "flokk"}]}))
    assert unknown["error"] == (
        'ops[0].op \'flokk\' is unsupported; send one of arrange, balance, clear, groove, meta, mix, '
        'steps, track, for example {"op":"steps","track":"kick","steps":"x..."}'
    )
    flock = json.loads(handler({"ops": [{"op": "flock", "action": "unperch", "slot": 0}]}))
    assert "Flock is user-controlled" in flock["error"]
    assert '"op":"steps"' in flock["error"]
    assert tools.state(root, "bad-op").count("rev 1") == 1


def test_apply_rejects_an_unknown_groove_and_a_bad_edit_atomically(tmp_path, monkeypatch):
    root = _root(tmp_path, monkeypatch)
    tools.new(root, "bad", 90)
    with pytest.raises(Exception):
        tools.apply(root, "bad", [{"op": "groove", "groove": "does-not-exist"}])
    with pytest.raises(Exception):
        tools.apply(root, "bad", [
            {"op": "track", "action": "add", "id": "kick", "kind": "drum", "source": "factory:kick_boom"},
            {"op": "steps", "track": "missing", "steps": "x"},
        ])
    state = tools.state(root, "bad")
    assert "kick" not in state
