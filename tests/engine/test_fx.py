import numpy as np
import pytest

from rookery.fx import apply_fx, corvus_status


def test_empty_and_builtin_chain_keep_stereo_length_and_reset_state():
    t = np.arange(2048, dtype=np.float32) / 44100
    audio = np.column_stack((0.2 * np.sin(2 * np.pi * 440 * t), 0.1 * np.sin(2 * np.pi * 660 * t)))
    assert np.array_equal(apply_fx(audio, [], 44100), audio)
    chain = [{"type": "delay", "delay_seconds": 0.01, "feedback": 0.2, "mix": 0.3},
             {"type": "limiter", "ceiling_db": -1.0}]
    first = apply_fx(audio, chain, 44100)
    second = apply_fx(audio, chain, 44100)
    assert first.shape == audio.shape and first.dtype == np.float32
    assert np.array_equal(first, second)


@pytest.mark.parametrize("fx", [
    [{"type": "highpass", "cutoff_frequency_hz": 100}],
    [{"type": "lowpass", "cutoff_hz": 1000}],
])
def test_cutoff_names_are_supported(fx):
    result = apply_fx(np.ones((1000, 2), dtype=np.float32) * 0.1, fx, 44100)
    assert result.shape == (1000, 2)


@pytest.mark.parametrize("fx", [
    [{"type": "unknown"}], [{"type": "highpass", "q": 0.7}],
    [{"type": "compressor", "threshold_db": float("nan")}],
])
def test_unknown_fx_settings_and_nonfinite_values_rejected(fx):
    with pytest.raises(ValueError):
        apply_fx(np.zeros((32, 2), dtype=np.float32), fx, 44100)


def test_corvus_status_is_safe_without_install():
    status = corvus_status(r"Z:\missing\DrippyFX.vst3")
    assert status["found"] is False
    assert "params" in status


def test_corvus_mapping_parameters_are_actionable_and_cache_is_deepcopied(monkeypatch, tmp_path):
    import sys
    import types

    class Descriptor:
        min_value, max_value, default_value = 0.0, 100.0, 50.0

    class Plugin:
        parameters = {"fatness": Descriptor()}

        def __init__(self):
            self.fatness = 25.0

    monkeypatch.setitem(sys.modules, "pedalboard", types.SimpleNamespace(load_plugin=lambda path: Plugin()))
    module = tmp_path / "plugin.vst3"
    module.touch()
    first = corvus_status(str(module))
    assert first["found"] is True
    assert first["params"] == [{"name": "fatness", "min": 0.0, "max": 100.0,
                                "default": 50.0, "value": 25.0}]
    first["params"][0]["value"] = -999
    assert corvus_status(str(module))["params"][0]["value"] == 25.0

    from rookery.fx import _plugin_param_info
    assert _plugin_param_info(Plugin())[0]["value"] == 25.0


class _WrappedBool:
    """Truthy wrapper like pedalboard's WrappedBool; deliberately not a bool subclass."""

    def __init__(self, value):
        self._value = value

    def __bool__(self):
        return self._value


def test_corvus_status_reports_numeric_and_boolean_controls(monkeypatch, tmp_path):
    import sys
    import types

    class Numeric:
        type = float
        min_value, max_value, default_value = 0.0, 100.0, 50.0
        range = (0.0, 100.0, None)

    class Boolean:
        type = bool
        min_value, max_value, default_value = False, True, True
        range = (False, True, 1)

    class Plugin:
        parameters = {"fatness": Numeric(), "distortion_bypass": Boolean()}

        def __init__(self):
            self.fatness = 10.0
            self.distortion_bypass = _WrappedBool(True)

    monkeypatch.setitem(sys.modules, "pedalboard", types.SimpleNamespace(load_plugin=lambda path: Plugin()))
    module = tmp_path / "plugin.vst3"
    module.touch()
    params = {row["name"]: row for row in corvus_status(str(module))["params"]}
    assert set(params) == {"fatness", "distortion_bypass"}
    assert params["fatness"] == {"name": "fatness", "min": 0.0, "max": 100.0,
                                 "default": 50.0, "value": 10.0}
    assert params["distortion_bypass"] == {"name": "distortion_bypass", "min": 0.0, "max": 1.0,
                                           "default": 1.0, "value": 1.0}


def test_make_vst_sets_boolean_controls_as_real_bools(monkeypatch, tmp_path):
    import sys
    import types

    class Numeric:
        type = float
        min_value, max_value, default_value = 0.0, 100.0, 50.0
        range = (0.0, 100.0, None)

    class Boolean:
        type = bool
        min_value, max_value, default_value = False, True, False
        range = (False, True, 1)

    class Plugin:
        parameters = {"fatness": Numeric(), "distortion_bypass": Boolean()}

        def __init__(self):
            self.fatness = 10.0
            self.distortion_bypass = _WrappedBool(False)

    monkeypatch.setitem(sys.modules, "pedalboard", types.SimpleNamespace(load_plugin=lambda path: Plugin()))
    module = tmp_path / "plugin.vst3"
    module.touch()
    from rookery.fx import _make_vst, configured_vst3

    with configured_vst3(module):
        plugin = _make_vst({"type": "vst3", "path": str(module),
                            "params": {"distortion_bypass": 1, "fatness": 10}})
        assert plugin.distortion_bypass is True
        assert plugin.fatness == 10.0
        with pytest.raises(ValueError, match="0 or 1"):
            _make_vst({"type": "vst3", "path": str(module), "params": {"distortion_bypass": 0.3}})


def test_limiter_threshold_and_ceiling_are_forwarded(monkeypatch):
    import sys
    import types

    class Limiter:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    module = types.SimpleNamespace(Chorus=object, Compressor=object, Delay=object, Distortion=object,
                                   HighpassFilter=object, Limiter=Limiter, LowpassFilter=object, Reverb=object)
    monkeypatch.setitem(sys.modules, "pedalboard", module)
    from rookery.fx import _make_plugin

    assert _make_plugin({"type": "limiter", "threshold_db": -3}).kwargs["threshold_db"] == -3
    assert _make_plugin({"type": "limiter", "ceiling_db": -8}).kwargs["threshold_db"] == -8
    with pytest.raises(ValueError, match="not both"):
        _make_plugin({"type": "limiter", "threshold_db": -3, "ceiling_db": -8})


@pytest.mark.parametrize("name", ["corvus.dll", "corvus.json", "corvus.txt"])
def test_corvus_status_rejects_non_vst3_explicit_paths_without_loading(monkeypatch, tmp_path, name):
    import sys
    import types

    calls = []
    monkeypatch.setitem(sys.modules, "pedalboard", types.SimpleNamespace(load_plugin=lambda path: calls.append(path)))
    module = tmp_path / name
    module.touch()

    status = corvus_status(str(module))
    assert status["found"] is False
    assert status["path"] is None
    assert calls == []


def test_plugin_path_rejects_invalid_explicit_suffix_without_fallback(tmp_path):
    from rookery.fx import _plugin_path

    dummy = tmp_path / "plugin.dll"
    dummy.touch()
    assert _plugin_path(str(dummy)) is None


def test_plugin_path_accepts_uppercase_vst3_suffix(tmp_path):
    from rookery.fx import _plugin_path

    module = tmp_path / "Plugin.VST3"
    module.touch()
    assert _plugin_path(str(module)) == module


def test_make_vst_rejects_non_vst3_path_before_loading(monkeypatch, tmp_path):
    import sys
    import types

    calls = []
    monkeypatch.setitem(sys.modules, "pedalboard", types.SimpleNamespace(load_plugin=lambda path: calls.append(path)))
    from rookery.fx import _make_vst

    dummy = tmp_path / "effect.json"
    dummy.touch()
    with pytest.raises(ValueError, match="vst3"):
        _make_vst({"type": "vst3", "path": str(dummy), "params": {}})
    assert calls == []


def test_distinct_limiter_thresholds_produce_distinct_audio():
    t = np.arange(4096, dtype=np.float32) / 44100
    signal = np.column_stack((0.95 * np.sin(2 * np.pi * 440 * t),) * 2)
    mild = apply_fx(signal, [{"type": "limiter", "threshold_db": -3}], 44100)
    strong = apply_fx(signal, [{"type": "limiter", "threshold_db": -20}], 44100)
    assert not np.array_equal(mild, strong)



def _fake_pedalboard(monkeypatch, calls):
    import sys
    import types

    class Plugin:
        parameters = {}

    def load_plugin(path):
        calls.append(path)
        return Plugin()

    monkeypatch.setitem(sys.modules, "pedalboard", types.SimpleNamespace(load_plugin=load_plugin))


def test_vst3_is_never_loaded_without_a_configured_path(monkeypatch, tmp_path):
    from rookery.fx import _make_vst

    calls = []
    _fake_pedalboard(monkeypatch, calls)
    module = tmp_path / "plugin.vst3"
    module.touch()
    with pytest.raises(ValueError, match="not configured"):
        _make_vst({"type": "vst3", "path": str(module), "params": {}})
    with pytest.raises(ValueError, match="not configured"):
        _make_vst({"type": "vst3", "params": {}})
    assert calls == []


def test_vst3_loads_only_the_configured_plugin(monkeypatch, tmp_path):
    from rookery.fx import _make_vst, configured_vst3

    calls = []
    _fake_pedalboard(monkeypatch, calls)
    configured = tmp_path / "Corvus.vst3"
    configured.touch()
    other = tmp_path / "Other.vst3"
    other.touch()
    with configured_vst3(configured):
        _make_vst({"type": "vst3", "params": {}})
        _make_vst({"type": "vst3", "path": str(configured), "params": {}})
        with pytest.raises(ValueError, match="configured corvus_vst3_path"):
            _make_vst({"type": "vst3", "path": str(other), "params": {}})
    assert [str(path) for path in calls] == [str(configured), str(configured)]


def test_corvus_status_has_no_hard_coded_fallback(monkeypatch):
    import rookery.fx as fx

    calls = []
    _fake_pedalboard(monkeypatch, calls)
    monkeypatch.setattr(fx.Path, "is_file", lambda self: True)
    monkeypatch.setattr(fx.Path, "is_dir", lambda self: True)
    fx._corvus_cache.clear()
    status = fx.corvus_status(None)
    assert status["found"] is False and status["configured"] is False and status["path"] is None
    assert fx._plugin_path(None) is None
    assert calls == []
    assert not hasattr(fx, "_CORVUS_DEFAULT")


def test_vst3_tool_schema_has_no_model_supplied_path():
    import json
    from pathlib import Path

    from rookery.tools import SCHEMAS

    text = json.dumps(SCHEMAS)
    vst = [item for item in json.loads(text)["rookery_mix"]["parameters"]["properties"]["fx"]["items"]["oneOf"]
           if item["properties"]["type"].get("const") == "vst3"]
    assert vst and "path" not in vst[0]["properties"] and vst[0]["required"] == ["type"]
    generated = json.loads((Path(__file__).resolve().parents[2] / "rookery" / "tool_schemas.json").read_text(encoding="utf-8"))
    assert '"vst3"' in json.dumps(generated) and "Installed VST3 module path" not in json.dumps(generated)


def test_soundza_key_is_read_through_the_hermes_secret_scope(monkeypatch):
    import sys
    import types

    from rookery import soundza

    seen = []
    scope = types.ModuleType("agent.secret_scope")
    scope.get_secret = lambda name, default=None: seen.append(name) or "profile-key"
    package = types.ModuleType("agent")
    package.secret_scope = scope
    monkeypatch.setitem(sys.modules, "agent", package)
    monkeypatch.setitem(sys.modules, "agent.secret_scope", scope)
    monkeypatch.setenv("SOUNDZA_API_KEY", "process-env-key")
    assert soundza._api_key() == "profile-key"
    assert seen == ["SOUNDZA_API_KEY"]
