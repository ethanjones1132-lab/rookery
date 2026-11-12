import asyncio
import importlib.util
import json
import subprocess
import sys
import time
import types
from pathlib import Path

import pytest
from starlette.responses import JSONResponse


ROOT = Path(__file__).resolve().parents[2]


def _load(name, path, package=False):
    kwargs = {"submodule_search_locations": [str(path.parent)]} if package else {}
    spec = importlib.util.spec_from_file_location(name, path, **kwargs)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("order", [("root", "api"), ("api", "root")])
def test_hermes_root_and_standalone_api_share_engine_from_unrelated_cwd(
    order, monkeypatch, tmp_path
):
    unrelated = tmp_path / "unrelated"
    unrelated.mkdir()
    monkeypatch.chdir(unrelated)
    data_dir = tmp_path / "data"
    monkeypatch.setenv("ROOKERY_DATA_DIR", str(data_dir))
    path_before = list(sys.path)
    parent_created = "hermes_plugins" not in sys.modules
    if parent_created:
        parent = types.ModuleType("hermes_plugins")
        parent.__path__ = []
        parent.__package__ = "hermes_plugins"
        sys.modules["hermes_plugins"] = parent
    root_name = f"hermes_plugins.rookery_test_{order[0]}"
    api_name = f"hermes_dashboard_plugin_rookery_test_{order[0]}"
    loaded = {}
    try:
        for item in order:
            if item == "root":
                loaded["root"] = _load(root_name, ROOT / "__init__.py", package=True)
            else:
                loaded["api"] = _load(api_name, ROOT / "dashboard" / "plugin_api.py")
        plugin = loaded["root"]
        api = loaded["api"]
        engine = plugin.load_engine(ROOT)
        assert api._engine is engine
        assert api._engine.service is engine.service
        service = engine.service.get_service()
        assert api._engine.service.get_service() is service
        ctx = type("Context", (), {"register_tool": lambda self, **args: self.tools.update({args["name"]: args})})()
        ctx.tools = {}
        plugin.register(ctx)

        original_new = service.new

        def inspect_editing(*args, **kwargs):
            assert api._engine.service.get_service() is service
            assert api._engine.events.is_editing("shared")
            return original_new(*args, **kwargs)

        service.new = inspect_editing
        returned = json.loads(ctx.tools["rookery_new"]["handler"](
            {"name": "shared", "bpm": 90, "genre": "boom-bap"}
        ))
        assert returned["rev"] == 1
        project = asyncio.run(api.project("shared", None))
        assert project["project"]["name"] == "shared"
        assert project["agent_editing"] is False
        assert list(sys.path) == path_before
    finally:
        sys.modules.pop(root_name, None)
        sys.modules.pop(api_name, None)
        if parent_created:
            sys.modules.pop("hermes_plugins", None)


def test_api_error_responses_have_contract_shapes(monkeypatch, tmp_path):
    monkeypatch.setenv("ROOKERY_DATA_DIR", str(tmp_path / "data"))
    api = _load("hermes_dashboard_plugin_rookery_errors", ROOT / "dashboard" / "plugin_api.py")
    try:
        missing = asyncio.run(api.project("absent", None))
        assert isinstance(missing, JSONResponse) and missing.status_code == 404
        assert set(json.loads(missing.body)) == {"message"}

        asyncio.run(api._run("new", "beat", 90, source="user"))
        stale = asyncio.run(api.edit({"name": "beat", "op": "meta", "rev": 0, "bpm": 91}))
        assert isinstance(stale, JSONResponse) and stale.status_code == 409
        assert set(json.loads(stale.body)) == {"message", "rev"}

        invalid = asyncio.run(api.edit({"name": "beat", "op": "meta", "bpm": 0}))
        assert isinstance(invalid, JSONResponse) and invalid.status_code == 422
        assert set(json.loads(invalid.body)) == {"message"}
    finally:
        sys.modules.pop("hermes_dashboard_plugin_rookery_errors", None)


def test_async_render_endpoint_offloads_blocking_work(monkeypatch):
    api = _load("hermes_dashboard_plugin_rookery_async", ROOT / "dashboard" / "plugin_api.py")

    class SlowService:
        def render(self, name):
            time.sleep(0.15)
            return {"hash": "a" * 64, "rev": 1, "audio_url": "/audio/" + "a" * 64,
                    "report": {}, "meters": {}, "duration_samples": 44100, "sample_rate": 44100}

    monkeypatch.setattr(api._engine.service, "get_service", lambda: SlowService())

    async def run():
        started = time.perf_counter()
        task = asyncio.create_task(api.render({"name": "slow"}))
        await asyncio.sleep(0.02)
        elapsed = time.perf_counter() - started
        result = await task
        return elapsed, result

    try:
        elapsed, result = asyncio.run(run())
        assert elapsed < 0.1
        assert result["hash"] == "a" * 64
    finally:
        sys.modules.pop("hermes_dashboard_plugin_rookery_async", None)


def test_status_passes_kit_credits_through_to_the_page(monkeypatch):
    api = _load("hermes_dashboard_plugin_rookery_credits", ROOT / "dashboard" / "plugin_api.py")
    credits = {"library/skipit-horns.flac": {
        "source": "soundza", "title": "Skipit Horns", "creator": "Antronical",
        "landing_url": "https://soundza.com/sound/skipit-horns",
        "license_url": "https://soundza.com/license"}}

    class FakeService:
        def status(self):
            return {"version": "test", "corvus": {},
                    "kits": {"factory": [], "user_dir": "kits", "user": [], "credits": credits}}

    monkeypatch.setattr(api._engine.service, "get_service", lambda: FakeService())
    try:
        result = asyncio.run(api.status())
        assert result["kits"]["credits"] == credits
        assert result["kits"]["user_dir"] == "kits"
    finally:
        sys.modules.pop("hermes_dashboard_plugin_rookery_credits", None)


def test_export_endpoint_writes_export_and_validates_options(monkeypatch, tmp_path):
    monkeypatch.setenv("ROOKERY_DATA_DIR", str(tmp_path / "data"))
    api = _load("hermes_dashboard_plugin_rookery_export", ROOT / "dashboard" / "plugin_api.py")
    try:
        asyncio.run(api._run("new", "api-export", 120, source="user"))
        invalid = asyncio.run(api.export({"name": "api-export", "fps": 0}))
        assert isinstance(invalid, JSONResponse) and invalid.status_code == 422
        result = asyncio.run(api.export({"name": "api-export", "song": False,
                                         "stems": False, "midi": False, "fps": 30}))
        assert "api-export-" in result["folder"]
        assert "Use cues.json" in result["note"]
        assert any(item["path"] == "cues.json" for item in result["files"])
    finally:
        sys.modules.pop("hermes_dashboard_plugin_rookery_export", None)


def test_dashboard_module_import_defers_engine_until_first_use():
    script = """
import importlib.util, json, sys
path = sys.argv[1]
spec = importlib.util.spec_from_file_location("rookery_dashboard_lazy", path)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
heavy = [name for name in ("numpy", "scipy", "soundfile", "pyloudnorm", "pedalboard")
         if name in sys.modules]
loaded_before = module._ENGINE is not None
engine = module._get_engine()
print(json.dumps({
    "heavy_after_import": heavy,
    "loaded_before": loaded_before,
    "engine_is_shared": engine is module._engine,
    "heavy_after_call": [name for name in ("numpy", "scipy", "soundfile", "pyloudnorm", "pedalboard")
                         if name in sys.modules],
}))
"""
    proc = subprocess.run(
        [sys.executable, "-c", script, str(ROOT / "dashboard" / "plugin_api.py")],
        capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)
    assert result["heavy_after_import"] == []
    assert result["loaded_before"] is False
    assert result["engine_is_shared"] is True
    assert "soundfile" in result["heavy_after_call"]


def _call(awaitable):
    return asyncio.run(awaitable)


def test_every_route_answers_missing_project_bad_name_with_json(monkeypatch, tmp_path):
    monkeypatch.setenv("ROOKERY_DATA_DIR", str(tmp_path / "data"))
    name = "hermes_dashboard_plugin_rookery_route_errors"
    api = _load(name, ROOT / "dashboard" / "plugin_api.py")
    try:
        _call(api._run("new", "real", 90, source="user"))
        cases = [
            ("get missing", lambda: api.project("absent", None), 404),
            ("get bad name", lambda: api.project("bad name"), 422),
            ("get bad since", lambda: api.project("real", "junk"), 422),
            ("edit missing", lambda: api.edit({"name": "absent", "op": "meta", "bpm": 91}), 404),
            ("edit bad name", lambda: api.edit({"name": "bad name", "op": "meta", "bpm": 91}), 422),
            ("undo missing", lambda: api.undo({"name": "absent"}), 404),
            ("undo bad name", lambda: api.undo({"name": "bad name"}), 422),
            ("render missing", lambda: api.render({"name": "absent"}), 404),
            ("render bad name", lambda: api.render({"name": "bad name"}), 422),
            ("export missing", lambda: api.export({"name": "absent"}), 404),
            ("export bad name", lambda: api.export({"name": "bad name"}), 422),
            ("delete missing", lambda: api.delete_project("absent"), 404),
            ("delete bad name", lambda: api.delete_project("bad name"), 422),
            ("rename missing", lambda: api.rename_project("absent", {"to": "next"}), 404),
            ("rename bad name", lambda: api.rename_project("bad name", {"to": "next"}), 422),
            ("create from missing", lambda: api.create_project({"from": "absent"}), 404),
            ("create bad name", lambda: api.create_project({"name": "bad name"}), 422),
            ("audio junk hash", lambda: api.audio("not-a-hash"), 404),
            ("audio traversal", lambda: api.audio("../secret"), 404),
        ]
        for label, call, status in cases:
            response = _call(call())
            assert isinstance(response, JSONResponse), label
            assert response.status_code == status, (label, response.status_code)
            payload = json.loads(response.body)
            assert payload.get("message"), label
            assert set(payload) <= {"message", "rev"}, label
        conflict = _call(api.create_project({"name": "real"}))
        assert isinstance(conflict, JSONResponse) and conflict.status_code == 409
        assert set(json.loads(conflict.body)) == {"message", "rev"}
    finally:
        sys.modules.pop(name, None)


def test_engine_load_failure_returns_json_503_everywhere(monkeypatch):
    name = "hermes_dashboard_plugin_rookery_engine_down"
    api = _load(name, ROOT / "dashboard" / "plugin_api.py")

    def unavailable():
        raise RuntimeError("soundfile missing")

    monkeypatch.setattr(api, "_get_engine", unavailable)
    calls = [
        api.projects,
        lambda: api.project("beat", None),
        lambda: api.create_project({}),
        lambda: api.rename_project("beat", {"to": "next"}),
        lambda: api.delete_project("beat"),
        api.status,
        api.flock_catalog,
        lambda: api.edit({"name": "beat", "op": "meta", "bpm": 91}),
        lambda: api.undo({"name": "beat"}),
        lambda: api.render({"name": "beat"}),
        lambda: api.export({"name": "beat"}),
        lambda: api.audio("a" * 64),
    ]
    try:
        for call in calls:
            response = _call(call())
            assert isinstance(response, JSONResponse)
            assert response.status_code == 503
            payload = json.loads(response.body)
            assert set(payload) == {"message"}
            assert "engine unavailable" in payload["message"]
    finally:
        sys.modules.pop(name, None)


def test_render_response_carries_loop_fit_and_mix_notes(monkeypatch):
    name = "hermes_dashboard_plugin_rookery_render_fields"
    api = _load(name, ROOT / "dashboard" / "plugin_api.py")
    payload = {
        "hash": "b" * 64, "wav_hash": "c" * 64, "rev": 2, "audio_url": "/audio/" + "b" * 64,
        "report": {}, "meters": {}, "mix": {"centroid_hz": 900},
        "balance": {"bed": {"ok": True}}, "mix_notes": ["bed is 2 LU under the kick"],
        "fit": [{"a": "bed", "b": "lead", "register_overlap": 0.2, "rhythm_overlap": 0.3}],
        "ref": "kick", "duration_samples": 44100, "sample_rate": 44100,
        "flock_events": {}, "kick_onsets": [], "flock_active_combos": [],
    }

    class FakeService:
        def render(self, project_name):
            return dict(payload)

    monkeypatch.setattr(api._engine.service, "get_service", lambda: FakeService())
    try:
        result = _call(api.render({"name": "any"}))
        assert result["mix_notes"] == payload["mix_notes"]
        assert result["fit"] == payload["fit"]
        assert result["balance"] == payload["balance"]
        assert result["ref"] == "kick"
    finally:
        sys.modules.pop(name, None)
