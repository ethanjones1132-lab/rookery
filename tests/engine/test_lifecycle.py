import asyncio
import importlib.util
import json
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from rookery.project import ProjectError, ProjectStore
from rookery.service import Service


ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def data_dir(tmp_path):
    return tmp_path / "data"


def _api(monkeypatch, data_dir):
    monkeypatch.setenv("ROOKERY_DATA_DIR", str(data_dir))
    name = f"lifecycle_api_{uuid4().hex}"
    spec = importlib.util.spec_from_file_location(name, ROOT / "dashboard" / "plugin_api.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return name, module


def test_create_route_blank_duplicate_validation_conflict_and_missing_source(monkeypatch, data_dir):
    name, api = _api(monkeypatch, data_dir)
    published = []
    monkeypatch.setattr(api._engine.events, "publisher", lambda plugin, event, payload: published.append((event, payload)))
    try:
        made = asyncio.run(api.create_project({}))
        assert made["project"]["name"] == "beat-1"
        assert made["rev"] == 1
        assert [(t["id"], t["source"], set(t["steps"])) for t in made["project"]["tracks"]] == [
            ("kick", "factory:kick_punch", {"."}),
            ("snare", "factory:snare_snap", {"."}),
            ("hat", "factory:hat_tight", {"."}),
        ]
        assert asyncio.run(api.create_project({}))["project"]["name"] == "beat-2"
        assert asyncio.run(api.create_project({"name": "bad name"})).status_code == 422
        assert asyncio.run(api.create_project({"name": "beat-1"})).status_code == 409
        assert asyncio.run(api.create_project({"from": "missing"})).status_code == 404

        asyncio.run(api.edit({"name": "beat-1", "op": "steps", "track": "kick", "steps": "x"}))
        copied = asyncio.run(api.create_project({"name": "copy", "from": "beat-1"}))
        assert copied["project"]["tracks"][0]["steps"] == "x" * 64
        assert copied["rev"] == 1
        asyncio.run(api.edit({"name": "copy", "op": "clear"}))
        source_after_copy_edit = asyncio.run(api.project("beat-1", None))
        assert source_after_copy_edit["project"]["tracks"][0]["steps"] == "x" * 64
        assert source_after_copy_edit["rev"] == 2
        assert any(event == "project.created" and payload.get("from") == "beat-1" for event, payload in published)
    finally:
        sys.modules.pop(name, None)


def test_rename_moves_history_render_records_and_undo_still_works(data_dir):
    store = ProjectStore(data_dir)
    store.create_lifecycle("old")
    store.edit("old", "steps", track="kick", steps="x")
    store.edit("old", "meta", bpm=101)
    service = Service(data_dir)
    old_records = service.render_dir / "projects" / "old"
    old_records.mkdir(parents=True)
    (old_records / "2.json").write_text('{"rev":2}', encoding="utf-8")

    service.rename_project("old", "new")
    assert not (data_dir / "projects" / "old").exists()
    assert list((data_dir / "projects" / "new" / "history").glob("*.json"))
    assert (service.render_dir / "projects" / "new" / "2.json").is_file()
    assert json.loads((service.render_dir / "projects" / "new" / "2.json").read_text())["name"] == "new"
    undone = store.undo("new")
    assert undone["project"]["bpm"] == 90
    assert undone["project"]["tracks"][0]["steps"] == "x" * 64
    undone = store.undo("new")
    assert undone["project"]["tracks"][0]["steps"] == "." * 64


def test_rename_and_delete_errors_and_soft_delete_location(data_dir):
    store = ProjectStore(data_dir)
    store.create_lifecycle("first")
    store.create_lifecycle("second")
    with pytest.raises(ProjectError):
        store.rename("missing", "next")
    with pytest.raises(ProjectError):
        store.rename("first", "second")
    with pytest.raises(ProjectError):
        store.rename("first", "bad name")
    with pytest.raises(ProjectError):
        store.delete("missing")
    trash = store.delete("first")
    assert trash.parent == data_dir / "trash"
    assert trash.name.startswith("first-")
    assert (trash / "project.json").is_file()
    assert not (data_dir / "projects" / "first").exists()


def test_rename_and_delete_route_shapes_and_errors(monkeypatch, data_dir):
    name, api = _api(monkeypatch, data_dir)
    try:
        asyncio.run(api.create_project({"name": "before"}))
        asyncio.run(api.create_project({"name": "occupied"}))
        renamed = asyncio.run(api.rename_project("before", {"to": "after"}))
        assert renamed["project"]["name"] == "after"
        assert asyncio.run(api.rename_project("missing", {"to": "other"})).status_code == 404
        assert asyncio.run(api.rename_project("after", {"to": "occupied"})).status_code == 409
        assert asyncio.run(api.rename_project("after", {"to": "bad name"})).status_code == 422
        deleted = asyncio.run(api.delete_project("after"))
        assert deleted == {"deleted": "after"}
        assert asyncio.run(api.delete_project("after")).status_code == 404
    finally:
        sys.modules.pop(name, None)


def test_clear_is_revisioned_diff_and_undo_restores_every_step(data_dir):
    store = ProjectStore(data_dir)
    store.create_lifecycle("clear")
    store.edit("clear", "steps", track="kick", steps="x..x")
    store.edit("clear", "steps", track="snare", steps="....x...")
    before = store.read("clear")
    cleared = store.edit("clear", "clear")
    assert cleared["rev"] == 4
    step_diffs = [item for item in cleared["diff"] if item["field"] == "steps"]
    assert [item["track"] for item in step_diffs] == ["kick", "snare"]
    assert all(item["steps"] == sorted(item["steps"]) for item in step_diffs)
    assert all(set(item["to"]) == {"."} for item in step_diffs)
    assert (cleared["project"]["bpm"], cleared["project"]["bars"], cleared["project"]["swing"], cleared["project"]["master"], cleared["project"].get("flock")) == (
        before["bpm"], before["bars"], before["swing"], before["master"], before.get("flock")
    )
    assert [
        {key: value for key, value in track.items() if key != "steps"}
        for track in cleared["project"]["tracks"]
    ] == [
        {key: value for key, value in track.items() if key != "steps"}
        for track in before["tracks"]
    ]
    restored = store.undo("clear")
    assert [track["steps"] for track in restored["project"]["tracks"]] == [track["steps"] for track in before["tracks"]]
    one = store.edit("clear", "clear", track="kick")
    assert one["project"]["tracks"][0]["steps"] == "." * 64
    assert one["project"]["tracks"][1]["steps"] == before["tracks"][1]["steps"]
    store.edit("clear", "clear")
    with pytest.raises(ProjectError, match="nothing to clear"):
        store.edit("clear", "clear")
    with pytest.raises(ProjectError, match="nothing to clear"):
        store.edit("clear", "clear", track="hat")
