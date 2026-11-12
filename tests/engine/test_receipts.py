"""Compact chat receipts, revision deltas, safe loop patterns, and humanization."""

from __future__ import annotations

import json
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from rookery import tools
from rookery.project import ValidationError, canonical_project, project_hash
from rookery.service import get_service, reset_services_for_tests


def _root(tmp_path, monkeypatch):
    data = tmp_path / "data"
    monkeypatch.setenv("ROOKERY_DATA_DIR", str(data))
    reset_services_for_tests()
    return data


class _Events:
    @contextmanager
    def editing(self, _name):
        yield


def _handler(tool_name):
    return tools.make_handler(SimpleNamespace(tools=tools, events=_Events()), tool_name)


def _call(tool_name, **params):
    return json.loads(_handler(tool_name)(params))


def test_edit_receipt_is_compact_and_describes_changes(tmp_path, monkeypatch):
    _root(tmp_path, monkeypatch)
    made = _call("rookery_new", name="receipt", bpm=90, bars=8)
    assert made == {"name": "receipt", "rev": 1, "changed": []}
    added = _call("rookery_track", name="receipt", action="add", id="kick",
                  kind="drum", source="factory:kick_boom")
    assert added["name"] == "receipt" and added["rev"] == 2
    assert "kick added" in added["changed"]
    edited = _call("rookery_steps", name="receipt", track="kick", steps="x......." * 16)
    encoded = json.dumps(edited, separators=(",", ":")).encode()
    assert len(encoded) < 800
    assert edited["changed"] == ["kick steps changed (16 steps)"]

    receipts = [
        _call("rookery_mix", name="receipt", target="master", fx=[{"type": "limiter", "ceiling_db": -1}]),
        _call("rookery_apply", name="receipt", ops=[{"op": "meta", "bpm": 92}]),
        _call("rookery_undo", name="receipt"),
    ]
    assert all(item["name"] == "receipt" and isinstance(item["changed"], list) for item in receipts)
    assert all(len(json.dumps(item, separators=(",", ":")).encode()) < 800 for item in receipts)
    assert "master fx changed" in receipts[0]["changed"]
    assert receipts[1]["changed"] == ["bpm changed"]


def test_state_since_returns_user_and_agent_changes(tmp_path, monkeypatch):
    root = _root(tmp_path, monkeypatch)
    tools.new(root, "history", 90)
    start_rev = get_service(root).store.read("history")["rev"]
    get_service(root).edit({"name": "history", "op": "track", "action": "add",
                            "id": "kick", "kind": "drum", "source": "factory:kick_boom"},
                           source="user", tool="dashboard")
    tools.steps(root, "history", "kick", "x.......")
    delta = _call("rookery_state", name="history", since=start_rev)
    assert delta["rev"] == 3
    assert [change["source"] for change in delta["changes"]] == ["user", "agent"]
    assert "kick added" in delta["changes"][0]["changed"]
    assert any("kick steps" in line for line in delta["changes"][1]["changed"])
    missing = _call("rookery_state", name="history", since=0)
    assert "no longer in history" in missing["note"]
    assert "history | rev 3" in missing["state"]


def test_non_divisor_rejected_in_single_and_batch_edits(tmp_path, monkeypatch):
    root = _root(tmp_path, monkeypatch)
    tools.new(root, "divisor", 90, bars=4)
    tools.track(root, "divisor", "add", "kick", kind="drum", source="factory:kick_boom")
    expected = "steps length 15 does not divide the 64-step loop; use 1, 2, 4, 8, 16, 32 or 64"
    with pytest.raises(ValidationError, match="steps length 15 does not divide") as single:
        tools.steps(root, "divisor", "kick", "x" * 15)
    assert str(single.value) == expected
    with pytest.raises(ValidationError, match="steps length 15 does not divide") as batch:
        tools.apply(root, "divisor", [{"op": "steps", "track": "kick", "steps": "x" * 15}])
    assert str(batch.value) == expected


def test_humanize_meta_is_validated_undoable_and_deterministic(tmp_path, monkeypatch):
    root = _root(tmp_path, monkeypatch)
    tools.new(root, "human", 90)
    tools.track(root, "human", "add", "kick", kind="drum", source="factory:kick_boom")
    tools.steps(root, "human", "kick", "x.......")
    before = get_service(root).store.read("human")
    unhumanized_key = canonical_project(before)
    result = tools.track(root, "human", "set", "master", humanize_ms=3.5)
    assert result["project"]["humanize_ms"] == 3.5
    assert tools.SCHEMAS["rookery_track"]["parameters"]["properties"]["humanize_ms"]["maximum"] == 6
    assert tools.SCHEMAS["rookery_apply"]["parameters"]["properties"]["ops"]["items"]["properties"]["humanize_ms"]["minimum"] == 0
    assert "humanize 3.5 ms" in tools.state(root, "human")
    with pytest.raises(ValidationError, match="humanize_ms must be between 0 and 6"):
        tools.track(root, "human", "set", "master", humanize_ms=6.1)
    undone = tools.undo(root, "human")
    assert "humanize_ms" not in undone["project"]
    assert not {key for key in undone["project"] if key.startswith("_history_change_") or key == "_history_to_rev"}
    assert canonical_project(undone["project"]) == unhumanized_key

    from rookery.render import render_audio, wav_bytes

    humanized = tools.track(root, "human", "set", "master", humanize_ms=3.5)["project"]
    first, _ = render_audio(humanized)
    second, _ = render_audio(humanized)
    assert wav_bytes(first, 44100, "PCM_24") == wav_bytes(second, 44100, "PCM_24")


def test_project_without_humanize_keeps_legacy_audio_hash(tmp_path, monkeypatch):
    root = _root(tmp_path, monkeypatch)
    project = tools.new(root, "hash-compat", 90)["project"]
    assert "humanize_ms" not in project
    render_version = "rookery-render-2;cyclic-hp;per-track-fx;bar-tail;numpy=2.4.3;scipy=1.17.1;pedalboard=0.9.26;soundfile=0.14.0;pyloudnorm=0.2.0"
    assert project["mix_profile"] == "targets-v1"
    assert project_hash(project, render_version) == "00b695bdb699f041ec260d4cb1dcbfe0ec763d183d0759c5f7dfacb95911f5f5"
    legacy = {**project}
    legacy.pop("mix_profile")
    assert project_hash(legacy, render_version) == "350452fb7e457170f6c96869f0a36514bc344a8c5e0d1d342bb429150d057d41"
