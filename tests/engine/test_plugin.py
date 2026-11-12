import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


class FakePluginContext:
    def __init__(self):
        self.tools = {}

    def register_tool(self, *, name, toolset, schema, handler):
        self.tools[name] = {
            "toolset": toolset,
            "schema": schema,
            "handler": handler,
        }


def _load_plugin(name="rookery_plugin"):
    spec = importlib.util.spec_from_file_location(
        name,
        ROOT / "__init__.py",
        submodule_search_locations=[str(ROOT)],
    )
    plugin = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = plugin
    spec.loader.exec_module(plugin)
    return plugin


def test_registers_exact_eleven_tools_and_runs_round_trip(monkeypatch, tmp_path):
    monkeypatch.setenv("ROOKERY_DATA_DIR", str(tmp_path / "data"))
    plugin = _load_plugin()
    try:
        ctx = FakePluginContext()
        plugin.register(ctx)

        expected = {
            "rookery_new", "rookery_steps", "rookery_track", "rookery_mix",
            "rookery_apply", "rookery_render", "rookery_state", "rookery_undo",
            "rookery_kits", "rookery_export", "rookery_samples",
        }
        assert set(ctx.tools) == expected
        manifest_tools = {
            line.strip()[2:]
            for line in (ROOT / "plugin.yaml").read_text(encoding="utf-8").splitlines()
            if line.startswith("  - ")
        }
        assert manifest_tools == expected
        schemas = json.loads((ROOT / "rookery" / "tool_schemas.json").read_text(encoding="utf-8"))
        assert tuple(ctx.tools) == plugin.TOOL_NAMES == tuple(schemas)
        for name, tool in ctx.tools.items():
            assert tool["toolset"] == "rookery"
            assert tool["schema"]["name"] == name
            assert tool["schema"]["description"]
            assert tool["schema"]["parameters"]["type"] == "object"
            for field, spec in tool["schema"]["parameters"]["properties"].items():
                assert spec.get("description"), (name, field)

        made = json.loads(ctx.tools["rookery_new"]["handler"](
            {"name": "dusty", "bpm": 90, "genre": "boom-bap"}
        ))
        assert made["rev"] == 1
        edited = json.loads(ctx.tools["rookery_steps"]["handler"](
            {"track": "kick", "steps": "x...x...x...x..."}
        ))
        assert edited["rev"] == 2
        assert edited["changed"] == ["kick steps changed (20 steps)"]
        state = json.loads(ctx.tools["rookery_state"]["handler"]({}))
        assert "kick" in state and "rev 2" in state
        undone = json.loads(ctx.tools["rookery_undo"]["handler"]({}))
        assert undone["rev"] == 3
        changed = json.loads(ctx.tools["rookery_track"]["handler"](
            {"action": "set", "id": "master", "swing": 0.5}
        ))
        assert changed["changed"] == ["swing changed"]
        state = json.loads(ctx.tools["rookery_state"]["handler"]({}))
        assert "swing 0.5" in state
        undone = json.loads(ctx.tools["rookery_undo"]["handler"]({}))
        assert undone["changed"] == ["swing changed"]
        assert len(ctx.tools) == 11
        assert "choke_group" in ctx.tools["rookery_track"]["schema"]["parameters"]["properties"]
        opened = json.loads(ctx.tools["rookery_track"]["handler"](
            {"action": "add", "id": "openhat", "kind": "drum",
             "source": "factory:hat_open", "choke_group": "hats"}
        ))
        assert "openhat added" in opened["changed"]
        state = json.loads(ctx.tools["rookery_state"]["handler"]({}))
        assert '"choke_group":"hats"' in state

        assert "rookery_flock" not in ctx.tools
        apply_ops = ctx.tools["rookery_apply"]["schema"]["parameters"]["properties"]["ops"]["items"]
        assert "flock" not in apply_ops["properties"]["op"]["enum"]
        blocked = json.loads(ctx.tools["rookery_apply"]["handler"]({
            "ops": [{"op": "flock", "action": "perch", "bird": "bramble"}],
        }))
        assert "Flock is user-controlled" in blocked["error"]
        assert '"op":"steps"' in blocked["error"]
    finally:
        sys.modules.pop(plugin.__name__, None)


def test_new_tool_accepts_a_project_key_and_scale(monkeypatch, tmp_path):
    monkeypatch.setenv("ROOKERY_DATA_DIR", str(tmp_path / "data"))
    plugin = _load_plugin("rookery_plugin_song_key")
    try:
        ctx = FakePluginContext()
        plugin.register(ctx)
        key_schema = ctx.tools["rookery_new"]["schema"]["parameters"]["properties"]
        assert key_schema["key"]["enum"] and key_schema["scale"]["enum"] == ["major", "minor"]
        made = json.loads(ctx.tools["rookery_new"]["handler"](
            {"name": "keyed", "bpm": 92, "key": "Bb", "scale": "minor"}
        ))
        assert "key changed" in made["changed"]
        assert "scale changed" in made["changed"]
        state = json.loads(ctx.tools["rookery_state"]["handler"]({}))
        assert "key A# minor" in state
    finally:
        sys.modules.pop(plugin.__name__, None)


def test_render_tool_returns_json_snapshot_and_media_line(monkeypatch, tmp_path):
    monkeypatch.setenv("ROOKERY_DATA_DIR", str(tmp_path / "data"))
    plugin = _load_plugin("rookery_plugin_render")
    try:
        ctx = FakePluginContext()
        plugin.register(ctx)
        ctx.tools["rookery_new"]["handler"]({"name": "rendered", "bpm": 90, "genre": "boom-bap"})
        result = ctx.tools["rookery_render"]["handler"]({"name": "rendered"})
        payload, media = result.split("\nMEDIA:", 1)
        snapshot = json.loads(payload)
        assert snapshot["name"] == "rendered"
        assert snapshot["rev"] == 1
        assert snapshot["tracks"][0]["steps"] == "x.....x...x....." * 4
        assert snapshot["path"] == media
        assert Path(media).is_absolute()
        assert set(snapshot["meters"])
        assert snapshot["fit"] == []
        assert snapshot["mix"]["bands_pct"]["mid"] >= 0.0
        assert -1.0 <= snapshot["mix"]["correlation"] <= 1.0
    finally:
        sys.modules.pop(plugin.__name__, None)


AUDIO_STACK = ("numpy", "scipy", "soundfile", "pyloudnorm", "pedalboard")


def _manifest_tools():
    names = []
    inside = False
    for line in (ROOT / "plugin.yaml").read_text(encoding="utf-8").splitlines():
        if line.strip() == "provides_tools:":
            inside = True
            continue
        if inside:
            if line.strip() and not line.startswith((" ", "\t")):
                break
            if line.strip().startswith("- "):
                names.append(line.strip()[2:].strip())
    return names


def test_tool_schemas_json_matches_engine_and_manifest():
    from rookery import tools

    data = json.loads((ROOT / "rookery" / "tool_schemas.json").read_text(encoding="utf-8"))
    assert list(data) == _manifest_tools()
    assert data == tools.SCHEMAS
    plugin = _load_plugin("rookery_plugin_schemas")
    try:
        assert list(plugin.TOOL_NAMES) == list(data)
    finally:
        sys.modules.pop(plugin.__name__, None)


def test_register_does_not_import_audio_stack_in_fresh_process():
    script = """
import importlib.util, json, sys, time
root = sys.argv[1]
spec = importlib.util.spec_from_file_location(
    "rookery_plugin_cold", root + "/__init__.py", submodule_search_locations=[root])
plugin = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = plugin
spec.loader.exec_module(plugin)

class Context:
    def __init__(self):
        self.tools = {}
    def register_tool(self, *, name, toolset, schema, handler):
        self.tools[name] = {"toolset": toolset, "schema": schema, "handler": handler}

ctx = Context()
started = time.perf_counter()
plugin.register(ctx)
elapsed = time.perf_counter() - started
heavy = [name for name in ("numpy", "scipy", "soundfile", "pyloudnorm", "pedalboard")
         if name in sys.modules]
engine_modules = sorted(name for name in sys.modules
                        if "rookery" in name and name.rsplit(".", 1)[-1] in
                        {"service", "project", "tools", "export", "render", "mix", "samples"})
print(json.dumps({"seconds": elapsed, "heavy": heavy, "engine_modules": engine_modules,
                  "tools": list(ctx.tools)}))
"""
    proc = subprocess.run(
        [sys.executable, "-c", script, str(ROOT)],
        capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)
    assert result["heavy"] == []
    assert result["engine_modules"] == []
    assert result["tools"] == _manifest_tools()
    # Hermes abandons a plugin whose import + register() exceeds 10 s; this is
    # orders of magnitude tighter so a regressed eager import is obvious.
    assert result["seconds"] < 1.0, result["seconds"]


def test_first_lazy_call_matches_direct_handler(monkeypatch, tmp_path):
    monkeypatch.setenv("ROOKERY_DATA_DIR", str(tmp_path / "data"))
    plugin = _load_plugin("rookery_plugin_lazy")
    try:
        ctx = FakePluginContext()
        plugin.register(ctx)
        assert plugin._ENGINE is None

        made = json.loads(ctx.tools["rookery_new"]["handler"](
            {"name": "parity", "bpm": 90, "genre": "boom-bap"}
        ))
        assert made["rev"] == 1
        engine = plugin.load_engine(ROOT)
        direct = engine.tools.make_handler(engine, "rookery_state")
        lazy = ctx.tools["rookery_state"]["handler"]
        assert lazy({}) == direct({"name": "parity"})
        assert lazy({"name": "parity"}) == direct({"name": "parity"})
    finally:
        sys.modules.pop(plugin.__name__, None)
